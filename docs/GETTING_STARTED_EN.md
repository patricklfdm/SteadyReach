# Installation quick reference

[English](GETTING_STARTED_EN.md) | [简体中文](GETTING_STARTED_CN.md)

Open **Start a new project** or expand an entry under **Saved projects** to continue a previous version. Use coordinates for a new site, a survey package when you already have `survey.json` with its referenced files, or native input for a supported existing culvert model. At final confirmation, check the separate HEC-RAS, report and GIS rows. A mapped project checks its projected terrain crop before solving. If GIS needs attention, correct the terrain or choose hydraulic results and reports only, then confirm the revised outputs. Native geometry can require a second extent check after compilation. After preparation, choose **Review calculation inputs** when the required data are ready. To inspect a draft, expand the site data, geometry or hydraulic parameters. Check the assumptions and delivery options before authorizing a run.

After the run, **Summary** shows flow, water levels and the first issue requiring judgment. **Hydraulic review** contains the warnings and scenario studies. **Reports and maps** opens the PDFs, QGIS and both delivery packages. On the home page, expand a site's entry to find the original and its revisions. Version management is inside each entry.

**Starting with one coordinate.** Choose **River reach (bridges excluded)** and supply the project title and location. Leave unknown numbers empty. The app searches for a directed USGS river, nearby mapped road crossings and a DEM covering the candidate bends and cross sections. Open **Automatic DEM layout / QA repair**. At a crossing, choose the intended reach by its two road names. Generate the preview, check the river and banks against the imagery, then adopt it. The parameter page shows populated values, sources, estimates and any missing inputs together. One final confirmation starts HEC-RAS. [River instructions](RIVER_REACH_EN.md)

For a reach without structures, choose **River reach (bridges excluded)** and follow the [river guide](RIVER_REACH_EN.md). It removes culvert/road fields and requires channel-bed representation and active boundary conditions. The crossing-specific steps below apply to culvert projects.

On a new site, import the available material and check the crossing and elevation context, then choose **Prepare an automatic draft**. Review highlighted uncertainty and the complete parameter list before **Confirm and run HEC-RAS**.

For a site without an existing model, use [consolidated preparation](AUTOMATION_EN.md) to avoid repeated parameter transcription and separate bank confirmations.

Use the [Windows installation guide](WINDOWS_SETUP_EN.md), then the [user manual](USER_GUIDE_EN.md). Daily entry: `start_workflow.cmd`.

After the run, see [Results, revisions and sensitivity](RESULTS_REVIEW_EN.md) for optional native output completion, one-click QGIS preview and safe recalculation.
