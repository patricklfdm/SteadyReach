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

## Measured results on the acceptance workstation

The signed software at [9f9f9903c82a](https://github.com/patricklfdm/SteadyReach/commit/9f9f9903c82aefe7294f72f6bd5af4fd43cbea54) completed the same-workstation pilot. A firm can use this build for a supervised trial within the documented scope.

| Entry | Registered jobs | Final pairs / eligible | First-attempt pairs / eligible | Expected stops detected |
|---|---:|---:|---:|---:|
| Coordinate | 3 | — | — | 3/3 |
| Partial evidence | 6 | 5/5 | 5/5 | 1/1 |
| Survey | 13 | 13/13 | 12/13 | — |
| Native model | 4 | 3/3 | 3/3 | 1/1 |

Across 26 registered jobs, 20 of 21 eligible jobs produced verified paired packages on the first attempt and all 21 did so eventually. All five seeded blockers were detected. False delivery-ready decisions totaled 0. An intentional low-space reservation accounts for the eligible retry. Each delivered job had its own native run ID, matching HDF and two readable report languages. Repeated runs at the same site count toward operational reliability.

- Washington State Park used the February 6, 2019 measurement of 41.0 m³/s. Eight interior points from that event were held back. The largest signed residual by absolute magnitude was +0.429 ft at RS 400 (model minus observed). The imposed outlet was excluded. The source gives no formal vertical accuracy assessment, and the project supplies no approved design tolerance. [USGS field data](https://doi.org/10.5066/P9K3ENAX)
- At Konkapot RS 2666, the five-section Q100 trial gave 1256.51 ft. The longer published conceptual model gave 1255.30 ft. Its dam, bridge and geometry differ. This is a comparison with another model. [Monterey design report](https://www.mass.gov/doc/conceptual-design-report/download)
- Before the frozen release, the Monterey case exposed report and terrain-link export failures. Its original HDF was re-exported successfully. The first formal candidate also stopped the Washington reach because it treated an in-place surveyed outlet as a streamgage. Four dependent jobs were incomplete in that candidate. The revised software verified the original point, preserved the unknown uncertainty and ran the whole gate again.

### Time, storage and recovery

| Matched stage | Original P5, s | Signed P10, s | Change |
|---|---:|---:|---:|
| Archive and retire | 11.48 | 32.95 | +187.02% |
| Restore | 2.59 | 2.33 | -10.04% |
| Recalculate through handoff | 42.55 | 42.69 | +0.33% |
| HEC-RAS worker | 4.61 | 4.86 | +5.34% |
| English report conversion | 3.83 | 3.89 | +1.41% |
| Chinese report conversion | 4.02 | 3.94 | -1.89% |
| Summary conversion | 2.98 | 2.88 | -3.29% |

Each column compares two nine-section jobs on the same workstation. With n = 2, nearest-rank P95 is the slower sample. The historical QGIS-only duration is unavailable. Only archive-and-retire exceeded the 20% investigation trigger. The candidate registry held 171 editions at inspection, versus 24 for the baseline. Profiling identified the scan for other editions that share a file. In the 24-edition registry the optimized inventory returned identical file ownership and reclaim decisions for both jobs, in 1.63 and 1.55 s versus 2.28 and 2.23 s previously. Allow the measured 32.95 s archive step for a supervised pilot. A larger registry needs a separate capacity target and test.

The 128 capacity samples recorded a peak of 6.66 GiB of logical working files and a minimum of 0.74 GiB free on the volume. These figures include this cohort’s release folder, new editions and converter scratch. Edition archives on other paths are excluded. Two migrations and verified rollbacks took 42.5 and 42.0 s. Recovery after native interruption took 29.1 s. Export recovery after QGIS timeout and a locked document took 10.5 and 10.8 s. Both export retries kept their original HDF.

Independent engineering sign-off, timed first use by an engineer and qualification on a second workstation remain pending.
