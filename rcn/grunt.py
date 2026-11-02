#!/usr/bin/env python3
"""Land facts for a point: the cadastral parcel (GUGiK ULDK) and mining areas (PIG-PIB MIDAS).

Both are public services answering a point query; the answers are cached in SQLite per point (rounded to 1 m)
for CACHE_DAYS, so building the same card again sends no request. A service that fails is reported as such,
never as "nothing there". Coordinates are our (northing, easting) in EPSG:2180; both services want easting first.
Source checks from the Raspberry Pi, 2026-11-02: docs/superpowers/specs/2026-11-02-funkcje-jak-mscanner.md.
Standard library only.
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

ULDK_URL = "https://uldk.gugik.gov.pl/"
MIDAS_URL = "https://cbdgmapa.pgi.gov.pl/arcgis/rest/services/midas/MapServer"
MIDAS_LAYERS = {"obszary_gornicze": 1, "tereny_gornicze": 2}
CACHE_DAYS = 30
TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (compatible; mieszkanie100/0.1; prywatne narzedzie, jedno zapytanie na zadanie)"
_TECHNICAL = ("OBJECTID", "FID", "SHAPE", "GLOBALID", "ST_AREA", "ST_LENGTH")


class SourceError(Exception):
    """The service did not answer in a usable way; the message names it."""


def http_get(url: str) -> Tuple[int, Optional[str]]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, OSError):
        return 0, None


def _xy(point: Tuple[float, float]) -> str:
    north, east = point
    return "%.2f,%.2f" % (east, north)


def parcel(point: Tuple[float, float], fetch: Callable = http_get) -> Optional[Dict[str, str]]:
    """The parcel at the point, or None where ULDK has none (e.g. a road outside cadastre data)."""
    query = urllib.parse.urlencode({"request": "GetParcelByXY", "xy": _xy(point) + ",2180",
                                    "result": "id,voivodeship,county,commune,region,parcel"}, safe=",")
    status, text = fetch(ULDK_URL + "?" + query)
    if status != 200 or text is None:
        raise SourceError("ULDK (GUGiK) nie odpowiedział: HTTP %d" % status)
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines or lines[0].strip().startswith("-1") or len(lines) < 2:
        return None
    parts = lines[1].split("|")
    keys = ("id", "wojewodztwo", "powiat", "gmina", "obreb", "numer")
    return {k: (parts[i].strip() if i < len(parts) else None) for i, k in enumerate(keys)}


def _plain(attrs: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in attrs.items()
            if v not in (None, "", " ") and not any(k.upper().startswith(t) for t in _TECHNICAL)}


def mining(point: Tuple[float, float], fetch: Callable = http_get) -> Dict[str, List[Dict[str, Any]]]:
    """Mining areas (obszary górnicze) and mining terrains (tereny górnicze) that contain the point."""
    out = {}
    for key, layer in MIDAS_LAYERS.items():
        query = urllib.parse.urlencode({"geometry": _xy(point), "geometryType": "esriGeometryPoint", "inSR": "2180",
                                        "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
                                        "returnGeometry": "false", "f": "json"}, safe=",")
        status, text = fetch("%s/%d/query?%s" % (MIDAS_URL, layer, query))
        if status != 200 or text is None:
            raise SourceError("MIDAS (PIG-PIB) nie odpowiedział: HTTP %d" % status)
        try:
            data = json.loads(text)
        except ValueError:
            raise SourceError("MIDAS (PIG-PIB): odpowiedź nie jest JSON")
        if "error" in data:
            raise SourceError("MIDAS (PIG-PIB): %s" % (data["error"].get("message") or data["error"]))
        out[key] = [_plain(f.get("attributes") or {}) for f in data.get("features") or []]
    return out


class PointCache:
    """Answers per (source, point rounded to 1 m), kept CACHE_DAYS."""

    def __init__(self, path: str):
        self.con = sqlite3.connect(path)
        self.con.execute("CREATE TABLE IF NOT EXISTS bufor (zrodlo TEXT, y INTEGER, x INTEGER, dzien TEXT, wynik TEXT,"
                         " PRIMARY KEY (zrodlo, y, x))")
        self.con.commit()

    def get_or(self, source: str, point: Tuple[float, float], work: Callable[[], Any], today: Optional[date] = None):
        today = today or date.today()
        y, x = int(round(point[0])), int(round(point[1]))
        row = self.con.execute("SELECT dzien, wynik FROM bufor WHERE zrodlo=? AND y=? AND x=?", (source, y, x)).fetchone()
        if row and row[0] >= (today - timedelta(days=CACHE_DAYS)).isoformat():
            return json.loads(row[1])
        value = work()
        with self.con:
            self.con.execute("INSERT OR REPLACE INTO bufor VALUES (?,?,?,?,?)",
                             (source, y, x, today.isoformat(), json.dumps(value, ensure_ascii=False)))
        return value

    def close(self):
        self.con.close()


def report(point: Tuple[float, float], cache_path: str, fetch: Callable = http_get,
           today: Optional[date] = None) -> Dict[str, Any]:
    """Parcel and mining facts for a card; a failed source leaves None and a message in "bledy"."""
    cache = PointCache(cache_path)
    out: Dict[str, Any] = {"dzialka": None, "gornictwo": None, "bledy": []}
    try:
        for key, source, work in (("dzialka", "uldk", lambda: parcel(point, fetch)),
                                  ("gornictwo", "midas", lambda: mining(point, fetch))):
            try:
                out[key] = cache.get_or(source, point, work, today)
            except SourceError as exc:
                out["bledy"].append(str(exc))
    finally:
        cache.close()
    return out


if __name__ == "__main__":
    # Quick check on the Pi: python3 rcn/grunt.py NORTHING EASTING
    north, east = (float(v) for v in sys.argv[1:3]) if len(sys.argv) >= 3 else (262720.44, 497795.80)
    print(json.dumps(report((north, east), os.path.join("ref", "bufor_zrodel.sqlite")), ensure_ascii=False, indent=1))
