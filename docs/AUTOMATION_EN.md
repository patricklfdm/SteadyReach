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

### Focused bank review after refinement

The **Bank-profile gallery / batch selection** evaluates the current sections, including sections added by spacing trials. Its default filter shows interpretation flags. Choose **Inferred from neighbors**, **Ambiguous terrain**, **Missing / invalid banks**, or **All sections** to focus the review. Counts update immediately; selected changes remain visible even when they do not match the filter. Profiles are drawn when expanded to keep large galleries responsive.

New spacing sections record their neighboring-section bank fractions as low-confidence assumptions. Older spacing sections with the same derivation are also flagged when their original candidate metadata is absent. A saved number alone is not evidence of an independently identified bank. Current explicit profile selections are identified as user selections, without implying engineering acceptance; changed profiles invalidate that selection context. Check the reason beside each profile, then save any intended corrections together.

Continuing a computed refinement refreshes the reach summary against current station identities and preserves saved bank positions. It does not reuse old section-array indices or rerank retained controls. The final parameter review also includes unresolved bank interpretations. Imagery, survey interpretation and effective floodplain connectivity still require judgment; this feature does not independently validate banks against aerial imagery.

### Propose bank replacements in one batch

In **Bank-profile gallery / batch selection**, expand **Suggest bank replacements together**. This is useful after section refinement, when many new banks were inherited from adjacent sections.

1. Keep **Inherited / missing banks** to retain the other saved banks as fixed controls. The optional **All banks with interpretation flags** scope also evaluates saved conditional bank choices. Structure approach controls, explicit roughness subdivisions and spatial conflicts are excluded.
2. Click **Prepare bank replacement preview**. The workflow compares current-profile slope breaks at three smoothing scales and ranks candidate pairs along the reach using the existing continuity checks. It shows saved/proposed left and right stations, movement, confidence, reasons and expandable profile overlays. Blue dashed lines are saved banks; orange lines are candidates. Preparing a new preview clears its previous unadopted selections. Existing unrelated pending edits are saved first.
3. Click **Select stable candidates** to select changed candidates that meet the implemented scale/continuity checks. This is a grouped selection, not automatic acceptance. No candidates are selected merely by opening the preview. Check the overlays; select or clear individual candidates as needed. Ambiguous and unavailable pairs are not part of the stable selection.
4. Choose **Adopt selected bank candidates**, or use the normal **Save all changes / Review all parameters** action. Only selected pairs change. Changed geometry, other edits or a stale preview require a new proposal. Saved choices retain their full method, previous values and selection evidence; low-confidence interpretations remain flagged after adoption.
5. Open **Review all parameters**, inspect the changes and confirm before running HEC-RAS. Equivalent dependent values rebind automatically. A materially changed derivation still needs a choice. No reviewer name or written justification is required.

The preview survives reopening and language changes. Adoption reports success and the gallery shows the saved positions. The Complete package retains the proposal and selected-section record through its source-evidence index. The replacement logic uses terrain morphology and fixed controls; it does not independently interpret aerial imagery, identify bankfull discharge, validate submerged geometry or certify effective flow areas. A bank change can materially change computed water levels, so review the resulting native warnings and comparison.

### Detailed steps

1. **Acquire/import the site material.** The existing USGS DEM/catalog lookup and document extraction run first. Inspect the source count, survey CRS, elevation units/datum and failed attempts. Import a site folder if anonymous public downloading is unavailable. Automated acquisition is limited to supported providers and document formats.
2. **Propose and check exterior flow paths.** Use [automatic DEM layout](DEM_AUTOMATION_EN.md) for anchors, positions/widths and bank candidates without first picking every point. Saved source associations take priority; coordinate-only alternatives can disagree on direction, so check the actual flow and road gap before adoption. Existing sections use QA suggestions; manually pick only when needed.
3. **Associate openings together.** Open **Opening groups and survey-point associations**, then **Suggest all opening pairs**. With one usable survey and separable mouth clusters, recognized `LC` and `CROWN` codes suggest a rectangular opening and circular pipe pairs, ordered looking downstream. Point numbers are not hardcoded. Check inlet/outlet IDs, group and barrel numbers against the sketch/map. Ambiguous clusters remain unresolved. Other codes can be associated by entering IDs.
4. **Choose what the elevations mean.** `Location only` produces no invert. `Identified interior invert points` uses the identified point elevations after unit conversion. `Assume interior crown / low chord` subtracts the entered clear height from the mean identified elevation and labels the result **assumed**. Exterior crown elevation, nominal outside diameter, sediment and a nonuniform soffit can invalidate that assumption. No vertical datum shift is performed. Multiple IDs at one mouth are averaged; do not combine different barrels or unrelated surfaces.
5. **Save associations.** This generates candidates without overwriting adopted dimensions or inverts. Additional groups are created only when the displayed creation option is checked; unknown dimensions stay blank. Associate every member of a multi-barrel group. Different member lengths/inverts do not get silently averaged; split unequal openings into separate groups or provide an explicit compatible representation.
6. **Generate sections and resolve early geometry issues before bank review.** The panel checks cutline intersections, missing elevations, projected opening overlap/out-of-section centers, adverse invert slopes and populated approach-length constraints. Tentative pairing warnings appear even before centers are adopted; confirmed conflicts block the relevant center adoption and final solve. Click **Inspect section**, request bounded rotations and preview actual DEM resampling. Inspect the direction/coverage before applying. Rotation suggestions do not establish hydraulic correctness.
7. **Review candidates and profiles together.** Use **Review parameter candidates together**. Existing values default to **Keep saved value**. **Select unique missing candidates** only prepares selections; inspect their formulas/conditions before **Save all selected changes**. Conflicting alternatives stay unresolved. You may edit any value directly. The **Bank-profile gallery / batch selection** shows saved selections and uncertainty; expand relevant profiles and save selected changes in one batch. It never replaces all saved banks with the algorithm's defaults.
8. **Confirm the complete model once.** Open **Review all parameters**. Missing/invalid inputs still wait for correction. Review assumptions, floor/entrance/blockage, boundaries, flow paths and all values. Only **Confirm and run HEC-RAS** launches computation. Saved source/geometry changes invalidate earlier confirmations; equivalent derivations refresh at final review, while changed values or supporting evidence require a new selection or edit.

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

## Geometry edits and repeated candidate selection

After saving geometry changes, open **Review all parameters**. The workflow recomputes adopted derivations and automatically refreshes their geometry binding when the value, range, evidence class, source and substantive explanation all match. The review page reports the number refreshed, and the project event record retains both candidate records. Changes to a value, range or source still require selection or editing. The final calculation confirmation binds the resulting current inputs.

Bank proposals locate the channel from its saved map anchor projected onto the cutline. This keeps an asymmetric floodplain extension from moving the search origin to the section midpoint. Profiles without usable map registration retain midpoint-based screening. Review uncertain shoulders, gradual valley walls and possible secondary channels in the gallery.

After a boundary sensitivity batch, create a QA revision from that baseline. Extent screening automatically includes authenticated boundary cases with matching geometry, discharge, roughness and flow regime. The preview reports the included study count. This supplies the wet-end water-level envelope without preparing a separate text file. Study evidence changes stop this route for review. Explicit reference controls remain available for independently sourced levels.

## Pagosa automation assessment — 17 November 2026

The guided trial used 32 sections and four saved project editions. Its 91 recorded backend events include automatic events, so they cannot be interpreted as 91 manual clicks or used to calculate an automation percentage.

| Work | Current assistance | Remaining work and automation opportunity |
|---|---|---|
| Acquire and interpret sources | Bounded USGS DEM acquisition, coordinate-based effective FEMA FIS discovery, supported flow/roughness table parsing, grouped source selection and hashes | Engineers confirm river/location applicability and resolve conflicting dates or units. Unsupported layouts, partial extraction and unavailable downloads remain visible. |
| Reach and section layout | Terrain route search, section sampling, intersection checks and joint direction/coverage proposals | The reach limits and effective flow paths need confirmation. Warning-driven two-level section-spacing trials are available for continuous rivers. Excluded intervals and unresolved hydraulic response remain visible. |
| Banks | Anchor-aware multiscale candidates, joint reach-wide ranking, fixed manual controls, labelled continuity interpolation and batch editing | Gradual valley walls, terraces, divided channels and weight-sensitive candidates require interpretation. Independently checked imagery support remains development work. |
| Derived parameters | Automatic-owned values update, and semantically identical selected candidates now rebind during final review | Materially changed assumptions or derivations remain displayed for a consolidated decision. Manual corrections retain ownership. |
| Results | Native input/output identity checks, full warning export, wet-edge location, baseline-bound sensitivity comparison and bilingual reports | Energy convergence, critical-depth fallback, boundary applicability, floodplain connectivity and submerged-bed representation still require engineering assessment. |
| Model corrections | Isolated joint-direction/coverage previews, nested spacing trials, bounded multi-round wet-end repair using freshly computed levels, and editable continuation from completed cases | Each batch needs one explicit confirmation. Coupled direction/spacing/control choices and unresolved physical interpretations still need assessment; the program stops at its confirmed limits. |
| Delivery | Mapper/GIS generation, bilingual reports and one-action Complete/Minimal refresh | Desktop readability, geographic interpretation and engineering acceptance retain human review. |

The first isolated regression replayed existing Pagosa data and actual solver outputs. It produced seven downstream extension proposals from the earlier boundary study, preserved interior samples and bank plan positions, and found zero wet-end sections in the final extended edition. An equivalent mid-reach geometry edit refreshed both unchanged boundary candidates in one draft transaction.

That first bank comparison generated 30 of 32 pairs, up from 19. Median distance from the earlier user-selected banks was 3.28 ft and the maximum was 58.91 ft. Those earlier selections are conditional interpretations. Surveyed bank accuracy requires independent observations. That regression retained site hashes and used existing outputs. The subsequent real-run test is described below.

## Reach-wide banks and calculation feedback

Automatic preparation ranks finite left/right bank pairs jointly along each reach. It combines local slope-break scores, support across smoothing scales and a soft continuity penalty based on distance between sections. Existing manually entered banks act as fixed controls. Changes to geometry, CRS, reach boundaries or those controls invalidate the saved proposal context.

The selector tests continuity weights of 0.5, 1 and 2. Sensitive choices are flagged. One missing interior pair may use labelled low-confidence interpolation from two supported neighboring pairs, subject to spacing and local relief checks. Structure faces and reach boundaries interrupt this interpolation. The existing conditional end-section extrapolation remains available. The final parameter review retains all assumptions and editable values.

A fresh isolated Pagosa Q100 test automatically filled all 32 bank pairs and completed HEC-RAS, native warning export, bilingual reports and mapped Complete/Minimal packages. One interior pair used interpolation and three pairs were sensitive to the tested continuity weights. Relative to the earlier conditional manually selected banks, the maximum computed WSE change was 0.841796875 ft at RS 2200. Native messages increased from 21 to 28 and three sections had wet endpoints. The feedback stage proposed bounded DEM extensions at all three affected sections. These findings keep the bank interpretation and hydraulic QA open. Full model improvement requires the follow-up computation and engineering assessment described in the results guide.

The follow-up isolated revision adopted those three exterior DEM extensions within a 2000 ft search bound, preserved interior samples and bank plan positions, refreshed equivalent derivations and ran a fresh Q100 case through the normal confirmation entry point. Wet-end sections decreased from 3 to 0 and native messages from 28 to 25. The maximum WSE difference from the automatic-bank edition was 0.00390625 ft. Both mapped packages and all three reports were regenerated. Critical-depth fallback, energy-solution warnings, floodplain interpretation and submerged-bed adequacy remain open. The automated tests exercise the software sequence with conditional assumptions. User calculation confirmation and engineering assessment remain part of normal operation.

## Joint section direction and coverage regression

A replay of the earlier Pagosa geometry resolved the three extension conflicts that previously needed manual direction edits. The program jointly selected neighboring directions and widths, resampled rotated profiles from the real DEM and generated bank candidates for one confirmation. Search limits remain explicit, including a notice when a feasible combination was found before the search budget was exhausted. The bilingual browser test verified the preview, adoption feedback and automatic rebinding of two unchanged boundary inputs.

During development, four fresh isolated HEC-RAS Q100 calculations exercised reference-level coverage followed by actual-WSE feedback. Wet sections decreased from 29 to 6, 1 and 0. Native messages decreased from 57 to 27, 23 and 22. The final extension retained all 32 computed water levels exactly at native output precision. The final Complete and Minimal packages contain 127 and 20 payload files respectively. The English and Chinese reports each have 17 pages, and the English summary has two. All 36 final report pages were rendered and inspected. Original user-project hashes were preserved.

These regression copies use the existing conditional flow, roughness, normal-depth boundaries and surface-DEM bed assumption. The test operator accepted the displayed proposals for software validation. Hydraulic QA retains the RS 600 critical-depth and energy findings, boundary interpretation, floodplain connectivity and submerged-bed uncertainty. Desktop reopening of these newly generated packages and cross-machine validation remain pending. Section-spacing trials and supervised bounded wet-end repair batches are available through the results guide.

An observed transient imagery HTTP 502 was recovered by regenerating the delivery from the saved calculation. Imagery requests now retry HTTP 429, 500, 502, 503 and 504 up to three times with short waits, retain failed-attempt records and report persistent failure. Access and data-validation errors are reported immediately.

If a service-generated temporary image URL fails, the downloader can request the same locked mosaic through the documented [direct image stream](https://developers.arcgis.com/rest/services-reference/enterprise/export-image/). The metadata extent and CRS must pass first; image size, alpha coverage, budget and source records are still checked. The fallback is limited to output-link HTTP 400/404/410 and the transient codes above. It does not bypass authorization failures or data-validation errors. A failed export retains the calculation and current reports, with a direct **Retry delivery without solving** button.


## Nested spacing regression

The Results page now prepares two nested, warning-located DEM refinements for continuous river models. It includes a plan view, bank/profile review, bounded new-section coverage screening, persistent preview confirmation, per-case progress and authenticated retained-section comparisons. Native flow/boundaries/roughness and retained section data are checked, with conservation of all three reach-length totals. The report refresh incorporates completed trials. [Operating steps](RESULTS_REVIEW_EN.md).

Two isolated Pagosa batches each ran 32, 49 and 83 sections through HEC-RAS. The second batch added baseline-WSE coverage screening before confirmation. Its maximum successive WSE changes were 0.54541015625 ft and 0.22998046875 ft, so the 0.10 ft internal check remains open. Wet-end sections in its two refinements were 3 and 12, compared with 9 and 25 in the earlier unscreened batch. The retained baseline had zero wet-end sections. Native messages in the final three cases were 22, 23 and 34. RS 2100–2000 was explicitly excluded because the nested cutlines could not fit with fixed existing sections. These are conditional numerical experiments with unresolved hydraulic findings.

## Revision interpretation and export recovery regression

A further isolated test continued from the computed 83-section case. It preserved all section centers and bank map positions, extended 12 profiles, and explicitly adopted a changed conditional downstream slope. One fresh HEC-RAS Q100 run completed. The largest parent/current WSE difference was 2.2666015625 ft at RS 100. The reports and results page now identify the simultaneous geometry and boundary changes; this comparison does not close the spacing test. Native messages changed from 34 to 33, while wet-end sections changed from 12 to 16, so this revision is not evidence of overall hydraulic improvement.

The same test encountered failed imagery output links. Direct image streaming recovered the locked official mosaic, and an export-only retry produced both mapped packages without changing the native calculation. Current report downloads remained available during export failure. The English/Chinese browser comparison and recovery flow, 70 final report pages, two exhibit pages, package hashes and relative references were checked. Native desktop reopening of these new packages and cross-machine validation remain separate pending checks. Hydraulic QA remains open.

After computing, the sensitivity panel can collect adopted ranges and matching document candidates from the sealed inputs. Review up to four parameters together and confirm one batch, with no reviewer-name form. Unadopted document ranges remain unselected; sources and edited assumptions stay traceable. See [results review](RESULTS_REVIEW_EN.md).

## Sensitivity range regression

An independent 83-section Pagosa Q100 trial gathered two previously adopted exterior-DEM slope ranges and two unselected San Juan River roughness ranges from the sealed FEMA source review. The regression operator explicitly accepted their conditional applicability, then confirmed four parameters together. Nine fresh HEC-RAS runs completed, and the repeated baseline reproduced the original water levels at native precision. Section arrays and flow remained unchanged; every variant changed only its stated parameter.

The tested maximum matched-section WSE differences were 0.283203125 ft for channel n, 0.14404296875 ft for overbank n, 0 ft for the selected upstream slope range, and 1.59375 ft for the downstream slope range. These figures describe this conditional geometry and the displayed ranges only. They do not calibrate the site or establish confidence intervals. Native warnings and wet section ends remain open; fewer warnings in an alternative boundary case do not justify adopting that boundary. The original user project was preserved. Source hashes, edited-range records and actual comparisons are retained for report/package export.

## Automatic next-step guidance

On Results, **Suggested next steps from this calculation** automatically checks the native result identity, warning evidence and completed studies belonging to that exact baseline. It groups the work into native evidence, flow/output consistency, boundary response, wet-end repair, flow-path interpretation, section spacing, physical inputs and delivery. Unknown messages remain explicitly listed. The order is a work sequence, not a risk score or engineering acceptance.

Expand an item and choose **Open relevant review tool**. The matching panel opens and receives focus; no input changes and no calculation starts. Preview and final-confirmation controls in that tool still apply. The guidance reports temporary failures with a retry button and ignores responses from a project you have already left.

A completed repair batch is a separate calculation: baseline warnings remain visible, and the guide points to the existing batch before suggesting repetition. A small boundary response does not validate the boundary. A spacing test for a parent model does not establish convergence of the current changed geometry. Source or study evidence changes remain errors; incomplete studies cannot suppress required work. The guide does not prescribe ineffective-flow areas, relocate banks, select boundary slopes or close warnings automatically.

The Pagosa regression used the existing isolated 83-section Q100 calculation and its nine-case sensitivity batch. All 52 current diagnostic records were assigned to review groups, the four boundary variants were authenticated, and the maximum tested boundary response was 1.59375 ft. The guide correctly retained spacing as untested for this exact baseline and avoided repeating a complete native-warning export. This test reused verified real outputs and did not invoke HEC-RAS or change either the original or isolated project.

Computed-result review now [locates warnings with native profiles and adjacent-section comparisons](RESULTS_REVIEW_EN.md#review-computed-sections-without-hunting-through-native-windows). The workflow prepares the evidence in the page; physical flow connectivity and acceptance remain engineering decisions.

Automatic spacing recommendations now combine verified native warnings and actual hydraulic changes, retain per-interval exclusions and deferred candidates, and stop with an explanatory preview when the DEM/layout cannot support further nested refinement. Report-only batch failures can be retried without another solve. See [spacing selection and recovery](RESULTS_REVIEW_EN.md#automatic-spacing-selection-and-recovery).

### Resume an incomplete batch without repeating completed calculations

Restart the app after updating. **Retry incomplete spacing batch** authenticates each saved case against the confirmed configuration, source inputs, sealed extraction, native input files and native outputs. A completed case is reused even if the software code changed since its original calculation. Its original run ID is retained; this is reuse, not a fresh validation of the current solver adapter. Intact registered reports are reused. Missing or unusable reports receive a new edition without calling HEC-RAS. Prior case records and report editions remain available. An interrupted report recovery can reuse the edition that was already registered.

Changed calculation evidence stops that case and remains blocked on a repeated retry; it does not silently trigger a replacement solve. Restore the original evidence or prepare a new reviewed study. A genuinely unfinished calculation follows the normal solver path. Software QA, report visual review and engineering acceptance remain separate.

The spacing result now distinguishes wet sections retained from the baseline from wet sections introduced by refinement, retaining each affected profile while counting a section only once. A wet-ended spacing series is provisional even if the numerical differences satisfy the threshold. Use **Prepare editable QA revision from selected case**, review the automatically prepared coverage proposals, confirm the revised model and compute it, then assess spacing again from that baseline. The saved nested series is not modified. Automatic coverage repair and two-level spacing remain separate confirmed operations; the workflow does not yet automatically iterate both together.
