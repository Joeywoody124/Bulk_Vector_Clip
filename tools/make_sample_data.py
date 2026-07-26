"""Build the sample GeoPackage used by docs/TRY-IT.md.

Run with a python that has the QGIS bindings:

    QT_QPA_PLATFORM=offscreen python3 tools/make_sample_data.py

Everything is in EPSG:3361 (NAD83(HARN) / South Carolina, feet) and laid out
around a plausible State Plane origin. The faults in the data are deliberate
and are listed in docs/TRY-IT.md so you know what each tool should find.
"""

import os
import sys

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsVectorFileWriter,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

CRS = "EPSG:3361"
X0, Y0 = 2_000_000.0, 500_000.0
OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sample", "fieldkit_demo.gpkg",
)


def point(x, y):
    return QgsPointXY(X0 + x, Y0 + y)


def polygon(*corners):
    ring = [point(x, y) for x, y in corners]
    ring.append(ring[0])
    return QgsGeometry.fromPolygonXY([ring])


def box(x, y, width, height):
    return polygon((x, y), (x + width, y), (x + width, y + height), (x, y + height))


def line(*points):
    return QgsGeometry.fromPolylineXY([point(x, y) for x, y in points])


# ---------------------------------------------------------------------------
# The layers
# ---------------------------------------------------------------------------

def site_boundary():
    """An L-shaped site, 4000 x 3000 ft. Coverage for the sheet tools."""
    fields = [("name", QVariant.String)]
    geometry = polygon((0, 0), (4000, 0), (4000, 1200), (1500, 1200),
                       (1500, 3000), (0, 3000))
    return "site_boundary", QgsWkbTypes.Polygon, fields, [(geometry, ["Phase 1"])]


def road_centerline():
    """Two roads with a bend. row_width drives the data-defined ROW offsets."""
    fields = [("name", QVariant.String), ("row_width", QVariant.Double)]
    main = line((100, 600), (2600, 600), (3900, 1000))
    side = line((1200, 600), (1200, 2800))
    return "road_centerline", QgsWkbTypes.LineString, fields, [
        (main, ["Palmetto Way", 60.0]),
        (side, ["Live Oak Lane", 50.0]),
    ]


def parcels_with_gaps():
    """A 4 x 3 block of parcels, tiled exactly, with three deliberate faults.

    1. The parcel at column 1, row 1 is missing entirely - a 300,000 sf hole
       that must NOT be treated as a sliver.
    2. Column 3, row 1 is 3 ft narrow on its left - an enclosed sliver.
    3. Column 0, row 0 is 3 ft narrow on its right - a sliver open at the
       bottom edge of the block, which only the sliver-width setting finds.
    """
    fields = [("parcel_id", QVariant.String)]
    width, height = 600.0, 500.0
    features = []
    for col in range(4):
        for row in range(3):
            if (col, row) == (1, 1):
                continue  # the missing parcel
            x, y = col * width, row * height
            w = width
            if (col, row) == (3, 1):
                x += 3.0
                w -= 3.0  # enclosed sliver against column 2
            if (col, row) == (0, 0):
                w -= 3.0  # open-ended sliver against column 1
            features.append((box(x, y, w, height),
                             ["P-%d%02d" % (col, row)]))
    return "parcels_with_gaps", QgsWkbTypes.Polygon, fields, features


def parcels_with_overlaps():
    """Two overlapping pairs: one a 20 ft slab, one a 2 ft sliver."""
    fields = [("parcel_id", QVariant.String), ("survey_year", QVariant.Int)]
    return "parcels_with_overlaps", QgsWkbTypes.Polygon, fields, [
        (box(0, 2000, 500, 500), ["OV-A", 2018]),
        (box(480, 2000, 500, 500), ["OV-B", 2024]),   # 20 ft x 500 overlap
        (box(1100, 2000, 500, 500), ["OV-C", 2021]),
        (box(1598, 2000, 500, 500), ["OV-D", 2015]),  # 2 ft x 500 sliver
    ]


def storm_pipes():
    """A trunk and four laterals. Two stop short, one is fine, one is far off."""
    fields = [("pipe_id", QVariant.String), ("size_in", QVariant.Int)]
    return "storm_pipes", QgsWkbTypes.LineString, fields, [
        (line((200, 250), (3800, 250)), ["TRUNK", 36]),
        (line((800, 900), (800, 255)), ["LAT-1", 18]),    # 5 ft short
        (line((1600, 900), (1600, 262)), ["LAT-2", 15]),  # 12 ft short
        (line((2400, 900), (2400, 250)), ["LAT-3", 18]),  # connected
        (line((3200, 900), (3200, 320)), ["LAT-4", 12]),  # 70 ft short
    ]


def survey_parcels():
    """The good version of a boundary - the reference for snapping."""
    fields = [("source", QVariant.String)]
    return "survey_parcels", QgsWkbTypes.Polygon, fields, [
        (box(2600, 2000, 700, 600), ["Boundary survey 2024"]),
    ]


def field_sketch():
    """The same boundary, digitised by eye: every corner is 1-4 ft out."""
    fields = [("source", QVariant.String)]
    sloppy = polygon((2602, 2003), (3304, 2001), (3299, 2604), (2597, 2598))
    return "field_sketch", QgsWkbTypes.Polygon, fields, [
        (sloppy, ["Traced from aerial"]),
    ]


LAYERS = [
    site_boundary, road_centerline, parcels_with_gaps, parcels_with_overlaps,
    storm_pipes, survey_parcels, field_sketch,
]


def write():
    crs = QgsCoordinateReferenceSystem(CRS)
    if not crs.isValid():
        raise SystemExit("EPSG:3361 is not available in this PROJ install")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)

    transform_context = QgsCoordinateTransformContext()
    first = True
    for builder in LAYERS:
        name, wkb_type, field_defs, rows = builder()

        fields = QgsFields()
        for field_name, field_type in field_defs:
            fields.append(QgsField(field_name, field_type))

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = name
        options.fileEncoding = "UTF-8"
        options.actionOnExistingFile = (
            QgsVectorFileWriter.CreateOrOverwriteFile if first
            else QgsVectorFileWriter.CreateOrOverwriteLayer
        )

        writer = QgsVectorFileWriter.create(
            OUT, fields, wkb_type, crs, transform_context, options)
        if writer.hasError() != QgsVectorFileWriter.NoError:
            raise SystemExit("%s: %s" % (name, writer.errorMessage()))

        for geometry, attributes in rows:
            feature = QgsFeature(fields)
            feature.setGeometry(geometry)
            feature.setAttributes(attributes)
            writer.addFeature(feature)
        del writer
        first = False
        print("  %-24s %d feature(s)" % (name, len(rows)))

    print("\nWrote %s" % OUT)


def main():
    QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", "/usr"), True)
    app = QgsApplication([], False)
    app.initQgis()
    write()
    app.exitQgis()
    return 0


if __name__ == "__main__":
    sys.exit(main())
