"""Where polygons overlap, decide which one keeps the overlap and trim the other."""

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsSpatialIndex,
    QgsWkbTypes,
)

RULE_LABELS = [
    "The one drawn first keeps it",
    "The larger polygon keeps it",
    "The smaller polygon keeps it",
    "The higher value in a field keeps it",
    "Report only - do not change any geometry",
]
RULE_FIRST, RULE_LARGEST, RULE_SMALLEST, RULE_FIELD, RULE_REPORT = range(5)


class EraseOverlaps(QgsProcessingAlgorithm):
    """The mirror of Fill gaps: the same digitising mistake in the other direction."""

    INPUT = "INPUT"
    RULE = "RULE"
    PRIORITY_FIELD = "PRIORITY_FIELD"
    MAX_AREA = "MAX_AREA"
    OUTPUT = "OUTPUT"
    OUTPUT_OVERLAPS = "OUTPUT_OVERLAPS"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT, "Polygons", [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.RULE, "Who keeps the overlap", RULE_LABELS,
                defaultValue=RULE_FIRST
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PRIORITY_FIELD, "Priority field (for the field rule)",
                parentLayerParameterName=self.INPUT, optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_AREA,
                "Leave overlaps larger than this area alone (0 = no limit)",
                QgsProcessingParameterNumber.Double, defaultValue=0.0, minValue=0.0
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT, "Trimmed polygons", QgsProcessing.TypeVectorPolygon
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_OVERLAPS, "Overlaps found",
                QgsProcessing.TypeVectorPolygon, optional=True, createByDefault=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))
        rule = self.parameterAsEnum(parameters, self.RULE, context)
        priority_field = self.parameterAsString(
            parameters, self.PRIORITY_FIELD, context)
        max_area = self.parameterAsDouble(parameters, self.MAX_AREA, context)

        if rule == RULE_FIELD and not priority_field:
            raise QgsProcessingException(
                "The field rule needs a priority field to compare.")

        out_fields = QgsFields(source.fields())
        out_fields.append(QgsField("overlaps_fixed", QVariant.Int))
        out_fields.append(QgsField("area_lost", QVariant.Double))

        overlap_fields = QgsFields()
        overlap_fields.append(QgsField("overlap_id", QVariant.Int))
        overlap_fields.append(QgsField("area", QVariant.Double))
        overlap_fields.append(QgsField("kept_by", QVariant.String))
        overlap_fields.append(QgsField("taken_from", QVariant.String))
        overlap_fields.append(QgsField("action", QVariant.String))

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            QgsWkbTypes.MultiPolygon, source.sourceCrs()
        )
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))
        overlap_sink, overlap_dest_id = self.parameterAsSink(
            parameters, self.OUTPUT_OVERLAPS, context, overlap_fields,
            QgsWkbTypes.Polygon, source.sourceCrs()
        )

        feedback.pushInfo("Reading polygons...")
        features = {}
        geometries = {}
        original_area = {}
        index = QgsSpatialIndex()
        repaired = 0
        for feature in source.getFeatures():
            if feedback.isCanceled():
                break
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            if not geometry.isGeosValid():
                fixed = geometry.makeValid()
                if fixed is not None and not fixed.isEmpty():
                    geometry = fixed
                    repaired += 1
            features[feature.id()] = feature
            geometries[feature.id()] = geometry
            original_area[feature.id()] = geometry.area()
            index.addFeature(feature)

        if repaired:
            feedback.pushWarning(
                "%d input geometr%s repaired before looking for overlaps."
                % (repaired, "y was" if repaired == 1 else "ies were"))
        if not geometries:
            raise QgsProcessingException("No usable polygons in the input layer.")

        order = sorted(geometries)
        rank = {fid: position for position, fid in enumerate(order)}
        fixed_count = {fid: 0 for fid in order}
        number = 0
        left_alone = 0
        emptied = []
        step = 85.0 / len(order)

        for position, fid in enumerate(order):
            if feedback.isCanceled():
                break
            # Only look forward, so each pair is considered exactly once.
            candidates = sorted({
                other for other in index.intersects(geometries[fid].boundingBox())
                if other in geometries and rank.get(other, -1) > position
            })

            for other in candidates:
                first, second = geometries[fid], geometries[other]
                if first.isEmpty() or second.isEmpty():
                    continue
                if not first.intersects(second):
                    continue
                overlap = first.intersection(second)
                if overlap is None or overlap.isEmpty():
                    continue
                area = overlap.area()
                if area <= 0:
                    continue  # touching along an edge is not an overlap

                number += 1
                if max_area > 0 and area > max_area:
                    left_alone += 1
                    self._report(overlap_sink, overlap_fields, number, area,
                                 None, None, "left alone - larger than the limit")
                    continue

                if rule == RULE_REPORT:
                    self._report(overlap_sink, overlap_fields, number, area,
                                 None, None, "reported only")
                    continue

                winner, loser = self._decide(
                    fid, other, geometries, features, rule, priority_field)
                trimmed = geometries[loser].difference(overlap)
                if trimmed is None:
                    continue
                geometries[loser] = trimmed
                fixed_count[loser] += 1
                if trimmed.isEmpty():
                    emptied.append(loser)

                self._report(overlap_sink, overlap_fields, number, area,
                             str(winner), str(loser), "trimmed")

            feedback.setProgress(int(position * step))

        feedback.pushInfo("Writing output...")
        for fid in order:
            geometry = QgsGeometry(geometries[fid])
            geometry.convertToMultiType()
            out = QgsFeature(out_fields)
            out.setGeometry(geometry)
            lost = original_area[fid] - geometries[fid].area()
            out.setAttributes(
                features[fid].attributes() + [fixed_count[fid], max(lost, 0.0)])
            sink.addFeature(out, QgsFeatureSink.FastInsert)

        feedback.pushInfo(
            "%d overlap(s) found, %d trimmed."
            % (number, sum(fixed_count.values())))
        if left_alone:
            feedback.pushInfo(
                "%d overlap(s) left alone for being larger than the limit - those "
                "are in the overlap layer to look at." % left_alone)
        if emptied:
            feedback.pushWarning(
                "%d feature(s) were completely inside another and now have empty "
                "geometry: %s. Those are duplicates or containments, not "
                "digitising slop - delete them by hand once you have looked."
                % (len(emptied), ", ".join(str(f) for f in emptied[:10])))

        results = {self.OUTPUT: dest_id}
        if overlap_sink is not None:
            results[self.OUTPUT_OVERLAPS] = overlap_dest_id
        return results

    @staticmethod
    def _report(sink, fields, number, area, winner, loser, action):
        if sink is None:
            return
        feature = QgsFeature(fields)
        feature.setAttributes([number, area, winner, loser, action])
        sink.addFeature(feature, QgsFeatureSink.FastInsert)

    @staticmethod
    def _decide(first, second, geometries, features, rule, priority_field):
        """Returns (winner, loser)."""
        if rule == RULE_LARGEST:
            return ((first, second)
                    if geometries[first].area() >= geometries[second].area()
                    else (second, first))
        if rule == RULE_SMALLEST:
            return ((first, second)
                    if geometries[first].area() <= geometries[second].area()
                    else (second, first))
        if rule == RULE_FIELD:
            left = features[first].attribute(priority_field)
            right = features[second].attribute(priority_field)
            try:
                higher = left is not None and (right is None or left >= right)
            except TypeError:  # values that will not compare, e.g. text vs null
                higher = True
            return (first, second) if higher else (second, first)
        # RULE_FIRST: the lower feature id was drawn first.
        return (first, second) if first <= second else (second, first)

    def name(self):
        return "eraseoverlaps"

    def displayName(self):
        return "Erase overlaps between polygons"

    def group(self):
        return "Editing"

    def groupId(self):
        return "editing"

    def shortHelpString(self):
        return (
            "<p>Finds every place two polygons overlap, decides which one keeps "
            "the overlapping ground, and trims it out of the other.</p>"
            "<p>This is the mirror of <i>Fill gaps between polygons</i>. Gaps and "
            "overlaps are the same digitising mistake in opposite directions, and "
            "a coverage is only clean when both are gone.</p>"
            "<h3>Who keeps the overlap</h3>"
            "<p><b>Drawn first</b> is the safe default: the older polygon is "
            "usually the surveyed one and the newer one is the sketch. "
            "<b>Larger</b> and <b>smaller</b> are useful when one layer is a "
            "coarse boundary and the other is detail. <b>Field</b> lets a "
            "priority column decide - a survey date, a source rank, a confidence "
            "score.</p>"
            "<h3>Leave large overlaps alone</h3>"
            "<p>Set this and anything bigger is reported but not touched. A "
            "two-foot slither along a shared line is digitising slop; two parcels "
            "overlapping by half an acre is a disagreement about where the "
            "boundary is, and no rule should silently pick a winner.</p>"
            "<p>Overlaps are resolved in feature-id order, and each trim uses the "
            "geometry as it stands at that point, so three polygons stacked on the "
            "same ground resolve cleanly instead of double-subtracting.</p>"
            "<p>A polygon completely inside another ends up with empty geometry "
            "and is reported as a warning - that is a duplicate, not slop, and "
            "wants deleting by hand.</p>"
            "<p>The output is a new layer; the input is never modified.</p>"
        )

    def createInstance(self):
        return EraseOverlaps()

    def tr(self, string):
        return QCoreApplication.translate("FieldKit", string)
