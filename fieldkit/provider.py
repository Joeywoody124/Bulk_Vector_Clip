"""The Processing provider that puts every Field Kit tool in the toolbox."""

from qgis.core import QgsProcessingProvider

from .algs.atlas_grid_builder import AtlasGridBuilder
from .algs.bulk_vector_clip import BulkVectorClip
from .algs.close_undershoots import CloseUndershoots
from .algs.erase_overlaps import EraseOverlaps
from .algs.fill_gaps import FillGaps
from .algs.renumber_sheets import RenumberSheets
from .algs.row_from_centerline import RightOfWayFromCenterline
from .algs.sheet_estimator import SheetEstimator
from .algs.snap_and_verify import SnapAndVerify

ALGORITHMS = [
    RightOfWayFromCenterline,
    FillGaps,
    EraseOverlaps,
    SnapAndVerify,
    CloseUndershoots,
    AtlasGridBuilder,
    SheetEstimator,
    RenumberSheets,
    BulkVectorClip,
]


class FieldKitProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        for algorithm in ALGORITHMS:
            self.addAlgorithm(algorithm())

    def id(self):
        return "fieldkit"

    def name(self):
        return "Field Kit"

    def longName(self):
        return "Field Kit - sheets, bulk jobs and polygon editing"

    def supportsNonFileBasedOutput(self):
        return True
