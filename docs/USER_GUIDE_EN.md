# SteadyReach: user guide

**English** | [简体中文](USER_GUIDE_CN.md) | [Home](../README.md)

For a reach without structures, choose **River reach (bridges excluded)** and follow the [river guide](RIVER_REACH_EN.md). It removes culvert/road fields and requires channel-bed representation and active boundary conditions. The crossing-specific steps below apply to culvert projects.

For a new site, import available material, check the crossing and terrain metadata, then click **Prepare an automatic draft**. Inspect the staged geometry, labelled estimates and highlighted uncertainties before confirming the full model once. [Consolidated preparation](AUTOMATION_EN.md).

## 1. Open the app

Double-click `start_workflow.cmd`. Keep its console running. It opens a local browser page; all project files remain on your machine. With an installed environment there are no PowerShell commands to type during normal use. The default language is English; select 简体中文 to change it.

For a missing Python environment the launcher invokes the retained setup procedure. HEC-RAS must be installed and discoverable. QGIS supports editable GIS/exhibit production; LibreOffice provides PDF conversion. Do not close an unrelated open engineering project to satisfy an automated check: save/close it yourself if it prevents an owned solver session.

Under **Saved projects**, each project you create has one collapsed entry. Expand its name to see the original first, followed by QA drafts and revisions, newest first. Choose **Open / continue** on the version you want. Independently created projects with the same name have separate entries. After restarting the launcher, use the browser address it opens for that session.

## 2. Choose your starting information

**Surveyed river package.** If a surveyor supplied `survey.json`, its GeoTIFF and the cited originals, select them together on the project page. [Preparing and using a surveyed river package](SURVEYED_RIVER_EN.md).

**Coordinates or partial information:** enter a project name, WGS84 latitude and longitude in decimal degrees. Longitude is negative in the western United States. Enter discharge in cfs only if known; optional Manning n values can also be supplied. Leave unknown fields blank. Select Prepare project. The program queries/downloads USGS terrain and reads available metadata; it then pauses with the model inputs that still need attention.

**Existing model:** select the `.prj`, selected `.pNN`, corresponding `.gNN` and `.fNN` together. A local `.prj` path is an alternative if file selection fails. Type the intended plan, such as `p01`, if the source's saved plan is different or unavailable. The preview shows both saved and selected plans. Previous result files are not needed or imported. Coordinates are needed for automatic map acquisition; if no map is required, omit coordinates and uncheck GIS.

For a new model, first use the [detailed no-model guide](NO_MODEL_GUIDE_EN.md): material preparation, map picks, conditional ranges, road sampling and final confirmation.

## 3. Complete the model on one page

With a native model, inspect its profiles, barrel groups, cross sections, roughness and boundaries. Supply the native foot convention and model elevation datum. For GIS, also supply the native projected CRS and confirm the displayed DEM elevation unit/datum. The app can read a DEM metadata candidate, but cannot reliably infer an undocumented native CRS. A datum mismatch prevents mapping; the app does not invent a datum shift.

If a previously entered discharge or roughness conflicts with the imported model, the discrepancy is shown. Either select the correct source model, or explicitly select Use native values instead of earlier entries. The prior entries remain in a separate record. Importing a model never silently replaces them.

Without a native model, expand Flow and roughness, Structure/units/boundaries and the section controls. Enter the actual values available from drawings, surveys or engineering judgement. Necessary values include flow, roughness, structure shape/count/opening, length, inlet/outlet elevations, floor/inlet type, road geometry, boundaries and cross sections. There is no mandatory name, reason or individual confirmation field. User entries are recorded as unverified user inputs. Clicking a reference candidate preserves its assumption class and supporting range/source; it does not label the candidate as a measurement.

For DEM-derived sections, start with **Automatic DEM layout / QA repair** to propose exterior anchors, positions, extents and bank candidates. Check DEM units/datum, actual flow direction and coverage, adopt the displayed choices together, then review the complete parameters. Manual map, section and bank controls remain available under B when needed. NoData, intersections and invalid bank order still block calculation. See the [DEM automation guide](DEM_AUTOMATION_EN.md).

Start with **Find, import and inspect source material**: public lookup, PDF/text extraction, survey CSV and optional local Windows OCR now produce reviewable candidates. Existing inputs are preserved. Survey points can be inspected on the DEM without a separate QGIS step. See [source assistance](SOURCE_ASSIST_EN.md) for coverage, folder import, units and failed-attempt handling.

Scalar edits save automatically after a short pause. Selected candidates, associations and bank batches appear in a pending banner; **Save all changes** commits them together. Wait for Saved locally. Returning to Projects, switching language or opening final review also saves pending selections first. A stale batch stops with an actionable error; earlier successful saves remain. Correct invalid numbers and save before refreshing or closing the browser. Downloads can be retried without replacing the draft.

The DEM map supports fine wheel zoom, dragging and fit controls. For intersecting cutlines, use B → Adjust section directions / DEM preview: request rotations without narrowing, inspect actual DEM profiles, then explicitly apply. Recheck banks and affected dependent inputs afterward; see [section repair and map controls](NO_MODEL_GUIDE_EN.md).

## 4. Confirm the complete parameters, then run

Open Review all parameters. Check the full list, units, sources and estimate/assumption labels. Expand long arrays; Edit values (all fields) allows corrections. Missing or invalid inputs are identified with field navigation and keep Run disabled.

After edits, Save and refresh parameter list, check the single confirmation, then Confirm and run HEC-RAS. The backend checks input files and parameter fingerprints; changed inputs require new confirmation. No reviewer name, reason or individual signatures are required.

The program then builds an independent working model, runs actual HEC-RAS, extracts this run's results, checks output identity and hydraulic diagnostics, generates the reports, and builds both delivery packages. With GIS selected it also prepares terrain, contours, offline imagery when available, native Mapper associations and QGIS layouts/exhibits. Keep the launcher running; you can close the browser tab. Only one project processes at a time.

## 5. Read and deliver the result

The results page shows flow, headwater, tailwater, velocity and road flow where the installed interface provides them. A dash means unavailable, not zero. Native group tables and the complete warning list are exported automatically after computation and included in reports. If export is unavailable, save/close HEC-RAS and use **Export native outputs and update deliverables** without solving again. Keep Windows signed in and avoid clipboard use during export. Expand grouped warnings and any display/machine differences to see unresolved issues. [Detailed instructions](RESULTS_REVIEW_EN.md).

Open Report_EN/Report_CN DOCX or PDF, and Summary_EN for the English executive summary. Open Minimal for the small native HEC-RAS/Mapper/exhibit package; open Complete for editable QGIS, both report languages, source snapshots and QA/run evidence. Keep the chosen package's subfolders together. Use copies for reviewer edits/recomputation, so the sealed package remains reproducible.

The package status READY_FOR_REVIEW means files were generated and checked. It does not mean hydraulic QA, field applicability or design adequacy passed. Regenerate reports/delivery retries exports without another solver run. Read warnings before treating any result as a design conclusion.

## 6. Problems and stopping

- Missing inputs: fill them, import a complete native model, or expand Stop this project and abandon. Abandon keeps files; no name or explanation is required.
- Download failure: correct connectivity and Retry preparation. Previously saved values remain.
- Unsupported geometry/plan: supply a supported steady model; the adapter does not guess unknown native syntax.
- Solver blocked: inspect Technical details and the task log; resolve the installation/open-project issue. No mock result is substituted.
- GIS export incomplete: hydraulic results can still be visible; retry delivery after resolving the reported cause. Do not label the missing map as complete.
- Changed inputs after a finished run: create an independent editable revision on Results for a workflow-built model. The original run is retained; recheck and confirm the revised inputs before calculation. For imported native models, edit in HEC-RAS and import a new project.


## Interpretation

Public-model reproduction checks software behavior, not current field conditions. Coordinates and surface DEM do not establish buried geometry. Read [limitations](LIMITATIONS_EN.md) before using a result for design.

[Results: complete native output, revise, compare and launch QGIS](RESULTS_REVIEW_EN.md)

## Delete and restore saved projects

Expand the project entry, choose **Delete project** on the version you want to remove, then **Confirm deletion**. Other versions stay in the same entry, including when you delete the original. A running version becomes eligible after its current task finishes.

Open **Deleted projects** and choose **Restore project** to put that version back in its original entry. Files stay in their original location, so related revisions can use them and they continue to occupy disk space.

## Complete a draft, compare editions and hand over the results

1. Open the incomplete draft. **What should I do next?** shows the first task and keeps other groups collapsed. With sections and site documents available, try automatic draft preparation first. On a calculated revision, open **Hydraulic review → Comparison with previous calculation**.
2. If a colleague has the missing site or design data, export the missing-site CSV. Fill `value` in the displayed `unit`. Enter the model's matching elevation `datum` where applicable and cite the record, page or location in `source`. Use `reported` for values stated in the source and `assumed` for engineering assumptions. Leave unknown values blank. Import the returned worksheet, select the applicable candidates and confirm the complete input list before solving.
3. When choosing an edition, review native warnings, native errors, wet ends and the largest stage change at verified common centers. Expand the wet-end list for profiles, stations, sides and water depth above the endpoints. Check floodplain connectivity on the map. A dash for native warnings means evidence is incomplete. Inspect section and profile correspondence if the inventories changed.
4. In the results overview, compare the baseline and revision, including changed sources, headwater, tailwater and remaining conditions. Choose the edition and click **Prepare handoff for the selected use**. Transfer the entire generated `Handoff_…` folder. It contains `Complete`, `Minimal` and two offline entry pages. Open `Start_EN.html` or `Start_zh-CN.html` in the copied folder to check the use limits, reports, map and HEC-RAS project. If a delivery condition is open, the handoff is for diagnostic review.
5. After an interruption, reopen the project. Document analysis, reports and delivery have separate retry actions. Choose **Recover saved solver result without recalculating** when verified native outputs exist. If the confirmed inputs survived but the solver still needs to run, resolve the original error and choose **Confirm and resume approved computation**. If the application identifies changed evidence, restore the matching files first.

**Request records together.** On a draft, open **Request site records or measurements**. Request crossing, road and relevant vertical control from the survey team together. Route event discharge to the hydrology provider. Each worksheet identifies missing fields, conflicts and adopted values to verify. Enter incoming findings in `value`, identify units, datum and source, then import under Site materials and review the candidates. Assumptions remain available for conditional screening.

**Explain a river revision.** Under **Hydraulic review → Comparison with previous calculation**, choose **Inspect both native runs at this station**. The preview opens at the largest water-level change at a verified common center. Check the two native profiles, floodplain shares, warnings and any available observations or boundary tests. Choose **Save this comparison for a decision** to retain the first run, record a preference for the second, request a survey or defer the choice. Add a note if useful. Regenerate reports to include the selected station, run and note.

### Start from ordinary files

For a crossing, start with coordinates. Under **Site data and source files**, select the site folder, inspect the filenames and save the selection. If two files share a name, select the intended originals individually. Open the photos and location file. If either portal or flow direction is ambiguous, download the portal survey request and return to the saved project when the marked plan or field coordinates arrive. Map picks and approximate road widths support conditional screening. Record their basis when confirming the inputs.

For a surveyed river, select **Georeferenced river survey package**, select a folder containing one `survey.json`, then **Inspect survey sources and event criteria**. The importer checks every listed file against the manifest. Where a recognized protocol supplies a threshold, choose **Use these event conditions** and review the event, station and threshold before calculating. For other surveys you can include a manifest-listed `observed_profiles.csv` using the observation CSV template and an additional `profile` column matching the native profile name. Document the event date, coordinates, datum, units, resolution or uncertainty and original source. Use one event and date per profile. Set the project tolerance separately under intended use.

For a previously downloaded USGS site, **Use previously downloaded site terrain** accepts a DEM with its acquisition receipt and optional NAIP imagery with its own receipt. Confirm the DEM vertical unit and datum from the source.

### Choose a result for handoff

In **Hydraulic review**, inspect the same side of each persistently wet section in both editions. The endpoint may have moved. Compare floodplain connectivity, stage and discharge shares before extending again. A missing field measurement can be the next action. After selecting an edition, you can add a short note for the recipient. To send the earlier run, choose **Keep previous calculation**, then **Open selected baseline** and create its handoff. The opening guide identifies the run, allowable use, outstanding conditions and available observations. Transfer that whole folder.

With survey inputs, **Use archived imagery for this survey** accepts just the dated NAIP GeoTIFF and its acquisition receipt. The survey manifest continues to supply the terrain and vertical reference.

**When the initial crossing cuts intersect.** Locate the conflicting pair on the DEM and choose **Mark exterior channels on the map**. Trace each exterior channel in downstream order with at least two points per side. For a coordinate return, verify the CRS shown on the map, then use **Enter a point in the map CRS**. Propose sections again and zoom in to check the reviewed channel path and connected floodplain. After calculating, check wet ends, boundary influence and stage. If the path is still ambiguous, keep the draft and download the field request.
