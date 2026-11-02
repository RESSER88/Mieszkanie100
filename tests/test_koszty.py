"""Tests for rcn/koszty.py (purchase costs). Run: python3 -m unittest discover -s tests -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rcn import koszty  # noqa: E402


class NotaryTests(unittest.TestCase):
    def test_maximum_rate_brackets(self):
        self.assertEqual(koszty.notary_max(2000), 100)
        self.assertEqual(koszty.notary_max(50000), 710 + 200)
        self.assertEqual(koszty.notary_max(839000), 1010 + 0.004 * 779000)        # 4 126 zł
        self.assertEqual(koszty.notary_max(1500000), 4770 + 0.002 * 500000)
        self.assertEqual(koszty.notary_max(5000000), 10000)                       # capped


class CostTests(unittest.TestCase):
    def items(self, result):
        return {i["klucz"]: i["kwota"] for i in result["jednorazowe"]}

    def test_secondary_market(self):
        r = koszty.costs(839000, 65.08, "wtorny", koszty.Assumptions(prowizja_proc=2.0, wklad_proc=20))
        i = self.items(r)
        self.assertEqual(i["pcc"], 16780.0)
        self.assertAlmostEqual(i["taksa"], round(4126 * 1.23, 2))
        self.assertEqual(i["wpis_wlasnosci"], 200.0)
        self.assertNotIn("zalozenie_kw", i)
        self.assertAlmostEqual(i["prowizja"], round(839000 * 0.02 * 1.23, 2))
        self.assertEqual(i["hipoteka"], 219.0)
        self.assertAlmostEqual(r["razem_jednorazowe"], round(sum(i.values()), 2))
        self.assertEqual(r["kredyt"]["kwota"], 671200.0)

    def test_primary_market_has_no_pcc_two_acts_half_rate_and_finishing(self):
        r = koszty.costs(1000000, 100.0, "pierwotny", koszty.Assumptions(wykonczenie_m2=2500))
        i = self.items(r)
        self.assertNotIn("pcc", i)
        self.assertAlmostEqual(i["taksa"], round(2 * 0.5 * koszty.notary_max(1000000) * 1.23, 2))
        self.assertEqual(i["zalozenie_kw"], 100.0)
        self.assertEqual(i["wykonczenie"], 250000.0)

    def test_monthly_payment_and_fees(self):
        a = koszty.Assumptions(wklad_proc=20, oprocentowanie=7.2, lata=25, czynsz_m2=6.0)
        r = koszty.costs(800000, 80.0, "wtorny", a)
        rate = 0.072 / 12
        expected = 640000 * rate / (1 - (1 + rate) ** -300)
        self.assertAlmostEqual(r["kredyt"]["rata"], round(expected, 2))
        self.assertEqual(r["miesiecznie"]["czynsz"], 480.0)
        self.assertAlmostEqual(r["miesiecznie"]["razem"], round(expected + 480, 2))

    def test_cash_purchase_and_zero_rate(self):
        r = koszty.costs(500000, 50.0, "wtorny", koszty.Assumptions(wklad_proc=100))
        self.assertIsNone(r["kredyt"])
        self.assertNotIn("hipoteka", self.items(r))
        r = koszty.costs(500000, 50.0, "wtorny", koszty.Assumptions(wklad_proc=0, oprocentowanie=0, lata=10))
        self.assertAlmostEqual(r["kredyt"]["rata"], round(500000 / 120, 2))

    def test_from_params_validates(self):
        a = koszty.assumptions_from({"wklad_proc": "30", "oprocentowanie": "6,5", "lata": "20", "prowizja_proc": ""})
        self.assertEqual((a.wklad_proc, a.oprocentowanie, a.lata, a.prowizja_proc), (30.0, 6.5, 20, 0.0))
        for bad in ({"wklad_proc": "120"}, {"lata": "0"}, {"oprocentowanie": "x"}):
            with self.assertRaises(ValueError, msg=bad):
                koszty.assumptions_from(bad)


if __name__ == "__main__":
    unittest.main()
