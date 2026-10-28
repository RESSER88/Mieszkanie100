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

from rcn import karta, okolica, otoczenie, wiek  # noqa: E402

PORTALS = ("otodom.pl", "olx.pl", "gratka.pl", "nieruchomosci-online.pl", "morizon.pl", "domiporta.pl",
           "adresowo.pl", "rynekpierwotny.pl")
MAP_OSM_RADIUS_M = 1000.0      # every object this close is drawn
MAP_OSM_PER_CATEGORY = 40      # at most this many per category inside MAP_OSM_RADIUS_M
MARKET_TEXT = {"rynekWtorny": "wtórny", "rynekPierwotny": "pierwotny"}


class Context:
    """Paths and the building-age index, built once at start (the RCN base changes only on import)."""

    def __init__(self, rcn_db: str, osm_db: str, oferty_db: str, today: Optional[date] = None):
        self.rcn_db, self.osm_db, self.oferty_db = rcn_db, osm_db, oferty_db
        self.today = today
        con = sqlite3.connect(rcn_db)
        try:
            self.ages = wiek.age_index(con, (today or date.today()).year)
        finally:
            con.close()


def allowed_link(link: str) -> bool:
    parts = urllib.parse.urlsplit(link.strip())
    host = (parts.hostname or "").lower()
    return parts.scheme in ("http", "https") and any(host == p or host.endswith("." + p) for p in PORTALS)


def _latlon(y: float, x: float) -> List[float]:
    lat, lon = otoczenie.pl1992_to_wgs84(y, x)
    return [round(lat, 6), round(lon, 6)]


def _geojson(gtype: str, coords) -> Dict[str, Any]:
    def conv(c):
        if isinstance(c[0], (int, float)):
            lat, lon = otoczenie.pl1992_to_wgs84(c[0], c[1])
            return [round(lon, 6), round(lat, 6)]
        return [conv(p) for p in c]
    return {"type": gtype, "coordinates": conv(coords)}


def _osm_for_map(items: List[dict]) -> List[dict]:
    """Everything within MAP_OSM_RADIUS_M (capped per category) plus the nearest object of each category."""
    chosen, per_category = [], {}
    for item in items:                       # nearest first
        n = per_category.get(item["kategoria"], 0)
        if n == 0 or (item["odleglosc_m"] <= MAP_OSM_RADIUS_M and n < MAP_OSM_PER_CATEGORY):
            per_category[item["kategoria"]] = n + 1
            chosen.append({"kategoria": item["kategoria"], "etykieta": otoczenie.LABELS[item["kategoria"]],
                           "nazwa": item["nazwa"], "odleglosc_m": round(item["odleglosc_m"]),
                           "szczegoly": item["szczegoly"], "geojson": _geojson(item["typ_geometrii"], item["geometria"])})
    return chosen


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
    return 200, {
        "ok": True,
        "karta": karta.format_card(card),
        "oferta": {k: o.get(k) for k in ("portal", "url", "tytul", "cena", "powierzchnia_m2", "cena_m2", "rynek",
                                         "ulica", "rok_budowy", "lokalizacja_przyblizona", "polozenie_uwaga")},
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


PAGE = r"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mieszkanie100 mapa</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>
  :root { --bg: #fafaf8; --fg: #1d1d1b; --muted: #66665f; --line: #d9d9d2; --accent: #1f5f8b;
          --low: #2e8b57; --mid: #8a8a80; --high: #c0392b; --new: #111; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #161614; --fg: #ecece6; --muted: #a3a39a; --line: #3a3a35; --accent: #6fb0dd; --new: #fff; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.45 system-ui, sans-serif; }
  header, section { padding: 12px 16px; max-width: 1100px; margin: 0 auto; }
  h1 { font-size: 18px; margin: 0 0 8px; }
  form { display: grid; gap: 8px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; }
  input, select, button { font: inherit; padding: 8px 10px; border: 1px solid var(--line); border-radius: 6px;
                          background: var(--bg); color: var(--fg); min-width: 0; }
  input[name=link] { width: 100%; }
  .row input { flex: 1 1 120px; }
  button { background: var(--accent); color: #fff; border: 0; cursor: pointer; }
  details summary { cursor: pointer; color: var(--muted); }
  #status { color: var(--muted); min-height: 1.4em; }
  #status.err { color: var(--high); }
  #map { height: 62vh; min-height: 320px; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
  .legend { background: var(--bg); color: var(--fg); padding: 6px 8px; border-radius: 6px; font-size: 12px;
            line-height: 1.5; box-shadow: 0 1px 4px rgba(0,0,0,.3); }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: -1px; }
  #summary { font-size: 15px; }
  pre { white-space: pre-wrap; word-break: break-word; font-size: 12.5px; background: transparent;
        border: 1px solid var(--line); border-radius: 6px; padding: 10px; }
</style>
</head>
<body>
<header>
  <h1>Mieszkanie100: oferta na tle sprzedaży i otoczenia</h1>
  <form id="f">
    <input name="link" type="url" placeholder="Wklej link do ogłoszenia (Otodom, OLX z zapisanych wyników, Gratka, …)">
    <details>
      <summary>albo wpisz ręcznie (położenie: środek ulicy z RCN)</summary>
      <div class="row" style="margin-top:8px">
        <input name="ulica" placeholder="ulica, np. Szurmana">
        <input name="cena" placeholder="cena zł" inputmode="numeric">
        <input name="metraz" placeholder="metraż m²" inputmode="decimal">
        <select name="rynek"><option value="">rynek?</option><option value="wtorny">wtórny</option>
          <option value="pierwotny">pierwotny</option></select>
        <input name="rok" placeholder="rok budowy" inputmode="numeric">
      </div>
    </details>
    <div class="row">
      <label>promień <select name="promien"><option>300</option><option selected>500</option><option>1000</option>
        </select> m</label>
      <label>okres <select name="miesiace"><option>12</option><option selected>24</option><option>36</option>
        <option>60</option></select> mies.</label>
      <button type="submit">Pokaż</button>
    </div>
  </form>
  <div id="status"></div>
</header>
<div id="map"></div>
<section>
  <div id="summary"></div>
  <pre id="card" hidden></pre>
</section>
<script>
const map = L.map("map").setView([50.2299, 18.9906], 13);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19, attribution: "&copy; autorzy OpenStreetMap (ODbL) | ceny: RCN, GUGiK"
}).addTo(map);
const control = L.control.layers(null, null, {collapsed: true}).addTo(map);
let layers = [];
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const zl = v => v == null ? "brak" : Math.round(v).toLocaleString("pl-PL");
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const OSM_COLORS = {linia_wn: "#d35400", linia_inna: "#e59866", stacja_energetyczna: "#d35400", maszt: "#8e44ad",
  kolej: "#555", droga_glowna: "#b03a2e", przemysl: "#7f8c8d", skladowisko: "#6e2c00", oczyszczalnia: "#6e2c00",
  kamieniolom: "#6e2c00", droga_w_budowie: "#f39c12", droga_planowana: "#f1c40f", przedszkole: "#27ae60",
  szkola: "#2471a3", przystanek: "#1abc9c"};

const legend = L.control({position: "bottomright"});
legend.onAdd = () => {
  const d = L.DomUtil.create("div", "legend");
  d.innerHTML = `<span class="dot" style="background:${css("--low")}"></span>poniżej typowego<br>
    <span class="dot" style="background:${css("--mid")}"></span>typowa cena<br>
    <span class="dot" style="background:${css("--high")}"></span>powyżej typowego<br>
    <span class="dot" style="border:2px solid ${css("--new")}"></span>budynek do 10 lat (RCN)<br>
    <span class="dot" style="border:3px solid ${css("--accent")}"></span>oferta`;
  return d;
};
legend.addTo(map);

function clear() { layers.forEach(l => { map.removeLayer(l); control.removeLayer(l); }); layers = []; }

function show(data) {
  clear();
  const p25 = data.porownanie.p25, p75 = data.porownanie.p75;
  const color = v => p25 == null ? css("--mid") : v < p25 ? css("--low") : v > p75 ? css("--high") : css("--mid");
  const sales = L.layerGroup(data.transakcje.map(t => L.circleMarker(t.punkt, {
      radius: 7, weight: t.nowy ? 3 : 1, color: t.nowy ? css("--new") : "#fff", fillColor: color(t.cena_m2),
      fillOpacity: .85}).bindPopup(`<b>${zl(t.cena_m2)} zł/m²</b>, ${t.pow_m2} m², rynek ${t.rynek}<br>
      ${esc(t.adres)}, ${t.data}<br>budynek: ${esc(t.wiek)}<br>${t.odleglosc_m} m od oferty`)));
  const circle = L.circle(data.srodek, {radius: data.promien_m, color: css("--accent"), weight: 1, fill: false});
  const o = data.oferta;
  const offer = L.circleMarker(data.srodek, {radius: 16, color: css("--accent"), weight: 5, fill: false})
      .bindPopup(`<b>${esc(o.tytul || "oferta")}</b><br>${zl(o.cena)} zł, ${o.powierzchnia_m2} m²,
      ${zl(o.cena_m2)} zł/m²${data.przyblizone ? "<br><i>położenie przybliżone</i>" : ""}`);
  const main = L.layerGroup([circle, offer, sales]).addTo(map);   // sales on top stay clickable
  layers.push(main); control.addOverlay(main, "oferta i sprzedaże (RCN)");
  const groups = {};
  data.otoczenie.forEach(it => {
    const c = OSM_COLORS[it.kategoria] || "#444";
    const g = L.geoJSON(it.geojson, {style: {color: c, weight: 3, fillOpacity: .15},
      pointToLayer: (f, ll) => L.circleMarker(ll, {radius: 5, color: c, weight: 2, fillOpacity: .6})})
      .bindPopup(`<b>${esc(it.etykieta)}</b>${it.nazwa ? ": " + esc(it.nazwa) : ""}<br>${it.odleglosc_m} m
        ${it.szczegoly ? "<br>" + esc(it.szczegoly) : ""}`);
    (groups[it.etykieta] = groups[it.etykieta] || L.layerGroup()).addLayer(g);
  });
  Object.entries(groups).forEach(([name, g]) => { g.addTo(map); layers.push(g); control.addOverlay(g, name); });
  map.fitBounds(circle.getBounds(), {padding: [20, 20]});
  const s = data.porownanie, n = data.porownanie_nowe;
  const line = (label, x) => x.status === "brak_danych" ? `${label}: brak danych` :
    `${label}: mediana <b>${zl(x.mediana)} zł/m²</b>, typowo ${zl(x.p25)}–${zl(x.p75)}, próbka ${x.proba}` +
    (x.status === "za_mala_proba" ? " (za mała próba)" : "");
  document.getElementById("summary").innerHTML =
    `<p><b>${zl(o.cena_m2)} zł/m²</b> w ofercie: ${esc(data.polozenie || "brak porównania")}.<br>
     ${line(s.rynek, s)}<br>${line("Wtórny, budynki do 10 lat", n)}${data.polozenie_nowe ?
       " (oferta: " + esc(data.polozenie_nowe) + ")" : ""}</p>`;
  const card = document.getElementById("card");
  card.textContent = data.karta; card.hidden = false;
}

document.getElementById("f").addEventListener("submit", async ev => {
  ev.preventDefault();
  const st = document.getElementById("status");
  const q = new URLSearchParams([...new FormData(ev.target)].filter(([k, v]) => v));
  st.className = ""; st.textContent = "Liczę… (pobranie ogłoszenia może potrwać kilka sekund)";
  try {
    const r = await fetch("/api/karta?" + q);
    const data = await r.json();
    if (!data.ok) { st.className = "err"; st.textContent = "Błąd: " + data.blad; return; }
    st.textContent = `Sprzedaży na mapie: ${data.transakcje.length}, obiektów otoczenia: ${data.otoczenie.length}.`;
    show(data);
  } catch (e) { st.className = "err"; st.textContent = "Błąd połączenia: " + e; }
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    sys.exit(main())
