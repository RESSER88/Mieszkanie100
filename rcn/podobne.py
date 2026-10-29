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


def _candidates(db_path: str, streets, center: Tuple[float, float], radius_m: float, accept,
                exclude: Optional[Dict[str, Any]], city: str) -> List[Tuple]:
    """(distance, offer, point, where, first seen, last seen) for stored offers inside the radius, nearest first."""
    if not os.path.exists(db_path):
        return []
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("SELECT dane_json, pierwszy_raz, ostatnio FROM oferty").fetchall()
    finally:
        con.close()
    out = []
    for data, first, last in rows:
        o = json.loads(data)
        if not accept(o.get("powierzchnia_m2")):
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
            out.append((distance, o, point, where, first, last))
    return sorted(out, key=lambda c: c[0])


def _unique(candidates, limit: Optional[int]) -> List[Dict[str, Any]]:
    """The same flat on two portals once (with "takze_na"), nearest first, at most `limit`."""
    chosen: List[Dict[str, Any]] = []
    for distance, o, point, where, first, last in candidates:
        twin = next((c for c in chosen if portale.same_offer(c["_oferta"], o)), None)
        if twin is not None:
            if o["portal"] != twin["portal"] and o["portal"] not in twin["takze_na"]:
                twin["takze_na"].append(o["portal"])
            continue
        if limit is not None and len(chosen) == limit:
            continue          # keep scanning: a later copy may still belong to an already chosen offer
        lat, lon = otoczenie.pl1992_to_wgs84(*point)
        chosen.append({"portal": o["portal"], "id": o.get("id"), "url": o.get("url"), "tytul": o.get("tytul"),
                       "cena": o.get("cena"), "powierzchnia_m2": o.get("powierzchnia_m2"),
                       "cena_m2": o.get("cena_m2"), "rynek": o.get("rynek"), "inwestycja": o.get("inwestycja"),
                       "pokoje": o.get("pokoje"), "pietro": o.get("pietro"), "ulica": o.get("ulica"),
                       "zabudowa": o.get("zabudowa"), "dzielnica": o.get("dzielnica"),
                       "inwestycja_id": o.get("inwestycja_id"),
                       "odleglosc_m": round(distance), "polozenie": where, "punkt": [round(lat, 6), round(lon, 6)],
                       "pierwszy_raz": first, "ostatnio": last, "takze_na": [], "_oferta": o})
    for c in chosen:
        del c["_oferta"]
    return chosen


def similar_offers(db_path: str, streets, center: Tuple[float, float], area: Optional[float],
                   radius_m: float = 500.0, tol: float = AREA_TOL, limit: int = LIMIT,
                   exclude: Optional[Dict[str, Any]] = None, city: str = "Katowice") -> List[Dict[str, Any]]:
    """Nearest saved offers with area within ±tol of `area`, inside radius_m of center (EPSG:2180)."""
    if not area:
        return []
    accept = lambda size: size is not None and abs(size - area) <= tol * area    # noqa: E731
    return _unique(_candidates(db_path, streets, center, radius_m, accept, exclude, city), limit)


AREA_CAP = 1000     # guard for a very wide search; the page says when the cap is reached


def offers_in_area(db_path: str, streets, center: Tuple[float, float], radius_m: float,
                   area_min: Optional[float] = None, area_max: Optional[float] = None,
                   city: str = "Katowice", limit: int = AREA_CAP) -> List[Dict[str, Any]]:
    """Every saved offer with area in [area_min, area_max] inside radius_m of center, nearest first."""
    def accept(size):
        return size is not None and (area_min is None or size >= area_min) and (area_max is None or size <= area_max)
    return _unique(_candidates(db_path, streets, center, radius_m, accept, None, city), limit)


def _norm(text: Optional[str]) -> str:
    return " ".join((text or "").casefold().split())


def group_offers(offers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Developer listings sell many units in one building: units of one investment (or at one point) as one group.

    The key is the investment name when the listing gives one, otherwise the map point rounded to about 10 m.
    Groups keep the order of their nearest offer."""
    groups: Dict[Tuple, Dict[str, Any]] = {}
    for o in offers:
        if o.get("inwestycja"):
            key = ("inwestycja", _norm(o["inwestycja"]))
        elif o.get("inwestycja_id"):
            key = ("inwestycja_id", o["portal"], o["inwestycja_id"])
        else:
            key = ("punkt", round(o["punkt"][0], 4), round(o["punkt"][1], 4))
        g = groups.get(key)
        if g is None:
            name = o.get("inwestycja") or ("inwestycja nr %s (%s)" % (o["inwestycja_id"], o["portal"])
                                            if o.get("inwestycja_id") else None)
            g = groups[key] = {"inwestycja": name, "nazwa": name or o.get("tytul"),
                               "punkt": o["punkt"], "odleglosc_m": o["odleglosc_m"], "polozenie": o["polozenie"],
                               "oferty": []}
        g["oferty"].append(o)
    out = []
    for g in groups.values():
        def span(field):
            values = [o[field] for o in g["oferty"] if o.get(field) is not None]
            return (min(values), max(values)) if values else (None, None)
        g["liczba"] = len(g["oferty"])
        g["metraz_od"], g["metraz_do"] = span("powierzchnia_m2")
        g["cena_m2_od"], g["cena_m2_do"] = span("cena_m2")
        g["cena_od"], g["cena_do"] = span("cena")
        g["portale"] = sorted({o["portal"] for o in g["oferty"]} | {p for o in g["oferty"] for p in o["takze_na"]})
        out.append(g)
    return out
