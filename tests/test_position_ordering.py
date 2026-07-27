"""Ordering sheets by where they sit, after a human has moved them around."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fieldkit.core import gridmath as g  # noqa: E402


def tidy_grid(cols=3, rows=2, width=100.0, height=80.0):
    """A clean grid, keyed 'r{row}c{col}' with row 0 at the bottom."""
    items = {}
    for row in range(rows):
        for col in range(cols):
            items["r%dc%d" % (row, col)] = (
                col * width + width / 2.0,
                row * height + height / 2.0,
                width,
                height,
            )
    return items


class BandRowsTest(unittest.TestCase):
    def test_clean_grid_bands_into_rows(self):
        bands = g.band_rows(tidy_grid())
        self.assertEqual(bands, [
            ["r1c0", "r1c1", "r1c2"],
            ["r0c0", "r0c1", "r0c2"],
        ])

    def test_a_nudged_sheet_stays_in_its_row(self):
        items = tidy_grid()
        cx, cy, w, h = items["r1c1"]
        items["r1c1"] = (cx + 12.0, cy + 20.0, w, h)  # a quarter sheet up and over
        bands = g.band_rows(items)
        self.assertEqual(len(bands), 2)
        self.assertIn("r1c1", bands[0])

    def test_a_sheet_dropped_a_full_row_starts_a_new_band(self):
        items = tidy_grid(cols=2, rows=2)
        cx, cy, w, h = items["r1c1"]
        items["r1c1"] = (cx, cy - 200.0, w, h)
        bands = g.band_rows(items)
        self.assertEqual(len(bands), 3)

    def test_moving_a_sheet_sideways_reorders_within_the_row(self):
        items = tidy_grid()
        cx, cy, w, h = items["r1c0"]
        items["r1c0"] = (cx + 250.0, cy, w, h)  # dragged past the others
        self.assertEqual(g.band_rows(items)[0], ["r1c1", "r1c2", "r1c0"])

    def test_columns(self):
        bands = g.band_rows(tidy_grid(cols=2, rows=2), axis="x")
        self.assertEqual(bands, [["r1c0", "r0c0"], ["r1c1", "r0c1"]])

    def test_single_sheet(self):
        self.assertEqual(g.band_rows({"only": (0.0, 0.0, 10.0, 10.0)}), [["only"]])

    def test_empty(self):
        self.assertEqual(g.band_rows({}), [])

    def test_bad_ratio(self):
        with self.assertRaises(ValueError):
            g.band_rows(tidy_grid(), band_ratio=0)

    def test_bad_axis(self):
        with self.assertRaises(ValueError):
            g.band_rows(tidy_grid(), axis="diagonal")


class OrderByPositionTest(unittest.TestCase):
    def test_row_major_top_down(self):
        ordered, bands = g.order_by_position(tidy_grid(), g.ORDER_ROW_NS)
        self.assertEqual(ordered,
                         ["r1c0", "r1c1", "r1c2", "r0c0", "r0c1", "r0c2"])
        self.assertEqual(len(bands), 2)

    def test_row_major_bottom_up(self):
        ordered, _ = g.order_by_position(tidy_grid(), g.ORDER_ROW_SN)
        self.assertEqual(ordered[0], "r0c0")

    def test_serpentine_alternates(self):
        ordered, _ = g.order_by_position(tidy_grid(), g.ORDER_SERPENTINE)
        self.assertEqual(ordered,
                         ["r1c0", "r1c1", "r1c2", "r0c2", "r0c1", "r0c0"])

    def test_column_major(self):
        ordered, _ = g.order_by_position(tidy_grid(cols=2, rows=2), g.ORDER_COL)
        self.assertEqual(ordered, ["r1c0", "r0c0", "r1c1", "r0c1"])

    def test_every_mode_keeps_every_sheet(self):
        items = tidy_grid()
        for mode in (g.ORDER_ROW_NS, g.ORDER_ROW_SN, g.ORDER_COL,
                     g.ORDER_SERPENTINE):
            ordered, _ = g.order_by_position(items, mode)
            self.assertEqual(sorted(ordered), sorted(items))

    def test_extra_sheet_added_off_to_one_side(self):
        # The "add a sheet where I need one" case: it must not be dropped.
        items = tidy_grid()
        items["extra"] = (500.0, 40.0, 100.0, 80.0)
        ordered, _ = g.order_by_position(items, g.ORDER_ROW_NS)
        self.assertIn("extra", ordered)
        self.assertEqual(ordered[-1], "extra")  # bottom row, furthest right

    def test_unknown_mode(self):
        with self.assertRaises(ValueError):
            g.order_by_position(tidy_grid(), "spiral")


class NeighboursTest(unittest.TestCase):
    def test_clean_grid(self):
        neighbours = g.neighbours_by_position(tidy_grid())
        middle = neighbours["r0c1"]
        self.assertEqual(middle["w"], "r0c0")
        self.assertEqual(middle["e"], "r0c2")
        self.assertEqual(middle["n"], "r1c1")
        self.assertIsNone(middle["s"])

    def test_corners_have_no_neighbour_outward(self):
        neighbours = g.neighbours_by_position(tidy_grid())
        corner = neighbours["r1c0"]
        self.assertIsNone(corner["w"])
        self.assertIsNone(corner["n"])
        self.assertEqual(corner["e"], "r1c1")
        self.assertEqual(corner["s"], "r0c0")

    def test_north_picks_the_sheet_it_actually_overlaps(self):
        # Top row shifted half a sheet right: r0c1 overlaps r1c1 more than r1c2
        items = tidy_grid()
        for col in range(3):
            cx, cy, w, h = items["r1c%d" % col]
            items["r1c%d" % col] = (cx + 40.0, cy, w, h)
        self.assertEqual(g.neighbours_by_position(items)["r0c1"]["n"], "r1c1")

    def test_lone_sheet_has_none(self):
        neighbours = g.neighbours_by_position({"only": (0.0, 0.0, 10.0, 10.0)})
        self.assertEqual(
            neighbours["only"], {"n": None, "s": None, "e": None, "w": None})


if __name__ == "__main__":
    unittest.main()
