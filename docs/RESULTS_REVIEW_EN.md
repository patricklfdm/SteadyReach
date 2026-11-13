# Results, revisions and optional sensitivity

**English** | [简体中文](RESULTS_REVIEW_CN.md) | [User guide](USER_GUIDE_EN.md)

## The normal path

1. Finish **Model → Review all parameters → Confirm and run HEC-RAS**. Read the completed calculation and unresolved hydraulic checks on **Results**.
2. Open the generated English/Chinese reports and Minimal/Complete folders. **Open QGIS review copy** launches the configured QGIS with its own environment and a disposable copy of Complete. This avoids broken system shortcuts and preserves the sealed package. Review-copy edits do not update the package automatically.
3. If the automatic adapter has all needed outputs, no supplementary upload is required. If it lacks a group table or complete warning list, use the optional step below. No reviewer identity, reason form or screenshot upload is required.
4. If assumptions or geometry need changing, create a separate editable revision. Confirm its inputs before a new solve. Old calculations remain available in the project list.

## Complete missing native outputs

The automatic adapter reads verified HDF, controller and available log outputs. Some HEC-RAS 7.0.1 results are only available in native tables; this release does **not** automatically drive the HEC-RAS GUI to export them.

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

Expand **Optional sensitivity batch**, choose channel/overbank Manning n, an applicable normal-depth slope, or a group's uniform bottom fill, and enter explicit low/high values. Select **Prepare and review batch**. Inspect each displayed change, then **Confirm displayed cases and calculate**. Editing the range clears the old proposal; the backend rejects stale confirmation.

The app runs the baseline and changed cases sequentially with the real solver, generates each case's reports, and compares headwater and matched-section water levels. Identical-to-baseline bounds do not create duplicate variants. The baseline GIS package is retained instead of exporting the same maps repeatedly. Ranges are explicit assumptions, not measured confidence intervals. Roughness batches are rejected when section-level Manning segments would override the selected global value. An upstream normal-depth test is rejected for a subcritical plan, which does not use that boundary. Bottom-fill depth applies along the full barrel; an inlet photograph alone does not establish that condition. Failed cases and incomplete native output remain visible; no sensitivity ranking grants engineering acceptance.

## Remaining human decisions

Check source applicability, datum, physical opening identity, buried geometry, effective flow paths, uncertain banks, inlet/floor/obstruction assumptions and boundary validity. Review Mapper/QGIS alignment and final report pages. User-authored source notes are retained in their original language; if Chinese construction notes occur in an English report, the report flags language review. Supply suitable English wording before an English-only external delivery. No local translator is assumed to preserve engineering meaning.

## Automatic DEM / QA proposals

[Automatic layout and QA repair](DEM_AUTOMATION_EN.md) adds anchor searches, adaptive positions/widths and wet-end extensions preserving original samples. **Prepare QA revision suggestions** on Results proposes changes in an independent revision; adoption still requires full parameter confirmation before a solve. Direction, flow connectivity, structures, boundaries and unresolved warnings remain engineering decisions, not convergence or design acceptance.
