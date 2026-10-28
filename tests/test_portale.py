"""Tests for rcn/portale.py. Run: python3 -m unittest discover -s tests -v

Fixtures mirror what `oferta.py probe` showed on the Raspberry Pi on 2026-10-28 for the
same flat listed on Nieruchomosci-online.pl (JSON-LD) and Gratka (Nuxt devalue payload).
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rcn import portale as pt  # noqa: E402

NO_URL = "https://katowice.nieruchomosci-online.pl/mieszkanie,z-aneksem-kuchennym/26868680.html"
GR_URL = "https://gratka.pl/nieruchomosci/mieszkanie-katowice-ligota-biskupa-tadeusza-szurmana/ob/48453361"

NO_LD = [
    {"@type": "Organization", "address": {"@type": "PostalAddress", "streetAddress": "ul. Kardynała Stefana Wyszyńskiego 1",
                                          "addressLocality": "Olsztyn"}},
    {"@type": "BreadcrumbList"},
    {"@type": "WebSite"},
    {"@type": "Apartment",
     "address": {"@type": "PostalAddress", "streetAddress": "Biskupa Tadeusza Szurmana", "addressLocality": "Katowice",
                 "addressCountry": "PL", "addressRegion": "śląskie"},
     "geo": {"@type": "GeoCoordinates", "latitude": 50.231846, "longitude": 18.968098},
     "offers": [{"price": 839000, "priceCurrency": "PLN",
                 "priceSpecification": {"@type": "UnitPriceSpecification", "price": 12891.83, "unitCode": "MTK"}}],
     "numberOfRooms": 4, "floorLevel": 4, "yearBuilt": 2020,
     "floorSize": {"@type": "QuantitativeValue", "value": 65.08, "unitCode": "MTR"}},
]
NO_HTML = ("<html><head><title>Osiedle franciszkańskie w Katowicach ul. Szurmana, Ligota</title>"
           '<meta property="og:title" content="Apartament, ul. Szurmana">'
           + "".join('<script type="application/ld+json">%s</script>' % json.dumps(b, ensure_ascii=False) for b in NO_LD)
           + "</head><body><p>Lokalizacja przybliżona</p><p>Mieszkanie z balkonem.</p>"
             "<p>Kontakt: Jan Kowalski 600 000 000</p></body></html>")

# Nuxt "devalue" payload: values are indices into the array; index 6 is the main listing,
# index 28 a recommended one that must not be picked.
GR_NUXT = [
    ["ShallowReactive", 1], {"data": 2}, {"listing-48453361": 6}, "n", "n", "n",
    {"area": 7, "price": 8, "priceM2": 10, "numberOfRooms": 12, "floor": 13, "marketType": 14,
     "location": 15, "title": 20, "buildingDetailedInformation": 21, "description": 27},
    "65,08 m²", {"amount": 9}, 839000, {"amount": 11}, 12892, 4, 4, "Rynek wtórny",
    {"location": 16, "street": 17, "map": 18}, "Katowice, Ligota", "Biskupa Tadeusza Szurmana",
    {"latitude": 19, "longitude": 24}, 50.2318, "Mieszkanie na sprzedaż 65 m² (4 pok.)",
    [22], {"label": 23, "value": 25}, "Rok budowy", 18.9681, "2020", "x",
    "Lokal oddany do użytku we wrześniu 2020 roku. Balkon o powierzchni około 7 m². Kontakt 600 111 222.",
    {"area": 29, "price": 30, "numberOfRooms": 31}, 50.0, {"amount": 32}, 2, 450000,
]
GR_HTML = ('<html><head><title>Mieszkanie na sprzedaż 65 m² (4 pok.) | Katowice | Gratka</title>'
           '<script type="application/ld+json">{"@type":"Product","price":839000,"priceCurrency":"PLN"}</script>'
           '<script type="application/json" id="__NUXT_DATA__">%s</script></head><body>'
           '<div>Polecane: mieszkanie z ogródkiem 72 m² i tarasem 28 m²</div></body></html>'
           % json.dumps(GR_NUXT, ensure_ascii=False))


class DevalueTests(unittest.TestCase):
    def test_resolves_indices_and_wrappers(self):
        data = pt.devalue_hydrate([["Reactive", 1], {"a": 2, "b": 3}, "x", [4, -1], 1])  # -1 = undefined
        self.assertEqual(data, {"a": "x", "b": [1, None]})

    def test_shared_references_are_reused(self):
        data = pt.devalue_hydrate([{"a": 1, "b": 1}, {"c": 2}, 5])
        self.assertIs(data["a"], data["b"])

    def test_first_object_with_keys_wins(self):
        arr = GR_NUXT
        self.assertEqual(pt.devalue_find_first(arr, {"area", "price", "numberOfRooms"})["numberOfRooms"], 4)


class NieruchomosciOnlineTests(unittest.TestCase):
    def setUp(self):
        self.offer = pt.parse_listing(NO_HTML, NO_URL)

    def test_fields(self):
        o = self.offer
        self.assertEqual((o["portal"], o["id"]), ("nieruchomosci-online", "26868680"))
        self.assertEqual((o["cena"], o["powierzchnia_m2"], o["pokoje"], o["pietro"], o["rok_budowy"]),
                         (839000.0, 65.08, 4, 4, 2020))
        self.assertAlmostEqual(o["cena_m2"], 12891.83)
        self.assertEqual((o["ulica"], o["miejscowosc"]), ("Biskupa Tadeusza Szurmana", "Katowice"))
        self.assertEqual((o["lat"], o["lon"]), (50.231846, 18.968098))

    def test_skips_portal_own_address(self):
        self.assertNotEqual(self.offer["miejscowosc"], "Olsztyn")

    def test_flags_approximate_location(self):
        self.assertTrue(self.offer["lokalizacja_przyblizona"])

    def test_nothing_missing(self):
        self.assertEqual(self.offer["brakuje"], [])

    def test_whole_page_mentions_are_marked_less_certain(self):
        self.assertEqual(self.offer["wzmianki_zrodlo"], "cała strona")

    def test_json_ld_description_preferred_over_page_text(self):
        ld = json.loads(json.dumps(NO_LD))
        ld[3]["description"] = "Mieszkanie z tarasem 30 m²."
        html = NO_HTML.replace(json.dumps(NO_LD[3], ensure_ascii=False), json.dumps(ld[3], ensure_ascii=False))
        offer = pt.parse_listing(html, NO_URL)
        self.assertEqual((offer["wzmianki"], offer["wzmianki_zrodlo"]), ({"taras": 30.0}, "opis"))


class GratkaTests(unittest.TestCase):
    def setUp(self):
        self.offer = pt.parse_listing(GR_HTML, GR_URL)

    def test_main_listing_not_recommended_one(self):
        o = self.offer
        self.assertEqual((o["portal"], o["id"]), ("gratka", "48453361"))
        self.assertEqual((o["cena"], o["powierzchnia_m2"], o["pokoje"], o["pietro"]), (839000.0, 65.08, 4, 4))
        self.assertEqual(o["cena_m2"], 12892.0)

    def test_year_from_detail_list_market_and_coordinates(self):
        o = self.offer
        self.assertEqual(o["rok_budowy"], 2020)
        self.assertEqual(o["rynek"], "wtorny")
        self.assertEqual((o["lat"], o["lon"]), (50.2318, 18.9681))
        self.assertEqual(o["ulica"], "Biskupa Tadeusza Szurmana")

    def test_features_from_description_only(self):
        self.assertEqual(self.offer["wzmianki"]["balkon"], 7.0)
        self.assertNotIn("ogrod", self.offer["wzmianki"])     # garden of a recommended listing
        self.assertNotIn("taras", self.offer["wzmianki"])
        self.assertEqual(self.offer["wzmianki_zrodlo"], "opis")

    def test_location_given_as_list_of_places(self):
        arr = json.loads(json.dumps(GR_NUXT))
        arr[16] = [33, 34, 35]
        arr += ["śląskie", "Katowice", "Ligota"]
        html = GR_HTML.replace(json.dumps(GR_NUXT, ensure_ascii=False), json.dumps(arr, ensure_ascii=False))
        offer = pt.parse_listing(html, GR_URL)
        self.assertEqual((offer["miejscowosc"], offer["dzielnica"]), ("Katowice", "Ligota"))

    def test_offer_never_contains_contact_data(self):
        text = json.dumps(self.offer, ensure_ascii=False) + json.dumps(pt.parse_listing(NO_HTML, NO_URL),
                                                                       ensure_ascii=False)
        for secret in ("600 111 222", "600 000 000", "Kowalski"):
            self.assertNotIn(secret, text)


class FeatureAndHelperTests(unittest.TestCase):
    def test_mentions_with_areas(self):
        w = pt.features_from_text("Parter z ogródkiem 60 m² i tarasem o powierzchni 25,5 m2. Miejsce postojowe w hali.")
        self.assertEqual((w["ogrod"], w["taras"], w["miejsce_postojowe"]), (60.0, 25.5, True))

    def test_mention_without_area_is_true(self):
        self.assertEqual(pt.features_from_text("Duży taras z widokiem.")["taras"], True)

    def test_year_from_text(self):
        self.assertEqual(pt.features_from_text("Budynek oddany do użytku w 2019 r.")["rok"], 2019)
        self.assertEqual(pt.features_from_text("Rok budowy: 2021")["rok"], 2021)

    def test_number_parsing(self):
        self.assertEqual(pt.to_number("65,08 m²"), 65.08)
        self.assertEqual(pt.to_number("839 000 zł"), 839000.0)
        self.assertEqual(pt.to_number({"amount": 12892}), 12892.0)
        self.assertIsNone(pt.to_number("brak"))

    def test_same_offer_across_portals(self):
        a, b = pt.parse_listing(NO_HTML, NO_URL), pt.parse_listing(GR_HTML, GR_URL)
        self.assertTrue(pt.same_offer(a, b))
        c = dict(a, powierzchnia_m2=80.0)
        self.assertFalse(pt.same_offer(a, c))

    def test_unknown_portal_uses_generic_json_ld(self):
        offer = pt.parse_listing(NO_HTML, "https://inny-portal.pl/oferta/123")
        self.assertEqual((offer["portal"], offer["cena"]), ("inny-portal.pl", 839000.0))

    def test_missing_fields_are_listed(self):
        offer = pt.parse_listing("<html><title>x</title></html>", "https://inny-portal.pl/oferta/5")
        self.assertIn("cena", offer["brakuje"])
        self.assertIn("wspolrzedne", offer["brakuje"])



# Otodom listing page: props.pageProps.ad, field names as used by ncola/otodom_scraper (2026-07).
OD_URL = "https://www.otodom.pl/pl/oferta/4-pokoje-z-ogrodem-ligota-ID4abcD"
OD_AD = {
    "id": 66554433, "title": "4 pokoje z ogrodem, Ligota", "market": "SECONDARY", "slug": "4-pokoje-z-ogrodem-ligota-ID4abcD",
    "description": "<p>Mieszkanie na parterze z ogrodem 80 m² i tarasem. Kontakt 600 222 333.</p>",
    "developmentTitle": "Osiedle Franciszkańskie V",
    "target": {"Price": 1290000, "Price_per_m": 10750, "Area": "120", "Rooms_num": ["4"], "Floor_no": ["ground_floor"],
               "Build_year": "2021", "Building_type": ["block"], "City": "katowice",
               "Extras_types": ["balcony", "garden", "terrace", "garage"]},
    "location": {"address": {"street": {"name": "ul. Biskupa Tadeusza Szurmana"}, "city": {"name": "Katowice"}},
                 "coordinates": {"latitude": 50.2318, "longitude": 18.9681},
                 "reverseGeocoding": {"locations": [{"locationLevel": "city", "name": "Katowice"},
                                                    {"locationLevel": "district", "name": "Ligota-Panewniki"}]}},
    "owner": {"id": 1, "name": "Anna Właścicielka"}, "agency": {"id": 2, "name": "Biuro Nieruchomości XYZ"},
}
OD_HTML = ('<html><head><title>4 pokoje | Otodom</title><script id="__NEXT_DATA__" type="application/json">%s'
           '</script></head><body>Polecane: kawalerka z ogródkiem 300 m²</body></html>'
           % json.dumps({"props": {"pageProps": {"ad": OD_AD}}}, ensure_ascii=False))


class OtodomTests(unittest.TestCase):
    def setUp(self):
        self.offer = pt.parse_listing(OD_HTML, OD_URL)

    def test_fields(self):
        o = self.offer
        self.assertEqual((o["portal"], o["id"]), ("otodom", "66554433"))
        self.assertEqual((o["cena"], o["powierzchnia_m2"], o["cena_m2"], o["pokoje"], o["pietro"], o["rok_budowy"]),
                         (1290000.0, 120.0, 10750.0, 4, 0, 2021))
        self.assertEqual((o["rynek"], o["ulica"], o["miejscowosc"], o["dzielnica"]),
                         ("wtorny", "ul. Biskupa Tadeusza Szurmana", "Katowice", "Ligota-Panewniki"))
        self.assertEqual((o["lat"], o["lon"]), (50.2318, 18.9681))
        self.assertEqual(o["inwestycja"], "Osiedle Franciszkańskie V")
        self.assertEqual(o["brakuje"], [])

    def test_features_from_listing_extras_and_description(self):
        w = self.offer["wzmianki"]
        self.assertEqual((w["ogrod"], w["taras"], w["balkon"], w["miejsce_postojowe"]), (80.0, True, True, True))
        self.assertEqual(self.offer["wzmianki_zrodlo"], "opis i cechy ogłoszenia")

    def test_floor_numbers(self):
        self.assertEqual(pt.otodom_floor(["floor_4"]), 4)
        self.assertEqual(pt.otodom_floor("ground_floor"), 0)
        self.assertEqual(pt.otodom_floor(["floor_higher_10"]), 10)
        self.assertIsNone(pt.otodom_floor(None))

    def test_no_owner_or_agency_data(self):
        text = json.dumps(self.offer, ensure_ascii=False)
        for secret in ("Właścicielka", "Biuro Nieruchomości XYZ", "600 222 333"):
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
