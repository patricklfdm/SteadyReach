# Starting without an existing HEC-RAS model

**English** | [简体中文](NO_MODEL_GUIDE_CN.md) | [Home](../README.md)

**Starting with one coordinate.** Choose **River reach (bridges excluded)** and supply the project title and location. Leave unknown numbers empty. The app searches for a directed USGS river, nearby mapped road crossings and a DEM covering the candidate bends and cross sections. Open **Automatic DEM layout / QA repair**. At a crossing, choose the intended reach by its two road names. Generate the preview, check the river and banks against the imagery, then adopt it. The parameter page shows populated values, sources, estimates and any missing inputs together. One final confirmation starts HEC-RAS. [River instructions](RIVER_REACH_EN.md)

For a reach without structures, choose **River reach (bridges excluded)** and follow the [river guide](RIVER_REACH_EN.md). It removes culvert/road fields and requires channel-bed representation and active boundary conditions. The crossing-specific steps below apply to culvert projects.

Use **Prepare an automatic draft** after source import and crossing/metadata checks. It stages geometry and labelled estimates together. Resolve highlighted issues, then use the single final parameter confirmation. The tools below provide detailed inspection and correction routes. [Automatic preparation](AUTOMATION_EN.md).

Use `start_workflow.cmd`. The supported scope is one reach with one box/circular culvert crossing and 1D steady flow; distinct openings may use separate groups. Normal operation uses the local browser, without AI, reviewer names, signatures, per-field explanations or screenshot submissions.

Start with [source-linked consolidated preparation](AUTOMATION_EN.md) for multi-group pairing, formulas, early geometry checks, batch parameter choices and bank profiles.

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

Start with **Find, import and inspect source material**: public lookup, PDF/text extraction, survey CSV and optional local Windows OCR now produce reviewable candidates. Existing inputs are preserved. Survey points can be inspected on the DEM without a separate QGIS step. See [source assistance](SOURCE_ASSIST_EN.md) for coverage, folder import, units and failed-attempt handling.

## 1. Create the project and acquire terrain

Select Coordinates / partial information. Enter a name and WGS84 decimal coordinates; western US longitude is negative. Enter known flow/roughness and leave unknown items blank. Prepare project retrieves DEM and metadata.

Progress, completion and errors are visible. Saved drafts survive retries. Missing information pauses input completion without starting the solver.

## 2. Inspect extracted candidates and supply remaining values

Use A · Flow and roughness and C · Culvert and road. Each field has an origin label. Source / change input origin lets you choose a transcribed source value, user entry/correction or estimate/assumption. No name or explanation is required.

Unknowns may stay blank or receive an explicit assumption. Selected candidates retain their assumption/source records; edits preserve the previous origin. A reported value is not automatically an independently verified measurement.

## 3. Propose anchors and sections, then review them together

Start with **Automatic DEM layout / QA repair → Propose anchors and sections**. Associated survey mouths, saved map positions or a coordinate-only DEM search supply candidate exterior anchors, adaptive section positions and widths, with intersection checks. Select a layout, check direction/coverage/banks, then **Adopt and review calculation inputs**; this does not start the solver. See the [DEM automation guide](DEM_AUTOMATION_EN.md) for complete steps, coordinate-only direction ambiguity and QA revisions.

Use the manual alternative below if candidates do not describe the actual flow path. You do not need to complete these picks before requesting an automatic proposal.

### Manual picks / adjustments (alternative)

1. In B · DEM, sections and banks, check vertical units/datum and load the DEM. Zoom as needed.
2. Pick at least two upstream-reach anchors from the remote end toward the inlet.
3. Pick at least two downstream-reach anchors from the outlet toward the remote end. Both lists follow flow direction; exclude the covered crossing from the exterior terrain routes.
4. The initial 200/40 ft width/spacing values are editable sampling proposals, not site dimensions. Allow at least four functional sections and sufficient flow-area coverage. Generate / replace candidate sections retains the prior draft history.
5. Resolve early cutline and opening-projection conflicts first. Use the bank-profile gallery to inspect uncertain profiles, revise points and save only selected changes together; other saved banks are retained.
6. Review parameter candidates together: identifiers, face stations, flow-path lengths and structure/road derivations. Existing inputs default to Keep saved value; select replacements explicitly.

Map points save automatically; the active mode and counts remain visible. Undo removes the current mode's last point. Editing map picks does not silently change generated sections: explicitly regenerate to replace them, then review new bank/structure candidates.

Within an exterior reach, channel-length candidates follow the saved flowline; equal overbank lengths remain an explicit assumption. Across a structure or without a usable line, the separate straight-distance candidate remains conditional. Review unequal paths and bypass. RS values are identifiers, not surveyed chainages. Intersections, NoData and invalid bank order remain blocking. Editing sampled positions/elevations preserves the original DEM history and removes the claim that those values are unchanged DEM samples.

## Intersecting sections: adjust, resample and apply on the model page

Under **B · DEM, sections and banks**, open **Adjust section directions / DEM preview** to see the affected river stations. Red map cutlines identify spatial issues. With point-picking modes off, click a section line to select it. Positive rotation is counterclockwise about the section center in map coordinates.

1. Choose **Suggest rotations (keep widths)**. A bounded search within ±30° can adjust adjacent sections together, retaining widths and centers. These are layout candidates, not proof of flow-normal orientation or complete floodplain coverage; complex layouts may remain unresolved.
2. Alternatively select a section and edit its rotation or width; shift and sampling controls are collapsed. **Add / update adjustment** combines several changes. Editing the current section and clicking Preview also includes that edit. Reducing width is an explicit user choice; do not omit conveyance merely to remove an intersection.
3. Choose **Preview DEM resampling**. The app reads the actual raster and displays old/new profiles, green dashed candidate cutlines, remaining spatial issues and missing elevations. Saved geometry remains unchanged. Apply stays disabled for intersections involving edited sections or missing elevations. Issues elsewhere remain visible and still block solving.
4. After inspecting locations, flow paths and elevations, choose **Use this DEM preview**. The previous draft is retained. Only changed profiles lose bank selections; other saved banks and still-valid reviews are retained. Center shifts invalidate neighboring reach lengths; face changes invalidate dependent station references and offsets. Sources, opening dimensions and map anchors remain saved. Changed inputs or DEM files invalidate an earlier preview.
5. Recheck banks and missing inputs, then confirm all parameters before HEC-RAS runs. Removing intersections does not establish hydraulic QA or design acceptance.

**Map controls:** drag to pan; use the wheel for fine zooming around the pointer; zoom buttons change the scale by about 20%. **Fit DEM** and **Fit sections** recover the extent. With the map focused, arrow keys pan, + / − zoom and Home fits the DEM. Dragging never adds a point, even in picking mode; a click adds one. Scale, DEM resolution, CRS and coverage boundary remain visible. Views range from eight DEM cells to four times the largest DEM dimension. Blank space outside the coverage is unavailable terrain, not a new download; zooming does not improve DEM resolution.

## 4. Use conditional structure and road proposals where appropriate

- **Length/layout:** pick inlet/outlet group centers. Select the opening group in the map to retain separate inlet/outlet picks for multiple groups. Survey-point associations can instead derive every mapped barrel together. Explicit gap spacing enables equal parallel multi-barrel proposals; inspect skew and unequal members. See [formulas and limits](AUTOMATION_EN.md).
- **Survey invert:** explicitly identify invert points or assume interior crown/low chord minus clear height in the association panel. Matching datum is required. Location-only associations supply no invert.
- **DEM invert:** with selected functional face sections/banks, explicit mouth picks and nearby exterior DEM sections, the app can extrapolate within-bank bed lows a short distance to a mouth. This assumes bed/invert continuity; it is not a buried-invert measurement. Sediment, drops, vegetation or embankments can invalidate it. The displayed interval only spans the near bed and extrapolated bed; it is **not a bound on the actual invert error**. No unsupported value is proposed if prerequisites fail.
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
