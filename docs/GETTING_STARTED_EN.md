# Installation quick reference

[English](GETTING_STARTED_EN.md) | [简体中文](GETTING_STARTED_CN.md)

Before choosing the boundary or requesting field records, open **Hydraulic evidence and offline replay → Inspect hydraulic evidence** to check gaps, station applicability and source editions. A field return reopens the affected inputs for confirmation. [Evidence intake and returns](HYDRAULIC_INTAKE_EN.md)

To see disk usage, keep an edition online, or recover working files while keeping its published packages, use **Saved projects → Manage this version → Storage and recovery by edition**. [Edition storage and recovery](LOCAL_RELEASE_EN.md#archive-and-recover-one-edition)

**Agree the delivery conditions before computing.** Open **Intended use and flow paths → Delivery conditions for this purpose**. Choose screening, comparison or engineering review, then enable the conditions. Select the modeled profile, any required dry section ends and source-backed geometry. For a culvert you can specify minimum road margin. For a river you can name a registered independent event, an optional observation RS and the maximum absolute stage error in feet. Give the project basis for numerical limits. The confirmation screen records these choices with that run.

After computing, read **Delivery assessment** and the opening decision in either full report. A failed limit lists what to revise. A missing observation or survey lists what to obtain. Use an editable revision to change model inputs or agreed conditions, recompute and choose the working edition before exporting its recipient guide. An open case can be transferred for diagnostic review. Meeting the listed checks supports the agreed purpose within the reported hydraulic QA limits. Engineering sign-off remains with the responsible engineer.

On your first visit, open **Try a worked river example**. Choose a Manning’s n, inspect the water-level change at RS 516 for the same East Fork flood, and open the practice report to compare all four sections. The exercise uses verified HEC-RAS outputs and keeps your selection in this browser tab. When starting your own location, choose the site type. Use the river option for a reach between bridges whose structures are excluded. Use the culvert option to calculate barrel flow, headwater or road overflow.

Open **Start a new project** or expand an entry under **Saved projects** to continue a previous version. Use coordinates for a new site, a survey package when you already have `survey.json` with its referenced files, or native input for a supported existing culvert model. At final confirmation, check the separate HEC-RAS, report and GIS rows. A mapped project checks its projected terrain crop before solving. If GIS needs attention, correct the terrain or choose hydraulic results and reports only, then confirm the revised outputs. Native geometry can require a second extent check after compilation. After preparation, choose **Review calculation inputs** when the required data are ready. To inspect a draft, expand the site data, geometry or hydraulic parameters. Check the assumptions and delivery options before authorizing a run.

After the run, **Summary** shows flow, water levels and the first issue requiring judgment. **Hydraulic review** contains the warnings and scenario studies. **Reports and maps** opens the PDFs, QGIS and both delivery packages. On the home page, expand a site's entry to find the original and its revisions. Version management is inside each entry.

**Drafts and adoption.** The current browser tab retains the project form and pending selections across language changes, navigation and refresh. **Save all selected changes** or **Review calculation inputs** applies the selected parameters and banks to the model. Direct parameter edits still autosave. After refreshing, reselect any attachments listed by name. Field feedback is drafted per flood event and written to the project with **Save and preview field feedback**.

**Revisions and batch recovery.** Use the revision number, purpose, local time and latest task to identify an edition. When a follow-up batch stops, check the delivery status, saved cases and retry scope alongside the existing hydraulic result. Resuming the batch may invoke HEC-RAS for cases that still require calculation.

**Starting with one coordinate.** Choose **River reach (bridges excluded)** and supply the project title and location. Leave unknown numbers empty. The app searches for a directed USGS river, nearby mapped road crossings and a DEM covering the candidate bends and cross sections. Open **Automatic DEM layout / QA repair**. At a crossing, choose the intended reach by its two road names. Generate the preview, check the river and banks against the imagery, then adopt it. The parameter page shows populated values, sources, estimates and any missing inputs together. One final confirmation starts HEC-RAS. [River instructions](RIVER_REACH_EN.md)

For a reach without structures, choose **River reach (bridges excluded)** and follow the [river guide](RIVER_REACH_EN.md). It removes culvert/road fields and requires channel-bed representation and active boundary conditions. The crossing-specific steps below apply to culvert projects.

On a new site, import the available material and check the crossing and elevation context, then choose **Prepare an automatic draft**. Review highlighted uncertainty and the complete parameter list before **Confirm and run HEC-RAS**.

For a site without an existing model, use [consolidated preparation](AUTOMATION_EN.md) to avoid repeated parameter transcription and separate bank confirmations.

Use the [Windows installation guide](WINDOWS_SETUP_EN.md), then the [user manual](USER_GUIDE_EN.md). Daily entry: `start_workflow.cmd`.

After the run, see [Results, revisions and sensitivity](RESULTS_REVIEW_EN.md) for optional native output completion, one-click QGIS preview and safe recalculation.

For an incomplete draft, start with **What should I do next?** Follow the link to section repair, automatic preparation or source review. If site data are needed, choose **Export missing site data (CSV)**. Fill values in the listed units, import the worksheet under site materials and select the candidates. After calculation, choose **Reports and maps → Verify packages and create recipient guide** for bilingual reading instructions tied to this run.

## First calculation from culvert photos and a pin

On the preparation page, open **Start with the crossing**. Import the photos, location and hydrology report. Compare the available values with the originals. Each parameter links to its editor and shows its evidence class. Identify the inlet and outlet on the DEM for each opening group, or associate surveyed openings. Choose **Preview reach anchors and sections**. Check the flow direction against the photos, then inspect the proposed extent, crossings and bank profiles. Adopt the displayed geometry to populate dependent inputs. Open the calculation review and check flow, roughness, dimensions and the estimated inverts before confirming the first run.

When a road drawing or memo arrives, open **Revise inputs / compare a new run → Create editable revision** on the results page. Import the supplement, select its road-width entry and choose **Compare width and road profiles**. Check the source wording, old and proposed widths, upstream offset and both crest profiles. If all six associated inputs have unique derivations, adopt them with the width in one action. Independent surveyed values and competing interpretations require individual review. The effective overflow width can remain an assumption even when a memo gives the nominal road width. Confirm the revised inputs before computing and compare the two runs before selecting an edition for handoff.

## Resolve an open condition and select a handoff edition

- **Wet section end.** Select its RS in the overview and choose **Inspect computed section**. Check the edition imagery, computed water level, neighboring sections and floodplain connectivity. Choose **Revise this wet section** to edit its direction or width in an independent draft. Preview DEM sampling, review banks and dependent inputs, then confirm the calculation. Compare wet ends and water levels between editions.
- **Estimated culvert inverts.** Choose **Request inlet and outlet elevations** and download the worksheet. Each opening group has one row per end with the previous estimate separate from the blank answer. Keep group, end, units, datum and edition identifiers intact. Ask for the value, evidence class and source. Pause if needed, then return to the issuing edition and import the reply in a new revision. Review matched values and any competing records before computing.
- **Unknown roadway discharge.** Open the native-output action and check the matching HEC-RAS run, plan and profile. Export the native roadway-flow record. An absent record stays unknown.
- **Handoff.** Compare supplemental sources, hydraulic results and remaining conditions. Retain the baseline, select the revision or pause. Choose **Prepare handoff for the selected use** and copy the entire generated folder. Its bilingual start pages link to the selected edition’s reports and map.

### Check what a revision changed

Under **Choose an edition or pause this review**, expand **Inspect section ends**. Filter by status and select an RS to open its current map and profile. A positive depth means that the computed water surface exceeds ground at that edition’s endpoint. A wider section places the endpoint on different ground. Inspect the flow path when a side remains wet. Upstream/downstream stage, maximum channel velocity and Froude number are shown for rivers; headwater, tailwater and roadway flow are shown for crossings.

After copying the entire `Handoff_…` folder, open `Start_EN.html` in Edge or Chrome. Under **Verify a copied folder**, select that same folder and wait for the file count and run ID. A mismatch names the affected file. Recopy from the selected edition and repeat the check. Keep working copies used for HEC-RAS edits in a separate directory. The check reads local files and requires no SteadyReach installation.
