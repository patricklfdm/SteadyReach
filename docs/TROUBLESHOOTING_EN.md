# Troubleshooting

**English** | [简体中文](TROUBLESHOOTING_CN.md) | [Home](../README.md)

| Symptom | Action |
|---|---|
| Browser closes or an old address no longer works | Relaunch `start_workflow.cmd`, keep its console open, then Open / continue the saved project. The local token/port may change. |
| Missing parameter | Complete the highlighted field or explicitly adopt an applicable candidate. The draft remains saved; no calculation has started. |
| Confirmation becomes unavailable after editing | Save and refresh the full parameter list, then confirm the changed inputs again. |
| Original `.prj` refers to an unavailable plan | Upload all four files for the intended plan; select the actual supplied plan (for the included example: p01). Do not rename unrelated files to satisfy references. |
| Windows will not open a downloaded JSON on double-click | JSON is data, not a program. Open it from VS Code or Notepad using File → Open; the app's saved project does not depend on double-click association. |
| QGIS DLL/environment error | Start the installed QGIS from its official shortcut. Rerun setup and select the installation root, then `check_environment.cmd`. Do not manually launch an internal binary with an unrelated shell environment. |
| Download or certificate failure | Keep `status/setup` logs. Check connectivity, system clock and your organization's trusted certificates; retry setup. Keep certificate verification enabled. |
| HEC-RAS unavailable/unsupported | Install the supported 7.0.1 build normally. The adapter deliberately refuses an unknown executable. |
| HEC-RAS already has a project open | Save and close it yourself before retrying. Do not discard unrelated work. |
| Missing source CRS or different vertical datum | Supply the documented projection and datum, or run without GIS. Do not guess a projection or silently apply an elevation shift. |
| Reports ready, map incomplete | Read the mapping error, resolve missing terrain/imagery or QGIS, then regenerate delivery. A hydraulic result does not prove map completion. |
| Missing result shown as a dash | The field was not extracted or is unavailable. It is not zero. Check warnings and native output. |

For investigation retain the task log, `status/doctor.json`, and the project's saved input/summary files locally. Share only the files the recipient is authorized to see; logs can contain local paths. To stop a draft, use Stop this project → Abandon → Confirm abandon. Files remain available for your own backup.

## Saving, OCR and result editions

- **Selections remain pending:** click Save all changes, not browser Refresh. If a dependency changed, clear the stale selection and reopen the model; completed saves remain.
- **OCR unavailable:** rerun setup to install the pinned Windows bindings, then run the full environment check. No PowerShell execution-policy change is needed. Empty photo OCR is not a successful dimension extraction; use the retained original or a transcription.
- **QGIS shortcut fails:** on Results use Open QGIS review copy after a mapped Complete package exists. It uses the configured QGIS environment without editing global PATH. Missing QGIS still requires installation/setup.
- **Report links disappear after native import:** expected. Click Update reports and both packages; links return only for refreshed exports. See [results guide](RESULTS_REVIEW_EN.md).
- **Need to change a finished model:** create an independent editable revision on Results (workflow-built models), then confirm and solve it. Do not edit sealed result files.

When refreshing reports, an intact previous package can supply the same verified offline aerial mosaic. An edited manifest, changed map extent or image hash mismatch is rejected. Keep the sealed package and use a review copy for desktop software; preserve the error if regeneration fails.
