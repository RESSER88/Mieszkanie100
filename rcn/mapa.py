#!/usr/bin/env python3
"""Map page on the Raspberry Pi: paste a listing link (or type street, price, area) and see the card on a map.

Usage on the Pi:  python3 rcn/mapa.py   then open http://<Pi address>:8100 on a phone in the home network.
The server only fetches listing pages from the portals in PORTALS, so it cannot be used to fetch other
addresses. No login: run it only in the home network. Map tiles come from OpenStreetMap (attribution shown);
Leaflet is loaded from unpkg with a pinned version and an integrity hash. Standard library only.
"""
import argparse
import json
import os
import re
import socket
import sqlite3
import sys
import urllib.parse
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rcn import filtry, karta, okolica, otoczenie, podobne, wiek  # noqa: E402

PORTALS = ("otodom.pl", "olx.pl", "gratka.pl", "nieruchomosci-online.pl", "morizon.pl", "domiporta.pl",
           "adresowo.pl", "rynekpierwotny.pl")
MAP_OSM_RADIUS_M = 1000.0      # every object this close is drawn
MAP_OSM_PER_CATEGORY = 40      # at most this many per category inside MAP_OSM_RADIUS_M
# Big nuisances are drawn whole up to the surroundings radius (3 km): OSM cuts a line into many short
# ways, so drawing only the nearest one left most of a power line or a railway off the map.
FULL_RADIUS = {"linia_najwyzsza", "linia_wn", "stacja_energetyczna", "kolej", "droga_glowna", "lotnisko",
               "droga_w_budowie", "droga_planowana"}
FULL_RADIUS_CAP = 600          # ways per category, a guard for dense road networks
# Power lines are sparse and matter from afar, so they are looked up further than the rest.
GRID = ("linia_najwyzsza", "linia_wn")
GRID_RADIUS_M = 10000.0
OSM_RADIUS_M = 3000.0          # surroundings around a search pin (the card uses its own, also 3 km)
SIMPLIFY_M = 3.0               # shapes are simplified to this tolerance before sending to the phone
MARKET_TEXT = {"rynekWtorny": "wtórny", "rynekPierwotny": "pierwotny"}
# Groups for the page and the map legend: what to avoid, roads that will change, what a family uses daily.
GROUPS = {"linia_wn": "uciazliwosci", "linia_inna": "uciazliwosci", "stacja_energetyczna": "uciazliwosci",
          "maszt": "uciazliwosci", "kolej": "uciazliwosci", "droga_glowna": "uciazliwosci", "przemysl": "uciazliwosci",
          "linia_najwyzsza": "uciazliwosci", "tramwaj": "uciazliwosci", "lotnisko": "uciazliwosci",
          "droga_drugorzedna": "uciazliwosci",
          "skladowisko": "uciazliwosci", "oczyszczalnia": "uciazliwosci", "kamieniolom": "uciazliwosci",
          "droga_w_budowie": "drogi", "droga_planowana": "drogi",
          "przedszkole": "na_co_dzien", "szkola": "na_co_dzien", "przystanek": "na_co_dzien"}


_PUBLIC_TOKEN = re.compile(r"^pk\.[A-Za-z0-9._-]+$")


def public_token(token: Optional[str]) -> Optional[str]:
    """A Mapbox token that may go to the browser: public (pk.) only. Secret tokens (sk.) never leave the server."""
    token = (token or "").strip()
    return token if _PUBLIC_TOKEN.match(token) else None


TOKEN_FILE = os.path.expanduser("~/.mieszkanie100.env")


def token_from_file(path: str = TOKEN_FILE) -> Optional[str]:
    """The Mapbox token from the Pi's env file: a bare token or a (export) MAPBOX_ACCESS_TOKEN=... line."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if line.startswith("MAPBOX_ACCESS_TOKEN="):
            line = line[len("MAPBOX_ACCESS_TOKEN="):]
        return line.strip().strip("'\"") or None
    return None


def render_page(token: Optional[str]) -> str:
    """The page with the Mapbox public token (or null: OpenStreetMap tiles, no routes)."""
    value = json.dumps(token) if token and _PUBLIC_TOKEN.match(token) else "null"
    return PAGE.replace("window.MAPBOX_TOKEN = null;", "window.MAPBOX_TOKEN = %s;" % value, 1)


class Context:
    """Paths and the building-age index, built once at start (the RCN base changes only on import)."""

    def __init__(self, rcn_db: str, osm_db: str, oferty_db: str, today: Optional[date] = None,
                 mapbox_token: Optional[str] = None):
        self.rcn_db, self.osm_db, self.oferty_db = rcn_db, osm_db, oferty_db
        self.page = render_page(public_token(mapbox_token))
        self.today = today
        con = sqlite3.connect(rcn_db)
        try:
            self.ages = wiek.age_index(con, (today or date.today()).year)
            self.streets = okolica.street_index(con)
        finally:
            con.close()


def allowed_link(link: str) -> bool:
    parts = urllib.parse.urlsplit(link.strip())
    host = (parts.hostname or "").lower()
    return parts.scheme in ("http", "https") and any(host == p or host.endswith("." + p) for p in PORTALS)


def _latlon(y: float, x: float) -> List[float]:
    lat, lon = otoczenie.pl1992_to_wgs84(y, x)
    return [round(lat, 6), round(lon, 6)]


def simplify(points: List[List[float]], tol: float = SIMPLIFY_M) -> List[List[float]]:
    """Douglas-Peucker on planar EPSG:2180 points; keeps both ends, drops vertices closer than tol to the line."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        best, index = -1.0, None
        for i in range(a + 1, b):
            d = otoczenie.point_segment_distance(points[i], points[a], points[b])
            if d > best:
                best, index = d, i
        if index is not None and best > tol:
            keep[index] = True
            stack += [(a, index), (index, b)]
    return [p for p, k in zip(points, keep) if k]


def _geojson(gtype: str, coords) -> Dict[str, Any]:
    def conv(c):
        if isinstance(c[0], (int, float)):
            lat, lon = otoczenie.pl1992_to_wgs84(c[0], c[1])
            return [round(lon, 6), round(lat, 6)]
        if c and isinstance(c[0][0], (int, float)):          # a line or a ring
            return [conv(p) for p in simplify(c)]
        return [conv(p) for p in c]
    return {"type": gtype, "coordinates": conv(coords)}


def _osm_for_map(items: List[dict]) -> List[dict]:
    """Big nuisances whole up to the surroundings radius; the rest within MAP_OSM_RADIUS_M; nearest of each always."""
    chosen, per_category = [], {}
    for item in items:                       # nearest first
        n = per_category.get(item["kategoria"], 0)
        full = item["kategoria"] in FULL_RADIUS and n < FULL_RADIUS_CAP
        if n == 0 or full or (item["odleglosc_m"] <= MAP_OSM_RADIUS_M and n < MAP_OSM_PER_CATEGORY):
            per_category[item["kategoria"]] = n + 1
            chosen.append({"kategoria": item["kategoria"], "grupa": GROUPS.get(item["kategoria"], "uciazliwosci"),
                           "etykieta": otoczenie.LABELS[item["kategoria"]],
                           "nazwa": item["nazwa"], "odleglosc_m": round(item["odleglosc_m"]),
                           "szczegoly": item["szczegoly"], "pse": "sieć przesyłowa PSE" in (item["szczegoly"] or ""),
                           "geojson": _geojson(item["typ_geometrii"], item["geometria"])})
    return chosen


def _nearest_by_category(items: List[dict]) -> List[dict]:
    """Nearest object of each category, in the order of otoczenie.CATEGORIES (missing ones listed as missing)."""
    first: Dict[str, dict] = {}
    count: Dict[str, int] = {}
    for item in items:
        first.setdefault(item["kategoria"], item)
        count[item["kategoria"]] = count.get(item["kategoria"], 0) + 1
    out = []
    for key, label in otoczenie.CATEGORIES:
        item = first.get(key)
        out.append({"kategoria": key, "grupa": GROUPS.get(key, "uciazliwosci"), "etykieta": label,
                    "odleglosc_m": round(item["odleglosc_m"]) if item else None,
                    "nazwa": item["nazwa"] if item else None, "szczegoly": item["szczegoly"] if item else None,
                    "liczba": count.get(key, 0)})
    return out


def _surroundings(osm: Optional[sqlite3.Connection], center, radius_m: float) -> List[dict]:
    """OSM objects for a point, nearest first: everything to radius_m plus power lines to GRID_RADIUS_M."""
    if osm is None:
        return []
    items = otoczenie.nearby(osm, center, radius_m, geometry=True)
    seen = {i["id"] for i in items}
    items += [i for i in otoczenie.nearby(osm, center, GRID_RADIUS_M, GRID, geometry=True) if i["id"] not in seen]
    items.sort(key=lambda i: i["odleglosc_m"])
    return items


def _summary(s: okolica.Summary) -> Dict[str, Any]:
    return {"proba": s.n, "od": s.period_from, "do": s.period_to, "mediana": s.median_m2, "p25": s.p25_m2,
            "p75": s.p75_m2, "status": s.status}


def card_json(ctx: Context, params: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
    """(HTTP status, JSON body) for /api/karta."""
    link = (params.get("link") or "").strip()
    try:
        radius = float(params.get("promien") or 500)
        months = int(params.get("miesiace") or 24)
        if radius <= 0 or radius > 3000 or months <= 0 or months > 180:
            raise ValueError
    except ValueError:
        return 400, {"ok": False, "blad": "promień 1–3000 m, okres 1–180 miesięcy"}
    try:
        if link:      # a pasted link wins over manual fields left over from an earlier card
            if not allowed_link(link):
                return 400, {"ok": False, "blad": "obsługiwane są tylko linki do portali: " + ", ".join(PORTALS)}
            offer = karta.offer_from_link(link, oferty_db=ctx.oferty_db)
        elif params.get("ulica"):
            if not (params.get("cena") and params.get("metraz")):
                raise karta.CardError("wpis ręczny wymaga ulicy, ceny i metrażu")
            rok = int(params["rok"]) if (params.get("rok") or "").isdigit() else None
            rynek = params.get("rynek") if params.get("rynek") in ("wtorny", "pierwotny") else None
            offer = karta.manual_offer(ctx.rcn_db, params["ulica"], params["cena"], params["metraz"],
                                       params.get("miasto") or "Katowice", rynek, rok)
        else:
            return 400, {"ok": False, "blad": "wklej link do ogłoszenia albo wpisz ulicę, cenę i metraż"}
        rcn = sqlite3.connect(ctx.rcn_db)
        osm = otoczenie.connect(ctx.osm_db) if os.path.exists(ctx.osm_db) else None
        try:
            card = karta.build_card(offer, rcn, osm, radius, months, today=ctx.today, ages=ctx.ages)
            items = _surroundings(osm, card["srodek"], card["promien_otoczenia_m"])
        finally:
            rcn.close()
            if osm is not None:
                osm.close()
    except karta.CardError as exc:
        return 422, {"ok": False, "blad": str(exc)}
    summaries = dict(card["porownanie"])
    compared = dict(okolica.MARKETS)[card["rynek_porownania"]]
    o = card["oferta"]
    similar = podobne.similar_offers(ctx.oferty_db, ctx.streets, card["srodek"], o.get("powierzchnia_m2"),
                                     radius_m=radius, exclude=o)
    b = card["budynek_rcn"]
    return 200, {
        "ok": True,
        "karta": karta.format_card(card),
        "oferta": {k: o.get(k) for k in ("portal", "id", "url", "tytul", "cena", "powierzchnia_m2", "cena_m2",
                                         "pokoje", "pietro", "rynek", "ulica", "miejscowosc", "dzielnica",
                                         "inwestycja", "rok_budowy", "lokalizacja_przyblizona", "polozenie_uwaga",
                                         "wzmianki", "wzmianki_zrodlo")},
        "budynek": {"rcn": wiek.describe(b) if b else None,
                    "odleglosc_m": round(b["odleglosc_m"]) if b else None,
                    "powod": None if b else ("brak sprzedaży w promieniu %g m od punktu oferty" % karta.SAME_BUILDING_M
                                             if card["polozenie_dokladne"] else "położenie oferty jest przybliżone")},
        "porownania": [{"etykieta": label, **_summary(s)} for label, s in card["porownanie"]],
        "otoczenie_lista": _nearest_by_category(items),
        "promien_otoczenia_m": card["promien_otoczenia_m"],
        "promien_sieci_m": GRID_RADIUS_M,
        "podobne": similar,
        "srodek": _latlon(*card["srodek"]),
        "przyblizone": not card["polozenie_dokladne"],
        "promien_m": radius,
        "okno": list(card["okno"]),
        "porownanie": {"rynek": compared, **_summary(summaries[compared])},
        "porownanie_nowe": _summary(summaries[wiek.NEW_SECONDARY]),
        "polozenie": card["polozenie"],
        "polozenie_nowe": card["polozenie_nowe"],
        "transakcje": [{"punkt": _latlon(r["y_pl1992"], r["x_pl1992"]), "cena_m2": r["cena_m2"],
                        "pow_m2": r["pow_m2"], "data": r["dok_data"], "rynek": MARKET_TEXT.get(r["rodzaj_rynku"], "?"),
                        "adres": " ".join(p for p in (r.get("ulica"), r.get("nr")) if p),
                        "wiek": r["wiek"], "nowy": r["budynek_do_10_lat"], "odleglosc_m": round(r["odleglosc_m"])}
                       for r in card["transakcje"]],
        "otoczenie": _osm_for_map(items),
    }


def _float(params: Dict[str, str], key: str) -> Optional[float]:
    text = (params.get(key) or "").strip().replace(",", ".")
    return float(text) if text else None


def search_json(ctx: Context, params: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
    """(HTTP status, JSON body) for /api/szukaj: saved offers of a chosen size around a pin, a link or a street."""
    try:
        f = filtry.parse(params)
    except filtry.FilterError as exc:
        return 400, {"ok": False, "blad": str(exc)}
    try:
        radius = _float(params, "promien") or 1000.0
        lat, lon = _float(params, "lat"), _float(params, "lon")
        if not 100 <= radius <= 3000:
            raise ValueError
    except ValueError:
        return 400, {"ok": False, "blad": "promień 100–3000 m, położenie liczbami"}
    area_min, area_max = f.metraz_od, f.metraz_do
    approximate = False
    try:
        if lat is not None and lon is not None:
            center = otoczenie.wgs84_to_pl1992(lat, lon)
        elif (params.get("link") or "").strip():
            link = params["link"].strip()
            if not allowed_link(link):
                return 400, {"ok": False, "blad": "obsługiwane są tylko linki do portali: " + ", ".join(PORTALS)}
            offer = karta.offer_from_link(link, oferty_db=ctx.oferty_db)
            if offer.get("y_pl1992") is not None:
                center = (offer["y_pl1992"], offer["x_pl1992"])
            elif offer.get("lat") is not None and offer.get("lon") is not None:
                center = otoczenie.wgs84_to_pl1992(offer["lat"], offer["lon"])
            else:
                raise karta.CardError("ogłoszenie nie podaje położenia; postaw pinezkę na mapie")
            approximate = bool(offer.get("lokalizacja_przyblizona"))
        elif (params.get("ulica") or "").strip():
            found = okolica.center_from_index(ctx.streets, params["ulica"], params.get("miasto") or "Katowice")
            if found is None:
                raise karta.CardError("nie znaleziono ulicy '%s' w bazie RCN" % params["ulica"])
            center, approximate = found[:2], True
        else:
            return 400, {"ok": False, "blad": "postaw pinezkę na mapie, wklej link albo wpisz ulicę"}
    except karta.CardError as exc:
        return 422, {"ok": False, "blad": str(exc)}
    found = podobne.offers_in_area(ctx.oferty_db, ctx.streets, center, radius, area_min, area_max)
    freshness = _store_freshness(ctx.oferty_db)
    latest = {portal: info["ostatnio"] for portal, info in freshness.items()}
    today = ctx.today or date.today()
    offers = [o for o in found if filtry.keep(o, f, latest, today)]
    if f.z_dala and offers:
        offers = _away_from_nuisances(ctx, offers, f.z_dala)
    offers = filtry.sort(offers, f.sortuj)
    groups = podobne.group_offers(offers)
    date_from = okolica.months_ago(today, 24).isoformat()
    osm = otoczenie.connect(ctx.osm_db) if os.path.exists(ctx.osm_db) else None
    try:
        items = _surroundings(osm, center, OSM_RADIUS_M)
    finally:
        if osm is not None:
            osm.close()
    rcn = sqlite3.connect(ctx.rcn_db)
    try:
        rows, _ = okolica.transactions_in_radius(rcn, center, radius, date_from, today.isoformat(), area_min, area_max)
    finally:
        rcn.close()
    return 200, {
        "ok": True, "srodek": _latlon(*center), "przyblizone": approximate, "promien_m": radius,
        "metraz_od": area_min, "metraz_do": area_max, "liczba_ofert": len(offers),
        "przed_filtrami": len(found), "limit_osiagniety": len(found) >= podobne.AREA_CAP, "grupy": groups,
        "sortuj": f.sortuj, "deweloperzy": f.deweloperzy,
        "rcn": [{"etykieta": label, **_summary(okolica.summarize([r for r in rows if r["rodzaj_rynku"] == key]))}
                for key, label in okolica.MARKETS],
        "zrodla": freshness,
        "otoczenie": _osm_for_map(items), "otoczenie_lista": _nearest_by_category(items),
        "promien_otoczenia_m": OSM_RADIUS_M, "promien_sieci_m": GRID_RADIUS_M,
    }


def _away_from_nuisances(ctx: Context, offers: List[dict], away: Dict[str, float]) -> List[dict]:
    """Offers with no object of the chosen nuisance kinds closer than the given distance (OSM, offer point)."""
    if not os.path.exists(ctx.osm_db):
        return offers
    osm = otoczenie.connect(ctx.osm_db)
    try:
        kept = []
        for o in offers:
            point = otoczenie.wgs84_to_pl1992(*o["punkt"])
            if all(not otoczenie.nearby(osm, point, distance, filtry.NUISANCES[key])
                   for key, distance in away.items()):
                kept.append(o)
        return kept
    finally:
        osm.close()


def _store_freshness(path: str) -> Dict[str, Dict[str, Any]]:
    """Per portal: number of saved offers and the last day a search saw any of them."""
    if not os.path.exists(path):
        return {}
    con = sqlite3.connect(path)
    try:
        return {portal: {"oferty": n, "ostatnio": last} for portal, n, last in
                con.execute("SELECT portal, COUNT(*), MAX(ostatnio) FROM oferty GROUP BY portal")}
    finally:
        con.close()


def make_handler(ctx: Context):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802 (http.server naming)
            parts = urllib.parse.urlsplit(self.path)
            if parts.path == "/":
                self._send(200, ctx.page.encode("utf-8"), "text/html; charset=utf-8")
            elif parts.path in ("/api/karta", "/api/szukaj"):
                params = {k: v[-1] for k, v in urllib.parse.parse_qs(parts.query).items()}
                try:
                    status, body = (card_json if parts.path == "/api/karta" else search_json)(ctx, params)
                except Exception as exc:  # keep the server up; the message goes to the page and the terminal
                    self.log_error("błąd karty: %r", exc)
                    status, body = 500, {"ok": False, "blad": "błąd programu: %s" % exc}
                self._send(status, json.dumps(body, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            else:
                self._send(404, b"nie ma takiej strony", "text/plain; charset=utf-8")

    return Handler


def _local_address() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.0.1", 9))      # no packet is sent; only picks the LAN interface
            return s.getsockname()[0]
    except OSError:
        return "adres-raspberry-pi"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Mapa z kartą mieszkania (serwer w sieci domowej).")
    p.add_argument("--rcn-db", default="rcn_test.sqlite")
    p.add_argument("--osm-db", default="osm_slask.sqlite")
    p.add_argument("--oferty-db", default="oferty.sqlite")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8100)
    args = p.parse_args(argv)
    if not os.path.exists(args.rcn_db):
        print("BŁĄD: nie ma bazy RCN %s" % args.rcn_db, file=sys.stderr)
        return 2
    print("Wczytuję wiek budynków z RCN...", flush=True)
    raw_token = os.environ.get("MAPBOX_ACCESS_TOKEN") or token_from_file()   # never printed
    token = public_token(raw_token)
    if raw_token and token is None:
        print("UWAGA: MAPBOX_ACCESS_TOKEN nie jest tokenem publicznym (pk.); nie trafi do przeglądarki."
              " Mapa użyje kafelków OpenStreetMap, trasy wyłączone.", flush=True)
    elif token is None:
        print("Bez tokenu Mapbox: kafelki OpenStreetMap, trasy wyłączone (MAPBOX_ACCESS_TOKEN albo plik %s)."
              % TOKEN_FILE, flush=True)
    else:
        print("Mapbox: podkład i trasy włączone (gdy Mapbox odmówi kafelków, strona przełączy się na OpenStreetMap).",
              flush=True)
    ctx = Context(args.rcn_db, args.osm_db, args.oferty_db, mapbox_token=token)
    if not os.path.exists(args.osm_db):
        print("UWAGA: nie ma bazy OSM %s, mapa bez otoczenia." % args.osm_db)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(ctx))
    print("Mapa działa: http://%s:%d  (zatrzymanie: Ctrl+C)" % (_local_address(), args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mapa.html"), encoding="utf-8") as _page:
    PAGE = _page.read()

if __name__ == "__main__":
    sys.exit(main())
