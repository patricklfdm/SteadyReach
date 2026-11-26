# Single-workstation pilot

[简体中文](PILOT_CN.md) · [Administration and recovery](OPERATIONS_EN.md) · [Release checks](LOCAL_RELEASE_EN.md)

An engineer can use this trial for a single-reach, one-dimensional steady-flow study within the supported geometry. Each package identifies the selected version, input evidence, original HEC-RAS result and outstanding hydraulic questions. Package integrity and field agreement are separate decisions.

## Choose the starting point

| Available material | What the engineer does | Evidence needed for the intended use |
|---|---|---|
| A coordinate | Confirm the reach and flow direction. Read the missing-input register and download the field request. | Establish the flow, vertical units and datum, submerged geometry, hydraulic boundaries and any crossing dimensions. A nearby relative stage needs the event, a datum tie and a spatial transfer before it can set a boundary. |
| Drawings and partial site information | Import the documents, inspect the map, review the parameters marked estimated and confirm the study purpose. Return corrected fields against the selected edition. | The report carries assumptions forward. For a study that calls for surveyed inverts or tailwater, collect those items and confirm the affected parameters. |
| A surveyed river reach | Import the survey folder and dated imagery. Review flow, coordinate system, stage datum, bathymetry and the independent event locations. | Keep a prescribed downstream stage separate from interior observations. Set an error criterion with engineering justification. Retain unknown measurement uncertainty. |
| An existing steady culvert model | Select the original project, plan, geometry and flow files. Inspect the selected plan and approve the foot convention and datum. | The inspected importer supports one reach with a circular/box crossing and constant discharge per profile. A georeferenced presentation additionally needs reviewed map context. Native-only packages identify their model-space scope. |

## Review and issue a result

1. Open the selected edition and verify the native run, profiles, section count and open warnings. Check whether the available observations cover the proposed use. Record the location of a failure or missing field.
2. Compare the revision against the baseline. Return measurements through the field request. Review the changed items, recompute and select an edition for handoff.
3. Verify the complete and minimal manifests. Open the two report languages in the complete folder. Check the HEC-RAS result identity in both folders. For mapped deliveries, open the offline exhibit and review the terrain, imagery and model alignment.
4. When sharing externally, inspect the recipient's file inventory and the review status of that exact edition. Use the approved contact channel for originals. Engineering approval is a separate project decision.

## Release workload for administrators

Add `--p10 --p10-sources <frozen-originals-directory> --p10-baseline <original-P5-release.json>` to the P9 release command. Use a signed candidate, a disposable checkout and the original P5 hardware and two restore workloads. The source directory contains `wsp_raw`, `wsp_imagery`, `konkapot_imagery`, `twinpipe`, the Konkapot report and referenced terrain, and the USACE example archive. The public source inventory and selection rules are under `examples/enterprise_pilot`. Keep local projects, original documents and signing keys outside version control.

The gate registers 26 jobs across four entry routes. Five incompatible or incomplete requests must stop at the specified decision. The other 21 must have distinct native run IDs, sealed paired packages and readable bilingual reports. The low-space exercise makes an impossible reservation, checks the refusal and retries at a feasible size. Jobs that repeat a site contribute to software reliability. Only original observations at independent interior stations contribute to field comparisons.

Review `p10/release.json`, the top-level `release.json` and `storage_samples.jsonl`. Evaluate first-pass and final paired delivery against the eligible denominator, and false-ready outcomes against all seeded blockers. The same-host timing comparison uses two matched nine-section workloads, so its nearest-rank P95 is the slower of those two jobs. Investigate a stage increase over 20% using the retained timings and logs. Treat unwitnessed operator time, independent engineering approval and cross-machine compatibility as open qualifications.

The Washington State Park case uses measured Missouri river terrain, discharge and interior water elevations. The Monterey case uses a published Massachusetts conceptual alternative, conditional submerged geometry and a shortened reach. Its comparison is against a published model result. Spring Creek is a software tutorial. The Phelps Brook comparison reproduces published model output. [Missouri source data](https://doi.org/10.5066/P9K3ENAX) · [Missouri study](https://doi.org/10.3133/sir20225002) · [Monterey conceptual design](https://www.mass.gov/doc/conceptual-design-report/download) · [Phelps Brook release](https://doi.org/10.5066/P14HJGZI)
