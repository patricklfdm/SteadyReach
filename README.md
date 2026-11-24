# SteadyReach

**English** | [简体中文](README.zh-CN.md)

[Local production review and recovery](docs/LOCAL_RELEASE_EN.md) · [Measured Siletz River benchmark](examples/siletz_or/README.md)

A Windows desktop workflow for one-dimensional steady-flow river and culvert analysis with HEC-RAS. The workflow runs locally without an AI service. The browser guides you through **Project → Prepare model → Confirm inputs → Results**. On a first visit, **Try a worked river example** lets you compare recorded water levels and open a practice report before creating a project. [Getting started](docs/GETTING_STARTED_EN.md)

For a new model, import the available material and check the crossing and terrain metadata. Click **Prepare an automatic draft** to prepare sections, banks and labelled estimates together. Resolve highlighted issues, then confirm the complete model once. Numeric bank editing and profile grids support corrections. [Preparation guide](docs/AUTOMATION_EN.md).

**Starting with one coordinate.** Choose **River reach (bridges excluded)** and supply the project title and location. Leave unknown numbers empty. The app searches for a directed USGS river, nearby mapped road crossings and a DEM covering the candidate bends and cross sections. Open **Automatic DEM layout / QA repair**. At a crossing, choose the intended reach by its two road names. Generate the preview, check the river and banks against the imagery, then adopt it. The parameter page shows populated values, sources, estimates and any missing inputs together. One final confirmation starts HEC-RAS. [River instructions](docs/RIVER_REACH_EN.md)

## Start here

1. Download this repository as a ZIP and extract it into a writable folder, or clone it. Avoid OneDrive/network folders for active calculations.
2. Install **HEC-RAS 7.0.1** and, for editable maps and exhibits, **QGIS 3.44 LTR**. See [installation](docs/WINDOWS_SETUP_EN.md); newer HEC-RAS versions are not automatically interchangeable with this adapter.
3. Double-click **start_workflow.cmd**. On first use it prepares local Python and required packages; follow the setup prompts for QGIS. Keep the console open.
4. For a river between two bridges, follow [the river walkthrough](docs/RIVER_REACH_EN.md). For a culvert, try the [Phelps Brook example](examples/phelps_brook/README.md) or the [crossing guide](docs/NO_MODEL_GUIDE_EN.md).
5. Review all parameters, correct values or assumptions, and explicitly confirm before the real solver starts. Open the reports and **Minimal / Complete** folders from Results.

[User manual](docs/USER_GUIDE_EN.md) · [Installation and repair](docs/WINDOWS_SETUP_EN.md) · [Troubleshooting](docs/TROUBLESHOOTING_EN.md) · [Scope and limitations](docs/LIMITATIONS_EN.md)

The Results screen assigns a handoff level, identifies the limiting sections and evidence, and links to the existing QA and revision tools. [Delivery assessment](docs/RESULTS_REVIEW_EN.md#delivery-assessment).

## What it does

- Supports draggable DEM maps, fine zoom and explicit batch section rotation → real DEM preview → apply, with intersection checks and preserved draft history.
- Joint QA proposals compare neighboring section directions and wet-end extensions, resample rotated profiles, and present bank candidates for consolidated confirmation. Search bounds and unresolved hydraulic findings remain visible.
- River results offer two nested DEM spacing trials with one batch confirmation, actual solver runs and comparison of water levels, warnings and wet ends. [Results and spacing guide](docs/RESULTS_REVIEW_EN.md).
- River wet-end repairs can run within a confirmed width and round limit, using each actual calculation to extend DEM ends and export final reports and both packages. [Repair batch guide](docs/RESULTS_REVIEW_EN.md#automatic-wet-end-repair-batches).
- Continue directly from a computed repair or spacing case. The new editable revision carries its actual geometry and input sources, prepares joint DEM/bank changes, and presents one full parameter confirmation before the next calculation. [Continuation steps](docs/RESULTS_REVIEW_EN.md#continue-from-a-computed-case).
- Queries USGS DEMs for U.S. locations, prepares terrain, samples cross sections and proposes bank positions.
- Ranks bank pairs across adjacent sections, preserves manual controls and flags interpolation or unstable choices. Revision results show verified water-level changes at every matching section and changes in warning coverage.
- Imports a supported existing steady model, or builds a model from entered and terrain-derived inputs.
- Labels suggested/estimated values and leaves unsupported mandatory inputs empty. All no-model numerical fields can be edited before one final confirmation.
- Runs actual HEC-RAS, checks output identity, retains warnings and produces full English/Chinese DOCX and PDF reports plus an English summary.
- Automatically exports all supported culvert-group/profile tables and the full native warning table; earlier runs can retry export and refresh deliverables without solving again. See [scope and desktop requirements](docs/RESULTS_REVIEW_EN.md).
- Produces a small native-model delivery folder and a complete folder with reports and, when GIS is enabled and available, Mapper terrain/contours, QGIS layouts and exhibits.

The supported calculation scope is one river/reach: either a river without structures, or one box/circular culvert crossing with supported barrel groups. [River-reach guide](docs/RIVER_REACH_EN.md) covers bridge-excluded limits, known-stage boundaries and sensitivity. Surface DEM does not establish submerged beds or buried inverts. Successful calculation/package creation is not engineering approval.

## Source-assisted input

The model page now retrieves effective FEMA FIS reports by coordinates and supports grouped river/Q100/roughness selection with page references. It searches supported public sources, parses survey CSV, PDF text/scanned pages, DOCX paragraphs/tables, KML/KMZ placemarks and labelled text, attempts local OCR, overlays survey points on the DEM and proposes values with provenance. It keeps existing values, distinguishes conflicts and failed attempts, and groups parameters in collapsed sections with a missing-item navigator. See [source assistance](docs/SOURCE_ASSIST_EN.md). Provider coverage is limited; unsupported or ambiguous site information still needs an engineer.

Under **Saved projects**, expand a project name to see the original and its QA drafts and revisions. Select **Open / continue** on the version you want. You can delete individual versions and restore them from **Deleted projects**.

## Your files

Working projects, downloaded data, local tools and reports are created on your computer and excluded by `.gitignore`. Back up the whole working project when needed. Never publish user attachments, model outputs or machine settings by forcing ignored files into Git.

Application code and original documentation: [MIT License](LICENSE). Bundled public examples, native templates and external programs retain their own terms; see [third-party notices](THIRD_PARTY_NOTICES.md).

## Results and follow-up changes

Save selected candidates, associations and banks together. Results supports independent revisions, native-table cross-checks, synchronized reports/packages, wet-edge plots, source-based sensitivity ranges with one batch confirmation and launching a QGIS review copy. See [result operations](docs/RESULTS_REVIEW_EN.md). Local flow paths, structural interpretation and engineering acceptance still require judgment.

River reports now include native-input readback and completed baseline-bound sensitivity studies. Use **Update reports and both packages** once after a study. Complete packages retain portable sensitivity evidence and imagery acquisition records. See [River-reach guide](docs/RIVER_REACH_EN.md).
