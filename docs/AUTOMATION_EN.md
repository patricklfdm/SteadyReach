# Source-linked preparation and one final confirmation

**English** | [简体中文](AUTOMATION_CN.md) | [No-model guide](NO_MODEL_GUIDE_EN.md)

For a reach without structures, choose **River reach (bridges excluded)** and follow the [river guide](RIVER_REACH_EN.md). It removes culvert/road fields and requires channel-bed representation and active boundary conditions. The crossing-specific steps below apply to culvert projects.

Use the model page's **Prepare together, confirm once** panel. It reduces repeated transcription and review without treating unknown buried geometry as measured data. It works locally without an AI service. It does not start HEC-RAS until the final parameter confirmation.

## Fast path for a new model

1. Create the site, allow the USGS terrain/source lookup to finish, and import the available site folder or files. Check the crossing, flow direction, elevation units and datum. Identify each opening's ends on the map or associate survey points when the material supports that interpretation.
2. In **Prepare together, confirm once**, click **Prepare an automatic draft**. The background task reuses extracted text, reads supported material, builds or repairs eligible DEM geometry, proposes banks and fills compatible source values and labelled conditional estimates. An initial layout is staged as editable geometry. Inspect the map and uncertainty flags when the task finishes.
3. Resolve the displayed source differences and remaining missing items. Existing manual values take priority. Use the bank-profile grid and numeric left/right inputs for corrections. Numeric edits snap to the nearest DEM sample and display the chosen station plus pending-save feedback. Both the single-section editor and gallery save through **Save all changes** or **Review all parameters**. Switching sections retains pending choices. Out-of-range or reversed banks show a persistent message and block saving.
4. Open **Review all parameters**. Automatically owned values refresh against current dependencies before this list is bound. The confirmation page groups uncertain bank pairs and source-extraction limits with links to affected parameters. Inspect these interpretations together with the complete values, assumptions, road alignment, floor/entrance/blockage, flow paths and boundaries. Confirm once to run HEC-RAS and generate the reports and both delivery folders.

The automatic button authorizes preparation of an editable conditional draft. The final calculation checkbox authorizes the solver. An unavailable or conflicting candidate stays unresolved. When a previous automatic estimate loses its supporting inputs, the app clears it and identifies the missing field. A manual correction takes ownership of that field and survives later automatic preparation.

### Conditional estimates available in the draft

- Identified mouth coordinates support plan length, approach distance and opening stations. Equal multi-barrel spacing requires an explicit wall/gap value.
- A short exterior DEM fit can provide a conditional invert if sampling and fit-stability checks pass. Its fit-window range describes the tested extrapolations. Review bed/floor continuity, sediment and possible drops.
- An entered road width and compatible mouth/face geometry enable a bounded road-corridor search. Separate upstream/downstream profiles retain exterior DEM elevations and bridge the opening envelope between suitable shoulders. The whole profile is labelled assumed, with samples and search bounds retained. Review road alignment, cover and bypass paths.
- Box-culvert construction can use a labelled concrete-floor, square-edged headwall scenario. Mixed flow, concrete roughness, losses and zero blockage remain editable scenario assumptions. Source conflicts require a choice.
- End sections with unresolved bank breaks are tested at wider DEM coverage within the existing search bounds. An eligible bank-continuity extrapolation from two adjacent sections remains a low-confidence assumption. NoData, intersections and unresolvable banks retain a focused review item.

Road/structure estimates and section geometry require site interpretation. Hydraulic warnings, sensitivity and engineering acceptance remain separate review outcomes.

## Detailed source and geometry tools

1. **Acquire/import the site material.** The existing USGS DEM/catalog lookup and document extraction run first. Inspect the source count, survey CRS, elevation units/datum and failed attempts. Import a site folder if anonymous public downloading is unavailable. Automated acquisition is limited to supported providers and document formats.
2. **Propose and check exterior flow paths.** Use [automatic DEM layout](DEM_AUTOMATION_EN.md) for anchors, positions/widths and bank candidates without first picking every point. Saved source associations take priority; coordinate-only alternatives can disagree on direction, so check the actual flow and road gap before adoption. Existing sections use QA suggestions; manually pick only when needed.
3. **Associate openings together.** Open **Opening groups and survey-point associations**, then **Suggest all opening pairs**. With one usable survey and separable mouth clusters, recognized `LC` and `CROWN` codes suggest a rectangular opening and circular pipe pairs, ordered looking downstream. Point numbers are not hardcoded. Check inlet/outlet IDs, group and barrel numbers against the sketch/map. Ambiguous clusters remain unresolved. Other codes can be associated by entering IDs.
4. **Choose what the elevations mean.** `Location only` produces no invert. `Identified interior invert points` uses the identified point elevations after unit conversion. `Assume interior crown / low chord` subtracts the entered clear height from the mean identified elevation and labels the result **assumed**. Exterior crown elevation, nominal outside diameter, sediment and a nonuniform soffit can invalidate that assumption. No vertical datum shift is performed. Multiple IDs at one mouth are averaged; do not combine different barrels or unrelated surfaces.
5. **Save associations.** This generates candidates without overwriting adopted dimensions or inverts. Additional groups are created only when the displayed creation option is checked; unknown dimensions stay blank. Associate every member of a multi-barrel group. Different member lengths/inverts do not get silently averaged; split unequal openings into separate groups or provide an explicit compatible representation.
6. **Generate sections and resolve early geometry issues before bank review.** The panel checks cutline intersections, missing elevations, projected opening overlap/out-of-section centers, adverse invert slopes and populated approach-length constraints. Tentative pairing warnings appear even before centers are adopted; confirmed conflicts block the relevant center adoption and final solve. Click **Inspect section**, request bounded rotations and preview actual DEM resampling. Inspect the direction/coverage before applying. Rotation suggestions do not establish hydraulic correctness.
7. **Review candidates and profiles together.** Use **Review parameter candidates together**. Existing values default to **Keep saved value**. **Select unique missing candidates** only prepares selections; inspect their formulas/conditions before **Save all selected changes**. Conflicting alternatives stay unresolved. You may edit any value directly. The **Bank-profile gallery / batch selection** shows saved selections and uncertainty; expand relevant profiles and save selected changes in one batch. It never replaces all saved banks with the algorithm's defaults.
8. **Confirm the complete model once.** Open **Review all parameters**. Missing/invalid inputs still wait for correction. Review assumptions, floor/entrance/blockage, boundaries, flow paths and all values. Only **Confirm and run HEC-RAS** launches computation. Saved source/geometry changes invalidate earlier confirmations; stale derived values are flagged for recalculation or an explicit edit.

## What is derived

| Candidate | Calculation and limitation |
|---|---|
| Opening length | Plan distance between associated mouth centers in the survey's original projected coordinates, converted to international feet; not a surveyed hydraulic barrel length |
| Invert | Identified interior invert elevation, or explicitly assumed interior crown minus clear height; matching elevation datum required |
| Each barrel's face stations | Orthogonal projection onto each face's station axis; skew can compress spacing, so overlap is checked before adoption |
| Inlet-to-section distance | Perpendicular mouth-to-upstream-face distance, explicitly a conditional approach-length proxy; not necessarily the distance along the barrel axis |
| Multiple groups without survey | Select **Opening group for inlet / outlet picks** in the map and pick each group's ends. Group-specific length, offset and station candidates are generated. Equal multi-barrel spacing additionally requires the entered clear gap; no hidden invert is derived from those XY picks |
| Road crest | `RDCL`/`CREST` survey-point elevations and projected stations, labelled conditional on these points actually describing the overtopping crest and adequate coverage; a road centerline is not necessarily the crest. Explicit DEM crest-line sampling remains available |
| Channel reach lengths | Distance along the saved flowline, where both sections belong to that exterior reach; overbank lengths remain an explicit equal-length assumption until their paths are known. Across the covered crossing, the separate straight-distance proposal remains conditional |
| Roughness, losses and normal-depth slope | Existing documented reference choices and supported exterior-terrain estimates, with applicability conditions; no automatic calibration |

## Progress and editing behavior

- Source documents and the original DEM remain unchanged. Actions show busy, saved or actionable error states.
- A still-current pending DEM preview is restored when reopening the tools. The separate manual preview tool waits for its Apply action; the automatic-draft button stages an eligible layout for final review. Changed input versions, associations or sources require a new preview.
- Resampling clears bank choices only on the changed profiles. Unchanged bank choices and still-valid review stamps remain. Moving a section center invalidates neighboring reach lengths; changing an upstream face invalidates dependent opening/road offsets and station references. Center-preserving rotations do not discard unchanged center-to-center lengths.
- Adopted automated values retain formulas, point associations, file hashes, units and assumptions. Changed dependencies are highlighted; the final gate prevents using them unnoticed.
- Review/assumption records are calculation context, not signatures or engineering certification. No reviewer name, reason field or evidence-upload ritual is introduced.

Human judgment is still needed when source semantics, construction, localized blockage, effective flow paths, boundary suitability or ambiguous banks cannot be inferred reliably. No unsupported numeric range is supplied just to complete the form. Spatial QA, solver completion and engineering acceptance remain separate.

## Save once, then review results

Use **Save all changes** to commit scalar edits, selected parameter candidates, opening associations and bank batches. A persistent banner lists pending batches. Returning to Projects, switching language or opening the final review also saves selected changes first. Saving is sequential: if a later batch becomes stale, earlier successful saves remain and unresolved selections stay available for correction. Saving map points refreshes related candidates while retaining pending choices. A choice whose basis changed is marked stale and waits for replacement or clearing. Individual candidate buttons also verify the current source and dependency context. **Select changed derived values** selects updated source-linked candidates for review without replacing manual overrides. Browser refresh/closure can discard unsaved candidate/bank selections; wait for Saved locally first.

After calculation, use [result completion, independent revisions, wet-edge screening and sensitivity batches](RESULTS_REVIEW_EN.md). These additions remove repeated transcription and export steps while preserving engineering judgment.
