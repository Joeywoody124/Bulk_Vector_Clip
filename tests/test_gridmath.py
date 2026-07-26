import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fieldkit.core import gridmath as g  # noqa: E402


class CountAlongTest(unittest.TestCase):
    def test_exact_fit(self):
        self.assertEqual(g.count_along(300, 100, 0), (3, 100))

    def test_partial_needs_another(self):
        self.assertEqual(g.count_along(301, 100, 0)[0], 4)

    def test_smaller_than_one_cell(self):
        self.assertEqual(g.count_along(40, 100, 0), (1, 100))

    def test_overlap_costs_cells(self):
        # 10% overlap: each cell only advances 90
        count, step = g.count_along(300, 100, 10)
        self.assertEqual(step, 90)
        self.assertEqual(count, 4)  # covers 3*90 + 100 = 370

    def test_cells_actually_cover_the_span(self):
        for span in (1, 99, 100, 101, 250, 999.5):
            for overlap in (0, 5, 25):
                count, step = g.count_along(span, 100, overlap)
                covered = (count - 1) * step + 100
                self.assertGreaterEqual(covered + 1e-9, span)
                if count > 1:
                    self.assertLess((count - 2) * step + 100, span)

    def test_overlap_must_be_less_than_cell(self):
        with self.assertRaises(ValueError):
            g.count_along(300, 100, 100)


class GridOriginTest(unittest.TestCase):
    bbox = (1000.0, 2000.0, 1300.0, 2200.0)

    def test_lower_left(self):
        grid = g.grid_origin(self.bbox, 100, 100, anchor=g.ANCHOR_LOWER_LEFT)
        self.assertEqual((grid["x0"], grid["y0"]), (1000.0, 2000.0))
        self.assertEqual((grid["ncols"], grid["nrows"]), (3, 2))

    def test_centre_balances_the_overhang(self):
        # 300 wide, 200 tall. Columns fit exactly; rows need 2 cells for 200,
        # so there is no overhang either. Use a span that does overhang:
        grid = g.grid_origin((0.0, 0.0, 110.0, 100.0), 100, 100,
                             anchor=g.ANCHOR_CENTER)
        self.assertEqual(grid["ncols"], 2)
        # two 100-wide cells cover 200 for a 110 span -> 45 spare each side
        self.assertAlmostEqual(grid["x0"], -45.0)

    def test_centre_never_leaves_coverage_uncovered(self):
        grid = g.grid_origin((0.0, 0.0, 110.0, 100.0), 100, 100,
                             anchor=g.ANCHOR_CENTER)
        right = grid["x0"] + (grid["ncols"] - 1) * grid["step_x"] + 100
        self.assertLessEqual(grid["x0"], 0.0 + 1e-9)
        self.assertGreaterEqual(right + 1e-9, 110.0)

    def test_snap_lands_on_round_numbers(self):
        grid = g.grid_origin((1037.0, 2094.0, 1300.0, 2200.0), 100, 100,
                             anchor=g.ANCHOR_SNAP, snap_to=50)
        self.assertEqual((grid["x0"], grid["y0"]), (1000.0, 2050.0))

    def test_snap_is_stable_under_small_boundary_changes(self):
        # The whole point of snapping: nudging the boundary must not shift
        # every sheet and invalidate a printed set.
        a = g.grid_origin((1037.0, 2094.0, 1300.0, 2200.0), 100, 100,
                          anchor=g.ANCHOR_SNAP, snap_to=50)
        b = g.grid_origin((1041.0, 2097.0, 1300.0, 2200.0), 100, 100,
                          anchor=g.ANCHOR_SNAP, snap_to=50)
        self.assertEqual((a["x0"], a["y0"]), (b["x0"], b["y0"]))

    def test_explicit_origin(self):
        grid = g.grid_origin(self.bbox, 100, 100, anchor=g.ANCHOR_ORIGIN,
                             origin=(900.0, 1900.0))
        self.assertEqual((grid["x0"], grid["y0"]), (900.0, 1900.0))
        self.assertEqual(grid["ncols"], 4)

    def test_snap_needs_an_interval(self):
        with self.assertRaises(ValueError):
            g.grid_origin(self.bbox, 100, 100, anchor=g.ANCHOR_SNAP, snap_to=0)


class CellBoundsTest(unittest.TestCase):
    def test_bounds(self):
        grid = g.grid_origin((0.0, 0.0, 300.0, 200.0), 100, 100,
                             anchor=g.ANCHOR_LOWER_LEFT)
        self.assertEqual(g.cell_bounds(grid, 100, 100, 0, 0), (0, 0, 100, 100))
        self.assertEqual(g.cell_bounds(grid, 100, 100, 1, 2), (200, 100, 300, 200))

    def test_overlapping_cells_share_ground(self):
        grid = g.grid_origin((0.0, 0.0, 300.0, 100.0), 100, 100, overlap_x=10,
                             anchor=g.ANCHOR_LOWER_LEFT)
        first = g.cell_bounds(grid, 100, 100, 0, 0)
        second = g.cell_bounds(grid, 100, 100, 0, 1)
        self.assertAlmostEqual(first[2] - second[0], 10.0)


class OrderTest(unittest.TestCase):
    cells = [(r, c) for r in range(3) for c in range(2)]

    def test_row_major_reads_top_down(self):
        self.assertEqual(
            g.order_cells(self.cells, g.ORDER_ROW_NS),
            [(2, 0), (2, 1), (1, 0), (1, 1), (0, 0), (0, 1)],
        )

    def test_row_major_south_north(self):
        self.assertEqual(g.order_cells(self.cells, g.ORDER_ROW_SN)[0], (0, 0))

    def test_column_major(self):
        self.assertEqual(
            g.order_cells(self.cells, g.ORDER_COL),
            [(2, 0), (1, 0), (0, 0), (2, 1), (1, 1), (0, 1)],
        )

    def test_serpentine_alternates(self):
        self.assertEqual(
            g.order_cells(self.cells, g.ORDER_SERPENTINE),
            [(2, 0), (2, 1), (1, 1), (1, 0), (0, 0), (0, 1)],
        )

    def test_every_mode_keeps_every_cell(self):
        for mode in (g.ORDER_ROW_NS, g.ORDER_ROW_SN, g.ORDER_COL,
                     g.ORDER_SERPENTINE):
            self.assertEqual(sorted(g.order_cells(self.cells, mode)),
                             sorted(self.cells))

    def test_unknown_mode(self):
        with self.assertRaises(ValueError):
            g.order_cells(self.cells, "sideways")


class LabelTest(unittest.TestCase):
    def test_alpha(self):
        self.assertEqual(g.alpha_label(0), "A")
        self.assertEqual(g.alpha_label(25), "Z")
        self.assertEqual(g.alpha_label(26), "AA")
        self.assertEqual(g.alpha_label(27), "AB")
        self.assertEqual(g.alpha_label(51), "AZ")
        self.assertEqual(g.alpha_label(52), "BA")

    def test_sheet_id(self):
        self.assertEqual(g.format_sheet_id("C-{n:02d}", 7, 0, 0), "C-07")
        self.assertEqual(g.format_sheet_id("{n}", 12, 0, 0), "12")

    def test_grid_ref_letters_rows_from_the_top(self):
        # 3 rows: the top row (row index 2) should be "A"
        self.assertEqual(
            g.format_sheet_id("{alpha_row}{col1}", 1, 2, 0, nrows=3), "A1")
        self.assertEqual(
            g.format_sheet_id("{alpha_row}{col1}", 1, 0, 2, nrows=3), "C3")

    def test_bad_template_is_reported_clearly(self):
        with self.assertRaises(ValueError):
            g.format_sheet_id("{sheet}", 1, 0, 0)


class RotateTest(unittest.TestCase):
    def test_quarter_turn_clockwise(self):
        x, y = g.rotate_point(1.0, 0.0, 0.0, 0.0, 90.0)
        self.assertAlmostEqual(x, 0.0)
        self.assertAlmostEqual(y, -1.0)

    def test_round_trip_is_lossless(self):
        for theta in (0.0, 17.5, 90.0, -33.3, 180.0):
            x, y = g.rotate_point(123.4, -567.8, 10.0, 20.0, theta)
            x2, y2 = g.rotate_point(x, y, 10.0, 20.0, -theta)
            self.assertAlmostEqual(x2, 123.4, places=9)
            self.assertAlmostEqual(y2, -567.8, places=9)


if __name__ == "__main__":
    unittest.main()
