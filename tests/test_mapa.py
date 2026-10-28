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

    def test_only_portal_links_are_fetched(self):
        for link in ("http://192.168.1.1/admin", "file:///etc/passwd", "https://otodom.pl.evil.com/x",
                     "https://example.com/oferta"):
            status, body = mapa.card_json(self.ctx, {"link": link})
            self.assertEqual(status, 400, link)
            self.assertIn("tylko linki do portali", body["blad"])
        self.assertTrue(mapa.allowed_link("https://www.otodom.pl/pl/oferta/abc"))

    def test_errors_are_messages(self):
        self.assertEqual(mapa.card_json(self.ctx, {})[0], 400)
        status, body = mapa.card_json(self.ctx, {"ulica": "Nieznana", "cena": "1", "metraz": "1"})
        self.assertEqual(status, 422)
        self.assertIn("nie znaleziono ulicy", body["blad"])
        self.assertEqual(mapa.card_json(self.ctx, {"ulica": "Szurmana", "cena": "1", "metraz": "1",
                                                   "promien": "99999"})[0], 400)


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
