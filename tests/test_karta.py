"""Tests for rcn/karta.py. Run: python3 -m unittest discover -s tests -v"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from rcn import karta as kt  # noqa: E402
from rcn import otoczenie as oz  # noqa: E402
from rcn import portale as pt  # noqa: E402
from rcn import rcn_import as ri  # noqa: E402
import test_portale as tp  # noqa: E402

TODAY = date(2026, 10, 28)
LAT, LON = 50.231846, 18.968098


def sale(gid, m2_price, area=65.0, market="rynekWtorny", north_m=0.0, day="2026-03-01"):
    y, x = oz.wgs84_to_pl1992(LAT, LON)
    row = dict.fromkeys(ri.Store._COLS)
    row.update(gid=gid, teryt="2469", tran_id="T%d" % gid, obj_id="O%d" % gid, dok_data=day, rodzaj_rynku=market,
               rodzaj_obiektu="mieszkalna", pow_m2=area, cena_m2=m2_price, obj_cena=m2_price * area,
               tran_cena=m2_price * area, nier_cena=m2_price * area, miejscowosc="Katowice",
               ulica="ul. Szurmana", nr=str(gid), y_pl1992=y + north_m, x_pl1992=x,
               raw_json=json.dumps({"NIER_UDZIAL": "1/1", "TRAN_RODZAJ_TRANS": "wolnyRynek"}))
    return row


def rcn_db(path, rows):
    store = ri.Store(path)
    store.save_page("lokale", "2469", rows, max(r["gid"] for r in rows))
    store.close()


class CardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rcn = os.path.join(self.tmp.name, "rcn.sqlite")
        rows = [sale(i, 10000.0 + 50 * i, north_m=10.0 * i) for i in range(1, 21)]        # 10 050..11 000 zl/m2
        rows += [sale(100 + i, 12500.0 + 100 * i, market="rynekPierwotny") for i in range(12)]  # 12 500..13 600
        rows += [sale(200, 20000.0, area=120.0), sale(201, 9000.0, north_m=900.0)]          # other size, too far
        rcn_db(self.rcn, rows)
        self.offer = pt.parse_listing(tp.NO_HTML, tp.NO_URL)    # 65.08 m2, 12 891.83 zl/m2, market unknown

    def tearDown(self):
        self.tmp.cleanup()

    def card(self, **kw):
        con = __import__("sqlite3").connect(self.rcn)
        try:
            return kt.build_card(self.offer, con, today=TODAY, **kw)
        finally:
            con.close()

    def test_offer_above_typical_secondary_range(self):
        card = self.card()
        self.assertEqual(card["rynek_porownania"], "rynekWtorny")
        self.assertEqual(card["polozenie"], "powyżej typowego zakresu")
        self.assertEqual(card["odsetek_tanszych"], 100.0)

    def test_comparables_limited_by_area_and_radius(self):
        card = self.card()
        wt = dict(card["porownanie"])["Rynek wtórny"]
        self.assertEqual(wt.n, 20)       # the 120 m2 sale and the 900 m away sale are left out

    def test_offer_market_decides_comparison(self):
        self.offer["rynek"] = "pierwotny"
        card = self.card()
        self.assertEqual(card["rynek_porownania"], "rynekPierwotny")
        self.assertEqual(card["polozenie"], "w typowym zakresie")

    def test_report_text(self):
        text = kt.format_card(self.card())
        for expected in ("839 000 zł", "65,08 m²", "12 892 zł/m²", "powyżej typowego zakresu", "próbka 20",
                         "Lokalizacja w ogłoszeniu jest przybliżona", "ceny ofertowej", "rok budowy 2020",
                         "Najbliższe sprzedaże"):
            self.assertIn(expected, text)

    def test_missing_coordinates_is_an_error_not_a_guess(self):
        self.offer["lat"] = self.offer["lon"] = None
        with self.assertRaises(kt.CardError):
            self.card()

    def test_osm_section_when_database_given(self):
        seq = os.path.join(self.tmp.name, "o.geojsonseq")
        with open(seq, "w", encoding="utf-8") as f:
            f.write("\x1e" + json.dumps({"type": "Feature", "id": "n1", "properties": {"amenity": "kindergarten",
                    "name": "P1"}, "geometry": {"type": "Point", "coordinates": [LON, LAT + 0.0027]}}) + "\n")
        osm = os.path.join(self.tmp.name, "osm.sqlite")
        oz.import_geojsonseq(seq, osm)
        con = oz.connect(osm)
        card = self.card(osm_con=con)
        con.close()
        self.assertIn("przedszkole: najbliżej 300 m (P1)", kt.format_card(card))


class CliTests(unittest.TestCase):
    def test_card_from_saved_file(self):
        with tempfile.TemporaryDirectory() as d:
            html = os.path.join(d, "ogl.html")
            with open(html, "w", encoding="utf-8") as f:
                f.write(tp.NO_HTML)
            db = os.path.join(d, "rcn.sqlite")
            rcn_db(db, [sale(i, 10000.0 + 50 * i) for i in range(1, 15)])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = kt.main([tp.NO_URL, "--file", html, "--rcn-db", db], today=TODAY)
            self.assertEqual(code, 0)
            self.assertIn("Karta mieszkania", out.getvalue())

    def test_missing_coordinates_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            html = os.path.join(d, "ogl.html")
            with open(html, "w", encoding="utf-8") as f:
                f.write("<html><title>x</title></html>")
            db = os.path.join(d, "rcn.sqlite")
            rcn_db(db, [sale(1, 10000.0)])
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = kt.main(["https://inny.pl/oferta/12345", "--file", html, "--rcn-db", db], today=TODAY)
            self.assertEqual(code, 2)
            self.assertIn("współrzędnych", err.getvalue())


if __name__ == "__main__":
    unittest.main()
