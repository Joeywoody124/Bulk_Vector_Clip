# Grid Tools — standalone QGIS plugin

The three sheet-layout tools from Field Kit, packaged on their own so you can
drop this one folder into QGIS and test it.

| Tool | What it does |
|---|---|
| **Atlas grid builder** | Coverage polygon + paper size + scale → a numbered sheet grid, culled to sheets with real coverage, optionally rotated to fit the site |
| **Sheet count estimator** | How many sheets at each scale on your ladder, without creating anything |
| **Renumber sheets** | After you move sheets around by hand, rebuild the numbering, grid refs and neighbour links from where they actually sit |

Requires QGIS 3.34 or newer. Nothing else — no pip installs.

**Generated, not hand-edited.** Built from `fieldkit/` in the repo by
`tools/build_gridtools.py`. If you change a tool, change it in `fieldkit/` and
re-run the builder, or the two copies drift apart.

---

## 1. Get the files onto your machine

Open **Command Prompt** (not PowerShell — the commands below are `cmd` syntax):

```bat
cd /d "E:\CLAUDE_Workspace\Claude\Report_Files\Projects\Bulk_Vector_Clip_Utilties"
git clone -b claude/qgis-script-suite-plan-y4uave https://github.com/Joeywoody124/Bulk_Vector_Clip.git
```

That gives you:

```
E:\CLAUDE_Workspace\Claude\Report_Files\Projects\Bulk_Vector_Clip_Utilties\
    Bulk_Vector_Clip\
        dist\gridtools\          <-- this plugin
        fieldkit\                <-- the full nine-tool plugin
        sample\fieldkit_demo.gpkg
        docs\
```

**No git?** Download
<https://github.com/Joeywoody124/Bulk_Vector_Clip/archive/refs/heads/claude/qgis-script-suite-plan-y4uave.zip>,
unzip it into that folder, and the plugin is in `dist\gridtools` inside.

## 2. Install into QGIS

**Easiest:** double-click **`install_windows.bat`** in this folder. It creates a
directory junction into your QGIS plugins folder and tells you what to do next.

A junction (`mklink /J`) does **not** need administrator rights, unlike a
symbolic link. And because it's a link rather than a copy, `git pull` updates
what QGIS runs.

**By hand**, if you prefer:

```bat
mklink /J "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\gridtools" ^
  "E:\CLAUDE_Workspace\Claude\Report_Files\Projects\Bulk_Vector_Clip_Utilties\Bulk_Vector_Clip\dist\gridtools"
```

**Or just copy it** — simplest, but you'll have to re-copy after any change:

```bat
xcopy /E /I ^
  "E:\CLAUDE_Workspace\Claude\Report_Files\Projects\Bulk_Vector_Clip_Utilties\Bulk_Vector_Clip\dist\gridtools" ^
  "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\gridtools"
```

> The folder in the plugins directory **must** be named `gridtools`. The
> modules import each other by that name.

## 3. Turn it on

1. Start QGIS (restart it if it was already open).
2. **Plugins → Manage and Install Plugins → Settings** → tick **Show also
   experimental plugins**. This plugin is marked experimental until it's been
   used on a real job.
3. **Installed** tab → tick **Grid Tools**.
4. Open the Processing Toolbox (`Ctrl+Alt+T`). You should see **Grid Tools →
   Sheets** with three entries.

If it doesn't appear, open **Plugins → Python Console** and look for an import
error — that's where QGIS reports a plugin that failed to load.

## 4. Test it

`sample_sites.gpkg` is in this folder. Drag it onto QGIS and add
**`site_boundary`** and **`corridor_site`**. Both are EPSG:3361 (South Carolina
State Plane, feet). Set the project CRS to match.

### Sheet count estimator

Run it on `site_boundary`, scales `1"=40',1"=60',1"=100'`, everything else
default (ARCH D landscape, 1" margins, 5% overlap).

**Expect:**

| Scale | Sheets |
|---|---|
| 1"=40' | 12 |
| 1"=60' | 8 |
| 1"=100' | 3 |

The log also prints the ground size of a sheet and the average fill.

### Atlas grid builder

Run it on `site_boundary` with everything at default (ARCH D, landscape,
1"=60').

**Expect 8 sheets**, `C-01` to `C-08`, each **2040 × 1320 ft** on the ground —
which is 22" × 34" of printable paper at 1"=60'. Matches the estimator exactly.

Label the layer by `sheet_id` so you can read the numbering on the map.

### Rotation — the one worth seeing

`corridor_site` is a 5000 × 500 ft strip running north-east at 35°.

1. Run the grid builder on it with **Rotation: None** → **7 sheets**, most of
   them mostly empty.
2. Run it again with **Rotation: Auto (line the sheets up with the site)** →
   **3 sheets**, and `map_rotation` comes out **35.02°**.

Less than half the paper for the same coverage. That's the case there's no
native answer for.

> When you use a rotated grid in a layout, bind the map item's rotation to
> `"map_rotation"` with a data-defined override, and give the north arrow a
> data-defined rotation of `-"map_rotation"` so it keeps pointing north.

### Renumber sheets

1. Save a grid to a GeoPackage (right-click the result → *Export → Save
   Features As*) and add it back — you want something editable that persists.
2. Toggle editing on. **Turn snapping off first**, or sheet corners will jump
   onto whatever is underneath.
3. Move a sheet with **Move Feature(s)**. Copy-paste one to add a sheet — it
   arrives the right size, which drawing one never does.
4. Run **Renumber sheets** on that same layer. It edits in place, so run it as
   often as you like.

Numbering, `grid_ref` and the four `nbr_*` neighbour fields all get rebuilt
from where the sheets now sit. Try the **Serpentine** order and a template like
`SD-{n:03d}` starting at 101 — you should get `SD-101` … `SD-108`.

To keep an id you typed yourself: add an integer field `locked`, put `1` in
that sheet, and point **Keep the existing id where this field is set** at it.

## Sheet sizes in EPSG:3361

At 1" margins, landscape, for reference:

| Paper | 1"=20' | 1"=40' | 1"=60' | 1"=100' |
|---|---|---|---|---|
| Letter (8.5×11) | 180 × 130 ft | 360 × 260 ft | 540 × 390 ft | 900 × 650 ft |
| Tabloid (11×17) | 300 × 180 ft | 600 × 360 ft | 900 × 540 ft | 1500 × 900 ft |
| ARCH D (24×36) | 680 × 440 ft | 1360 × 880 ft | 2040 × 1320 ft | 3400 × 2200 ft |

Scales parse however you write them: `1"=60'`, `1"=60`, `1 in = 60 ft` and
`1:720` all mean the same thing.

## Notes

- **This coexists with the full Field Kit plugin.** Its provider id is
  `gridtools`, not `fieldkit`, so if you install both you get both toolbox
  groups and no clash. The grid tools will simply appear twice.
- **Changing the code:** install the **Plugin Reloader** plugin, then reload
  Grid Tools after an edit — QGIS caches Python modules and won't pick up
  changes on its own. Remember edits here get overwritten next time the builder
  runs; make them in `fieldkit/` instead.
- **Uninstalling:** untick it in the plugin manager, then
  `rmdir "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\gridtools"`.
  Removing a junction does not touch the files it points at.

## If something goes wrong

| Symptom | Cause |
|---|---|
| Grid Tools not in the plugin list | Experimental plugins are hidden — tick the box in Settings |
| Ticked but no toolbox group | Import error; check the Python Console |
| "The coverage layer is in a geographic CRS" | Your layer is EPSG:4326. Reproject to 3361 — degrees make sheet sizes meaningless |
| "Margins ... leave nothing to print on" | Margin is in **millimetres**. 1 inch is 25.4 |
| Sheets come out the wrong size | Check the layer's CRS units, or force them with the advanced **Map units** parameter |
| Edits don't take effect | Reload the plugin, or restart QGIS |

Full documentation for all nine tools is in `docs/` in the repository, starting
with `docs/TRY-IT.md`.
