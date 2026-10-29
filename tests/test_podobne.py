"""Tests for rcn/podobne.py. Run: python3 -m unittest discover -s tests -v"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from rcn import okolica, podobne  # noqa: E402
from rcn import otoczenie as oz  # noqa: E402
from rcn.olx import OfferStore  # noqa: E402
import test_karta as tk  # noqa: E402

CENTER = oz.wgs84_to_pl1992(tk.LAT, tk.LON)


def offer(portal, oid, area, price, lat=None, lon=None, street=None, approx=False):
    return {"portal": portal, "id": oid, "url": "https://www.%s.pl/oferta/%s" % (portal, oid), "tytul": "T" + oid,
            "cena": price, "powierzchnia_m2": area, "cena_m2": round(price / area, 2), "ulica": street,
            "miejscowosc": "Katowice", "lat": lat, "lon": lon, "lokalizacja_przyblizona": approx, "rynek": None}


class StreetIndexTests(unittest.TestCase):
    def test_index_gives_the_same_center_as_find_center(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "rcn.sqlite")
            tk.rcn_db(path, [tk.sale(i, 10000.0, north_m=10.0 * i) for i in range(1, 6)])
            con = sqlite3.connect(path)
            index = okolica.street_index(con)
            for street in ("Szurmana", "ul. Biskupa Szurmana"):
                got, want = okolica.center_from_index(index, street), okolica.find_center(con, street)
                self.assertAlmostEqual(got[0], want[0], places=6)
                self.assertAlmostEqual(got[1], want[1], places=6)
                self.assertEqual(got[2], want[2])
            self.assertIsNone(okolica.center_from_index(index, "Nieznana"))
            con.close()


class SimilarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        rcn = os.path.join(self.tmp.name, "rcn.sqlite")
        tk.rcn_db(rcn, [tk.sale(i, 10000.0, north_m=10.0 * i) for i in range(1, 6)])   # street centre ~30 m north
        self.rcn = sqlite3.connect(rcn)
        self.db = os.path.join(self.tmp.name, "oferty.sqlite")
        north = lambda m: tk.LAT + m / 111200.0    # noqa: E731
        offers = [offer("olx", "1", 66.0, 800000, north(100), tk.LON, approx=True),
                  offer("olx", "2", 64.0, 900000, north(300), tk.LON),
                  offer("olx", "3", 120.0, 1500000, north(50), tk.LON),          # other size
                  offer("olx", "4", 65.0, 700000, north(900), tk.LON),          # too far
                  offer("otodom", "5", 63.0, 760000, street="Szurmana"),        # position from RCN street
                  offer("otodom", "6", 66.0, 800000, north(110), tk.LON)]       # same flat as olx 1
        for i in range(7, 12):
            offers.append(offer("olx", str(i), 65.0, 850000 + 20000 * i, north(400 + i), tk.LON))
        store = OfferStore(self.db)
        store.upsert(offers, "2026-10-27")
        store.close()

    def tearDown(self):
        self.rcn.close()
        self.tmp.cleanup()

    def find(self, **kw):
        return podobne.similar_offers(self.db, okolica.street_index(self.rcn), CENTER, 65.0, **kw)

    def test_nearest_five_of_similar_size(self):
        found = self.find()
        self.assertEqual([o["id"] for o in found], ["5", "1", "2", "7", "8"])
        self.assertEqual(found[0]["polozenie"], "środek ulicy z RCN")
        self.assertEqual(found[1]["polozenie"], "przybliżone")
        self.assertEqual(found[2]["polozenie"], "z ogłoszenia")
        self.assertAlmostEqual(found[1]["odleglosc_m"], 100, delta=2)
        self.assertEqual(found[1]["ostatnio"], "2026-10-27")

    def test_same_flat_on_two_portals_listed_once(self):
        found = self.find(limit=10)
        ids = [o["id"] for o in found]
        self.assertNotIn("6", ids)
        self.assertEqual(found[ids.index("1")]["takze_na"], ["otodom"])

    def test_the_card_offer_itself_is_left_out(self):
        me = offer("olx", "1", 66.0, 800000)
        self.assertNotIn("1", [o["id"] for o in self.find(exclude=me)])
        self.assertNotIn("6", [o["id"] for o in self.find(exclude=me)])      # its copy on Otodom too

    def test_missing_store_or_area_gives_nothing(self):
        self.assertEqual(podobne.similar_offers(os.path.join(self.tmp.name, "brak.sqlite"), {}, CENTER, 65.0), [])
        self.assertEqual(podobne.similar_offers(self.db, {}, CENTER, None), [])


if __name__ == "__main__":
    unittest.main()


class AreaSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "oferty.sqlite")
        north = lambda m: tk.LAT + m / 111200.0    # noqa: E731
        offers = [offer("olx", "a", 95.0, 1100000, north(200), tk.LON),
                  offer("olx", "b", 130.0, 1500000, north(250), tk.LON),
                  offer("olx", "c", 70.0, 700000, north(260), tk.LON),                    # too small
                  offer("olx", "d", 110.0, 1200000, north(5000), tk.LON)]                 # too far
        dev = [offer("otodom", "u%d" % i, 100.0 + i, 1000000 + 20000 * i, north(600), tk.LON) for i in range(4)]
        for o in dev:
            o["inwestycja"], o["rynek"] = "Ogrody Panewnickie", "pierwotny"
        store = OfferStore(self.db)
        store.upsert(offers + dev, "2026-10-29")
        store.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_offers_in_range_and_radius(self):
        found = podobne.offers_in_area(self.db, [], CENTER, 1000.0, 90.0, 140.0)
        self.assertEqual([o["id"] for o in found], ["a", "b", "u0", "u1", "u2", "u3"])

    def test_development_units_grouped(self):
        groups = podobne.group_offers(podobne.offers_in_area(self.db, [], CENTER, 1000.0, 90.0, 140.0))
        dev = [g for g in groups if g["inwestycja"]]
        self.assertEqual(len(dev), 1)
        g = dev[0]
        self.assertEqual((g["nazwa"], g["liczba"]), ("Ogrody Panewnickie", 4))
        self.assertEqual((g["metraz_od"], g["metraz_do"]), (100.0, 103.0))
        self.assertEqual(len(groups), 3)                       # a, b and the development

    def test_offers_at_one_point_grouped_without_investment_name(self):
        north = tk.LAT + 300 / 111200.0
        same = [offer("olx", "p%d" % i, 100.0, 1000000 + 50000 * i, north, tk.LON) for i in range(3)]
        db = os.path.join(self.tmp.name, "punkt.sqlite")
        store = OfferStore(db)
        store.upsert(same, "2026-10-29")
        store.close()
        groups = podobne.group_offers(podobne.offers_in_area(db, [], CENTER, 1000.0, 90.0, 140.0))
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["liczba"], 3)
        self.assertIsNone(groups[0]["inwestycja"])


class InvestmentIdTests(unittest.TestCase):
    def test_units_with_one_investment_id_grouped_even_at_different_points(self):
        units = []
        for i in range(3):
            u = offer("nieruchomosci-online", "n%d" % i, 100.0, 1000000 + 30000 * i, tk.LAT + i * 0.001, tk.LON)
            u["inwestycja_id"] = "46289"
            units.append(u)
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "o.sqlite")
            store = OfferStore(db)
            store.upsert(units, "2026-10-29")
            store.close()
            groups = podobne.group_offers(podobne.offers_in_area(db, [], CENTER, 2000.0))
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["inwestycja"], "inwestycja nr 46289 (nieruchomosci-online)")
