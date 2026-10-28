#!/usr/bin/env python3
"""Offer card: one listing set against RCN sales around its coordinates and OSM surroundings.

Usage on the Pi:  python3 rcn/karta.py URL [--file saved.html] --rcn-db rcn_test.sqlite --osm-db osm_slask.sqlite
Comparables are residential free-market sales of a similar size (default ±30% of the
offer's area) within the radius and period. Asking prices and sale prices are shown side
by side, never mixed into one statistic. Standard library only.
"""
import argparse
import os
import sqlite3
import sys
import urllib.parse
from datetime import date
from typing import Any, Dict, Optional

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rcn import okolica, otoczenie, portale  # noqa: E402
from rcn.oferta import clean_url, fetch, save_html  # noqa: E402

MARKET_KEYS = {"wtorny": "rynekWtorny", "pierwotny": "rynekPierwotny"}
NEAREST = 5


class CardError(Exception):
    """The card cannot be built without guessing (e.g. no coordinates in the listing)."""


def build_card(offer: Dict[str, Any], rcn_con: sqlite3.Connection, osm_con: Optional[sqlite3.Connection] = None,
               radius_m: float = 500.0, months: int = 24, area_tol: float = 0.3,
               osm_radius_m: float = 3000.0, today: Optional[date] = None) -> Dict[str, Any]:
    if offer.get("y_pl1992") is not None and offer.get("x_pl1992") is not None:
        center = (offer["y_pl1992"], offer["x_pl1992"])
    elif offer.get("lat") is not None and offer.get("lon") is not None:
        center = otoczenie.wgs84_to_pl1992(offer["lat"], offer["lon"])
    else:
        raise CardError("ogłoszenie nie podaje współrzędnych; ustalenie położenia z adresu jest dopiero w planie")
    today = today or date.today()
    date_from, date_to = okolica.months_ago(today, months).isoformat(), today.isoformat()
    area = offer.get("powierzchnia_m2")
    area_min, area_max = (area * (1 - area_tol), area * (1 + area_tol)) if area else (None, None)
    rows, excluded = okolica.transactions_in_radius(rcn_con, center, radius_m, date_from, date_to, area_min, area_max)
    summaries = [(label, okolica.summarize([r for r in rows if r["rodzaj_rynku"] == key]))
                 for key, label in okolica.MARKETS]
    market = MARKET_KEYS.get(offer.get("rynek") or "", "rynekWtorny")
    label = dict(okolica.MARKETS)[market]
    summary = dict(summaries)[label]
    position, cheaper = None, None
    price = offer.get("cena_m2")
    if price is not None and summary.status != "brak_danych":
        if price < summary.p25_m2:
            position = "poniżej typowego zakresu"
        elif price > summary.p75_m2:
            position = "powyżej typowego zakresu"
        else:
            position = "w typowym zakresie"
        same = [r["cena_m2"] for r in rows if r["rodzaj_rynku"] == market]
        cheaper = round(100.0 * sum(1 for v in same if v < price) / len(same), 1)
    surroundings = otoczenie.nearby(osm_con, center, osm_radius_m) if osm_con is not None else None
    return {"oferta": offer, "promien_m": radius_m, "okno": (date_from, date_to), "zakres_m2": (area_min, area_max),
            "porownanie": summaries, "rynek_porownania": market, "polozenie": position, "odsetek_tanszych": cheaper,
            "najblizsze": rows[:NEAREST], "odrzucone": excluded, "otoczenie": surroundings,
            "promien_otoczenia_m": osm_radius_m}


def _num(value: Optional[float], digits: int = 0) -> str:
    if value is None:
        return "brak"
    text = "{:,.{d}f}".format(value, d=digits).replace(",", " ")
    return text.replace(".", ",")


def format_card(card: Dict[str, Any]) -> str:
    o = card["oferta"]
    market_text = {"wtorny": "rynek wtórny", "pierwotny": "rynek pierwotny"}.get(o.get("rynek") or "", "rynek nieznany")
    lines = [
        "Karta mieszkania (%s, ogłoszenie %s)" % (o["portal"], o.get("id") or "bez numeru"),
        "%s" % (o.get("tytul") or ""),
        "Oferta: %s zł, %s m², %s zł/m² (cena ofertowa), pokoje: %s, piętro: %s, %s" % (
            _num(o.get("cena")), _num(o.get("powierzchnia_m2"), 2), _num(o.get("cena_m2")),
            o.get("pokoje") if o.get("pokoje") is not None else "brak",
            o.get("pietro") if o.get("pietro") is not None else "brak", market_text),
        "Adres: %s, %s%s; rok budowy %s" % (o.get("ulica") or "brak ulicy", o.get("miejscowosc") or "brak miejscowości",
                                            ", " + o["dzielnica"] if o.get("dzielnica") else "",
                                            o.get("rok_budowy") or "nieznany"),
    ]
    if o.get("inwestycja"):
        lines.append("Inwestycja: %s" % o["inwestycja"])
    if o.get("wzmianki"):
        mentions = ", ".join("%s%s" % (k, "" if v is True else " %g m²" % v if isinstance(v, float) else " %s" % v)
                             for k, v in o["wzmianki"].items())
        source = {"opis": "z opisu", "opis i cechy ogłoszenia": "z opisu i listy cech ogłoszenia"}.get(
            o.get("wzmianki_zrodlo"), "z całej strony, mniej pewne")
        lines.append("Wzmianki w treści ogłoszenia (%s): %s" % (source, mentions))
    if o.get("polozenie_uwaga"):
        lines.append(o["polozenie_uwaga"])
    if o.get("lokalizacja_przyblizona"):
        lines.append("Lokalizacja w ogłoszeniu jest przybliżona, więc promień liczony jest od przybliżonego punktu.")
    area_min, area_max = card["zakres_m2"]
    lines += ["", "Na tle sprzedaży (RCN, akty notarialne) w promieniu %g m, %s .. %s, lokale %s m²:" % (
        card["promien_m"], card["okno"][0], card["okno"][1],
        "dowolne" if area_min is None else "%s–%s" % (_num(area_min), _num(area_max)))]
    for label, s in card["porownanie"]:
        if s.status == "brak_danych":
            lines.append("  %s: BRAK DANYCH (to nie znaczy, że ceny są niskie)" % label)
            continue
        lines.append("  %s: próbka %d, okres %s .. %s, mediana %s zł/m², typowy zakres %s–%s zł/m²%s" % (
            label, s.n, s.period_from, s.period_to, _num(s.median_m2), _num(s.p25_m2), _num(s.p75_m2),
            ", UWAGA: za mała próba" if s.status == "za_mala_proba" else ""))
    compared = dict(okolica.MARKETS)[card["rynek_porownania"]].lower()
    if card["polozenie"]:
        lines.append("Wynik: cena ofertowa %s zł/m² jest %s (%s; tańszych sprzedaży: %s%%)." % (
            _num(o.get("cena_m2")), card["polozenie"], compared, _num(card["odsetek_tanszych"], 1)))
    else:
        lines.append("Wynik: brak porównania (%s bez danych lub oferta bez ceny za m²)." % compared)
    if not o.get("rynek"):
        lines.append("Ogłoszenie nie podaje rynku, porównanie z rynkiem wtórnym.")
    lines.append("To porównanie ceny ofertowej z cenami transakcyjnymi, a nie wycena. Porównanie nie filtruje"
                 " jeszcze wg wieku budynku.")
    dropped = ["%s: %d" % (lab, card["odrzucone"].get(key, 0)) for key, lab in okolica.EXCLUSIONS
               if card["odrzucone"].get(key)]
    if dropped:
        lines.append("Odrzucono z porównania: " + ", ".join(dropped) + ".")
    lines += ["", "Najbliższe sprzedaże:"]
    for r in card["najblizsze"] or []:
        lines.append("  %4.0f m  %s %s, %s m², %s zł/m², %s, %s" % (
            r["odleglosc_m"], r.get("ulica") or "", r.get("nr") or "", _num(r.get("pow_m2"), 1),
            _num(r.get("cena_m2")), r.get("dok_data"), "pierwotny" if r["rodzaj_rynku"] == "rynekPierwotny" else "wtórny"))
    if not card["najblizsze"]:
        lines.append("  brak w promieniu i okresie")
    if card["otoczenie"] is not None:
        lines += ["", otoczenie.format_report("punkt z ogłoszenia", card["promien_otoczenia_m"], card["otoczenie"])]
    return "\n".join(lines)


def _offer_from_link(args) -> Optional[Dict[str, Any]]:
    try:
        url = clean_url(args.url)
    except ValueError as exc:
        print("BŁĄD: %s" % exc, file=sys.stderr)
        return None
    if "olx.pl" in urllib.parse.urlsplit(url).netloc and not args.file:
        # OLX listing pages answer 403; use the stored search result instead.
        from rcn.olx import OfferStore
        store = OfferStore(args.oferty_db)
        try:
            offer = store.find_by_url(url)
        finally:
            store.close()
        if offer is None:
            print("BŁĄD: tej oferty OLX nie ma w zapisanych wynikach. Najpierw uruchom"
                  " `python3 rcn/olx.py szukaj` (strony ogłoszeń OLX odmawiają pobrania).", file=sys.stderr)
        return offer
    if args.file:
        try:
            with open(args.file, encoding="utf-8", errors="replace") as f:
                html = f.read()
        except OSError:
            print("BŁĄD: nie ma pliku %s (nazwę pokazuje linia „Zapisano:” w wyniku probe)" % args.file,
                  file=sys.stderr)
            return None
    else:
        status, html = fetch(url)
        if status != 200 or html is None:
            print("BŁĄD: portal zwrócił HTTP %d. Nie ponawiać w pętli. Można zapisać stronę w przeglądarce"
                  " i podać ją przez --file albo wpisać dane ręcznie (--ulica, --cena, --metraz)." % status,
                  file=sys.stderr)
            return None
        save_html(url, html, os.path.join("ref", "oferty"))
    return portale.parse_listing(html, url)


def _manual_offer(args) -> Optional[Dict[str, Any]]:
    """Offer typed in by hand; position is the mean of RCN records on the street (approximate)."""
    rcn = sqlite3.connect(args.rcn_db)
    try:
        center = okolica.find_center(rcn, args.ulica, args.miasto)
    finally:
        rcn.close()
    if center is None:
        return None
    cena, metraz = portale.to_number(args.cena), portale.to_number(args.metraz)
    return {"portal": "wpis ręczny", "id": None, "url": None, "tytul": None, "cena": cena,
            "powierzchnia_m2": metraz, "cena_m2": round(cena / metraz, 2) if cena and metraz else None,
            "pokoje": None, "pietro": None, "rok_budowy": args.rok, "rynek": args.rynek, "ulica": args.ulica,
            "miejscowosc": args.miasto, "dzielnica": None, "lat": None, "lon": None,
            "y_pl1992": center[0], "x_pl1992": center[1], "lokalizacja_przyblizona": False, "wzmianki": {},
            "wzmianki_zrodlo": None, "brakuje": [],
            "polozenie_uwaga": "Położenie przybliżone: środek ulicy %s z %d rekordów RCN." % (args.ulica, center[2])}


def main(argv=None, today: Optional[date] = None) -> int:
    p = argparse.ArgumentParser(description="Karta mieszkania z linku do ogłoszenia albo z danych wpisanych ręcznie.")
    p.add_argument("url", nargs="?")
    p.add_argument("--file", help="zapisana strona ogłoszenia (bez pobierania z internetu)")
    p.add_argument("--cena", help="wpis ręczny: cena ofertowa w zł")
    p.add_argument("--metraz", help="wpis ręczny: powierzchnia w m²")
    p.add_argument("--ulica", help="wpis ręczny: ulica, położenie ze środka ulicy w bazie RCN")
    p.add_argument("--miasto", default="Katowice")
    p.add_argument("--rynek", choices=["wtorny", "pierwotny"])
    p.add_argument("--rok", type=int, help="wpis ręczny: rok budowy")
    p.add_argument("--rcn-db", default="rcn_test.sqlite")
    p.add_argument("--osm-db", default="osm_slask.sqlite")
    p.add_argument("--oferty-db", default="oferty.sqlite", help="zapisane wyniki wyszukiwania OLX (rcn/olx.py)")
    p.add_argument("--radius", type=float, default=500.0)
    p.add_argument("--months", type=int, default=24)
    p.add_argument("--area-tol", type=float, default=0.3, help="dopuszczalna różnica metrażu, ułamek (0.3 = 30%%)")
    args = p.parse_args(argv)
    if args.ulica:
        if not (args.cena and args.metraz):
            print("BŁĄD: wpis ręczny wymaga --cena, --metraz i --ulica", file=sys.stderr)
            return 2
        offer = _manual_offer(args)
        if offer is None:
            print("BŁĄD: nie znaleziono ulicy '%s' w miejscowości %s w bazie RCN." % (args.ulica, args.miasto),
                  file=sys.stderr)
            return 2
    elif args.url:
        offer = _offer_from_link(args)
        if offer is None:
            return 2
    else:
        print("BŁĄD: podaj link do ogłoszenia albo --ulica, --cena i --metraz", file=sys.stderr)
        return 2
    rcn = sqlite3.connect(args.rcn_db)
    osm = otoczenie.connect(args.osm_db) if os.path.exists(args.osm_db) else None
    try:
        card = build_card(offer, rcn, osm, args.radius, args.months, args.area_tol, today=today)
    except CardError as exc:
        print("BŁĄD: %s. Brakuje: %s" % (exc, ", ".join(offer["brakuje"]) or "-"), file=sys.stderr)
        return 2
    finally:
        rcn.close()
        if osm is not None:
            osm.close()
    print(format_card(card))
    return 0


if __name__ == "__main__":
    sys.exit(main())
