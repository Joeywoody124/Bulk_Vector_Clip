"""Field Kit - a QGIS Processing provider for sheet layout, bulk jobs and editing."""


def classFactory(iface):  # noqa: N802 - the name QGIS looks for
    from .plugin import FieldKitPlugin

    return FieldKitPlugin(iface)
