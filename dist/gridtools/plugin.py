"""Plugin entry point: register the Processing provider, and take it away again."""

from qgis.core import QgsApplication

from .provider import GridToolsProvider


class GridToolsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initGui(self):
        # Hold the reference: the registry does not own the Python object, and
        # a garbage-collected provider registers nothing and reports no error.
        self.provider = GridToolsProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
