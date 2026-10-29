"""Tests for rcn/filtry.py. Run: python3 -m unittest discover -s tests -v"""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rcn import filtry  # noqa: E402


def o(i, **kw):
    base = {"portal": "olx", "id": str(i), "cena": 800000.0, "powierzchnia_m2": 80.0, "cena_m2": 10000.0,
            "pokoje": 3, "pietro": 2, "rynek": "wtorny", "zabudowa": "blok", "inwestycja": None,
            "pierwszy_raz": "2026-10-01", "ostatnio": "2026-10-29", "odleglosc_m": 100 * i, "takze_na": []}
    base.update(kw)
    return base


TODAY = date(2026, 10, 29)


class ParseTests(unittest.TestCase):
    def test_numbers_and_choices(self):
        f = filtry.parse({"cena_do": "1 200 000", "cena_m2_od": "9500,5", "pokoje_od": "3", "rynek": "pierwotny",
                          "portale": "olx,otodom", "zabudowa": "blok,kamienica", "deweloperzy": "ukryj",
                          "sortuj": "cena_m2", "nowe_dni": "7", "tylko_aktualne": "1"})
        self.assertEqual((f.cena_do, f.cena_m2_od, f.pokoje_od), (1200000.0, 9500.5, 3.0))
        self.assertEqual(f.portale, {"olx", "otodom"})
        self.assertEqual(f.zabudowa, {"blok", "kamienica"})
        self.assertEqual((f.rynek, f.deweloperzy, f.sortuj, f.nowe_dni, f.tylko_aktualne),
                         ("pierwotny", "ukryj", "cena_m2", 7, True))

    def test_bad_values_are_errors(self):
        for bad in ({"cena_od": "x"}, {"cena_od": "5", "cena_do": "1"}, {"rynek": "inny"}, {"sortuj": "losowo"},
                    {"deweloperzy": "?"}, {"pietro_od": "-5"}):
            with self.assertRaises(filtry.FilterError, msg=bad):
                filtry.parse(bad)


class KeepTests(unittest.TestCase):
    def keep(self, offer, **params):
        latest = {"olx": "2026-10-29", "otodom": "2026-10-28"}
        return filtry.keep(offer, filtry.parse(params), latest, TODAY)

    def test_ranges(self):
        self.assertTrue(self.keep(o(1), cena_od="700000", cena_do="900000"))
        self.assertFalse(self.keep(o(1), cena_do="700000"))
        self.assertFalse(self.keep(o(1), cena_m2_do="9000"))
        self.assertFalse(self.keep(o(1), pokoje_od="4"))
        self.assertFalse(self.keep(o(1), pietro_do="1"))
        self.assertTrue(self.keep(o(1, pietro=0), bez_parteru="0"))
        self.assertFalse(self.keep(o(1, pietro=0), bez_parteru="1"))

    def test_unknown_value_fails_a_set_filter_but_not_an_unset_one(self):
        self.assertFalse(self.keep(o(1, pokoje=None), pokoje_od="2"))
        self.assertTrue(self.keep(o(1, pokoje=None)))

    def test_market_building_type_portal(self):
        self.assertFalse(self.keep(o(1), rynek="pierwotny"))
        self.assertFalse(self.keep(o(1), zabudowa="kamienica"))
        self.assertTrue(self.keep(o(1, zabudowa="Blok"), zabudowa="blok"))
        self.assertFalse(self.keep(o(1), portale="otodom"))
        self.assertTrue(self.keep(o(1, takze_na=["otodom"]), portale="otodom"))   # the same flat on Otodom

    def test_developers(self):
        dev = o(1, inwestycja="Ogrody", rynek="pierwotny")
        self.assertFalse(self.keep(dev, deweloperzy="ukryj"))
        self.assertTrue(self.keep(dev, deweloperzy="tylko"))
        self.assertFalse(self.keep(o(2), deweloperzy="tylko"))

    def test_freshness(self):
        self.assertTrue(self.keep(o(1, pierwszy_raz="2026-10-25"), nowe_dni="7"))
        self.assertFalse(self.keep(o(1, pierwszy_raz="2026-10-01"), nowe_dni="7"))
        self.assertFalse(self.keep(o(1, ostatnio="2026-10-20"), tylko_aktualne="1"))
        self.assertTrue(self.keep(o(1, portal="otodom", ostatnio="2026-10-28"), tylko_aktualne="1"))


class SortTests(unittest.TestCase):
    def test_sort_orders_and_missing_last(self):
        offers = [o(1, cena_m2=12000.0), o(2, cena_m2=None), o(3, cena_m2=9000.0, pierwszy_raz="2026-10-28")]
        ids = lambda key: [x["id"] for x in filtry.sort(offers, key)]    # noqa: E731
        self.assertEqual(ids("odleglosc"), ["1", "2", "3"])
        self.assertEqual(ids("cena_m2"), ["3", "1", "2"])
        self.assertEqual(ids("najnowsze"), ["3", "1", "2"])


if __name__ == "__main__":
    unittest.main()


class DeveloperSignalTests(unittest.TestCase):
    def test_signals(self):
        self.assertTrue(filtry.is_developer(o(1, inwestycja="Ogrody")))
        self.assertTrue(filtry.is_developer(o(1, inwestycja_id="46289")))
        self.assertTrue(filtry.is_developer(o(1, rynek="pierwotny")))
        self.assertTrue(filtry.is_developer(o(1, deweloper=True)))
        for title in ("Nowe mieszkanie 3 pok. od dewelopera", "Bezpośrednio od DEWELOPERA, 0% prowizji",
                      "Apartament, inwestycja Franciszkańska, oddanie w 2027", "Mieszkanie bez PCC, Ligota"):
            self.assertTrue(filtry.is_developer(o(1, tytul=title)), title)
        self.assertFalse(filtry.is_developer(o(1, tytul="Mieszkanie po remoncie, Ligota")))

    def test_hide_uses_every_signal(self):
        latest = {"olx": "2026-10-29"}
        f = filtry.parse({"deweloperzy": "ukryj"})
        self.assertFalse(filtry.keep(o(1, tytul="Nowe mieszkanie od dewelopera"), f, latest, TODAY))
        self.assertTrue(filtry.keep(o(2, tytul="Mieszkanie po remoncie"), f, latest, TODAY))
