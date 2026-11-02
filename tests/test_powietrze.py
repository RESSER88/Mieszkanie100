"""Tests for rcn/powietrze.py (GIOŚ air quality). Run: python3 -m unittest discover -s tests -v"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rcn import powietrze  # noqa: E402

STATIONS = {"Lista stacji pomiarowych": [
    {"Identyfikator stacji": 814, "Kod stacji": "SlKatoKossut", "Nazwa stacji": "Katowice, ul. Kossutha",
     "WGS84 φ N": "50.264611", "WGS84 λ E": "18.975028", "Nazwa miasta": "Katowice"},
    {"Identyfikator stacji": 841, "Kod stacji": "SlTychyTolst", "Nazwa stacji": "Tychy, ul. Tołstoja",
     "WGS84 φ N": "50.099903", "WGS84 λ E": "18.990236", "Nazwa miasta": "Tychy"}], "totalPages": 1}
INDEX = {"AqIndex": {"Identyfikator stacji pomiarowej": 814, "Data wykonania obliczeń indeksu": "2026-11-02 12:20:00",
                     "Wartość indeksu": 1, "Nazwa kategorii indeksu": "Dobry",
                     "Data danych źródłowych, z których policzono wartość indeksu dla wskaźnika PM10": "2026-11-02 11:00:00"}}


def fetch(url):
    if "station/findAll" in url:
        return 200, json.dumps(STATIONS)
    if "aqindex/getIndex/814" in url:
        return 200, json.dumps(INDEX)
    return 404, None


class AirTests(unittest.TestCase):
    def test_nearest_station_and_index(self):
        with tempfile.TemporaryDirectory() as d:
            air = powietrze.air_quality(50.23168, 18.96909, os.path.join(d, "c.sqlite"), fetch=fetch, today=date(2026, 11, 2))
        self.assertEqual(air["stacja"], "Katowice, ul. Kossutha")
        self.assertAlmostEqual(air["odleglosc_km"], 3.7, delta=0.15)
        self.assertEqual((air["indeks"], air["czas"]), ("Dobry", "2026-11-02 12:20:00"))

    def test_station_list_cached_index_not(self):
        calls = []

        def counting(url):
            calls.append(url)
            return fetch(url)
        with tempfile.TemporaryDirectory() as d:
            for _ in range(2):
                powietrze.air_quality(50.23, 18.97, os.path.join(d, "c.sqlite"), fetch=counting, today=date(2026, 11, 2))
        self.assertEqual(sum("findAll" in u for u in calls), 1)
        self.assertEqual(sum("getIndex" in u for u in calls), 2)

    def test_index_missing_is_reported(self):
        def no_index(url):
            return fetch(url) if "findAll" in url else (500, None)
        with tempfile.TemporaryDirectory() as d:
            air = powietrze.air_quality(50.23, 18.97, os.path.join(d, "c.sqlite"), fetch=no_index, today=date(2026, 11, 2))
        self.assertEqual(air["stacja"], "Katowice, ul. Kossutha")
        self.assertIsNone(air["indeks"])
        self.assertIn("HTTP 500", air["uwaga"])


if __name__ == "__main__":
    unittest.main()
