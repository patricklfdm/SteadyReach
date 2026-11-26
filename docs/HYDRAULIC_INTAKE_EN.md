# From source files to confirmed hydraulic inputs

[简体中文](HYDRAULIC_INTAKE_CN.md)

## Start with an original field table

1. Open a prepared project and choose **Import an original measurement table → Start from my field table**. River observations need located cross sections. Select a UTF-8 CSV or tab-delimited file up to 2 MB and 10,000 rows, or a USGS field-measurements GeoJSON. For an Excel workbook, save the relevant sheet as UTF-8 CSV.
2. Choose **Read columns and suggest matches**. For example, `X,Y,measwse` identifies position and water elevation. A registered FGDC XML that names this file and attribute can supply units and reference systems. Verify the event date, discharge, profile and survey CRS against the source. Dates from filenames and discharges from the model are suggestions. Nonempty source columns take precedence over whole-table defaults.
3. Choose **Locate and preview source rows**. On a longitudinal trace, a candidate must be within 5 m of a section center and match that cut unambiguously. Review the nearest row, its role and nearby alternatives. Check out-of-range points, duplicates, ties and datum conflicts before adopting. Flood marks away from the center or influenced by a structure require separate location review.
4. An editable single-profile subcritical or mixed-flow model can adopt one directly surveyed outlet. Screening or review with unquantified vertical accuracy requires explicit consent. Interior levels are hidden in this preview. After computation, return unused interior observations for one event, confirm their independence and create a separate revision. Both paths retain the normal final input confirmation.
5. For a remote gage, compare coordinates, distance and datum. USGS discharge and relative height are paired by site and visit. Use the gage-boundary procedure below once the zero, event and transfer are documented. Culvert sheets accept `group,inletinvertft,outletinvertft,datum` or `group,end,elevation,unit,datum`. Groups start at 1; use `inlet` or `outlet` for the end. A blank end preserves its previous value and evidence class.


Open a saved coordinate or survey project. Expand **Hydraulic evidence and offline replay** and select **Inspect hydraulic evidence**. Do this before choosing a boundary or requesting site measurements. The list uses the current draft or the sealed inputs of the calculated edition.

| Evidence | What to check | Useful next record |
|---|---|---|
| Terrain | Working raster, horizontal extent, vertical datum and units, catalog edition | Survey control and a raster covering the modeled floodplain |
| Submerged channel | Surveyed stations and the basis of the channel elevations | Dated underwater cross sections tied to the project datum |
| Discharge | Profile, event or annual exceedance probability, magnitude, units and source | Published frequency table for this reach or discharge measured during the modeled event |
| Stage | Station identity, observation time, datum, units, boundary section and uncertainty | A simultaneous water elevation at the boundary or a documented transfer to it |
| Crossing | Barrel group, inlet and outlet inverts, length and road geometry | Survey worksheet or record drawing identifying the group, both ends, datum and units |

Expand a category to see current values, evidence classes, candidates, original names and SHA-256 fingerprints. A catalog publication date and a field measurement date describe different events. Unknown metadata remains open. On an editable edition, **Add metadata from an original document** records what you read in a selected original. Saving a second entry for that source and category replaces the first entry on this edition. If two datums differ, supply the conversion record before using elevations together.

A search with no match means the service responded. An unavailable service can be retried. Partial responses and conflicting records remain visible. A value labelled conditional can support a screening run if the project purpose allows it. Source records and a calculation receipt alone cannot establish fitness for design.

## Decide whether a gage supports a downstream stage

For a river with a known downstream stage, verify the station, modeled profile, event date and discharge. The observation must reference the model's elevation datum and units, identify its position and report positive vertical uncertainty. Gage height additionally needs the dated elevation of gage zero. Check the section matched to the actual station coordinates. For an off-site station, supply the event-specific signed water-level offset to the downstream section, its uncertainty and the original supporting document. A calibration, context or holdout reading remains independent. Keep a separately documented boundary such as normal depth while a stage transfer is unresolved, and test the selected boundary's sensitivity.

**Soquel example.** USGS 11160000 matches RS 1700 and lies about 714 m from the center of the downstream section. The site record lists NGVD29 while the model uses NAVD88. A frequency estimate at the station can inform discharge selection. A Q100 tailwater still requires a compatible event water level, datum and documented transfer. **Dexter example.** The 1,540 cfs visit provides a measured discharge and an interior holdout at RS 500. Keep that stage available for comparison after the run.

### Optional structured evidence

Include `observed_profiles.csv` with the survey sources or use the field-return workflow. Use the existing observation columns for event, date, role, kind, coordinates, horizontal CRS, elevation, units, vertical datum, discharge, uncertainty and source. Identify the model profile using the `profile` column. Use `boundary` only when proposing a control, `holdout` for independent comparison, and include the station identifier such as `USGS-11160000` in `source`. Enter the absolute elevation for `stage`; for `gage_height`, provide height and `gage_zero` in the row's stated elevation units. Boundary declarations apply to the downstream end of an active steady river profile.

For supplied survey sources, a supplemental `intake_evidence.json` can link an event, gage zero or transfer to its original. Register each supporting file alongside the declaration in the survey manifest. Use actual record fingerprints. The declaration cannot cite itself. The following field names describe the format.

| Array in schema `intake_evidence_1` | Fields per entry |
|---|---|
| `records` | `category` (terrain, channel, flow, stage or structure), `source_sha256`, and documented `date`, `footprint`, `datum`, `unit`, `version` as available |
| `events` | `station`, `profile`, `event`, `date`, `source_sha256` |
| `gage_zeros` | `station`, `date`, `datum`, `zero_ft`, `source_sha256` |
| `datum_ties` | `station`, `event`, `date`, `from_datum`, `to_datum`, `source_stage_ft`, `offset_ft`, `uncertainty_ft`, `basis`, `source_sha256`. For an absolute stage converted from the registered station datum, the original elevation plus the signed offset must match the observation in feet. |
| `transfers` | `station`, `profile`, `event`, `date`, `target_rs`, `datum`, `offset_ft`, `uncertainty_ft`, `basis`, `source_sha256` |

Use ISO dates, numeric offsets and uncertainties in feet, and station IDs from registered USGS monitoring-location records. The transferred stage equals the observed absolute stage in feet plus the signed offset. A conflicting or unsupported declared boundary prevents confirmation of that known-stage input. Existing normal-depth controls retain their own basis.

## Directly surveyed outlet

For an absolute water level measured on the outlet cross section, include the measured point as a CSV extract with the header `x,y,elevation` and one data row. List the file in the survey manifest. In `intake_evidence.json`, bind the event to this extract’s SHA-256 with `method: "direct_outlet_survey"`. Provide the profile, event, date, coordinate system, vertical datum, unit and original point citation in `point_source`. Enter the same citation in the boundary row of `observed_profiles.csv` with kind `boundary_stage`. The Washington State Park example prepares these files from the dated provider record.

The application compares the two records, locates the point on the downstream section and checks the event discharge and imposed elevation. When the source lacks a quantified vertical uncertainty, `accept_unquantified_for_screening: true` permits a conditional run for screening or engineering review following confirmation. The confirmation page and report identify the missing accuracy. Other uses and mismatches remain blocked. A relative gage height or off-site gage follows the gage-zero and transfer checks above. The imposed outlet is excluded from residual scoring.

## Freeze, replay and resume

1. Select **Freeze these sources**. Keep the archive path and SHA-256 receipt. The archive includes the working DEM, material actually registered by this edition, recorded search responses and available local imagery. Full unclipped provider tiles are recorded separately by reference.
2. Select **Replay last frozen intake offline**. The app checks the archive and its members, reinterprets the original evidence and compares the resulting inventory fingerprint. For a detached archive use `python -m ras_workflow.intake_freeze "<archive.zip>" --sha256 "<receipt SHA-256>"` in an installed checkout.
3. On the survey route, **Recover frozen original survey folder** restores the original manifest and its listed files; available local imagery is placed beside it. Import the recovered survey from the home page for a fresh calculation. Restore a full working edition with **Storage and recovery by edition** if you also need subsequent geometry edits, calculations and handoffs.
4. For a field return, start from the calculated parent. Import the returned worksheet or observations, check units and datum, and open **Review calculation inputs** in the new edition. The changes panel shows the affected values and the number carried forward. A return with the same numeric value can still change the evidence. An independent observation alone can update the comparison with all hydraulic inputs carried forward. If the parent confirmation is unavailable the page requests a full review. Confirm the current edition before starting its solver.

For setup and the same-workstation release procedure, see [Getting started](GETTING_STARTED_EN.md) and [Local release checks](LOCAL_RELEASE_EN.md).
