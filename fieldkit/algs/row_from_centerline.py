"""Right-of-way polygons from a centerline, with independent left/right offsets."""

import math

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
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
    QgsProcessingParameters,
    QgsPropertyDefinition,
    QgsWkbTypes,
)

JOIN_STYLE_LABELS = ["Mitre (sharp corners)", "Round", "Bevel"]
JOIN_STYLES = [Qgis.JoinStyle.Miter, Qgis.JoinStyle.Round, Qgis.JoinStyle.Bevel]

END_CAP_LABELS = [
    "Flat - close straight across the end",
    "Square - carry the width past the end",
    "Round - fillet the end",
]
CAP_FLAT, CAP_SQUARE, CAP_ROUND = 0, 1, 2


class RightOfWayFromCenterline(QgsProcessingAlgorithm):
    """Buffer a centerline asymmetrically and close it into a ROW polygon."""

    INPUT = "INPUT"
    OFFSET_LEFT = "OFFSET_LEFT"
    OFFSET_RIGHT = "OFFSET_RIGHT"
    END_CAP = "END_CAP"
    JOIN_STYLE = "JOIN_STYLE"
    SEGMENTS = "SEGMENTS"
    MITRE_LIMIT = "MITRE_LIMIT"
    DISSOLVE = "DISSOLVE"
    OUTPUT = "OUTPUT"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT, "Centerline", [QgsProcessing.TypeVectorLine]
            )
        )

        for name, label, default in (
            (self.OFFSET_LEFT, "Offset left of the centerline", 25.0),
            (self.OFFSET_RIGHT, "Offset right of the centerline", 25.0),
        ):
            param = QgsProcessingParameterDistance(
                name, label, defaultValue=default, parentParameterName=self.INPUT,
                minValue=0.0
            )
            # Data-defined, so a per-feature width field can drive it: click the
            # button beside the box and pick a field or expression such as
            # "row_width" / 2.
            param.setIsDynamic(True)
            param.setDynamicPropertyDefinition(
                QgsPropertyDefinition(name, label, QgsPropertyDefinition.DoublePositive)
            )
            param.setDynamicLayerParameterName(self.INPUT)
            self.addParameter(param)

        self.addParameter(
            QgsProcessingParameterEnum(
                self.END_CAP, "End treatment", END_CAP_LABELS, defaultValue=CAP_FLAT
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.JOIN_STYLE, "Corner treatment", JOIN_STYLE_LABELS, defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.DISSOLVE, "Dissolve the result into a single polygon",
                defaultValue=False
            )
        )

        for param in (
            QgsProcessingParameterNumber(
                self.SEGMENTS, "Segments per quarter circle",
                QgsProcessingParameterNumber.Integer, defaultValue=8, minValue=1
            ),
            QgsProcessingParameterNumber(
                self.MITRE_LIMIT, "Mitre limit",
                QgsProcessingParameterNumber.Double, defaultValue=2.0, minValue=1.0
            ),
        ):
            param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(param)

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT, "Right of way", QgsProcessing.TypeVectorPolygon
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))

        cap = self.parameterAsEnum(parameters, self.END_CAP, context)
        join = JOIN_STYLES[self.parameterAsEnum(parameters, self.JOIN_STYLE, context)]
        segments = self.parameterAsInt(parameters, self.SEGMENTS, context)
        mitre_limit = self.parameterAsDouble(parameters, self.MITRE_LIMIT, context)
        dissolve = self.parameterAsBool(parameters, self.DISSOLVE, context)

        left_default = self.parameterAsDouble(parameters, self.OFFSET_LEFT, context)
        right_default = self.parameterAsDouble(parameters, self.OFFSET_RIGHT, context)
        left_dynamic = QgsProcessingParameters.isDynamic(parameters, self.OFFSET_LEFT)
        right_dynamic = QgsProcessingParameters.isDynamic(parameters, self.OFFSET_RIGHT)
        left_property = parameters[self.OFFSET_LEFT] if left_dynamic else None
        right_property = parameters[self.OFFSET_RIGHT] if right_dynamic else None
        expression_context = self.createExpressionContext(parameters, context, source)

        if left_default <= 0 and right_default <= 0 and not (left_dynamic or right_dynamic):
            raise QgsProcessingException(
                "Both offsets are zero - there is no right of way to build."
            )

        fields = QgsFields(source.fields())
        for name in ("row_left", "row_right", "row_width"):
            fields.append(QgsField(name, QVariant.Double))

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields,
            QgsWkbTypes.MultiPolygon, source.sourceCrs()
        )
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        total = 100.0 / source.featureCount() if source.featureCount() else 0
        dissolved = []
        skipped = 0

        for current, feature in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break

            left, right = left_default, right_default
            if left_dynamic or right_dynamic:
                expression_context.setFeature(feature)
                if left_dynamic:
                    left, ok = left_property.valueAsDouble(expression_context, left_default)
                    if not ok:
                        left = left_default
                if right_dynamic:
                    right, ok = right_property.valueAsDouble(expression_context, right_default)
                    if not ok:
                        right = right_default

            geometry = self._build(feature.geometry(), left, right, cap, join,
                                   segments, mitre_limit)
            if geometry is None or geometry.isEmpty():
                skipped += 1
                feedback.pushWarning(
                    "Feature %s produced no right of way (offsets %s / %s)"
                    % (feature.id(), left, right)
                )
            elif dissolve:
                dissolved.append(geometry)
            else:
                out = QgsFeature(fields)
                out.setGeometry(geometry)
                out.setAttributes(feature.attributes() + [left, right, left + right])
                sink.addFeature(out, QgsFeatureSink.FastInsert)

            feedback.setProgress(int(current * total))

        if dissolve and dissolved:
            merged = QgsGeometry.unaryUnion(dissolved)
            out = QgsFeature(fields)
            out.setGeometry(merged)
            out.setAttributes([None] * source.fields().count() + [None, None, None])
            sink.addFeature(out, QgsFeatureSink.FastInsert)

        if skipped:
            feedback.pushInfo("%d feature(s) produced no output." % skipped)

        return {self.OUTPUT: dest_id}

    def _build(self, geometry, left, right, cap, join, segments, mitre_limit):
        """One centerline -> one ROW polygon."""
        if geometry is None or geometry.isEmpty():
            return None

        if geometry.isMultipart():
            parts = geometry.asMultiPolyline()
        else:
            parts = [geometry.asPolyline()]

        pieces = []
        for points in parts:
            if len(points) < 2:
                continue
            if cap == CAP_SQUARE:
                points = self._extend_ends(points, max(left, right))
            line = QgsGeometry.fromPolylineXY(points)

            sides = []
            if left > 0:
                sides.append(line.singleSidedBuffer(
                    left, segments, Qgis.BufferSide.Left, join, mitre_limit))
            if right > 0:
                sides.append(line.singleSidedBuffer(
                    right, segments, Qgis.BufferSide.Right, join, mitre_limit))
            sides = [s for s in sides if s is not None and not s.isEmpty()]
            if not sides:
                continue

            corridor = sides[0]
            for side in sides[1:]:
                corridor = corridor.combine(side)

            if cap == CAP_ROUND:
                radius = max(left, right)
                for point in (points[0], points[-1]):
                    corridor = corridor.combine(
                        QgsGeometry.fromPointXY(QgsPointXY(point)).buffer(radius, segments)
                    )

            pieces.append(corridor)

        if not pieces:
            return None
        result = pieces[0] if len(pieces) == 1 else QgsGeometry.unaryUnion(pieces)
        if result is None or result.isEmpty():
            return None
        result.convertToMultiType()
        return result

    @staticmethod
    def _extend_ends(points, distance):
        """Push both ends out along their own bearing, for a square end cap."""
        if distance <= 0 or len(points) < 2:
            return points

        def beyond(inner, outer):
            dx, dy = outer.x() - inner.x(), outer.y() - inner.y()
            length = math.hypot(dx, dy)
            if length == 0:
                return None
            return QgsPointXY(outer.x() + dx / length * distance,
                              outer.y() + dy / length * distance)

        points = list(points)
        start = beyond(points[1], points[0])
        end = beyond(points[-2], points[-1])
        if start is not None:
            points.insert(0, start)
        if end is not None:
            points.append(end)
        return points

    def name(self):
        return "rowfromcenterline"

    def displayName(self):
        return "Right of way from centerline"

    def group(self):
        return "Editing"

    def groupId(self):
        return "editing"

    def shortHelpString(self):
        return (
            "<p>Builds a right-of-way polygon from a centerline, with independent "
            "left and right offsets, and closes the ends.</p>"
            "<p>Both offsets carry a data-defined button, so a per-feature width "
            "field can drive them - point it at a field or an expression like "
            "<i>\"row_width\" / 2</i> for a variable-width corridor.</p>"
            "<h3>End treatment</h3>"
            "<p><b>Flat</b> closes straight across the last vertex. <b>Square</b> "
            "carries the full width one offset past the end. <b>Round</b> fillets "
            "the end with an arc of the larger offset.</p>"
            "<h3>Notes</h3>"
            "<p>Corners use a mitre join by default, so a bend in the centerline "
            "produces a sharp ROW corner rather than a rounded one. Lower the mitre "
            "limit if very tight bends produce spikes.</p>"
            "<p>Curved (circular string) geometry is segmentised, and Z/M values "
            "are dropped.</p>"
        )

    def createInstance(self):
        return RightOfWayFromCenterline()

    def tr(self, string):
        return QCoreApplication.translate("FieldKit", string)
