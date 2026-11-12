# SteadyReach: user guide

**English** | [简体中文](USER_GUIDE_CN.md) | [Home](../README.md)

## 1. Open the app

Double-click `start_workflow.cmd`. Keep its console running. It opens a local browser page; all project files remain on your machine. With an installed environment there are no PowerShell commands to type during normal use. The default language is English; select 简体中文 to change it.

For a missing Python environment the launcher invokes the retained setup procedure. HEC-RAS must be installed and discoverable. QGIS supports editable GIS/exhibit production; LibreOffice provides PDF conversion. Do not close an unrelated open engineering project to satisfy an automated check: save/close it yourself if it prevents an owned solver session.

The homepage lists saved projects. Use Open / continue after restarting the launcher. The browser address changes between sessions; open the current launcher address rather than an old bookmark.

## 2. Choose your starting information

**Coordinates or partial information:** enter a project name, WGS84 latitude and longitude in decimal degrees. Longitude is negative in the western United States. Enter discharge in cfs only if known; optional Manning n values can also be supplied. Leave unknown fields blank. Select Prepare project. The program queries/downloads USGS terrain and reads available metadata; it then pauses with the model inputs that still need attention.

**Existing model:** select the `.prj`, selected `.pNN`, corresponding `.gNN` and `.fNN` together. A local `.prj` path is an alternative if file selection fails. Type the intended plan, such as `p01`, if the source's saved plan is different or unavailable. The preview shows both saved and selected plans. Previous result files are not needed or imported. Coordinates are needed for automatic map acquisition; if no map is required, omit coordinates and uncheck GIS.

For a new model, first use the [detailed no-model guide](NO_MODEL_GUIDE_EN.md): material preparation, map picks, conditional ranges, road sampling and final confirmation.

## 3. Complete the model on one page

With a native model, inspect its profiles, barrel groups, cross sections, roughness and boundaries. Supply the native foot convention and model elevation datum. For GIS, also supply the native projected CRS and confirm the displayed DEM elevation unit/datum. The app can read a DEM metadata candidate, but cannot reliably infer an undocumented native CRS. A datum mismatch prevents mapping; the app does not invent a datum shift.

If a previously entered discharge or roughness conflicts with the imported model, the discrepancy is shown. Either select the correct source model, or explicitly select Use native values instead of earlier entries. The prior entries remain in a separate record. Importing a model never silently replaces them.

Without a native model, expand Flow and roughness, Structure/units/boundaries and the section controls. Enter the actual values available from drawings, surveys or engineering judgement. Necessary values include flow, roughness, structure shape/count/opening, length, inlet/outlet elevations, floor/inlet type, road geometry, boundaries and cross sections. There is no mandatory name, reason or individual confirmation field. User entries are recorded as unverified user inputs. Clicking a reference candidate preserves its assumption class and supporting range/source; it does not label the candidate as a measurement.

For DEM-derived sections, expand Generate sections from DEM. Check DEM units/datum, load the map and select at least two anchors on each exterior reach, ordered upstream to downstream. Keep the covered crossing out of those terrain routes. Width/spacing are editable sampling proposals, not known site dimensions. Generate candidates, inspect the sampled sections and bank candidates, then accept appropriate bank positions individually or in a batch. Pick left/right toggles visibly identify the active selection. Missing terrain, intersecting cutlines, invalid bank order and stale section fingerprints still block use. Structure and hydrologic data still require input.

Optional supporting files can be saved together without descriptions or reviewer names. Photos/PDFs are retained as material; the workflow does not automatically read arbitrary photos into a hydraulic model. A missing length or invert remains missing until a value is explicitly entered.

Changes save automatically after a short pause; wait for Saved locally. Save draft is also available. An invalid numeric value must be corrected. Returning to the project list or starting a run saves current edits. If saving has not finished, leaving the browser warns about unsaved changes. Downloads can be retried without replacing the completed draft.

## 4. Confirm the complete parameters, then run

Open Review all parameters. Check the full list, units, sources and estimate/assumption labels. Expand long arrays; Edit values (all fields) allows corrections. Missing or invalid inputs are identified with field navigation and keep Run disabled.

After edits, Save and refresh parameter list, check the single confirmation, then Confirm and run HEC-RAS. The backend checks input files and parameter fingerprints; changed inputs require new confirmation. No reviewer name, reason or individual signatures are required.

The program then builds an independent working model, runs actual HEC-RAS, extracts this run's results, checks output identity and hydraulic diagnostics, generates the reports, and builds both delivery packages. With GIS selected it also prepares terrain, contours, offline imagery when available, native Mapper associations and QGIS layouts/exhibits. Keep the launcher running; you can close the browser tab. Only one project processes at a time.

## 5. Read and deliver the result

The results page shows flow, headwater, tailwater, velocity and road flow where the installed interface provides them. A dash means unavailable, not zero. Multiple culvert groups may lack independently extracted group velocities. Expand grouped warnings to see unresolved issues.

Open Report_EN/Report_CN DOCX or PDF, and Summary_EN for the English executive summary. Open Minimal for the small native HEC-RAS/Mapper/exhibit package; open Complete for editable QGIS, both report languages, source snapshots and QA/run evidence. Keep the chosen package's subfolders together. Use copies for reviewer edits/recomputation, so the sealed package remains reproducible.

The package status READY_FOR_REVIEW means files were generated and checked. It does not mean hydraulic QA, field applicability or design adequacy passed. Regenerate reports/delivery retries exports without another solver run. Read warnings before treating any result as a design conclusion.

## 6. Problems and stopping

- Missing inputs: fill them, import a complete native model, or expand Stop this project and abandon. Abandon keeps files; no name or explanation is required.
- Download failure: correct connectivity and Retry preparation. Previously saved values remain.
- Unsupported geometry/plan: supply a supported steady model; the adapter does not guess unknown native syntax.
- Solver blocked: inspect Technical details and the task log; resolve the installation/open-project issue. No mock result is substituted.
- GIS export incomplete: hydraulic results can still be visible; retry delivery after resolving the reported cause. Do not label the missing map as complete.
- Changed inputs after a finished run: create a new project for a new analysis. The workflow does not offer an in-place redesign editor for completed runs.


## Interpretation

Public-model reproduction checks software behavior, not current field conditions. Coordinates and surface DEM do not establish buried geometry. Read [limitations](LIMITATIONS_EN.md) before using a result for design.
