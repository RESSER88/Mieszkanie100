#!/usr/bin/env python3
"""Transaction prices around a street, from the SQLite DB built by rcn_import.py.

Every statistic is reported with its sample size and period. Missing data is
reported as missing, never as a low price. Distances are planar metres in
EPSG:2180 (northing, easting), accurate to well under 0.1% at this scale.
Standard library only (Python 3.8+).
"""
import argparse
import calendar
import math
import sqlite3
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

MIN_SAMPLE = 10
MARKETS = (("rynekWtorny", "Rynek wtórny"), ("rynekPierwotny", "Rynek pierwotny"))
_PREFIXES = ("ul.", "al.", "pl.", "os.", "ulica", "aleja", "plac", "osiedle")


def _norm_street(text: str) -> str:
    text = " ".join(text.casefold().split())
    for prefix in _PREFIXES:
        if text.startswith(prefix + " "):
            return text[len(prefix) + 1:]
    return text


def find_center(con: sqlite3.Connection, street: str,
                city: str = "Katowice") -> Optional[Tuple[float, float, int]]:
    """Mean (northing, easting, n) of records on the street; None if there are none."""
    needle, city_key = _norm_street(street), city.casefold()
    ys, xs = [], []
    for name, town, y, x in con.execute(
            "SELECT ulica, miejscowosc, y_pl1992, x_pl1992 FROM lokale"
            " WHERE ulica IS NOT NULL AND y_pl1992 IS NOT NULL AND x_pl1992 IS NOT NULL"):
        if (town or "").casefold() == city_key and needle in _norm_street(name):
            ys.append(y)
            xs.append(x)
    if not ys:
        return None
    return sum(ys) / len(ys), sum(xs) / len(xs), len(ys)


def transactions_in_radius(con: sqlite3.Connection, center: Tuple[float, float], radius_m: float,
                           date_from: str, date_to: str, area_min: Optional[float] = None,
                           area_max: Optional[float] = None) -> Tuple[List[dict], int]:
    """Records with a price per m2 inside the radius and date window, each transaction once.

    Returns (rows, skipped) where skipped counts priced rows in the window that have
    no coordinates and so could not be placed.
    """
    cy, cx = center
    sql = ("SELECT gid, tran_id, obj_id, dok_data, rodzaj_rynku, liczba_izb, pow_m2, cena_m2, obj_cena,"
           " ulica, nr, y_pl1992, x_pl1992 FROM lokale WHERE dok_data BETWEEN ? AND ?"
           " AND cena_m2 IS NOT NULL")
    params: list = [date_from, date_to]
    if area_min is not None:
        sql += " AND pow_m2 >= ?"
        params.append(area_min)
    if area_max is not None:
        sql += " AND pow_m2 <= ?"
        params.append(area_max)
    cols = ("gid", "tran_id", "obj_id", "dok_data", "rodzaj_rynku", "liczba_izb", "pow_m2", "cena_m2",
            "obj_cena", "ulica", "nr", "y_pl1992", "x_pl1992")
    latest: Dict[object, dict] = {}
    skipped = 0
    for values in con.execute(sql, params):
        row = dict(zip(cols, values))
        if row["y_pl1992"] is None or row["x_pl1992"] is None:
            skipped += 1
            continue
        distance = math.hypot(row["y_pl1992"] - cy, row["x_pl1992"] - cx)
        if distance > radius_m:
            continue
        row["odleglosc_m"] = distance
        key = (row["tran_id"], row["obj_id"]) if row["tran_id"] is not None else row["gid"]
        if key not in latest or row["gid"] > latest[key]["gid"]:
            latest[key] = row
    return sorted(latest.values(), key=lambda r: r["odleglosc_m"]), skipped


@dataclass
class Summary:
    n: int
    period_from: Optional[str]
    period_to: Optional[str]
    median_m2: Optional[float]
    p25_m2: Optional[float]
    p75_m2: Optional[float]
    min_m2: Optional[float]
    max_m2: Optional[float]
    median_price: Optional[float]
    status: str    # "ok", "za_mala_proba" or "brak_danych"


def _percentile(sorted_values: List[float], p: float) -> float:
    pos = p * (len(sorted_values) - 1)
    low = int(math.floor(pos))
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)


def summarize(rows: List[dict], min_sample: int = MIN_SAMPLE) -> Summary:
    if not rows:
        return Summary(0, None, None, None, None, None, None, None, None, "brak_danych")
    values = sorted(float(r["cena_m2"]) for r in rows)
    dates = sorted(r["dok_data"] for r in rows if r.get("dok_data"))
    prices = [float(r["obj_cena"]) for r in rows if r.get("obj_cena") is not None]
    return Summary(
        n=len(values), period_from=dates[0] if dates else None, period_to=dates[-1] if dates else None,
        median_m2=statistics.median(values), p25_m2=_percentile(values, 0.25),
        p75_m2=_percentile(values, 0.75), min_m2=values[0], max_m2=values[-1],
        median_price=statistics.median(prices) if prices else None,
        status="ok" if len(values) >= min_sample else "za_mala_proba")


def months_ago(today: date, months: int) -> date:
    year, month0 = divmod(today.year * 12 + today.month - 1 - months, 12)
    month = month0 + 1
    return date(year, month, min(today.day, calendar.monthrange(year, month)[1]))


def _zl(value: Optional[float]) -> str:
    return "brak" if value is None else "{:,.0f}".format(value).replace(",", " ")


def format_report(street: str, center_n: int, radius_m: float, date_from: str, date_to: str,
                  area_min: Optional[float], area_max: Optional[float],
                  summaries: List[Tuple[str, Summary]], skipped: int) -> str:
    area = "dowolna" if area_min is None and area_max is None else "%s..%s m2" % (
        "?" if area_min is None else "%g" % area_min, "?" if area_max is None else "%g" % area_max)
    lines = [
        "Okolica: %s (środek z %d rekordów), promień %g m" % (street, center_n, radius_m),
        "Okno: %s .. %s (daty dokumentów, nie pewne daty transakcji). Powierzchnia: %s" % (
            date_from, date_to, area),
        "",
    ]
    for label, s in summaries:
        if s.status == "brak_danych":
            lines.append("%s: BRAK DANYCH w tym oknie i promieniu (to nie znaczy, że ceny są niskie)." % label)
        else:
            lines.append("%s: próbka %d transakcji, okres %s .. %s" % (label, s.n, s.period_from, s.period_to))
            lines.append("  mediana %s zł/m2, typowy zakres (25.-75. percentyl) %s .. %s zł/m2, min %s, max %s" % (
                _zl(s.median_m2), _zl(s.p25_m2), _zl(s.p75_m2), _zl(s.min_m2), _zl(s.max_m2)))
            lines.append("  mediana ceny transakcji %s zł" % _zl(s.median_price))
            if s.status == "za_mala_proba":
                lines.append("  UWAGA: próbka poniżej %d transakcji, mediana może wprowadzać w błąd." % MIN_SAMPLE)
        lines.append("")
    if skipped:
        lines.append("Pominięto %d rekordów bez współrzędnych (nie da się ich przypisać do okolicy)." % skipped)
    lines.append("Źródło: Rejestr Cen Nieruchomości (RCN). Ceny z aktów notarialnych, nie ceny ofertowe.")
    return "\n".join(lines)


def _positive(kind):
    def parse(text):
        value = kind(text)
        if value <= 0:
            raise argparse.ArgumentTypeError("musi być większe od zera")
        return value
    return parse


def main(argv=None, today: Optional[date] = None) -> int:
    p = argparse.ArgumentParser(description="Ceny transakcyjne w promieniu od ulicy (RCN).")
    p.add_argument("--db", default="rcn_test.sqlite")
    p.add_argument("--street", required=True, help="np. 'Braci Mniejszych'")
    p.add_argument("--city", default="Katowice")
    p.add_argument("--radius", type=_positive(float), default=500.0, help="promień w metrach")
    p.add_argument("--months", type=_positive(int), default=24, help="ile ostatnich miesięcy")
    p.add_argument("--area-min", type=float, default=None)
    p.add_argument("--area-max", type=float, default=None)
    args = p.parse_args(argv)

    today = today or date.today()
    date_from, date_to = months_ago(today, args.months).isoformat(), today.isoformat()
    con = sqlite3.connect(args.db)
    try:
        center = find_center(con, args.street, args.city)
        if center is None:
            print("BŁĄD: nie znaleziono ulicy '%s' w miejscowości %s w bazie." % (args.street, args.city),
                  file=sys.stderr)
            return 2
        rows, skipped = transactions_in_radius(
            con, center[:2], args.radius, date_from, date_to, args.area_min, args.area_max)
    finally:
        con.close()
    summaries = [(label, summarize([r for r in rows if r["rodzaj_rynku"] == key])) for key, label in MARKETS]
    print(format_report(args.street, center[2], args.radius, date_from, date_to,
                        args.area_min, args.area_max, summaries, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
