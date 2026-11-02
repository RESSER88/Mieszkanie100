"""Tests for rcn/grunt.py (parcel from ULDK, mining areas from PIG MIDAS). Run: python3 -m unittest discover -s tests -v"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rcn import grunt  # noqa: E402

POINT = (262720.44, 497795.80)          # (northing, easting) EPSG:2180, ul. Szurmana


class FakeFetch:
    def __init__(self, answers):
        self.answers, self.urls = answers, []

    def __call__(self, url):
        self.urls.append(url)
        for key, answer in self.answers.items():
            if key in url:
                return answer
        return 404, None


class UldkTests(unittest.TestCase):
    def test_parcel_and_axis_order(self):
        fetch = FakeFetch({"GetParcelByXY": (200, "0\n246901_1.0003.AR_45.14/15|śląskie|Katowice|Katowice|Ligota|14/15\n")})
        parcel = grunt.parcel(POINT, fetch=fetch)
        self.assertEqual(parcel, {"id": "246901_1.0003.AR_45.14/15", "wojewodztwo": "śląskie", "powiat": "Katowice",
                                  "gmina": "Katowice", "obreb": "Ligota", "numer": "14/15"})
        self.assertIn("xy=497795.80,262720.44,2180", fetch.urls[0])            # easting first

    def test_no_parcel_and_failures(self):
        self.assertIsNone(grunt.parcel(POINT, fetch=FakeFetch({"GetParcelByXY": (200, "-1 brak wyników\n")})))
        with self.assertRaises(grunt.SourceError):
            grunt.parcel(POINT, fetch=FakeFetch({}))


class MidasTests(unittest.TestCase):
    def answer(self, features):
        return 200, json.dumps({"features": [{"attributes": a} for a in features]})

    def test_inside_mining_area_and_terrain(self):
        fetch = FakeFetch({"MapServer/1/query": self.answer([{"OBJECTID": 7, "NAZWA": "Katowice-Ligota", "KOPALINA": "węgiel kamienny",
                                                               "Shape_Area": 1.5}]),
                           "MapServer/2/query": self.answer([{"NAZWA_TG": "Teren górniczy Ligota", "STATUS": "aktywny"}])})
        result = grunt.mining(POINT, fetch=fetch)
        self.assertEqual(result["obszary_gornicze"], [{"NAZWA": "Katowice-Ligota", "KOPALINA": "węgiel kamienny"}])
        self.assertEqual(result["tereny_gornicze"][0]["NAZWA_TG"], "Teren górniczy Ligota")
        self.assertTrue(all("geometry=497795.80,262720.44" in u and "inSR=2180" in u for u in fetch.urls))

    def test_outside(self):
        fetch = FakeFetch({"MapServer/1/query": self.answer([]), "MapServer/2/query": self.answer([])})
        self.assertEqual(grunt.mining(POINT, fetch=fetch), {"obszary_gornicze": [], "tereny_gornicze": []})

    def test_arcgis_error_is_a_source_error(self):
        fetch = FakeFetch({"query": (200, json.dumps({"error": {"code": 400, "message": "Invalid"}}))})
        with self.assertRaises(grunt.SourceError):
            grunt.mining(POINT, fetch=fetch)


class CacheTests(unittest.TestCase):
    def test_same_point_asked_once_within_ttl(self):
        with tempfile.TemporaryDirectory() as d:
            cache = grunt.PointCache(os.path.join(d, "c.sqlite"))
            calls = []

            def work():
                calls.append(1)
                return {"x": 1}
            self.assertEqual(cache.get_or("uldk", POINT, work, today=date(2026, 11, 2)), {"x": 1})
            self.assertEqual(cache.get_or("uldk", (POINT[0] + 0.05, POINT[1]), work, today=date(2026, 11, 20)), {"x": 1})
            self.assertEqual(len(calls), 1)
            cache.get_or("uldk", POINT, work, today=date(2026, 12, 15))             # older than 30 days
            self.assertEqual(len(calls), 2)
            cache.close()

    def test_report_collects_each_source_and_its_error(self):
        fetch = FakeFetch({"GetParcelByXY": (200, "0\nA|s|K|K|Ligota|1\n")})        # MIDAS does not answer
        with tempfile.TemporaryDirectory() as d:
            report = grunt.report(POINT, os.path.join(d, "c.sqlite"), fetch=fetch, today=date(2026, 11, 2))
        self.assertEqual(report["dzialka"]["obreb"], "Ligota")
        self.assertIsNone(report["gornictwo"])
        self.assertIn("MIDAS", report["bledy"][0])


if __name__ == "__main__":
    unittest.main()


MPZP_PLAIN = ("@MPZP TerenyID;Shape;PLAN_ID;OPIS;WR_SYMBOL;OZNACZENIE_TERENU;MAX_WYSOKOSC_BUDYNKU;POW_BIOLOGICZNIE_CZYNNA\r\n"
              "77;Polygon;1234;Tereny zabudowy mieszkaniowej wielorodzinnej;MW;12MW;25;30\r\n")


class ZoningTests(unittest.TestCase):
    def test_plan_from_text_plain(self):
        fetch = FakeFetch({"GetFeatureInfo": (200, MPZP_PLAIN)})
        terms = grunt.zoning(POINT, fetch=fetch)
        self.assertEqual(len(terms), 1)
        t = terms[0]
        self.assertEqual((t["warstwa"], t["symbol"], t["przeznaczenie"]), ("MPZP Tereny", "12MW",
                         "zabudowa mieszkaniowa wielorodzinna"))
        self.assertEqual(t["pola"]["MAX_WYSOKOSC_BUDYNKU"], "25")
        self.assertNotIn("Shape", t["pola"])
        url = fetch.urls[0]
        self.assertIn("CRS=EPSG%3A2180", url)
        self.assertIn("BBOX=262670.44%2C497745.80%2C262770.44%2C497845.80", url)     # northing first in WMS 1.3.0

    def test_header_on_its_own_line_and_no_plan(self):
        text = "@MPZP Tereny\nID;WR_SYMBOL;OPIS\n5;U;usługi\n"
        self.assertEqual(grunt.zoning(POINT, fetch=FakeFetch({"GetFeatureInfo": (200, text)}))[0]["przeznaczenie"],
                         "zabudowa usługowa")
        self.assertEqual(grunt.zoning(POINT, fetch=FakeFetch({"GetFeatureInfo": (200, "m. Katowice: brak wyniku dla wskazanego obszaru")})), [])

    def test_symbol_meanings(self):
        self.assertEqual(grunt.symbol_meaning("3MN"), "zabudowa mieszkaniowa jednorodzinna")
        self.assertEqual(grunt.symbol_meaning("KDL"), "droga publiczna")
        self.assertEqual(grunt.symbol_meaning("1ZP"), "zieleń urządzona")
        self.assertEqual(grunt.symbol_meaning("MW/U"), "zabudowa mieszkaniowa wielorodzinna / zabudowa usługowa")
        self.assertIsNone(grunt.symbol_meaning("XYZ"))


class GeohazardTests(unittest.TestCase):
    def test_identify_collects_layer_names(self):
        answer = json.dumps({"results": [{"layerName": "GDT - obszary udokumentowanej płytkiej eksploatacji złóż węgla kamiennego do 100 m p.p.t.",
                                          "attributes": {"OBJECTID": 1, "OPIS": "eksploatacja płytka"}}]})
        fetch = FakeFetch({"gdt/MapServer/identify": (200, answer), "sopo_obszary/MapServer/identify": (200, '{"results": []}')})
        hazards = grunt.geohazards(POINT, fetch=fetch)
        self.assertEqual(hazards["gdt"][0]["warstwa"][:40], "GDT - obszary udokumentowanej płytkiej e")
        self.assertEqual(hazards["sopo"], [])
        self.assertTrue(all("sr=2180" in u and "geometry=497795.80%2C262720.44" in u for u in fetch.urls))


class MiningSummaryTests(unittest.TestCase):
    def test_known_midas_fields(self):
        s = grunt.mining_summary({"NAZWA_OG": "Stara Ligota I ", "KOPALINA": "METAN POKŁADÓW WĘGLI (MPW), WĘGLE KAMIENNE",
                                  "STATUS": "aktualny", "DATA_WAZNOSCI": "29/05/2035", "NADZOR_OUG": "Okręgowy Urząd Górniczy - Katowice"})
        self.assertEqual(s, "Stara Ligota I: metan pokładów węgli (mpw), węgle kamienne; aktualny, ważny do 29/05/2035;"
                            " nadzór: Okręgowy Urząd Górniczy - Katowice")

    def test_parcel_names_cleaned(self):
        fetch = FakeFetch({"GetParcelByXY": (200, "0\nA|śląskie|powiat Katowice|Katowice (miasto)|Dz. Ligota|14/15\n")})
        p = grunt.parcel(POINT, fetch=fetch)
        self.assertEqual((p["powiat"], p["gmina"], p["obreb"]), ("Katowice", "Katowice", "Ligota"))
