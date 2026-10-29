"""Tests for rcn/mapa.py. Run: python3 -m unittest discover -s tests -v"""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from rcn import mapa  # noqa: E402
from rcn import otoczenie as oz  # noqa: E402
import test_karta as tk  # noqa: E402

TODAY = date(2026, 10, 28)
UNIT = "246901_1.0003.AR_45.14/15.5_BUD.%d_LOK"


def build(d):
    rcn = os.path.join(d, "rcn.sqlite")
    rows = [tk.sale(i, 10000.0 + 50 * i, north_m=10.0 * i) for i in range(1, 13)]
    rows += [tk.sale(500, 12000.0, market="rynekPierwotny", day="2021-05-01", obj_id=UNIT % 1)]
    tk.rcn_db(rcn, rows)
    seq = os.path.join(d, "o.geojsonseq")
    with open(seq, "w", encoding="utf-8") as f:
        f.write("\x1e" + json.dumps({"type": "Feature", "id": "n1", "properties": {"amenity": "kindergarten",
                "name": "P1"}, "geometry": {"type": "Point", "coordinates": [tk.LON, tk.LAT + 0.0027]}}) + "\n")
        f.write("\x1e" + json.dumps({"type": "Feature", "id": "w1", "properties": {"power": "line",
                "voltage": "110000"}, "geometry": {"type": "LineString", "coordinates": [
                    [tk.LON - 0.01, tk.LAT + 0.005], [tk.LON + 0.01, tk.LAT + 0.005]]}}) + "\n")
    osm = os.path.join(d, "osm.sqlite")
    oz.import_geojsonseq(seq, osm)
    return mapa.Context(rcn, osm, os.path.join(d, "oferty.sqlite"), today=TODAY)


class CardJsonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctx = build(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_manual_entry_gives_points_in_wgs84(self):
        status, body = mapa.card_json(self.ctx, {"ulica": "Szurmana", "cena": "839000", "metraz": "65,08"})
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        self.assertTrue(body["przyblizone"])
        self.assertEqual(len(body["transakcje"]), 12)            # the primary sale is outside the 24-month window
        lat, lon = body["transakcje"][0]["punkt"]
        self.assertAlmostEqual(lat, tk.LAT, delta=0.002)
        self.assertAlmostEqual(lon, tk.LON, delta=0.002)
        self.assertEqual(body["porownanie"]["rynek"], "Rynek wtórny")
        self.assertIn("Karta mieszkania", body["karta"])

    def test_surroundings_drawn_as_geojson(self):
        status, body = mapa.card_json(self.ctx, {"ulica": "Szurmana", "cena": "839000", "metraz": "65"})
        kinds = {o["kategoria"]: o for o in body["otoczenie"]}
        self.assertEqual(kinds["przedszkole"]["geojson"]["type"], "Point")
        lon, lat = kinds["przedszkole"]["geojson"]["coordinates"]
        self.assertAlmostEqual(lat, tk.LAT + 0.0027, places=5)
        self.assertEqual(kinds["linia_wn"]["geojson"]["type"], "LineString")

    def test_sections_for_the_page(self):
        from rcn.olx import OfferStore
        store = OfferStore(self.ctx.oferty_db)
        store.upsert([{"portal": "olx", "id": "9", "url": "https://www.olx.pl/d/oferta/9", "tytul": "Obok",
                       "cena": 700000, "powierzchnia_m2": 62.0, "cena_m2": 11290.32, "ulica": None,
                       "miejscowosc": "Katowice", "lat": tk.LAT + 0.001, "lon": tk.LON,
                       "lokalizacja_przyblizona": True}], "2026-10-27")
        store.close()
        status, body = mapa.card_json(self.ctx, {"ulica": "Szurmana", "cena": "839000", "metraz": "65"})
        self.assertEqual([p["id"] for p in body["podobne"]], ["9"])
        self.assertEqual(body["podobne"][0]["polozenie"], "przybliżone")
        labels = [c["etykieta"] for c in body["porownania"]]
        self.assertEqual(labels, ["Rynek wtórny", "Rynek pierwotny",
                                  "Rynek wtórny, tylko budynki do 10 lat (szacunek z RCN)"])
        near = {c["kategoria"]: c for c in body["otoczenie_lista"]}
        self.assertEqual(near["przedszkole"]["grupa"], "na_co_dzien")
        self.assertAlmostEqual(near["przedszkole"]["odleglosc_m"], 240, delta=2)    # from the street centre
        self.assertIsNone(near["kolej"]["odleglosc_m"])
        self.assertEqual(body["budynek"]["powod"], "położenie oferty jest przybliżone")

    def test_power_lines_up_to_10_km(self):
        import json as _json
        seq = os.path.join(self.tmp.name, "far.geojsonseq")
        far = tk.LAT + 6000 / 111200.0             # a 400 kV line 6 km north: outside the 3 km surroundings
        with open(seq, "w", encoding="utf-8") as f:
            f.write("\x1e" + _json.dumps({"type": "Feature", "id": "w9", "properties": {"power": "line",
                    "voltage": "400000", "operator": "PSE"}, "geometry": {"type": "LineString", "coordinates": [
                        [tk.LON - 0.01, far], [tk.LON + 0.01, far]]}}) + "\n")
            f.write("\x1e" + _json.dumps({"type": "Feature", "id": "n9", "properties": {"amenity": "school"},
                    "geometry": {"type": "Point", "coordinates": [tk.LON, far]}}) + "\n")
        oz.import_geojsonseq(seq, self.ctx.osm_db)
        status, body = mapa.card_json(self.ctx, {"ulica": "Szurmana", "cena": "839000", "metraz": "65"})
        drawn = [o for o in body["otoczenie"] if o["kategoria"] == "linia_najwyzsza"]
        self.assertEqual(len(drawn), 1)
        self.assertTrue(drawn[0]["pse"])
        near = {c["kategoria"]: c for c in body["otoczenie_lista"]}
        self.assertAlmostEqual(near["linia_najwyzsza"]["odleglosc_m"], 5940, delta=30)
        self.assertIsNone(near["szkola"]["odleglosc_m"])             # schools stay within 3 km
        self.assertEqual(body["promien_sieci_m"], 10000)

    def test_only_portal_links_are_fetched(self):
        for link in ("http://192.168.1.1/admin", "file:///etc/passwd", "https://otodom.pl.evil.com/x",
                     "https://example.com/oferta"):
            status, body = mapa.card_json(self.ctx, {"link": link})
            self.assertEqual(status, 400, link)
            self.assertIn("tylko linki do portali", body["blad"])
        self.assertTrue(mapa.allowed_link("https://www.otodom.pl/pl/oferta/abc"))

    def test_link_wins_over_leftover_manual_fields(self):
        from unittest import mock
        with mock.patch.object(mapa.karta, "offer_from_link", side_effect=mapa.karta.CardError("pobrano link")) as got:
            status, body = mapa.card_json(self.ctx, {"link": "https://www.otodom.pl/pl/oferta/x-ID1", "ulica": "Szurmana",
                                                     "cena": "839000", "metraz": "65"})
        got.assert_called_once()
        self.assertEqual(body["blad"], "pobrano link")

    def test_errors_are_messages(self):
        self.assertEqual(mapa.card_json(self.ctx, {})[0], 400)
        status, body = mapa.card_json(self.ctx, {"ulica": "Nieznana", "cena": "1", "metraz": "1"})
        self.assertEqual(status, 422)
        self.assertIn("nie znaleziono ulicy", body["blad"])
        self.assertEqual(mapa.card_json(self.ctx, {"ulica": "Szurmana", "cena": "1", "metraz": "1",
                                                   "promien": "99999"})[0], 400)


class MapSelectionTests(unittest.TestCase):
    def item(self, cat, dist, gtype="LineString", coords=None):
        return {"kategoria": cat, "nazwa": None, "odleglosc_m": dist, "szczegoly": "", "typ_geometrii": gtype,
                "geometria": coords or [(250000.0, 500000.0), (250000.0, 500100.0)]}

    def test_power_line_drawn_whole_to_3_km_school_only_nearest(self):
        items = [self.item("linia_wn", 1500 + i) for i in range(30)]
        items += [self.item("szkola", 1500 + i, "Point", (250000.0, 500000.0)) for i in range(30)]
        chosen = mapa._osm_for_map(items)
        self.assertEqual(sum(1 for c in chosen if c["kategoria"] == "linia_wn"), 30)
        self.assertEqual(sum(1 for c in chosen if c["kategoria"] == "szkola"), 1)

    def test_simplify_drops_points_on_a_straight_line_keeps_corners(self):
        line = [(0.0, float(x)) for x in range(0, 101, 5)] + [(50.0, 100.0)]
        self.assertEqual(mapa.simplify(line), [(0.0, 0.0), (0.0, 100.0), (50.0, 100.0)])
        wiggle = [(0.0, 0.0), (1.0, 50.0), (0.0, 100.0)]                 # 1 m off: below the tolerance
        self.assertEqual(len(mapa.simplify(wiggle)), 2)

    def test_pse_flag_for_the_page(self):
        item = self.item("linia_najwyzsza", 800)
        item["szczegoly"] = "napięcie 400 kV, sieć przesyłowa PSE (wg tagu operatora w OSM)"
        self.assertTrue(mapa._osm_for_map([item])[0]["pse"])


class ServerTests(unittest.TestCase):
    def test_page_and_api_over_http(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = build(d)
            server = mapa.ThreadingHTTPServer(("127.0.0.1", 0), mapa.make_handler(ctx))
            server.RequestHandlerClass.log_message = lambda *a: None
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = "http://127.0.0.1:%d" % server.server_address[1]
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                page = opener.open(base + "/").read().decode("utf-8")
                self.assertIn("leaflet@1.9.4", page)
                self.assertIn('integrity="sha256-', page)
                q = urllib.parse.urlencode({"ulica": "Szurmana", "cena": "839000", "metraz": "65"})
                body = json.loads(opener.open(base + "/api/karta?" + q).read().decode("utf-8"))
                self.assertTrue(body["ok"])
                with self.assertRaises(urllib.error.HTTPError) as err:
                    opener.open(base + "/api/karta?link=" + urllib.parse.quote("http://10.0.0.1/"))
                self.assertEqual(err.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
