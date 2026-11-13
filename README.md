# SteadyReach

**English** | [简体中文](README.zh-CN.md)

For new sites, let the program propose anchors, section positions/extents and bank candidates, then review them together. Completed projects can create independent QA revisions. See [automatic DEM layout and QA-guided repair](docs/DEM_AUTOMATION_EN.md).

Use [consolidated preparation](docs/AUTOMATION_EN.md) for multiple opening groups, source-linked formulas, early geometry checks and batch input/bank review. Existing choices stay saved.

A Windows desktop workflow for one-dimensional steady-flow culvert analysis with HEC-RAS. Work locally through three browser screens: **Project → Model → Results**. No AI service is needed.

## Start here

1. Download this repository as a ZIP and extract it into a writable folder, or clone it. Avoid OneDrive/network folders for active calculations.
2. Install **HEC-RAS 7.0.1** and, for editable maps and exhibits, **QGIS 3.44 LTR**. See [installation](docs/WINDOWS_SETUP_EN.md); newer HEC-RAS versions are not automatically interchangeable with this adapter.
3. Double-click **start_workflow.cmd**. On first use it prepares local Python and required packages; follow the setup prompts for QGIS. Keep the console open.
4. Try the included [Phelps Brook example](examples/phelps_brook/README.md), or follow the [no-existing-model guide](docs/NO_MODEL_GUIDE_EN.md) for your own crossing.
5. Review all parameters, correct values or assumptions, and explicitly confirm before the real solver starts. Open the reports and **Minimal / Complete** folders from Results.

[User manual](docs/USER_GUIDE_EN.md) · [Installation and repair](docs/WINDOWS_SETUP_EN.md) · [Troubleshooting](docs/TROUBLESHOOTING_EN.md) · [Scope and limitations](docs/LIMITATIONS_EN.md)

## What it does

- Supports draggable DEM maps, fine zoom and explicit batch section rotation → real DEM preview → apply, with intersection checks and preserved draft history.
- Queries USGS DEMs for U.S. locations, prepares terrain, samples cross sections and proposes bank positions.
- Imports a supported existing steady model, or builds a model from entered and terrain-derived inputs.
- Labels suggested/estimated values and leaves unsupported mandatory inputs empty. All no-model numerical fields can be edited before one final confirmation.
- Runs actual HEC-RAS, checks output identity, retains warnings and produces full English/Chinese DOCX and PDF reports plus an English summary.
- Produces a small native-model delivery folder and a complete folder with reports and, when GIS is enabled and available, Mapper terrain/contours, QGIS layouts and exhibits.

The supported calculation scope is one river/reach and one box or circular culvert crossing, potentially with multiple barrel groups. Surface DEM does not establish buried inverts. Successful calculation/package creation is not engineering approval.

## Source-assisted input

The model page now searches supported public sources, parses survey CSV/PDF/text, attempts local OCR, overlays survey points on the DEM and proposes values with provenance. It keeps existing values, distinguishes conflicts and failed attempts, and groups parameters in collapsed sections with a missing-item navigator. See [source assistance](docs/SOURCE_ASSIST_EN.md). Provider coverage is limited; unsupported or ambiguous site information still needs an engineer.

## Your files

Working projects, downloaded data, local tools and reports are created on your computer and excluded by `.gitignore`. Back up the whole working project when needed. Never publish user attachments, model outputs or machine settings by forcing ignored files into Git.

Application code and original documentation: [MIT License](LICENSE). Bundled public examples, native templates and external programs retain their own terms; see [third-party notices](THIRD_PARTY_NOTICES.md).

## Results and follow-up changes

Save selected candidates, associations and banks together. Results supports independent revisions, native-table cross-checks, synchronized reports/packages, wet-edge plots, optional sensitivity batches and launching a QGIS review copy. See [result operations](docs/RESULTS_REVIEW_EN.md). Local flow paths, structural interpretation and engineering acceptance still require judgment.
