"""Clip a pile of layers to one boundary, into one GeoPackage, keeping the styles."""

import os
import re

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDistance,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterString,
    QgsVectorFileWriter,
    QgsVectorLayer,
)


class BulkVectorClip(QgsProcessingAlgorithm):
    """The one-boundary, many-layers job, done in a single pass."""

    LAYERS = "LAYERS"
    MASK = "MASK"
    BUFFER = "BUFFER"
    SKIP_EMPTY = "SKIP_EMPTY"
    KEEP_STYLES = "KEEP_STYLES"
    PREFIX = "PREFIX"
    OUTPUT = "OUTPUT"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.LAYERS, "Layers to clip", QgsProcessing.TypeVectorAnyGeometry
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.MASK, "Clip boundary", [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.BUFFER, "Pad the boundary first", defaultValue=0.0,
                parentParameterName=self.MASK
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.SKIP_EMPTY, "Skip layers that clip to nothing", defaultValue=True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.KEEP_STYLES, "Carry the styles across", defaultValue=True
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.PREFIX, "Prefix for the output layer names",
                defaultValue="", optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT, "Output GeoPackage", "GeoPackage (*.gpkg)"
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.parameterAsLayerList(parameters, self.LAYERS, context)
        if not layers:
            raise QgsProcessingException("No layers selected.")
        mask_source = self.parameterAsSource(parameters, self.MASK, context)
        if mask_source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.MASK))

        buffer_distance = self.parameterAsDouble(parameters, self.BUFFER, context)
        skip_empty = self.parameterAsBool(parameters, self.SKIP_EMPTY, context)
        keep_styles = self.parameterAsBool(parameters, self.KEEP_STYLES, context)
        prefix = self.parameterAsString(parameters, self.PREFIX, context) or ""
        path = self.parameterAsFileOutput(parameters, self.OUTPUT, context)

        mask_geometries = [
            f.geometry() for f in mask_source.getFeatures()
            if f.hasGeometry() and not f.geometry().isEmpty()
        ]
        if not mask_geometries:
            raise QgsProcessingException("The clip boundary has no usable geometry.")
        mask = QgsGeometry.unaryUnion(mask_geometries)
        if not mask.isGeosValid():
            repaired = mask.makeValid()
            if repaired is not None and not repaired.isEmpty():
                mask = repaired
        if buffer_distance:
            mask = mask.buffer(buffer_distance, 8)
        mask_crs = mask_source.sourceCrs()

        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError as exc:
                raise QgsProcessingException(
                    "Cannot overwrite %s: %s. Close it in QGIS first." % (path, exc))

        transform_context = context.transformContext()
        used_names = set()
        written = []
        first = True
        step = 100.0 / len(layers)

        for index, layer in enumerate(layers):
            if feedback.isCanceled():
                break
            if not isinstance(layer, QgsVectorLayer):
                feedback.pushWarning("Skipping %s: not a vector layer." % layer.name())
                continue

            clip_geometry = QgsGeometry(mask)
            if layer.crs() != mask_crs:
                transform = QgsCoordinateTransform(mask_crs, layer.crs(), transform_context)
                try:
                    clip_geometry.transform(transform)
                except Exception as exc:  # noqa: BLE001 - report and carry on
                    feedback.pushWarning(
                        "Skipping %s: cannot reproject the boundary into %s (%s)."
                        % (layer.name(), layer.crs().authid(), exc))
                    continue

            name = self._unique_name(prefix + layer.name(), used_names)
            features = []
            request = QgsFeatureRequest().setFilterRect(clip_geometry.boundingBox())
            for feature in layer.getFeatures(request):
                if feedback.isCanceled():
                    break
                geometry = feature.geometry()
                if geometry is None or geometry.isEmpty():
                    continue
                if not geometry.intersects(clip_geometry):
                    continue
                clipped = geometry.intersection(clip_geometry)
                if clipped is None or clipped.isEmpty():
                    continue
                out = QgsFeature(feature)
                out.setGeometry(clipped)
                features.append(out)

            if not features and skip_empty:
                feedback.pushInfo("%s: nothing inside the boundary, skipped."
                                  % layer.name())
                feedback.setProgress(int((index + 1) * step))
                continue

            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = name
            options.fileEncoding = "UTF-8"
            options.actionOnExistingFile = (
                QgsVectorFileWriter.CreateOrOverwriteFile if first
                else QgsVectorFileWriter.CreateOrOverwriteLayer
            )

            writer = QgsVectorFileWriter.create(
                path, layer.fields(), layer.wkbType(), layer.crs(),
                transform_context, options,
            )
            if writer.hasError() != QgsVectorFileWriter.NoError:
                raise QgsProcessingException(
                    "Could not write %s into %s: %s"
                    % (name, path, writer.errorMessage()))
            for feature in features:
                writer.addFeature(feature)
            del writer
            first = False

            feedback.pushInfo("%s -> %s (%d feature(s))"
                              % (layer.name(), name, len(features)))
            written.append((layer, name))
            feedback.setProgress(int((index + 1) * step))

        if not written:
            raise QgsProcessingException(
                "Nothing was written - every layer clipped to nothing.")

        if keep_styles:
            self._copy_styles(path, written, feedback)

        feedback.pushInfo("%d layer(s) written to %s" % (len(written), path))
        return {self.OUTPUT: path}

    @staticmethod
    def _unique_name(name, used):
        """GeoPackage layer names: keep them tidy and never collide."""
        cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_") or "layer"
        if cleaned[0].isdigit():
            cleaned = "_" + cleaned
        candidate, suffix = cleaned, 2
        while candidate.lower() in used:
            candidate = "%s_%d" % (cleaned, suffix)
            suffix += 1
        used.add(candidate.lower())
        return candidate

    @staticmethod
    def _copy_styles(path, written, feedback):
        """Store each source layer's style inside the GeoPackage."""
        for source_layer, name in written:
            try:
                destination = QgsVectorLayer(
                    "%s|layername=%s" % (path, name), name, "ogr")
                if not destination.isValid():
                    continue
                document = QDomDocument()
                source_layer.exportNamedStyle(document)
                ok, message = destination.importNamedStyle(document)
                if not ok:
                    feedback.pushWarning("Style for %s: %s" % (name, message))
                    continue
                destination.saveStyleToDatabase(name, "", True, "")
            except Exception as exc:  # noqa: BLE001 - a style is never worth failing over
                feedback.pushWarning(
                    "Could not store the style for %s (%s). The data is fine."
                    % (name, exc))

    def name(self):
        return "bulkvectorclip"

    def displayName(self):
        return "Bulk vector clip"

    def group(self):
        return "Bulk"

    def groupId(self):
        return "bulk"

    def shortHelpString(self):
        return (
            "<p>Clips every selected layer to one boundary and writes the lot into a "
            "single GeoPackage.</p>"
            "<ul>"
            "<li>The boundary is reprojected per layer, so a project with mixed CRSs "
            "just works.</li>"
            "<li>Styles are stored inside the GeoPackage, so the layers come back "
            "styled when you add them again.</li>"
            "<li>Layers that clip to nothing are skipped instead of writing a pile "
            "of empty layers.</li>"
            "<li><b>Pad the boundary</b> gives you a strip of context outside the "
            "site rather than a hard cut at the property line.</li>"
            "</ul>"
            "<p>Existing output is deleted first, so point it at a new file unless "
            "you mean to replace one.</p>"
        )

    def createInstance(self):
        return BulkVectorClip()

    def tr(self, string):
        return QCoreApplication.translate("FieldKit", string)
