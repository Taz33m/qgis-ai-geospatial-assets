# Source Notes

## Primary Data Sources

### NYS Building Footprints FeatureServer

URL: <https://gisservices.its.ny.gov/arcgis/rest/services/BuildingFootprints/FeatureServer>

Used for `buildings`. The service description states that NYC records primarily come from NYC OpenData building footprints. The package stores the raw clipped download in:

`data/raw/nys_building_footprints_bbox.geojson`

### OpenStreetMap via Overpass API

URL: <https://overpass-api.de/api/interpreter>

Used for roads, sidewalks, crosswalks, parking candidates, green space, water context, and POIs. OSM data is available under the Open Database License. The raw Overpass download is stored in:

`data/raw/osm_overpass_lower_manhattan.json`

### Manual QGIS-Style Interpretation

Used only for generalized land-use zones and a review-marked Hudson River edge polygon. These assets are intentionally flagged with `source=Manual QGIS-style interpretation...`, `confidence=medium`, and `review_status=needs_review`.

## License and Attribution

This repository contains derived public geospatial data. Users should preserve source attribution and comply with source licenses, including OSM ODbL requirements when using or redistributing OSM-derived layers.

The code and documentation in this repository may be reused for portfolio/research purposes, but the data layers themselves retain their source-license obligations.

## Known Limitations

- The study area is intentionally compact; it is a portfolio-quality ROI, not a citywide dataset.
- OSM pedestrian and crossing coverage may be incomplete or uneven.
- Point-derived crosswalks and parking assets are review aids, not final authoritative geometries.
- Land-use zones are generalized interpretation labels, not legal zoning or PLUTO parcel data.
- The project demonstrates an AI-ready asset workflow, not a certified municipal basemap.
