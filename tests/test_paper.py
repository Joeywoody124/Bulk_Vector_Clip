import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fieldkit.core import paper  # noqa: E402


class ParseScaleTest(unittest.TestCase):
    def test_ratio(self):
        self.assertEqual(paper.parse_scale("1:2000"), 2000)
        self.assertEqual(paper.parse_scale("1:500"), 500)

    def test_engineering(self):
        self.assertEqual(paper.parse_scale("1\"=50'"), 600)
        self.assertEqual(paper.parse_scale("1\"=20'"), 240)
        self.assertEqual(paper.parse_scale("1 in = 100 ft"), 1200)

    def test_metric_equals(self):
        self.assertEqual(paper.parse_scale("1cm=20m"), 2000)

    def test_bare_number(self):
        self.assertEqual(paper.parse_scale("600"), 600)

    def test_rejects_nonsense(self):
        for bad in ("", "banana", "1:0", "-5"):
            with self.assertRaises(ValueError):
                paper.parse_scale(bad)

    def test_scale_list(self):
        self.assertEqual(
            paper.parse_scale_list("1\"=20',1\"=50',1:1000"), [240, 600, 1000]
        )


class SheetSizeTest(unittest.TestCase):
    def test_arch_d_at_1in_50ft(self):
        # 24x36 landscape, 1" margins -> 22x34 printable. At 1"=50' that is
        # 1100 x 1700 feet, which is the number you would work out by hand.
        width, height = paper.sheet_size(
            paper.PAPER_SIZES["ARCH D (24x36)"],
            margin_mm=25.4,
            scale_denominator=600,
            metres_per_unit=paper.METRES_PER_UNIT["ft"],
        )
        self.assertAlmostEqual(width, 1700.0, places=6)
        self.assertAlmostEqual(height, 1100.0, places=6)

    def test_portrait_swaps(self):
        landscape = paper.sheet_size(
            paper.PAPER_SIZES["ARCH D (24x36)"], 25.4, 600,
            paper.METRES_PER_UNIT["ft"], landscape=True)
        portrait = paper.sheet_size(
            paper.PAPER_SIZES["ARCH D (24x36)"], 25.4, 600,
            paper.METRES_PER_UNIT["ft"], landscape=False)
        self.assertAlmostEqual(landscape[0], portrait[1])
        self.assertAlmostEqual(landscape[1], portrait[0])

    def test_metric(self):
        # A1 landscape, 10 mm margins, 1:1000 -> 821 x 574 m
        width, height = paper.sheet_size(
            paper.PAPER_SIZES["A1 (594x841)"], 10.0, 1000.0,
            paper.METRES_PER_UNIT["m"])
        self.assertAlmostEqual(width, 821.0, places=6)
        self.assertAlmostEqual(height, 574.0, places=6)

    def test_survey_feet_differ_slightly_from_international(self):
        args = (paper.PAPER_SIZES["ARCH D (24x36)"], 25.4, 600)
        intl = paper.sheet_size(*args, metres_per_unit=paper.METRES_PER_UNIT["ft"])
        us = paper.sheet_size(*args, metres_per_unit=paper.METRES_PER_UNIT["ftUS"])
        self.assertNotEqual(intl[0], us[0])
        self.assertLess(abs(intl[0] - us[0]), 0.01)  # negligible at sheet scale

    def test_margins_too_big(self):
        with self.assertRaises(ValueError):
            paper.sheet_size(paper.PAPER_SIZES["A4 (210x297)"], 200.0, 1000, 1.0)


class FormatScaleTest(unittest.TestCase):
    def test_imperial(self):
        self.assertEqual(paper.format_scale(600, imperial=True), '1" = 50\'')

    def test_metric(self):
        self.assertEqual(paper.format_scale(2000), "1:2000")


if __name__ == "__main__":
    unittest.main()
