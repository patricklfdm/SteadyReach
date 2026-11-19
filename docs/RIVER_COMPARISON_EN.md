# Compare a river model with alternatives and field data

[简体中文](RIVER_COMPARISON_CN.md) · [Start with a location](RIVER_REACH_EN.md)

## Use the results page

1. Open the solved river edition in **Saved projects**. Confirm the profile, discharge and units. For a California frequency estimate, the reviewed flow source identifies the USGS station, workbook cell and transfer distance.
If final input review shows competing values, choose **Choose source candidates for missing inputs**. Read the river or station name next to the number before adopting. LOW bank confidence marks a candidate needing a closer look at the profile.

If public lookup or download failed, preparation and final review identify the affected source. Extraction counts cover local files. Retry the search or import the appropriate official volume from a local site folder, then revisit candidates and confirm their river and page.

2. Open **Compare two geometry revisions** and set the maximum total section width in feet. **Preview both geometries** proposes extensions with fixed directions and a second layout that permits rotation. Inspect changes in each case, including moved banks and floodplain connectivity. Confirm once and select **Run both revisions**. The original model and both solutions are retained.
3. Read the three same-scale maps. Select an RS to see its left/right end elevations, calculated water level and change, left/right overbank flow and critical-depth fallback. Red marks a newly wet end, green a cleared end and orange an end that remains wet. Two layouts with the same count can affect different locations. A blank native flow or fallback value means unavailable. Download the comparison CSV for all sections.
4. To test boundary influence, open **Suggest ranges from saved inputs**. Select supported boundary ranges, check the low and high values, preview, then confirm the batch. Read the largest absolute change and its RS and the number of sections above the displayed threshold. These results apply to the tested ranges and one-at-a-time changes.

## Check field data

Open **Field observations and event checks**. Download the CSV header. Enter one observation per row and use UTF-8. Select the file or paste the whole CSV, then click **Check and save observations**. Importing a table preserves its source and creates a screening record tied to this calculation.

| Column | What to enter |
|---|---|
| event, date | One flood or survey ID and its ISO date (YYYY-MM-DD). Use a separate event for independent validation. |
| role, kind | Roles: calibration, holdout, boundary, context. Kinds: stage, gage_height, bed, boundary_stage. Use boundary for a measured downstream stage used to drive the trial. |
| x, y, horizontal_crs | Easting/northing or longitude/latitude in the stated CRS (e.g. EPSG:4326). Use the observation location. |
| elevation, unit, vertical_datum | Reported value in ft, us_survey_ft or m. Supply a documented datum. The app checks consistency with the modeled datum. If converting beforehand, cite the transformation in source. |
| gage_zero | For gage_height, enter the zero elevation in the stated units and datum. |
| flow, flow_unit | Event discharge in cfs or m3/s for water-level observations. Bed survey rows may omit flow. |
| vertical_uncertainty, horizontal_uncertainty_m | Reported uncertainty in the elevation unit and in metres, respectively. Leave unreported values blank. |
| source | Source, page or survey identifier and any datum conversion or coordinate qualifications. |

A section match uses a maximum separation of 5 m, including supplied horizontal uncertainty, and checks for ambiguous neighboring sections. Inspect the reported distance. Bed measurements compare with the native station/elevation profile at their projected station. Flood stages require compatible location, datum, event and discharge. Matching quality includes professional judgment about timing, channel change, flow steadiness and representativeness.

For an eligible event, choose **Preview event**, review flow and boundary, confirm and compute. The results group keeps completed events for the current observation table. Residuals are calculated water level minus observed water level (ft). A downstream stage used as the boundary cannot provide an independent residual at that section. Keep holdout floods separate from calibration and record uncertainty when interpreting any difference. If a point is outside the modeled reach or uses a different datum, the page identifies which evidence to obtain.
