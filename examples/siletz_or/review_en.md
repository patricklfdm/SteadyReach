# Independent review of the SteadyReach 1D steady-flow benchmark

**Decision requested.** Determine whether the frozen versions reproduce the measured events adequately for the proposed use. The Siletz interior residual exceeds the prespecified 0.15 m investigation threshold. Engineering acceptance is pending. The mapped package opens a model of the January 2018 measured event. Design discharges and flood hazard mapping require a separate assessment.

## 1. Review the observations before opening the model

At Siletz, the downstream Twin Bridges sensor 986237 at RS 34913 prescribes stage. The Neighborhood Bar sensor 9695486 at RS 44056 is the only scored interior location. The two event windows span noon ±6 hours Pacific standard time. Each uses 49 approved discharge readings and 25 sensor readings per station. Compare the station coordinates, datum, sensor elevations and time conventions in the original CSV and XML files under each attempt's Sources folder. Horizontal positioning and time metadata require interpretation. Instrument precision alone does not establish total comparison uncertainty. [USGS measured water levels](https://www.usgs.gov/data/water-surface-elevation-data-siletz-river-2017-18)

The reach discharge equals the observed median at gage 14305500 multiplied by the published flow allocation ratio for river stations 44506 and 19532. The study released georeferenced section data and terrain. SteadyReach reused that survey interpretation, fixed channel/overbank roughness at 0.035/0.065, and calculated new profiles in HEC-RAS. Some sensors from this campaign informed the USGS study. Both dates were selected before inspecting these model residuals. Evaluate discharge transfer, temporal stability and survey representativeness separately. [USGS model release](https://www.usgs.gov/data/one-and-two-dimensional-hydraulic-models-siletz-river-oregon) · [USGS study and table 14](https://pubs.usgs.gov/publication/sir20255063/full)

## 2. Check model results against the measured stages

Signed error is calculated minus observed. Boundary values are in feet, interior elevations and errors in metres NAVD88. Repeated rows come from isolating a profile or extending map terrain. They refer to the same two observed dates.

| Attempt folder | Profile | Date | Reach cfs | Boundary requested / actual ft | Matches | Interior observed / calculated m | Error m |
|---|---|---|---:|---|---|---|---:|
{{results}}

The development event failed the native boundary readback. Open the dual-profile Model.f01 and compare its downstream stage with the last section in Model.p01.hdf, including the Critical Water Surface dataset. The requested low-flow stage is below the model's calculated critical elevation. Review the surveyed outlet/control location, section elevations, stage-to-section transfer and flow regime before proposing changes. Preserve both event identities and the original residuals. The independent-date holdout also exceeds the investigation threshold at the interior station. Do not fit roughness to that result and then reuse the event as independent validation. [HEC-RAS steady-flow boundary and regime guidance](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/6.3/basic-data-requirements/steady-flow-data)

East Fork provides a second check using different field observations. The calibration RMSE is **{{training}} m** and the holdout RMSE is **{{holdout}} m** across three interior stations, with downstream RS 0220 imposed. The measured flow and stage changed in the holdout, while n = 0.035 and the geometry stayed fixed. Inspect the dates, RS-by-RS errors, frozen inputs and native HDF in East_Fork. This short station-referenced reach tests stage reproduction. Siletz separately tests GIS delivery and a failed engineering threshold. [1979 surveyed sections](https://pubs.usgs.gov/of/1980/1190/report.pdf) · [1979 measured stages](https://pubs.usgs.gov/of/1980/1189/report.pdf) · [1980 holdout](https://pubs.usgs.gov/of/1982/0359/report.pdf)

## 3. Open and record the decision

{{packages}}

Open the minimal HEC_RAS/Model.prj in HEC-RAS 7.0.1 and enter RAS Mapper. The complete package includes the bilingual exhibits, GIS project, source evidence and reports. Make a working copy before saving through HEC-RAS or QGIS. Published bathymetric terrain takes precedence. Current USGS 3DEP elevations fill missing cartographic cells in the square exhibit only. The hydraulic station/elevation arrays come from the archived cross sections. Inspect the boundaries of the two terrain sources before interpreting floodplain detail.

1. Identify the attempt ID, run ID and native HDF digest from review.json. Verify package bytes against SHA256.json.
2. Inspect flow, water surface and critical elevation at RS 34913 and RS 44056 in the native output. Trace the matching date and sample values back to the raw tables. Review warnings.txt when available. The failed run retains its worker log.
3. Check the 18-row section inventories for each profile, the source datum and field measurement limits. State the accuracy required for the intended use, how it was determined and where it applies.
4. Record an independent disposition, named model version, scope, unresolved stations and any requested new measurements. Where recalibration is necessary, reserve a further observed event before tuning. The packet currently contains no engineer disposition or signature.
