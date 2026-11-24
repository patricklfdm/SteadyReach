# Check a steady-flow model against two measured East Fork River floods

[简体中文](README.zh-CN.md) · [Section review on the results page](../../docs/RIVER_COMPARISON_EN.md)

This short Wyoming reach has four monumented USGS sections, 0220, 0301, 0421 and 0516. Their identifiers give distance upstream in metres from the reference at 0000. The 296 m reach uses the 21 May 1979 survey at one-metre transverse intervals. The surveyed staff gages refer to NGVD29. Add 2,150 m to the tabulated relative elevations.

| Input | Table and locator |
|---|---|
| Surveyed bed elevations | 1979 survey, tables 4–7, printed pp. 21, 25, 29, 33. Read the 21 May column of each table. The source marks carried dry-point values. [USGS OFR 80-1190](https://pubs.usgs.gov/of/1980/1190/report.pdf) |
| Calibration, 30 May 1979 | Table 10, printed p. 33, staff stages from 14:10 to 14:12 local survey time. Table 11, printed p. 35, discharge at section 0000 of 16.3 m³/s at 14:16. [USGS OFR 80-1189](https://pubs.usgs.gov/of/1980/1189/report.pdf) |
| Holdout, 10 June 1980 | Tables 49 and 50, printed pp. 100, 110. Left/right readings at the four sections from 11:59 to 12:09, using their mean. Discharge at 0000 was 19.3 m³/s at 12:15. [USGS OFR 82-359](https://pubs.usgs.gov/of/1982/0359/report.pdf) |

The optional home-page exercise reads [practice.json](practice.json). It includes water surface elevations at all four sections from three recorded runs of the 30 May 1979 event. The roughness values are 0.030, 0.035 and 0.040. Each case identifies its native HDF by SHA-256. The exercise compares against 0.030 in metres, NGVD29. RS 220 supplies the downstream stage. The Windows procedure below can reproduce these runs.

## Repeat on Windows

Prepare SteadyReach and its supported HEC-RAS as described in the main guide. From the repository root run the following. Outputs go to a new directory for each step.

```powershell
.\.venv\Scripts\python.exe examples\east_fork_wy\field_trial.py
```

Copy the output directory from the last line. Use its calibration record in the second command.

```powershell
.\.venv\Scripts\python.exe examples\east_fork_wy\field_trial.py --calibration "projects/east_fork_wy_check/<first-run>/calibration.json"
```

The first command varies one uniform Manning n over seven prespecified values from 0.020 to 0.050 in increments of 0.005. It minimizes the unweighted stage RMSE of the three non-boundary sections. The second command checks the saved evidence and uses the frozen n and geometry with the new event flow and downstream stage. Read `residuals.csv`, case `model/Model.prj`, `execution.json` and `native_export/warnings.txt`. The sign convention is computed minus observed. The downstream stage at RS 0220 is imposed and has a blank residual for both events.

| Metric | Calibration | Holdout |
|---|---:|---:|
| Fitted / frozen uniform n | 0.035 | 0.035 |
| Scored sections | 3 | 3 |
| RMSE (m) | 0.0228 | 0.0147 |
| Mean absolute error (m) | 0.0201 | 0.0145 |
| Signed bias (m) | +0.0130 | +0.0037 |
| Largest absolute error (m) | 0.0350 | 0.0162 |

The four sections remained dry at both sampled ends in these two solutions. HEC-RAS reported divided flow at RS 0301 in both. Snowmelt runoff snapshots, an applied downstream stage and three independent station locations provide a limited check of this short reach. Roughness and subarea boundaries are modeling choices. The reach lengths use measured station spacing for all three flow paths. The energy-loss coefficients (expansion 0.3, contraction 0.1) and steady, subcritical, constant discharge are assumptions. The staff gages were a few metres upstream of the sections. USGS reports typical bed-elevation uncertainty of 0.02–0.03 m, stage rounding and local superelevation at bends. The bed could change between years. Absolute surveyed plan coordinates and a separate horizontal error bound are unavailable in this station-based trial. Its native project uses a local schematic engineering grid and carries no GIS or flood-extent claim. The test does not establish transferable accuracy for a Q100 profile.
