# River reaches without structures

**English** | [简体中文](RIVER_REACH_CN.md) | [Home](../README.md)

Use **River reach (bridges excluded)** on the home page for one continuous river/reach in 1D steady flow. This builds cross sections, flow data and boundaries without a dummy culvert or roadway. The original culvert option remains available. Importing an existing native river-only model is not part of this new builder route.

## Before starting

Prepare a location, design discharge with its source, the intended upstream and downstream limits, and terrain metadata. Identify whether the submerged channel comes from survey or only a surface DEM. A bridge location identifies a model limit; it does not supply the hydraulic boundary value.

For a reach between two excluded bridges, place the upstream limit downstream of the upper bridge and the downstream limit upstream of the lower bridge. Bridge backwater or contraction may still influence these sections. If those effects cannot be represented by justified boundary data, reconsider the limits or obtain the structure/model data.

## Project → Model

1. Start `start_workflow.cmd`, choose **River reach (bridges excluded)**, and enter the project title and coordinates. Supply flow in **cfs** if known. The location marker is only a search location, not an automatically accepted centerline.
2. Prepare the project. Review the USGS DEM source, age, horizontal CRS, vertical datum and vertical units. Import the available survey, hydrology and reference documents through the same source panel used for other projects.
3. On the DEM map select river anchors **in upstream-to-downstream order**. At least two are required; add points through bends and keep both ends inside the intended bridge limits. Save the anchors.
4. Click **Prepare an automatic draft**. The program searches a terrain corridor through those anchors, proposes a continuous flowline, adaptive cross sections and banks, and tests section intersections/coverage. Review the preview before adopting it. The section identifiers are sequential RS labels, not surveyed chainage.
5. Resolve highlighted geometry issues. Use the existing map pan/zoom, section rotation/resampling, profile grids and numeric bank editing. Check direction and flow connectivity yourself; the lowest DEM corridor can follow a wrong branch or a flattened water surface.
6. Review the collapsed parameter groups. River mode removes barrel, invert, roadway and inlet fields. Save the channel/overbank roughness, bed representation and active boundary parameters. Suggested values remain labelled assumptions until reviewed; a reference FEMA water level is not a bed elevation.

You can also open **Enter or paste reach coordinates** to enter 2–100 easting/northing pairs, one pair per line in upstream-to-downstream order. Use the DEM CRS and horizontal units shown on the map. **Save coordinates and show on map** checks the format and coverage and displays the saved line for review.

## DEM coverage

If either end of the reach is outside the downloaded map, open **Reach extent and DEM → Expand DEM coverage**, enter the coverage radius in metres, and click **Expand from downloaded DEM**. This radius describes acquisition around the project coordinate. Select the hydraulic endpoints separately. The action verifies the cached original USGS files and full cell coverage, retains saved inputs and all existing DEM cells, and refreshes the map after completion. Use **Fit DEM** to see the expanded extent. A coverage failure retains the current map and inputs. Reduce the radius or obtain adjoining tiles if the cached originals are insufficient.

## Screening section coverage with an existing water-level reference

After creating a draft, expand **Automatic DEM layout / QA repair → Check extent against reference water levels**. Select an imported source, enter its matching vertical datum, and paste current section IDs and associated water elevations in feet, one pair per line. Check **Use reference water levels for this preview** and request QA suggestions. The search width cap is under **Optional search bounds**.

The program interpolates between controls using section-center distances and holds the nearest control beyond either end. Review the association of reference and current sections, especially where their positions or survey dates differ. Proposed extensions retain existing DEM samples and saved bank positions. The preview records the source hash and reference controls. Conflicting extensions remain listed for further work. Review the map, profiles and remaining issues before adoption. Reference screening does not set hydraulic boundary conditions. Calculation and boundary sensitivity follow the full input confirmation.

## Boundary inputs

| Choice | Required entry | Meaning |
|---|---|---|
| Subcritical | Downstream boundary | Upstream hydraulic boundary is not used. |
| Mixed | Upstream normal-depth slope and downstream boundary | Both ends are required. |
| Downstream normal depth | Positive slope in ft/ft | A representative boundary energy slope; test its suitability. |
| Downstream known WSE | One absolute elevation in ft for each flow profile, in the displayed order | Same vertical datum as the model. Enter water-surface elevation, not depth or raw gauge height. |

The current river builder supports subcritical and mixed regimes, upstream normal depth, and downstream normal depth or known WSE. Other HEC-RAS boundary types are not exposed. Changing the boundary selector changes the required fields; saved inactive values do not become active boundaries. A mismatch between stage count and flow-profile count blocks calculation and retains the draft.

**Bed representation** must be selected explicitly: surveyed channel, combined survey/DEM, or conditional surface DEM. Selecting a survey category does not validate or create a survey. The engineer must supply the corresponding geometry. A hydroflattened DEM usually represents the water surface and cannot establish submerged conveyance; conditional surface-DEM results remain preliminary.

## Confirm → Calculate → Results

Review the complete input summary and assumptions, then explicitly confirm before running. Changes require renewed confirmation. HEC-RAS runs in an isolated project, and the program checks fresh result identity, section/profile count, flow, geometry and boundary readback. Missing or failed native exports remain visible and can be retried.

River results show **upstream/downstream reach WSE**, energy grade, section velocity and Froude number. These endpoints are not culvert headwater/tailwater or water levels within the excluded bridges. Reports retain the bed basis, boundaries, warnings and evidence links. A numerical flow readback check is not a complete floodplain mass-balance assessment.

Results provides English/Chinese DOCX and PDF reports, an English summary, and **Minimal / Complete** delivery folders. With the GIS prerequisites available, delivery includes Mapper terrain/contours, native cross-section mapping, QGIS layers/layouts and exhibits. No structure layer is manufactured for a river-only model. An exhibit is not a verified inundation map. Check both native programs and all significant warnings before engineering use.

## Boundary sensitivity

After a baseline computation, expand the sensitivity panel. It lists only the active boundary inputs: downstream slope, upstream slope when mixed, or downstream WSE for each profile. Choose low/high values with a site-specific basis, inspect the prepared cases and confirm once to run real HEC-RAS variants. There is no universal automatic ±percentage.

Compare the maximum change at matched cross sections and the response in the interior of the reach, not just at the prescribed boundary. If the boundary choice controls the conclusions, obtain better stage data, extend the model, or include the controlling structure in an appropriate model. A small response over a chosen range is not proof of calibration or section-spacing convergence.

## What has been checked

The river route has been exercised locally with actual HEC-RAS 7.0.1: synthetic prismatic normal-depth cases at 100/200 cfs, known-stage cases, a three-case boundary sensitivity batch, native warning export, bilingual reports and mapped dual packages. A browser acceptance run checked continuous-reach layout, conditional fields, invalid stage count and explicit confirmation. These are software verification cases, not results for Pagosa or any other real site. Existing multi-group culvert computation and native table exports were also regressed. Other machines and site hydraulic adequacy need separate review.

Manning coefficients retain up to seven decimal places in the native eight-character field. Result readback checks coefficient differences within 0.0000001, separately from station coordinates. River report input tables retain values such as 0.0425. A coefficient that rounds to zero or one at native precision is rejected before solving.


## Refreshing reports after sensitivity tests

After the batch finishes, click **Update reports and both packages** once on the Results page. The workflow collects the current completed studies, regenerates reports and builds both packages. **Regenerate reports** also remains available for a report-only update. Earlier editions remain saved. If mapping fails, the new reports remain available and package generation can be retried.

River reports read section roughness, banks and boundary cards from the hashed native inputs. Completed sensitivity studies are included only when bound to the exact report baseline. The report checks the case inputs/results, reproduces the baseline water levels and recomputes comparison values from native outputs. Studies from earlier geometry revisions are excluded; altered evidence stops report generation. Tested ranges remain conditional and do not close hydraulic QA or engineering acceptance.

Chinese diagnostic guidance is localized and repeated warnings are grouped with affected stations. Counts can overlap between native warnings and automated diagnostics; they are not counts of independent defects.


The Complete package retains the hashed sources behind report sensitivity tables, including case inputs, native results and diagnostic records. `Evidence/ReportSources/index.json` maps historical workspace paths to files inside the package; identical content may share one copy. Imagery acquisition records are preserved even when the offline mosaic is reused. The Minimal package remains intended for opening the model, Mapper and English exhibit; use Complete for source and sensitivity review.


## Feedback and source coverage

QA revision previews show a saved confirmation and the proposed section count when complete. Expand the DEM layout and QA panel to review changes before adopting them. Background progress reconnects automatically after a temporary connection failure.

Local PDF extraction attempts up to 200 pages and 600,000 characters, with OCR on up to 40 low-text pages. The source panel displays inspected and total page counts. Partial extraction and low-text pages remain marked for original-page review. Run **Reanalyze saved material** again to update documents parsed by an older extractor. Extracted text and figures require a site, unit and datum check before values are adopted.

English and Chinese reports use matching-language plot labels. Dense overview maps label a subset of sections while drawing every cutline. The section tables and profile panels retain all section identifiers.
