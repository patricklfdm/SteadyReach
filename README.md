# SteadyReach

**English** | [简体中文](README.zh-CN.md)

A Windows desktop workflow for one-dimensional steady-flow culvert analysis with HEC-RAS. Work locally through three browser screens: **Project → Model → Results**. No AI service is needed.

## Start here

1. Download this repository as a ZIP and extract it into a writable folder, or clone it. Avoid OneDrive/network folders for active calculations.
2. Install **HEC-RAS 7.0.1** and, for editable maps and exhibits, **QGIS 3.44 LTR**. See [installation](docs/WINDOWS_SETUP_EN.md); newer HEC-RAS versions are not automatically interchangeable with this adapter.
3. Double-click **start_workflow.cmd**. On first use it prepares local Python and required packages; follow the setup prompts for QGIS. Keep the console open.
4. Try the included [Phelps Brook example](examples/phelps_brook/README.md), or follow the [no-existing-model guide](docs/NO_MODEL_GUIDE_EN.md) for your own crossing.
5. Review all parameters, correct values or assumptions, and explicitly confirm before the real solver starts. Open the reports and **Minimal / Complete** folders from Results.

[User manual](docs/USER_GUIDE_EN.md) · [Installation and repair](docs/WINDOWS_SETUP_EN.md) · [Troubleshooting](docs/TROUBLESHOOTING_EN.md) · [Scope and limitations](docs/LIMITATIONS_EN.md)

## What it does

- Queries USGS DEMs for U.S. locations, prepares terrain, samples cross sections and proposes bank positions.
- Imports a supported existing steady model, or builds a model from entered and terrain-derived inputs.
- Labels suggested/estimated values and leaves unsupported mandatory inputs empty. All no-model numerical fields can be edited before one final confirmation.
- Runs actual HEC-RAS, checks output identity, retains warnings and produces full English/Chinese DOCX and PDF reports plus an English summary.
- Produces a small native-model delivery folder and a complete folder with reports and, when GIS is enabled and available, Mapper terrain/contours, QGIS layouts and exhibits.

The supported calculation scope is one river/reach and one box or circular culvert crossing, potentially with multiple barrel groups. Surface DEM does not establish buried inverts. Successful calculation/package creation is not engineering approval.

## Your files

Working projects, downloaded data, local tools and reports are created on your computer and excluded by `.gitignore`. Back up the whole working project when needed. Never publish user attachments, model outputs or machine settings by forcing ignored files into Git.

Application code and original documentation: [MIT License](LICENSE). Bundled public examples, native templates and external programs retain their own terms; see [third-party notices](THIRD_PARTY_NOTICES.md).
