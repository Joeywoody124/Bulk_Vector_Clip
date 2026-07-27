"""Grid Tools - atlas sheet grids for QGIS."""


def classFactory(iface):  # noqa: N802 - the name QGIS looks for
    from .plugin import GridToolsPlugin

    return GridToolsPlugin(iface)
