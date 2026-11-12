# Windows installation and repair

**English** | [简体中文](WINDOWS_SETUP_CN.md) | [Home](../README.md)

## 1. Extract the application

Download this repository's ZIP and extract it completely, or clone it. Choose a local writable folder such as `C:\Work\SteadyReach`; no specific drive is required. Do not run inside the ZIP. Allow several GB for tools and additional space for terrain and results. No Python installation or command-line experience is required for the normal launcher path.

## 2. Install HEC-RAS

Use the official [HEC-RAS download page](https://www.hec.usace.army.mil/software/hec-ras/download.aspx). In **Archived Versions**, choose **HEC-RAS 7.0.1 Setup Package** for native Windows. Complete the vendor installer normally and open HEC-RAS once. This adapter checks the inspected 7.0.1 executables and registered controller; a later version will not automatically pass. Do not edit the approved hashes to bypass this check.

Save and close any engineering project before a workflow calculation. If an existing project prevents the owned solver session from starting, the app stops and reports the issue instead of overwriting that project.

## 3. Install QGIS if you need maps

Install **QGIS 3.44 LTR** from [QGIS downloads](https://qgis.org/download/), using a Windows standalone installer for that series. The app was exercised with 3.44.15. Newer versions require their own compatibility checks. Start QGIS normally once. The app needs its installation root containing both `bin` and `apps`; select that root when setup asks. Do not choose `qgis-bin.exe`, the Start menu shortcut, or only the `bin` folder.

QGIS is needed for editable layouts and mapped delivery. You may defer it for a native-model/report exercise with GIS unchecked; the full environment check will still report mapped delivery as unavailable.

## 4. Double-click start_workflow.cmd

First start invokes `setup_workflow.cmd`. It creates a checkout-local Python 3.12 environment, installs pinned Python packages, prepares the solver runtime and downloads a portable LibreOffice PDF converter. It checks download hashes and keeps logs under `status/setup`. HEC-RAS and QGIS remain separately installed programs. No administrator elevation or security-policy change is requested by the application setup.

Downloads can take several minutes. Read the byte/percentage/progress messages; do not repeatedly open additional setup windows. If a source stalls or fails, keep the logs and rerun setup. Verified completed downloads are reused. Failed partial files do not count as successful downloads.

When prompted, choose QGIS's installation root or press Enter to defer. At completion, the browser opens the local application. Keep the console running. Pressing a key at the console's final “press any key” prompt closes a finished launcher; it does not uninstall the environment or erase projects.

## 5. Check or repair later

- **Normal use:** double-click `start_workflow.cmd`.
- **Repair/install dependencies or update QGIS selection:** double-click `setup_workflow.cmd`.
- **Check installation, actual PDF conversion and QGIS export:** double-click `check_environment.cmd`. The detailed result is `status/doctor.json`.

These checks are software checks, not a hydraulic calculation. A successful check does not approve a site design. If a `.venv` folder is incomplete, keep it for diagnosis; move it aside only after all app/installation windows have stopped, then rerun setup. Do not remove saved projects to repair Python.

If software paths change, rerun setup. Machine choices live in `.tools/workflow_tools.json`; they are local and must not be published. See [troubleshooting](TROUBLESHOOTING_EN.md).
