"""Extend dangling line ends until they meet the network they were meant to join."""

import math

from qgis.PyQt.QtCore import QCoreApplication, QVariant
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
    QgsProcessingParameterDefinition,
    QgsProcessingParameterDistance,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsSpatialIndex,
    QgsWkbTypes,
)

MODE_LABELS = [
    "Extend along the line's own bearing",
    "Extend along the bearing, then snap to the nearest line if that misses",
    "Snap straight to the nearest line",
]
MODE_EXTEND, MODE_EXTEND_THEN_SNAP, MODE_SNAP = 0, 1, 2


class CloseUndershoots(QgsProcessingAlgorithm):
    """Fix the almost-touching line ends that digitising leaves behind."""

    INPUT = "INPUT"
    TOLERANCE = "TOLERANCE"
    MODE = "MODE"
    CONNECTED_TOL = "CONNECTED_TOL"
    OUTPUT = "OUTPUT"
    OUTPUT_REPORT = "OUTPUT_REPORT"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT, "Lines", [QgsProcessing.TypeVectorLine]
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.TOLERANCE, "Close gaps up to this length", defaultValue=5.0,
                parentParameterName=self.INPUT, minValue=0.0
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.MODE, "How to close them", MODE_LABELS,
                defaultValue=MODE_EXTEND_THEN_SNAP
            )
        )
        param = QgsProcessingParameterDistance(
            self.CONNECTED_TOL, "Treat ends this close as already connected",
            defaultValue=0.001, parentParameterName=self.INPUT, minValue=0.0
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT, "Lines with ends closed", QgsProcessing.TypeVectorLine
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_REPORT, "Dangle report", QgsProcessing.TypeVectorPoint,
                optional=True, createByDefault=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))
        tolerance = self.parameterAsDouble(parameters, self.TOLERANCE, context)
        mode = self.parameterAsEnum(parameters, self.MODE, context)
        connected_tol = self.parameterAsDouble(parameters, self.CONNECTED_TOL, context)
        if tolerance <= 0:
            raise QgsProcessingException("The gap tolerance must be greater than 0.")

        out_fields = QgsFields(source.fields())
        out_fields.append(QgsField("ends_closed", QVariant.Int))

        report_fields = QgsFields()
        report_fields.append(QgsField("fid", QVariant.Int))
        report_fields.append(QgsField("part", QVariant.Int))
        report_fields.append(QgsField("end", QVariant.String))
        report_fields.append(QgsField("status", QVariant.String))
        report_fields.append(QgsField("distance", QVariant.Double))

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            QgsWkbTypes.MultiLineString, source.sourceCrs()
        )
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))
        report_sink, report_dest_id = self.parameterAsSink(
            parameters, self.OUTPUT_REPORT, context, report_fields,
            QgsWkbTypes.Point, source.sourceCrs()
        )

        feedback.pushInfo("Indexing lines...")
        features = {}
        geometries = {}
        index = QgsSpatialIndex()
        for feature in source.getFeatures():
            if feedback.isCanceled():
                break
            if not feature.hasGeometry() or feature.geometry().isEmpty():
                continue
            features[feature.id()] = feature
            geometries[feature.id()] = feature.geometry()
            index.addFeature(feature)

        if not geometries:
            raise QgsProcessingException("No usable lines in the input layer.")

        total = 100.0 / len(geometries)
        fixed = 0
        unresolved = 0

        for current, (fid, feature) in enumerate(features.items()):
            if feedback.isCanceled():
                break

            parts = self._parts(geometries[fid])
            closed_here = 0
            new_parts = []

            for part_index, points in enumerate(parts):
                points = list(points)
                if len(points) < 2:
                    new_parts.append(points)
                    continue

                for end_name in ("start", "end"):
                    at_start = end_name == "start"
                    tip = points[0] if at_start else points[-1]
                    inner = points[1] if at_start else points[-2]

                    if self._is_connected(index, geometries, fid, tip, connected_tol):
                        continue

                    target, status, distance = self._resolve(
                        index, geometries, fid, tip, inner, tolerance, mode
                    )
                    if target is not None:
                        if at_start:
                            points.insert(0, target)
                        else:
                            points.append(target)
                        closed_here += 1
                        fixed += 1
                    else:
                        unresolved += 1

                    if report_sink is not None:
                        point_feature = QgsFeature(report_fields)
                        point_feature.setGeometry(QgsGeometry.fromPointXY(tip))
                        point_feature.setAttributes(
                            [fid, part_index, end_name, status, distance]
                        )
                        report_sink.addFeature(point_feature, QgsFeatureSink.FastInsert)

                new_parts.append(points)

            out = QgsFeature(out_fields)
            geometry = QgsGeometry.fromMultiPolylineXY(
                [p for p in new_parts if len(p) >= 2]
            )
            out.setGeometry(geometry)
            out.setAttributes(feature.attributes() + [closed_here])
            sink.addFeature(out, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(current * total))

        feedback.pushInfo(
            "%d dangling end(s) closed, %d left open." % (fixed, unresolved)
        )
        if unresolved:
            feedback.pushInfo(
                "The ones left open are in the dangle report with status "
                "'unresolved' - either the gap is longer than the tolerance, or "
                "they are genuine ends of the network."
            )

        results = {self.OUTPUT: dest_id}
        if report_sink is not None:
            results[self.OUTPUT_REPORT] = report_dest_id
        return results

    @staticmethod
    def _parts(geometry):
        if geometry.isMultipart():
            return geometry.asMultiPolyline()
        line = geometry.asPolyline()
        return [line] if line else []

    @staticmethod
    def _neighbours(index, geometries, fid, rectangle):
        return [
            other for other in index.intersects(rectangle)
            if other != fid and other in geometries
        ]

    def _is_connected(self, index, geometries, fid, point, tolerance):
        point_geometry = QgsGeometry.fromPointXY(point)
        rectangle = point_geometry.boundingBox()
        rectangle.grow(max(tolerance, 1e-9))
        for other in self._neighbours(index, geometries, fid, rectangle):
            if geometries[other].distance(point_geometry) <= tolerance:
                return True
        return False

    def _resolve(self, index, geometries, fid, tip, inner, tolerance, mode):
        """Find where a dangling tip should reach. Returns (point, status, distance)."""
        if mode in (MODE_EXTEND, MODE_EXTEND_THEN_SNAP):
            hit = self._extend(index, geometries, fid, tip, inner, tolerance)
            if hit is not None:
                return hit[0], "extended", hit[1]
            if mode == MODE_EXTEND:
                return None, "unresolved", None

        hit = self._nearest(index, geometries, fid, tip, tolerance)
        if hit is not None:
            return hit[0], "snapped", hit[1]
        return None, "unresolved", None

    def _extend(self, index, geometries, fid, tip, inner, tolerance):
        """Shoot a probe out along the last segment's bearing and see what it hits."""
        dx, dy = tip.x() - inner.x(), tip.y() - inner.y()
        length = math.hypot(dx, dy)
        if length == 0:
            return None
        far = QgsPointXY(tip.x() + dx / length * tolerance,
                         tip.y() + dy / length * tolerance)
        probe = QgsGeometry.fromPolylineXY([tip, far])

        best, best_distance = None, None
        for other in self._neighbours(index, geometries, fid, probe.boundingBox()):
            crossing = probe.intersection(geometries[other])
            if crossing is None or crossing.isEmpty():
                continue
            for vertex in crossing.vertices():
                candidate = QgsPointXY(vertex.x(), vertex.y())
                distance = tip.distance(candidate)
                if distance <= 1e-12 or distance > tolerance:
                    continue
                if best_distance is None or distance < best_distance:
                    best, best_distance = candidate, distance
        if best is None:
            return None
        return best, best_distance

    def _nearest(self, index, geometries, fid, tip, tolerance):
        """Nearest point on any other line, within tolerance."""
        rectangle = QgsGeometry.fromPointXY(tip).boundingBox()
        rectangle.grow(tolerance)
        best, best_squared = None, None
        for other in self._neighbours(index, geometries, fid, rectangle):
            squared, point, _, _ = geometries[other].closestSegmentWithContext(tip)
            if squared < 0:
                continue
            if best_squared is None or squared < best_squared:
                best, best_squared = point, squared
        if best is None:
            return None
        distance = math.sqrt(best_squared)
        if distance > tolerance or distance <= 1e-12:
            return None
        return QgsPointXY(best), distance

    def name(self):
        return "closeundershoots"

    def displayName(self):
        return "Close dangling line ends"

    def group(self):
        return "Editing"

    def groupId(self):
        return "editing"

    def shortHelpString(self):
        return (
            "<p>Finds line ends that stop just short of the network and carries them "
            "the rest of the way - the classic undershoot left behind when tracing "
            "without snapping on.</p>"
            "<p><b>Extend along the bearing</b> continues the line in the direction it "
            "was already heading, which is what you want for a pipe run or a road "
            "stub: the geometry keeps its alignment. <b>Snap to the nearest line</b> "
            "takes the shortest path instead, which closes more gaps but can bend the "
            "end sideways.</p>"
            "<p>The default does the first and falls back to the second.</p>"
            "<h3>Reading the report</h3>"
            "<p>The point layer marks every dangle it looked at: <i>extended</i>, "
            "<i>snapped</i>, or <i>unresolved</i>. Unresolved is not necessarily a "
            "problem - the real end of a cul-de-sac is a dangle too. Look at them "
            "before raising the tolerance.</p>"
            "<p>Note this closes gaps by moving <i>ends</i>; it does not split the "
            "line it meets. Run <i>Split with lines</i> afterwards if you need proper "
            "node-to-node topology.</p>"
        )

    def createInstance(self):
        return CloseUndershoots()

    def tr(self, string):
        return QCoreApplication.translate("FieldKit", string)
