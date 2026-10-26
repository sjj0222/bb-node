import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from events import line as L


class TestLineBB_D1(unittest.TestCase):
    def test_neg_zero_split_parsed(self):
        # -0/0.5 should parse correctly
        p = L.parse_line("-0/0.5")
        self.assertIsNotNone(p)
        self.assertEqual(len(p), 2)
        
    def test_neg_zero_equiv_to_neg_point_five_zero(self):
        # -0/0.5 and -0.5/0 should be equivalent
        r = L.compare_line("-0/0.5", "-0.5/0")
        self.assertFalse(r["changed"])
        self.assertEqual(r["direction"], "SAME")
        
    def test_neg_zero_vs_pos_zero_different(self):
        r = L.compare_line("-0/0.5", "+0/0.5")
        self.assertTrue(r["changed"])
        
    def test_line_raw_preserved(self):
        n = L.norm("-0/0.5")
        self.assertIsNotNone(n)
        self.assertEqual(n["raw"], "-0/0.5")
        
    def test_invalid_inputs(self):
        for bad in ["", None, "abc"]:
            r = L.compare_line(bad, "-0.5")
            self.assertIsNone(r["changed"])
            self.assertEqual(r["direction"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
