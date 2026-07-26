"""Sheet grids for an atlas: sized from the paper, culled, numbered."""

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterDistance,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsWkbTypes,
)

from ..core import gridmath, paper
from . import _grid

SIZE_MODE_LABELS = ["From paper size and scale", "Direct cell size"]
SIZE_PAPER, SIZE_DIRECT = 0, 1


class AtlasGridBuilder(QgsProcessingAlgorithm):
    """Coverage polygon in, numbered sheet grid out."""

    COVERAGE = "COVERAGE"
    BUFFER = "BUFFER"
    SIZE_MODE = "SIZE_MODE"
    PAPER = "PAPER"
    ORIENTATION = "ORIENTATION"
    MARGIN = "MARGIN"
    SCALE = "SCALE"
    CELL_WIDTH = "CELL_WIDTH"
    CELL_HEIGHT = "CELL_HEIGHT"
    UNITS = "UNITS"
    OVERLAP = "OVERLAP"
    ANCHOR = "ANCHOR"
    SNAP_TO = "SNAP_TO"
    ORIGIN_X = "ORIGIN_X"
    ORIGIN_Y = "ORIGIN_Y"
    ROTATION = "ROTATION"
    ANGLE = "ANGLE"
    CULL = "CULL"
    MIN_COVERAGE = "MIN_COVERAGE"
    ORDER = "ORDER"
    START_AT = "START_AT"
    TEMPLATE = "TEMPLATE"
    OUTPUT = "OUTPUT"

    def initAlgorithm(self, config=None):
        add = self.addParameter

        add(QgsProcessingParameterFeatureSource(
            self.COVERAGE, "Coverage area", [QgsProcessing.TypeVectorPolygon]))
        add(QgsProcessingParameterEnum(
            self.SIZE_MODE, "Sheet size from", SIZE_MODE_LABELS,
            defaultValue=SIZE_PAPER))
        add(QgsProcessingParameterEnum(
            self.PAPER, "Paper size", paper.PAPER_NAMES,
            defaultValue=paper.PAPER_NAMES.index("ARCH D (24x36)")))
        add(QgsProcessingParameterEnum(
            self.ORIENTATION, "Orientation", _grid.ORIENTATION_LABELS, defaultValue=0))
        add(QgsProcessingParameterString(
            self.SCALE, "Scale (1\"=50', 1:2000, ...)", defaultValue="1\"=50'"))
        add(QgsProcessingParameterNumber(
            self.MARGIN, "Margin around the map, in mm",
            QgsProcessingParameterNumber.Double, defaultValue=25.4, minValue=0.0))
        add(QgsProcessingParameterNumber(
            self.OVERLAP, "Overlap between sheets, % of sheet",
            QgsProcessingParameterNumber.Double, defaultValue=5.0,
            minValue=0.0, maxValue=49.0))
        add(QgsProcessingParameterEnum(
            self.ANCHOR, "Where the grid starts", _grid.ANCHOR_LABELS, defaultValue=0))
        add(QgsProcessingParameterEnum(
            self.ROTATION, "Rotation", _grid.ROTATION_LABELS, defaultValue=0))
        add(QgsProcessingParameterEnum(
            self.ORDER, "Sheet order", _grid.ORDER_LABELS, defaultValue=0))
        add(QgsProcessingParameterString(
            self.TEMPLATE, "Sheet id template", defaultValue="C-{n:02d}"))
        add(QgsProcessingParameterNumber(
            self.MIN_COVERAGE, "Drop sheets covering less than this % of the sheet",
            QgsProcessingParameterNumber.Double, defaultValue=0.5,
            minValue=0.0, maxValue=100.0))

        advanced = [
            QgsProcessingParameterDistance(
                self.BUFFER, "Pad the coverage first", defaultValue=0.0,
                parentParameterName=self.COVERAGE, minValue=0.0),
            QgsProcessingParameterDistance(
                self.CELL_WIDTH, "Cell width (direct mode)", defaultValue=0.0,
                parentParameterName=self.COVERAGE, minValue=0.0),
            QgsProcessingParameterDistance(
                self.CELL_HEIGHT, "Cell height (direct mode)", defaultValue=0.0,
                parentParameterName=self.COVERAGE, minValue=0.0),
            QgsProcessingParameterEnum(
                self.UNITS, "Map units", _grid.UNIT_LABELS, defaultValue=0),
            QgsProcessingParameterDistance(
                self.SNAP_TO, "Snap the grid origin to multiples of",
                defaultValue=100.0, parentParameterName=self.COVERAGE, minValue=0.0),
            QgsProcessingParameterNumber(
                self.ORIGIN_X, "Origin X", QgsProcessingParameterNumber.Double,
                defaultValue=0.0, optional=True),
            QgsProcessingParameterNumber(
                self.ORIGIN_Y, "Origin Y", QgsProcessingParameterNumber.Double,
                defaultValue=0.0, optional=True),
            QgsProcessingParameterNumber(
                self.ANGLE, "Angle, degrees clockwise",
                QgsProcessingParameterNumber.Double, defaultValue=0.0),
            QgsProcessingParameterNumber(
                self.START_AT, "First sheet number",
                QgsProcessingParameterNumber.Integer, defaultValue=1),
            QgsProcessingParameterBoolean(
                self.CULL, "Drop sheets with no coverage", defaultValue=True),
        ]
        for param in advanced:
            param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            add(param)

        add(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Sheets", QgsProcessing.TypeVectorPolygon))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.COVERAGE, context)
        if source is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.COVERAGE))

        crs = source.sourceCrs()
        units = _grid.metres_per_unit(
            crs, self.parameterAsEnum(parameters, self.UNITS, context))

        coverage = _grid.dissolved_coverage(
            source, self.parameterAsDouble(parameters, self.BUFFER, context))

        size_mode = self.parameterAsEnum(parameters, self.SIZE_MODE, context)
        denominator = None
        if size_mode == SIZE_PAPER:
            try:
                denominator = paper.parse_scale(
                    self.parameterAsString(parameters, self.SCALE, context))
                cell_w, cell_h = paper.sheet_size(
                    paper.PAPER_SIZES[
                        paper.PAPER_NAMES[
                            self.parameterAsEnum(parameters, self.PAPER, context)]],
                    self.parameterAsDouble(parameters, self.MARGIN, context),
                    denominator, units,
                    landscape=self.parameterAsEnum(
                        parameters, self.ORIENTATION, context) == 0,
                )
            except ValueError as exc:
                raise QgsProcessingException(str(exc))
        else:
            cell_w = self.parameterAsDouble(parameters, self.CELL_WIDTH, context)
            cell_h = self.parameterAsDouble(parameters, self.CELL_HEIGHT, context)
            if cell_w <= 0 or cell_h <= 0:
                raise QgsProcessingException(
                    "Direct mode needs a cell width and height greater than 0.")

        feedback.pushInfo("Sheet covers %.2f x %.2f map units." % (cell_w, cell_h))

        overlap_pct = self.parameterAsDouble(parameters, self.OVERLAP, context)
        overlap_x = cell_w * overlap_pct / 100.0
        overlap_y = cell_h * overlap_pct / 100.0

        anchor = _grid.anchor_for(self.parameterAsEnum(parameters, self.ANCHOR, context))
        theta, centre = _grid.alignment(
            coverage,
            self.parameterAsEnum(parameters, self.ROTATION, context),
            self.parameterAsDouble(parameters, self.ANGLE, context),
        )
        if theta:
            feedback.pushInfo("Sheets rotated; map rotation is %.3f degrees." % theta)

        try:
            grid, cells = _grid.build_cells(
                coverage, cell_w, cell_h, overlap_x, overlap_y, anchor,
                snap_to=self.parameterAsDouble(parameters, self.SNAP_TO, context),
                origin=(self.parameterAsDouble(parameters, self.ORIGIN_X, context),
                        self.parameterAsDouble(parameters, self.ORIGIN_Y, context)),
                theta=theta, centre=centre,
                cull=self.parameterAsBool(parameters, self.CULL, context),
                min_coverage_pct=self.parameterAsDouble(
                    parameters, self.MIN_COVERAGE, context),
                feedback=feedback,
            )
        except ValueError as exc:
            raise QgsProcessingException(str(exc))

        if not cells:
            raise QgsProcessingException(
                "No sheets survived. Check the coverage layer, or lower the minimum "
                "coverage percentage.")

        order = _grid.order_for(self.parameterAsEnum(parameters, self.ORDER, context))
        template = self.parameterAsString(parameters, self.TEMPLATE, context)
        start_at = self.parameterAsInt(parameters, self.START_AT, context)

        by_position = {(c["row"], c["col"]): c for c in cells}
        ordered = gridmath.order_cells(by_position.keys(), order)

        try:
            for number, position in enumerate(ordered, start=start_at):
                cell = by_position[position]
                cell["n"] = number
                cell["sheet_id"] = gridmath.format_sheet_id(
                    template, number, position[0], position[1],
                    nrows=grid["nrows"], ncols=grid["ncols"])
                cell["grid_ref"] = gridmath.format_sheet_id(
                    "{alpha_row}{col1}", number, position[0], position[1],
                    nrows=grid["nrows"], ncols=grid["ncols"])
        except ValueError as exc:
            raise QgsProcessingException(str(exc))

        fields = QgsFields()
        for name, kind in (
            ("sheet_no", QVariant.Int), ("sheet_id", QVariant.String),
            ("grid_ref", QVariant.String), ("row", QVariant.Int),
            ("col", QVariant.Int), ("center_x", QVariant.Double),
            ("center_y", QVariant.Double), ("map_rotation", QVariant.Double),
            ("scale", QVariant.Double), ("cov_pct", QVariant.Double),
            ("nbr_n", QVariant.String), ("nbr_s", QVariant.String),
            ("nbr_e", QVariant.String), ("nbr_w", QVariant.String),
        ):
            fields.append(QgsField(name, kind))

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields, QgsWkbTypes.Polygon, crs)
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        def neighbour(row, col):
            other = by_position.get((row, col))
            return other["sheet_id"] if other else None

        for position in ordered:
            if feedback.isCanceled():
                break
            cell = by_position[position]
            row, col = position
            centroid = cell["geometry"].centroid().asPoint()
            feature = QgsFeature(fields)
            feature.setGeometry(cell["geometry"])
            feature.setAttributes([
                cell["n"], cell["sheet_id"], cell["grid_ref"], row, col,
                centroid.x(), centroid.y(), theta, denominator, cell["cov_pct"],
                neighbour(row + 1, col), neighbour(row - 1, col),
                neighbour(row, col + 1), neighbour(row, col - 1),
            ])
            sink.addFeature(feature, QgsFeatureSink.FastInsert)

        feedback.pushInfo("%d sheet(s) written." % len(ordered))
        return {self.OUTPUT: dest_id}

    def name(self):
        return "atlasgridbuilder"

    def displayName(self):
        return "Atlas grid builder"

    def group(self):
        return "Sheets"

    def groupId(self):
        return "sheets"

    def shortHelpString(self):
        return (
            "<p>Turns a coverage polygon into a numbered sheet grid ready to drive "
            "an atlas.</p>"
            "<h3>Sheet size</h3>"
            "<p>Give it the paper and the scale and it works out the ground size: "
            "24x36 with 1\" margins at 1\"=50' is 1700 x 1100 feet. No arithmetic on "
            "the back of an envelope.</p>"
            "<h3>Where the grid starts</h3>"
            "<p><b>Centre on the coverage</b> is the default because a lower-left "
            "start leaves a nearly empty column hanging off the side. <b>Snap to a "
            "round coordinate</b> is the one to use on a live job: nudge the "
            "boundary next month and the sheets land in the same place instead of "
            "shifting a few feet and invalidating the printed set.</p>"
            "<h3>Rotation</h3>"
            "<p><b>Auto</b> lines the grid up with the site's own axis, which is "
            "worth several sheets on a diagonal corridor. The rotation is written "
            "to <i>map_rotation</i>; bind the layout map item's rotation to that "
            "field, and give the north arrow a data-defined rotation of "
            "<i>-map_rotation</i> so it keeps pointing north. Check the first "
            "rotated set by eye.</p>"
            "<h3>Attributes</h3>"
            "<p><i>sheet_id</i> is the atlas page name, <i>scale</i> and "
            "<i>map_rotation</i> drive the map item, <i>cov_pct</i> tells you which "
            "sheets are nearly empty, and <i>nbr_n/s/e/w</i> hold the neighbouring "
            "sheet ids for match-line callouts. Those are relative to the grid, so "
            "on a rotated grid \"north\" means grid north.</p>"
        )

    def createInstance(self):
        return AtlasGridBuilder()

    def tr(self, string):
        return QCoreApplication.translate("FieldKit", string)
