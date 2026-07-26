# Roadmap & Architecture

Phase 1 is built and installable (v0.1.0). Everything from Phase 2 on is still
a plan. See [`IDEAS.md`](IDEAS.md) for the wider backlog.

---

## 1. Delivery format

**Decision: a Processing provider plugin, one file per algorithm.**

Each tool is a `QgsProcessingAlgorithm` subclass in its own file under
`fieldkit/algs/`. That single choice buys:

- It appears in the **Processing Toolbox**, so it works in the Batch dialog,
  inside graphical **Models**, and from `processing.run()` in the Python
  console — for free, no extra UI code.
- Customizing means opening one readable file. No build step, no compile.
- A thin plugin wrapper (`__init__.py`, `plugin.py`, `provider.py`,
  `metadata.txt`) registers the lot as a "Field Kit" group in the toolbox.

**Revised during Phase 1:** the original plan also promised that any single
`.py` could be dropped into `processing/scripts/` and used without installing
the plugin. That holds for the self-contained editing tools, but the sheet
tools share `core/gridmath.py` and `algs/_grid.py` between them, and QGIS's
script loader has no way to resolve those imports. Duplicating the maths into
each file to preserve the claim would cost more than the claim is worth, so the
plugin install is the supported path. `docs/INSTALL.md` describes a symlink
setup that keeps editing-and-reloading just as quick.

### Testability constraint

QGIS can't run in CI. So: **all math lives in pure-Python modules that import
nothing from `qgis`.** Grid origins, rotation, sheet numbering, paper→map-unit
conversion — all pure functions over plain tuples, unit-tested with stdlib
`unittest` in GitHub Actions. The algorithm file is a thin adapter that reads
QGIS parameters, calls the pure function, and writes features.

This is not a purity exercise; it's the only way to have regression tests at
all, and grid math is exactly the kind of code that breaks silently.

### Layout, as built

```
README.md
LICENSE
docs/
  INSTALL.md
  ROADMAP.md
  IDEAS.md
  sheet-workflow.md          # generate -> move by hand -> renumber
  specs/atlas-grid-builder.md
  tips/                      # the "hacks and tips" half of the suite
fieldkit/                    # the plugin package (zip this to install)
  __init__.py                # classFactory
  plugin.py                  # registers/unregisters the provider
  provider.py
  metadata.txt
  algs/
    row_from_centerline.py
    fill_gaps.py
    snap_and_verify.py
    close_undershoots.py
    atlas_grid_builder.py
    sheet_estimator.py
    renumber_sheets.py
    bulk_vector_clip.py
    _grid.py                 # shared QGIS-side helpers for the sheet tools
  core/                      # pure python, no qgis imports — the tested part
    gridmath.py
    paper.py
tests/                       # runs without QGIS
```

Two things from the original sketch aren't there yet. `expressions/` waits for
the expression pack (idea 19). `presets/*.json` turned out to be premature —
paper sizes and the unit table live in `core/paper.py`, which is a one-line
edit and needs no loader; JSON presets only earn their place once there is
something worth sharing between machines.

### Naming

The repo is currently `Bulk_Vector_Clip`, which names one tool rather than the
suite. Suggest keeping the repo name (links and clones already exist) but
naming the *plugin* something suite-shaped — "QGIS Field Kit" is the working
title used here. Easy to change before first release, painful after.

---

## 2. Phasing

### Phase 1 — done (v0.1.0)

- [x] Plugin scaffolding, provider, CI running the pure-python tests
- [x] **Atlas Grid Builder** — [spec](specs/atlas-grid-builder.md)
- [x] **Sheet Count Estimator**
- [x] **Bulk Vector Clip** — the repo's namesake
- [x] **Right of way from centerline**, **Fill gaps**, **Snap and verify**,
      **Close dangling line ends** — the editing group, added to Phase 1 once
      it became clear that day-to-day editing, not sheet layout, is where the
      time actually goes
- [x] **Renumber sheets** — closes the loop: generate, move sheets by hand
      with QGIS's own tools, then rebuild the numbering from where they sit
- [x] `docs/tips/digitising-without-gaps.md`, `docs/tips/crs-notes.md`,
      `docs/sheet-workflow.md`

The architecture held: the `core/` vs `algs/` split paid for itself on the two
sheet tools, which share all their maths and disagree about nothing.

**Not yet verified in QGIS.** Every tool compiles and the pure maths is tested,
but nothing here has been run against a real layer. The acceptance test at the
end of the atlas spec is the first thing to do.

### Phase 2 — after real use

Order deliberately not fixed. Run v0.1 on a live job first; what's annoying in
practice should decide this, not what looked good on paper. The candidates, with
notes on what QGIS already does, are in [`IDEAS.md`](IDEAS.md).

The four that look strongest today: **Erase overlaps** (the mirror of Fill
Gaps), **Polygonize with diagnostics**, **Fillet corners**, and **Corridor
strip maps**.

---

## 3. Tool specifications

The three below are built. Everything uses the PyQGIS API in QGIS 3.34+ and no
third-party dependencies.

### 3.1 Atlas Grid Builder ★ flagship

Full spec: [`specs/atlas-grid-builder.md`](specs/atlas-grid-builder.md).

Summary: coverage polygon + paper size + scale → a sheet grid that is sized
from the paper (not guessed in map units), snapped to a sane origin, optionally
rotated to the site's principal axis, culled to cells that actually contain
coverage, and numbered in the order a plan set reads.

What `native:creategrid` gives you today: spacing X/Y, extent, and overlap in
map units. What it does not: paper-driven sizing, rotation, culling to a
coverage polygon, sliver suppression, sheet numbering, serpentine order, or
neighbor attributes. That gap is the tool.

The spec's `ESTIMATE_ONLY` flag was dropped as built: the grid summary always
prints to the log, and the multi-scale question is the estimator's whole job,
so the flag would have been a parameter earning nothing.

### 3.2 Sheet Count Estimator

**Input:** coverage layer, paper size, margins, a scale ladder (defaults to
`1"=20'` through `1"=200'`, or write `1:500/1:1000/1:2000`), overlap %.

**Output:** an HTML table in the Processing results panel —

| Scale | Sheet size (map units) | Sheets | Coverage/sheet |
|---|---|---|---|
| 1"=20' | 460 × 700 ft | 84 | 12% |
| 1"=50' | 1150 × 1750 ft | 15 | 34% |
| 1"=100' | 2300 × 3500 ft | 6 | 51% |

Plus a "smallest scale that fits in N sheets" answer.

**Feasibility:** trivial once the grid core exists — it runs the same culling
math per candidate scale and counts, without materializing an output layer. A
real cull count, not `area ÷ cell_area`, because the naive number is wrong by
30–60% on any non-rectangular site.

**Why not native:** there is no native equivalent. Today this is "generate a
grid, look at the feature count, delete it, change the spacing, repeat."

### 3.3 Bulk Vector Clip

**Input:** boundary polygon (or a selected feature), a checklist of layers
(default: everything visible), output GeoPackage path.

**Behavior:**
- Clips each layer, reprojecting the boundary per-layer so mixed-CRS projects
  just work.
- Preserves the layer's style — writes it into the GeoPackage's `layer_styles`
  table via `saveStyleToDatabase()`, so reopening the GPKG comes up styled.
- Skips layers that clip to nothing (with a note in the log) instead of
  writing dozens of empty layers.
- Optional: buffer the boundary by N units first (the "give me a little
  context around the site" case).

Two things from the spec are **not** built: adding the results back into the
project in a group, and handling raster layers via
`gdal:cliprasterbymasklayer`. Rasters are the bigger gap — the tool warns and
skips them rather than pretending. Both are easy to add once it's clear they're
wanted.

**As built:** clips with `QgsGeometry.intersection()` per feature behind a
bounding-box request, rather than shelling out to `native:clip` per layer —
fewer moving parts, and it makes the skip-empty and per-layer reprojection
behaviour straightforward. The style preservation is what makes it better than
the Batch Processing dialog.

### 3.4 onwards

The remaining tool specs moved to [`IDEAS.md`](IDEAS.md), which frames each one
against what QGIS already does rather than as a commitment to build it. Keeping
two lists in sync was going to fail, and the backlog is the more honest home.

The four editing tools built in Phase 1 are specified in their own
`shortHelpString()` — visible in the toolbox as the tool's help panel, which is
where you actually want it while running them.

---

## 4. Documentation plan

The suite is half tooling, half knowledge. `docs/tips/` holds the parts that
are better as documentation than as code:

- **expressions.md** — the snippets worth keeping: conditional labeling,
  `array_agg` for summary tables, atlas-aware expressions
  (`@atlas_featurenumber`, `@atlas_pagename`), geometry generators for
  match-line hatching.
- **layouts.md** — layout tricks: overview maps with the atlas frame, dynamic
  scale bars, legend filtering by atlas feature, HTML items for tables.
- **styling.md** — rule-based renderers that scale-switch, symbol levels for
  clean road casings, saving `.qml` per project vs per layer.
- **processing-models.md** — when a Model beats a script, and how to make a
  Model take a layer choice instead of a hard-coded layer.
- **crs-notes.md** — State Plane, `ft` vs `ftUS`, and when on-the-fly
  reprojection quietly costs you accuracy.

Written so far:

- **digitising-without-gaps.md** — snapping configuration, topological editing,
  avoid-overlap, tracing, and the advanced digitising panel. It came first
  because it is the honest answer to most of "help me trace without gaps":
  three settings beat any cleanup tool.
- **crs-notes.md** — EPSG:3361 and its neighbours, why South Carolina's
  international foot means the `ftUS` trap doesn't apply here, and the sheet
  size table for the paper/scale combinations in daily use.

Each tool's own documentation lives in its `shortHelpString()`, which QGIS shows
in the tool's help panel. That is where it gets read, so that is where it goes;
`docs/specs/` is for design decisions that need arguing out before the code
exists.

---

## 5. Open questions

Answered so far by picking a default and moving on — say the word and any of
these changes in one line:

1. **QGIS floor: 3.34.** Lets the code use the modern `Qgis.*` enums without
   compatibility shims.
2. **Default paper: ARCH D (24x36) landscape, 1" margins.** Note ANSI D is
   22x34 and ARCH D is 24x36 — an earlier draft of these docs had them
   confused, which would have made every sheet 2" small.
3. **Default sheet template: `C-{n:02d}`.**

4. **Working CRS: EPSG:3361**, NAD83(HARN) / South Carolina in feet. Its unit
   is the *international* foot, so the estimator's ladder defaults to
   engineering scales and the `ft`/`ftUS` question never arises — see
   [`tips/crs-notes.md`](tips/crs-notes.md).

Still genuinely open:

5. **Distribution.** Clone-and-symlink for you, or a zip release so coworkers
   can install it? Only affects whether it's worth adding a release workflow.
