"""How many sheets will this take? Answered before anything is generated."""

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterDistance,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
)

from ..core import paper
from . import _grid


class SheetEstimator(QgsProcessingAlgorithm):
    """Sheet counts across a ladder of scales, without creating a single layer."""

    COVERAGE = "COVERAGE"
    BUFFER = "BUFFER"
    PAPER = "PAPER"
    ORIENTATION = "ORIENTATION"
    MARGIN = "MARGIN"
    SCALES = "SCALES"
    OVERLAP = "OVERLAP"
    ANCHOR = "ANCHOR"
    ROTATION = "ROTATION"
    MIN_COVERAGE = "MIN_COVERAGE"
    UNITS = "UNITS"
    OUTPUT_HTML = "OUTPUT_HTML"

    def initAlgorithm(self, config=None):
        add = self.addParameter
        add(QgsProcessingParameterFeatureSource(
            self.COVERAGE, "Coverage area", [QgsProcessing.TypeVectorPolygon]))
        add(QgsProcessingParameterString(
            self.SCALES, "Scales to try (comma separated)",
            defaultValue="1\"=20',1\"=30',1\"=40',1\"=50',1\"=100',1\"=200'"))
        add(QgsProcessingParameterEnum(
            self.PAPER, "Paper size", paper.PAPER_NAMES,
            defaultValue=paper.PAPER_NAMES.index("ARCH D (24x36)")))
        add(QgsProcessingParameterEnum(
            self.ORIENTATION, "Orientation", _grid.ORIENTATION_LABELS, defaultValue=0))
        add(QgsProcessingParameterNumber(
            self.MARGIN, "Margin around the map, in mm",
            QgsProcessingParameterNumber.Double, defaultValue=25.4, minValue=0.0))
        add(QgsProcessingParameterNumber(
            self.OVERLAP, "Overlap between sheets, % of sheet",
            QgsProcessingParameterNumber.Double, defaultValue=5.0,
            minValue=0.0, maxValue=49.0))
        add(QgsProcessingParameterEnum(
            self.ROTATION, "Rotation", _grid.ROTATION_LABELS, defaultValue=0))
        add(QgsProcessingParameterEnum(
            self.ANCHOR, "Where the grid starts", _grid.ANCHOR_LABELS, defaultValue=0))
        add(QgsProcessingParameterNumber(
            self.MIN_COVERAGE, "Drop sheets covering less than this % of the sheet",
            QgsProcessingParameterNumber.Double, defaultValue=0.5,
            minValue=0.0, maxValue=100.0))
        add(QgsProcessingParameterDistance(
            self.BUFFER, "Pad the coverage first", defaultValue=0.0,
            parentParameterName=self.COVERAGE, minValue=0.0))
        add(QgsProcessingParameterEnum(
            self.UNITS, "Map units", _grid.UNIT_LABELS, defaultValue=0))
        add(QgsProcessingParameterFileDestination(
            self.OUTPUT_HTML, "Report", "HTML files (*.html)",
            optional=True, createByDefault=False))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.COVERAGE, context)
        if source is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.COVERAGE))

        units = _grid.metres_per_unit(
            source.sourceCrs(), self.parameterAsEnum(parameters, self.UNITS, context))
        coverage = _grid.dissolved_coverage(
            source, self.parameterAsDouble(parameters, self.BUFFER, context))
        coverage_area = coverage.area()

        try:
            denominators = paper.parse_scale_list(
                self.parameterAsString(parameters, self.SCALES, context))
        except ValueError as exc:
            raise QgsProcessingException(str(exc))

        paper_name = paper.PAPER_NAMES[
            self.parameterAsEnum(parameters, self.PAPER, context)]
        landscape = self.parameterAsEnum(parameters, self.ORIENTATION, context) == 0
        margin = self.parameterAsDouble(parameters, self.MARGIN, context)
        overlap_pct = self.parameterAsDouble(parameters, self.OVERLAP, context)
        anchor = _grid.anchor_for(self.parameterAsEnum(parameters, self.ANCHOR, context))
        min_coverage = self.parameterAsDouble(parameters, self.MIN_COVERAGE, context)

        theta, centre = _grid.alignment(
            coverage, self.parameterAsEnum(parameters, self.ROTATION, context))

        imperial = abs(units - paper.METRES_PER_UNIT["m"]) > 1e-9
        rows = []
        for index, denominator in enumerate(denominators):
            if feedback.isCanceled():
                break
            try:
                cell_w, cell_h = paper.sheet_size(
                    paper.PAPER_SIZES[paper_name], margin, denominator, units,
                    landscape=landscape)
                _, cells = _grid.build_cells(
                    coverage, cell_w, cell_h,
                    cell_w * overlap_pct / 100.0, cell_h * overlap_pct / 100.0,
                    anchor, snap_to=0.0, theta=theta, centre=centre,
                    cull=True, min_coverage_pct=min_coverage,
                )
            except ValueError as exc:
                raise QgsProcessingException(str(exc))

            covered = sum(c["cov_pct"] for c in cells) / len(cells) if cells else 0.0
            rows.append({
                "scale": paper.format_scale(denominator, imperial=imperial),
                "width": cell_w,
                "height": cell_h,
                "sheets": len(cells),
                "fill": covered,
            })
            feedback.setProgress(int((index + 1) * 100.0 / len(denominators)))

        if not rows:
            raise QgsProcessingException("No scales were evaluated.")

        feedback.pushInfo("")
        feedback.pushInfo("%s %s, %.1f mm margins, %.0f%% overlap"
                          % (paper_name, "landscape" if landscape else "portrait",
                             margin, overlap_pct))
        feedback.pushInfo("Coverage area: %.0f square map units" % coverage_area)
        if theta:
            feedback.pushInfo("Grid rotated %.2f degrees to fit the site" % theta)
        feedback.pushInfo("")
        feedback.pushInfo("%-14s %-24s %8s %10s" % ("Scale", "Sheet covers",
                                                    "Sheets", "Avg fill"))
        for row in rows:
            feedback.pushInfo("%-14s %-24s %8d %9.0f%%" % (
                row["scale"],
                "%.0f x %.0f" % (row["width"], row["height"]),
                row["sheets"], row["fill"]))
        feedback.pushInfo("")

        best = min(rows, key=lambda r: r["sheets"])
        feedback.pushInfo(
            "Fewest sheets: %s at %d sheet(s)." % (best["scale"], best["sheets"]))

        results = {"SHEET_COUNTS": {r["scale"]: r["sheets"] for r in rows}}
        html_path = self.parameterAsFileOutput(parameters, self.OUTPUT_HTML, context)
        if html_path:
            self._write_html(html_path, paper_name, landscape, margin, overlap_pct,
                             theta, coverage_area, rows)
            results[self.OUTPUT_HTML] = html_path
        return results

    @staticmethod
    def _write_html(path, paper_name, landscape, margin, overlap_pct, theta,
                    coverage_area, rows):
        cells = "\n".join(
            "<tr><td>{scale}</td><td>{width:.0f} &times; {height:.0f}</td>"
            "<td style='text-align:right'>{sheets}</td>"
            "<td style='text-align:right'>{fill:.0f}%</td></tr>".format(**row)
            for row in rows
        )
        html = """<html><head><meta charset="utf-8"><style>
body {{ font-family: sans-serif; margin: 2em; }}
table {{ border-collapse: collapse; margin-top: 1em; }}
th, td {{ border: 1px solid #ccc; padding: 6px 12px; }}
th {{ background: #f0f0f0; text-align: left; }}
</style></head><body>
<h2>Sheet estimate</h2>
<p>{paper} {orientation}, {margin:.1f} mm margins, {overlap:.0f}% overlap{rotation}<br>
Coverage area: {area:,.0f} square map units</p>
<table><tr><th>Scale</th><th>Sheet covers (map units)</th><th>Sheets</th>
<th>Avg fill</th></tr>
{rows}
</table></body></html>""".format(
            paper=paper_name,
            orientation="landscape" if landscape else "portrait",
            margin=margin, overlap=overlap_pct,
            rotation=(", grid rotated %.2f&deg;" % theta) if theta else "",
            area=coverage_area, rows=cells,
        )
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(html)

    def name(self):
        return "sheetestimator"

    def displayName(self):
        return "Sheet count estimator"

    def group(self):
        return "Sheets"

    def groupId(self):
        return "sheets"

    def shortHelpString(self):
        return (
            "<p>Answers \"how many sheets is this at 1\"=50'?\" for a whole ladder of "
            "scales at once, and creates nothing.</p>"
            "<p>The counts come from actually laying each grid out and culling the "
            "empty cells - not from dividing the area by the sheet size, which is "
            "wrong by half on any site that is not a rectangle.</p>"
            "<p><b>Avg fill</b> is how much of a typical sheet has coverage on it. A "
            "low number means you are printing a lot of white paper and should look "
            "at a smaller scale or a rotated grid.</p>"
            "<p>Every setting here matches the Atlas grid builder, so once you like a "
            "row in the table you can copy the settings straight across.</p>"
        )

    def createInstance(self):
        return SheetEstimator()

    def tr(self, string):
        return QCoreApplication.translate("FieldKit", string)
