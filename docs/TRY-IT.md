# Try it — a 20 minute test drive

Sample data ships with the repo, with known faults in it. Every step below says
what you should see, so this is a test rather than a demo: if a number doesn't
match, something is wrong and it's worth telling me.

Everything is in **EPSG:3361**, feet.

---

## 1. Install

Full detail in [INSTALL.md](INSTALL.md). The short version:

```bash
git clone https://github.com/Joeywoody124/Bulk_Vector_Clip.git ~/src/Bulk_Vector_Clip
```

**Windows** (PowerShell as administrator):

```powershell
New-Item -ItemType SymbolicLink `
  -Path "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins\fieldkit" `
  -Target "C:\src\Bulk_Vector_Clip\fieldkit"
```

**Linux:**

```bash
ln -s ~/src/Bulk_Vector_Clip/fieldkit \
  ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/fieldkit
```

Restart QGIS, then *Plugins → Manage and Install Plugins → Installed* and tick
**Field Kit**.

> If it isn't in the list, tick *Show also experimental plugins* in the Settings
> tab — the plugin is marked experimental until it has been used on a real job.

### Check it loaded

Open the Processing Toolbox (`Ctrl+Alt+T`). You should see **Field Kit** with
three groups and **nine** tools:

- **Editing** — Close dangling line ends, Erase overlaps between polygons,
  Fill gaps between polygons, Right of way from centerline, Snap to layer and verify
- **Sheets** — Atlas grid builder, Renumber sheets, Sheet count estimator
- **Bulk** — Bulk vector clip

If Field Kit is missing entirely, open *Plugins → Python Console* and look for
an import error. The usual cause is the plugin folder being named something
other than `fieldkit`.

## 2. Open the sample data

Drag `sample/fieldkit_demo.gpkg` from the repo onto the QGIS window and add all
seven layers. Set the project CRS to EPSG:3361 (*Project → Properties → CRS*).

| Layer | What's wrong with it, deliberately |
|---|---|
| `site_boundary` | Nothing — an L-shaped 4000 × 3000 ft site |
| `road_centerline` | Nothing — two roads, with a `row_width` field |
| `parcels_with_gaps` | One parcel missing entirely; two 3 ft slivers |
| `parcels_with_overlaps` | Two overlapping pairs, one 20 ft, one 2 ft |
| `storm_pipes` | Two laterals stop short of the trunk; one stops 70 ft short |
| `survey_parcels` | Nothing — the good boundary |
| `field_sketch` | The same boundary traced by eye, corners 1–4 ft out |

Rebuild it any time with
`QT_QPA_PLATFORM=offscreen python3 tools/make_sample_data.py`.

---

## 3. Right of way from centerline

The one to try first, because the data-defined offsets are the part that isn't
obvious.

1. Run **Editing → Right of way from centerline**.
2. Input: `road_centerline`.
3. Beside **Offset left**, click the little button to the right of the number
   box (it looks like a slider or a data-defined icon) → **Edit…** → enter:

   ```
   "row_width" / 2
   ```

   Do the same for **Offset right**.
4. Leave the end treatment on *Flat* and run.

**Expect:** two polygons.

| Road | row_width | Area |
|---|---|---|
| Palmetto Way | 60 | 231,609 sf |
| Live Oak Lane | 50 | 110,000 sf |

Live Oak is 2200 ft of centreline at 50 ft wide — exactly 110,000 sf, which is
the check that the offsets are doing what they claim.

**Then try:** set both offsets back to plain numbers, 40 left and 20 right, and
run again. The corridor should sit visibly off-centre from the road.

## 4. Fill gaps between polygons

1. Run **Editing → Fill gaps between polygons** on `parcels_with_gaps`.
2. Set **What to do** to *Report only*. Run.

**Expect:** two gaps.

| Gap | Origin | Area |
|---|---|---|
| 1 | interior | 300,000 sf |
| 2 | interior | 1,500 sf |

The 300,000 sf one is the missing parcel — a real hole, not a sliver. The 1,500
sf one is a 3 ft × 500 ft sliver.

3. Now run it again with:
   - **Ignore gaps larger than** `5000`
   - **Also find open-ended slivers narrower than** `10`
   - **What to do**: *give each gap to the neighbour it shares the most edge with*

**Expect:** two gaps, both 1,500 sf — the missing parcel is now correctly left
alone, and a *second* sliver appears with origin `sliver`. That one is open at
the bottom edge of the block, so it is not a hole in the dissolved coverage and
the first run could not see it at all.

Two parcels come back with `gaps_filled = 1`. Style the output by `gaps_filled`
to see which.

## 5. Erase overlaps between polygons

1. Run **Editing → Erase overlaps between polygons** on
   `parcels_with_overlaps`, rule *The one drawn first keeps it*.

**Expect:** two overlaps, 10,000 sf and 1,000 sf, both trimmed. In the output,
`OV-B` lost 10,000 sf and `OV-D` lost 1,000 sf; `OV-A` and `OV-C` lost nothing.

2. Run again with **Leave overlaps larger than** `5000`.

**Expect:** the 10,000 sf overlap is reported with action *left alone* and
nothing is trimmed from `OV-B`. That's the point of the setting: a 20 ft slab
across a parcel line is a disagreement, not slop.

3. Run again with rule *The higher value in a field keeps it* and the priority
   field set to `survey_year`. Now the newer survey wins, so `OV-A` (2018) loses
   to `OV-B` (2024) instead of the other way round.

## 6. Close dangling line ends

1. Run **Editing → Close dangling line ends** on `storm_pipes`, tolerance `20`.

**Expect** in the dangle report:

| Pipe | Status | Distance |
|---|---|---|
| LAT-1 | extended | 5.0 ft |
| LAT-2 | extended | 12.0 ft |
| LAT-4 | unresolved | — (70 ft short, past the tolerance) |

Plus several `unresolved` entries for the open ends of the trunk and the tops of
the laterals. **That is correct** — the far end of a lateral and the end of the
trunk are genuine ends of the network, not faults. Unresolved means "I looked
and didn't close it", not "this is broken". Look before raising the tolerance.

## 7. Snap to layer and verify

1. Run **Editing → Snap to layer and verify**: layer `field_sketch`, align to
   `survey_parcels`, tolerance `10`.

**Expect:** `snap_moved = 5`, `snap_max = 4.12` ft. (Five, not four, because the
closing vertex of the ring counts.)

2. Add the **Displacement vectors** output to the map and style it red over the
   original. Each vector shows exactly which corner moved and how far — this is
   the check you do *before* accepting a snap.

3. Run again with **Reject a feature if any vertex would move further than**
   set to `2`. The feature is now written out untouched with `snap_moved = 0`,
   and the log says why. That guard is what stops a loose tolerance dragging a
   corner across the street.

## 8. Sheet count estimator

1. Run **Sheets → Sheet count estimator** on `site_boundary`, leave the scale
   ladder at its default.

**Expect**, on ARCH D landscape with 1" margins and 5% overlap:

| Scale | Sheets |
|---|---|
| 1"=20' | 40 |
| 1"=40' | 12 |
| 1"=60' | 8 |
| 1"=100' | 3 |
| 1"=200' | 1 |

The log also prints the ground size of a sheet at each scale and the average
fill. Low fill means you're printing white paper.

## 9. Atlas grid builder

1. Run **Sheets → Atlas grid builder** on `site_boundary` — everything at its
   default (ARCH D, landscape, 1"=60', 5% overlap, centred, cull on).

**Expect 8 sheets**, `C-01` through `C-08`, matching the estimator exactly.
Each sheet is **2040 × 1320 ft** on the ground. Check a couple of attributes:

| Sheet | grid_ref | cov_pct | nbr_e | nbr_s |
|---|---|---|---|---|
| C-01 | A1 | 36% | C-02 | C-03 |
| C-02 | A2 | 17% | — | C-04 |
| C-07 | C2 | 69% | C-08 | — |

`cov_pct` of 17% on C-02 is the tool telling you that sheet is mostly empty.

2. Label the layer by `sheet_id` so you can read the numbering on screen.
3. Try **Rotation → Auto** on a diagonal site of your own — on this L-shaped
   one, square is already the right answer.

## 10. Renumber after moving sheets

This is the loop, and the reason the grid is a starting point rather than an
answer. Full write-up in [sheet-workflow.md](sheet-workflow.md).

1. Save the grid from step 9 into a GeoPackage (right-click → *Export → Save
   Features As*), and add it back. Memory layers work, but you'll want it to
   persist.
2. Toggle editing on it. Turn **snapping off** first, or sheet corners will
   jump onto parcel vertices.
3. Use **Move Feature(s)** to slide a sheet somewhere else. Copy-paste one to
   add a sheet — it arrives the right size, which drawing one never does.
4. Run **Sheets → Renumber sheets** on the same layer.

**Expect:** numbering, `grid_ref` and the four `nbr_*` fields all rebuilt from
where the sheets now sit. Move a sheet a long way down and it joins the row
below; nudge it sideways and it stays in its row.

5. Add an integer field `locked`, put `1` in one sheet, and re-run with **Keep
   the existing id where this field is set** pointed at it. That sheet keeps
   its id while everything else renumbers around it.

## 11. Bulk vector clip

1. Run **Bulk → Bulk vector clip**. Layers: tick all seven. Boundary:
   `site_boundary`. Output: a new `.gpkg`.

**Expect:** five layers written, two skipped.

| Layer | Result |
|---|---|
| `site_boundary` | 1 feature |
| `road_centerline` | 2 features |
| `parcels_with_gaps` | 11 features |
| `parcels_with_overlaps` | **3** features — `OV-D` falls outside the site and is dropped |
| `storm_pipes` | 5 features |
| `survey_parcels`, `field_sketch` | skipped — nothing inside the boundary |

The log lists what went where and what was skipped. Styles are stored inside
the GeoPackage.

2. Style a layer before running, then add the clipped copy back — it should come
   back styled.

---

## Then: your own data

The one thing the sample can't tell you is whether the sheet set *prints*
right. On a real project:

1. Estimator across your scales. Sanity check one row by hand.
2. Grid at your chosen scale, output to a GeoPackage.
3. Wire the atlas: coverage layer is the sheet layer, page name expression
   `"sheet_id"`, sort by `"sheet_no"`. Map item → *Controlled by atlas*, fixed
   scale bound to `"scale"`.
4. Match-line labels: `coalesce('SEE SHEET ' || "nbr_e", '')`.
5. Export and look: no blank sheets, adjacent sheets visibly overlap, numbering
   reads in a sensible order, callouts name real neighbours.

That last step is the only part of this toolkit that has never been checked by
anything but eyes, so it's the one worth doing carefully the first time.

## Running the automated tests

```bash
# maths only, no QGIS needed
python -m unittest discover -s tests

# every algorithm against real QGIS
QT_QPA_PLATFORM=offscreen python3 tests/smoke_qgis.py
```

Both run in CI on every push. The smoke tests use synthetic layers rather than
this sample GeoPackage, so the two are independent checks of the same code.

## If something goes wrong

- **A tool errors out** — the Processing log usually says why in plain words
  (wrong CRS, margins bigger than the sheet, a template with an unknown field).
  Copy the whole log into an issue.
- **"The coverage layer is in a geographic CRS"** — your layer is in EPSG:4326.
  Reproject to 3361; degrees make every distance meaningless.
- **A tool is missing from the toolbox** — check the Python Console for import
  errors after enabling the plugin.
- **Changed a tool and nothing happened** — install the **Plugin Reloader**
  plugin and reload Field Kit; QGIS caches Python modules.
