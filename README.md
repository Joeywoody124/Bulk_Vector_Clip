# Bulk Vector Clip — QGIS Field Kit

A suite of QGIS tools for the jobs that QGIS *technically* supports but makes
tedious: laying out atlas sheet grids, clipping thirty layers to one boundary,
packaging a project so it doesn't arrive with broken paths.

**Status: planning.** No tool code exists yet. This README and
[`docs/ROADMAP.md`](docs/ROADMAP.md) are the design; nothing here is installable.

---

## Why this exists

Most of these tasks are already possible in QGIS. They're just spread across
the Processing toolbox, the Batch dialog, the layout designer, and three
plugins that each do 20% of the job. The friction is never "can QGIS do it" —
it's the eight dialogs, the units that don't match, and the fact that you
have to redo the whole sequence next week on the next site.

This suite collapses those sequences into single tools with defaults that
already match how you work.

## Design rules

These are non-negotiable, because they're the entire point:

1. **Simpler than the QGIS counterpart, or it doesn't ship.** If a tool needs
   more clicks than the native path, it's a failed design.
2. **One screen, sensible defaults.** Every parameter has a default that works
   for a typical site plan. Advanced options collapse.
3. **Readable, editable Python.** Every tool is a plain `.py` file with no
   compiled parts and no dependencies beyond what QGIS already ships. Open it,
   change the default sheet size, save. That's the customization story.
4. **Presets are JSON files.** Paper sizes, scale ladders, naming templates —
   all in `presets/`, all editable, all shareable by dropping a file in Slack.
5. **Estimate before you generate.** Anything that can produce 200 features
   has a dry-run mode that just tells you the count.
6. **Feet are a first-class citizen.** US survey feet, `ft` vs `ftUS`, State
   Plane — handled explicitly, not assumed to be meters.

## The tools (planned)

### Sheets & atlas

| Tool | What it does | Why not the native one |
|---|---|---|
| **Atlas Grid Builder** | Coverage polygon + paper size + scale → a numbered, culled, optionally rotated sheet grid ready to drive an atlas | `native:creategrid` has no paper-size sizing, no rotation, no culling to coverage, no sheet numbering |
| **Sheet Count Estimator** | "How many sheets at 1"=50'? At 1"=100'?" — a table, no layers created | Doesn't exist. Today you generate a grid and count rows |
| **Corridor Strip Maps** | Centerline + station interval → sheets rotated to follow the road/pipe | Doesn't exist natively at all |
| **Sheet Index & Match Lines** | Key map layer + neighbor sheet IDs for match-line callouts | Manual |
| **Batch Layout Export** | Every layout / every atlas page → PDF or PNG with a filename template, optionally merged | Atlas export is per-layout and per-hand |

### Bulk operations

| Tool | What it does | Why not the native one |
|---|---|---|
| **Bulk Vector Clip** | Clip every visible layer to one boundary, keep styles, write to one GeoPackage, skip empty results | `native:clip` is one layer at a time; Batch Processing drops styles |
| **Project Packager** | Copy all file-based sources next to the project and rewrite the paths | `native:package` doesn't relink the project or handle rasters well |
| **Geometry Cleanup Chain** | Fix geometries → snap → dedupe vertices → drop nulls, with a report of what changed | Four separate algorithms, no report |
| **Style Broadcaster** | Push one layer's style to every layer matching a name pattern | Copy/paste style, one at a time |

### QA & everyday

| Tool | What it does |
|---|---|
| **CRS Doctor** | Scans the project for mismatched, missing, or obviously-wrong CRS (features sitting at 0,0 or 400 km off-site) |
| **Field Toolkit** | Add/rename/drop/reorder many fields in one pass |
| **Station & Offset** | Chainage labels along a line, offset points at intervals, station-offset lookup |
| **Canvas Export at Scale** | Export the current view at an exact scale and paper size without building a layout |
| **Expression Pack** | Custom expression functions (`sheet_label()`, `station_at()`, `area_ac()`) installed with the plugin |

Plus [`docs/tips/`](docs/ROADMAP.md#documentation-plan) — the hacks that are
documentation rather than code: expression snippets, styling tricks, Processing
model patterns.

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the architecture, phasing, and
per-tool specs. The flagship tool has its own detailed spec:
[`docs/specs/atlas-grid-builder.md`](docs/specs/atlas-grid-builder.md).

## License

MIT — see [LICENSE](LICENSE).
