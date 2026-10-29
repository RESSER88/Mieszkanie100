"""Tests for rcn/listy.py (result lists of Nieruchomosci-online and Morizon). Run: python3 -m unittest discover -s tests -v

The HTML below follows the selectors used by marcmos/flatscraper (2026-01); it is not a saved page yet.
"""
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from rcn import listy  # noqa: E402
from rcn.olx import OfferStore  # noqa: E402
import test_portale as tp  # noqa: E402

NO_LIST = """<html><body><section class="tiles">
<div class="tile tile-tile"><h2 class="name"><a href="https://katowice.nieruchomosci-online.pl/mieszkanie,z-ogrodem/26900001.html">
 Mieszkanie z ogrodem, Ligota</a></h2>
 <div class="tertiary__box tertiary__box--primary"><span>1 190 000 zł</span><span>118,50 m²</span></div></div>
<div class="tile"><h2 class="name"><a href="https://katowice.nieruchomosci-online.pl/inwestycja,osiedle/123.html?">Osiedle X</a></h2>
 <div class="tertiary__box--primary"><span>od 500 000 zł</span><span>40 m²</span></div></div>
<div class="tile"><h2 class="name"><a href="https://gliwice.nieruchomosci-online.pl/mieszkanie,m3/26900002.html">Gliwice</a></h2>
 <div class="tertiary__box--primary"><span>600 000 zł</span><span>60 m²</span></div></div>
<div class="tile"><h2 class="name"><a href="https://katowice.nieruchomosci-online.pl/mieszkanie,m2/26900003.html">Małe</a></h2>
 <div class="tertiary__box--primary"><span>400 000 zł</span><span>38 m²</span></div></div>
</section></body></html>"""

MORIZON_LIST = """<html><body>
<div data-cy="card"><a data-cy="propertyUrl" href="/oferta/sprzedaz-mieszkanie-katowice-ligota-panewnicka-120m2-mzn2045678901">x</a>
 <div data-cy="cardPropertyOfferPrice">1 250 000 zł<span>10 417 zł/m²</span></div>
 <div class="property-info">4 pok. 120 m² piętro 2/4</div></div>
<div data-cy="card"><a data-cy="propertyUrl" href="/oferta/sprzedaz-mieszkanie-katowice-centrum-45m2-mzn2045678902">y</a>
 <div data-cy="cardPropertyOfferPrice">520 000 zł</div><div class="property-info">2 pok. 45 m² parter/10</div></div>
</body></html>"""


class ListParserTests(unittest.TestCase):
    def test_nieruchomosci_online_tiles(self):
        items = listy.parse_no_list(NO_LIST, city_url="https://katowice.nieruchomosci-online.pl")
        self.assertEqual([i["id"] for i in items], ["26900001", "26900003"])     # investment and other city left out
        first = items[0]
        self.assertEqual((first["cena"], first["powierzchnia_m2"]), (1190000.0, 118.5))
        self.assertEqual(first["tytul"], "Mieszkanie z ogrodem, Ligota")
        self.assertEqual(first["portal"], "nieruchomosci-online")

    def test_morizon_cards(self):
        items = listy.parse_morizon_list(MORIZON_LIST)
        self.assertEqual([i["id"] for i in items], ["2045678901", "2045678902"])
        first = items[0]
        self.assertEqual(first["url"], "https://www.morizon.pl/oferta/sprzedaz-mieszkanie-katowice-ligota-panewnicka-120m2-mzn2045678901")
        self.assertEqual((first["cena"], first["powierzchnia_m2"], first["pokoje"], first["pietro"]), (1250000.0, 120.0, 4, 2))
        self.assertEqual(items[1]["pietro"], 0)

    def test_page_urls(self):
        self.assertEqual(listy.page_url("https://katowice.nieruchomosci-online.pl/mieszkania,sprzedaz/", 3, "p"),
                         "https://katowice.nieruchomosci-online.pl/mieszkania,sprzedaz/?p=3")
        self.assertEqual(listy.page_url("https://www.morizon.pl/mieszkania/katowice/?ps%5Bliving_area_from%5D=100", 2, "page"),
                         "https://www.morizon.pl/mieszkania/katowice/?ps%5Bliving_area_from%5D=100&page=2")
        self.assertEqual(listy.page_url("https://x.pl/a?page=1", 1, "page"), "https://x.pl/a?page=1")


class SearchTests(unittest.TestCase):
    def test_list_then_details_for_matching_offers_into_the_store(self):
        pages = {"https://katowice.nieruchomosci-online.pl/w/": NO_LIST,
                 "https://katowice.nieruchomosci-online.pl/mieszkanie,z-ogrodem/26900001.html": tp.NO_HTML}
        fetched, sleeps = [], []

        def fetch(url):
            fetched.append(url)
            return (200, pages[url]) if url in pages else (404, None)

        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "oferty.sqlite")
            report = listy.search("nieruchomosci-online", "https://katowice.nieruchomosci-online.pl/w/", db,
                                  area_min=100, max_pages=1, max_details=10, fetch_page=fetch,
                                  sleep=sleeps.append, today=date(2026, 10, 29))
            store = OfferStore(db)
            saved = store.find_by_url("https://katowice.nieruchomosci-online.pl/mieszkanie,z-ogrodem/26900001.html")
            store.close()
        self.assertEqual(fetched, ["https://katowice.nieruchomosci-online.pl/w/",
                                   "https://katowice.nieruchomosci-online.pl/mieszkanie,z-ogrodem/26900001.html"])
        self.assertEqual((report["na_liscie"], report["pasuje"], report["ze_szczegolami"], report["nowe"]), (2, 1, 1, 1))
        self.assertEqual(saved["portal"], "nieruchomosci-online")
        self.assertEqual(saved["id"], "26900001")
        self.assertIsNotNone(saved["lat"])                       # position from the listing page
        self.assertEqual(saved["cena"], 839000.0)                # the listing page wins over the list (it is more complete)
        self.assertTrue(all(s == 3.0 for s in sleeps))

    def test_refusal_stops_and_keeps_what_was_read(self):
        def fetch(url):
            return (403, None)
        with tempfile.TemporaryDirectory() as d:
            report = listy.search("morizon", "https://www.morizon.pl/mieszkania/katowice/", os.path.join(d, "o.sqlite"),
                                  fetch_page=fetch, sleep=lambda s: None, today=date(2026, 10, 29))
        self.assertIn("HTTP 403", report["uwaga"])
        self.assertEqual(report["na_liscie"], 0)


if __name__ == "__main__":
    unittest.main()
