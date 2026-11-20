# Results, revisions and optional sensitivity

[Q100 river sensitivity, grouped issues and operator counts](RIVER_REVIEW_EN.md)

**English** | [简体中文](RESULTS_REVIEW_CN.md) | [User guide](USER_GUIDE_EN.md)

For a reach without structures, choose **River reach (bridges excluded)** and follow the [river guide](RIVER_REACH_EN.md). It removes culvert/road fields and requires channel-bed representation and active boundary conditions. The crossing-specific steps below apply to culvert projects.

## Reduce native warnings in a river model

1. Open the saved river result, expand **Reduce native HEC-RAS warnings**, and select **Preview scope and original warnings**. A verified, full native export and matching run inputs are required. If the export is missing, use **Complete native outputs / refresh deliverables** first.
2. Review the maximum number of calculations (default 8, range 1–12) and the total width allowed for extensions (default 2,000 ft). Select **Confirm limits and start automatic review** once. The app shows progress for each isolated calculation. A baseline with zero warnings and all ends above the screening margin can finish without a solver run.
3. Compare **lowest warning count** with **suggested for review**. The latter first considers native errors and the number of profile/station locations affected by a wet end or critical-depth fallback warning, then fallback warnings, wet ends, numerical warnings, endpoints within 0.30 ft, total warnings and the maximum change in water level at original stations. Notes are counted separately. The minimum is limited to the distinct alternatives actually tested.
4. Choose a trial to open its native project folder, inspect its evidence, or create a separate editable revision. The original project remains available. Review changes in water levels, loss of conveyance and overbank flow against site evidence before adopting a trial.

The batch can extend or bend exterior limbs using the DEM and can coordinate neighboring overbanks while preserving the original channel and bank locations. On DEM-based channels it can sample new bank-aligned sections on either side of numerical warnings. Trials keep original flows, roughness and boundary conditions. Surveyed channel beds are protected from DEM infill. Explicit roughness subdivisions and ineffective areas constrain automatic edits. The 0.30 ft margin and the 25/100 m floodplain connectivity checks are screening assumptions. They do not establish freeboard, conveyance or design acceptance. Residual divided flow, structures and hydraulic controls may need surveyed openings, bathymetry, flood marks or engineering interpretation. A missing native export or a failed trial produces an incomplete result.

## Delivery assessment

Expand **Find records and plan fieldwork** to search official sources for the controlling uncertainty. The page reuses intact results on subsequent visits. Each task names a station, coordinates, requested measurement and decision. Gage distances, datum, rating dates and discharge coverage, peak records and catalog leads remain available with retrieval evidence under the project’s field_search folder. Open **Gage datum and station history** to read the USGS gage statement for a candidate station. Check the zero, location changes and subsidence at the date of the observation. The observation worksheet leaves the gage zero blank for review. Missing or failed sources remain visible. Confirm field applicability before changing hydraulic inputs.

Choose **Review checks in one batch** to preselect the applicable sensitivity, geometry alternatives and full-reach two-stage spacing checks. Edit the options and inspect the maximum native calculations. The workflow verifies previously computed cases on the same baseline and reuses matching evidence. A different width, refinement geometry or parameter endpoint calls for a new trial. One batch confirmation covers the displayed checks and export.

The grade applies to the selected computed edition. Open **Unadopted geometry alternatives** to inspect new wet ends and flow splits in the alternatives. Under **Engineering area of interest**, select two native stations to compare boundary, whole-model and local stage responses. Other checks retain their whole-model scope. The saved assessment records both grades and the selected endpoints.

Open the computed edition. The card at the top checks the run and grades what you can hand to another engineer. It gives the reason for the first action, the limiting findings and a link to each existing review tool. Select **Save assessment summary (.txt)** and then **Open saved summary**. The project keeps the dated assessment, run ID, source hashes and findings in its `assessment_exports` folder.

| Level | Intended use | Evidence |
|---|---|---|
| L0 | Recover calculation evidence | The selected run, profile inventory, native HDF, controller or sealed extraction cannot be verified. |
| L1 | Internal diagnosis | The native result is verified. An incomplete warning export, inconsistent discharge, stale or incomplete mapped packages, failed evidence check or non-site run limits handoff. |
| L2 | Conditional engineering review | The actual native result and both mapped packages are verified. Give the engineer the findings alongside the model. Typical limitations include wet ends, geometry-dependent overbank flow, boundary influence, unresolved warnings, partial spacing coverage or a surface DEM used for the channel bed. |
| L3 | Technical package ready for sign-off review | Checks for the applicable scope have supporting evidence. For a river this includes full-reach spacing across two refinements, applicable low/high boundary tests, surveyed bed representation and independent non-boundary event observations. The responsible engineer reviews the intended use and decides approval. |

Boundary effects above the workflow's internal 0.10 ft comparison threshold are listed by profile and station. A downstream stage prescribed in a field test cannot count as a validation point. Signed holdout differences outside the documented measurement uncertainty, or missing uncertainty, require interpretation. That comparison supplies an investigation trigger, not a design tolerance. Missing or mismatched observations remain visible limitations. A conditional culvert with unverified structures stays at L2 or below. QA dispositions must match the same run and issue inventory. A documented conditional explanation can account for individual messages. It cannot override a material flow inconsistency, a failed integrity check or a newly wet end.

For a new wet end, **Open related tool** opens the applicable section and geometry on the floodplain map. For a boundary response, it opens the sensitivity tool; inspect tested cases before rerunning. **Prepare QA revision suggestions** uses the existing independent draft route. **Open editable revision tool** opens the existing revision controls. Neither reading the assessment nor opening a tool starts HEC-RAS. A new calculation still uses the normal parameter confirmation. The assessment rechecks package bytes, Mapper dependencies and the packaged plan HDF against the displayed run. The package receipt's visual-review status appears separately. Engineering approval always belongs to the responsible reviewer.

## The normal path

For an independently revised model, **Comparison with previous calculation** shows river-specific metrics, every matching section's native WSE change, the largest absolute change and diagnostic counts for both editions. It verifies raw HDF/controller identity before comparing. Added or removed sections and unmatched profiles remain visible. Different discharges, model types, units or datums stop the comparison. A changed endpoint ID suppresses its endpoint delta. Matching RS labels still require checking any changed physical locations. The 0.1 ft flag is a workflow screening threshold. Native-message coverage and combined numerical/native records are listed separately.

1. Finish **Model → Review all parameters → Confirm and run HEC-RAS**. Read the completed calculation and unresolved hydraulic checks on **Results**.
2. Open the generated English/Chinese reports and Minimal/Complete folders. **Open QGIS review copy** launches the configured QGIS with its own environment and a disposable copy of Complete. This avoids broken system shortcuts and preserves the sealed package. Review-copy edits do not update the package automatically.
3. If the automatic adapter has all needed outputs, no supplementary upload is required. If it lacks a group table or complete warning list, use the optional step below. No reviewer identity, reason form or screenshot upload is required.
4. If assumptions or geometry need changing, create a separate editable revision. Confirm its inputs before a new solve. Old calculations remain available in the project list.

## Automatic next review

If the fixed-direction extension preview still has incompatible locations, the app also prepares **one independent joint direction and width draft**. It uses the same displayed width bound, existing DEM sampling and neighboring-section conflict checks. Eligible geometry, bank candidates and dependent values are staged together. The original model, its results and the fixed-direction preview remain available; no extra HEC-RAS calculation starts.

Choose **Open the prepared geometry revision** to inspect its map, profiles, interpretations and complete parameter list, then confirm a new calculation. Remaining review-item counts include retained hydraulic messages; they are not counts of geometric conflicts or proof that warnings have been closed. A previous water level screens candidate extent only. The revised geometry needs its own solve, boundary checks and spacing assessment.

Refreshing or preparing the same next review again reuses the saved independent draft. It preserves later edits and does not recreate a deleted or abandoned draft. If preparation only partly succeeds, open that draft and use **Prepare an automatic draft** after addressing the displayed cause. Existing results remain available. Older automatic coverage previews can use **Prepare joint geometry suggestions** to add this follow-up without replacing their saved scope. A manually selected study preview is not replaced.

After a new successful main calculation, **Suggested next review** automatically prepares the applicable next step. It does not start additional calculations or replace the saved baseline.

- When authenticated water levels exceed section ends, continuous river models receive a fixed-direction DEM extension preview. Suggested bounds are at most 3 repair calculations and 2,000 ft total section width. The preview lists changed sections and unresolved locations; inspect exterior floodplain connectivity and roughness suitability before confirming. Original interior elevations, bank positions in plan and hydraulic controls remain protected.
- When no positive wet-end exceedance is found, the app prepares the existing combined sensitivity/spacing review using adopted source ranges and feasible intervals. This condition only addresses section-end coverage; it is not a hydraulic QA pass. The existing limits and separate batch confirmation still apply.
- If no compatible extension exists, or a structure model needs geometry interpretation, the app keeps that decision visible. It does not skip straight to checks and imply that coverage is resolved.

Click **Inspect the prepared review**, inspect the relevant profiles and assumptions, then confirm in that panel when appropriate. Adjusting limits requires a new preview. Existing manually selected previews are retained. A completed coverage-repair result is not automatically repeated against its earlier baseline; continue from its final case when a new model edition is needed.

For older computed projects, **Prepare next review automatically** performs the same preparation through the task queue. Imported native geometry is excluded. A preparation error leaves completed calculations, reports and packages available; retry preparation or use the individual review tools. Preparation is bound to the exact baseline and source hashes. It never supplies engineering acceptance or reuses calculation consent.

## Checks and delivery with one confirmation

For a completed workflow-built model, expand **Prepare checks and delivery together**. Leave the desired checks selected, set the limits and click **Prepare checks and delivery preview**. Preparation does not start HEC-RAS.

- Sensitivity uses up to four active parameters with already adopted, applicable source ranges. It lists unsupported or unselected ranges; it does not invent percentage bounds. To choose another range, use the optional sensitivity panel first.
- Automatic nested spacing currently applies to continuous river reaches. It uses authenticated native results to recommend feasible intervals and displays excluded intervals, plan positions, profiles, inferred banks and coverage assumptions. The default interval limit is 12; the model and geometry limits may reduce the selection.
- Added-section coverage correction allows 0–3 rounds, default 2, with a displayed total-width cap (default 2,000 ft). Zero means no additional correction rounds. Original profiles and hydraulic controls remain fixed. Wet original sections, geometric conflicts, unavailable DEM data or the round limit stop further correction.

Inspect the proposed ranges, all relevant added profiles and the maximum native-calculation count. Tick the combined confirmation and click **Confirm and run checks → deliverables**. The app runs available checks in order, shows stage/case progress, then refreshes English/Chinese reports, the English summary and Complete/Minimal packages. The baseline geometry is preserved; the app does not choose a preferred boundary or automatically promote a trial case.

Unavailable checks retain their reason. A completed study can still be **NOT_CONVERGED** and require engineering interpretation; this does not prevent a report from documenting it. A failed native calculation or invalid evidence stops later stages. After correcting an external failure, **Resume checks and delivery** reuses the original confirmed scope and authenticates completed cases before reuse. A report/export failure does not require another hydraulic solve. Changed inputs or confirmation evidence require a new preview. Progress and saved previews survive reopening, and changing preview limits requires preparing them again.

Successful exports mean files are ready for review. Hydraulic QA, missing physical data and engineering acceptance retain their separate status.

## Complete missing native outputs

After each new solve, the adapter automatically exports **every computed culvert group/profile** and the complete **Errors, Warnings and Notes** table from its owned HEC-RAS process. It checks the native selectors, headers, model/output hashes, geometry and HDF/COM values before including the texts in reports. No AI service, reviewer form or screenshot upload is needed. Complete keeps the original text and export receipt in `Evidence/NativeSupplement`; Minimal keeps its normal compact contents.

For earlier runs, or after an unavailable export, expand **Complete native outputs / refresh deliverables → Retry native export without solving** and click **Export native outputs and update deliverables**. The action opens a separate copy of the saved results and automatically updates reports and both packages. The original computation is preserved and is not repeated.

Save and close HEC-RAS before starting. Keep a signed-in Windows desktop available. Output windows may briefly appear; the adapter uses the clipboard and leaves the last exported table there. Avoid copying other content during export. An existing HEC-RAS process is left untouched and produces a retry message. This adapter is limited to the inspected English/US Customary 7.0.1 build, one river/reach and one crossing with 1–10 groups. Unknown layouts, identity changes, clipboard interference or timeouts leave an explicit unavailable status without discarding a verified computation.

**Complete with differences** means all texts were obtained, but a native display value differs from HDF/COM beyond the normal half-display-unit check. Both values and an OPEN QA item are retained; machine results are never replaced. For hash-bound automatic exports only, discrepancies up to one 0.01 display unit may be retained this way; larger differences or blank/value conflicts reject import. This is an export consistency rule, not a hydraulic accuracy tolerance. The Phelps example exercises this state. Blank roadway flow stays unknown; rounded group sums are not used to infer it.

If automatic export remains unavailable, the collapsed **How to export missing native tables** section provides the manual fallback:

1. Open a copy of this run's HEC-RAS model and select its computed plan. In **View → Summary Errors, Warnings and Notes**, select the complete river/reach and every computed profile, then export text.
2. In **Culvert Output**, select each group and profile. Use **Copy to Clipboard (Data and Headings)** and save each table as a UTF-8 `.txt`. Preserve the header and empty cells. Do not substitute zero or hand-edit values to pass checks.
3. On Results, expand **Complete native outputs / refresh deliverables**. Select the files together. Check the complete-profile scope only if you actually exported that scope. Click **Import and cross-check exports**.
4. The app checks the plan/profile/group, barrel count, inverts, water and energy levels against the actual run, and checks the first group's independent controller values. A wrong header, duplicate group or inconsistent value is rejected. Text contains no run hash: correct run selection still depends on the person exporting it. The current strict adapter accepts the inspected English/US Customary HEC-RAS 7.0.1 table layout; unsupported layouts remain unresolved.
5. A new result edition is saved without changing the calculation. Click **Update reports and both packages**. The earlier reports/packages remain on disk but are hidden from the current result links until updated exports are ready. Blank road flow remains unavailable even if rounded group flows sum to the inflow.

Imported warnings may increase the issue count because previously unavailable messages are now visible. Importing evidence does not close hydraulic QA. Complete contains the original texts and hashes under `Evidence/NativeSupplement`.

For report-only updates, the app reuses the previous sealed package's verified offline imagery when its CRS, map extent and image hash match. No imagery download is needed. An edited package, changed extent or failed check produces an explicit error. Keep sealed packages intact and open review copies. New sites or changed extents still require suitable imagery acquisition.

## Revise without losing the original

Expand the Results revision section and create an editable revision. For models built by the workflow, it retains source references, values and provenance in a separate draft; the original run stays immutable. Edit, review the full parameter list and explicitly confirm the new run. Results then show matched-profile differences against the parent run. Imported native models must instead be edited in HEC-RAS and imported as a new project; no unsupported native redesign conversion is attempted.

**Computed section review / warning locations** shows actual computed water levels over the original cross-section arrays, together with native messages and adjacent sections. The edge-exceedance values identify low section ends. Separated wetted intervals do not prove longitudinally connected flow paths. In an editable revision, **Suggest wet-edge extension from prior run** tests a bounded set of wider DEM sections. Inspect the proposed changes using the normal DEM preview and intersection checks before applying. It does not modify the structure approach sections, replace the surveyed channel, raise terrain or force a solution. If the available DEM/domain cannot find high ground, review the model extent and bypass paths yourself. A dry-end proposal is not proof of hydraulic convergence; recompute after confirming changes.

## Optional sensitivity with one confirmation

Expand **Optional sensitivity batch → Suggest ranges from saved inputs** after computing a baseline.

1. Click **Suggest ranges from calculation inputs**. The app reads the sealed calculation decision and its verified sources. Previously adopted ranges are selected. Matching document ranges that were not adopted remain unselected, even when their numbers match the baseline.
2. Select up to four parameters. Check the source, river/site, units and applicability; edit any endpoint as needed. The table shows baseline values and the range basis. Unsupported or missing ranges stay blank rather than receiving arbitrary percentages. A range outside the baseline is labelled an alternative scenario.
3. Click **Prepare selected cases for one confirmation**. Inspect the baseline and the low/high variants together. Each variant changes one parameter; the batch does not test their combined effect. Bounds equal to the baseline do not create duplicate variants. The maximum is nine native runs.
4. Check **I confirm these conditional ranges, their source applicability and the displayed cases**, then choose **Confirm and run selected sensitivity cases**. Keep the launcher open. Preparing ranges or cases alone does not start HEC-RAS. Editing a range clears the previous proposal; changed input/source hashes require a new preview.
5. Watch per-case progress, then review upstream/headwater and matched-section water-level differences. Choose **Update reports and both packages** to include the verified comparisons and source records in the baseline delivery. The native model and results for each case remain in the separate study folder.

The collapsed **Or enter a single range manually** form remains available. Supported parameters include channel/overbank Manning n, active normal-depth boundaries, known downstream water levels and uniform culvert bottom fill. Section-specific roughness overrides and inactive upstream boundaries are explicitly excluded. Bottom fill applies along the full barrel; an inlet photograph alone does not establish that condition.

Ranges are conditional experiments, not measured confidence intervals or automatic calibration. Edited bounds retain the original reference and a separate assumption label. The workflow runs the baseline and variants sequentially with the real solver and generates case reports; it retains the baseline GIS package instead of repeating identical map exports. Failed computations or incomplete native exports remain visible. Neither a small response nor successful execution closes hydraulic QA or grants engineering acceptance.

## River section-spacing trials

After a river calculation, expand **Section-spacing trial** on Results.

1. Use **Recommend from native results** (default) to propose intervals from verified warnings and computed changes. The editable limit defaults to 12 intervals. **Intervals beside spacing-related warnings** and **Entire continuous reach** remain available.
2. Click **Prepare nested spacing preview**. The program inserts an intermediate DEM section in each selected interval, then splits those intervals again. The table shows the three case sizes. Saved previews survive reopening and language switching.
3. Review **Section plan view**, **Selected intervals and warning locations**, and the expandable new profiles. Red dashed lines identify inferred banks. Elevations come from the actual DEM. Bank fractions come from neighboring confirmed sections, added loss coefficients use the upstream interval, and existing left/channel/right reach-length totals are partitioned. These assumptions enter the batch confirmation.
4. Check excluded intervals. Bounded direction/width searches screen new ends against the maximum baseline WSE interpolated along the saved flowline. Intervals that cannot support both nested levels remain listed for geometry review. The trial covers the displayed accepted intervals. Missing DEM data, incompatible datum/CRS and unsupported section-specific controls require attention.
5. Check the confirmation box and click **Confirm and run three spacing cases**. Real HEC-RAS computes the baseline and two refinements sequentially. The progress table shows queued, processing, computed and failed cases. Keep the launcher open. Each case saves native inputs, results, warnings and reports.
6. Review both maximum retained-section WSE differences and the native-message/wet-end counts. The internal 0.10 ft check requires both consecutive refinements to meet the threshold at every retained section, including the upstream comparison section. **Convergence remains open** calls for further interpretation. A declining difference alone does not satisfy the check.
7. Select **Update reports and both packages** to include authenticated comparisons in the baseline delivery. **Open spacing trial files** opens the separate case models and reports. To revise a computed refinement, select it under **Continue from computed case** and click **Prepare editable QA revision from selected case**.

Automatic trials currently support one continuous workflow-built river reach. Original section elevations, banks and loss coefficients are retained. Flow, boundaries, roughness and interval length totals are held constant. Explicit roughness subdivisions or ineffective-flow areas need section-specific engineering treatment. Automatic drafts are limited to 500 sections and avoid channel intervals shorter than two DEM cells. Surface-DEM bed uncertainty, bridge influence, floodplain connectivity and hydraulic warnings remain part of engineering review.

HEC calls for sections at changes in discharge, slope, shape and roughness. The workflow uses that guidance for candidate locations and tests the native water-level response. [HEC cross-section guidance](https://www.hec.usace.army.mil/confluence/rasdocs/rasum/6.4/entering-and-editing-geometric-data/cross-section-data).

## Automatic wet-end repair batches

For a computed continuous river reach, open **Automatic wet-end repair batch** on Results.

1. Set a maximum total section width between 120 and 2000 ft and a limit of one to five new calculations. The displayed 2000 ft and three rounds are editable search limits. Check available terrain and floodplain connectivity.
2. Click **Preview bounded wet-end repair**. Inspect the proposed left/right extensions and expandable profiles. Blue shows the actual baseline water level. Existing samples and bank positions in plan are retained. Newly added exterior samples inherit the selected overbank roughness assumption.
3. Review the conditional exterior-material assumption and limits, check the confirmation box and choose **Confirm and run repair batch**. Each round uses the previous actual water levels, prepares compatible fixed-direction DEM extensions and invokes HEC-RAS. Keep the launcher open. The saved baseline is explicitly identified as reused.
4. The batch stops when all computed ends are dry, the confirmed round limit is reached, no compatible extension is available, or a computation fails. The progress table identifies unused rounds. Original profiles, bank plan positions, direction, flows, boundaries and roughness are verified at each step. Explicit roughness subdivisions, missing terrain or geometry conflicts can require manual review.
5. Review the wet-section and native-message counts and successive water-level changes. Open **final repair reports**, **repaired Minimal** or **repaired Complete** for the last successful case. The main result links still refer to the starting baseline. The batch report records every completed round and its stopping condition.

A failed export can be retried through the saved confirmed batch. Completed, authenticated calculations are reused and the existing confirmation is preserved. Modified source or confirmation evidence requires a new preview. The final packages are independent of the original baseline. When extension changes the map extent, the batch acquires imagery for the new bounds within the configured download budget. An intact mosaic is reused when its bounds and CRS match.

If a calculation fails partway, completed case files remain saved. Resolve the reported error and retry the confirmed batch to finish the calculation and export the final packages.

Dry section ends establish the implemented coverage check. Spacing convergence, submerged-bed adequacy, effective floodplain connectivity, boundary influence, other warnings and engineering acceptance require further assessment. Use an editable revision for repairs needing changes to direction, actual bank position or hydraulic controls, and review those changes together.

## Continue from a computed case

An editable revision can now prepare [grouped bank replacements](AUTOMATION_EN.md#propose-bank-replacements-in-one-batch). Review old and proposed stations together and adopt selected candidates before the ordinary full-parameter confirmation. This changes the bank interpretation while keeping section samples and locations unchanged; it is not a section-spacing convergence test. The resulting report comparison identifies bank changes and their computed water-level effects. Terrain-derived stability does not establish hydraulic accuracy.

For refined models, use the [focused bank gallery](AUTOMATION_EN.md#focused-bank-review-after-refinement) in the new editable revision. Bank-review categories use current station identities. Added sections whose banks came from neighboring fractions remain explicitly assumed, even when the source case had no confidence metadata. Retained bank coordinates are not changed by this bookkeeping refresh.

The isolated Pagosa regression had 83 sections: 51 with inherited bank assumptions and 40 with terrain-interpretation flags, overlapping to give 80 distinct flagged sections. This is an unresolved interpretation inventory, not a new hydraulic warning count. Native `.prj`, `.g01`, `.p01` and `.f01` files were byte-identical before and after the metadata repair. The regression did not rerun HEC-RAS or establish engineering acceptance.

1. After a wet-end repair batch, click **Continue from final repair with automatic QA preparation**. For a spacing trial, select a completed refinement and choose **Prepare editable QA revision from selected case**.
2. The app verifies the selected calculation and source files, then opens a separate editable project. Its starting geometry, bank positions, flow, roughness and boundaries come from the chosen case. Section and profile identities carry the matching input provenance across changed section counts. The result comparison uses this selected calculation as the parent.
3. Keep the launcher open while **automatic preparation** runs. The program uses the selected case's actual water levels to search for compatible DEM extensions and direction changes, proposes banks for changed profiles, and fills dependent draft values. Missing or conflicting information remains visible. Completed preparation returns to the model page.
4. Inspect the consolidated changes, plan and profiles. Edit uncertain banks, flow paths or assumptions as needed. Open the complete parameter review and confirm when ready to calculate. The new calculation writes its own native results, reports and packages.

Every continuation requires a fresh full-parameter confirmation. Local terrain and imagery references are resolved for the new project location. Unchanged geometry retains its bank-method metadata through review. Altered section samples trigger fresh candidates and invalidate the old geometry review. If source hashes have changed, reopen the source calculation and resolve the reported mismatch before continuing.

If another project is processing, the independent draft opens with the reason preparation was deferred. Wait for that job to finish, then choose **Prepare an automatic draft** in the saved revision.

The page stays in **Processing** while its background task is alive, including the source, geometry and parameter substeps. Progress refreshes automatically; an intermediate saved draft does not mean preparation has finished. A stopped worker is shown as interrupted with saved inputs retained.

## Changed parameters after geometry edits

Open **Review all parameters** after adopting a geometry revision. Identical derived values with identical ranges and source evidence are rebound automatically. If the derivation has materially changed, **Review changed dependencies together** shows each saved value, its previous basis/range, and current candidates with their conditions and ranges.

Choose a current candidate, or explicitly choose **Keep saved value as a conditional assumption** after checking its applicability. Retaining an old value records the previous derivation and changes its classification to an assumption; it does not claim that the new geometry produced that value. Further geometry changes trigger another check. **Edit value in complete list** opens the ordinary editable field when neither choice fits.

Click **Save these decisions and refresh review** once for the selected group. No choices are preselected. You may resolve some fields first; others continue to block computation. A stale page, changed evidence, or invalid selection rejects the whole group before saving. The page reports successful saves and refreshes the complete input review. Confirm the updated inputs separately before running HEC-RAS. No reviewer name or explanatory form is required.

If map or package export fails after computation, the results page keeps the reports and shows **Retry delivery without solving** beside the error. Resolve a missing dependency, or retry a transient map-service failure. The action rebuilds reports/packages from the same calculation; it does not rerun HEC-RAS. The previous failed attempt remains recorded.

## Automatic revision interpretation

For a newly created editable revision, the parent calculation reference is carried into the confirmed configuration. After computing, **Comparison with previous calculation** reads both runs' sealed input snapshots and native water levels. It lists changed hydraulic inputs, added/removed sections, changed profiles, center displacement, direction changes and bank displacement in map coordinates. Extending a section can change bank station numbers while leaving their actual map positions unchanged; this is identified automatically.

The results page distinguishes the maximum difference at matching station IDs from the maximum at verified unchanged centers. A moved or unverifiable center is excluded from the latter. The 0.01 ft coordinate-matching tolerance is a bookkeeping tolerance, not survey accuracy. Even an unchanged center can have a changed profile shape or hydraulic controls. When geometry and other inputs changed together, the page and reports explicitly state that the comparison is not an isolated section-spacing convergence test.

Both technical reports and the English summary include the revision interpretation automatically; full values and source references remain in `report_data.json`. Complete includes the referenced parent-result and input-snapshot files through its report-source index. Missing or modified evidence is reported as unavailable. This comparison highlights consequences and review priorities; it does not automatically accept a revision or resolve engineering QA.

## Remaining human decisions

Check source applicability, datum, physical opening identity, buried geometry, effective flow paths, uncertain banks, inlet/floor/obstruction assumptions and boundary validity. Review Mapper/QGIS alignment and final report pages. User-authored source notes are retained in their original language; if Chinese construction notes occur in an English report, the report flags language review. Supply suitable English wording before an English-only external delivery. No local translator is assumed to preserve engineering meaning.

## Automatic DEM / QA proposals

[Automatic layout and QA repair](DEM_AUTOMATION_EN.md) adds anchor searches, adaptive positions/widths and wet-end extensions preserving original samples. **Prepare QA revision suggestions** on Results proposes changes in an independent revision; adoption still requires full parameter confirmation before a solve. Direction, flow connectivity, structures, boundaries and unresolved warnings remain engineering decisions, not convergence or design acceptance.


After boundary sensitivity completes, **Prepare QA revision suggestions** also reads verified cases bound to that exact baseline. It screens wet ends against their maximum computed water levels and reports the included study count. Geometry, flow, roughness and regime must match. The preview preserves source hashes and requires adoption followed by a fresh calculation. [Preparation and automation assessment](AUTOMATION_EN.md).

## Automatic next-step guidance

On Results, **Suggested next steps from this calculation** automatically checks the native result identity, warning evidence and completed studies belonging to that exact baseline. It groups the work into native evidence, flow/output consistency, boundary response, wet-end repair, flow-path interpretation, section spacing, physical inputs and delivery. Unknown messages remain explicitly listed. The order is a work sequence, not a risk score or engineering acceptance.

Expand an item and choose **Open relevant review tool**. The matching panel opens and receives focus; no input changes and no calculation starts. Preview and final-confirmation controls in that tool still apply. The guidance reports temporary failures with a retry button and ignores responses from a project you have already left.

A completed repair batch is a separate calculation: baseline warnings remain visible, and the guide points to the existing batch before suggesting repetition. A small boundary response does not validate the boundary. A spacing test for a parent model does not establish convergence of the current changed geometry. Source or study evidence changes remain errors; incomplete studies cannot suppress required work. The guide does not prescribe ineffective-flow areas, relocate banks, select boundary slopes or close warnings automatically.

The Pagosa regression used the existing isolated 83-section Q100 calculation and its nine-case sensitivity batch. All 52 current diagnostic records were assigned to review groups, the four boundary variants were authenticated, and the maximum tested boundary response was 1.59375 ft. The guide correctly retained spacing as untested for this exact baseline and avoided repeating a complete native-warning export. This test reused verified real outputs and did not invoke HEC-RAS or change either the original or isolated project.

## Review computed sections without hunting through native windows

On Results, expand **Computed section review / warning locations**. The program reads the hash-verified native HDF and controller outputs, matches warnings to their profile/reach/section and shows every matching section. **Inspect flow paths and transitions** in next-step guidance opens this panel directly. No solver runs or input changes occur.

- Filter by profile, **Warnings / observations** or **All computed sections**, then search a station ID or warning code. Unlocated/global messages remain visible separately.
- Expand a section to see its original message, native ground, model banks, computed water surface, energy grade and available critical water elevation. Missing values remain blank. Blue bars and the table identify geometric ground/WSE intersections.
- Compare the immediately upstream/downstream native values and channel distances; buttons open those neighbors without switching applications. The local plan shows the bound cutlines, banks and wet intersections when geographic correspondence is available. It is not an inundation map.
- Open the related coverage, spacing or editable-revision tool from that section. Those tools retain their own previews and confirmation before any model change or calculation.

This panel supports one continuous native reach with verified international-foot output. A changed result/source or mismatched native geometry is rejected. Missing geographic correspondence leaves the actual native profile available with an explicit notice. Plotting wet ground does not establish effective conveyance, bypass connectivity or ineffective-flow boundaries; these require engineering interpretation. The panel does not close warnings. The [HEC Critical Creek example](https://www.hec.usace.army.mil/confluence/rasdocs/rasappguide/latest/critical-creek-example-1) illustrates reviewing section graphics, detailed results and native messages together.


## Automatic spacing selection and recovery

The selector matches the sealed native section samples and banks to the current geometry before proposing intervals. A changed baseline configuration requires a new computation first. Solver-difficulty messages take priority over spacing advisories; computed energy loss above 1 ft, change in native weighted velocity head (EGL minus WSE) above 0.5 ft, or adjacent channel Froude values below 0.9 and above 1.1 can also propose an interval. The head-change checks follow [HEC troubleshooting guidance](https://www.hec.usace.army.mil/confluence/rasdocs/hgt/latest/tutorials/1d-steady-flow/troubleshooting-with-hec-ras). The Froude band and ordering are workflow screening choices, not engineering acceptance criteria. Missing values remain unknown. These observations do not prove that spacing caused a warning.

The preview displays the actual values, warning codes, selected intervals, excluded intervals and candidates deferred by the count limit. It screens section-specific roughness/ineffective controls, bent cutlines, native station precision and space for two refinement levels at no less than two DEM cells. Exact DEM coverage and joint layout checks follow; an unavailable interval is omitted with its reason, and automatic selection tries the next eligible candidate. Existing sections and hydraulic controls are retained. Full-reach convergence is not inferred from a limited selection.

When no complete two-level trial fits, the page saves a **No eligible intervals** explanation and offers no calculation button. More sampling cannot improve the original DEM accuracy. Inspect the excluded locations, change the geometry in an independent revision, or obtain better data as appropriate. Unlocated spacing messages remain visible.

If a confirmed batch has incomplete cases, use **Retry incomplete spacing batch** after resolving its error. For a report-only failure, the workflow verifies the same configuration, inputs, summary, extraction and native outputs, then writes a new report edition without calling HEC-RAS. The original failed attempt stays recorded. A missing or changed native record blocks this reuse; an actual calculation failure may require another solve. Projects that never used grouped bank replacement do not require that optional selection record.

### Resume an incomplete batch without repeating completed calculations

Restart the app after updating. **Retry incomplete spacing batch** authenticates each saved case against the confirmed configuration, source inputs, sealed extraction, native input files and native outputs. A completed case is reused even if the software code changed since its original calculation. Its original run ID is retained; this is reuse, not a fresh validation of the current solver adapter. Intact registered reports are reused. Missing or unusable reports receive a new edition without calling HEC-RAS. Prior case records and report editions remain available. An interrupted report recovery can reuse the edition that was already registered.

Changed calculation evidence stops that case and remains blocked on a repeated retry; it does not silently trigger a replacement solve. Restore the original evidence or prepare a new reviewed study. A genuinely unfinished calculation follows the normal solver path. Software QA, report visual review and engineering acceptance remain separate.

The spacing result now distinguishes wet sections retained from the baseline from wet sections introduced by refinement, retaining each affected profile while counting a section only once. A wet-ended spacing series is provisional even if the numerical differences satisfy the threshold. Use **Prepare editable QA revision from selected case**, review the automatically prepared coverage proposals, confirm the revised model and compute it, then assess spacing again from that baseline. The saved nested series is not modified. For an existing fixed batch, that independent revision remains available. New spacing batches can instead include bounded automatic coverage correction as described below.

### Keep added sections covered during a spacing batch

**Section-spacing trial** now offers **Automatically extend added wet sections within the confirmed limits**. Choose 1–3 correction rounds and a maximum total width of 120–2000 ft. The saved preview shows these bounds and the maximum number of real case calculations (three initial cases plus three per correction round). Review the added profiles, inferred banks and these bounds, then confirm once. Missing or changed evidence still blocks the batch.

After each complete three-case series, the program reads actual water levels from all profiles. It attempts straight exterior DEM extension on added sections only. Shared profiles receive the same extension in both refinement levels, while each level keeps its own LOB/channel/ROB length partitions. Original section shapes, interior points, bank plan positions, flow, roughness and boundary conditions remain fixed. No terrain elevation is fabricated and no warning is closed by changing a control parameter.

Each correction is a new saved series. The batch stops when ends are covered, the unchanged baseline has wet ends, no compatible extension exists, the round limit is reached or a calculation is incomplete. It preserves every round, progress, input/result hashes and the exact reason for stopping. Restarted batches reuse authenticated completed calculations. The final round's numerical convergence and wet-end coverage are reported separately; a dry endpoint is not proof of floodplain connectivity or engineering acceptance. Continue from a selected final case as an independent editable revision if original geometry needs engineering changes.

### Locate spacing response without opening three projects

After a complete three-case spacing trial, expand **Locate spacing differences and compare sections**. It authenticates the final series (including every bounded correction round when used), aligns native section/profile identities and lists the exact maximum locations and number of sections exceeding the saved internal threshold. Separate profiles remain separate; a newly added section is compared only where it exists in both consecutive levels. Missing outputs remain unknown.

The default list shows the largest water-level changes first. Select a profile, filter to all observations or all sections, or search an RS. Expanding a section shows all available WSE/EGL, critical elevations, channel velocity/Froude and minimum-error values side by side, overlaid water levels, the final native section and its mapped neighbors, and each case's native/diagnostic messages. Wet ends and changes across channel Fr = 1 are flagged automatically. The longitudinal view uses section order, not a distance scale.

This is read-only result review: no solver, geometry change or warning closure occurs. These observations do not establish the cause of a difference, an active flow path, a hydraulic jump or a preferred case. Use the existing computed-case continuation to prepare an independent revision when needed, then review and confirm its parameters. A changed result token or unavailable native evidence stops the comparison with a retry message.
