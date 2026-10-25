import json
import os
import sys
import unittest
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import events.line as L

ORACLE_PATH = os.path.expanduser("~/bb_d1_overnight/_52_oracle.json")


class TestLinePhase1(unittest.TestCase):
    def test_neg_zero_splits(self):
        r1 = L.compare_line("-0/0.5", "-0.5/0")
        self.assertFalse(r1["changed"])
        self.assertEqual(r1["direction"], "SAME")
        r2 = L.compare_line(" -0/0.5 ", "-0.5/0")
        self.assertFalse(r2["changed"])

    def test_neg_zero_vs_pos_split(self):
        r = L.compare_line("-0/0.5", "+0/0.5")
        self.assertTrue(r["changed"])

    def test_pos_zero_equiv(self):
        r1 = L.compare_line("+0/0.5", "0/0.5")
        self.assertFalse(r1["changed"])
        r2 = L.compare_line("0/0.5", "+0.5/0")
        self.assertFalse(r2["changed"])

    def test_invalid_inputs(self):
        for bad in ["", None, "abc", "1/2/3"]:
            r = L.compare_line(bad, "-0.5")
            self.assertIsNone(r["changed"])
            self.assertEqual(r["direction"], "UNKNOWN")

    def test_non_finite_rejected(self):
        for bad in ["inf", "-inf", "nan", "+inf", "1e309"]:
            r = L.compare_line(bad, "-0.5")
            self.assertIsNone(r["changed"], f"{bad} not rejected")
            self.assertEqual(r["direction"], "UNKNOWN")
            # also check parse_line
            self.assertIsNone(L.parse_line(bad), f"parse_line({bad}) not None")

    def test_existing_regression_cases(self):
        cases = [
            ("-0.5", "-0.75", "DEEPER", "QUARTER_STEP", 1.0),
            ("-1", "-1/1.5", "DEEPER", "QUARTER_STEP", 1.0),
            ("-1/1.5", "-1", "SHALLOWER", "QUARTER_STEP", 1.0),
            ("+0.5", "+0.25", "SHALLOWER", "QUARTER_STEP", 1.0),
            ("+0.25", "+0.5", "DEEPER", "QUARTER_STEP", 1.0),
            ("0", "-0.5", "DEEPER", "HALF_STEP", 2.0),
            ("-0.5", "0", "SHALLOWER", "HALF_STEP", 2.0),
            ("0.5", "0/0.5", "SHALLOWER", "QUARTER_STEP", 1.0),
            ("0/0.5", "0.5", "DEEPER", "QUARTER_STEP", 1.0),
            ("1", "1/1.5", "DEEPER", "QUARTER_STEP", 1.0),
            ("1/1.5", "1", "SHALLOWER", "QUARTER_STEP", 1.0),
        ]
        for old, new, d, ct, s in cases:
            r = L.compare_line(old, new)
            self.assertTrue(r["changed"], f"{old}->{new}")
            self.assertEqual(r["direction"], d)
            self.assertEqual(r["change_type"], ct)
            self.assertEqual(r["steps"], s)

    def test_whitespace_handling(self):
        r = L.compare_line(" -0/0.5 ", "-0.5/0")
        self.assertFalse(r["changed"])

    def test_norm_basic(self):
        n = L.norm("-0/0.5")
        self.assertIsNotNone(n)
        self.assertIn("raw", n)
        self.assertIn("legs", n)
        self.assertIn("depth", n)

    def test_neg_zero_not_silent(self):
        n = L.norm("-0/0.5")
        self.assertIsNotNone(n)
        self.assertEqual(n["legs"], [-0.5, -0.0])

    def test_neg_zero_vs_pos_split_value(self):
        r = L.compare_line("-0/0.5", "+0/0.5")
        self.assertTrue(r["changed"])


class TestLinePhase2_52(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(ORACLE_PATH) as f:
            cls.oracle = json.load(f)

    def test_52_migrations(self):
        fail_list = []
        for case in self.oracle:
            r = L.compare_line(case["old"], case["new"])
            exp = case["spec"]
            ok = False
            if exp["changed"] is False:
                ok = (r["changed"] is False)
            elif exp["changed"] is True:
                ok = (r["changed"] is True)
            elif exp["changed"] is None:
                ok = (r["changed"] is None)
            if not ok:
                fail_list.append((case, r))
        self.assertEqual(len(fail_list), 0, f"failures: {fail_list[:5]}")


if __name__ == "__main__":
    unittest.main()
