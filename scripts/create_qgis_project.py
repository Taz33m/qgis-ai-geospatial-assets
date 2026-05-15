#!/usr/bin/env python3
"""Create a styled QGIS project and QGIS-rendered map export."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsMarkerSymbol,
    QgsProject,
    QgsSimpleMarkerSymbolLayerBase,
    QgsVectorLayer,
)


ROOT = Path(__file__).resolve().parents[1]
GPKG = ROOT / "data" / "processed" / "lower_manhattan_ai_assets.gpkg"
PROJECT_PATH = ROOT / "qgis" / "lower_manhattan_ai_assets.qgz"
QGIS_RENDER_PATH = ROOT / "screenshots" / "06_qgis_project_render.png"
CRS_WORKING = "EPSG:2263"

LAYER_ORDER = [
    "land_use_zones",
    "water",
    "green_space",
    "parking",
    "buildings",
    "roads",
    "sidewalks",
    "crosswalks",
    "points_of_interest",
    "qa_issues",
    "roi",
]

DISPLAY_NAMES = {
    "land_use_zones": "Land Use Zones",
    "water": "Water",
    "green_space": "Green Space",
    "parking": "Parking Review Assets",
    "buildings": "Official Building Footprints",
    "roads": "Road Network",
    "sidewalks": "Sidewalk / Pedestrian Network",
    "crosswalks": "Crosswalk Candidates",
    "points_of_interest": "Points of Interest",
    "qa_issues": "QA Issues",
    "roi": "Study Area ROI",
}


def rgba(hex_color: str, alpha: int = 255) -> QColor:
    color = QColor(hex_color)
    color.setAlpha(alpha)
    return color


def set_polygon_style(layer: QgsVectorLayer, fill: str, stroke: str, opacity: float, width: str = "0.4") -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": fill,
            "outline_color": stroke,
            "outline_width": width,
            "outline_width_unit": "MM",
        }
    )
    symbol.setOpacity(opacity)
    layer.setRenderer(layer.renderer().clone())
    layer.renderer().setSymbol(symbol)


def set_line_style(layer: QgsVectorLayer, color: str, width: str, opacity: float = 1.0) -> None:
    symbol = QgsLineSymbol.createSimple(
        {
            "color": color,
            "line_width": width,
            "line_width_unit": "MM",
        }
    )
    symbol.setOpacity(opacity)
    layer.setRenderer(layer.renderer().clone())
    layer.renderer().setSymbol(symbol)


def set_point_style(layer: QgsVectorLayer, color: str, size: str, opacity: float = 1.0, shape: str = "circle") -> None:
    symbol = QgsMarkerSymbol.createSimple(
        {
            "name": shape,
            "color": color,
            "outline_color": "#111111",
            "outline_width": "0.1",
            "size": size,
            "size_unit": "MM",
        }
    )
    if shape == "cross":
        symbol.symbolLayer(0).setShape(QgsSimpleMarkerSymbolLayerBase.Cross)
    symbol.setOpacity(opacity)
    layer.setRenderer(layer.renderer().clone())
    layer.renderer().setSymbol(symbol)


def style_layer(layer_name: str, layer: QgsVectorLayer) -> None:
    if layer_name == "land_use_zones":
        set_polygon_style(layer, "#7367f0", "#b8b3ff", 0.22, "0.25")
    elif layer_name == "water":
        set_polygon_style(layer, "#4da3ff", "#9dd0ff", 0.55, "0.35")
    elif layer_name == "green_space":
        set_polygon_style(layer, "#61d394", "#8ff0b4", 0.45, "0.28")
    elif layer_name == "parking":
        set_polygon_style(layer, "#f6bd60", "#ffd28a", 0.5, "0.35")
    elif layer_name == "buildings":
        set_polygon_style(layer, "#cdd2dc", "#ffffff", 0.85, "0.12")
    elif layer_name == "roads":
        set_line_style(layer, "#111317", "0.85", 0.95)
    elif layer_name == "sidewalks":
        set_line_style(layer, "#ff9f1c", "0.32", 0.78)
    elif layer_name == "crosswalks":
        set_line_style(layer, "#fff275", "0.5", 0.85)
    elif layer_name == "points_of_interest":
        set_point_style(layer, "#ff5d8f", "1.0", 0.42)
    elif layer_name == "qa_issues":
        set_point_style(layer, "#ff2d2d", "3.0", 0.95, "cross")
    elif layer_name == "roi":
        set_polygon_style(layer, "0,0,0,0", "#ffffff", 0.9, "0.5")


def main() -> None:
    PROJECT_PATH.parent.mkdir(parents=True, exist_ok=True)
    QGIS_RENDER_PATH.parent.mkdir(parents=True, exist_ok=True)

    qgs = QgsApplication([], False)
    qgs.initQgis()

    try:
        project = QgsProject.instance()
        project.clear()
        project.setCrs(QgsCoordinateReferenceSystem(CRS_WORKING))
        project.writeEntry("Paths", "/Absolute", False)
        project.setTitle("AI-Ready Lower Manhattan Geospatial Assets")

        loaded_layers: dict[str, QgsVectorLayer] = {}
        for layer_name in LAYER_ORDER:
            uri = f"{GPKG}|layername={layer_name}"
            vector_layer = QgsVectorLayer(uri, DISPLAY_NAMES[layer_name], "ogr")
            if not vector_layer.isValid():
                raise RuntimeError(f"Could not load {layer_name} from {GPKG}")
            style_layer(layer_name, vector_layer)
            project.addMapLayer(vector_layer)
            loaded_layers[layer_name] = vector_layer

        root = project.layerTreeRoot()
        order = [loaded_layers[name] for name in reversed(LAYER_ORDER)]
        root.setHasCustomLayerOrder(True)
        root.setCustomLayerOrder(order)

        if not project.write(str(PROJECT_PATH)):
            raise RuntimeError(f"Could not write {PROJECT_PATH}")

        settings = QgsMapSettings()
        render_layers = [loaded_layers[name] for name in LAYER_ORDER if name != "roi"]
        settings.setLayers(render_layers)
        settings.setDestinationCrs(QgsCoordinateReferenceSystem(CRS_WORKING))
        extent = loaded_layers["roi"].extent()
        extent.grow(extent.width() * 0.02)
        settings.setExtent(extent)
        settings.setOutputSize(QSize(2200, 1650))
        settings.setBackgroundColor(rgba("#071013"))

        job = QgsMapRendererParallelJob(settings)
        job.start()
        job.waitForFinished()
        image = job.renderedImage()
        if image.isNull():
            raise RuntimeError("QGIS render produced a null image")
        image.save(str(QGIS_RENDER_PATH), "PNG")
        print(f"Wrote {PROJECT_PATH}")
        print(f"Wrote {QGIS_RENDER_PATH}")
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    main()
