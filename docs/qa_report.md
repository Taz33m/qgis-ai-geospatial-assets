# QA Report

Generated: 2026-05-15

## Summary

- Total normalized features: **7,219**
- Features requiring human review: **1,740**
- Low-confidence review features: **34**
- Working CRS: **EPSG:2263**
- Web/export CRS: **EPSG:4326**

The QA workflow intentionally separates production-ready features from review features. `qa_flag=review` is not a failure; it means the asset is retained but should be checked against imagery or local authoritative context before use in an AI training/evaluation batch.

## Layer Checks

| Layer | Features | Geometry | Needs review | Low confidence | Invalid after fix | Duplicate geometries |
|---|---:|---|---:|---:|---:|---:|
| `land_use_zones` | 5 | Polygon | 5 | 0 | 0 | 0 |
| `water` | 18 | Polygon | 1 | 0 | 0 | 0 |
| `green_space` | 1230 | MultiPolygon, Polygon | 0 | 0 | 0 | 0 |
| `parking` | 42 | Polygon | 42 | 34 | 0 | 0 |
| `buildings` | 558 | Polygon | 0 | 0 | 0 | 0 |
| `roads` | 496 | LineString | 0 | 0 | 0 | 0 |
| `sidewalks` | 1890 | LineString, MultiLineString | 1201 | 0 | 0 | 0 |
| `crosswalks` | 950 | LineString | 491 | 0 | 0 | 0 |
| `points_of_interest` | 2025 | Point | 0 | 0 | 0 | 0 |
| `qa_issues` | 5 | Point | 0 | 0 | 0 | 0 |

## Review Notes

- Official building footprints are used where available and clipped to the ROI.
- OSM pedestrian features are useful for annotation context but do not guarantee complete sidewalk coverage.
- OSM crossing nodes were converted to short review lines so crosswalk assets can be inspected visually in QGIS.
- Parking assets in dense Lower Manhattan often indicate garages or access points, so they are flagged for review.
- Generalized land-use and Hudson River polygons are included to demonstrate labeling and QA workflow discipline, not to claim legal zoning precision.
