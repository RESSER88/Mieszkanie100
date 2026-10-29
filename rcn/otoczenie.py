#!/usr/bin/env python3
"""Surroundings of a place from an OpenStreetMap extract (nuisances, schools, stops, roads).

Input is a GeoJSON text sequence produced on the Raspberry Pi by osmium (see
docs/rcn-testy-na-raspberry-pi.md). Features are classified, projected to EPSG:2180
(the RCN coordinate system, northing first) and stored in SQLite with a bounding box,
so a radius query needs no network. OSM is community data: a missing object is reported
as missing in the data, never as absent on the ground. Standard library only.
"""
import argparse
import json
import math
import os
import sqlite3
import sys
from typing import Dict, List, Optional, Sequence, Tuple

# EPSG:2180 (PUWG 1992): transverse Mercator on GRS80, Krueger series (sub-millimetre here).
_A, _F = 6378137.0, 1 / 298.257222101
_N = _F / (2 - _F)
_RECT = _A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_ALPHA = (_N / 2 - 2 * _N ** 2 / 3 + 5 * _N ** 3 / 16, 13 * _N ** 2 / 48 - 3 * _N ** 3 / 5, 61 * _N ** 3 / 240)
_K0, _LON0, _E0, _N0 = 0.9993, math.radians(19.0), 500000.0, -5300000.0
_ECC = 2 * math.sqrt(_N) / (1 + _N)

CATEGORIES = (
    ("linia_najwyzsza", "linia najwyższego napięcia (220–400 kV)"),
    ("linia_wn", "linia wysokiego napięcia (110 kV)"),
    ("linia_inna", "inna linia energetyczna lub bez napięcia w danych"),
    ("stacja_energetyczna", "stacja energetyczna WN (110 kV i więcej)"),
    ("maszt", "maszt lub wieża telekomunikacyjna"),
    ("kolej", "kolej"),
    ("tramwaj", "torowisko tramwajowe"),
    ("lotnisko", "lotnisko lub lądowisko"),
    ("droga_glowna", "droga główna"),
    ("droga_drugorzedna", "droga drugorzędna (zwykle wojewódzka)"),
    ("przemysl", "teren przemysłowy"),
    ("skladowisko", "składowisko odpadów"),
    ("oczyszczalnia", "oczyszczalnia ścieków"),
    ("kamieniolom", "kamieniołom"),
    ("droga_w_budowie", "droga w budowie"),
    ("droga_planowana", "droga planowana"),
    ("przedszkole", "przedszkole"),
    ("szkola", "szkoła"),
    ("przystanek", "przystanek"),
)
LABELS = dict(CATEGORIES)
_MAIN_ROADS = {"motorway", "trunk", "primary", "motorway_link", "trunk_link", "primary_link"}
_LANDUSE = {"industrial": "przemysl", "landfill": "skladowisko", "quarry": "kamieniolom"}
# Road classes worth reporting when under construction or planned; footpaths and local streets are noise.
_ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary"}
LINEAR = {"linia_najwyzsza", "linia_wn", "linia_inna", "kolej", "tramwaj", "droga_glowna", "droga_drugorzedna",
          "droga_w_budowie", "droga_planowana"}
_SECONDARY = {"secondary", "secondary_link"}
PSE_WIKIDATA = "Q1749435"    # Polskie Sieci Elektroenergetyczne, the transmission system operator


def wgs84_to_pl1992(lat: float, lon: float) -> Tuple[float, float]:
    """(northing, easting) in EPSG:2180 for a WGS84 latitude and longitude in degrees."""
    phi, dlon = math.radians(lat), math.radians(lon) - _LON0
    t = math.sinh(math.atanh(math.sin(phi)) - _ECC * math.atanh(_ECC * math.sin(phi)))
    xi = math.atan2(t, math.cos(dlon))
    eta = math.atanh(math.sin(dlon) / math.sqrt(1 + t * t))
    north, east = xi, eta
    for j, alpha in enumerate(_ALPHA, start=1):
        north += alpha * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
        east += alpha * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
    return _N0 + _K0 * _RECT * north, _E0 + _K0 * _RECT * east


_BETA = (_N / 2 - 2 * _N ** 2 / 3 + 37 * _N ** 3 / 96, _N ** 2 / 48 + _N ** 3 / 15, 17 * _N ** 3 / 480)
_DELTA = (2 * _N - 2 * _N ** 2 / 3 - 2 * _N ** 3, 7 * _N ** 2 / 3 - 8 * _N ** 3 / 5, 56 * _N ** 3 / 15)


def pl1992_to_wgs84(north: float, east: float) -> Tuple[float, float]:
    """(lat, lon) in degrees for EPSG:2180 (northing, easting); inverse of wgs84_to_pl1992 (map display)."""
    xi = (north - _N0) / (_K0 * _RECT)
    eta = (east - _E0) / (_K0 * _RECT)
    xi_p = xi - sum(b * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    eta_p = eta - sum(b * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    chi = math.asin(math.sin(xi_p) / math.cosh(eta_p))
    phi = chi + sum(d * math.sin(2 * j * chi) for j, d in enumerate(_DELTA, 1))
    return math.degrees(phi), math.degrees(_LON0 + math.atan2(math.sinh(eta_p), math.cos(xi_p)))


def _max_voltage(text: Optional[str]) -> Optional[float]:
    values = []
    for part in (text or "").split(";"):
        try:
            values.append(float(part.strip()))
        except ValueError:
            pass
    return max(values) if values else None


def classify(tags: Dict[str, str]) -> Optional[str]:
    """Category key for OSM tags, or None when the object is not of interest."""
    amenity, highway, railway = tags.get("amenity"), tags.get("highway"), tags.get("railway")
    if amenity == "kindergarten":
        return "przedszkole"
    if amenity == "school":
        return "szkola"
    if highway == "bus_stop" or railway == "tram_stop" or tags.get("public_transport") == "platform":
        return "przystanek"
    if highway in ("construction", "proposed"):
        road_class = (tags.get(highway) or "").replace("_link", "")
        if road_class and road_class not in _ROAD_CLASSES:
            return None
        return "droga_w_budowie" if highway == "construction" else "droga_planowana"
    if highway in _MAIN_ROADS:
        return "droga_glowna"
    if highway in _SECONDARY:
        return "droga_drugorzedna"
    if railway == "rail":
        return "kolej"
    if railway == "tram":
        return "tramwaj"
    if tags.get("aeroway") == "aerodrome":
        return "lotnisko"
    power = tags.get("power")
    if power == "line":
        voltage = _max_voltage(tags.get("voltage"))
        if voltage is not None and voltage >= 220000:
            return "linia_najwyzsza"
        return "linia_wn" if voltage is not None and voltage >= 110000 else "linia_inna"
    if power == "substation":
        voltage = _max_voltage(tags.get("voltage"))
        high = (voltage is not None and voltage >= 110000) or tags.get("substation") == "transmission"
        return "stacja_energetyczna" if high else None
    man_made = tags.get("man_made")
    if man_made == "mast" or (man_made == "tower" and tags.get("tower:type") == "communication"):
        return "maszt"
    if man_made == "wastewater_plant":
        return "oczyszczalnia"
    return _LANDUSE.get(tags.get("landuse"))


def is_pse(tags: Dict[str, str]) -> bool:
    """Operator tagged as PSE (the name is written in several ways, so the Wikidata id comes first)."""
    if tags.get("operator:wikidata") == PSE_WIKIDATA:
        return True
    operator = (tags.get("operator") or "").casefold()
    return "pse" in operator.replace(".", " ").split() or "polskie sieci elektroenergetyczne" in operator


def _details(category: str, tags: Dict[str, str]) -> str:
    parts = []
    if category in ("linia_najwyzsza", "linia_wn", "linia_inna", "stacja_energetyczna"):
        voltage = _max_voltage(tags.get("voltage"))
        if voltage is not None:
            parts.append("napięcie %g kV" % (voltage / 1000))
        if is_pse(tags):
            parts.append("sieć przesyłowa PSE (wg tagu operatora w OSM)")
        elif tags.get("operator"):
            parts.append("operator %s" % tags["operator"])
    elif category in ("droga_w_budowie", "droga_planowana"):
        road_class = tags.get("construction") or tags.get("proposed")
        if road_class:
            parts.append("klasa %s" % road_class)
        parts.append("rok otwarcia %s" % tags["opening_date"] if tags.get("opening_date") else "rok otwarcia nieznany")
    return ", ".join(parts)


def _project(coords):
    """Recursively turn [lon, lat] pairs into (northing, easting) tuples."""
    if coords and isinstance(coords[0], (int, float)):
        if len(coords) < 2:
            raise ValueError("pozycja bez dwóch współrzędnych")
        return wgs84_to_pl1992(coords[1], coords[0])
    if not coords:
        raise ValueError("pusta geometria")
    return [_project(c) for c in coords]


def _flatten(gtype: str, coords) -> List[Tuple[float, float]]:
    if gtype == "Point":
        return [coords]
    if gtype == "LineString":
        return list(coords)
    if gtype in ("Polygon", "MultiLineString"):
        return [p for part in coords for p in part]
    if gtype == "MultiPolygon":
        return [p for poly in coords for ring in poly for p in ring]
    raise ValueError("nieobsługiwany typ geometrii: %s" % gtype)


def point_segment_distance(p, a, b) -> float:
    (py, px), (ay, ax), (by, bx) = p, a, b
    dy, dx = by - ay, bx - ax
    length2 = dy * dy + dx * dx
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((py - ay) * dy + (px - ax) * dx) / length2))
    return math.hypot(py - (ay + t * dy), px - (ax + t * dx))


def _inside(p, ring) -> bool:
    py, px = p
    inside = False
    for (ay, ax), (by, bx) in zip(ring, ring[1:]):
        if (ay > py) != (by > py) and px < ax + (py - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def _line_distance(p, pts) -> float:
    if len(pts) == 1:
        return math.hypot(p[0] - pts[0][0], p[1] - pts[0][1])
    return min(point_segment_distance(p, a, b) for a, b in zip(pts, pts[1:]))


def _polygon_distance(p, rings) -> float:
    if _inside(p, rings[0]) and not any(_inside(p, hole) for hole in rings[1:]):
        return 0.0
    return min(_line_distance(p, ring) for ring in rings)


def distance_to_shape(p: Tuple[float, float], gtype: str, coords) -> float:
    """Metres from a projected point to a projected geometry (0 inside a polygon)."""
    if gtype == "Point":
        return math.hypot(p[0] - coords[0], p[1] - coords[1])
    if gtype == "LineString":
        return _line_distance(p, coords)
    if gtype == "MultiLineString":
        return min(_line_distance(p, part) for part in coords)
    if gtype == "Polygon":
        return _polygon_distance(p, coords)
    if gtype == "MultiPolygon":
        return min(_polygon_distance(p, poly) for poly in coords)
    raise ValueError("nieobsługiwany typ geometrii: %s" % gtype)


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE IF NOT EXISTS osm_obiekty (id TEXT PRIMARY KEY, kategoria TEXT NOT NULL, nazwa TEXT,"
        " tagi_json TEXT, typ_geometrii TEXT, geom_json TEXT, min_y REAL, max_y REAL, min_x REAL, max_x REAL)")
    con.execute("CREATE INDEX IF NOT EXISTS osm_bbox ON osm_obiekty (min_y, max_y, min_x, max_x)")
    con.commit()
    return con


class ImportGuardError(Exception):
    """The new extract is much smaller than the base; refusing to replace it (an empty or failed osmium run)."""


GUARD_SHARE = 0.5     # a refresh must keep at least half the objects, unless forced


def import_geojsonseq(path: str, db_path: str, force: bool = False) -> Dict[str, int]:
    """Load an osmium GeoJSON sequence; a re-import replaces the base, but never with a much smaller extract."""
    stats = {"zapisane": 0, "pominiete": 0, "bledne": 0}
    con = connect(db_path)
    rows = []
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, start=1):
            line = line.strip().lstrip("\x1e").strip()
            if not line:
                continue
            try:
                feat = json.loads(line)
                tags = feat.get("properties") or {}
                category = classify(tags)
                if category is None:
                    stats["pominiete"] += 1
                    continue
                geom = feat.get("geometry") or {}
                gtype, coords = geom.get("type"), _project(geom.get("coordinates"))
                pts = _flatten(gtype, coords)
            except (ValueError, TypeError, KeyError, IndexError):
                stats["bledne"] += 1
                continue
            ys, xs = [p[0] for p in pts], [p[1] for p in pts]
            rows.append((str(feat.get("id") or "linia-%d" % number), category, tags.get("name"),
                         json.dumps(tags, ensure_ascii=False), gtype, json.dumps(coords),
                         min(ys), max(ys), min(xs), max(xs)))
            stats["zapisane"] += 1
    existing = con.execute("SELECT COUNT(*) FROM osm_obiekty").fetchone()[0]
    if existing and not force and len(rows) < GUARD_SHARE * existing:
        con.close()
        raise ImportGuardError("nowy plik ma %d obiektów, a baza %d; to wygląda na nieudany lub pusty wynik osmium."
                               " Baza zostaje bez zmian. Jeśli to zamierzone, dodaj --force." % (len(rows), existing))
    with con:  # full refresh: objects missing from the new extract must disappear
        con.execute("DELETE FROM osm_obiekty")
        con.executemany("INSERT OR REPLACE INTO osm_obiekty VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    con.close()
    return stats


def nearby(con: sqlite3.Connection, center: Tuple[float, float], radius_m: float,
           categories: Optional[Sequence[str]] = None, geometry: bool = False) -> List[dict]:
    """Objects within the radius, nearest first, with distance, name and details (and the shape for a map)."""
    cy, cx = center
    sql = ("SELECT id, kategoria, nazwa, tagi_json, typ_geometrii, geom_json FROM osm_obiekty"
           " WHERE max_y >= ? AND min_y <= ? AND max_x >= ? AND min_x <= ?")
    params: list = [cy - radius_m, cy + radius_m, cx - radius_m, cx + radius_m]
    if categories:
        sql += " AND kategoria IN (%s)" % ",".join("?" * len(categories))
        params.extend(categories)
    found = []
    for oid, category, name, tags_json, gtype, geom_json in con.execute(sql, params):
        coords = json.loads(geom_json)
        if gtype == "Point":
            coords = tuple(coords)
        distance = distance_to_shape(center, gtype, coords)
        if distance <= radius_m:
            item = {"id": oid, "kategoria": category, "nazwa": name, "odleglosc_m": distance,
                    "szczegoly": _details(category, json.loads(tags_json))}
            if geometry:
                item["typ_geometrii"], item["geometria"] = gtype, coords
            found.append(item)
    return sorted(found, key=lambda item: item["odleglosc_m"])


def format_report(street: str, radius_m: float, items: List[dict],
                  categories: Sequence[str] = tuple(key for key, _ in CATEGORIES)) -> str:
    lines = ["Otoczenie: %s, promień %g m (OpenStreetMap, dane orientacyjne)" % (street, radius_m), ""]
    for key in categories:
        mine = [i for i in items if i["kategoria"] == key]
        label = LABELS.get(key, key)
        if not mine:
            lines.append("%s: brak w danych OSM w promieniu %g m" % (label, radius_m))
            continue
        first = mine[0]
        text = "%s: najbliżej %.0f m" % (label, first["odleglosc_m"])
        if first.get("nazwa"):
            text += " (%s)" % first["nazwa"]
        if key in LINEAR:
            text += ", odcinków w danych w promieniu: %d" % len(mine)
        elif key == "przystanek":
            names = {i["nazwa"] for i in mine if i.get("nazwa")}
            text += ", różnych nazw w promieniu: %d" % (len(names) or len(mine))
        else:
            text += ", w promieniu: %d" % len(mine)
        if first.get("szczegoly"):
            text += " · " + first["szczegoly"]
        lines.append(text)
    lines += ["", "Źródło: © autorzy OpenStreetMap (licencja ODbL). Brak obiektu w danych nie oznacza,"
                  " że nie ma go w terenie. Odległości w linii prostej."]
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Otoczenie nieruchomości z danych OpenStreetMap.")
    sub = p.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="wczytaj plik GeoJSON z osmium do bazy")
    imp.add_argument("--geojsonseq", required=True)
    imp.add_argument("--osm-db", default="osm_slask.sqlite")
    imp.add_argument("--force", action="store_true", help="zastąp bazę nawet dużo mniejszym plikiem")
    near = sub.add_parser("near", help="obiekty w promieniu od ulicy z bazy RCN")
    near.add_argument("--osm-db", default="osm_slask.sqlite")
    near.add_argument("--rcn-db", default="rcn_test.sqlite")
    near.add_argument("--street", required=True)
    near.add_argument("--city", default="Katowice")
    near.add_argument("--radius", type=float, default=1000.0)
    args = p.parse_args(argv)

    if args.command == "import":
        try:
            stats = import_geojsonseq(args.geojsonseq, args.osm_db, args.force)
        except ImportGuardError as exc:
            print("BŁĄD: %s" % exc, file=sys.stderr)
            return 2
        print("Zapisane: %(zapisane)d, pominięte (inne obiekty): %(pominiete)d, błędne: %(bledne)d" % stats)
        return 0
    from rcn.okolica import find_center
    rcn = sqlite3.connect(args.rcn_db)
    try:
        center = find_center(rcn, args.street, args.city)
    finally:
        rcn.close()
    if center is None:
        print("BŁĄD: nie znaleziono ulicy '%s' w miejscowości %s w bazie RCN." % (args.street, args.city),
              file=sys.stderr)
        return 2
    con = connect(args.osm_db)
    try:
        items = nearby(con, center[:2], args.radius)
    finally:
        con.close()
    print(format_report(args.street, args.radius, items))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(main())
