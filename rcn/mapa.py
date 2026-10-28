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
import socket
import sqlite3
import sys
import urllib.parse
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rcn import karta, okolica, otoczenie, podobne, wiek  # noqa: E402

PORTALS = ("otodom.pl", "olx.pl", "gratka.pl", "nieruchomosci-online.pl", "morizon.pl", "domiporta.pl",
           "adresowo.pl", "rynekpierwotny.pl")
MAP_OSM_RADIUS_M = 1000.0      # every object this close is drawn
MAP_OSM_PER_CATEGORY = 40      # at most this many per category inside MAP_OSM_RADIUS_M
# Big nuisances are drawn whole up to the surroundings radius (3 km): OSM cuts a line into many short
# ways, so drawing only the nearest one left most of a power line or a railway off the map.
FULL_RADIUS = {"linia_najwyzsza", "linia_wn", "stacja_energetyczna", "kolej", "droga_glowna", "lotnisko",
               "droga_w_budowie", "droga_planowana"}
FULL_RADIUS_CAP = 600          # ways per category, a guard for dense road networks
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


class Context:
    """Paths and the building-age index, built once at start (the RCN base changes only on import)."""

    def __init__(self, rcn_db: str, osm_db: str, oferty_db: str, today: Optional[date] = None):
        self.rcn_db, self.osm_db, self.oferty_db = rcn_db, osm_db, oferty_db
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
        if params.get("ulica"):
            if not (params.get("cena") and params.get("metraz")):
                raise karta.CardError("wpis ręczny wymaga ulicy, ceny i metrażu")
            rok = int(params["rok"]) if (params.get("rok") or "").isdigit() else None
            rynek = params.get("rynek") if params.get("rynek") in ("wtorny", "pierwotny") else None
            offer = karta.manual_offer(ctx.rcn_db, params["ulica"], params["cena"], params["metraz"],
                                       params.get("miasto") or "Katowice", rynek, rok)
        elif link:
            if not allowed_link(link):
                return 400, {"ok": False, "blad": "obsługiwane są tylko linki do portali: " + ", ".join(PORTALS)}
            offer = karta.offer_from_link(link, oferty_db=ctx.oferty_db)
        else:
            return 400, {"ok": False, "blad": "wklej link do ogłoszenia albo wpisz ulicę, cenę i metraż"}
        rcn = sqlite3.connect(ctx.rcn_db)
        osm = otoczenie.connect(ctx.osm_db) if os.path.exists(ctx.osm_db) else None
        try:
            card = karta.build_card(offer, rcn, osm, radius, months, today=ctx.today, ages=ctx.ages)
            items = otoczenie.nearby(osm, card["srodek"], card["promien_otoczenia_m"], geometry=True) if osm else []
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
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif parts.path == "/api/karta":
                params = {k: v[-1] for k, v in urllib.parse.parse_qs(parts.query).items()}
                try:
                    status, body = card_json(ctx, params)
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
    ctx = Context(args.rcn_db, args.osm_db, args.oferty_db)
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
