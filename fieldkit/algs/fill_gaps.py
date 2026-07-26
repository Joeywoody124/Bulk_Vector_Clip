"""Find slivers and gaps between polygons, and close them by giving them to a neighbour."""

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
    QgsProcessingParameterDistance,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsSpatialIndex,
    QgsWkbTypes,
)

MODE_LABELS = [
    "Fill - give each gap to the neighbour it shares the most edge with",
    "Fill - give each gap to its largest neighbour",
    "Report only - do not change any geometry",
]
MODE_SHARED_EDGE, MODE_LARGEST, MODE_REPORT = 0, 1, 2


class FillGaps(QgsProcessingAlgorithm):
    """Close the slivers left behind by digitising polygons that should share edges."""

    INPUT = "INPUT"
    BOUNDARY = "BOUNDARY"
    MAX_AREA = "MAX_AREA"
    SLIVER_WIDTH = "SLIVER_WIDTH"
    MODE = "MODE"
    OUTPUT = "OUTPUT"
    OUTPUT_GAPS = "OUTPUT_GAPS"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT, "Polygons", [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BOUNDARY, "Boundary they should fill (optional)",
                [QgsProcessing.TypeVectorPolygon], optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_AREA, "Ignore gaps larger than this area (0 = no limit)",
                QgsProcessingParameterNumber.Double, defaultValue=0.0, minValue=0.0
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.SLIVER_WIDTH,
                "Also find open-ended slivers narrower than (0 = off)",
                defaultValue=0.0, parentParameterName=self.INPUT, minValue=0.0
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.MODE, "What to do", MODE_LABELS, defaultValue=MODE_SHARED_EDGE
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT, "Filled polygons", QgsProcessing.TypeVectorPolygon
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_GAPS, "Gaps found", QgsProcessing.TypeVectorPolygon,
                optional=True, createByDefault=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))
        boundary_source = self.parameterAsSource(parameters, self.BOUNDARY, context)
        max_area = self.parameterAsDouble(parameters, self.MAX_AREA, context)
        sliver_width = self.parameterAsDouble(
            parameters, self.SLIVER_WIDTH, context)
        mode = self.parameterAsEnum(parameters, self.MODE, context)

        out_fields = QgsFields(source.fields())
        out_fields.append(QgsField("gaps_filled", QVariant.Int))
        out_fields.append(QgsField("gap_area", QVariant.Double))

        gap_fields = QgsFields()
        gap_fields.append(QgsField("gap_id", QVariant.Int))
        gap_fields.append(QgsField("origin", QVariant.String))
        gap_fields.append(QgsField("area", QVariant.Double))
        gap_fields.append(QgsField("perimeter", QVariant.Double))
        gap_fields.append(QgsField("neighbours", QVariant.Int))
        gap_fields.append(QgsField("assigned_to", QVariant.String))

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            QgsWkbTypes.MultiPolygon, source.sourceCrs()
        )
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))
        gap_sink, gap_dest_id = self.parameterAsSink(
            parameters, self.OUTPUT_GAPS, context, gap_fields,
            QgsWkbTypes.Polygon, source.sourceCrs()
        )

        feedback.pushInfo("Reading polygons...")
        features = {}
        geometries = {}
        index = QgsSpatialIndex()
        invalid = 0
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
                    invalid += 1
            features[feature.id()] = feature
            geometries[feature.id()] = geometry
            index.addFeature(feature)

        if invalid:
            feedback.pushWarning(
                "%d input geometr%s repaired before searching for gaps."
                % (invalid, "y was" if invalid == 1 else "ies were")
            )
        if not geometries:
            raise QgsProcessingException("No usable polygons in the input layer.")

        feedback.setProgress(15)
        feedback.pushInfo("Dissolving to find gaps...")
        union = QgsGeometry.unaryUnion(list(geometries.values()))
        if union is None or union.isEmpty():
            raise QgsProcessingException("Could not dissolve the input polygons.")

        gaps = [(g, "interior") for g in self._interior_rings(union)]

        if boundary_source is not None:
            boundary_geoms = [
                f.geometry() for f in boundary_source.getFeatures()
                if f.hasGeometry() and not f.geometry().isEmpty()
            ]
            if boundary_geoms:
                boundary = QgsGeometry.unaryUnion(boundary_geoms)
                remainder = boundary.difference(union)
                if remainder is not None and not remainder.isEmpty():
                    for part in self._parts(remainder):
                        gaps.append((part, "boundary"))

        if sliver_width > 0:
            # An interior ring only exists where a gap is fully enclosed. A
            # sliver between two polygons that is open at both ends is not a
            # hole in the dissolved coverage, so it needs finding another way:
            # buffer out and back in, which closes anything narrower than the
            # buffer diameter, then subtract the original.
            radius = sliver_width / 2.0
            closed = union.buffer(radius, 8)
            if closed is not None and not closed.isEmpty():
                closed = closed.buffer(-radius, 8)
            if closed is not None and not closed.isEmpty():
                extra = closed.difference(union)
                if extra is not None and not extra.isEmpty():
                    for part in self._parts(extra):
                        gaps.append((part, "sliver"))

        gaps = self._dedupe(gaps)

        if max_area > 0:
            before = len(gaps)
            gaps = [(g, o) for g, o in gaps if g.area() <= max_area]
            if before != len(gaps):
                feedback.pushInfo(
                    "%d gap(s) larger than %s left alone." % (before - len(gaps), max_area)
                )

        feedback.setProgress(35)
        feedback.pushInfo("%d gap(s) found." % len(gaps))

        additions = {}
        step = 55.0 / len(gaps) if gaps else 0
        for number, (gap, origin) in enumerate(gaps, start=1):
            if feedback.isCanceled():
                break
            candidates = [
                fid for fid in index.intersects(gap.boundingBox())
                if fid in geometries
            ]
            best_fid, best_score = None, 0.0
            for fid in candidates:
                shared = gap.intersection(geometries[fid])
                if shared is None or shared.isEmpty():
                    continue
                score = geometries[fid].area() if mode == MODE_LARGEST else shared.length()
                if score > best_score:
                    best_fid, best_score = fid, score

            if mode != MODE_REPORT and best_fid is not None:
                additions.setdefault(best_fid, []).append(gap)

            if gap_sink is not None:
                gap_feature = QgsFeature(gap_fields)
                gap_feature.setGeometry(gap)
                gap_feature.setAttributes([
                    number, origin, gap.area(), gap.length(), len(candidates),
                    str(best_fid) if best_fid is not None and mode != MODE_REPORT else None,
                ])
                gap_sink.addFeature(gap_feature, QgsFeatureSink.FastInsert)

            feedback.setProgress(int(35 + number * step))

        unassigned = len(gaps) - sum(len(v) for v in additions.values())
        if mode != MODE_REPORT and unassigned:
            feedback.pushWarning(
                "%d gap(s) had no neighbour to give them to and were left open."
                % unassigned
            )

        feedback.pushInfo("Writing output...")
        filled_total = 0
        for fid, feature in features.items():
            out = QgsFeature(out_fields)
            extra = additions.get(fid, [])
            geometry = geometries[fid]
            if extra:
                merged = QgsGeometry.unaryUnion([geometry] + extra)
                if merged is not None and not merged.isEmpty():
                    geometry = merged
                    filled_total += len(extra)
            geometry = QgsGeometry(geometry)
            geometry.convertToMultiType()
            out.setGeometry(geometry)
            out.setAttributes(
                feature.attributes()
                + [len(extra), sum(g.area() for g in extra) if extra else 0.0]
            )
            sink.addFeature(out, QgsFeatureSink.FastInsert)

        feedback.pushInfo(
            "%d gap(s) found, %d filled into %d polygon(s)."
            % (len(gaps), filled_total, len(additions))
        )

        results = {self.OUTPUT: dest_id}
        if gap_sink is not None:
            results[self.OUTPUT_GAPS] = gap_dest_id
        return results

    @staticmethod
    def _dedupe(gaps):
        """Drop empties, and gaps found twice by two different methods."""
        kept = []
        for geometry, origin in gaps:
            area = geometry.area()
            if area <= 0:
                continue
            duplicate = False
            for existing, _ in kept:
                shared = geometry.intersection(existing)
                if (shared is not None and not shared.isEmpty()
                        and shared.area() > 0.5 * area):
                    duplicate = True
                    break
            if not duplicate:
                kept.append((geometry, origin))
        return kept

    @staticmethod
    def _parts(geometry):
        """Split a possibly-multipart geometry into single-part QgsGeometry objects."""
        if geometry.isMultipart():
            return [QgsGeometry.fromPolygonXY(rings)
                    for rings in geometry.asMultiPolygon() if rings]
        polygon = geometry.asPolygon()
        return [QgsGeometry.fromPolygonXY(polygon)] if polygon else []

    @staticmethod
    def _interior_rings(union):
        """Every hole in the dissolved coverage - these are the gaps."""
        if union.isMultipart():
            polygons = union.asMultiPolygon()
        else:
            single = union.asPolygon()
            polygons = [single] if single else []
        holes = []
        for rings in polygons:
            for ring in rings[1:]:
                hole = QgsGeometry.fromPolygonXY([ring])
                if hole is not None and not hole.isEmpty():
                    holes.append(hole)
        return holes

    def name(self):
        return "fillgaps"

    def displayName(self):
        return "Fill gaps between polygons"

    def group(self):
        return "Editing"

    def groupId(self):
        return "editing"

    def shortHelpString(self):
        return (
            "<p>Dissolves the input polygons, treats every hole in the result as a "
            "gap, and gives each gap to a neighbouring polygon so the coverage "
            "closes up.</p>"
            "<p>Supply a <b>boundary</b> layer as well and the tool also finds gaps "
            "along the outside edge - the strip between your polygons and the "
            "parcel or ROW line they are supposed to reach.</p>"
            "<h3>Open-ended slivers</h3>"
            "<p>A gap is only a hole in the dissolved coverage if something "
            "surrounds it. Two polygons side by side with a gap between them "
            "leave a sliver that is open at both ends, and no amount of "
            "dissolving turns that into a hole.</p>"
            "<p>Set <i>Also find open-ended slivers narrower than</i> to catch "
            "those - the tool buffers the coverage out and back in by half that "
            "distance, which closes anything narrower, and takes the difference. "
            "It costs two buffer operations over the whole layer, so leave it at "
            "0 unless you need it.</p>"
            "<h3>Ignore gaps larger than</h3>"
            "<p>The important setting. Leave it at 0 and a genuine courtyard, pond "
            "or unmapped parcel gets swallowed too. Set it to a few square units "
            "and only digitising slivers are filled.</p>"
            "<p><b>Report only</b> writes the gap layer without touching geometry, "
            "which is the safe way to look before you leap.</p>"
            "<p>The output is a new layer; the input is never modified.</p>"
        )

    def createInstance(self):
        return FillGaps()

    def tr(self, string):
        return QCoreApplication.translate("FieldKit", string)
