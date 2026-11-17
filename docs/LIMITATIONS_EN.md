# Scope and interpretation

**English** | [简体中文](LIMITATIONS_CN.md) | [Home](../README.md)

This application supports Windows-native, one-reach 1D steady analysis for a river without structures or one box/circular culvert crossing, including supported groups of barrels. The river builder supports normal-depth/known downstream WSE boundaries; river-only native imports are not yet supported. It does not provide unsteady-flow, 2D flooding, sediment transport, structural design or a universal HEC-RAS importer.

**Information still requiring a person:** representative design flow, structure opening/floor/entrance, applicability of estimates, units/datums, real flow direction, section/bank/road coverage and interpretation of hydraulic warnings. Automated estimates are conditional choices; surface DEM cannot establish buried inverts. Coordinates alone cannot produce an accepted engineering conclusion.

The installed HEC-RAS adapter is pinned to inspected 7.0.1 binaries. QGIS 3.44.15 and the pinned PDF/Python dependencies have been exercised on Windows. New operating systems, software versions and machines require their own checks.

Keep these outcomes separate:

| Outcome | Meaning |
|---|---|
| Calculation completed | A fresh native solve produced outputs with the expected identity. |
| Report/package generated | Files were produced and dependencies checked. |
| Hydraulic QA | Warnings, continuity, flow regimes, boundaries and numerical stability require review. |
| Engineering acceptance | The inputs and conclusions are accepted for the intended site and purpose by the responsible engineer. |

Automatic output extraction can lack full native warning tables or complete roadway/group flow splits. Missing outputs stay unavailable. A positive road margin does not establish that every bypass remains dry. Bank margins are not levee protection levels. An exhibit shows ground and model locations; it is not a verified flood inundation map.

The included USGS example permits comparison with published model output. Reproducing it is not field calibration. Native output should be inspected and significant inputs tested for sensitivity before design conclusions are drawn. The user retains responsibility for final interpretation and acceptance.

## Scope of the added automation

Native group and full warning tables are exported automatically from the inspected English/US Customary HEC-RAS 7.0.1 process. An available signed-in Windows desktop and clipboard are required; this is not a headless-server guarantee. Failed exports retain computed results and allow a one-click retry or manual fallback. Display/machine discrepancies remain explicit QA issues; blanks are never converted to zero. See [export behavior and limits](RESULTS_REVIEW_EN.md).

Independent revisions apply to workflow-built models. Wet-edge searches are bounded, preserve structure approaches and never establish floodplain connectivity or convergence. Sensitivity tests explicit ranges; no universal range, field calibration or design certification is supplied. OCR can miss or misread text; catalog coverage is finite. English report templates do not translate arbitrary user-written notes; language review is flagged where Chinese construction notes remain.

## Automatic DEM / QA proposals

[Automatic layout and QA repair](DEM_AUTOMATION_EN.md) adds anchor searches, adaptive positions/widths and wet-end extensions preserving original samples. **Prepare QA revision suggestions** on Results proposes changes in an independent revision; adoption still requires full parameter confirmation before a solve. Direction, flow connectivity, structures, boundaries and unresolved warnings remain engineering decisions, not convergence or design acceptance.
