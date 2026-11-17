# Results, revisions and optional sensitivity

**English** | [简体中文](RESULTS_REVIEW_CN.md) | [User guide](USER_GUIDE_EN.md)

For a reach without structures, choose **River reach (bridges excluded)** and follow the [river guide](RIVER_REACH_EN.md). It removes culvert/road fields and requires channel-bed representation and active boundary conditions. The crossing-specific steps below apply to culvert projects.

## The normal path

For an independently revised model, **Comparison with previous calculation** shows river-specific metrics, every matching section's native WSE change, the largest absolute change and diagnostic counts for both editions. It verifies raw HDF/controller identity before comparing. Added or removed sections and unmatched profiles remain visible. Different discharges, model types, units or datums stop the comparison. A changed endpoint ID suppresses its endpoint delta. Matching RS labels still require checking any changed physical locations. The 0.1 ft flag is a workflow screening threshold. Native-message coverage and combined numerical/native records are listed separately.

1. Finish **Model → Review all parameters → Confirm and run HEC-RAS**. Read the completed calculation and unresolved hydraulic checks on **Results**.
2. Open the generated English/Chinese reports and Minimal/Complete folders. **Open QGIS review copy** launches the configured QGIS with its own environment and a disposable copy of Complete. This avoids broken system shortcuts and preserves the sealed package. Review-copy edits do not update the package automatically.
3. If the automatic adapter has all needed outputs, no supplementary upload is required. If it lacks a group table or complete warning list, use the optional step below. No reviewer identity, reason form or screenshot upload is required.
4. If assumptions or geometry need changing, create a separate editable revision. Confirm its inputs before a new solve. Old calculations remain available in the project list.

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

**Locate wet edges and separated water areas** shows actual computed water levels over the original cross-section arrays. Red end points indicate a section end below water. Separated wetted intervals do not prove longitudinally connected flow paths. In an editable revision, **Suggest wet-edge extension from prior run** tests a bounded set of wider DEM sections. Inspect the proposed changes using the normal DEM preview and intersection checks before applying. It does not modify the structure approach sections, replace the surveyed channel, raise terrain or force a solution. If the available DEM/domain cannot find high ground, review the model extent and bypass paths yourself. A dry-end proposal is not proof of hydraulic convergence; recompute after confirming changes.

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

1. Choose **Intervals beside spacing-related warnings** or **Entire continuous reach**. The warning option locates energy, conveyance, velocity-head and related findings in verified outputs.
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
