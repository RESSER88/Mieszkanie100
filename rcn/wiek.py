#!/usr/bin/env python3
"""Approximate building age from RCN sales, and a check of whether that is usable.

The unit id (LOK_ID_LOKALU) looks like 246901_1.0003.AR_45.14/15.5_BUD.69_LOK: the part
before _BUD is the parcel, the number after BUD. differs per unit (checked on the Pi: one
staircase at Szurmana 10 has BUD.13 to BUD.74). A building is therefore the parcel plus the
address (street and number); a unit without an address is grouped by parcel. RCN starts in 2012, so:
- the first sale in a building is a secondary-market sale before the cutoff year:
  the building already stood then, so it is older than the limit (certain);
- the first sale is a primary-market sale in or after the cutoff year: the building is
  roughly that new (developers often sell before completion, so the year is approximate);
- the first sale is a primary-market sale up to two years before the cutoff: borderline;
- otherwise unknown (never old just because data are missing).

Usage on the Pi:  python3 rcn/wiek.py diag --ulica "Szurmana" --ulica "Braci Mniejszych"
"""
import argparse
import collections
import os
import re
import sqlite3
import sys
from datetime import date
from typing import Any, Dict, Optional, Tuple

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rcn.okolica import _norm_street  # noqa: E402

YEARS = 10
LABELS = ("do 10 lat (szacunek)", "granica około 10 lat", "ponad 10 lat", "nieznany")
_PARCEL = re.compile(r"^(.+?)_BUD\.")


def parcel_of(unit_id: Optional[str]) -> Optional[str]:
    match = _PARCEL.match(unit_id or "")
    return match.group(1) if match else None


def building_key(unit_id: Optional[str], street: Optional[str], number: Optional[str]) -> Optional[str]:
    parcel = parcel_of(unit_id)
    if parcel is None:
        return None
    address = _norm_street(" ".join(p for p in (street, number) if p))
    return parcel + "|" + address if address else parcel


def building_stats(con: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    """Per building: number of sales, primary sales, first sale date overall and by market, address."""
    stats: Dict[str, Dict[str, Any]] = {}
    addresses: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for unit_id, day, market, street, number in con.execute(
            "SELECT obj_id, dok_data, rodzaj_rynku, ulica, nr FROM lokale WHERE dok_data IS NOT NULL"):
        key = building_key(unit_id, street, number)
        if key is None:
            continue
        s = stats.setdefault(key, {"sprzedaze": 0, "pierwotne": 0, "pierwsza": None, "pierwsza_pierwotna": None,
                                   "pierwsza_wtorna": None})
        s["sprzedaze"] += 1
        s["pierwsza"] = min(filter(None, (s["pierwsza"], day)))
        if market == "rynekPierwotny":
            s["pierwotne"] += 1
            s["pierwsza_pierwotna"] = min(filter(None, (s["pierwsza_pierwotna"], day)))
        elif market == "rynekWtorny":
            s["pierwsza_wtorna"] = min(filter(None, (s["pierwsza_wtorna"], day)))
        addresses[key][" ".join(p for p in (street, number) if p)] += 1
    for key, s in stats.items():
        s["adres"] = addresses[key].most_common(1)[0][0] if addresses[key] else ""
    return stats


def classify(s: Dict[str, Any], today_year: int, years: int = YEARS) -> Tuple[str, Optional[int]]:
    cutoff = today_year - years
    first_year = int(s["pierwsza"][:4])
    primary_year = int(s["pierwsza_pierwotna"][:4]) if s["pierwsza_pierwotna"] else None
    first_is_primary = s["pierwsza_pierwotna"] is not None and s["pierwsza_pierwotna"] == s["pierwsza"]
    if first_is_primary and primary_year >= cutoff:
        return LABELS[0], primary_year
    if first_is_primary and primary_year >= cutoff - 2:
        return LABELS[1], primary_year
    if first_year < cutoff:
        return LABELS[2], None
    return LABELS[3], None


def age_index(con: sqlite3.Connection, today_year: int) -> Dict[str, Dict[str, Any]]:
    """Building key -> {"wiek": label, "rok": approximate year or None, "stal_w": first sale year}."""
    index = {}
    for key, s in building_stats(con).items():
        label, year = classify(s, today_year)
        index[key] = {"wiek": label, "rok": year, "stal_w": int(s["pierwsza"][:4])}
    return index


def age_of(index: Dict[str, Dict[str, Any]], unit_id: Optional[str], street: Optional[str],
           number: Optional[str]) -> Dict[str, Any]:
    """Age entry for one sale record; "nieznany" when the building is not in the index."""
    key = building_key(unit_id, street, number)
    return index.get(key) or {"wiek": LABELS[3], "rok": None, "stal_w": None}


def is_new(entry: Dict[str, Any]) -> bool:
    return entry.get("wiek") == LABELS[0]


NEW_SECONDARY = "Rynek wtórny, tylko budynki do 10 lat (szacunek z RCN)"


def secondary_in_new(rows, index: Dict[str, Dict[str, Any]]) -> list:
    """Secondary-market sales in buildings estimated at up to 10 years (for a separate median)."""
    return [r for r in rows if r["rodzaj_rynku"] == "rynekWtorny"
            and is_new(age_of(index, r.get("obj_id"), r.get("ulica"), r.get("nr")))]


def describe(entry: Dict[str, Any]) -> str:
    """Short text for a card, e.g. "do 10 lat (szacunek), rok ok. 2021" or "nieznany, stał już w 2017"."""
    if entry.get("rok"):
        return "%s, rok ok. %d" % (entry["wiek"], entry["rok"])
    if entry["wiek"] == LABELS[3] and entry.get("stal_w"):
        return "%s, stał już w %d" % (entry["wiek"], entry["stal_w"])
    return entry["wiek"]


def main(argv=None, today: Optional[date] = None) -> int:
    p = argparse.ArgumentParser(description="Przybliżony wiek budynku z RCN: sprawdzenie, czy metoda działa.")
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("diag")
    d.add_argument("--db", default="rcn_test.sqlite")
    d.add_argument("--ulica", action="append", default=[])
    args = p.parse_args(argv)
    today = today or date.today()

    con = sqlite3.connect(args.db)
    try:
        total, with_id = con.execute("SELECT COUNT(*), COUNT(obj_id) FROM lokale").fetchone()
        stats = building_stats(con)
    finally:
        con.close()
    keyed = sum(s["sprzedaze"] for s in stats.values())
    by_class = collections.defaultdict(lambda: [0, 0])
    for s in stats.values():
        label, _ = classify(s, today.year)
        by_class[label][0] += 1
        by_class[label][1] += s["sprzedaze"]
    print("Wiek budynku z RCN (stan na %d, granica %d lat, dane RCN od 2012):" % (today.year, YEARS))
    print("rekordów lokali: %d, z identyfikatorem lokalu: %d, rekordów z identyfikatorem budynku: %d z %d" % (
        total, with_id, keyed, total))
    print("budynków: %d" % len(stats))
    for label in LABELS:
        print("  %s: %d budynków, %d sprzedaży" % (label, by_class[label][0], by_class[label][1]))
    for street in args.ulica:
        needle = _norm_street(street)
        print("\nBudynki przy: %s" % street)
        rows = [(s["adres"], s, classify(s, today.year)) for s in stats.values()
                if needle in _norm_street(s["adres"])]
        for address, s, (label, year) in sorted(rows, key=lambda r: r[0]):
            print("  %s | sprzedaży %d (pierwotnych %d) | pierwsza %s | pierwsza pierwotna %s | %s%s" % (
                address, s["sprzedaze"], s["pierwotne"], s["pierwsza"], s["pierwsza_pierwotna"] or "brak", label,
                " (rok ok. %d)" % year if year else ""))
        if not rows:
            print("  brak budynków z tą ulicą w danych")
    return 0


if __name__ == "__main__":
    sys.exit(main())
