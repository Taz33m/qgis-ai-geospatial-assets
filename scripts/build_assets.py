#!/usr/bin/env python3
"""Build the Lower Manhattan AI-ready geospatial asset package.

The script pulls public NYC/NYS building footprints plus OpenStreetMap context,
normalizes all feature layers to a shared annotation schema, writes a GeoPackage,
exports WGS84 GeoJSON, and creates portfolio screenshots.
"""

from __future__ import annotations

import json
import math
import textwrap
from collections import Counter, OrderedDict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import requests
from matplotlib.patches import Patch
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, shape
from shapely.ops import polygonize, transform
from shapely.validation import make_valid


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
GEOJSON_DIR = ROOT / "exports" / "geojson"
DOCS_DIR = ROOT / "docs"
SCREENSHOTS_DIR = ROOT / "screenshots"
MAPS_DIR = ROOT / "maps"

TODAY = date.today().isoformat()
CRS_WGS84 = "EPSG:4326"
CRS_WORKING = "EPSG:2263"

# Compact Battery Park City / World Trade Center / West Street ROI.
BBOX = {
    "west": -74.0195,
    "south": 40.7070,
    "east": -74.0050,
    "north": 40.7165,
}

ROI_POLYGON = Polygon(
    [
        (BBOX["west"], BBOX["south"]),
        (BBOX["east"], BBOX["south"]),
        (BBOX["east"], BBOX["north"]),
        (BBOX["west"], BBOX["north"]),
        (BBOX["west"], BBOX["south"]),
    ]
)

COMMON_FIELDS = [
    "asset_id",
    "feature_type",
    "label",
    "source",
    "source_id",
    "confidence",
    "review_status",
    "qa_flag",
    "notes",
    "last_updated",
]

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
]

OSM_POLYGON_KEYS = {
    "building",
    "landuse",
    "leisure",
    "natural",
    "amenity",
    "tourism",
    "historic",
    "shop",
}


def fetch_json(url: str, params: dict[str, Any] | None = None, timeout: int = 90) -> Any:
    headers = {"User-Agent": "qgis-ai-geospatial-assets/1.0 (portfolio research)"}
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_building_footprints() -> dict[str, Any]:
    url = (
        "https://gisservices.its.ny.gov/arcgis/rest/services/"
        "BuildingFootprints/FeatureServer/2/query"
    )
    params = {
        "f": "geojson",
        "where": "1=1",
        "geometry": f"{BBOX['west']},{BBOX['south']},{BBOX['east']},{BBOX['north']}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
    }
    data = fetch_json(url, params=params)
    (RAW_DIR / "nys_building_footprints_bbox.geojson").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )
    return data


def fetch_osm_context() -> dict[str, Any]:
    south, west, north, east = BBOX["south"], BBOX["west"], BBOX["north"], BBOX["east"]
    bbox = f"({south},{west},{north},{east})"
    queries = [
        f"""
        [out:json][timeout:45];
        (
          node["amenity"]{bbox};
          node["tourism"]{bbox};
          node["historic"]{bbox};
          node["shop"]{bbox};
          node["highway"="crossing"]{bbox};
        );
        out body;
        """,
        f"""
        [out:json][timeout:45];
        (
          way["highway"]{bbox};
          way["footway"]{bbox};
        );
        out body geom;
        """,
        f"""
        [out:json][timeout:45];
        (
          way["amenity"="parking"]{bbox};
          way["leisure"~"^(park|garden|pitch|playground)$"]{bbox};
          way["landuse"]{bbox};
          way["natural"="water"]{bbox};
          way["waterway"="riverbank"]{bbox};
          way["amenity"]{bbox};
          way["tourism"]{bbox};
          way["historic"]{bbox};
          way["shop"]{bbox};
        );
        out body geom;
        """,
    ]
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    elements_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for query in queries:
        last_error: Exception | None = None
        for endpoint in endpoints:
            try:
                response = fetch_json(endpoint, params={"data": query}, timeout=75)
                for element in response.get("elements", []):
                    elements_by_key[(element["type"], element["id"])] = element
                last_error = None
                break
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error

    data = {
        "version": 0.6,
        "generator": "combined Overpass API queries",
        "elements": list(elements_by_key.values()),
    }
    (RAW_DIR / "osm_overpass_lower_manhattan.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )
    return data


def drop_z(geometry):
    if geometry is None or geometry.is_empty:
        return geometry
    return transform(lambda x, y, z=None: (x, y), geometry)


def tags_for(element: dict[str, Any]) -> dict[str, str]:
    return element.get("tags", {}) or {}


def way_geometry(element: dict[str, Any]):
    coords = [(node["lon"], node["lat"]) for node in element.get("geometry", [])]
    if len(coords) < 2:
        return None
    closed = coords[0] == coords[-1] and len(coords) >= 4
    if closed and is_polygon_like(tags_for(element)):
        return Polygon(coords)
    return LineString(coords)


def relation_geometry(element: dict[str, Any]):
    tags = tags_for(element)
    if not is_polygon_like(tags):
        return None

    closed_polygons: list[Polygon] = []
    lines: list[LineString] = []
    for member in element.get("members", []):
        if member.get("role") not in ("outer", ""):
            continue
        geom = member.get("geometry") or []
        coords = [(node["lon"], node["lat"]) for node in geom]
        if len(coords) < 2:
            continue
        if coords[0] == coords[-1] and len(coords) >= 4:
            try:
                closed_polygons.append(Polygon(coords))
            except Exception:
                pass
        else:
            lines.append(LineString(coords))

    polygons = closed_polygons[:]
    if lines:
        try:
            merged = MultiLineString(lines)
            polygons.extend(list(polygonize(merged)))
        except Exception:
            pass

    if not polygons:
        return None
    if len(polygons) == 1:
        return polygons[0]
    return MultiPolygon(polygons)


def element_geometry(element: dict[str, Any]):
    element_type = element.get("type")
    if element_type == "node":
        return Point(element["lon"], element["lat"])
    if element_type == "way":
        return way_geometry(element)
    if element_type == "relation":
        return relation_geometry(element)
    return None


def is_polygon_like(tags: dict[str, str]) -> bool:
    if tags.get("area") == "yes":
        return True
    return bool(OSM_POLYGON_KEYS.intersection(tags.keys()))


def source_id(element: dict[str, Any]) -> str:
    return f"osm:{element.get('type')}/{element.get('id')}"


def clean_label(tags: dict[str, str], fallback: str) -> str:
    for key in ("name", "official_name", "operator", "brand", "highway", "amenity", "leisure"):
        value = tags.get(key)
        if value:
            return str(value).replace("_", " ").title()
    return fallback


def asset_record(
    geometry,
    layer: str,
    label: str,
    source: str,
    source_id_value: str,
    confidence: str = "high",
    review_status: str = "reviewed",
    qa_flag: str = "pass",
    notes: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "geometry": geometry,
        "feature_type": layer,
        "label": label[:120],
        "source": source[:80],
        "source_id": str(source_id_value)[:120],
        "confidence": confidence,
        "review_status": review_status,
        "qa_flag": qa_flag,
        "notes": notes[:240],
        "last_updated": TODAY,
    }
    if extra:
        record.update(extra)
    return record


def make_gdf(layer: str, records: list[dict[str, Any]]) -> gpd.GeoDataFrame:
    if not records:
        gdf = gpd.GeoDataFrame(columns=COMMON_FIELDS + ["geometry"], geometry="geometry", crs=CRS_WGS84)
    else:
        gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=CRS_WGS84)

    gdf = gdf[gdf.geometry.notna()].copy()
    if not gdf.empty:
        gdf["geometry"] = gdf.geometry.apply(drop_z)
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
        gdf["geometry"] = gdf.geometry.apply(lambda geom: make_valid(geom) if not geom.is_valid else geom)
        gdf = gpd.clip(gdf, gpd.GeoDataFrame(geometry=[ROI_POLYGON], crs=CRS_WGS84))

    for field in COMMON_FIELDS:
        if field not in gdf.columns:
            gdf[field] = ""

    gdf = gdf.reset_index(drop=True)
    prefix = "".join(part[0] for part in layer.split("_")).upper()
    gdf["asset_id"] = [f"{prefix}-{idx + 1:04d}" for idx in range(len(gdf))]
    ordered = COMMON_FIELDS + [
        col for col in gdf.columns if col not in set(COMMON_FIELDS + ["geometry"])
    ] + ["geometry"]
    return gdf[ordered]


def build_buildings(data: dict[str, Any]) -> gpd.GeoDataFrame:
    records = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        geom = shape(feature.get("geometry"))
        sid = props.get("OBJECTID") or props.get("SOURCEID") or feature.get("id")
        records.append(
            asset_record(
                geom,
                "building",
                "NYC Building Footprint",
                "NYS ITS / NYC OpenData Building Footprints",
                sid,
                "high",
                "reviewed",
                "pass",
                "Official footprint clipped to ROI; source vintage retained in raw download.",
                {
                    "source_date": props.get("SOURCEDATE", ""),
                    "source_provider": props.get("NYSGEO_SOURCE", ""),
                },
            )
        )
    return make_gdf("buildings", records)


def build_from_osm(osm: dict[str, Any]) -> dict[str, gpd.GeoDataFrame]:
    roads, sidewalks, crosswalk_lines, crosswalk_points = [], [], [], []
    parking, green, water, poi = [], [], [], []

    for element in osm.get("elements", []):
        tags = tags_for(element)
        geom = element_geometry(element)
        if geom is None or geom.is_empty:
            continue

        osm_id = source_id(element)
        label = clean_label(tags, "OSM Feature")

        highway = tags.get("highway", "")
        footway = tags.get("footway", "")
        if highway and highway not in {"footway", "path", "steps", "cycleway"}:
            if geom.geom_type in {"LineString", "MultiLineString"}:
                roads.append(
                    asset_record(
                        geom,
                        "road",
                        label,
                        "OpenStreetMap Overpass",
                        osm_id,
                        "high",
                        "reviewed",
                        "pass",
                        f"OSM highway={highway}; normalized for asset workflow.",
                        {"osm_class": highway},
                    )
                )

        if highway in {"footway", "path", "steps", "pedestrian"} and footway != "crossing":
            if geom.geom_type in {"LineString", "MultiLineString"}:
                status = "reviewed" if tags.get("footway") == "sidewalk" else "needs_review"
                sidewalks.append(
                    asset_record(
                        geom,
                        "sidewalk",
                        label,
                        "OpenStreetMap Overpass",
                        osm_id,
                        "medium" if status == "needs_review" else "high",
                        status,
                        "review" if status == "needs_review" else "pass",
                        f"OSM pedestrian geometry; footway={footway or 'not specified'}.",
                        {"osm_class": highway, "osm_footway": footway},
                    )
                )

        if footway == "crossing" or tags.get("crossing") or highway == "crossing":
            if geom.geom_type in {"LineString", "MultiLineString"}:
                crosswalk_lines.append(
                    asset_record(
                        geom,
                        "crosswalk",
                        label,
                        "OpenStreetMap Overpass",
                        osm_id,
                        "high",
                        "reviewed",
                        "pass",
                        "OSM crossing line retained as crosswalk asset.",
                    )
                )
            elif geom.geom_type == "Point":
                crosswalk_points.append((geom, label, osm_id))

        if tags.get("amenity") == "parking" or "parking" in tags:
            if geom.geom_type in {"Polygon", "MultiPolygon"}:
                parking.append(
                    asset_record(
                        geom,
                        "parking",
                        label,
                        "OpenStreetMap Overpass",
                        osm_id,
                        "medium",
                        "needs_review",
                        "review",
                        "Parking polygon from OSM; confirm surface/garage status if used for training.",
                    )
                )
            elif geom.geom_type == "Point":
                parking.append(
                    asset_record(
                        geom,
                        "parking",
                        label,
                        "OpenStreetMap Overpass",
                        osm_id,
                        "low",
                        "needs_review",
                        "review",
                        "Parking point will be buffered into a small review polygon.",
                    )
                )

        if tags.get("leisure") in {"park", "garden", "playground", "pitch"} or tags.get("landuse") in {
            "grass",
            "recreation_ground",
            "village_green",
        }:
            if geom.geom_type in {"Polygon", "MultiPolygon"}:
                green.append(
                    asset_record(
                        geom,
                        "green_space",
                        label,
                        "OpenStreetMap Overpass",
                        osm_id,
                        "high",
                        "reviewed",
                        "pass",
                        "OSM open-space polygon normalized for the asset schema.",
                    )
                )

        if tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
            if geom.geom_type in {"Polygon", "MultiPolygon"}:
                water.append(
                    asset_record(
                        geom,
                        "water",
                        label,
                        "OpenStreetMap Overpass",
                        osm_id,
                        "high",
                        "reviewed",
                        "pass",
                        "OSM water polygon clipped to ROI.",
                    )
                )

        if any(k in tags for k in ("amenity", "tourism", "historic", "shop")):
            point = geom if geom.geom_type == "Point" else geom.representative_point()
            poi_type = tags.get("amenity") or tags.get("tourism") or tags.get("historic") or tags.get("shop")
            poi.append(
                asset_record(
                    point,
                    "point_of_interest",
                    label,
                    "OpenStreetMap Overpass",
                    osm_id,
                    "medium",
                    "reviewed",
                    "pass",
                    f"POI normalized from OSM tag {poi_type}.",
                    {"poi_type": poi_type},
                )
            )

    layers = {
        "roads": make_gdf("roads", roads),
        "sidewalks": make_gdf("sidewalks", sidewalks),
        "crosswalks": make_gdf("crosswalks", crosswalk_lines),
        "parking": make_gdf("parking", parking),
        "green_space": make_gdf("green_space", green),
        "water": make_gdf("water", water),
        "points_of_interest": make_gdf("points_of_interest", poi),
    }

    layers["crosswalks"] = add_crosswalk_points(layers["crosswalks"], crosswalk_points)
    layers["parking"] = buffer_parking_points(layers["parking"])
    layers["water"] = ensure_hudson_water(layers["water"])
    return layers


def add_crosswalk_points(crosswalks: gpd.GeoDataFrame, points: list[tuple[Point, str, str]]) -> gpd.GeoDataFrame:
    if not points:
        return crosswalks
    point_gdf = gpd.GeoDataFrame(
        [
            asset_record(
                point,
                "crosswalk",
                label,
                "OpenStreetMap Overpass",
                sid,
                "medium",
                "needs_review",
                "review",
                "OSM crossing node converted to a short review line for map QA.",
            )
            for point, label, sid in points
        ],
        geometry="geometry",
        crs=CRS_WGS84,
    ).to_crs(CRS_WORKING)
    point_gdf["geometry"] = point_gdf.geometry.apply(
        lambda p: LineString([(p.x - 18, p.y), (p.x + 18, p.y)])
    )
    point_gdf = point_gdf.to_crs(CRS_WGS84)
    merged = pd.concat([crosswalks, make_gdf("crosswalks", point_gdf.to_dict("records"))], ignore_index=True)
    return make_gdf("crosswalks", merged.to_dict("records"))


def buffer_parking_points(parking: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if parking.empty:
        return parking
    projected = parking.to_crs(CRS_WORKING)
    projected["geometry"] = projected.geometry.apply(
        lambda geom: geom.buffer(28, cap_style=3) if geom.geom_type == "Point" else geom
    )
    return make_gdf("parking", projected.to_crs(CRS_WGS84).to_dict("records"))


def ensure_hudson_water(water: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    manual = asset_record(
        Polygon(
            [
                (BBOX["west"], BBOX["south"]),
                (-74.01705, BBOX["south"]),
                (-74.01705, BBOX["north"]),
                (BBOX["west"], BBOX["north"]),
                (BBOX["west"], BBOX["south"]),
            ]
        ),
        "water",
        "Hudson River ROI Edge",
        "Manual QGIS-style digitization from public basemap context",
        "manual:hudson-west-edge",
        "medium",
        "needs_review",
        "review",
        "Generalized water boundary added so the training package includes water/shoreline QA.",
    )
    merged = pd.concat([water, make_gdf("water", [manual])], ignore_index=True)
    return make_gdf("water", merged.to_dict("records"))


def build_land_use_zones() -> gpd.GeoDataFrame:
    zone_specs = [
        (
            "Battery Park City Waterfront Mixed Use",
            "mixed_use_residential_waterfront",
            [(-74.0193, 40.7090), (-74.01465, 40.7090), (-74.01465, 40.71635), (-74.0193, 40.71635)],
        ),
        (
            "World Trade Center Commercial Civic Core",
            "commercial_civic",
            [(-74.01465, 40.70955), (-74.00915, 40.70955), (-74.00915, 40.71375), (-74.01465, 40.71375)],
        ),
        (
            "Financial District Commercial Blocks",
            "commercial_office",
            [(-74.0116, 40.7071), (-74.00515, 40.7071), (-74.00515, 40.71105), (-74.0116, 40.71105)],
        ),
        (
            "Civic Transit And Institutional Edge",
            "civic_transport",
            [(-74.0137, 40.7130), (-74.00535, 40.7130), (-74.00535, 40.71635), (-74.0137, 40.71635)],
        ),
        (
            "Hudson River Open Water",
            "waterfront_open_space",
            [(-74.0195, 40.7070), (-74.01705, 40.7070), (-74.01705, 40.7165), (-74.0195, 40.7165)],
        ),
    ]

    records = []
    for label, zone_type, coords in zone_specs:
        records.append(
            asset_record(
                Polygon(coords + [coords[0]]),
                "land_use_zone",
                label,
                "Manual QGIS-style interpretation from NYC/OSM context",
                f"manual:{zone_type}",
                "medium",
                "needs_review",
                "review",
                "Generalized portfolio-scale land-use zone for AI labeling workflow demonstration.",
                {"zone_class": zone_type},
            )
        )
    return make_gdf("land_use_zones", records)


def build_qa_issues(layers: dict[str, gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    issue_specs = [
        (
            -74.01755,
            40.71455,
            "generalized_water_boundary",
            "medium",
            "water",
            "manual:hudson-west-edge",
            "Manual Hudson edge is generalized and should be cross-checked before model training.",
        ),
        (
            -74.01245,
            40.71165,
            "manual_land_use_boundary",
            "medium",
            "land_use_zones",
            "manual:commercial_civic",
            "Land-use polygons are portfolio-scale labels, not legal zoning boundaries.",
        ),
        (
            -74.0112,
            40.7133,
            "pedestrian_network_completeness",
            "high",
            "sidewalks",
            "osm:footway/path",
            "OSM footway density is strong near WTC but requires human review for every sidewalk edge.",
        ),
        (
            -74.0101,
            40.7112,
            "crosswalk_node_conversion",
            "low",
            "crosswalks",
            "osm:node-crossing",
            "Node crossings are rendered as short review lines and should be aligned to curb geometry.",
        ),
        (
            -74.0156,
            40.7102,
            "parking_geometry_uncertainty",
            "low",
            "parking",
            "osm:amenity=parking",
            "Parking assets may represent garage access instead of surface lots in dense Lower Manhattan.",
        ),
    ]

    records = []
    for lon, lat, issue_type, severity, affected_layer, feature_ref, note in issue_specs:
        records.append(
            asset_record(
                Point(lon, lat),
                "qa_issue",
                issue_type.replace("_", " ").title(),
                "Internal QA review",
                f"qa:{issue_type}",
                "high",
                "open",
                "review",
                note,
                {
                    "issue_type": issue_type,
                    "severity": severity,
                    "affected_layer": affected_layer,
                    "feature_ref": feature_ref,
                },
            )
        )

    for layer_name, gdf in layers.items():
        if gdf.empty:
            continue
        invalid = int((~gdf.is_valid).sum())
        if invalid:
            centroid = gdf.to_crs(CRS_WORKING).unary_union.centroid
            point = gpd.GeoSeries([centroid], crs=CRS_WORKING).to_crs(CRS_WGS84).iloc[0]
            records.append(
                asset_record(
                    point,
                    "qa_issue",
                    f"{layer_name} invalid geometry",
                    "Automated geometry validation",
                    f"qa:auto:{layer_name}",
                    "high",
                    "open",
                    "fail",
                    f"{invalid} invalid geometries detected after normalization.",
                    {
                        "issue_type": "invalid_geometry",
                        "severity": "high",
                        "affected_layer": layer_name,
                        "feature_ref": layer_name,
                    },
                )
            )

    return make_gdf("qa_issues", records)


def compute_metrics(layers: dict[str, gpd.GeoDataFrame]) -> OrderedDict[str, dict[str, Any]]:
    metrics: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for name in LAYER_ORDER:
        gdf = layers[name]
        projected = gdf.to_crs(CRS_WORKING) if not gdf.empty else gdf
        duplicate_count = 0
        if not gdf.empty:
            duplicate_count = int(gdf.geometry.apply(lambda geom: geom.wkb_hex).duplicated().sum())
        metrics[name] = {
            "features": int(len(gdf)),
            "geometry_types": ", ".join(sorted(set(gdf.geometry.geom_type))) if not gdf.empty else "none",
            "invalid_after_fix": int((~gdf.is_valid).sum()) if not gdf.empty else 0,
            "duplicate_geometries": duplicate_count,
            "needs_review": int((gdf["review_status"] == "needs_review").sum()) if "review_status" in gdf else 0,
            "low_confidence": int((gdf["confidence"] == "low").sum()) if "confidence" in gdf else 0,
            "area_sqft": round(float(projected.area.sum()), 1) if not projected.empty and projected.geom_type.isin(["Polygon", "MultiPolygon"]).any() else 0,
            "length_ft": round(float(projected.length.sum()), 1) if not projected.empty and projected.geom_type.isin(["LineString", "MultiLineString"]).any() else 0,
        }
    return metrics


def write_layers(layers: dict[str, gpd.GeoDataFrame]) -> None:
    gpkg_path = PROCESSED_DIR / "lower_manhattan_ai_assets.gpkg"
    if gpkg_path.exists():
        gpkg_path.unlink()

    for name in LAYER_ORDER:
        gdf = layers[name]
        projected = gdf.to_crs(CRS_WORKING)
        projected.to_file(gpkg_path, layer=name, driver="GPKG")
        gdf.to_crs(CRS_WGS84).to_file(GEOJSON_DIR / f"{name}.geojson", driver="GeoJSON")

    roi = gpd.GeoDataFrame(
        [
            {
                "name": "Lower Manhattan AI Asset ROI",
                "description": "Battery Park City / World Trade Center / West Street portfolio study area",
                "geometry": ROI_POLYGON,
            }
        ],
        crs=CRS_WGS84,
    )
    roi.to_crs(CRS_WORKING).to_file(gpkg_path, layer="roi", driver="GPKG")
    roi.to_file(GEOJSON_DIR / "roi.geojson", driver="GeoJSON")


def write_manifest(buildings: dict[str, Any], osm: dict[str, Any]) -> None:
    manifest = {
        "project": "AI-Ready Lower Manhattan Geospatial Asset Production Pipeline",
        "created": TODAY,
        "working_crs": CRS_WORKING,
        "export_crs": CRS_WGS84,
        "bbox": BBOX,
        "sources": [
            {
                "name": "NYS Building Footprints FeatureServer",
                "url": "https://gisservices.its.ny.gov/arcgis/rest/services/BuildingFootprints/FeatureServer",
                "features_downloaded": len(buildings.get("features", [])),
                "notes": "NYC records in this service cite NYC OpenData as the primary source.",
            },
            {
                "name": "OpenStreetMap via Overpass API",
                "url": "https://overpass-api.de/api/interpreter",
                "elements_downloaded": len(osm.get("elements", [])),
                "license": "Open Database License (ODbL)",
            },
            {
                "name": "Manual QGIS-style interpretation",
                "url": "Documented in docs/labeling_guide.md",
                "notes": "Used only for generalized water/land-use review assets and explicitly flagged for review.",
            },
        ],
    }
    (RAW_DIR / "source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def write_qa_report(metrics: OrderedDict[str, dict[str, Any]]) -> None:
    total_features = sum(item["features"] for item in metrics.values())
    needs_review = sum(item["needs_review"] for item in metrics.values())
    low_confidence = sum(item["low_confidence"] for item in metrics.values())
    rows = [
        "| Layer | Features | Geometry | Needs review | Low confidence | Invalid after fix | Duplicate geometries |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    for layer, values in metrics.items():
        rows.append(
            f"| `{layer}` | {values['features']} | {values['geometry_types']} | "
            f"{values['needs_review']} | {values['low_confidence']} | "
            f"{values['invalid_after_fix']} | {values['duplicate_geometries']} |"
        )

    report = f"""# QA Report

Generated: {TODAY}

## Summary

- Total normalized features: **{total_features:,}**
- Features requiring human review: **{needs_review:,}**
- Low-confidence review features: **{low_confidence:,}**
- Working CRS: **{CRS_WORKING}**
- Web/export CRS: **{CRS_WGS84}**

The QA workflow intentionally separates production-ready features from review features. `qa_flag=review` is not a failure; it means the asset is retained but should be checked against imagery or local authoritative context before use in an AI training/evaluation batch.

## Layer Checks

{chr(10).join(rows)}

## Review Notes

- Official building footprints are used where available and clipped to the ROI.
- OSM pedestrian features are useful for annotation context but do not guarantee complete sidewalk coverage.
- OSM crossing nodes were converted to short review lines so crosswalk assets can be inspected visually in QGIS.
- Parking assets in dense Lower Manhattan often indicate garages or access points, so they are flagged for review.
- Generalized land-use and Hudson River polygons are included to demonstrate labeling and QA workflow discipline, not to claim legal zoning precision.
"""
    (DOCS_DIR / "qa_report.md").write_text(report, encoding="utf-8")


def layer_color(layer: str):
    return {
        "land_use_zones": "#7367f0",
        "water": "#4da3ff",
        "green_space": "#61d394",
        "parking": "#f6bd60",
        "buildings": "#d9dde5",
        "roads": "#f5f5f5",
        "sidewalks": "#ff9f1c",
        "crosswalks": "#fff275",
        "points_of_interest": "#ff5d8f",
        "qa_issues": "#ff2d2d",
    }.get(layer, "#ffffff")


def plot_layers(layers: dict[str, gpd.GeoDataFrame], path: Path, title: str, subset: list[str]) -> None:
    fig, ax = plt.subplots(figsize=(14, 10), dpi=180)
    fig.patch.set_facecolor("#071013")
    ax.set_facecolor("#0b1518")

    roi = gpd.GeoDataFrame(geometry=[ROI_POLYGON], crs=CRS_WGS84).to_crs(CRS_WORKING)
    roi.boundary.plot(ax=ax, color="#ffffff", linewidth=1.2, alpha=0.7)

    for layer in subset:
        gdf = layers[layer]
        if gdf.empty:
            continue
        projected = gdf.to_crs(CRS_WORKING)
        color = layer_color(layer)
        geom_types = set(projected.geometry.geom_type)
        if geom_types.intersection({"Polygon", "MultiPolygon"}):
            projected[projected.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].plot(
                ax=ax,
                facecolor=color,
                edgecolor=color,
                linewidth=0.45,
                alpha=0.32 if layer in {"land_use_zones", "water", "green_space", "parking"} else 0.82,
            )
        if geom_types.intersection({"LineString", "MultiLineString"}):
            projected[projected.geometry.geom_type.isin(["LineString", "MultiLineString"])].plot(
                ax=ax,
                color=color,
                linewidth=1.2 if layer in {"roads", "sidewalks"} else 2.1,
                alpha=0.92,
            )
        if geom_types.intersection({"Point", "MultiPoint"}):
            projected[projected.geometry.geom_type.isin(["Point", "MultiPoint"])].plot(
                ax=ax,
                color=color,
                markersize=18 if layer != "qa_issues" else 55,
                alpha=0.95,
                marker="o" if layer != "qa_issues" else "x",
            )

    ax.set_title(title, loc="left", color="#f5f7f2", fontsize=18, pad=16, fontweight="bold")
    ax.text(
        0.01,
        0.02,
        "Battery Park City / WTC / West Street | CRS EPSG:2263 | Sources: NYS/NYC OpenData + OSM + flagged manual review assets",
        transform=ax.transAxes,
        color="#b8c2bf",
        fontsize=8,
    )
    ax.set_axis_off()
    legend = [
        Patch(facecolor=layer_color(layer), edgecolor=layer_color(layer), label=layer.replace("_", " "))
        for layer in subset
    ]
    ax.legend(
        handles=legend,
        loc="upper right",
        frameon=True,
        facecolor="#0f1b1f",
        edgecolor="#2f3f46",
        labelcolor="#f5f7f2",
        fontsize=8,
    )
    plt.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def write_attribute_table_image(layers: dict[str, gpd.GeoDataFrame], path: Path) -> None:
    sample = layers["buildings"][COMMON_FIELDS].head(3).copy()
    sample = pd.concat([sample, layers["crosswalks"][COMMON_FIELDS].head(2), layers["qa_issues"][COMMON_FIELDS].head(2)])
    wrapped = sample.copy()
    for column in ["label", "source", "notes"]:
        wrapped[column] = wrapped[column].apply(lambda value: "\n".join(textwrap.wrap(str(value), width=24)))
    cols = ["asset_id", "feature_type", "label", "confidence", "review_status", "qa_flag", "notes"]
    table_data = wrapped[cols].values.tolist()

    fig, ax = plt.subplots(figsize=(15, 7), dpi=180)
    fig.patch.set_facecolor("#071013")
    ax.set_axis_off()
    ax.set_title("Normalized Attribute Schema Sample", loc="left", color="#f5f7f2", fontsize=18, pad=18, fontweight="bold")
    table = ax.table(
        cellText=table_data,
        colLabels=cols,
        loc="center",
        cellLoc="left",
        colLoc="left",
        bbox=[0, 0, 1, 0.9],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7.6)
    table.scale(1, 2.1)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#304047")
        if row == 0:
            cell.set_facecolor("#18262b")
            cell.get_text().set_color("#7cf7cf")
            cell.get_text().set_weight("bold")
        else:
            cell.set_facecolor("#0f1b1f" if row % 2 else "#101f24")
            cell.get_text().set_color("#eef5f1")
    fig.savefig(path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def write_layer_inventory_image(metrics: OrderedDict[str, dict[str, Any]], path: Path) -> None:
    rows = [
        [
            layer.replace("_", " "),
            values["features"],
            values["geometry_types"],
            values["needs_review"],
            values["low_confidence"],
        ]
        for layer, values in metrics.items()
    ]
    fig, ax = plt.subplots(figsize=(12, 6), dpi=180)
    fig.patch.set_facecolor("#071013")
    ax.set_axis_off()
    ax.set_title("GeoPackage Layer Inventory", loc="left", color="#f5f7f2", fontsize=18, pad=18, fontweight="bold")
    table = ax.table(
        cellText=rows,
        colLabels=["layer", "features", "geometry", "review", "low conf."],
        loc="center",
        cellLoc="left",
        colLoc="left",
        bbox=[0, 0, 1, 0.9],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.8)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#304047")
        if row == 0:
            cell.set_facecolor("#18262b")
            cell.get_text().set_color("#7cf7cf")
            cell.get_text().set_weight("bold")
        else:
            cell.set_facecolor("#0f1b1f" if row % 2 else "#101f24")
            cell.get_text().set_color("#eef5f1")
    fig.savefig(path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def write_screenshots(layers: dict[str, gpd.GeoDataFrame], metrics: OrderedDict[str, dict[str, Any]]) -> None:
    plot_layers(
        layers,
        SCREENSHOTS_DIR / "01_raw_inputs_context.png",
        "Raw Input Context: Official Footprints + OSM Network",
        ["water", "green_space", "buildings", "roads", "sidewalks", "points_of_interest"],
    )
    plot_layers(
        layers,
        SCREENSHOTS_DIR / "02_final_asset_map.png",
        "AI-Ready Lower Manhattan Geospatial Asset Layers",
        ["land_use_zones", "water", "green_space", "parking", "buildings", "roads", "sidewalks", "crosswalks", "points_of_interest"],
    )
    plot_layers(
        layers,
        SCREENSHOTS_DIR / "03_qa_review_map.png",
        "QA Review Surface: Features Needing Human Attention",
        ["water", "green_space", "buildings", "roads", "sidewalks", "crosswalks", "qa_issues"],
    )
    write_attribute_table_image(layers, SCREENSHOTS_DIR / "04_attribute_schema_sample.png")
    write_layer_inventory_image(metrics, SCREENSHOTS_DIR / "05_layer_inventory.png")
    # A PDF export is useful for recruiters who want a printable artifact.
    plot_layers(
        layers,
        MAPS_DIR / "lower_manhattan_ai_assets_map.pdf",
        "AI-Ready Lower Manhattan Geospatial Asset Layers",
        ["land_use_zones", "water", "green_space", "parking", "buildings", "roads", "sidewalks", "crosswalks", "points_of_interest"],
    )


def main() -> None:
    for directory in [RAW_DIR, PROCESSED_DIR, GEOJSON_DIR, DOCS_DIR, SCREENSHOTS_DIR, MAPS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

    buildings_raw = fetch_building_footprints()
    osm_raw = fetch_osm_context()
    write_manifest(buildings_raw, osm_raw)

    layers = build_from_osm(osm_raw)
    layers["buildings"] = build_buildings(buildings_raw)
    layers["land_use_zones"] = build_land_use_zones()
    layers["qa_issues"] = build_qa_issues({**layers, "land_use_zones": layers["land_use_zones"], "buildings": layers["buildings"]})
    layers = OrderedDict((name, layers[name]) for name in LAYER_ORDER)

    metrics = compute_metrics(layers)
    write_layers(layers)
    write_qa_report(metrics)
    write_screenshots(layers, metrics)

    print("Generated Lower Manhattan AI-ready GIS package")
    for layer, values in metrics.items():
        print(f"- {layer}: {values['features']} features")


if __name__ == "__main__":
    main()
