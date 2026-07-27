# Laying out a sheet set by hand

The auto-generated grid is a starting point, not an answer. Real sheet sets get
nudged: a sheet slides over to catch the whole intersection, two get merged,
one gets added for the offsite easement. The workflow below keeps the numbering
and the match-line callouts correct while you do that.

No custom UI is involved — QGIS's own editing tools already move polygons
well, and rebuilding that would be worse than what's already there. The piece
that was missing is making the labels agree afterwards, and that's
**Renumber sheets**.

---

## The loop

### 1. Generate

**Field Kit → Sheets → Atlas grid builder.**

Send the output somewhere editable and permanent — a GeoPackage, not a
temporary layer. You're going to be editing it over several sessions.

Get the scale roughly right first with the **Sheet count estimator**; changing
scale later means regenerating, which throws away your manual moves.

### 2. Move things around

Toggle editing on the sheet layer and use the tools QGIS already has:

| Job | Tool |
|---|---|
| Slide a sheet | **Move Feature(s)** (Edit toolbar) |
| Slide it an exact distance | Move Feature, then type into the Advanced Digitizing panel (`Ctrl+4`) — `d` for distance, `a` for bearing |
| Add a sheet | Select an existing one, `Ctrl+C`, `Ctrl+V`, then move the copy. It arrives the right size, which drawing one never does |
| Delete a sheet | Select, `Delete` |
| Rotate one sheet | **Rotate Feature(s)** |

Two things worth setting up before you start:

- **Turn snapping off, or set it to the sheet layer only.** Snapping to the
  data underneath will jump sheet corners onto random parcel vertices.
- **Enable "show feature labels"** on `sheet_id` so you can see what you're
  moving. Everything below assumes you can read the numbers on screen.

Keep sheets the same size unless you mean to. The renumbering works from
centres and bounding boxes, so an accidentally-scaled sheet still gets numbered
— it just prints at the wrong scale, silently.

### 3. Renumber

**Field Kit → Sheets → Renumber sheets**, pointed at the same layer. It edits
in place, so you can run it as many times as you like.

It re-derives rows from where the sheets actually sit, then rewrites
`sheet_no`, `sheet_id`, `grid_ref`, `row`, `col`, `center_x`, `center_y` and
the four `nbr_*` neighbour fields. Missing fields get added.

Then look at the map. The labels are the check — if the numbering reads
wrong, it will read wrong on screen.

### 4. Repeat

Move more, renumber again. That's the whole loop.

---

## How rows get worked out

The original `row` and `col` stop meaning anything the moment you drag a sheet,
so they're thrown away and rebuilt from position.

Sheets are sorted top to bottom, and a new row starts when a sheet's centre
sits more than **half a sheet** below the one that opened the current row.
Nudge a sheet sideways or a little up and it stays in its row; drop it a full
sheet down and it starts a new one.

That half-sheet figure is the *How far a sheet can sit off its row* advanced
setting. Raise it toward 1.0 if you have a staircase layout following a
diagonal corridor and it keeps splitting rows that should be one. Lower it
toward 0.25 if two genuinely separate rows are being merged.

Neighbours (`nbr_n`, `nbr_s`, `nbr_e`, `nbr_w`) always come from rows on the
ground, never from the numbering order — a match line means the sheet next to
this one, whatever number it happens to carry.

## Keeping a label you typed yourself

Add an integer field called `locked` to the sheet layer, put `1` in it for the
sheets whose ids you've set by hand, and point the **Keep the existing id where
this field is set** parameter at it.

Those sheets keep their ids. Everything else renumbers around them. The sheet
numbers (`sheet_no`) still advance across every sheet, so nothing collides.

This is how you handle the sheet that has to be `C-101A` because it was issued
that way, or the detail sheet that was inserted after the fact.

## Wiring it to an atlas

Once the layer looks right:

- Layout → Atlas: coverage layer is the sheet layer, page name expression is
  `"sheet_id"`, sort by `"sheet_no"`.
- Map item: **Controlled by atlas**, fixed scale. Bind the scale to `"scale"`
  and the map rotation to `"map_rotation"` with data-defined overrides, and one
  layout serves every project.
- Match-line labels: `'SEE SHEET ' || "nbr_e"`, and so on. Wrap in a
  `coalesce()` so edge sheets don't print `SEE SHEET NULL`.

Because the tools write these fields on every run, none of that layout wiring
needs touching again after you move sheets.

---

## What a dedicated panel would add

A docked Sheet Manager — a list of sheets, click to zoom, drag to reorder,
buttons to add and delete — is the obvious next step, and it's on the backlog.
It's deliberately not built yet, because most of what it would provide already
exists:

| Panel feature | What QGIS already gives you |
|---|---|
| List of sheets | The attribute table, sorted on `sheet_no` |
| Click a sheet to zoom to it | Attribute table → *Zoom to feature* |
| Edit a label | Edit the `sheet_id` cell, and set `locked` so it survives |
| Reorder numbering | Move the sheet, run Renumber |
| Add / delete | Copy-paste and `Delete` |

The genuinely missing pieces are **add a sheet by clicking where you want its
centre**, and **live renumbering as you drag**. Both need a `QgsMapTool` and a
dock widget — a real chunk of work, and the part of the codebase hardest to
keep simple and testable.

Worth building once this loop has been used on a real sheet set and it's clear
which parts are actually annoying. If dragging-then-renumbering turns out to
be two clicks too many, that's the argument for the panel — and by then it'll
be obvious what it needs to do.
