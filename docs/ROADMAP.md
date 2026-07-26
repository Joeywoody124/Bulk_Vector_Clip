# Roadmap & Architecture

Planning document. No code exists yet — this describes what to build and in
what order.

---

## 1. Delivery format

**Decision: a Processing provider plugin, where every algorithm is also a
standalone drop-in script.**

Each tool is a `QgsProcessingAlgorithm` subclass in its own file with no
imports from the rest of the package. That single choice buys everything:

- It appears in the **Processing Toolbox**, so it works in the Batch dialog,
  inside graphical **Models**, and from `processing.run()` in the Python
  console — for free, no extra UI code.
- The same `.py` file can be dropped into
  `~/.local/share/QGIS/QGIS3/profiles/default/processing/scripts/` (or
  `%APPDATA%` on Windows) and used **without installing anything**. Useful on a
  locked-down work machine.
- Customizing means opening one readable file. No build step, no compile.

A thin plugin wrapper (`__init__.py`, `metadata.txt`, `provider.py`) registers
them all as a "Field Kit" group in the toolbox, plus registers the custom
expression functions and a small toolbar for the two or three tools that
genuinely want a live dialog.

### Testability constraint

QGIS can't run in CI. So: **all math lives in pure-Python modules that import
nothing from `qgis`.** Grid origins, rotation, sheet numbering, paper→map-unit
conversion — all pure functions over plain tuples, unit-tested with stdlib
`unittest` in GitHub Actions. The algorithm file is a thin adapter that reads
QGIS parameters, calls the pure function, and writes features.

This is not a purity exercise; it's the only way to have regression tests at
all, and grid math is exactly the kind of code that breaks silently.

### Proposed layout

```
README.md
LICENSE
docs/
  ROADMAP.md
  specs/atlas-grid-builder.md
  tips/                      # the "hacks and tips" half of the suite
fieldkit/                    # the plugin package (zip this to install)
  __init__.py
  metadata.txt
  provider.py
  algs/
    atlas_grid_builder.py
    sheet_estimator.py
    bulk_vector_clip.py
    ...
  core/                      # pure python, no qgis imports — the tested part
    gridmath.py
    paper.py
    naming.py
  expressions/functions.py
  presets/
    paper_sizes.json
    scale_ladders.json
    naming_templates.json
tests/                       # runs without QGIS
```

### Naming

The repo is currently `Bulk_Vector_Clip`, which names one tool rather than the
suite. Suggest keeping the repo name (links and clones already exist) but
naming the *plugin* something suite-shaped — "QGIS Field Kit" is the working
title used here. Easy to change before first release, painful after.

---

## 2. Phasing

### Phase 1 — prove the pattern (the flagship + the namesake)

1. Plugin scaffolding + provider + one preset file.
2. **Atlas Grid Builder** — full spec in
   [`specs/atlas-grid-builder.md`](specs/atlas-grid-builder.md).
3. **Sheet Count Estimator** — shares the same core module; ~40 lines of
   adapter once the grid math exists.
4. **Bulk Vector Clip** — the repo's namesake, and the simplest useful tool.
5. CI running the pure-python tests.

Phase 1 is the whole architecture proven end to end. If the split between
`core/` and `algs/` doesn't feel good here, fix it before there are twelve
tools.

### Phase 2 — the rest of the sheet workflow

6. Corridor Strip Maps
7. Sheet Index & Match Lines
8. Batch Layout Export
9. Auto-configure Atlas (build the layout + wire the atlas from a grid layer)

### Phase 3 — project hygiene

10. Project Packager / Relink
11. CRS Doctor
12. Geometry Cleanup Chain
13. Style Broadcaster

### Phase 4 — domain tools & polish

14. Station & Offset toolkit
15. Expression Pack
16. Field Toolkit
17. Canvas Export at Scale
18. `docs/tips/` written up properly

Ship Phase 1 as `v0.1.0` and use it on a real project before writing Phase 2.
Real use will reorder this list.

---

## 3. Tool specifications

Feasibility is noted per tool. Everything listed is achievable with the PyQGIS
API in QGIS 3.28+ and no third-party dependencies.

### 3.1 Atlas Grid Builder ★ flagship

Full spec: [`specs/atlas-grid-builder.md`](specs/atlas-grid-builder.md).

Summary: coverage polygon + paper size + scale → a sheet grid that is sized
from the paper (not guessed in map units), snapped to a sane origin, optionally
rotated to the site's principal axis, culled to cells that actually contain
coverage, and numbered in the order a plan set reads.

What `native:creategrid` gives you today: spacing X/Y, extent, and overlap in
map units. What it does not: paper-driven sizing, rotation, culling to a
coverage polygon, sliver suppression, sheet numbering, serpentine order,
neighbor attributes, or an estimate mode. That gap is the tool.

### 3.2 Sheet Count Estimator

**Input:** coverage layer, paper size, margins, a scale ladder
(`1"=20'/30'/40'/50'/100'/200'` or `1:500/1:1000/1:2000/1:5000`), overlap %.

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
- Optional: add results to the project in a group, replacing the originals.
- Handles no-geometry and raster layers by passing them through or clipping
  with `gdal:cliprasterbymasklayer`.

**Feasibility:** wraps `native:clip` per layer plus `QgsVectorFileWriter`;
straightforward. The style-preservation and skip-empty behavior are what make
it better than the Batch Processing dialog.

### 3.4 Corridor Strip Maps

**Input:** centerline, sheet length along the line (map units, or derived from
paper+scale), sheet width, overlap, start station.

**Behavior:** walk the line at the interval, take the local bearing at each
station, emit a rectangle rotated to that bearing and centered on (or offset
from) the line. Attributes: `sheet_no`, `sta_begin`, `sta_end`, `bearing`.

**Feasibility:** `QgsGeometry.interpolate()` for the point at a distance,
`interpolateAngle()` for the bearing, build the rectangle in local coordinates
and `QgsGeometry.rotate()` it. Well-trodden.

Optionally emit *curved* strip sheets for tight-radius alignments by
substituting a buffer of the line segment — worth it only if the flat version
proves inadequate on real alignments.

**Why not native:** nothing native does this. It's the reason people buy
Civil 3D for plan-and-profile sheets.

### 3.5 Sheet Index & Match Lines

Byproduct of the grid tools: given a sheet layer, produce (a) a key-map layer
of sheet outlines with labels, and (b) `nbr_n` / `nbr_s` / `nbr_e` / `nbr_w`
attributes so a match-line label can read "SEE SHEET C-12".

**Feasibility:** neighbor lookup is grid arithmetic when the grid came from
our own tool (row/col are attributes); for arbitrary sheet layers, fall back to
a spatial touch test.

### 3.6 Batch Layout Export

**Input:** which layouts (default: all), format, DPI, filename template with
tokens (`{layout}`, `{page}`, `{atlas_name}`, `{date}`), merge-to-single-PDF
toggle.

**Feasibility:** `QgsLayoutExporter.exportToPdf()` / `exportToImage()`, and the
atlas overload of `exportToPdf()` for a merged set. Straightforward; the value
is the filename templating and doing every layout in one go.

### 3.7 Auto-configure Atlas

Take a sheet layer and a layout (existing or created from a template), set the
atlas coverage layer, page-name expression, sort expression, and set the map
item to atlas-driven with a fixed scale.

**Feasibility:** `QgsLayoutAtlas.setCoverageLayer()`, `setPageNameExpression()`,
`setSortExpression()`, `QgsLayoutItemMap.setAtlasDriven()` and
`setAtlasScalingMode()`. All public API. This is the step that turns "I have a
grid" into "I have a plan set," and it's the most-repeated manual sequence in
the whole workflow.

### 3.8 Project Packager / Relink

Copy every file-based data source into `<project>/data/`, rewrite each layer's
source path, and save. Optionally zip the result.

**Feasibility:** iterate `QgsProject.instance().mapLayers()`, parse
`layer.source()` (careful: GPKG and delimited-text sources are URIs with
parameters, not bare paths — use `QgsProviderRegistry.decodeUri()`), copy, then
`layer.setDataSource()`. The URI handling is the only fiddly part.

**Why not native:** `native:package` writes layers to a new GPKG but leaves the
project pointing at the originals. This fixes the actual problem — handing a
project to someone else without a wall of red exclamation marks.

### 3.9 CRS Doctor

Read-only scan producing a report:
- Layers whose CRS ≠ project CRS (and whether that's fine or not).
- Layers with no CRS or a CRS QGIS guessed.
- Layers whose extent doesn't overlap the majority of the project — the
  classic "assigned ft to a metre CRS" symptom.
- `ft` vs `ftUS` mismatches within one project, which silently introduce a
  2 ppm error that matters on State Plane coordinates.

**Feasibility:** all `QgsCoordinateReferenceSystem` / `QgsMapLayer.extent()`
inspection. Easy, high value, and nothing native reports it.

### 3.10 Geometry Cleanup Chain

Chain `native:fixgeometries` → `native:snapgeometries` → remove duplicate
vertices → drop null/empty geometries, and report a before/after count per
step.

**Feasibility:** `processing.run()` chaining. The report is the differentiator.

### 3.11 Style Broadcaster

Copy one layer's style to every layer matching a name pattern or regex; and
save/load named style sets from a folder so the same symbology applies across
projects.

**Feasibility:** `QgsMapLayer.saveNamedStyle()` / `loadNamedStyle()`.

### 3.12 Station & Offset

- Label chainage along a line at an interval, with tick marks.
- Generate offset points at intervals (both sides, configurable).
- Given a point layer and a centerline, compute station + offset per point.

**Feasibility:** `lineLocatePoint()`, `interpolate()`, `closestSegmentWithContext()`.
All present in `QgsGeometry`.

### 3.13 Expression Pack

Custom expression functions registered by the plugin with `@qgsfunction`, so
they're available in the Field Calculator, labels, and atlas page-name
expressions:

- `sheet_label(row, col)` → `A1`, `B12`
- `station_at(layer, geom)` → `12+34.56`
- `area_ac(geom)` / `area_sf(geom)` — unit-aware, no manual conversion factor
- `fmt_scale(denominator)` → `1" = 50'`

**Feasibility:** `@qgsfunction` from `qgis.utils`; registered on plugin load,
unregistered on unload. Small, and disproportionately useful day to day.

### 3.14 Field Toolkit

One dialog to add, rename, drop, and reorder many fields at once, with
expression support per added field.

**Feasibility:** wraps `native:refactorfields`, which already does this but
through a table widget that is painful for more than three fields.

### 3.15 Canvas Export at Scale

Export the current canvas at an exact scale and paper size to PDF/PNG without
building a layout: build a `QgsPrintLayout` in memory, add a map item at the
requested scale centered on the canvas, export, discard.

**Feasibility:** straightforward. This is the single best "hack" in the suite —
a one-click answer to "I just need a 24×36 at 1"=50' of what I'm looking at."

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
- **shortcuts.md** — the keyboard and snapping settings that actually change
  throughput (advanced snapping config, tracing, `Ctrl+.` toggles).
- **crs-notes.md** — State Plane, `ft` vs `ftUS`, and when on-the-fly
  reprojection quietly costs you accuracy.

Each tool also gets a short `docs/specs/*.md` before it's written. Writing the
spec first is what keeps rule #1 (simpler than the native path) honest.

---

## 5. Open questions

1. **Units.** Which CRS do you actually work in day to day (EPSG:2273 SC State
   Plane ftUS?) — the defaults in `presets/` should match it rather than being
   generic.
2. **Paper and scale ladders.** Which sheet sizes and scales does your office
   standardize on? That's a five-minute preset file and it makes the estimator
   immediately correct instead of approximately correct.
3. **Sheet numbering convention.** `C-01`, `SD-101`, plain `1`? Drives the
   default naming template.
4. **QGIS version floor.** Targeting 3.28 LTR unless you're on 3.34/3.40 —
   this only affects a couple of API calls.
5. **Distribution.** Just clone-and-symlink for you, or a zip release / plugin
   repository entry so coworkers can install it?
