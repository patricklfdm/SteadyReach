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
