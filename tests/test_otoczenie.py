"""Tests for rcn/otoczenie.py. Run: python3 -m unittest discover -s tests -v

Reference EPSG:2180 coordinates were computed once with pyproj (EPSG:4326 -> EPSG:2180)
and are hard-coded, so the tests need no extra packages.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rcn import otoczenie as oz  # noqa: E402

REFERENCE = [  # name, lat, lon, northing, easting
    ("Katowice", 50.240265, 19.020127, 263674.942, 501434.811),
    ("Warszawa", 52.2297, 21.0122, 486757.209, 637382.204),
    ("Bielsko-Biala", 49.8224, 19.0584, 217229.934, 504199.494),
    ("Czestochowa", 50.8118, 19.1203, 327214.226, 508472.961),
    ("poludnik 19", 50.0, 19.0, 236968.449, 500000.000),
]


def feature(fid, geometry, **tags):
    return {"type": "Feature", "id": fid, "geometry": geometry, "properties": tags}


def point(lon, lat):
    return {"type": "Point", "coordinates": [lon, lat]}


def line(*coords):
    return {"type": "LineString", "coordinates": [list(c) for c in coords]}


def seq_file(features, path, separator=True):
    with open(path, "w", encoding="utf-8") as f:
        for feat in features:
            f.write(("\x1e" if separator else "") + json.dumps(feat, ensure_ascii=False) + "\n")


# Points near Katowice center (lat 50.2400, lon 19.0200); 0.001 deg lat ~ 111 m, 0.001 deg lon ~ 71 m.
LAT, LON = 50.2400, 19.0200


class ProjectionTests(unittest.TestCase):
    def test_matches_pyproj_reference_within_5_cm(self):
        for name, lat, lon, north, east in REFERENCE:
            y, x = oz.wgs84_to_pl1992(lat, lon)
            self.assertAlmostEqual(y, north, delta=0.05, msg=name)
            self.assertAlmostEqual(x, east, delta=0.05, msg=name)


class GeometryTests(unittest.TestCase):
    def test_point_to_segment_distance(self):
        self.assertAlmostEqual(oz.point_segment_distance((0, 0), (10, -5), (10, 5)), 10.0)
        self.assertAlmostEqual(oz.point_segment_distance((0, 0), (3, 4), (6, 8)), 5.0)   # nearest is an end

    def test_distance_to_polygon_is_zero_inside(self):
        square = [[(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]]
        self.assertEqual(oz.distance_to_shape((5, 5), "Polygon", square), 0.0)
        self.assertAlmostEqual(oz.distance_to_shape((15, 5), "Polygon", square), 5.0)

    def test_distance_to_line_and_point(self):
        self.assertAlmostEqual(oz.distance_to_shape((0, 0), "LineString", [(3, -1), (3, 1)]), 3.0)
        self.assertAlmostEqual(oz.distance_to_shape((0, 0), "Point", (3, 4)), 5.0)


class ClassifyTests(unittest.TestCase):
    def test_basic_categories(self):
        self.assertEqual(oz.classify({"amenity": "kindergarten"}), "przedszkole")
        self.assertEqual(oz.classify({"amenity": "school"}), "szkola")
        self.assertEqual(oz.classify({"highway": "bus_stop"}), "przystanek")
        self.assertEqual(oz.classify({"railway": "tram_stop"}), "przystanek")
        self.assertEqual(oz.classify({"railway": "rail"}), "kolej")
        self.assertEqual(oz.classify({"highway": "trunk"}), "droga_glowna")
        self.assertEqual(oz.classify({"landuse": "industrial"}), "przemysl")
        self.assertEqual(oz.classify({"power": "substation", "voltage": "110000;15000"}), "stacja_energetyczna")

    def test_power_line_by_highest_voltage(self):
        self.assertEqual(oz.classify({"power": "line", "voltage": "110000"}), "linia_wn")
        self.assertEqual(oz.classify({"power": "line", "voltage": "110000;220000"}), "linia_najwyzsza")
        self.assertEqual(oz.classify({"power": "line", "voltage": "400000"}), "linia_najwyzsza")
        self.assertEqual(oz.classify({"power": "line", "voltage": "15000"}), "linia_inna")
        self.assertEqual(oz.classify({"power": "line"}), "linia_inna")       # unknown voltage

    def test_transmission_grid_operator_marks_pse(self):
        tags = {"power": "line", "voltage": "220000", "operator": "PSE S.A."}
        self.assertEqual(oz.classify(tags), "linia_najwyzsza")
        self.assertIn("sieć przesyłowa PSE", oz._details("linia_najwyzsza", tags))
        self.assertIn("sieć przesyłowa PSE", oz._details("linia_najwyzsza", {"voltage": "400000",
                                                                           "operator:wikidata": "Q1749435"}))
        self.assertNotIn("PSE", oz._details("linia_najwyzsza", {"voltage": "220000", "operator": "Tauron"}))

    def test_more_nuisances(self):
        self.assertEqual(oz.classify({"railway": "tram"}), "tramwaj")
        self.assertEqual(oz.classify({"aeroway": "aerodrome", "name": "Muchowiec"}), "lotnisko")
        self.assertEqual(oz.classify({"highway": "secondary"}), "droga_drugorzedna")
        self.assertEqual(oz.classify({"highway": "secondary_link"}), "droga_drugorzedna")
        self.assertIsNone(oz.classify({"highway": "tertiary"}))
        for key in ("linia_najwyzsza", "tramwaj", "lotnisko", "droga_drugorzedna"):
            self.assertIn(key, oz.LABELS)
        self.assertTrue({"linia_najwyzsza", "tramwaj", "droga_drugorzedna"} <= oz.LINEAR)

    def test_roads_under_construction_and_planned(self):
        self.assertEqual(oz.classify({"highway": "construction", "construction": "primary"}), "droga_w_budowie")
        self.assertEqual(oz.classify({"highway": "construction", "construction": "tertiary_link"}), "droga_w_budowie")
        self.assertEqual(oz.classify({"highway": "construction"}), "droga_w_budowie")      # class unknown
        self.assertEqual(oz.classify({"highway": "proposed", "proposed": "motorway"}), "droga_planowana")

    def test_footpaths_and_local_roads_in_construction_are_ignored(self):
        for kind in ("footway", "cycleway", "path", "service", "residential", "steps"):
            self.assertIsNone(oz.classify({"highway": "construction", "construction": kind}), kind)
            self.assertIsNone(oz.classify({"highway": "proposed", "proposed": kind}), kind)

    def test_only_high_voltage_substations(self):
        self.assertEqual(oz.classify({"power": "substation", "substation": "transmission"}), "stacja_energetyczna")
        self.assertIsNone(oz.classify({"power": "substation", "substation": "minor_distribution"}))
        self.assertIsNone(oz.classify({"power": "substation", "voltage": "15000"}))
        self.assertIsNone(oz.classify({"power": "substation"}))

    def test_only_communication_towers_count_as_masts(self):
        self.assertEqual(oz.classify({"man_made": "mast"}), "maszt")
        self.assertEqual(oz.classify({"man_made": "tower", "tower:type": "communication"}), "maszt")
        self.assertIsNone(oz.classify({"man_made": "tower", "tower:type": "observation"}))

    def test_unrelated_tags_are_ignored(self):
        self.assertIsNone(oz.classify({"shop": "bakery"}))
        self.assertIsNone(oz.classify({"highway": "residential"}))


class StoreAndQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.seq = os.path.join(self.tmp.name, "o.geojsonseq")
        self.db = os.path.join(self.tmp.name, "osm.sqlite")
        feats = [
            feature("n1", point(LON, LAT + 0.0027), amenity="kindergarten", name="Przedszkole nr 1"),  # ~300 m N
            feature("n2", point(LON, LAT + 0.0090), amenity="kindergarten", name="Daleko"),            # ~1000 m N
            feature("w3", line((LON - 0.01, LAT - 0.0018), (LON + 0.01, LAT - 0.0018)),
                    power="line", voltage="110000;220000", operator="PSE"),                             # ~200 m S
            feature("w4", line((LON + 0.03, LAT - 0.02), (LON + 0.03, LAT + 0.02)),
                    highway="construction", construction="motorway", opening_date="2027"),             # ~2.1 km E
            feature("n5", point(LON + 0.001, LAT), shop="bakery"),                                     # ignored
            feature("n6", {"type": "Point", "coordinates": []}, amenity="school"),                     # broken
        ]
        seq_file(feats, self.seq)
        self.stats = oz.import_geojsonseq(self.seq, self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_counts_kept_ignored_and_broken(self):
        self.assertEqual(self.stats, {"zapisane": 4, "pominiete": 1, "bledne": 1})

    def test_import_without_record_separator(self):
        path = os.path.join(self.tmp.name, "plain.geojsonseq")
        seq_file([feature("n1", point(LON, LAT), amenity="school")], path, separator=False)
        self.assertEqual(oz.import_geojsonseq(path, os.path.join(self.tmp.name, "p.sqlite"))["zapisane"], 1)

    def test_reimport_drops_objects_missing_from_new_file(self):
        path = os.path.join(self.tmp.name, "small.geojsonseq")
        seq_file([feature("n1", point(LON, LAT), amenity="school")], path)
        oz.import_geojsonseq(path, self.db, force=True)         # a smaller extract, on purpose
        con = oz.connect(self.db)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM osm_obiekty").fetchone()[0], 1)

    def test_reimport_replaces_not_duplicates(self):
        oz.import_geojsonseq(self.seq, self.db)
        con = oz.connect(self.db)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM osm_obiekty").fetchone()[0], 4)

    def test_nearby_sorted_by_distance_with_details(self):
        con = oz.connect(self.db)
        center = oz.wgs84_to_pl1992(LAT, LON)
        found = oz.nearby(con, center, radius_m=3000)
        self.assertEqual([f["kategoria"] for f in found],
                         ["linia_najwyzsza", "przedszkole", "przedszkole", "droga_w_budowie"])
        self.assertAlmostEqual(found[0]["odleglosc_m"], 200, delta=10)
        self.assertEqual(found[0]["szczegoly"], "napięcie 220 kV, sieć przesyłowa PSE (wg tagu operatora w OSM)")
        self.assertEqual(found[1]["nazwa"], "Przedszkole nr 1")
        self.assertIn("rok otwarcia 2027", found[3]["szczegoly"])
        self.assertIn("klasa motorway", found[3]["szczegoly"])

    def test_nearby_respects_radius(self):
        con = oz.connect(self.db)
        found = oz.nearby(con, oz.wgs84_to_pl1992(LAT, LON), radius_m=500)
        self.assertEqual(sorted(f["kategoria"] for f in found), ["linia_najwyzsza", "przedszkole"])


class ReportTests(unittest.TestCase):
    def test_report_says_missing_in_osm_not_absent(self):
        text = oz.format_report("Braci Mniejszych", 1000, [], categories=("przedszkole",))
        self.assertIn("przedszkole: brak w danych OSM w promieniu 1000 m", text)
        self.assertIn("© autorzy OpenStreetMap", text)

    def test_report_shows_nearest_and_count(self):
        items = [{"kategoria": "przedszkole", "odleglosc_m": 312.4, "nazwa": "P1", "szczegoly": ""},
                 {"kategoria": "przedszkole", "odleglosc_m": 980.0, "nazwa": None, "szczegoly": ""}]
        text = oz.format_report("Braci Mniejszych", 1000, items, categories=("przedszkole",))
        self.assertIn("przedszkole: najbliżej 312 m (P1), w promieniu: 2", text)

    def test_linear_objects_count_segments_and_stops_count_names(self):
        items = [{"kategoria": "kolej", "odleglosc_m": 600.0, "nazwa": None, "szczegoly": ""}] * 3
        items += [{"kategoria": "przystanek", "odleglosc_m": 200.0, "nazwa": "Płochy", "szczegoly": ""},
                  {"kategoria": "przystanek", "odleglosc_m": 210.0, "nazwa": "Płochy", "szczegoly": ""},
                  {"kategoria": "przystanek", "odleglosc_m": 400.0, "nazwa": "Kościół", "szczegoly": ""}]
        text = oz.format_report("X", 1000, items, categories=("kolej", "przystanek"))
        self.assertIn("kolej: najbliżej 600 m, odcinków w danych w promieniu: 3", text)
        self.assertIn("przystanek: najbliżej 200 m (Płochy), różnych nazw w promieniu: 2", text)

    def test_cli_near_uses_street_center_from_rcn_db(self):
        from rcn import rcn_import as ri
        with tempfile.TemporaryDirectory() as d:
            seq, osm_db, rcn_db = (os.path.join(d, n) for n in ("o.geojsonseq", "osm.sqlite", "rcn.sqlite"))
            seq_file([feature("n1", point(LON, LAT + 0.0027), amenity="kindergarten", name="P1")], seq)
            oz.import_geojsonseq(seq, osm_db)
            y, x = oz.wgs84_to_pl1992(LAT, LON)
            row = dict.fromkeys(ri.Store._COLS)
            row.update(gid=1, teryt="2469", miejscowosc="Katowice", ulica="ul. Braci Mniejszych",
                       y_pl1992=y, x_pl1992=x, raw_json="{}")
            store = ri.Store(rcn_db)
            store.save_page("lokale", "2469", [row], 1)
            store.close()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = oz.main(["near", "--osm-db", osm_db, "--rcn-db", rcn_db,
                                "--street", "Braci Mniejszych", "--radius", "1000"])
            self.assertEqual(code, 0)
            self.assertIn("przedszkole: najbliżej 300 m (P1)", out.getvalue())


class InverseProjectionTests(unittest.TestCase):
    def test_round_trip_within_a_centimetre(self):
        for lat, lon in ((50.231846, 18.968098), (50.0, 19.0), (49.4, 17.2), (54.8, 23.9)):
            y, x = oz.wgs84_to_pl1992(lat, lon)
            back = oz.pl1992_to_wgs84(y, x)
            self.assertLess(abs(back[0] - lat) * 111000, 0.01)
            self.assertLess(abs(back[1] - lon) * 71000, 0.01)


class ImportGuardTests(unittest.TestCase):
    def write(self, path, n):
        with open(path, "w", encoding="utf-8") as f:
            for i in range(n):
                f.write("\x1e" + json.dumps({"type": "Feature", "id": "n%d" % i, "properties": {"amenity": "school"},
                        "geometry": {"type": "Point", "coordinates": [18.97, 50.23 + i * 1e-4]}}) + "\n")

    def test_much_smaller_extract_does_not_wipe_the_base(self):
        with tempfile.TemporaryDirectory() as d:
            seq, db = os.path.join(d, "o.geojsonseq"), os.path.join(d, "osm.sqlite")
            self.write(seq, 100)
            oz.import_geojsonseq(seq, db)
            self.write(seq, 0)
            with self.assertRaises(oz.ImportGuardError):
                oz.import_geojsonseq(seq, db)
            con = oz.connect(db)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM osm_obiekty").fetchone()[0], 100)
            con.close()
            self.write(seq, 40)
            oz.import_geojsonseq(seq, db, force=True)                 # on purpose
            con = oz.connect(db)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM osm_obiekty").fetchone()[0], 40)
            con.close()

    def test_similar_size_refresh_goes_through(self):
        with tempfile.TemporaryDirectory() as d:
            seq, db = os.path.join(d, "o.geojsonseq"), os.path.join(d, "osm.sqlite")
            self.write(seq, 100)
            oz.import_geojsonseq(seq, db)
            self.write(seq, 90)
            self.assertEqual(oz.import_geojsonseq(seq, db)["zapisane"], 90)


if __name__ == "__main__":
    unittest.main()
