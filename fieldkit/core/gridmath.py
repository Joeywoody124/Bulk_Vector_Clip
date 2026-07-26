"""Grid origin, cell layout, ordering and sheet-label maths.

Pure Python - see the package docstring for why. Everything here works on
plain tuples and numbers so it can be tested without QGIS.

Convention: row 0 is the *bottom* row, column 0 is the *left* column, matching
the way coordinates increase. Ordering functions are what turn that into the
order a plan set actually reads.
"""

import math

ANCHOR_CENTER = "center"
ANCHOR_LOWER_LEFT = "lower_left"
ANCHOR_SNAP = "snap"
ANCHOR_ORIGIN = "origin"

ORDER_ROW_NS = "row_ns"
ORDER_ROW_SN = "row_sn"
ORDER_COL = "col"
ORDER_SERPENTINE = "serpentine"


def count_along(span, cell, overlap):
    """How many cells of size ``cell`` overlapping by ``overlap`` cover ``span``.

    Returns ``(count, step)`` where ``step`` is the distance between the
    left edges of consecutive cells.
    """
    step = cell - overlap
    if cell <= 0:
        raise ValueError("Cell size must be positive")
    if step <= 0:
        raise ValueError(
            "Overlap (%s) must be smaller than the cell size (%s)" % (overlap, cell)
        )
    if span <= cell:
        return 1, step
    return int(math.ceil((span - cell) / step)) + 1, step


def grid_origin(bbox, cell_w, cell_h, overlap_x=0.0, overlap_y=0.0,
                anchor=ANCHOR_CENTER, snap_to=0.0, origin=None):
    """Work out where the grid starts and how many cells it needs.

    ``bbox`` is ``(xmin, ymin, xmax, ymax)``. Returns a dict with ``x0``,
    ``y0``, ``ncols``, ``nrows``, ``step_x`` and ``step_y``.
    """
    xmin, ymin, xmax, ymax = bbox
    if xmax < xmin or ymax < ymin:
        raise ValueError("Empty bounding box")

    if anchor == ANCHOR_ORIGIN:
        if origin is None:
            raise ValueError("anchor='origin' needs an origin")
        x0, y0 = float(origin[0]), float(origin[1])
    elif anchor == ANCHOR_SNAP:
        if snap_to <= 0:
            raise ValueError("anchor='snap' needs a positive snap interval")
        x0 = math.floor(xmin / snap_to) * snap_to
        y0 = math.floor(ymin / snap_to) * snap_to
    else:
        x0, y0 = xmin, ymin

    ncols, step_x = count_along(xmax - x0, cell_w, overlap_x)
    nrows, step_y = count_along(ymax - y0, cell_h, overlap_y)

    if anchor == ANCHOR_CENTER:
        # Re-centre the block of cells over the coverage so a site that is
        # 1.1 cells wide does not produce one full column and one near-empty
        # one hanging off the right-hand side.
        total_w = (ncols - 1) * step_x + cell_w
        total_h = (nrows - 1) * step_y + cell_h
        x0 = xmin - (total_w - (xmax - xmin)) / 2.0
        y0 = ymin - (total_h - (ymax - ymin)) / 2.0

    return {
        "x0": x0,
        "y0": y0,
        "ncols": ncols,
        "nrows": nrows,
        "step_x": step_x,
        "step_y": step_y,
    }


def cell_bounds(grid, cell_w, cell_h, row, col):
    """Bounds of one cell as ``(xmin, ymin, xmax, ymax)``."""
    xmin = grid["x0"] + col * grid["step_x"]
    ymin = grid["y0"] + row * grid["step_y"]
    return (xmin, ymin, xmin + cell_w, ymin + cell_h)


def order_cells(cells, mode=ORDER_ROW_NS):
    """Sort ``(row, col)`` pairs into sheet order.

    ``row_ns`` reads the top row left to right, then the next row down -
    the way a plan set is normally numbered. ``serpentine`` alternates
    direction each row, which minimises the pan between consecutive sheets
    when reviewing on screen.
    """
    cells = list(cells)
    if mode == ORDER_ROW_NS:
        return sorted(cells, key=lambda rc: (-rc[0], rc[1]))
    if mode == ORDER_ROW_SN:
        return sorted(cells, key=lambda rc: (rc[0], rc[1]))
    if mode == ORDER_COL:
        return sorted(cells, key=lambda rc: (rc[1], -rc[0]))
    if mode == ORDER_SERPENTINE:
        rows = sorted({rc[0] for rc in cells}, reverse=True)
        out = []
        for index, row in enumerate(rows):
            in_row = sorted((rc for rc in cells if rc[0] == row),
                            key=lambda rc: rc[1],
                            reverse=bool(index % 2))
            out.extend(in_row)
        return out
    raise ValueError("Unknown ordering mode %r" % mode)


def alpha_label(index):
    """0 -> A, 25 -> Z, 26 -> AA. Spreadsheet-style column labels."""
    if index < 0:
        raise ValueError("Index must not be negative")
    label = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def format_sheet_id(template, n, row, col, nrows=None, ncols=None):
    """Render a sheet id from a template such as ``C-{n:02d}`` or ``{alpha_row}{col1}``.

    Available fields: ``n``, ``row``, ``col`` (0-based, from the bottom left),
    ``row1``, ``col1`` (1-based), ``alpha_row``, ``alpha_col``.

    Rows are lettered from the top down, because that is how a key map reads.
    """
    row_from_top = (nrows - 1 - row) if nrows else row
    fields = {
        "n": n,
        "row": row,
        "col": col,
        "row1": row + 1,
        "col1": col + 1,
        "alpha_row": alpha_label(row_from_top),
        "alpha_col": alpha_label(col),
    }
    try:
        return template.format(**fields)
    except (KeyError, IndexError) as exc:
        raise ValueError(
            "Unknown field %s in template %r. Available: %s"
            % (exc, template, ", ".join(sorted(fields)))
        )
    except ValueError as exc:
        raise ValueError("Bad template %r: %s" % (template, exc))


def rotate_point(x, y, cx, cy, degrees_clockwise):
    """Rotate a point clockwise about a centre, matching QgsGeometry.rotate()."""
    theta = math.radians(-degrees_clockwise)
    dx, dy = x - cx, y - cy
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return (cx + dx * cos_t - dy * sin_t, cy + dx * sin_t + dy * cos_t)
