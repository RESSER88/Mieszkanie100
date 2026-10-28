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
