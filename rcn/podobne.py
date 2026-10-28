#!/usr/bin/env python3
"""Offers of a similar size near a point, from the saved search results (rcn/olx.py, rcn/otodom.py).

Nothing is fetched here: the offers are the ones the last searches stored in oferty.sqlite, so an
offer can be gone from the portal; each one carries the day it was last seen. Position is the
listing's own point when it has one (OLX marks it approximate), otherwise the mean RCN position of
its street, and the result says which. The same flat on two portals is listed once.
"""
import json
import math
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from rcn import okolica, otoczenie, portale

LIMIT = 5
AREA_TOL = 0.15


def _is_same(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    if a.get("portal") == b.get("portal") and a.get("id") is not None and a.get("id") == b.get("id"):
        return True
    if a.get("url") and a.get("url") == b.get("url"):
        return True
    return portale.same_offer(a, b)


def similar_offers(db_path: str, streets, center: Tuple[float, float], area: Optional[float],
                   radius_m: float = 500.0, tol: float = AREA_TOL, limit: int = LIMIT,
                   exclude: Optional[Dict[str, Any]] = None, city: str = "Katowice") -> List[Dict[str, Any]]:
    """Nearest saved offers with area within ±tol of `area`, inside radius_m of center (EPSG:2180)."""
    if not area or not os.path.exists(db_path):
        return []
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("SELECT dane_json, pierwszy_raz, ostatnio FROM oferty").fetchall()
    finally:
        con.close()
    candidates = []
    for data, first, last in rows:
        o = json.loads(data)
        size = o.get("powierzchnia_m2")
        if size is None or abs(size - area) > tol * area:
            continue
        if exclude is not None and _is_same(o, exclude):
            continue
        if o.get("lat") is not None and o.get("lon") is not None:
            point = otoczenie.wgs84_to_pl1992(o["lat"], o["lon"])
            where = "przybliżone" if o.get("lokalizacja_przyblizona") else "z ogłoszenia"
        elif o.get("ulica"):
            found = okolica.center_from_index(streets, o["ulica"], o.get("miejscowosc") or city)
            if found is None:
                continue
            point, where = found[:2], "środek ulicy z RCN"
        else:
            continue
        distance = math.hypot(point[0] - center[0], point[1] - center[1])
        if distance <= radius_m:
            candidates.append((distance, o, point, where, first, last))
    chosen: List[Dict[str, Any]] = []
    for distance, o, point, where, first, last in sorted(candidates, key=lambda c: c[0]):
        twin = next((c for c in chosen if portale.same_offer(c["_oferta"], o)), None)
        if twin is not None:
            if o["portal"] != twin["portal"] and o["portal"] not in twin["takze_na"]:
                twin["takze_na"].append(o["portal"])
            continue
        if len(chosen) == limit:
            continue          # keep scanning: a later copy may still belong to an already chosen offer
        lat, lon = otoczenie.pl1992_to_wgs84(*point)
        chosen.append({"portal": o["portal"], "id": o.get("id"), "url": o.get("url"), "tytul": o.get("tytul"),
                       "cena": o.get("cena"), "powierzchnia_m2": o.get("powierzchnia_m2"),
                       "cena_m2": o.get("cena_m2"), "rynek": o.get("rynek"), "inwestycja": o.get("inwestycja"),
                       "odleglosc_m": round(distance), "polozenie": where, "punkt": [round(lat, 6), round(lon, 6)],
                       "pierwszy_raz": first, "ostatnio": last, "takze_na": [], "_oferta": o})
    for c in chosen:
        del c["_oferta"]
    return chosen
