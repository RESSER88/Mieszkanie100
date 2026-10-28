"""Tests for rcn/oferta.py. Run: python3 -m unittest discover -s tests -v"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rcn import oferta as of  # noqa: E402

NEXT_DATA = {
    "props": {"pageProps": {"ad": {
        "price": {"value": 899000, "currency": "PLN"},
        "area": 118.5,
        "rooms": 4,
        "buildYear": 2021,
        "location": {"street": "ul. Biskupa Tadeusza Szurmana", "lat": 50.2205, "lon": 18.9512},
        "contact": {"phone": "+48 600 000 000", "name": "Jan Agent", "city": "Gliwice",
                    "address": "ul. Biurowa 1"},
        "agency": {"address": "ul. Pośrednika 7", "agentPhone": "600111222"},
        "description": "Mieszkanie z ogródkiem " * 50,
    }}},
}
LD_JSON = {
    "@context": "https://schema.org", "@type": "Product", "name": "Mieszkanie 4 pokoje",
    "offers": {"@type": "Offer", "price": "899000", "priceCurrency": "PLN"},
    "geo": {"latitude": "50.2205", "longitude": "18.9512"},
    "seller": {"telephone": "600000000", "email": "a@b.pl"},
}
HTML = """<html><head>
<title>Mieszkanie Katowice Ligota | Portal</title>
<meta property="og:title" content="Mieszkanie 4 pokoje, Ligota">
<meta property="og:image" content="https://img/x.jpg">
<script type="application/ld+json">%s</script>
<script id="__NEXT_DATA__" type="application/json">%s</script>
<script>var noise = 1;</script>
</head><body><a href="tel:600000000">zadzwoń</a></body></html>""" % (json.dumps(LD_JSON), json.dumps(NEXT_DATA))


class CleanUrlTests(unittest.TestCase):
    def test_strips_tracking_parameters(self):
        url = ("https://katowice.nieruchomosci-online.pl/mieszkanie,z-aneksem-kuchennym/26868680.html"
               "?utm_source=google&utm_medium=cpc&gad_source=1&gad_campaignid=1&gclid=abc&utm_id=2")
        self.assertEqual(of.clean_url(url),
                         "https://katowice.nieruchomosci-online.pl/mieszkanie,z-aneksem-kuchennym/26868680.html")

    def test_keeps_other_parameters(self):
        self.assertEqual(of.clean_url("https://x.pl/a?id=5&utm_term=z"), "https://x.pl/a?id=5")

    def test_rejects_non_http(self):
        with self.assertRaises(ValueError):
            of.clean_url("file:///etc/passwd")


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.result = of.extract_structured(HTML)
        self.found = dict(self.result["kandydaci"])

    def test_title_and_sources(self):
        self.assertEqual(self.result["tytul"], "Mieszkanie Katowice Ligota | Portal")
        self.assertEqual(self.result["zrodla"], {"ld_json": 1, "next_data": 1, "meta": 2})

    def test_finds_price_area_coordinates_and_address(self):
        self.assertEqual(self.found["next_data.props.pageProps.ad.price.value"], 899000)
        self.assertEqual(self.found["next_data.props.pageProps.ad.area"], 118.5)
        self.assertEqual(self.found["next_data.props.pageProps.ad.buildYear"], 2021)
        self.assertEqual(self.found["next_data.props.pageProps.ad.location.lat"], 50.2205)
        self.assertEqual(self.found["ld_json[0].geo.longitude"], "18.9512")
        self.assertEqual(self.found["ld_json[0].offers.price"], "899000")
        self.assertIn("Szurmana", self.found["next_data.props.pageProps.ad.location.street"])

    def test_never_outputs_contact_data(self):
        text = json.dumps(self.result, ensure_ascii=False)
        for secret in ("600 000 000", "600000000", "a@b.pl", "Jan Agent", "ul. Biurowa 1", "Gliwice",
                       "600111222", "ul. Pośrednika 7"):
            self.assertNotIn(secret, text)

    def test_long_text_values_are_shortened(self):
        long_values = [v for _, v in self.result["kandydaci"] if isinstance(v, str) and len(v) > 120]
        self.assertEqual(long_values, [])

    def test_page_without_structured_data(self):
        result = of.extract_structured("<html><head><title>Pusta</title></head></html>")
        self.assertEqual((result["tytul"], result["kandydaci"]), ("Pusta", []))

    def test_broken_json_block_is_counted_not_fatal(self):
        result = of.extract_structured('<script type="application/ld+json">{oops</script>')
        self.assertEqual(result["bledne_bloki"], 1)


class ReportTests(unittest.TestCase):
    def test_report_is_compact_and_says_what_to_paste(self):
        text = of.format_probe("https://x.pl/a", 200, "ref/oferty/x.html", of.extract_structured(HTML))
        self.assertIn("HTTP 200", text)
        self.assertIn("next_data.props.pageProps.ad.price.value = 899000", text)
        self.assertLessEqual(len(text.splitlines()), 90)

    def test_report_for_blocked_page(self):
        text = of.format_probe("https://x.pl/a", 403, None, None)
        self.assertIn("HTTP 403", text)
        self.assertIn("portal odmówił", text)


if __name__ == "__main__":
    unittest.main()
