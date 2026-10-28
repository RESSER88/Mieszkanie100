"""Tests for rcn/okolica.py. Run: python3 -m unittest discover -s tests -v"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rcn import okolica as ok  # noqa: E402
from rcn import rcn_import as ri  # noqa: E402


def rec(gid, ulica="ul. Braci Mniejszych", y=262000.0, x=494000.0, day="2026-01-15",
        cena_m2=8000.0, pow_m2=50.0, rynek="rynekWtorny", tran_id=None, obj_id=None,
        miejscowosc="Katowice"):
    row = dict.fromkeys(ri.Store._COLS)
    row.update(
        gid=gid, teryt="2469", tran_id=tran_id or "T%d" % gid, obj_id=obj_id or "O%d" % gid,
        dok_data=day, rodzaj_rynku=rynek, rodzaj_obiektu="mieszkalna", liczba_izb=3,
        pow_m2=pow_m2, cena_m2=cena_m2, miejscowosc=miejscowosc, ulica=ulica, nr="1",
        y_pl1992=y, x_pl1992=x, raw_json="{}")
    if cena_m2 is not None:
        row.update(tran_cena=cena_m2 * pow_m2, nier_cena=cena_m2 * pow_m2, obj_cena=cena_m2 * pow_m2)
    return row


def make_store(rows, path=":memory:"):
    store = ri.Store(path)
    if rows:
        store.save_page("lokale", "2469", rows, max(r["gid"] for r in rows))
    return store


class FindCenterTests(unittest.TestCase):
    def test_averages_street_records(self):
        store = make_store([rec(1, y=262000.0), rec(2, y=262100.0), rec(3, ulica="ul. Inna", y=1.0)])
        y, x, n = ok.find_center(store.con, "Braci Mniejszych")
        self.assertEqual(n, 2)
        self.assertAlmostEqual(y, 262050.0)
        self.assertAlmostEqual(x, 494000.0)

    def test_ignores_case_prefix_and_polish_capitals(self):
        store = make_store([rec(1, ulica="ul. Łąkowa")])
        self.assertIsNotNone(ok.find_center(store.con, "ŁĄKOWA"))
        self.assertIsNotNone(ok.find_center(store.con, "ul. łąkowa"))

    def test_none_when_street_missing(self):
        store = make_store([rec(1)])
        self.assertIsNone(ok.find_center(store.con, "Nieistniejąca"))

    def test_skips_rows_without_coordinates_and_other_cities(self):
        store = make_store([rec(1, y=None, x=None), rec(2, miejscowosc="Gliwice"), rec(3, y=262500.0)])
        y, _, n = ok.find_center(store.con, "Braci Mniejszych")
        self.assertEqual((n, y), (1, 262500.0))


class RadiusTests(unittest.TestCase):
    CENTER = (262000.0, 494000.0)

    def run_query(self, rows, **kw):
        store = make_store(rows)
        args = dict(radius_m=500.0, date_from="2025-01-01", date_to="2026-12-31")
        args.update(kw)
        return ok.transactions_in_radius(store.con, self.CENTER, **args)

    def test_distance_filter(self):
        rows, _ = self.run_query([rec(1, y=262300.0), rec(2, y=262800.0)])   # 300 m and 800 m
        self.assertEqual([r["gid"] for r in rows], [1])
        self.assertAlmostEqual(rows[0]["odleglosc_m"], 300.0)

    def test_uses_euclidean_distance_not_box(self):
        rows, _ = self.run_query([rec(1, y=262400.0, x=494400.0)])           # 566 m diagonal
        self.assertEqual(rows, [])

    def test_date_filter_is_inclusive(self):
        rows, _ = self.run_query([rec(1, day="2025-01-01"), rec(2, day="2026-12-31"),
                                  rec(3, day="2024-12-31")])
        self.assertEqual(sorted(r["gid"] for r in rows), [1, 2])

    def test_area_range(self):
        rows, _ = self.run_query([rec(1, pow_m2=120.0), rec(2, pow_m2=45.0)], area_min=100.0, area_max=140.0)
        self.assertEqual([r["gid"] for r in rows], [1])

    def test_each_transaction_once_latest_version_wins(self):
        rows, _ = self.run_query([rec(1, tran_id="T", obj_id="O"), rec(2, tran_id="T", obj_id="O")])
        self.assertEqual([r["gid"] for r in rows], [2])

    def test_excludes_rows_without_price_per_m2(self):
        rows, _ = self.run_query([rec(1, cena_m2=None), rec(2)])
        self.assertEqual([r["gid"] for r in rows], [2])

    def test_reports_skipped_rows_without_coordinates(self):
        rows, skipped = self.run_query([rec(1, y=None, x=None), rec(2)])
        self.assertEqual(([r["gid"] for r in rows], skipped), ([2], 1))


class SummaryTests(unittest.TestCase):
    def rows(self, values, day="2026-01-15"):
        return [{"cena_m2": float(v), "obj_cena": float(v) * 50, "dok_data": day} for v in values]

    def test_median_and_percentiles(self):
        s = ok.summarize(self.rows(range(1, 12)))
        self.assertEqual((s.n, s.median_m2, s.p25_m2, s.p75_m2), (11, 6.0, 3.5, 8.5))
        self.assertEqual(s.status, "ok")

    def test_period_is_min_max_of_dates(self):
        rows = self.rows(range(1, 12))
        rows[0]["dok_data"] = "2025-03-01"
        rows[1]["dok_data"] = "2026-09-30"
        s = ok.summarize(rows)
        self.assertEqual((s.period_from, s.period_to), ("2025-03-01", "2026-09-30"))

    def test_empty_is_no_data_not_zero(self):
        s = ok.summarize([])
        self.assertEqual(s.status, "brak_danych")
        self.assertIsNone(s.median_m2)

    def test_small_sample_flagged(self):
        s = ok.summarize(self.rows([1, 2, 3]), min_sample=10)
        self.assertEqual(s.status, "za_mala_proba")
        self.assertEqual(s.median_m2, 2.0)

    def test_outliers_stay_in_min_max(self):
        s = ok.summarize(self.rows([1069] + [8000] * 10 + [32532]))
        self.assertEqual((s.min_m2, s.max_m2), (1069.0, 32532.0))


class ReportAndCliTests(unittest.TestCase):
    TODAY = date(2026, 10, 28)

    def run_cli(self, rows, *extra):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.sqlite")
            make_store(rows, path).close()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = ok.main(["--db", path, "--street", "Braci Mniejszych"] + list(extra), today=self.TODAY)
            return code, out.getvalue()

    def many(self, n, **kw):
        return [rec(i, cena_m2=7000.0 + i, **kw) for i in range(1, n + 1)]

    def test_report_has_sample_period_and_market_split(self):
        rows = self.many(12) + [rec(100 + i, rynek="rynekPierwotny", cena_m2=11000.0 + i) for i in range(12)]
        code, text = self.run_cli(rows)
        self.assertEqual(code, 0)
        self.assertIn("Rynek wtórny", text)
        self.assertIn("Rynek pierwotny", text)
        self.assertIn("próbka 12", text)
        self.assertIn("2026-01-15", text)
        self.assertIn("nie pewne daty transakcji", text)

    def test_small_sample_warning(self):
        code, text = self.run_cli(self.many(3))
        self.assertEqual(code, 0)
        self.assertIn("UWAGA", text)

    def test_no_data_says_so_instead_of_zero(self):
        rows = [rec(1, day="2019-01-01")]    # outside the 24-month window
        code, text = self.run_cli(rows)
        self.assertEqual(code, 0)
        self.assertIn("BRAK DANYCH", text)
        self.assertNotIn("mediana 0", text)

    def test_missing_street_returns_2(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.sqlite")
            make_store([rec(1)], path).close()
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = ok.main(["--db", path, "--street", "Zupełnie Inna"], today=self.TODAY)
            self.assertEqual(code, 2)
            self.assertIn("nie znaleziono ulicy", err.getvalue())

    def test_rejects_nonpositive_radius_and_months(self):
        for bad in (["--radius", "0"], ["--radius", "-5"], ["--months", "0"]):
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    ok.main(["--db", ":memory:", "--street", "x"] + bad, today=self.TODAY)

    def test_months_window_arithmetic(self):
        self.assertEqual(ok.months_ago(date(2026, 10, 28), 24), date(2024, 10, 28))
        self.assertEqual(ok.months_ago(date(2026, 3, 31), 1), date(2026, 2, 28))


if __name__ == "__main__":
    unittest.main()
