"""Tests for rcn/rcn_import.py against a fake WFS server.

The fake server reproduces the format of a real ms:lokale record captured on
2026-10-28 and the quirks observed on the Raspberry Pi: numberMatched=unknown,
pages shorter than COUNT, MapServer exceptions returned with HTTP 200.
Run from the repository root: python3 -m unittest discover -s tests -v
"""
import http.server
import os
import re
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rcn import rcn_import as ri  # noqa: E402

RECORD_TEMPLATE = """    <wfs:member>
      <ms:lokale gml:id="lokale.{gid}">
        <ms:GEOMETRIA>
          <gml:Point gml:id="lokale.{gid}.1" srsName="urn:ogc:def:crs:EPSG::2180">
            <gml:pos>{north} {east}</gml:pos>
          </gml:Point>
        </ms:GEOMETRIA>
        <ms:gid>{gid}</ms:gid>
        <ms:SERWIS_RCN></ms:SERWIS_RCN>
        <ms:TERYT>{teryt}</ms:TERYT>
        <ms:TRAN_LOKALNY_ID_IIP>sygnrcwn-rcwn-tran-0000-{gid:012d}</ms:TRAN_LOKALNY_ID_IIP>
        <ms:TRAN_WERSJA_ID gml:id="lokale.{gid}.TRAN_WERSJA_ID"><gml:timePosition>2014-12-03T00:00:00Z</gml:timePosition></ms:TRAN_WERSJA_ID>
        <ms:TRAN_RODZAJ_TRANS>wolnyRynek</ms:TRAN_RODZAJ_TRANS>
        <ms:TRAN_RODZAJ_RYNKU>rynekWtorny</ms:TRAN_RODZAJ_RYNKU>
        <ms:TRAN_SPRZEDAJACY>osobaFizyczna</ms:TRAN_SPRZEDAJACY>
        <ms:TRAN_KUPUJACY>osobaFizyczna</ms:TRAN_KUPUJACY>
        <ms:TRAN_CENA_BRUTTO>{tran_price}</ms:TRAN_CENA_BRUTTO>
        <ms:DOK_DATA gml:id="lokale.{gid}.DOK_DATA"><gml:timePosition>{date}</gml:timePosition></ms:DOK_DATA>
        <ms:NIER_RODZAJ>nieruchomoscLokalowa</ms:NIER_RODZAJ>
        <ms:NIER_CENA_BRUTTO>{nier_price}</ms:NIER_CENA_BRUTTO>
        <ms:LOK_ID_LOKALU>246901_1.0003.AR_54.73/47.1_BUD.1_LOK_{gid}</ms:LOK_ID_LOKALU>
        <ms:LOK_FUNKCJA>mieszkalna</ms:LOK_FUNKCJA>
        <ms:LOK_LICZBA_IZB>4</ms:LOK_LICZBA_IZB>
        <ms:LOK_POW_UZYT>{area}</ms:LOK_POW_UZYT>
        <ms:LOK_POW_PRZYN></ms:LOK_POW_PRZYN>
        <ms:LOK_CENA_BRUTTO>{lok_price}</ms:LOK_CENA_BRUTTO>
        <ms:LOK_ADRES>MSC:Katowice;UL:ul. Łąkowa;NR_PORZ:7</ms:LOK_ADRES>
      </ms:lokale>
    </wfs:member>
"""

HEADER = """<?xml version='1.0' encoding="UTF-8" ?>
<wfs:FeatureCollection
   xmlns:ms="http://mapserver.gis.umn.edu/mapserver"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   xmlns:wfs="http://www.opengis.net/wfs/2.0"
   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
   timeStamp="2026-10-28T10:50:46" numberMatched="unknown" numberReturned="{n}">
"""

EXCEPTION_REPORT = """<?xml version='1.0' encoding="UTF-8" ?>
<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/1.1" version="2.0.0">
  <ows:Exception exceptionCode="NoApplicableCode"><ows:ExceptionText>msWFSGetFeature(): boom</ows:ExceptionText></ows:Exception>
</ows:ExceptionReport>
"""


def make_row(gid, teryt="2469", price=310000, area="81.3", date="2014-11-24",
             tran_price=None, nier_price=None, lok_price=None):
    return dict(
        gid=gid, teryt=teryt, north="262221.995342", east="494414.001881",
        tran_price=price if tran_price is None else tran_price,
        nier_price=price if nier_price is None else nier_price,
        lok_price=price if lok_price is None else lok_price,
        area=area, date=date)


def make_xml(rows):
    body = "".join(RECORD_TEMPLATE.format(**r) for r in rows)
    return (HEADER.format(n=len(rows)) + body + "</wfs:FeatureCollection>\n").encode("utf-8")


def parse_one(row):
    """Parse a single generated row and return its record."""
    records, _ = ri.parse_feature_collection(make_xml([row]), "lokale")
    return records[0]


class FakeWfs:
    """In-process WFS honoring TERYT, gid > N, SORTBY=gid A and COUNT."""

    def __init__(self, rows):
        self.rows = rows
        self.requests = []          # parsed FILTER gid bounds per request
        self.fail_first = 0         # first N requests answer HTTP 500
        self.exception_first = 0    # next N requests answer ExceptionReport (HTTP 200)
        self.short_by = 0           # return COUNT - short_by rows per page
        self.ignore_gid_filter = False
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                outer._serve(self)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d/wss/service/rcn" % self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def _serve(self, h):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
        flt = query.get("FILTER", [""])[0]
        count = int(query.get("COUNT", ["1000"])[0])
        teryt = re.search(r"<fes:ValueReference>TERYT</fes:ValueReference><fes:Literal>(\d+)<", flt)
        gid_min = re.search(r"<fes:ValueReference>gid</fes:ValueReference><fes:Literal>(\d+)<", flt)
        low = int(gid_min.group(1)) if gid_min else 0
        self.requests.append(low)
        if self.fail_first > 0:
            self.fail_first -= 1
            h.send_response(500)
            h.end_headers()
            return
        if self.exception_first > 0:
            self.exception_first -= 1
            payload = EXCEPTION_REPORT.encode("utf-8")
        else:
            rows = [r for r in self.rows if (not teryt or r["teryt"] == teryt.group(1))]
            if not self.ignore_gid_filter:
                rows = [r for r in rows if r["gid"] > low]
            rows.sort(key=lambda r: r["gid"])
            payload = make_xml(rows[:max(count - self.short_by, 0)])
        h.send_response(200)
        h.send_header("Content-Type", "text/xml")
        h.send_header("Content-Length", str(len(payload)))
        h.end_headers()
        h.wfile.write(payload)


def dataset(total=3200):
    """Every 4th row belongs to another county, so TERYT filtering matters."""
    rows = []
    gid = 47948740
    for i in range(total):
        teryt = "3203" if i % 4 == 3 else "2469"
        rows.append(make_row(gid, teryt=teryt, price=300000 + i, area="50.0",
                             date="2014-%02d-%02d" % (1 + i % 12, 1 + i % 28)))
        gid += 1 + (i % 3)   # gaps in gid are normal: other counties interleave
    return rows


class ParseTests(unittest.TestCase):
    def test_parses_real_like_record(self):
        rec = parse_one(make_row(47955696))
        self.assertEqual(rec["gid"], 47955696)
        self.assertEqual(rec["teryt"], "2469")
        self.assertEqual(rec["dok_data"], "2014-11-24")
        self.assertEqual(rec["tran_cena"], 310000.0)
        self.assertEqual(rec["pow_m2"], 81.3)
        self.assertEqual(rec["obj_cena"], 310000.0)
        self.assertAlmostEqual(rec["cena_m2"], 310000 / 81.3, places=2)
        self.assertEqual(rec["miejscowosc"], "Katowice")
        self.assertEqual(rec["ulica"], "ul. Łąkowa")
        self.assertEqual(rec["nr"], "7")
        self.assertEqual(rec["tran_id"], "sygnrcwn-rcwn-tran-0000-000047955696")
        self.assertTrue(rec["obj_id"].endswith("_LOK_47955696"))

    def test_coordinates_are_north_east(self):
        rec = parse_one(make_row(1))
        self.assertAlmostEqual(rec["y_pl1992"], 262221.995342)   # northing
        self.assertAlmostEqual(rec["x_pl1992"], 494414.001881)   # easting

    def test_empty_elements_become_none_and_raw_json_keeps_everything(self):
        rec = parse_one(make_row(1))
        import json
        raw = json.loads(rec["raw_json"])
        self.assertIsNone(raw["LOK_POW_PRZYN"])
        self.assertEqual(raw["TRAN_KUPUJACY"], "osobaFizyczna")
        self.assertNotIn("TRAN_KUPUJACY", rec)

    def test_exception_report_raises(self):
        with self.assertRaises(ri.WfsError):
            ri.parse_feature_collection(EXCEPTION_REPORT.encode("utf-8"), "lokale")

    def test_price_per_m2_only_when_prices_agree_and_values_valid(self):
        def per_m2(**kw):
            return parse_one(make_row(1, **kw))["cena_m2"]
        self.assertIsNotNone(per_m2())
        self.assertIsNone(per_m2(lok_price=100000))        # package deal: prices differ
        self.assertIsNone(per_m2(area="0"))
        self.assertIsNone(per_m2(area=""))
        self.assertIsNone(per_m2(lok_price=""))
        self.assertIsNone(per_m2(price=0))


class StoreTests(unittest.TestCase):
    def test_insert_is_idempotent_by_gid(self):
        rec = parse_one(make_row(5))
        with tempfile.TemporaryDirectory() as d:
            store = ri.Store(os.path.join(d, "t.sqlite"))
            store.save_page("lokale", "2469", [rec], 5)
            store.save_page("lokale", "2469", [rec], 5)
            self.assertEqual(store.count("lokale", "2469"), 1)
            store.close()


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "rcn.sqlite")
        self.rows = dataset()
        self.server = FakeWfs(self.rows)
        self.client = ri.WfsClient(self.server.url, retries=3, backoff=0.0, sleep=lambda s: None)
        self.expected = sum(1 for r in self.rows if r["teryt"] == "2469")

    def tearDown(self):
        self.server.close()
        self.tmp.cleanup()

    def run_import(self, **kw):
        store = ri.Store(self.db)
        try:
            return ri.import_layer(self.client, store, "lokale", "2469", pause=0.0, **kw), store.count("lokale", "2469")
        finally:
            store.close()

    def test_full_import_only_requested_teryt(self):
        stats, n = self.run_import(page_size=1000)
        self.assertTrue(stats.finished)
        self.assertEqual(n, self.expected)
        self.assertEqual(stats.records, self.expected)

    def test_short_pages_do_not_end_the_import(self):
        self.server.short_by = 1     # every page returns COUNT-1 rows
        stats, n = self.run_import(page_size=100)
        self.assertTrue(stats.finished)
        self.assertEqual(n, self.expected)

    def test_resume_continues_after_checkpoint_without_gaps(self):
        stats, n1 = self.run_import(page_size=500, max_pages=2)
        self.assertFalse(stats.finished)
        self.assertEqual(n1, 1000)
        self.server.requests.clear()
        stats, n2 = self.run_import(page_size=500)
        self.assertTrue(stats.finished)
        self.assertEqual(n2, self.expected)
        self.assertGreater(self.server.requests[0], 0)   # resumed from checkpoint, not from 0
        con = sqlite3.connect(self.db)
        dup = con.execute("SELECT COUNT(*) - COUNT(DISTINCT gid) FROM lokale").fetchone()[0]
        con.close()
        self.assertEqual(dup, 0)

    def test_retries_http_errors_and_exception_reports(self):
        self.server.fail_first = 2
        self.server.exception_first = 1
        stats, n = self.run_import(page_size=1000)
        self.assertTrue(stats.finished)
        self.assertEqual(n, self.expected)
        self.assertEqual(stats.retries, 3)

    def test_gives_up_after_retry_budget(self):
        self.server.fail_first = 99
        with self.assertRaises(ri.WfsError):
            self.run_import(page_size=1000)

    def test_ignored_gid_filter_is_detected_not_looped(self):
        self.server.ignore_gid_filter = True
        with self.assertRaises(ri.RcnError) as ctx:
            self.run_import(page_size=100)
        self.assertIn("gid", str(ctx.exception))

    def test_report_never_claims_completeness_without_reference(self):
        self.run_import(page_size=1000)
        store = ri.Store(self.db)
        text = ri.build_report(store, "lokale", "2469")
        store.close()
        self.assertIn("NIEZWERYFIKOWANA", text)
        self.assertNotIn("ZGODNA", text)
        self.assertIn(str(self.expected), text)

    def test_report_compares_with_expected_count(self):
        self.run_import(page_size=1000)
        store = ri.Store(self.db)
        ok = ri.build_report(store, "lokale", "2469", expect_count=self.expected)
        bad = ri.build_report(store, "lokale", "2469", expect_count=self.expected + 5)
        store.close()
        self.assertIn("ZGODNA", ok)
        self.assertIn("NIEZGODNA", bad)

    def test_report_counts_missing_values_and_date_range(self):
        self.rows.append(make_row(max(r["gid"] for r in self.rows) + 1, area="", date="2026-09-18"))
        self.expected += 1
        self.run_import(page_size=1000)
        store = ri.Store(self.db)
        text = ri.build_report(store, "lokale", "2469")
        store.close()
        self.assertIn("2026-09-18", text)
        self.assertRegex(text, r"bez powierzchni:\s+1\b")


if __name__ == "__main__":
    unittest.main()
