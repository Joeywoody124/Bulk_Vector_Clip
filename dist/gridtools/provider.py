"""The Processing provider that puts the grid tools in the toolbox."""

from qgis.core import QgsProcessingProvider

from .atlas_grid_builder import AtlasGridBuilder
from .renumber_sheets import RenumberSheets
from .sheet_estimator import SheetEstimator

ALGORITHMS = [AtlasGridBuilder, SheetEstimator, RenumberSheets]


class GridToolsProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        for algorithm in ALGORITHMS:
            self.addAlgorithm(algorithm())

    def id(self):
        # Deliberately not "fieldkit", so this can sit alongside the full
        # plugin without the two fighting over algorithm ids.
        return "gridtools"

    def name(self):
        return "Grid Tools"

    def longName(self):
        return "Grid Tools - atlas sheet grids, estimates and renumbering"

    def supportsNonFileBasedOutput(self):
        return True
