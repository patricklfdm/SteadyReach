# Automatic DEM layout and QA-guided section changes

**English** | [简体中文](DEM_AUTOMATION_CN.md) | [No-model guide](NO_MODEL_GUIDE_EN.md)

**Automatic-draft route.** The model page can stage an eligible initial layout or bounded QA correction together with dependent input estimates. Exterior end sections with unresolved bank morphology are tested at wider coverage while preserving intersection and NoData checks. Other uncertainty remains visible. Profile grids and numeric bank stations support the final inspection. [One-confirmation procedure](AUTOMATION_EN.md).

Use **Automatic DEM layout / QA repair** on the Model page. The program prepares a map and profiles for one consolidated decision. It does not run HEC-RAS while proposing or adopting geometry. No reviewer name, signature or reason field is required.

## Starting without sections

1. Prepare the project normally. Wait for the local USGS DEM and check its elevation unit/datum. Import available survey/drawing material. If opening-point associations already exist, save them first.
2. Open **Automatic DEM layout / QA repair → Propose anchors and sections**. Optional search bounds default to 400 ft of exterior reach on each side and a maximum section width of 800 ft. These are editable search controls, not surveyed dimensions, hydraulic boundary distances or inundation limits.
3. Review the candidate map. Saved, source-linked mouth locations have priority; explicit map locations or exterior anchors come next. With only a site coordinate, the program searches opposing low terrain sectors and can display up to three alternatives. The direction inferred from surface elevation can be reversed by a road, pond, obstruction or local terrain. Verify it against the actual crossing and available observations.
4. Check the exterior anchors, road gap, section placement and coverage. Initial section positions follow terrain routes; strong bends and bed-slope changes can receive additional sections. Widths expand using a terrain-relief screen. That screen is **not a calculated water level** and cannot establish Q100 floodplain coverage. “No intersections” is only a geometric check.
5. Expand **Inspect section profiles / edit bank candidates**. Review uncertain profiles. Change the left/right station values if needed; edits snap to displayed DEM samples. Existing bank locations are retained for QA extensions. An unresolved bank pair remains blank rather than receiving invented values. The manual map and bank tools remain available for ambiguous routes and profiles.
6. Check the consolidated confirmation and choose **Adopt and review calculation inputs**. For an initial layout, old face identifiers and dependent opening/road station positions and approach distances are invalidated. Source dimensions and inverts are retained. Review freshly derived positions and other missing values in **Prepare together, confirm once**.
7. Only after the complete input list passes its checks and you click **Confirm and run HEC-RAS** does a real calculation begin. Adoption of the map is not permission to run. Missing parameters stay in the editable project.

To change a proposal's search bounds, enter new values and generate a new proposal. Changes to the draft, sources, units, associations or DEM invalidate an earlier proposal. A still-current preview is restored when reopening the page. A failed search leaves saved geometry unchanged.

## After a calculation

On Results choose **Prepare QA revision suggestions**. The original completed project remains intact; a separate editable revision is created. The app searches the current QA findings and actual DEM for bounded changes:

| Finding | Program action | What remains a user decision |
|---|---|---|
| Intersecting eligible DEM sections or intersecting extension proposals | Jointly compare neighboring directions and coverage, retain centers, resample rotated sections and extend eligible ends | Direction approximately normal to flow, physical route and floodplain coverage |
| Previous calculated WSE above a section end | Attempt to extend the straight cutline outward to consecutive DEM points above that previous WSE, subject to width, NoData and intersection limits | Whether the added terrain belongs to the same floodplain and represents the intended conveyance |
| Structure-adjacent section, non-DEM source, explicit flow subdivisions, changed geometry or unavailable terrain | Withhold unsupported changes and show the reason | Appropriate geometry/data or a manual adjustment |
| Hydraulic jump, uncertain boundary, missing native table, questionable structure or unresolved convergence | Preserve the finding; no automatic numerical cure | Physical model choice, supporting evidence and subsequent sensitivity/QA |

For a wet-end extension, **every original station/elevation sample is preserved**. Station labels may shift to accommodate the added left end, while existing bank map locations stay fixed. The adapter limits the total to 500 points by reducing only new exterior sampling when needed; near-limit originals may require manual review. It does not raise endpoints or narrow a section to remove a warning. New width defaults to a maximum of 1,200 ft; change it only when the actual downloaded terrain covers the relevant area.

In the QA preview, brown is proposed ground, grey dashed is original ground and red dashed (where available) is the **previous** computed WSE. It is a screening reference, not the result of the revised model. Choose which proposed section changes to adopt; the selected combination is checked again. The original calculation and unresolved findings remain available. Confirm the full inputs and compute the revision, then inspect its new results. A disappearing wet-end finding does not demonstrate complete hydraulic QA or design adequacy.

## Joint direction and coverage review

QA suggestions now search neighboring sections together. The candidates use the saved direction and rotations of ±1, ±2, ±3, ±5, ±7.5, ±10, ±15, ±20, ±25 and ±30 degrees. Each rotated section is resampled from the verified DEM. Where a saved flowline is available, the proposed cut must cross it once and remain within its neighboring section-order interval. The original center stays fixed.

The bounded search prioritizes coverage, then smaller rotations and added width. It first searches candidates with the best available coverage at each section, then considers the complete candidate set. A connected group is limited to 100,000 search nodes. When that limit is reached, the page labels the retained feasible combination for review. A group with no feasible combination keeps its saved geometry and reports the conflict.

Expand **Direction and extent search details** to see each rotation, left/right extension and sample treatment. Straight extensions preserve original samples and bank plan positions. Rotated sections receive new samples and bank candidates. Confirm those banks in the same preview. Single-sided extensions can use the available total width budget. Both-sided extensions must fit within the combined budget.

Review the proposed directions and floodplain connections together. Deselecting one linked change can create an intersection, which the adoption check reports. After adoption, the complete parameter review refreshes equivalent derived inputs and lists assumptions. Recompute to check the new water levels and warnings. Repeat from an independent revision when actual water levels require more coverage.

## Scope and practical limits

- This is local, deterministic candidate generation; no AI service is required.
- It uses a projected local raster with known vertical unit/datum and an intact source hash. The current in-memory search accepts at most 16 million cells. Missing coverage or ambiguous terrain is reported; it is not filled with synthetic elevations.
- Search length is bounded to 100–1,000 ft per exterior side and maximum width to 120–2,000 ft. These implementation bounds are not HEC-RAS engineering criteria. Very long, broad, braided or divided reaches need an appropriate domain and explicit engineering layout.
- Surface DEM does not determine buried culvert length, invert, entrance shape, sediment, design discharge or calibrated roughness. Those remain source-based values or explicit assumptions.
- QA repair protects structure-face locations and retains hydraulic warnings for review. The automatic-draft route can fill a missing regime or supported boundary-slope assumption for final confirmation. Bypass representation and section-spacing convergence require their own engineering assessment.

HEC guidance calls for representative geometry and sections approximately normal to flow, covering the relevant floodplain; culverts also need appropriate functional exterior sections. See [cross-section geometry](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/7.0/basic-data-requirements/geometric-data/cross-section-geometry) and [culvert section locations](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/7.0/modeling-culverts/general-culvert-modeling-guidelines/cross-section-locations-for-culverts). The automatic search thresholds are implementation heuristics, not thresholds prescribed by those references.


## Nested spacing checks

For completed continuous river models, the Results page can prepare two DEM refinement levels with baseline-WSE extent screening, preserved existing controls, one batch confirmation and real solver comparison. Review excluded intervals, fresh wet ends and native warnings. New-section coverage searches use a 2000 ft width bound, increased to the existing maximum section width when needed. [Step-by-step spacing guide](RESULTS_REVIEW_EN.md).
