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
import re
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
    out = {k: (parts[i].strip() if i < len(parts) else None) for i, k in enumerate(keys)}
    # ULDK writes "powiat Katowice", "Katowice (miasto)", "Dz. Ligota" (Dz. = dzielnica as the precinct name).
    if out["powiat"]:
        out["powiat"] = re.sub(r"^powiat\s+", "", out["powiat"])
    if out["gmina"]:
        out["gmina"] = re.sub(r"\s*\((miasto|gmina miejska|gmina wiejska|obszar wiejski)\)$", "", out["gmina"])
    if out["obreb"]:
        out["obreb"] = re.sub(r"^Dz\.\s*", "", out["obreb"])
    return out


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


def mining_summary(attrs: Dict[str, Any]) -> str:
    """One line from a MIDAS record: name, mineral, status and expiry, supervising mining office."""
    name = str(attrs.get("NAZWA_OG") or attrs.get("NAZWA_TG") or attrs.get("NAZWA_ZLOZA") or "").strip()
    mineral = str(attrs.get("KOPALINA") or "").strip().lower()
    status = ", ".join(x for x in (str(attrs.get("STATUS") or "").strip(),
                                   "ważny do %s" % attrs["DATA_WAZNOSCI"] if attrs.get("DATA_WAZNOSCI") else "") if x)
    office = str(attrs.get("NADZOR_OUG") or "").strip()
    parts = [("%s: %s" % (name, mineral)) if name and mineral else (name or mineral), status,
             "nadzór: %s" % office if office else ""]
    return "; ".join(p for p in parts if p)


# Zoning symbols of local plans (rozporządzenie o projekcie MPZP, 2003; plans use them with a number prefix).
SYMBOLS = (("MW", "zabudowa mieszkaniowa wielorodzinna"), ("MN", "zabudowa mieszkaniowa jednorodzinna"),
           ("MU", "zabudowa mieszkaniowo-usługowa"), ("RM", "zabudowa zagrodowa"), ("PU", "zabudowa produkcyjno-usługowa"),
           ("UP", "usługi publiczne"), ("UO", "usługi oświaty"), ("UZ", "usługi zdrowia"), ("US", "usługi sportu"),
           ("U", "zabudowa usługowa"), ("P", "zabudowa produkcyjna, składy i magazyny"), ("ZP", "zieleń urządzona"),
           ("ZL", "las"), ("ZC", "cmentarz"), ("ZD", "ogrody działkowe"), ("ZN", "zieleń nieurządzona"),
           ("Z", "zieleń"), ("R", "rolnictwo"), ("WS", "wody powierzchniowe"), ("KDW", "droga wewnętrzna"),
           ("KD", "droga publiczna"), ("KS", "parking lub obsługa komunikacji"), ("KK", "kolej"), ("K", "komunikacja"),
           ("E", "elektroenergetyka"), ("G", "gazownictwo"), ("W", "wodociągi"), ("C", "ciepłownictwo"),
           ("O", "gospodarka odpadami"), ("T", "telekomunikacja"))


def symbol_meaning(symbol: Optional[str]) -> Optional[str]:
    """Meaning of a plan symbol like "12MW" or "MW/U"; None when the symbol is not a standard one."""
    meanings = []
    for part in re.split(r"[/,+]", symbol or ""):
        letters = re.sub(r"[^A-Z]", "", part.upper())
        match = next((m for code, m in SYMBOLS if letters.startswith(code)), None)
        if match:
            meanings.append(match)
    return " / ".join(meanings) or None


MPZP_URL = "https://mapy.geoportal.gov.pl/wss/ext/KrajowaIntegracjaMiejscowychPlanowZagospodarowaniaPrzestrzennego"
ZONING_FIELDS = ("OZNACZENIE_TERENU", "WR_SYMBOL", "SYMBOL_PODS", "OPIS", "PRZEZN_PODST_KOD", "MAX_WYSOKOSC_BUDYNKU",
                 "MAX_INTENSYWNOSC_ZABUDOWY", "MIN_INTENSYWNOSC_ZABUDOWY", "MAX_POW_ZABUDOWY", "POW_BIOLOGICZNIE_CZYNNA",
                 "MIN_POW_DZIALKI", "DATA_WEJSCIA", "PLAN_ID")


def _feature_info_plain(text: str) -> List[Dict[str, Any]]:
    """Esri WMS text/plain: "@Layer" then a header row and value rows separated by ";"."""
    rows, layer, header = [], None, None
    for line in re.split(r"\r\n|\r|\n", text or ""):
        if line.startswith("@"):
            match = re.match(r"^@(.*?)((?:ID|OBJECTID|FID);.*)?$", line)
            layer, header = match.group(1).strip(), (match.group(2).split(";") if match.group(2) else None)
            continue
        if layer is None or not line.strip():
            continue
        if header is None:
            header = line.split(";")
            continue
        values = line.split(";")
        rows.append({"warstwa": layer, "pola": dict(zip(header, values))})
    return rows


def zoning(point: Tuple[float, float], fetch: Callable = http_get) -> List[Dict[str, Any]]:
    """Local plan areas at the point (Krajowa Integracja MPZP, GetFeatureInfo text/plain); [] where no plan."""
    north, east = point
    params = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo", "LAYERS": "plany,wektor-pow",
              "QUERY_LAYERS": "plany,wektor-pow", "CRS": "EPSG:2180", "STYLES": "",
              "BBOX": "%.2f,%.2f,%.2f,%.2f" % (north - 50, east - 50, north + 50, east + 50),   # WMS 1.3.0: northing first
              "WIDTH": "101", "HEIGHT": "101", "I": "50", "J": "50", "INFO_FORMAT": "text/plain"}
    status, text = fetch(MPZP_URL + "?" + urllib.parse.urlencode(params))
    if status != 200 or text is None:
        raise SourceError("MPZP (GUGiK) nie odpowiedział: HTTP %d" % status)
    out = []
    for row in _feature_info_plain(text):
        fields = {k: v.strip() for k, v in row["pola"].items() if k in ZONING_FIELDS and v.strip() not in ("", "Null")}
        symbol = fields.get("OZNACZENIE_TERENU") or fields.get("WR_SYMBOL") or fields.get("SYMBOL_PODS")
        out.append({"warstwa": row["warstwa"], "symbol": symbol,
                    "przeznaczenie": symbol_meaning(fields.get("WR_SYMBOL") or symbol) or fields.get("OPIS"),
                    "pola": fields})
    return out


GEOHAZARD_SERVICES = {"gdt": "geozagrozenia/gdt", "sopo": "geozagrozenia/sopo_obszary"}
PIG_REST = "https://cbdgmapa.pgi.gov.pl/arcgis/rest/services"


def geohazards(point: Tuple[float, float], fetch: Callable = http_get) -> Dict[str, List[Dict[str, Any]]]:
    """PIG geohazard layers that contain the point: sinkholes and shallow coal mining (gdt), landslides (sopo)."""
    north, east = point
    out = {}
    for key, service in GEOHAZARD_SERVICES.items():
        params = {"geometry": "%.2f,%.2f" % (east, north), "geometryType": "esriGeometryPoint", "sr": "2180",
                  "layers": "all", "tolerance": "1", "returnGeometry": "false", "f": "json",
                  "mapExtent": "%.2f,%.2f,%.2f,%.2f" % (east - 100, north - 100, east + 100, north + 100),
                  "imageDisplay": "200,200,96"}
        status, text = fetch("%s/%s/MapServer/identify?%s" % (PIG_REST, service, urllib.parse.urlencode(params)))
        if status != 200 or text is None:
            raise SourceError("PIG geozagrożenia (%s) nie odpowiedział: HTTP %d" % (key, status))
        try:
            data = json.loads(text)
        except ValueError:
            raise SourceError("PIG geozagrożenia (%s): odpowiedź nie jest JSON" % key)
        if "error" in data:
            raise SourceError("PIG geozagrożenia (%s): %s" % (key, data["error"].get("message")))
        out[key] = [{"warstwa": r.get("layerName"), "pola": _plain(r.get("attributes") or {})}
                    for r in data.get("results") or []]
    return out


class PointCache:
    """Answers per (source, point rounded to 1 m), kept CACHE_DAYS."""

    def __init__(self, path: str):
        self.con = sqlite3.connect(path)
        self.con.execute("CREATE TABLE IF NOT EXISTS bufor (zrodlo TEXT, y INTEGER, x INTEGER, dzien TEXT, wynik TEXT,"
                         " PRIMARY KEY (zrodlo, y, x))")
        self.con.commit()

    def get_or(self, source: str, point: Tuple[float, float], work: Callable[[], Any], today: Optional[date] = None,
               days: int = CACHE_DAYS):
        today = today or date.today()
        y, x = int(round(point[0])), int(round(point[1]))
        row = self.con.execute("SELECT dzien, wynik FROM bufor WHERE zrodlo=? AND y=? AND x=?", (source, y, x)).fetchone()
        if row and row[0] >= (today - timedelta(days=days)).isoformat():
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
    out: Dict[str, Any] = {"dzialka": None, "gornictwo": None, "plan": None, "geozagrozenia": None, "bledy": []}
    try:
        for key, source, work in (("dzialka", "uldk", lambda: parcel(point, fetch)),
                                  ("gornictwo", "midas", lambda: mining(point, fetch)),
                                  ("plan", "mpzp2", lambda: zoning(point, fetch)),     # mpzp2: answers before the line-end fix are dropped
                                  ("geozagrozenia", "pig_gz", lambda: geohazards(point, fetch))):
            try:
                out[key] = cache.get_or(source, point, work, today)
            except SourceError as exc:
                out["bledy"].append(str(exc))
    finally:
        cache.close()
    if out["gornictwo"]:
        out["gornictwo_opis"] = {k: [mining_summary(a) for a in v] for k, v in out["gornictwo"].items()}
    return out


if __name__ == "__main__":
    # Quick check on the Pi: python3 rcn/grunt.py NORTHING EASTING
    north, east = (float(v) for v in sys.argv[1:3]) if len(sys.argv) >= 3 else (262720.44, 497795.80)
    print(json.dumps(report((north, east), os.path.join("ref", "bufor_zrodel.sqlite")), ensure_ascii=False, indent=1))
