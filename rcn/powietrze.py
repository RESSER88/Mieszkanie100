#!/usr/bin/env python3
"""Air quality at a point: the nearest GIOŚ station and its current air-quality index (api.gios.gov.pl, v1).

The station list (Polish keys such as "WGS84 φ N") is cached for STATIONS_DAYS; the index is fetched each time,
because it changes hourly. The station can be kilometres away: the card shows the distance. Standard library only.
"""
import json
import math
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from rcn.grunt import PointCache, SourceError, http_get

API = "https://api.gios.gov.pl/pjp-api/v1/rest"
STATIONS_DAYS = 7


def _number(record: Dict[str, Any], *words: str) -> Optional[float]:
    for key, value in record.items():
        if all(w in key for w in words):
            try:
                return float(str(value).replace(",", "."))
            except ValueError:
                return None
    return None


def stations(fetch: Callable = http_get) -> List[Dict[str, Any]]:
    status, text = fetch(API + "/station/findAll?size=500")
    if status != 200 or text is None:
        raise SourceError("GIOŚ (lista stacji) nie odpowiedział: HTTP %d" % status)
    data = json.loads(text)
    rows = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])
    out = []
    for r in rows:
        lat, lon = _number(r, "φ"), _number(r, "λ")
        if lat is not None and lon is not None:
            out.append({"id": r.get("Identyfikator stacji"), "nazwa": r.get("Nazwa stacji"), "lat": lat, "lon": lon})
    return out


def _find(value: Any, words) -> Any:
    """First value under a key containing all `words` (case-insensitive), anywhere in a nested answer."""
    if isinstance(value, dict):
        for key, child in value.items():
            if all(w in key.lower() for w in words) and not isinstance(child, (dict, list)):
                return child
        for child in value.values():
            found = _find(child, words)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find(child, words)
            if found is not None:
                return found
    return None


def air_quality(lat: float, lon: float, cache_path: str, fetch: Callable = http_get,
                today: Optional[date] = None) -> Dict[str, Any]:
    cache = PointCache(cache_path)
    try:
        listing = cache.get_or("gios_stacje", (0.0, 0.0), lambda: stations(fetch), today, days=STATIONS_DAYS)
    finally:
        cache.close()
    if not listing:
        raise SourceError("GIOŚ: pusta lista stacji")
    def km(s):
        return math.hypot((s["lat"] - lat) * 111.2, (s["lon"] - lon) * 111.2 * math.cos(math.radians(lat)))
    best = min(listing, key=km)
    out = {"stacja": best["nazwa"], "odleglosc_km": round(km(best), 1), "indeks": None, "czas": None, "uwaga": None}
    status, text = fetch("%s/aqindex/getIndex/%s" % (API, best["id"]))
    if status != 200 or text is None:
        out["uwaga"] = "GIOŚ nie podał indeksu: HTTP %d" % status
        return out
    data = json.loads(text)
    out["indeks"] = _find(data, ("nazwa", "kategorii"))
    out["czas"] = _find(data, ("data", "obliczeń"))
    return out
