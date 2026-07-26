# Spec — Atlas Grid Builder

**Status:** built as `fieldkit:atlasgridbuilder`, and covered by the QGIS smoke
tests since v0.2.0. Differences between this spec and the code are called out
inline.

Turn a coverage polygon into a sheet grid that's ready to drive an atlas:
sized from the paper, snapped, optionally rotated, culled to real coverage,
and numbered the way a plan set reads.

---

## The problem with the native path

`native:creategrid` takes an extent, an H/V spacing, and an H/V overlap, in map
units. To use it for atlas sheets today you:

1. Work out that a 24×36 sheet at 1"=60' with 1" margins is 2040 × 1320 ft —
   by hand, on the back of an envelope.
2. Get the extent of your coverage layer, and accept that the grid starts at
   the extent's lower-left corner wherever that happens to fall.
3. Generate it. Get 60 cells over a diagonal site where 22 have any coverage.
4. Select by location against the coverage, invert, delete — and notice
   afterwards that a few surviving cells clip 40 ft² of a corner and will
   print as a nearly blank sheet.
5. Add a `sheet_no` field and populate it with something involving `$id`,
   which numbers cells in creation order, which is column-major and not how
   anyone reads a plan set.
6. Discover the site runs northeast, so half of every sheet is empty, and
   there's no rotation option.

Steps 1–6 are the tool.

---

## Parameters

Grouped as they'd appear in the dialog. Everything below the first group is
collapsed under "Advanced" with working defaults.

### Coverage

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `COVERAGE` | polygon layer | — | Selected features only, if any |
| `BUFFER` | distance | 0 | Pad the coverage before gridding — so sheets extend past the property line |

### Sheet size — two ways in

**A. From paper (default).** This is the mode that doesn't exist natively.

| Parameter | Type | Default |
|---|---|---|
| `PAPER` | enum from `PAPER_SIZES` in `core/paper.py` | ARCH D (24x36) |
| `ORIENTATION` | landscape / portrait | landscape |
| `MARGIN` | mm or in | 1 in |
| `SCALE` | scale denominator or `1"=60'` string | 1"=60' |

Cell size in map units = `(paper_dimension − 2 × margin) × scale_denominator`,
with the paper dimension converted into the layer's units first. For a CRS in
feet: 24 in − 2 in = 22 in printable; at 1"=60', that's 1320 ft.

**B. Direct.** `CELL_WIDTH` / `CELL_HEIGHT` in map units, for when you already
know.

Either way, the resulting cell size is echoed in the log — the estimator and
this tool must never disagree.

### Overlap

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `OVERLAP` | percent or map units | 5% | Sheets share edge coverage so match lines have context |

`native:creategrid` expresses this as `HOVERLAY`/`VOVERLAY` in map units, which
is fine but means recomputing it every time the scale changes. Percent-of-sheet
is the unit people actually think in.

### Origin

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `ANCHOR` | enum | Center on coverage | `Coverage lower-left` / `Center on coverage` / `Snap to round coordinate` / `Specify XY` |
| `SNAP_TO` | distance | 100 | For the snap mode — grid lines land on multiples of this |
| `ORIGIN_X`, `ORIGIN_Y` | number | — | For the explicit mode |

Centering matters more than it sounds: with a lower-left origin, a site that's
1.1 cells wide produces two columns with the second nearly empty. Centering
produces one, or two balanced ones.

Snap-to-round exists so that regenerating the grid next month after the
boundary changes slightly produces *the same sheets*, rather than shifting
every sheet by 30 ft and invalidating the whole printed set.

### Rotation

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `ROTATION` | enum | None | `None` / `Auto (fit coverage)` / `Specify angle` |
| `ANGLE` | degrees | 0 | Clockwise, for the explicit mode |

**Auto** uses `QgsGeometry.orientedMinimumBoundingBox()` on the (dissolved)
coverage, which returns the angle of the minimum-area rotated rectangle. For a
diagonal corridor or a site fronting a skewed road this typically cuts sheet
count meaningfully.

Implementation: rotate the coverage by `θ` about the centroid to square it to
the axes, grid in that frame with plain rectangle math, then rotate each cell
back by `−θ`. `QgsGeometry.rotate(angle, center)` handles both directions. All
the messy parts stay in the axis-aligned frame.

**As built:** `orientedMinimumBoundingBox()`'s sign convention isn't worth
guessing at, so the code tries `+θ` and `−θ` and keeps whichever squares the
coverage up more tightly. Self-correcting, and cheap.

Rotated sheets need the layout map item rotated to match — `θ` is written to
`map_rotation` for a data-defined override. The north arrow then needs a
data-defined rotation of `−map_rotation` or it will lie. **Check the first
rotated set by eye** — this is the one place a sign error would be invisible
until it's printed.

### Culling

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `CULL` | bool | true | Drop cells that don't intersect the coverage |
| `MIN_COVERAGE` | percent of cell | 0.5% | Drop slivers — a cell catching a corner of the boundary isn't a sheet |

`MIN_COVERAGE` is the parameter that saves the most rework. It's also the one
to expose prominently, because the right value is judgment: 0.5% suppresses
accidental corners, 5% starts dropping legitimate edge sheets.

### Numbering

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `ORDER` | enum | Row-major, N→S | `Row-major N→S` / `Row-major S→N` / `Column-major` / `Serpentine`. *Along a line not built — see below* |
| `START_AT` | int | 1 | |
| `TEMPLATE` | string | `C-{n:02d}` | Tokens: `{n}`, `{row}`, `{col}`, `{alpha_row}`, `{alpha_col}` |

**Along a line** would take a centerline and order sheets by their projection
onto it — the right order for a corridor, where row-major is nonsense. Not
built: a corridor wants rotated-per-station sheets too, so it belongs with
Corridor Strip Maps rather than bolted onto this tool.

**Serpentine** (left-to-right, then right-to-left) minimizes the pan between
consecutive sheets when reviewing on screen.

### Output

| Parameter | Type | Default |
|---|---|---|
| `OUTPUT` | polygon layer | memory layer, added to project |
| ~~`MAKE_INDEX`~~ | — | Not built. The `grid_ref` attribute already makes a key map a labelling job |
| ~~`ESTIMATE_ONLY`~~ | — | Dropped: the summary always prints to the log, and the multi-scale question belongs to the estimator |

---

## Output schema

| Field | Type | Notes |
|---|---|---|
| `sheet_no` | int | Sequential in the chosen order |
| `sheet_id` | string | Formatted by `TEMPLATE` — use as the atlas page name |
| `row`, `col` | int | Grid position in the rotated frame |
| `grid_ref` | string | `A1`, `B2` — for a key map |
| `center_x`, `center_y` | double | In layer CRS |
| `map_rotation` | double | Degrees clockwise; 0 unless rotated |
| `scale` | double | Denominator, so the layout can label itself. Null in direct-cell-size mode |
| `cov_pct` | double | Percent of the cell covered — makes thin sheets easy to spot |
| `nbr_n/s/e/w` | string | Neighbor `sheet_id` or null, for match-line labels |

`sheet_id`, `map_rotation`, and `scale` as attributes are what let one layout serve
every project: the map item binds scale and rotation to the feature, and the
title block reads `sheet_id`, with no per-project editing.

---

## The summary

Printed to the log on every run, rather than hidden behind a flag:

```
Sheet covers 2040.00 x 1320.00 map units.
Grid 4 x 3 = 12 cells; kept 9 (3 empty, 0 below the coverage threshold).
9 sheet(s) written.
```

The Sheet Count Estimator is this same path in a loop over a scale ladder,
sharing `algs/_grid.py` so the two can't drift apart.

---

## Core math to isolate and test

In `fieldkit/core/`, no QGIS imports, 40 unit tests:

- `paper.parse_scale()` — `1:2000`, `1"=50'`, `1 in = 100 ft`, bare denominators
- `paper.sheet_size()` — with an explicit metres-per-unit, so ft, ftUS and
  metres are all just a number. The ft/ftUS difference is 2 ppm: real, and
  worth about 0.002 ft on a 1100 ft sheet, so it matters for *coordinates* and
  not for sheet sizes. An earlier draft of this spec overstated it.
- `gridmath.count_along()` — with a property test that the cells really do
  cover the span, and that dropping one would not
- `gridmath.grid_origin()` — including that snapping is stable when the
  boundary moves slightly, which is the whole reason the mode exists
- `gridmath.cell_bounds()`, `order_cells()` — including that every mode is a
  permutation, losing no cells
- `gridmath.alpha_label()` — overflow past Z (`AA`, `AB`)
- `gridmath.rotate_point()` — round trip is lossless

Everything touching a `QgsFeature`, a layer, or a CRS stays in the algorithm
file and is verified by hand in QGIS.

---

## Acceptance test (do this on a real site before calling it done)

`tests/smoke_qgis.py` now covers steps 1-3 automatically against real QGIS: it
checks the sheet comes out 2040 x 1320 ft at ARCH D / 1"=60' in EPSG:3361, that
numbering is contiguous, that neighbour links are reciprocal, that the top row
has nothing to its north, that every surviving sheet touches the site, and that
a snapped origin lands on a round coordinate.

Steps 4-6 still need a human, because they are about what the printed set looks
like:

1. Load a real project boundary in EPSG:2273.
2. Run the Sheet count estimator across `1"=20'` through `1"=200'`. Numbers
   should be sane and match a hand check on at least one scale.
3. Generate at 1"=50', ARCH D, 5% overlap, centered, culled.
4. Wire it to a layout atlas — page name `sheet_id`, sorted by `sheet_no`,
   fixed scale from `scale`.
5. Export the set. Confirm: no blank sheets, adjacent sheets visibly overlap,
   sheet numbers read in a sensible order, match-line callouts name real
   neighbors.
6. Re-run with `Auto` rotation on a diagonal site and confirm the sheet count
   drops.

If step 3 to step 5 takes longer than about two minutes, the tool hasn't
actually solved the problem.
