# AI Trainer Task Bank

These tasks are designed for evaluating whether an AI assistant understands practical QGIS and geospatial data workflows.

## 1. CRS Choice

**Prompt:** Why does this project use EPSG:2263 as the working CRS and EPSG:4326 for GeoJSON export?

**Expected answer:** EPSG:2263 is appropriate for local NYC editing/measurement because it is a projected CRS for New York Long Island; EPSG:4326 is broadly compatible for web GeoJSON. A good answer should mention measurement accuracy and export interoperability.

## 2. Geometry Validation

**Prompt:** A polygon layer has self-intersections after clipping. What should you do in QGIS before exporting it?

**Expected answer:** Run geometry validation/check tools, inspect errors, use fix geometries or manual vertex edits as appropriate, then rerun validation. A good answer should not simply say “export anyway.”

## 3. Crosswalk Node Ambiguity

**Prompt:** Some crosswalks come from OSM crossing nodes, not curb-to-curb line geometries. How should they be represented in an AI training dataset?

**Expected answer:** Keep them visible but mark them as approximate or needing review. Do not treat node-derived crossings as precise line labels unless aligned manually.

## 4. Attribute Schema

**Prompt:** Why include `confidence`, `review_status`, and `qa_flag` instead of only feature labels?

**Expected answer:** AI/data workflows need provenance and review state. These fields let downstream users separate trusted features from useful but uncertain candidates.

## 5. Sidewalk Coverage

**Prompt:** Can the sidewalk layer be assumed complete because it was downloaded from OSM?

**Expected answer:** No. OSM coverage varies; footways and paths may not capture every sidewalk. Completeness should be reviewed against imagery or authoritative pedestrian data.

## 6. Parking Interpretation

**Prompt:** Why are many parking features in Lower Manhattan flagged for review?

**Expected answer:** Dense urban parking often represents garages, access points, below-grade facilities, or approximate OSM nodes rather than surface parking polygons.

## 7. Export Formats

**Prompt:** Why provide both GeoPackage and GeoJSON exports?

**Expected answer:** GeoPackage is better for a multi-layer QGIS project with local CRS and richer GIS workflows. GeoJSON is useful for web sharing, simple inspection, and downstream tools.

## 8. Topology Rules

**Prompt:** What topology issues would you check in this project before calling it production-ready?

**Expected answer:** Invalid geometries, duplicates, unintended polygon overlaps/gaps where mutually exclusive, dangling road/path segments where connectivity matters, and point features outside expected polygons.

## 9. QA Issue Layer

**Prompt:** Why create a `qa_issues` layer instead of only writing notes in a README?

**Expected answer:** A spatial QA layer lets reviewers click issues in QGIS, see exact locations, and connect written review notes to map evidence.

## 10. AI Response Review

**Prompt:** An AI says “Run QuickOSM, export shapefiles, and you are done.” What feedback would you give?

**Expected answer:** The answer is incomplete. A strong workflow should include source selection, CRS handling, schema normalization, geometry/topology validation, ambiguity flags, export checks, and documentation.
