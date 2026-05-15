# Labeling Guide

This guide defines how features in the Lower Manhattan asset package should be interpreted by a human reviewer or an AI evaluation workflow.

## Confidence Levels

| Value | Use When |
|---|---|
| `high` | Geometry and label come from a strong source and require no obvious correction at portfolio scale. |
| `medium` | Feature is useful but may require imagery/source review for exact boundary or classification. |
| `low` | Feature is approximate, derived from a point, or likely represents an access point rather than a full asset. |

## Review Status

| Value | Use When |
|---|---|
| `reviewed` | The feature is acceptable for this portfolio dataset. |
| `needs_review` | The feature should be checked before being treated as training/evaluation ground truth. |
| `open` | QA issue is still unresolved. |

## Layer Rules

### Buildings

- Use official footprint geometry when available.
- Preserve source object ids and source date fields.
- Do not infer occupancy, ownership, height, or use unless another documented source supports it.

### Roads

- Treat OSM `highway` ways as road/network context.
- Do not assume routability without checking directionality, access, bridges, tunnels, and path separation.
- Use the layer for map reasoning and QA prompts, not as a complete navigation graph.

### Sidewalks

- Include OSM footway/path/pedestrian geometries.
- Flag pedestrian geometries as `needs_review` when OSM does not explicitly state `footway=sidewalk`.
- Do not assume every road has complete mapped sidewalk coverage.

### Crosswalks

- Keep OSM crossing ways as line assets.
- Convert crossing nodes to short review lines so they are visible during QGIS QA.
- Mark node-derived crosswalks for review because exact curb-to-curb alignment is not guaranteed.

### Parking

- Use OSM parking polygons where present.
- Buffer parking points into small review polygons for visibility.
- Treat Lower Manhattan parking features cautiously because many are garages, access points, or below-grade facilities.

### Green Space

- Include park, garden, pitch, playground, grass, and recreation-ground polygons.
- Do not treat these categories as legal parkland boundaries without a city parks source.

### Water

- Use OSM water polygons where present.
- Keep generalized manual water boundaries as review features, not authoritative shoreline geometry.

### Points of Interest

- Normalize OSM amenity, tourism, shop, and historic features to point assets.
- For polygon POIs, use an interior representative point so the asset remains easy to inspect in QGIS.

### Land Use Zones

- Treat land-use zones as portfolio-scale interpretation labels.
- Do not represent them as legal zoning, parcel, or tax-lot boundaries.
- Use them to test schema design, label reasoning, and QA documentation.

### QA Issues

- Use QA points to make ambiguity visible.
- QA records should identify the affected layer, issue type, severity, and review note.
- Do not delete review features simply because they are ambiguous; document the ambiguity.
