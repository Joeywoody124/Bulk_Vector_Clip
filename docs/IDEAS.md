# Ideas backlog

Everything considered for the toolbox but not built yet. Each one has a note on
what QGIS already does, so it is obvious whether a tool would earn its place.

Ranked roughly by how much they'd get used. Nothing here needs a library QGIS
doesn't already ship.

---

## Editing - the strongest candidates

### 1. Erase overlaps ★
The mirror of *Fill gaps*. Where two polygons overlap, give the overlap to one
of them by a rule: first drawn, largest, smallest, or by a priority field.
Report what was taken from whom.

Gaps and overlaps are the same digitising mistake in opposite directions, and
fixing only one is half a job. **Native:** nothing. The Geometry Checker can
find overlaps but its fixes are all-or-nothing.

### 2. Polygonize with diagnostics ★
`native:polygonize` builds polygons from linework and silently drops any loop
that doesn't close. This version reports *where* it failed: a point layer of
unclosed nodes with the gap distance, so you can see the three places your
linework is 0.02 ft short instead of guessing.

This is the real answer to "trace without gaps" - draw the linework, let the
tool tell you where it doesn't close, fix those spots, build the polygons.
**Native:** polygonize exists, diagnostics don't.

### 3. Fillet corners ★
Round a polygon or line corner with a given radius. Curb returns at every
intersection, radii at ROW corners, knuckles on a cul-de-sac.

Pairs directly with *Right of way from centerline*: build the corridor, then
fillet the returns. **Native:** nothing. This is the most-missed CAD feature in
QGIS.

### 4. Split polygon by area
Cut a parcel into pieces of a specified area or into N equal parts, along a
given bearing or perpendicular to an edge. Binary search on a sweep line; a
known, solvable problem.

**Native:** nothing. `native:splitwithlines` needs you to already know where
the line goes, which is the hard part.

### 5. Move by bearing and distance
Move, rotate or scale the selected features by typed values: a bearing and a
distance, a rotation about a specified point, a scale about a centroid.

**Native:** `native:affinetransform` does this behind a matrix-shaped UI that
nobody wants to fill in at 4pm.

### 6. Spike and sliver detector
Report near-zero-angle vertices, duplicate vertices, self-intersections and
needle-thin slivers as a point layer with the offending angle or width. Finding
these is most of the work; fixing them is usually a judgement call.

**Native:** Geometry Checker finds some of it, mixed in with everything else.

### 7. Conform edge
Replace the shared edge of polygon A with polygon B's version of it, so they
match exactly, without touching the rest of either. *Snap to layer and verify*
covers most cases; this is the surgical version for when it doesn't.

---

## Sheets and layouts

### 8. Corridor strip maps ★
Centerline plus station interval in, sheets rotated to the local bearing out.
Plan-and-profile sheet layout for a road or a pipe run. Attributes carry
begin/end station and bearing.

`QgsGeometry.interpolate()` for the point, `interpolateAngle()` for the
bearing. **Native:** nothing does this. It is why people keep a CAD seat.

### 9. Auto-configure atlas
Take a sheet layer and a layout and wire them together: coverage layer, page
name expression, sort order, atlas-driven map at a fixed scale, rotation bound
to `map_rotation`. The most-repeated manual sequence in the whole workflow.

All public API (`QgsLayoutAtlas`, `QgsLayoutItemMap.setAtlasDriven`).

### 10. Batch layout export
Every layout, or every atlas page, to PDF or PNG with a filename template
(`{layout}`, `{page}`, `{date}`) and an option to merge into one PDF.
**Native:** atlas export is per-layout, by hand.

### 11. Sheet index and match lines
Key map layer plus `nbr_*` lookups for "SEE SHEET C-12" callouts. Half of this
already exists as attributes on the grid builder's output; this packages it.

### 12. Canvas export at scale
Export the current view at an exact scale and paper size to PDF without
building a layout - build a `QgsPrintLayout` in memory, export, discard. The
best small hack on this list.

---

## Project hygiene

### 13. CRS doctor ★
Scan the project and report: layers whose CRS differs from the project's,
layers with no CRS, and layers whose extent doesn't overlap the others - the
classic symptom of a misassigned CRS. Read-only, instant, and nothing native
reports it.

### 14. Project packager / relink
Copy every file-based source next to the project and rewrite the paths so it
can be handed to someone else without a wall of red exclamation marks. The
fiddly part is that GeoPackage and delimited-text sources are URIs, not paths -
use `QgsProviderRegistry.decodeUri()`.

**Native:** `native:package` writes the data but leaves the project pointing at
the originals.

### 15. Geometry cleanup chain
Fix geometries → snap → remove duplicate vertices → drop empties, with a
before/after count at each step. Four algorithms exist; the chain and the
report don't.

### 16. Style broadcaster
Push one layer's style onto every layer matching a name pattern, and save named
style sets to a folder so the same symbology applies across projects.

---

## Civil and stormwater

### 17. Station and offset
Chainage labels along an alignment, offset points at intervals, and
station/offset lookup for a point layer against a centerline.
`lineLocatePoint()` and `closestSegmentWithContext()` do the work.

### 18. Pipe network sanity check
Inverts that don't fall downstream, pipes whose ends don't reach a structure,
structures with no pipes, duplicated node IDs. Ordinary topology checks with a
domain-specific report.

### 19. Expression pack
Custom functions registered with `@qgsfunction`, available in the field
calculator, labels and atlas expressions: `sheet_label()`, `station_at()`,
`area_ac()`, `fmt_scale()`. Small, and used constantly once they exist.

---

### 20. Sheet Manager panel ★
A docked panel over the sheet layer: the list of sheets, click to zoom, add a
sheet by clicking where its centre goes, delete, edit a label inline, and
renumber as you drag rather than after.

Most of what a panel would give you already exists — the attribute table is the
list, *Zoom to feature* is the zoom, copy-paste is "add a sheet", and
**Renumber sheets** closes the loop. See
[`sheet-workflow.md`](sheet-workflow.md) for how far that gets you.

The two genuinely missing pieces are **click to place a sheet** and **live
renumbering while dragging**. Both need a `QgsMapTool` plus a dock widget: a
real chunk of work, untestable in CI, and the part of the codebase hardest to
keep simple. Worth building once the existing loop has been used on a real
sheet set and it's clear which parts actually grate.

---

## Needs a map tool, not a Processing algorithm

These want live interaction with the canvas, so they'd need a toolbar and a
`QgsMapTool` subclass rather than a toolbox entry. More work, and harder to
keep simple - worth it only if the tool gets used daily.

- **Live ROW tracing** - draw a centerline and watch the corridor build as you
  go, with the offset editable mid-draw.
- **Snap brush** - click a node and pull every vertex within a radius onto it.
- **Vertex to typed coordinate** - select a vertex, type a survey coordinate,
  done.

---

## Deliberately not building

- **A better field calculator.** The native one is fine and everyone knows it.
- **Anything wrapping a GDAL algorithm one-to-one.** If the only improvement is
  a nicer label, it's noise in the toolbox.
- **Format conversion tools.** *Save As* and `native:package` cover it.
- **Automatic gap filling with no threshold.** A tool that silently swallows a
  pond because it looked like a sliver is worse than no tool.
