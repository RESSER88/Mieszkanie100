"""Tests for rcn/wiek.py. Run: python3 -m unittest discover -s tests -v"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rcn import rcn_import as ri  # noqa: E402
from rcn import wiek  # noqa: E402

BUD_A = "246901_1.0003.AR_54.73/47.1_BUD.1"     # new block: first sale primary 2018
BUD_B = "246901_1.0003.AR_54.80/2.1_BUD.2"      # old block: secondary sale in 2013
BUD_C = "246901_1.0003.AR_54.90/1.1_BUD.1"      # only secondary sales after 2016: unknown
BUD_D = "246901_1.0003.AR_54.95/1.1_BUD.3"      # first primary sale 2015: borderline


def row(gid, building, day, market, street="ul. Szurmana", nr="2"):
    r = dict.fromkeys(ri.Store._COLS)
    r.update(gid=gid, teryt="2469", tran_id="T%d" % gid, obj_id=building + "_LOK" if building else None,
             dok_data=day, rodzaj_rynku=market, rodzaj_obiektu="mieszkalna", ulica=street, nr=nr, raw_json="{}")
    return r


def db(path):
    rows = [row(1, BUD_A, "2018-03-01", "rynekPierwotny"), row(2, BUD_A, "2019-05-01", "rynekPierwotny"),
            row(3, BUD_A, "2024-01-10", "rynekWtorny"),
            row(4, BUD_B, "2013-02-01", "rynekWtorny", nr="10"), row(5, BUD_B, "2025-02-01", "rynekWtorny", nr="10"),
            row(6, BUD_C, "2021-06-01", "rynekWtorny", street="ul. Inna", nr="5"),
            row(7, BUD_D, "2015-07-01", "rynekPierwotny", nr="18"),
            row(8, None, "2020-01-01", "rynekWtorny")]
    store = ri.Store(path)
    store.save_page("lokale", "2469", rows, 8)
    return store


class KeyTests(unittest.TestCase):
    def test_building_key_from_unit_id(self):
        self.assertEqual(wiek.building_key("246901_1.0003.AR_54.73/47.1_BUD.1_LOK"), BUD_A)
        self.assertEqual(wiek.building_key(BUD_A + "_LOK.12"), BUD_A)
        self.assertIsNone(wiek.building_key("246901_1.0003.AR_54.73/47.1_LOK"))
        self.assertIsNone(wiek.building_key(None))


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = db(os.path.join(self.tmp.name, "rcn.sqlite"))
        self.stats = wiek.building_stats(self.store.con)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def age(self, key):
        return wiek.classify(self.stats[key], today_year=2026)

    def test_stats(self):
        a = self.stats[BUD_A]
        self.assertEqual((a["sprzedaze"], a["pierwotne"], a["pierwsza"], a["pierwsza_pierwotna"]),
                         (3, 2, "2018-03-01", "2018-03-01"))
        self.assertEqual(a["adres"], "ul. Szurmana 2")
        self.assertEqual(len(self.stats), 4)          # record without a building id is not counted

    def test_new_building_from_first_primary_sale(self):
        self.assertEqual(self.age(BUD_A), ("do 10 lat (szacunek)", 2018))

    def test_old_building_from_early_secondary_sale(self):
        self.assertEqual(self.age(BUD_B), ("ponad 10 lat", None))

    def test_only_recent_secondary_sales_is_unknown(self):
        self.assertEqual(self.age(BUD_C), ("nieznany", None))

    def test_primary_sale_just_before_cutoff_is_borderline(self):
        self.assertEqual(self.age(BUD_D), ("granica około 10 lat", 2015))


class ReportTests(unittest.TestCase):
    def test_diag_report(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "rcn.sqlite")
            db(path).close()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = wiek.main(["diag", "--db", path, "--ulica", "Szurmana"], today=date(2026, 10, 28))
            text = out.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("rekordów z identyfikatorem budynku: 7 z 8", text)
            self.assertIn("budynków: 4", text)
            self.assertIn("do 10 lat (szacunek): 1 budynków, 3 sprzedaży", text)
            self.assertIn("ul. Szurmana 2 | sprzedaży 3 (pierwotnych 2) | pierwsza 2018-03-01", text)
            self.assertNotIn("ul. Inna", text.split("Budynki przy")[1])


if __name__ == "__main__":
    unittest.main()
