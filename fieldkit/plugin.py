"""Plugin entry point: register the Processing provider, and take it away again."""

from qgis.core import QgsApplication

from .provider import FieldKitProvider


class FieldKitPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initGui(self):
        self.provider = FieldKitProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
