"""Tests for rcn/otodom.py. Run: python3 -m unittest discover -s tests -v

Item fields mirror the Otodom search page saved on the Raspberry Pi on 2026-10-28
(props.pageProps.data.searchAds.items, 32 items per page, no coordinates in items).
"""
import contextlib
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from rcn import otodom  # noqa: E402
import test_karta as tk  # noqa: E402


def ad(n, street="ul. Biskupa Tadeusza Szurmana", district="Ligota-Panewniki", area=120.0, price=1300000,
       rooms="FOUR", floor="GROUND", development=None, related=None, hide=False):
    return {
        "id": 68000000 + n, "slug": "oferta-%d-ID%d" % (n, n), "title": "Oferta %d" % n, "areaInSquareMeters": area,
        "roomsNumber": rooms, "floorNumber": floor, "estate": "FLAT", "transaction": "SELL", "hidePrice": hide,
        "totalPrice": None if hide else {"value": price, "currency": "PLN"},
        "pricePerSquareMeter": None if hide else {"value": round(price / area), "currency": "PLN"},
        "developmentId": 1 if development else None, "developmentTitle": development, "relatedAds": related,
        "agency": {"name": "Biuro XYZ"}, "advertOwner": {"name": "Jan Sprzedawca"},
        "location": {"mapDetails": {"radius": 0},
                     "address": {"street": {"name": street, "number": None} if street else None},
                     "reverseGeocoding": {"locations": [
                         {"locationLevel": "city_or_village", "name": "Katowice"},
                         {"locationLevel": "district", "name": district}]}},
    }


def page_html(items, page_count):
    data = {"props": {"pageProps": {"data": {"searchAds": {"items": items}},
                                    "tracking": {"listing": {"page_count": page_count}}}}}
    return ('<html><script id="__NEXT_DATA__" type="application/json">%s</script></html>'
            % json.dumps(data, ensure_ascii=False))


class FakeOtodom:
    def __init__(self, pages):
        self.pages, self.requests = pages, []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                page = int(query.get("page", ["1"])[0])
                outer.requests.append((page, self.headers.get("User-Agent")))
                body = outer.pages[page - 1].encode() if page <= len(outer.pages) else b""
                self.send_response(200 if body else 404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d/pl/wyniki/sprzedaz/mieszkanie/slaskie/katowice/katowice/katowice" % (
            self.server.server_port)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class ParseTests(unittest.TestCase):
    def test_regular_item(self):
        [o] = otodom.parse_item(ad(1))
        self.assertEqual((o["portal"], o["id"], o["url"]),
                         ("otodom", "68000001", "https://www.otodom.pl/pl/oferta/oferta-1-ID1"))
        self.assertEqual((o["cena"], o["powierzchnia_m2"], o["pokoje"], o["pietro"]), (1300000.0, 120.0, 4, 0))
        self.assertEqual((o["ulica"], o["dzielnica"], o["miejscowosc"]),
                         ("ul. Biskupa Tadeusza Szurmana", "Ligota-Panewniki", "Katowice"))
        self.assertIsNone(o["rynek"])

    def test_development_expands_related_units(self):
        related = [dict(ad(11, area=110.0, price=1200000), developmentTitle=None),
                   dict(ad(12, area=60.0, price=700000), developmentTitle=None)]
        offers = otodom.parse_item(ad(10, development="Ville Garden", related=related))
        self.assertEqual([o["id"] for o in offers], ["68000011", "68000012"])
        self.assertEqual({o["inwestycja"] for o in offers}, {"Ville Garden"})
        self.assertEqual({o["rynek"] for o in offers}, {"pierwotny"})

    def test_hidden_price_and_floor_codes(self):
        [o] = otodom.parse_item(ad(3, hide=True, floor="ABOVE_TENTH", rooms="MORE"))
        self.assertIsNone(o["cena"])
        self.assertEqual((o["pietro"], o["pokoje"]), (11, 10))
        self.assertIn("cena", o["brakuje"])

    def test_no_seller_or_agency_data(self):
        text = json.dumps(otodom.parse_item(ad(4)), ensure_ascii=False)
        self.assertNotIn("Biuro XYZ", text)
        self.assertNotIn("Sprzedawca", text)


class SearchTests(unittest.TestCase):
    def test_pages_by_page_count_with_pause(self):
        srv = FakeOtodom([page_html([ad(1), ad(2)], 2), page_html([ad(3)], 2)])
        try:
            waits = []
            items, pages = otodom.search_all(srv.base, pause=3.0, sleep=waits.append)
            self.assertEqual(([i["id"] for i in items], pages), ([68000001, 68000002, 68000003], 2))
            self.assertEqual([r[0] for r in srv.requests], [1, 2])
            self.assertEqual(waits, [3.0])
            self.assertIn("mieszkanie100", srv.requests[0][1])
        finally:
            srv.close()

    def test_area_filter_is_passed_to_otodom(self):
        self.assertIn("areaMin=100", otodom.page_url(otodom.SEARCH_URL, 1, area_min=100.0))
        self.assertNotIn("areaMin", otodom.page_url(otodom.SEARCH_URL, 1))

    def test_refusal_stops_and_keeps_partial(self):
        srv = FakeOtodom([page_html([ad(1)], 3)])
        try:
            with self.assertRaises(otodom.OtodomError) as ctx:
                otodom.search_all(srv.base, pause=0.0, sleep=lambda s: None)
            self.assertEqual(len(ctx.exception.partial), 1)
            self.assertEqual(len(srv.requests), 2)
        finally:
            srv.close()


class CliTests(unittest.TestCase):
    def test_search_compares_using_street_center(self):
        srv = FakeOtodom([page_html([ad(1), ad(2, district="Dąb", street="ul. Widok"), ad(3, area=50.0)], 1)])
        try:
            with tempfile.TemporaryDirectory() as d:
                rcn = os.path.join(d, "rcn.sqlite")
                tk.rcn_db(rcn, [tk.sale(i, 10000.0 + 50 * i, area=115.0) for i in range(1, 15)])
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = otodom.main(["szukaj", "--url", srv.base, "--rcn-db", rcn,
                                        "--oferty-db", os.path.join(d, "o.sqlite"), "--metraz-od", "100",
                                        "--dzielnica", "Ligota-Panewniki", "--pauza", "0"], today=date(2026, 10, 28))
                text = out.getvalue()
                self.assertEqual(code, 0)
                self.assertIn("Otodom: pobrano 3 ofert z 1 stron", text)
                self.assertIn("pasuje do filtrów: 1", text)
                self.assertIn("[NOWA] Oferta 1", text)
                self.assertIn("powyżej typowego zakresu", text)
                self.assertIn("położenie: środek ulicy", text)
        finally:
            srv.close()


if __name__ == "__main__":
    unittest.main()
