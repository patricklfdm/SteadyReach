# Starting without an existing HEC-RAS model

**English** | [简体中文](NO_MODEL_GUIDE_CN.md) | [Home](../README.md)

Use `start_workflow.cmd`. The supported scope is one reach with one box/circular culvert crossing and 1D steady flow; distinct openings may use separate groups. Normal operation uses the local browser, without AI, reviewer names, signatures, per-field explanations or screenshot submissions.

## Prepare available material

| Required information | Preferred material | If unavailable |
|---|---|---|
| Coordinates, actual crossing and flow direction | Location pin, aerials, site photos | Coordinates obtain USGS DEM automatically; identify the flow reaches and structure locations on the map |
| Discharge and profile | Applicable StreamStats/hydrology report | Leave blank until supplied in cfs; DEM does not determine Q100 |
| Count, shape and clear opening dimensions | Drawings, survey, scaled photos | Enter a reported value or explicit assumption; separate unequal openings/inverts into groups |
| Length, inlet/outlet inverts and datum | Survey/as-built drawings | Explicit mouth picks can propose a straight length; short exterior-bed extrapolation can propose a conditional invert where supported |
| Floor, entrance and blockage | Drawings, close photos, inspection | Supply or explicitly assume; blank never means clear/unblocked |
| Effective roadway width and crest profile | Road survey, plans, DEM | Sample a selected crest line; supply road width explicitly, never substitute it for barrel length |
| Roughness and entrance/exit losses | Site conditions and references | Select applicable documented candidates or edit their values |
| Sections, banks, flow-path lengths and boundaries | DEM, survey, site observations | Automated sampling/proposals still need flow-path and representativeness checks |
| Horizontal CRS, elevation datum and units | DEM metadata and survey notes | Read available DEM metadata; do not invent a vertical datum conversion |

Optional supporting files accepts several photos/PDFs at once. Originals are retained; the app does not claim arbitrary photo interpretation of buried geometry. Transcribe known engineering values into the matching fields. A separate evidence questionnaire is unnecessary.

## 1. Create the project and acquire terrain

Select Coordinates / partial information. Enter a name and WGS84 decimal coordinates; western US longitude is negative. Enter known flow/roughness and leave unknown items blank. Prepare project retrieves DEM and metadata.

Progress, completion and errors are visible. Saved drafts survive retries. Missing information pauses input completion without starting the solver.

## 2. Enter known values

Use A · Flow and roughness and C · Culvert and road. Each field has an origin label. Source / change input origin lets you choose a transcribed source value, user entry/correction or estimate/assumption. No name or explanation is required.

Unknowns may stay blank or receive an explicit assumption. Selected candidates retain their assumption/source records; edits preserve the previous origin. A reported value is not automatically an independently verified measurement.

## 3. Pick exterior reaches and generate sections

1. In B · DEM, sections and banks, check vertical units/datum and load the DEM. Zoom as needed.
2. Pick at least two upstream-reach anchors from the remote end toward the inlet.
3. Pick at least two downstream-reach anchors from the outlet toward the remote end. Both lists follow flow direction; exclude the covered crossing from the exterior terrain routes.
4. The initial 200/40 ft width/spacing values are editable sampling proposals, not site dimensions. Allow at least four functional sections and sufficient flow-area coverage. Generate / replace candidate sections retains the prior draft history.
5. Inspect profiles and uncertainty flags. Left/right bank buttons visibly toggle; select sampled points to revise banks. Individual or batch adoption and direct section-data editing are available.
6. Inspect and adopt missing layout candidates in a batch. These include model identifiers, structure/face stations, banks and reach lengths. Existing values are retained.

Map points save automatically; the active mode and counts remain visible. Undo removes the current mode's last point. Editing map picks does not silently change generated sections: explicitly regenerate to replace them, then review new bank/structure candidates.

Initial reach lengths assume equal straight center-to-center paths for channel and overbanks. Revise for bends, unequal paths or bypass. RS values are identifiers, not surveyed chainages. Intersections, NoData and invalid bank order remain blocking. Editing sampled positions/elevations preserves the original DEM history and removes the claim that those values are unchanged DEM samples.

## 4. Use conditional structure and road proposals where appropriate

- **Length/layout:** pick inlet/outlet group centers. For one identical group the app can propose a straight barrel length and inlet distance. Explicit wall/gap spacing enables equal parallel barrel-center proposals. Supply skewed/curved or unequal groups individually.
- **Invert:** with selected functional face sections/banks, explicit mouth picks and nearby exterior DEM sections, the app can extrapolate within-bank bed lows a short distance to a mouth. This assumes bed/invert continuity; it is not a buried-invert measurement. Sediment, drops, vegetation or embankments can invalidate it. The displayed interval only spans the near bed and extrapolated bed; it is **not a bound on the actual invert error**. No unsupported value is proposed if prerequisites fail.
- **Road crest:** adopt face station candidates first, then draw the crest left to right looking downstream. Sample the selected road crest. Its profile candidates appear under Culvert and road and require explicit selection. Check actual crest coverage, DEM resolution and possible low bypass paths.
- **Coefficients:** candidates carry applicability conditions and official references. Reference ranges are not site measurement uncertainty. A displayed gradual/abrupt section-loss scheme can fill missing values in a batch; do not mechanically apply subcritical guidance to mixed/supercritical conditions.
- **Boundary:** positive slopes sampled from exterior sections can serve as conditional normal-depth energy-slope proxies. The range describes sampled adjacent slopes, not a confidence interval. Adverse/insufficient terrain remains unresolved. Check reach extent and boundary sensitivity; do not substitute barrel slope for the remote energy slope.

All model fields remain editable. Arrays accept comma-separated numbers; matrices accept one row per line or JSON arrays. Wait for the local save message after edits.

## 5. Review once, then run the actual solver

Review all parameters lists every model field, unit and origin, plus project settings and source files. Expand long arrays as needed. Edit values (all fields) provides the complete editable form.

Missing/invalid inputs are identified with field navigation. Run stays disabled. After edits, Save and refresh parameter list.

Check the single confirmation covering parameters, estimates, banks and limitations, then Confirm and run HEC-RAS. This requests conditional computation, not engineering sign-off. Without confirmation the solver cannot start; changed inputs/files invalidate an earlier confirmation.

The app then creates a native model, runs HEC-RAS, extracts results, produces English/Chinese DOCX/PDF and an English summary, and generates requested Mapper/QGIS exhibits and both packages. Disabling GIS produces native-only packages without a map claim. Keep the launcher running.

## 6. Retrieve results or stop

Open Minimal or Complete on the results page. Complete retains the final parameter list, confirmation, supplied attachments and relevant estimates. Hydraulic warnings are separate: READY_FOR_REVIEW is not design acceptance.

To stop, expand Stop this project, choose Abandon workflow and the inline confirmation. Saved files remain; no reason is required.
