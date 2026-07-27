"""Snap geometries to a reference layer, and show exactly what moved."""

import math

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.analysis import QgsGeometrySnapper
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterDistance,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsWkbTypes,
)

MODE_LABELS = [
    "Prefer nodes - move vertices onto reference vertices where possible",
    "Prefer closest - move vertices onto the nearest point of the reference",
    "Prefer nodes, no extra vertices - never add vertices to the input",
    "End points only - snap line ends to reference ends",
]


class SnapAndVerify(QgsProcessingAlgorithm):
    """Snapping you can check afterwards, instead of hoping."""

    INPUT = "INPUT"
    REFERENCE = "REFERENCE"
    TOLERANCE = "TOLERANCE"
    MODE = "MODE"
    MAX_MOVE = "MAX_MOVE"
    OUTPUT = "OUTPUT"
    OUTPUT_MOVES = "OUTPUT_MOVES"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT, "Layer to adjust", [QgsProcessing.TypeVectorAnyGeometry]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.REFERENCE, "Align to this layer",
                [QgsProcessing.TypeVectorAnyGeometry]
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.TOLERANCE, "Search tolerance", defaultValue=1.0,
                parentParameterName=self.INPUT, minValue=0.0
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.MODE, "How to snap", MODE_LABELS, defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.MAX_MOVE,
                "Reject a feature if any vertex would move further than this "
                "(0 = no guard)",
                defaultValue=0.0, parentParameterName=self.INPUT, minValue=0.0
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT, "Snapped", QgsProcessing.TypeVectorAnyGeometry
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_MOVES, "Displacement vectors",
                QgsProcessing.TypeVectorLine, optional=True, createByDefault=True
            )
        )

    def _modes(self):
        return [
            QgsGeometrySnapper.PreferNodes,
            QgsGeometrySnapper.PreferClosest,
            QgsGeometrySnapper.PreferNodesNoExtraVertices,
            QgsGeometrySnapper.EndPointToEndPoint,
        ]

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))
        reference = self.parameterAsSource(parameters, self.REFERENCE, context)
        if reference is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.REFERENCE))

        tolerance = self.parameterAsDouble(parameters, self.TOLERANCE, context)
        max_move = self.parameterAsDouble(parameters, self.MAX_MOVE, context)
        mode = self._modes()[self.parameterAsEnum(parameters, self.MODE, context)]

        if tolerance <= 0:
            raise QgsProcessingException("The search tolerance must be greater than 0.")
        if reference.sourceCrs() != source.sourceCrs():
            feedback.pushWarning(
                "The two layers are in different CRSs (%s vs %s). Reproject one of "
                "them first - the tolerance is measured in the input layer's units."
                % (source.sourceCrs().authid(), reference.sourceCrs().authid())
            )

        out_fields = QgsFields(source.fields())
        out_fields.append(QgsField("snap_moved", QVariant.Int))
        out_fields.append(QgsField("snap_max", QVariant.Double))

        move_fields = QgsFields()
        move_fields.append(QgsField("fid", QVariant.Int))
        move_fields.append(QgsField("distance", QVariant.Double))

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            source.wkbType(), source.sourceCrs()
        )
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))
        move_sink, move_dest_id = self.parameterAsSink(
            parameters, self.OUTPUT_MOVES, context, move_fields,
            QgsWkbTypes.LineString, source.sourceCrs()
        )

        snapper = QgsGeometrySnapper(reference)

        total = 100.0 / source.featureCount() if source.featureCount() else 0
        changed_features = 0
        rejected = 0
        moved_vertices = 0
        largest_move = 0.0

        for current, feature in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break

            original = feature.geometry()
            out = QgsFeature(out_fields)

            if original is None or original.isEmpty():
                out.setGeometry(original)
                out.setAttributes(feature.attributes() + [0, 0.0])
                sink.addFeature(out, QgsFeatureSink.FastInsert)
                continue

            snapped = snapper.snapGeometry(original, tolerance, mode)
            moves = self._displacements(original, snapped)
            feature_max = max((d for _, _, d in moves), default=0.0)

            if max_move > 0 and feature_max > max_move:
                rejected += 1
                feedback.pushWarning(
                    "Feature %s left alone: a vertex would have moved %.4f, over the "
                    "%.4f guard." % (feature.id(), feature_max, max_move)
                )
                out.setGeometry(original)
                out.setAttributes(feature.attributes() + [0, 0.0])
                sink.addFeature(out, QgsFeatureSink.FastInsert)
                feedback.setProgress(int(current * total))
                continue

            if moves:
                changed_features += 1
                moved_vertices += len(moves)
                largest_move = max(largest_move, feature_max)
                if move_sink is not None:
                    for start, end, distance in moves:
                        vector = QgsFeature(move_fields)
                        vector.setGeometry(QgsGeometry.fromPolylineXY([start, end]))
                        vector.setAttributes([feature.id(), distance])
                        move_sink.addFeature(vector, QgsFeatureSink.FastInsert)

            out.setGeometry(snapped)
            out.setAttributes(feature.attributes() + [len(moves), feature_max])
            sink.addFeature(out, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(current * total))

        feedback.pushInfo(
            "%d feature(s) changed, %d vertex move(s), largest move %.4f."
            % (changed_features, moved_vertices, largest_move)
        )
        if rejected:
            feedback.pushInfo("%d feature(s) rejected by the move guard." % rejected)

        results = {self.OUTPUT: dest_id}
        if move_sink is not None:
            results[self.OUTPUT_MOVES] = move_dest_id
        return results

    @staticmethod
    def _displacements(original, snapped):
        """Where each original vertex ended up. Returns (from, to, distance) triples.

        Matching by nearest vertex rather than by index, because some snapping
        modes insert vertices and the indices no longer line up.
        """
        if snapped is None or snapped.isEmpty():
            return []
        moves = []
        for vertex in original.vertices():
            point = QgsPointXY(vertex.x(), vertex.y())
            squared, index = snapped.closestVertexWithContext(point)
            if index < 0:
                continue
            distance = math.sqrt(squared) if squared > 0 else 0.0
            if distance <= 0:
                continue
            target = snapped.vertexAt(index)
            moves.append((point, QgsPointXY(target.x(), target.y()), distance))
        return moves

    def name(self):
        return "snapandverify"

    def displayName(self):
        return "Snap to layer and verify"

    def group(self):
        return "Editing"

    def groupId(self):
        return "editing"

    def shortHelpString(self):
        return (
            "<p>Moves vertices onto a reference layer so shared edges match exactly - "
            "and then tells you what it did.</p>"
            "<p>The output carries <i>snap_moved</i> (how many vertices moved) and "
            "<i>snap_max</i> (the largest move) per feature, and the second output is "
            "a line layer of displacement vectors. Style it red over the original and "
            "a bad tolerance is obvious in one look.</p>"
            "<h3>The move guard</h3>"
            "<p>Set it and any feature with a vertex that would jump further than the "
            "guard is written out untouched and reported. That is the difference "
            "between snapping and hoping: a tolerance loose enough to catch real gaps "
            "is also loose enough to drag a corner across the street.</p>"
            "<p>The tolerance is in the input layer's units, so reproject first if the "
            "two layers differ.</p>"
        )

    def createInstance(self):
        return SnapAndVerify()

    def tr(self, string):
        return QCoreApplication.translate("FieldKit", string)
