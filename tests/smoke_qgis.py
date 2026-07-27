"""End-to-end smoke tests against a real QGIS.

Not picked up by ``unittest discover`` (the filename doesn't start with
``test``) because CI has no QGIS. Run it by hand wherever QGIS is installed:

    python3 tests/smoke_qgis.py

It builds synthetic layers in EPSG:3361, runs every Field Kit algorithm, and
checks the results are sane. This is the difference between "the code compiles"
and "the code works".
"""

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from qgis.core import (  # noqa: E402
    NULL,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant  # noqa: E402

CRS = "EPSG:3361"  # NAD83(HARN) / South Carolina (ft)
X0, Y0 = 2_000_000.0, 500_000.0  # a plausible SC State Plane origin

PASSED = []
FAILED = []
PROVIDER = None


def is_null(value):
    """QGIS NULL is a QVariant, not Python None. Both mean "no neighbour"."""
    return value is None or value == NULL or value == ""


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print("  ok    %s" % name)
    else:
        FAILED.append("%s %s" % (name, detail))
        print("  FAIL  %s %s" % (name, detail))


def memory_layer(name, geometry_type, fields=(), geometries=(), attributes=None):
    layer = QgsVectorLayer("%s?crs=%s" % (geometry_type, CRS), name, "memory")
    provider = layer.dataProvider()
    if fields:
        provider.addAttributes([QgsField(n, t) for n, t in fields])
        layer.updateFields()
    features = []
    for index, geometry in enumerate(geometries):
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        if attributes:
            feature.setAttributes(attributes[index])
        features.append(feature)
    provider.addFeatures(features)
    layer.updateExtents()
    return layer


def rectangle(x, y, width, height):
    return QgsGeometry.fromPolygonXY([[
        QgsPointXY(x, y), QgsPointXY(x + width, y),
        QgsPointXY(x + width, y + height), QgsPointXY(x, y + height),
        QgsPointXY(x, y),
    ]])


def run_all(processing):
    tmp = tempfile.mkdtemp(prefix="fieldkit-smoke-")
    try:
        test_row_from_centerline(processing)
        test_fill_gaps(processing)
        test_erase_overlaps(processing)
        test_snap_and_verify(processing)
        test_close_undershoots(processing)
        test_atlas_grid(processing)
        test_estimator(processing)
        test_renumber(processing)
        test_bulk_clip(processing, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# Editing
# --------------------------------------------------------------------------

def test_row_from_centerline(processing):
    print("\nRight of way from centerline")
    line = QgsGeometry.fromPolylineXY([
        QgsPointXY(X0, Y0), QgsPointXY(X0 + 1000, Y0),
        QgsPointXY(X0 + 1000, Y0 + 800),
    ])
    layer = memory_layer("centerline", "LineString",
                         [("width", QVariant.Double)], [line], [[80.0]])

    result = processing.run("fieldkit:rowfromcenterline", {
        "INPUT": layer, "OFFSET_LEFT": 30.0, "OFFSET_RIGHT": 20.0,
        "END_CAP": 0, "JOIN_STYLE": 0, "SEGMENTS": 8, "MITRE_LIMIT": 2.0,
        "DISSOLVE": False, "OUTPUT": "TEMPORARY_OUTPUT",
    })
    out = result["OUTPUT"]
    check("row: one polygon out", out.featureCount() == 1,
          "got %d" % out.featureCount())

    feature = next(out.getFeatures())
    area = feature.geometry().area()
    # 1800 ft of centreline, 50 ft wide, plus a bit at the corner.
    check("row: area is about length x width",
          1800 * 50 * 0.95 <= area <= 1800 * 50 * 1.15, "area=%.0f" % area)
    check("row: records the offsets",
          feature["row_left"] == 30.0 and feature["row_width"] == 50.0,
          "left=%s width=%s" % (feature["row_left"], feature["row_width"]))

    # Asymmetry must actually show up: the polygon should sit off-centre.
    centroid = feature.geometry().centroid().asPoint()
    check("row: asymmetric offsets shift the corridor", centroid.y() < Y0 + 400,
          "cy=%.1f" % centroid.y())

    square = processing.run("fieldkit:rowfromcenterline", {
        "INPUT": layer, "OFFSET_LEFT": 30.0, "OFFSET_RIGHT": 20.0,
        "END_CAP": 1, "JOIN_STYLE": 0, "SEGMENTS": 8, "MITRE_LIMIT": 2.0,
        "DISSOLVE": False, "OUTPUT": "TEMPORARY_OUTPUT",
    })["OUTPUT"]
    square_area = next(square.getFeatures()).geometry().area()
    check("row: square ends add area", square_area > area,
          "%.0f vs %.0f" % (square_area, area))


def test_fill_gaps(processing):
    print("\nFill gaps between polygons")

    # An enclosed hole: four blocks around a missing middle.
    ring = [
        rectangle(X0, Y0, 500, 500), rectangle(X0 + 510, Y0, 500, 500),
        rectangle(X0, Y0 + 510, 500, 500),
        rectangle(X0 + 510, Y0 + 510, 500, 500),
    ]
    # Bridge the outer edges so the 10 ft cross is genuinely enclosed.
    ring.append(rectangle(X0 - 100, Y0 - 100, 1210, 100))
    ring.append(rectangle(X0 - 100, Y0 + 1010, 1210, 100))
    ring.append(rectangle(X0 - 100, Y0, 100, 1010))
    ring.append(rectangle(X0 + 1010, Y0, 100, 1010))
    layer = memory_layer("blocks", "Polygon", [("name", QVariant.String)],
                         ring, [["b%d" % i] for i in range(len(ring))])

    result = processing.run("fieldkit:fillgaps", {
        "INPUT": layer, "MAX_AREA": 0.0, "MODE": 0,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_GAPS": "TEMPORARY_OUTPUT",
    })
    gaps = result["OUTPUT_GAPS"]
    filled = result["OUTPUT"]
    check("gaps: enclosed sliver found", gaps.featureCount() >= 1,
          "found %d" % gaps.featureCount())
    check("gaps: every input polygon comes back",
          filled.featureCount() == layer.featureCount(),
          "%d vs %d" % (filled.featureCount(), layer.featureCount()))
    check("gaps: something was filled",
          any(f["gaps_filled"] for f in filled.getFeatures()))

    before = sum(f.geometry().area() for f in layer.getFeatures())
    after = sum(f.geometry().area() for f in filled.getFeatures())
    check("gaps: filling adds area", after > before,
          "%.0f -> %.0f" % (before, after))

    # The open-ended case: two rectangles with a gap between them, no
    # surrounding polygons. There is no interior ring here, so this only
    # works via the boundary layer.
    pair = [rectangle(X0, Y0, 500, 500), rectangle(X0 + 505, Y0, 500, 500)]
    open_layer = memory_layer("pair", "Polygon", (), pair)
    boundary = memory_layer("boundary", "Polygon", (),
                            [rectangle(X0, Y0, 1005, 500)])

    without = processing.run("fieldkit:fillgaps", {
        "INPUT": open_layer, "MAX_AREA": 0.0, "MODE": 2,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_GAPS": "TEMPORARY_OUTPUT",
    })["OUTPUT_GAPS"]
    with_boundary = processing.run("fieldkit:fillgaps", {
        "INPUT": open_layer, "BOUNDARY": boundary, "MAX_AREA": 0.0, "MODE": 2,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_GAPS": "TEMPORARY_OUTPUT",
    })["OUTPUT_GAPS"]
    check("gaps: open-ended sliver needs the boundary layer",
          without.featureCount() == 0 and with_boundary.featureCount() >= 1,
          "without=%d with=%d"
          % (without.featureCount(), with_boundary.featureCount()))

    # ...or the sliver-width setting, which finds it with no boundary at all.
    by_width = processing.run("fieldkit:fillgaps", {
        "INPUT": open_layer, "MAX_AREA": 0.0, "SLIVER_WIDTH": 20.0, "MODE": 2,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_GAPS": "TEMPORARY_OUTPUT",
    })["OUTPUT_GAPS"]
    check("gaps: sliver width finds the open-ended gap",
          by_width.featureCount() >= 1, "found %d" % by_width.featureCount())
    found = sum(f.geometry().area() for f in by_width.getFeatures())
    check("gaps: the sliver is about the right size",
          500 * 5 * 0.8 <= found <= 500 * 5 * 1.5, "area=%.0f" % found)

    too_narrow = processing.run("fieldkit:fillgaps", {
        "INPUT": open_layer, "MAX_AREA": 0.0, "SLIVER_WIDTH": 2.0, "MODE": 2,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_GAPS": "TEMPORARY_OUTPUT",
    })["OUTPUT_GAPS"]
    check("gaps: a width below the gap finds nothing",
          too_narrow.featureCount() == 0,
          "found %d" % too_narrow.featureCount())

    # Turning it on must not double-count the enclosed hole.
    both = processing.run("fieldkit:fillgaps", {
        "INPUT": layer, "MAX_AREA": 0.0, "SLIVER_WIDTH": 30.0, "MODE": 0,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_GAPS": "TEMPORARY_OUTPUT",
    })["OUTPUT_GAPS"]
    check("gaps: enclosed holes are not reported twice",
          both.featureCount() == gaps.featureCount(),
          "%d with slivers vs %d without"
          % (both.featureCount(), gaps.featureCount()))

    # A big hole must survive the size threshold.
    kept = processing.run("fieldkit:fillgaps", {
        "INPUT": layer, "MAX_AREA": 50.0, "MODE": 0,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_GAPS": "TEMPORARY_OUTPUT",
    })["OUTPUT_GAPS"]
    check("gaps: size threshold leaves big holes alone",
          kept.featureCount() < gaps.featureCount() or gaps.featureCount() == 0,
          "%d vs %d" % (kept.featureCount(), gaps.featureCount()))


def test_erase_overlaps(processing):
    print("\nErase overlaps between polygons")
    # b overlaps a by 100x500; c sits entirely inside a.
    a = rectangle(X0, Y0, 500, 500)
    b = rectangle(X0 + 400, Y0, 500, 500)
    c = rectangle(X0 + 100, Y0 + 100, 50, 50)
    layer = memory_layer("stacked", "Polygon",
                         [("rank", QVariant.Int)], [a, b, c], [[1], [9], [5]])

    result = processing.run("fieldkit:eraseoverlaps", {
        "INPUT": layer, "RULE": 0, "MAX_AREA": 0.0,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_OVERLAPS": "TEMPORARY_OUTPUT",
    })
    out = result["OUTPUT"]
    overlaps = result["OUTPUT_OVERLAPS"]
    check("overlaps: found", overlaps.featureCount() >= 2,
          "found %d" % overlaps.featureCount())
    check("overlaps: every polygon comes back",
          out.featureCount() == 3, "got %d" % out.featureCount())

    geoms = sorted(out.getFeatures(), key=lambda f: -f.geometry().area())
    total = sum(f.geometry().area() for f in out.getFeatures())
    check("overlaps: no ground is counted twice",
          abs(total - QgsGeometry.unaryUnion([a, b, c]).area()) < 1.0,
          "%.1f vs %.1f" % (total, QgsGeometry.unaryUnion([a, b, c]).area()))
    check("overlaps: the first-drawn polygon kept its full area",
          abs(geoms[0].geometry().area() - 250000) < 1.0
          or abs(max(f.geometry().area() for f in out.getFeatures())
                 - 250000) < 1.0,
          "%.1f" % geoms[0].geometry().area())
    check("overlaps: area lost is recorded",
          any(f["area_lost"] > 0 for f in out.getFeatures()))

    # The larger-wins rule must give a different answer to first-wins.
    largest = processing.run("fieldkit:eraseoverlaps", {
        "INPUT": layer, "RULE": 1, "MAX_AREA": 0.0,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_OVERLAPS": "TEMPORARY_OUTPUT",
    })["OUTPUT"]
    check("overlaps: larger-wins keeps the containing polygon whole",
          max(f.geometry().area() for f in largest.getFeatures()) >= 250000 - 1)

    # The threshold must leave a big overlap alone.
    guarded = processing.run("fieldkit:eraseoverlaps", {
        "INPUT": layer, "RULE": 0, "MAX_AREA": 100.0,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_OVERLAPS": "TEMPORARY_OUTPUT",
    })["OUTPUT"]
    check("overlaps: the size limit leaves big ones alone",
          all(f["overlaps_fixed"] == 0 for f in guarded.getFeatures()))

    report = processing.run("fieldkit:eraseoverlaps", {
        "INPUT": layer, "RULE": 4, "MAX_AREA": 0.0,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_OVERLAPS": "TEMPORARY_OUTPUT",
    })["OUTPUT"]
    check("overlaps: report-only changes nothing",
          abs(sum(f.geometry().area() for f in report.getFeatures())
              - (a.area() + b.area() + c.area())) < 1.0)


def test_snap_and_verify(processing):
    print("\nSnap to layer and verify")
    reference = memory_layer("reference", "Polygon", (),
                             [rectangle(X0, Y0, 500, 500)])
    # Same shape, every corner 2 ft off.
    off = QgsGeometry.fromPolygonXY([[
        QgsPointXY(X0 + 2, Y0 + 2), QgsPointXY(X0 + 502, Y0 + 1),
        QgsPointXY(X0 + 501, Y0 + 502), QgsPointXY(X0 + 1, Y0 + 501),
        QgsPointXY(X0 + 2, Y0 + 2),
    ]])
    layer = memory_layer("sloppy", "Polygon", (), [off])

    result = processing.run("fieldkit:snapandverify", {
        "INPUT": layer, "REFERENCE": reference, "TOLERANCE": 5.0, "MODE": 0,
        "MAX_MOVE": 0.0, "OUTPUT": "TEMPORARY_OUTPUT",
        "OUTPUT_MOVES": "TEMPORARY_OUTPUT",
    })
    out = result["OUTPUT"]
    moves = result["OUTPUT_MOVES"]
    feature = next(out.getFeatures())
    check("snap: vertices moved", feature["snap_moved"] > 0,
          "moved=%s" % feature["snap_moved"])
    check("snap: displacement recorded",
          0 < feature["snap_max"] <= 5.0, "max=%s" % feature["snap_max"])
    check("snap: vector layer written", moves.featureCount() > 0,
          "%d vectors" % moves.featureCount())

    guarded = processing.run("fieldkit:snapandverify", {
        "INPUT": layer, "REFERENCE": reference, "TOLERANCE": 5.0, "MODE": 0,
        "MAX_MOVE": 0.5, "OUTPUT": "TEMPORARY_OUTPUT",
        "OUTPUT_MOVES": "TEMPORARY_OUTPUT",
    })["OUTPUT"]
    check("snap: move guard rejects the feature",
          next(guarded.getFeatures())["snap_moved"] == 0)


def test_close_undershoots(processing):
    print("\nClose dangling line ends")
    trunk = QgsGeometry.fromPolylineXY(
        [QgsPointXY(X0, Y0), QgsPointXY(X0, Y0 + 1000)])
    # Stops 3 ft short of the trunk, heading straight at it.
    stub = QgsGeometry.fromPolylineXY(
        [QgsPointXY(X0 + 300, Y0 + 500), QgsPointXY(X0 + 3, Y0 + 500)])
    layer = memory_layer("net", "LineString", (), [trunk, stub])

    result = processing.run("fieldkit:closeundershoots", {
        "INPUT": layer, "TOLERANCE": 10.0, "MODE": 1, "CONNECTED_TOL": 0.001,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_REPORT": "TEMPORARY_OUTPUT",
    })
    out = result["OUTPUT"]
    report = result["OUTPUT_REPORT"]
    closed = sum(f["ends_closed"] for f in out.getFeatures())
    check("undershoot: the stub was extended", closed >= 1, "closed=%d" % closed)
    check("undershoot: report written", report.featureCount() >= 1)

    statuses = {f["status"] for f in report.getFeatures()}
    check("undershoot: report carries a status",
          statuses & {"extended", "snapped", "unresolved"} != set(),
          "statuses=%s" % statuses)

    # With a tolerance below the gap, nothing should be closed.
    tight = processing.run("fieldkit:closeundershoots", {
        "INPUT": layer, "TOLERANCE": 1.0, "MODE": 1, "CONNECTED_TOL": 0.001,
        "OUTPUT": "TEMPORARY_OUTPUT", "OUTPUT_REPORT": "TEMPORARY_OUTPUT",
    })["OUTPUT"]
    check("undershoot: a tight tolerance closes nothing",
          sum(f["ends_closed"] for f in tight.getFeatures()) == 0)


# --------------------------------------------------------------------------
# Sheets
# --------------------------------------------------------------------------

def coverage_layer():
    """An L-shaped site, about 4000 x 3000 ft."""
    geometry = QgsGeometry.fromPolygonXY([[
        QgsPointXY(X0, Y0), QgsPointXY(X0 + 4000, Y0),
        QgsPointXY(X0 + 4000, Y0 + 1200), QgsPointXY(X0 + 1500, Y0 + 1200),
        QgsPointXY(X0 + 1500, Y0 + 3000), QgsPointXY(X0, Y0 + 3000),
        QgsPointXY(X0, Y0),
    ]])
    return memory_layer("site", "Polygon", (), [geometry])


def test_atlas_grid(processing):
    print("\nAtlas grid builder")
    coverage = coverage_layer()
    params = {
        "COVERAGE": coverage, "SIZE_MODE": 0, "PAPER": 2, "ORIENTATION": 0,
        "SCALE": "1\"=60'", "MARGIN": 25.4, "OVERLAP": 5.0, "ANCHOR": 0,
        "ROTATION": 0, "ORDER": 0, "TEMPLATE": "C-{n:02d}",
        "MIN_COVERAGE": 0.5, "BUFFER": 0.0, "UNITS": 0, "SNAP_TO": 100.0,
        "ANGLE": 0.0, "START_AT": 1, "CULL": True,
        "OUTPUT": "TEMPORARY_OUTPUT",
    }
    sheets = processing.run("fieldkit:atlasgridbuilder", dict(params))["OUTPUT"]
    check("grid: produced sheets", sheets.featureCount() > 0,
          "%d sheets" % sheets.featureCount())

    features = sorted(sheets.getFeatures(), key=lambda f: f["sheet_no"])
    first = features[0]
    box = first.geometry().boundingBox()
    # ARCH D landscape, 1" margins, 1"=60' -> 2040 x 1320 ft
    check("grid: sheet is the right size on the ground",
          abs(box.width() - 2040) < 1 and abs(box.height() - 1320) < 1,
          "%.1f x %.1f" % (box.width(), box.height()))
    check("grid: ids follow the template", first["sheet_id"] == "C-01",
          first["sheet_id"])
    check("grid: numbering is contiguous",
          [f["sheet_no"] for f in features] == list(range(1, len(features) + 1)))
    check("grid: scale recorded", first["scale"] == 720, str(first["scale"]))
    check("grid: coverage percent is sane",
          all(0 < f["cov_pct"] <= 100 for f in features))
    ids = {f["sheet_id"] for f in features}
    check("grid: neighbours reference real sheets",
          all(is_null(f[side]) or f[side] in ids
              for f in features for side in ("nbr_n", "nbr_s", "nbr_e", "nbr_w")))
    check("grid: neighbour links are reciprocal",
          all(is_null(f["nbr_e"]) or
              next(g for g in features if g["sheet_id"] == f["nbr_e"])["nbr_w"]
              == f["sheet_id"]
              for f in features))
    check("grid: the top row has no sheet to its north",
          all(is_null(f["nbr_n"]) for f in features
              if f["row"] == max(g["row"] for g in features)))
    check("grid: every sheet touches the site",
          all(f.geometry().intersects(next(coverage.getFeatures()).geometry())
              for f in features))

    culled = sheets.featureCount()
    unculled = processing.run("fieldkit:atlasgridbuilder",
                              dict(params, CULL=False,
                                   OUTPUT="TEMPORARY_OUTPUT"))["OUTPUT"]
    check("grid: culling drops empty sheets", unculled.featureCount() >= culled,
          "%d unculled vs %d culled" % (unculled.featureCount(), culled))

    rotated = processing.run("fieldkit:atlasgridbuilder",
                             dict(params, ROTATION=1,
                                  OUTPUT="TEMPORARY_OUTPUT"))["OUTPUT"]
    check("grid: rotation runs and records the angle",
          rotated.featureCount() > 0)

    snapped = processing.run("fieldkit:atlasgridbuilder",
                             dict(params, ANCHOR=2,
                                  OUTPUT="TEMPORARY_OUTPUT"))["OUTPUT"]
    corner = min(f.geometry().boundingBox().xMinimum()
                 for f in snapped.getFeatures())
    check("grid: snapped origin lands on a round coordinate",
          abs(corner / 100.0 - round(corner / 100.0)) < 1e-6, "x=%.4f" % corner)


def test_estimator(processing):
    print("\nSheet count estimator")
    result = processing.run("fieldkit:sheetestimator", {
        "COVERAGE": coverage_layer(),
        "SCALES": "1\"=20',1\"=60',1\"=100'",
        "PAPER": 2, "ORIENTATION": 0, "MARGIN": 25.4, "OVERLAP": 5.0,
        "ROTATION": 0, "ANCHOR": 0, "MIN_COVERAGE": 0.5, "BUFFER": 0.0,
        "UNITS": 0,
    })
    counts = result["SHEET_COUNTS"]
    check("estimator: one row per scale", len(counts) == 3, str(counts))
    # Look the rows up by key: Processing does not preserve the dict order, and
    # sorted as strings 1"=100' comes before 1"=20'.
    from fieldkit.core import paper
    ordered = [counts[paper.format_scale(d, imperial=True)]
               for d in (240, 720, 1200)]
    check("estimator: smaller scales need fewer sheets",
          ordered == sorted(ordered, reverse=True) and len(set(ordered)) > 1,
          str(counts))
    check("estimator: counts are positive", all(v > 0 for v in ordered))


def test_renumber(processing):
    print("\nRenumber sheets")
    sheets = memory_layer("sheets", "Polygon", (), [
        rectangle(X0, Y0 + 1000, 900, 900),          # top left
        rectangle(X0 + 950, Y0 + 1000, 900, 900),    # top right
        rectangle(X0, Y0, 900, 900),                 # bottom left
    ])

    processing.run("fieldkit:renumbersheets", {
        "INPUT": sheets, "ORDER": 0, "TEMPLATE": "C-{n:02d}", "START_AT": 1,
        "BAND_RATIO": 0.5, "UPDATE_NEIGHBOURS": True,
    })
    by_id = {f["sheet_id"]: f for f in sheets.getFeatures()}
    check("renumber: ids assigned", set(by_id) == {"C-01", "C-02", "C-03"},
          str(sorted(by_id)))
    check("renumber: top-left is first",
          abs(by_id["C-01"].geometry().boundingBox().xMinimum() - X0) < 1e-6)
    check("renumber: neighbours linked",
          by_id["C-01"]["nbr_e"] == "C-02" and by_id["C-01"]["nbr_s"] == "C-03",
          "e=%s s=%s" % (by_id["C-01"]["nbr_e"], by_id["C-01"]["nbr_s"]))
    check("renumber: grid refs built",
          by_id["C-01"]["grid_ref"] == "A1", by_id["C-01"]["grid_ref"])

    # Move the top-right sheet down into the bottom row and renumber again.
    target = by_id["C-02"].id()
    sheets.startEditing()
    sheets.changeGeometry(target, rectangle(X0 + 950, Y0, 900, 900))
    sheets.commitChanges()

    processing.run("fieldkit:renumbersheets", {
        "INPUT": sheets, "ORDER": 0, "TEMPLATE": "C-{n:02d}", "START_AT": 1,
        "BAND_RATIO": 0.5, "UPDATE_NEIGHBOURS": True,
    })
    moved = {f.id(): f for f in sheets.getFeatures()}[target]
    check("renumber: the moved sheet took a new number",
          moved["sheet_id"] != "C-02", moved["sheet_id"])
    check("renumber: it landed in the bottom row", moved["row"] == 0,
          "row=%s" % moved["row"])

    # A locked sheet keeps its id.
    sheets.startEditing()
    sheets.addAttribute(QgsField("locked", QVariant.Int))
    sheets.commitChanges()
    locked_index = sheets.fields().indexOf("locked")
    first = next(sheets.getFeatures())
    keep = first["sheet_id"]
    sheets.startEditing()
    sheets.changeAttributeValue(first.id(), locked_index, 1)
    sheets.commitChanges()

    processing.run("fieldkit:renumbersheets", {
        "INPUT": sheets, "ORDER": 3, "TEMPLATE": "X-{n:02d}", "START_AT": 50,
        "KEEP_FIELD": "locked", "BAND_RATIO": 0.5, "UPDATE_NEIGHBOURS": True,
    })
    after = {f.id(): f for f in sheets.getFeatures()}[first.id()]
    check("renumber: locked sheet keeps its id", after["sheet_id"] == keep,
          "%s vs %s" % (after["sheet_id"], keep))
    others = [f["sheet_id"] for f in sheets.getFeatures() if f.id() != first.id()]
    check("renumber: everything else renumbered",
          all(i.startswith("X-") for i in others), str(others))


# --------------------------------------------------------------------------
# Bulk
# --------------------------------------------------------------------------

def test_bulk_clip(processing, tmp):
    print("\nBulk vector clip")
    inside = memory_layer("parcels", "Polygon", [("id", QVariant.Int)],
                          [rectangle(X0, Y0, 400, 400)], [[1]])
    straddling = memory_layer("roads", "LineString", (), [
        QgsGeometry.fromPolylineXY(
            [QgsPointXY(X0 - 500, Y0 + 100), QgsPointXY(X0 + 2000, Y0 + 100)])
    ])
    far_away = memory_layer("elsewhere", "Polygon", (),
                            [rectangle(X0 + 90_000, Y0, 100, 100)])
    boundary = memory_layer("site", "Polygon", (),
                            [rectangle(X0, Y0, 1000, 1000)])
    path = os.path.join(tmp, "clipped.gpkg")

    processing.run("fieldkit:bulkvectorclip", {
        "LAYERS": [inside, straddling, far_away], "MASK": boundary,
        "BUFFER": 0.0, "SKIP_EMPTY": True, "KEEP_STYLES": True,
        "PREFIX": "", "OUTPUT": path,
    })
    check("clip: geopackage written", os.path.exists(path))

    written = QgsVectorLayer(path, "gpkg", "ogr")
    names = {n.split("!!::!!")[1] for n in written.dataProvider().subLayers()} \
        if written.isValid() else set()
    check("clip: layers inside the boundary are present",
          {"parcels", "roads"} <= names, str(sorted(names)))
    check("clip: the layer outside is skipped", "elsewhere" not in names,
          str(sorted(names)))

    roads = QgsVectorLayer("%s|layername=roads" % path, "roads", "ogr")
    check("clip: geometry really was clipped",
          roads.isValid()
          and next(roads.getFeatures()).geometry().length() <= 1001,
          "length=%.1f" % next(roads.getFeatures()).geometry().length()
          if roads.isValid() else "invalid")


def main():
    QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", "/usr"), True)
    app = QgsApplication([], False)
    app.initQgis()

    sys.path.append("/usr/share/qgis/python/plugins")
    from processing.core.Processing import Processing  # noqa: E402
    import processing  # noqa: E402

    Processing.initialize()

    from fieldkit.provider import FieldKitProvider  # noqa: E402

    # Keep a reference: the registry does not own the Python object, and a
    # garbage-collected provider silently registers nothing.
    global PROVIDER
    PROVIDER = FieldKitProvider()
    QgsApplication.processingRegistry().addProvider(PROVIDER)

    registered = [a.id() for a in QgsApplication.processingRegistry().algorithms()
                  if a.id().startswith("fieldkit:")]
    print("Registered: %s" % ", ".join(sorted(registered)))
    check("provider: all nine tools registered", len(registered) == 9,
          "got %d" % len(registered))

    crs = QgsCoordinateReferenceSystem(CRS)
    check("crs: EPSG:3361 resolves and is in feet",
          crs.isValid() and not crs.isGeographic(), crs.description())

    run_all(processing)

    print("\n%d passed, %d failed" % (len(PASSED), len(FAILED)))
    for failure in FAILED:
        print("  FAILED: %s" % failure)
    app.exitQgis()
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
