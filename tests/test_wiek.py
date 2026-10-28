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

# Unit ids as on the Pi: parcel, then BUD.<number that differs per unit>, then _LOK.
NEW = "246901_1.0003.AR_45.14/15.5"     # new block: first sale primary 2018
OLD = "246901_1.0003.AR_54.80/2.1"      # old block: secondary sale in 2013
UNK = "246901_1.0003.AR_54.90/1.1"      # only secondary sales after 2016: unknown
EDGE = "246901_1.0003.AR_54.95/1.1"     # first primary sale 2015: borderline
BUD_A, BUD_B = NEW + "|szurmana 2", OLD + "|szurmana 10"
BUD_C, BUD_D = UNK + "|inna 5", EDGE + "|szurmana 18"


def row(gid, parcel, day, market, street="ul. Szurmana", nr="2", unit=None):
    r = dict.fromkeys(ri.Store._COLS)
    unit_id = "%s_BUD.%d_LOK" % (parcel, unit or gid) if parcel else None
    r.update(gid=gid, teryt="2469", tran_id="T%d" % gid, obj_id=unit_id,
             dok_data=day, rodzaj_rynku=market, rodzaj_obiektu="mieszkalna", ulica=street, nr=nr, raw_json="{}")
    return r


def db(path):
    rows = [row(1, NEW, "2018-03-01", "rynekPierwotny"), row(2, NEW, "2019-05-01", "rynekPierwotny"),
            row(3, NEW, "2024-01-10", "rynekWtorny", street="Szurmana", unit=1),
            row(4, OLD, "2013-02-01", "rynekWtorny", nr="10"), row(5, OLD, "2025-02-01", "rynekWtorny", nr="10"),
            row(6, UNK, "2021-06-01", "rynekWtorny", street="ul. Inna", nr="5"),
            row(7, EDGE, "2015-07-01", "rynekPierwotny", nr="18"),
            row(8, None, "2020-01-01", "rynekWtorny")]
    store = ri.Store(path)
    store.save_page("lokale", "2469", rows, 8)
    return store


class KeyTests(unittest.TestCase):
    def test_units_of_one_building_share_a_key(self):
        a = wiek.building_key(NEW + "_BUD.69_LOK", "ul. Szurmana", "2")
        b = wiek.building_key(NEW + "_BUD.74_LOK", "Szurmana", "2")
        self.assertEqual(a, b)
        self.assertEqual(a, BUD_A)

    def test_two_addresses_on_one_parcel_are_two_buildings(self):
        self.assertNotEqual(wiek.building_key(NEW + "_BUD.1_LOK", "ul. Szurmana", "2"),
                            wiek.building_key(NEW + "_BUD.2_LOK", "ul. Szurmana", "4"))

    def test_unit_without_address_grouped_by_parcel(self):
        self.assertEqual(wiek.building_key(NEW + "_BUD.1_LOK", None, None), NEW)
        self.assertIsNone(wiek.building_key("246901_1.0003.AR_54.73/47.1_LOK", "ul. Szurmana", "2"))
        self.assertIsNone(wiek.building_key(None, "ul. Szurmana", "2"))


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


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = db(os.path.join(self.tmp.name, "rcn.sqlite"))
        self.index = wiek.age_index(self.store.con, 2026)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_sale_in_new_building(self):
        entry = wiek.age_of(self.index, NEW + "_BUD.99_LOK", "ul. Szurmana", "2")
        self.assertTrue(wiek.is_new(entry))
        self.assertEqual(wiek.describe(entry), "do 10 lat (szacunek), rok ok. 2018")

    def test_unknown_building_says_since_when_it_stood(self):
        entry = wiek.age_of(self.index, UNK + "_BUD.1_LOK", "ul. Inna", "5")
        self.assertFalse(wiek.is_new(entry))
        self.assertEqual(wiek.describe(entry), "nieznany, stał już w 2021")

    def test_building_missing_from_index(self):
        entry = wiek.age_of(self.index, "246901_9.AR_1.1_BUD.1_LOK", "ul. Nowa", "1")
        self.assertEqual(wiek.describe(entry), "nieznany")
        self.assertEqual(wiek.describe(wiek.age_of(self.index, NEW + "_BUD.1_LOK", "ul. Szurmana", "10")),
                         "nieznany")
        self.assertEqual(wiek.describe(self.index[BUD_B]), "ponad 10 lat")


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
