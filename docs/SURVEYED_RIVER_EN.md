# Import a surveyed river reach

**English** | [简体中文](SURVEYED_RIVER_CN.md) | [User guide](USER_GUIDE_EN.md)

Use this starting route for one surveyed, georeferenced river reach with no structure. A field or GIS lead first prepares the package. Once prepared, the engineer can open it from the ordinary project page without re-entering the geometry. To start with loose files, partial data or a surface DEM, use the coordinates route.

## Open an existing package

1. Choose **Georeferenced river survey package** under **Starting information** and enter a project name. Select `survey.json`, the original survey GeoTIFF or project crop, and every referenced source file together. Use plain filenames. Each file may be up to 15 MB and the selection up to 50 MB.
2. Select **Prepare project**. The import verifies filenames, SHA-256, the projected CRS, raster location, vertical units, section ordering, profiles and hydraulic inputs. An error identifies the field or source to correct. The project keeps independent copies of the originals.
3. On the model page, inspect the alignment, which parts of the bed are surveyed, bank interpretation, roughness, event discharge and tailwater. Open the complete parameter review and confirm the actual calculation. The event name and flow come from the survey package.
4. On the results page, check the native profile, warnings and maps. For a second event, import the observation CSV with its date, measured discharge, units, datum, positions and measurement uncertainty. Assign the downstream prescribed stage the boundary role. Use holdout for the unused event’s interior observations. Freeze roughness and geometry before comparing. The limit on the result page names any missing evidence. Preserve both mapped packages and use the same approved baseline for boundary and full-reach two-level spacing checks.

## Prepare the package

The preparer provides a UTF-8 `definition.json` containing these objects. Field notes, fitted coefficients, and interpolated bed data should carry their own sources and limitations.

| Object | Contents |
|---|---|
| `location` | `latitude` and `longitude`, WGS84 decimal degrees inside the surveyed raster. |
| `terrain` | `raster` (a plain GeoTIFF filename), `vertical_datum`, `vertical_unit` (one of `m`, `US survey foot`, `international foot`). Use a single-band projected survey raster in the geometry CRS, up to 16 million cells. Include sources and processing notes when providing a crop or combined survey/terrain model. |
| `geometry` | Use geometry schema `1.0`, `model_type: river`, `hydraulic_unit: international_ft`, `river` and `reach` names, `horizontal_crs` (projected EPSG code or WKT), `vertical_datum`, `channel_geometry_basis` (`surveyed_channel` or `combined_survey_and_dem`), and `flow_regime`. Provide one upstream-to-downstream `flowlines` record with `id` and projected `xy` pairs. |
| `geometry.cross_sections` | 4–500 sections. Supply descending numeric `rs`, `center_xy`, a left-to-right `cutline_xy` looking downstream, `station_ft`, `elevation_ft`, two `bank_stations_ft` at sampled stations, three `reach_lengths_ft` to the next section (left/channel/right, zero at the outlet), and `expansion_contraction` in that order. Use the projected CRS native horizontal units for XY and international feet for hydraulic arrays. Provide evidence for interpreted banks, flow lengths and losses. |
| `geometry.boundaries` | Supply each required end for the regime. A normal-depth end uses `type: normal_depth` and its positive slope under `boundary_slopes`. A known downstream stage uses `type: known_stage` and `stages_ft`, one absolute WSE per profile in the model datum. Document its date, source and datum. |
| `scenario` | Lowercase `id`, `channel_n`, `overbank_n`, `parameter_source`, and `profiles`. Each profile has a distinct short ASCII `id`, positive `flow_cfs` and a `source`. Cite independent flow records, survey dates, and the event used to select roughness. |

In the checkout’s PowerShell, run the following once, adapting paths and source descriptions to the real files. Keep the source files alongside the definition. Repeat `--source` for every original used. The command writes and validates `survey.json` with filenames and SHA-256 digests. Creating a second package in the same directory requires a new destination or moving the original manifest.

```powershell
.\.venv\Scripts\python.exe -m ras_workflow.survey_import .\field\definition.json --source .\field\bed.tif "Survey date, provider, units and datum" --source .\field\field_notes.pdf "Measurement method, gage zero and site uncertainty"
```

A received raster can combine surveyed and interpolated areas. The result page counts independent water-surface elevations and gage heights from the held-out event. Bed elevations check the geometry separately. The imposed outlet stage is excluded from the independent comparison. If a source omits measurement uncertainty, leave it blank. The page gives separate counts for missing uncertainty and residuals exceeding the documented uncertainty, and identifies the largest residual among those requiring review. Repeating a run of the same event retains one set of observations for that event.
