# Data Dictionary

Generated for the AI-ready Lower Manhattan QGIS portfolio package.

## Common Fields

| Field | Type | Meaning |
|---|---|---|
| `asset_id` | text | Stable portfolio asset identifier unique within each layer. |
| `feature_type` | text | Normalized feature family, such as `building`, `road`, `crosswalk`, or `qa_issue`. |
| `label` | text | Human-readable feature label for QA and map review. |
| `source` | text | Source system or workflow that produced the feature. |
| `source_id` | text | Original source identifier when available, such as OSM id or official object id. |
| `confidence` | text | `high`, `medium`, or `low` confidence in the feature geometry/label. |
| `review_status` | text | `reviewed`, `needs_review`, or `open`. |
| `qa_flag` | text | `pass`, `review`, or `fail`. |
| `notes` | text | Short human-readable QA or provenance note. |
| `last_updated` | date text | Date the asset package was generated. |

## Layer-Specific Fields

| Layer | Extra Fields |
|---|---|
| `buildings` | `source_date`, `source_provider` |
| `roads` | `osm_class` |
| `sidewalks` | `osm_class`, `osm_footway` |
| `points_of_interest` | `poi_type` |
| `land_use_zones` | `zone_class` |
| `qa_issues` | `issue_type`, `severity`, `affected_layer`, `feature_ref` |

## Geometry Types

| Layer | Geometry |
|---|---|
| `land_use_zones` | Polygon |
| `water` | Polygon |
| `green_space` | Polygon / MultiPolygon |
| `parking` | Polygon |
| `buildings` | Polygon |
| `roads` | LineString |
| `sidewalks` | LineString / MultiLineString |
| `crosswalks` | LineString |
| `points_of_interest` | Point |
| `qa_issues` | Point |

## Review Semantics

`review_status=needs_review` means the asset is useful enough to keep in the dataset, but should be checked against imagery, a more authoritative layer, or project-specific labeling rules before it is used as ground truth.

`qa_flag=review` is intentionally different from `qa_flag=fail`. Review features are part of the deliverable because ambiguity is normal in real GIS data production.
