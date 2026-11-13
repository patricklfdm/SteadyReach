# Automatic DEM layout and QA-guided section changes

**English** | [简体中文](DEM_AUTOMATION_CN.md) | [No-model guide](NO_MODEL_GUIDE_EN.md)

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
| Intersecting eligible DEM sections | Propose bounded rotations and resample the real DEM, retaining centers and widths | Direction approximately normal to flow, physical route and floodplain coverage |
| Previous calculated WSE above a section end | Attempt to extend the straight cutline outward to consecutive DEM points above that previous WSE, subject to width, NoData and intersection limits | Whether the added terrain belongs to the same floodplain and represents the intended conveyance |
| Structure-adjacent section, non-DEM source, explicit flow subdivisions, changed geometry or unavailable terrain | Withhold unsupported changes and show the reason | Appropriate geometry/data or a manual adjustment |
| Hydraulic jump, uncertain boundary, missing native table, questionable structure or unresolved convergence | Preserve the finding; no automatic numerical cure | Physical model choice, supporting evidence and subsequent sensitivity/QA |

For a wet-end extension, **every original station/elevation sample is preserved**. Station labels may shift to accommodate the added left end, while existing bank map locations stay fixed. The adapter limits the total to 500 points by reducing only new exterior sampling when needed; near-limit originals may require manual review. It does not raise endpoints or narrow a section to remove a warning. New width defaults to a maximum of 1,200 ft; change it only when the actual downloaded terrain covers the relevant area.

In the QA preview, brown is proposed ground, grey dashed is original ground and red dashed (where available) is the **previous** computed WSE. It is a screening reference, not the result of the revised model. Choose which proposed section changes to adopt; the selected combination is checked again. The original calculation and unresolved findings remain available. Confirm the full inputs and compute the revision, then inspect its new results. A disappearing wet-end finding does not demonstrate complete hydraulic QA or design adequacy.

## Scope and practical limits

- This is local, deterministic candidate generation; no AI service is required.
- It uses a projected local raster with known vertical unit/datum and an intact source hash. The current in-memory search accepts at most 16 million cells. Missing coverage or ambiguous terrain is reported; it is not filled with synthetic elevations.
- Search length is bounded to 100–1,000 ft per exterior side and maximum width to 120–2,000 ft. These implementation bounds are not HEC-RAS engineering criteria. Very long, broad, braided or divided reaches need an appropriate domain and explicit engineering layout.
- Surface DEM does not determine buried culvert length, invert, entrance shape, sediment, design discharge or calibrated roughness. Those remain source-based values or explicit assumptions.
- The program does not automatically move structure faces, invent bypass paths, select a new regime/boundary, or claim mesh/section-spacing convergence. Initial adaptive placement is a layout heuristic, not convergence testing.

HEC guidance calls for representative geometry and sections approximately normal to flow, covering the relevant floodplain; culverts also need appropriate functional exterior sections. See [cross-section geometry](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/7.0/basic-data-requirements/geometric-data/cross-section-geometry) and [culvert section locations](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/7.0/modeling-culverts/general-culvert-modeling-guidelines/cross-section-locations-for-culverts). The automatic search thresholds are implementation heuristics, not thresholds prescribed by those references.
