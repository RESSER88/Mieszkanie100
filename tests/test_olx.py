"""Tests for rcn/olx.py. Run: python3 -m unittest discover -s tests -v

Item shape mirrors the GraphQL response seen on the Raspberry Pi on 2026-10-28
(clientCompatibleListings, 986 sale listings in Katowice).
"""
import contextlib
import http.server
import io
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from rcn import olx  # noqa: E402
import test_karta as tk  # noqa: E402


def item(n, district="Ligota-Panewniki", m_label="120 m²", price=1300000, lat=50.231846, lon=18.968098,
         market="Wtórny", rooms="4 pokoje", floor="Parter"):
    return {
        "id": 900000000 + n, "url": "https://www.olx.pl/d/oferta/mieszkanie-%d-CID3-IDabc%d.html" % (n, n),
        "title": "Mieszkanie %d" % n, "location": {"city": {"name": "Katowice"}, "district": {"name": district}},
        "map": {"lat": lat, "lon": lon},
        "params": [
            {"key": "price", "value": {"__typename": "PriceParam", "value": price, "currency": "PLN"}},
            {"key": "price_per_m", "value": {"__typename": "GenericParam", "key": "x", "label": "10833.33 zł/m²"}},
            {"key": "floor_select", "value": {"__typename": "GenericParam", "key": "floor_0", "label": floor}},
            {"key": "market", "value": {"__typename": "GenericParam", "key": "secondary", "label": market}},
            {"key": "builttype", "value": {"__typename": "GenericParam", "key": "blok", "label": "Blok"}},
            {"key": "m", "value": {"__typename": "GenericParam", "key": "120", "label": m_label}},
            {"key": "rooms", "value": {"__typename": "GenericParam", "key": "four", "label": rooms}},
        ],
    }


class FakeGraphql:
    def __init__(self, items, fail_at_offset=None):
        self.items, self.fail_at, self.requests = items, fail_at_offset, []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                params = {p["key"]: p["value"] for p in body["variables"]["p"]}
                offset, limit = int(params["offset"]), int(params["limit"])
                outer.requests.append((offset, self.headers.get("User-Agent")))
                if outer.fail_at is not None and offset >= outer.fail_at:
                    self.send_response(403)
                    self.end_headers()
                    return
                data = {"data": {"clientCompatibleListings": {
                    "__typename": "ListingSuccess", "data": outer.items[offset:offset + limit],
                    "metadata": {"total_elements": len(outer.items)}}}}
                raw = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d/apigateway/graphql" % self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class ParseTests(unittest.TestCase):
    def test_parse_item(self):
        o = olx.parse_item(item(1, m_label="37,35 m²", price=300000, rooms="2 pokoje"))
        self.assertEqual((o["portal"], o["id"]), ("olx", "900000001"))
        self.assertEqual((o["cena"], o["powierzchnia_m2"], o["pokoje"], o["pietro"]), (300000.0, 37.35, 2, 0))
        self.assertEqual((o["rynek"], o["dzielnica"], o["miejscowosc"], o["zabudowa"]),
                         ("wtorny", "Ligota-Panewniki", "Katowice", "Blok"))
        self.assertAlmostEqual(o["cena_m2"], 300000 / 37.35, places=2)
        self.assertTrue(o["lokalizacja_przyblizona"])
        self.assertEqual(o["brakuje"], [])

    def test_primary_market_and_floor_number(self):
        o = olx.parse_item(item(2, market="Pierwotny", floor="4"))
        self.assertEqual((o["rynek"], o["pietro"]), ("pierwotny", 4))

    def test_missing_map_is_listed(self):
        raw = item(3)
        raw["map"] = None
        self.assertIn("wspolrzedne", olx.parse_item(raw)["brakuje"])

    def test_filters(self):
        o = olx.parse_item(item(4))
        self.assertTrue(olx.matches(o, dzielnice=["ligota-panewniki"], area_min=100))
        self.assertFalse(olx.matches(o, dzielnice=["Załęże"]))
        self.assertFalse(olx.matches(o, area_min=130))
        self.assertFalse(olx.matches(o, price_max=1000000))
        self.assertFalse(olx.matches(o, rynek="pierwotny"))


class SearchTests(unittest.TestCase):
    def test_pages_until_total_with_one_request_at_a_time(self):
        srv = FakeGraphql([item(i) for i in range(95)])
        try:
            waits = []
            client = olx.OlxClient(srv.url, sleep=waits.append)
            items, total = client.search_all(city_id=7691, region_id=6, pause=3.0)
            self.assertEqual((len(items), total), (95, 95))
            self.assertEqual([r[0] for r in srv.requests], [0, 40, 80])
            self.assertEqual(waits, [3.0, 3.0])
            self.assertIn("mieszkanie100", srv.requests[0][1])
        finally:
            srv.close()

    def test_stops_on_refusal_and_keeps_what_it_has(self):
        srv = FakeGraphql([item(i) for i in range(95)], fail_at_offset=40)
        try:
            client = olx.OlxClient(srv.url, sleep=lambda s: None)
            with self.assertRaises(olx.OlxError) as ctx:
                client.search_all(city_id=7691, region_id=6)
            self.assertEqual(len(ctx.exception.partial), 40)
            self.assertEqual(len(srv.requests), 2)        # no retry loop
        finally:
            srv.close()

    def test_max_pages_cap(self):
        srv = FakeGraphql([item(i) for i in range(200)])
        try:
            items, _ = olx.OlxClient(srv.url, sleep=lambda s: None).search_all(7691, 6, max_pages=2)
            self.assertEqual(len(items), 80)
        finally:
            srv.close()


class StoreTests(unittest.TestCase):
    def test_new_offers_are_flagged_once(self):
        with tempfile.TemporaryDirectory() as d:
            store = olx.OfferStore(os.path.join(d, "oferty.sqlite"))
            first = [olx.parse_item(item(i)) for i in range(3)]
            self.assertEqual(len(store.upsert(first, "2026-10-28")), 3)
            second = [olx.parse_item(item(i)) for i in range(4)]
            self.assertEqual([o["id"] for o in store.upsert(second, "2026-10-29")], ["900000003"])
            found = store.find_by_url("https://www.olx.pl/d/oferta/mieszkanie-2-CID3-IDabc2.html?utm_source=x")
            self.assertEqual(found["id"], "900000002")
            store.close()


class CliTests(unittest.TestCase):
    def test_search_report_with_rcn_comparison(self):
        srv = FakeGraphql([item(1), item(2, district="Załęże"), item(3, m_label="45 m²", price=400000)])
        try:
            with tempfile.TemporaryDirectory() as d:
                rcn = os.path.join(d, "rcn.sqlite")
                tk.rcn_db(rcn, [tk.sale(i, 10000.0 + 50 * i, area=115.0) for i in range(1, 15)])
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = olx.main(["szukaj", "--url", srv.url, "--rcn-db", rcn,
                                     "--oferty-db", os.path.join(d, "o.sqlite"), "--dzielnica", "Ligota-Panewniki",
                                     "--metraz-od", "100", "--pauza", "0"], today=date(2026, 10, 28))
                text = out.getvalue()
                self.assertEqual(code, 0)
                self.assertIn("pobrano 3 z 3", text)
                self.assertIn("pasuje do filtrów: 1", text)
                self.assertIn("[NOWA]", text)
                self.assertIn("powyżej typowego zakresu", text)
                self.assertIn("próbka 14", text)
                self.assertNotIn("Załęże", text.split("pasuje do filtrów")[1])
        finally:
            srv.close()


    def test_card_for_olx_link_uses_stored_search_results(self):
        from rcn import karta
        with tempfile.TemporaryDirectory() as d:
            rcn = os.path.join(d, "rcn.sqlite")
            tk.rcn_db(rcn, [tk.sale(i, 10000.0 + 50 * i, area=115.0) for i in range(1, 15)])
            store_path = os.path.join(d, "o.sqlite")
            store = olx.OfferStore(store_path)
            store.upsert([olx.parse_item(item(7))], "2026-10-28")
            store.close()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = karta.main(["https://www.olx.pl/d/oferta/mieszkanie-7-CID3-IDabc7.html", "--rcn-db", rcn,
                                   "--oferty-db", store_path], today=date(2026, 10, 28))
            self.assertEqual(code, 0)
            self.assertIn("Karta mieszkania (olx, ogłoszenie 900000007)", out.getvalue())

    def test_card_for_unknown_olx_link_says_run_search(self):
        from rcn import karta
        with tempfile.TemporaryDirectory() as d:
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = karta.main(["https://www.olx.pl/d/oferta/x-CID3-IDzzz.html",
                                   "--oferty-db", os.path.join(d, "o.sqlite")], today=date(2026, 10, 28))
            self.assertEqual(code, 2)
            self.assertIn("rcn/olx.py szukaj", err.getvalue())


if __name__ == "__main__":
    unittest.main()
