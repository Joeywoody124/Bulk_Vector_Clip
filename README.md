# Bulk Vector Clip — QGIS Field Kit

A Processing provider for QGIS that handles the jobs QGIS *technically*
supports but makes tedious: closing the gaps between polygons, building a
right-of-way from a centerline, laying out atlas sheet grids, clipping thirty
layers to one boundary.

**v0.2.0 — nine tools, installable, and verified against a real QGIS.**
See [`docs/INSTALL.md`](docs/INSTALL.md). Requires QGIS 3.34+ and nothing else —
no third-party Python packages. Every algorithm is exercised end to end on
synthetic layers in EPSG:3361 by `tests/smoke_qgis.py`, which runs in CI
against QGIS 3.34.

---

## Why this exists

Most of these tasks are already possible in QGIS. They're just spread across
the Processing toolbox, the Batch dialog, the layout designer, and three
plugins that each do 20% of the job. The friction is never "can QGIS do it" —
it's the eight dialogs, the units that don't match, and the fact that you have
to redo the whole sequence next week on the next site.

## Design rules

1. **Simpler than the QGIS counterpart, or it doesn't ship.** If a tool needs
   more clicks than the native path, it's a failed design.
2. **One screen, sensible defaults.** Rarely-changed parameters go under
   Advanced.
3. **Readable, editable Python.** One file per tool, no compiled parts, no
   dependencies. Open it, change the default, reload.
4. **Estimate before you generate.** Anything that can produce 200 features
   tells you the count first.
5. **Show your work.** Tools that move geometry report what moved and by how
   much. Snapping you can't verify is just hoping.
6. **Feet are a first-class citizen.** US survey feet, `ft` vs `ftUS`, State
   Plane — handled explicitly, not assumed to be metres.

## The tools

In the Processing Toolbox under **Field Kit**.

### Editing

| Tool | What it does | vs. native |
|---|---|---|
| **Right of way from centerline** | Centerline + independent left/right offsets → closed ROW polygon. Offsets are data-defined, so a width field can drive them. Flat, square or rounded ends; mitred corners. | Buffer is symmetrical and rounds the ends |
| **Fill gaps between polygons** | Dissolves, treats every hole as a gap, gives each gap to the neighbour it shares the most edge with. Finds open-ended slivers too, via a width setting, and an optional boundary layer catches edge gaps. Size threshold so a pond doesn't get swallowed. Report-only mode. | Geometry Checker finds them; fixing is all-or-nothing |
| **Snap to layer and verify** | Snaps geometry to a reference layer, then reports per-feature how many vertices moved and how far, plus a displacement-vector layer. A move guard rejects features that would jump too far. | `native:snapgeometries` snaps blind |
| **Erase overlaps between polygons** | The mirror of Fill gaps. Where two polygons overlap, one keeps the ground by a rule — drawn first, larger, smaller, or a priority field — and the other is trimmed. Large overlaps are reported rather than silently resolved. | Geometry Checker finds them; nothing native resolves them by rule |
| **Close dangling line ends** | Extends undershooting line ends along their own bearing until they meet the network, or snaps to nearest. Point report of every dangle: extended, snapped, or unresolved. | `native:extendlines` extends by a fixed distance, at everything |

Half of the gap problem is settings, not tools —
[`docs/tips/digitising-without-gaps.md`](docs/tips/digitising-without-gaps.md)
covers the three that matter.

### Sheets

| Tool | What it does | vs. native |
|---|---|---|
| **Atlas grid builder** | Coverage polygon + paper size + scale → numbered sheet grid. Sized from the paper, centred or snapped to a round coordinate, optionally rotated to the site's own axis, culled to cells with real coverage, numbered in plan-set order. Carries `sheet_id`, `scale`, `map_rotation`, `cov_pct` and neighbour ids for match lines. | `native:creategrid` gives spacing and overlap in map units, and nothing else on that list |
| **Sheet count estimator** | "How many sheets at 1"=60'? At 1"=100'?" across a whole scale ladder, creating nothing. Counts come from really laying out and culling each grid. | Doesn't exist |
| **Renumber sheets** | Move sheets wherever the job needs them with QGIS's own Move tool, then rebuild the numbering, grid refs and neighbour links from where they actually sit. Edits the layer in place, so it's a loop. A `locked` field keeps ids you typed by hand. | Doesn't exist |

The generate → move → renumber loop is written up in
[`docs/sheet-workflow.md`](docs/sheet-workflow.md).

### Bulk

| Tool | What it does | vs. native |
|---|---|---|
| **Bulk vector clip** | Clips every selected layer to one boundary into a single GeoPackage. Reprojects the boundary per layer, stores styles inside the GPKG, skips layers that clip to nothing. | `native:clip` is one layer at a time; the Batch dialog drops styles |

## Defaults

Set for engineering plan sets: **Letter, Tabloid and ARCH D (24×36)** at the
top of the paper list, **ARCH D landscape** with 1" margins as the default, and
**1"=60'** as the default scale. The estimator's ladder is 1"=20' through
1"=200'. Scales parse however you write them — `1"=60'`, `1"=60`, `1 in = 60 ft`
and `1:720` are all the same thing.

Sheet sizes come out in the layer's own units, read from its CRS. In
**EPSG:3361 (NAD83(HARN) / South Carolina, feet)** a 24×36 at 1"=60' with 1"
margins covers **2040 × 1320 ft**. The same settings in a metre CRS give
621.8 × 402.3 m — the same ground, different numbers.

All of this lives in `fieldkit/core/paper.py` and is a one-line edit. See
[`docs/tips/crs-notes.md`](docs/tips/crs-notes.md) for why SC is one of the
few states where `ft` vs `ftUS` isn't a trap.

## Documentation

- [`docs/INSTALL.md`](docs/INSTALL.md) — install, customize, call from Python
- [`docs/sheet-workflow.md`](docs/sheet-workflow.md) — generating a sheet set,
  moving sheets by hand, keeping the numbering and match lines correct
- [`docs/tips/digitising-without-gaps.md`](docs/tips/digitising-without-gaps.md)
  — snapping, topological editing, avoid-overlap, tracing, advanced digitising
- [`docs/tips/crs-notes.md`](docs/tips/crs-notes.md) — EPSG:3361, SC State
  Plane, and the sheet size table for the papers and scales in daily use
- [`docs/IDEAS.md`](docs/IDEAS.md) — the backlog, with what QGIS already does
  for each, so it's clear which ones would earn their place
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — architecture and phasing
- [`docs/specs/atlas-grid-builder.md`](docs/specs/atlas-grid-builder.md) — the
  flagship tool in detail

## Development

Two test layers, both in CI.

**Unit tests** cover `fieldkit/core/`, which imports nothing from `qgis` — so
the grid, paper and ordering maths is testable without a QGIS install at all:

```bash
python -m unittest discover -s tests
```

**Smoke tests** run every algorithm end to end against a real QGIS, on
synthetic layers in EPSG:3361 — checking that a ROW polygon comes out the right
area, that erasing overlaps leaves exactly the union area behind, that a snapped
grid origin lands on a round coordinate, and so on:

```bash
QT_QPA_PLATFORM=offscreen python3 tests/smoke_qgis.py
```

Needs QGIS installed (`apt install python3-qgis`), run with the system python
the bindings were built against.

## License

MIT — see [LICENSE](LICENSE).
