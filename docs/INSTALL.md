# Installing Field Kit

> Just want to try it? [`TRY-IT.md`](TRY-IT.md) walks through installing and
> then running every tool on the sample data, with the numbers you should get.
> This page is the reference for the details.

Targets QGIS 3.34 or newer; developed against 3.40. No third-party Python
packages - everything it uses ships with QGIS.

## Option 1: symlink the folder (best while it is changing)

Clone the repo somewhere permanent, then link `fieldkit/` into your QGIS
plugins folder. Edits to the code show up in QGIS after a plugin reload
(install **Plugin Reloader** if you are going to be changing tools).

**Linux**

```bash
git clone https://github.com/Joeywoody124/Bulk_Vector_Clip.git ~/src/Bulk_Vector_Clip
ln -s ~/src/Bulk_Vector_Clip/fieldkit \
  ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/fieldkit
```

**Windows** (PowerShell as administrator)

```powershell
git clone https://github.com/Joeywoody124/Bulk_Vector_Clip.git C:\src\Bulk_Vector_Clip
New-Item -ItemType SymbolicLink `
  -Path "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins\fieldkit" `
  -Target "C:\src\Bulk_Vector_Clip\fieldkit"
```

**macOS**

```bash
ln -s ~/src/Bulk_Vector_Clip/fieldkit \
  ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/fieldkit
```

Then restart QGIS and tick **Field Kit** in *Plugins → Manage and Install
Plugins → Installed*. The tools appear in the Processing Toolbox under
**Field Kit**, in three groups: Editing, Sheets, Bulk.

The folder must be named `fieldkit` - the modules import each other by that
name.

## Option 2: install a zip

```bash
cd Bulk_Vector_Clip
zip -r fieldkit.zip fieldkit -x '*__pycache__*'
```

Then *Plugins → Manage and Install Plugins → Install from ZIP*. Fine for
handing it to a coworker; awkward while you are still editing tools.

## Where things live

| Path | What |
|---|---|
| `fieldkit/algs/` | One file per tool. Open, edit, reload. |
| `fieldkit/core/` | The maths, with no QGIS imports, so it can be tested. |
| `tests/` | Runs with plain `python -m unittest discover -s tests`. |

## Customizing

Changing a default is a one-line edit. Sheet sizes and the unit table are in
`fieldkit/core/paper.py`; ordering and label rules in
`fieldkit/core/gridmath.py`; every tool's parameters and defaults are in its
own file under `fieldkit/algs/`.

If you change anything in `core/`, run the tests before trusting it:

```bash
python -m unittest discover -s tests
```

## Using the tools without the UI

Everything is a Processing algorithm, so it also works from the Python
console, in a Model, and in the Batch dialog:

```python
processing.run("fieldkit:rowfromcenterline", {
    "INPUT": "roads",
    "OFFSET_LEFT": 30,
    "OFFSET_RIGHT": 30,
    "END_CAP": 0,
    "OUTPUT": "TEMPORARY_OUTPUT",
})
```

Right-click any tool in the toolbox and choose *Copy as Python command* to get
the exact call with your current settings filled in.
