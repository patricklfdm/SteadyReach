# Local production review

## P20 held-out events on new reaches

Use an isolated Windows checkout with HEC-RAS and the report converter configured. Place the USGS originals in `status/p20_sources` under the filenames in `examples/enterprise_pilot/big_river_sources.json`. Keep the compressed DEMs and original CSVs. The commands check all nine publisher files against their registered SHA-256. Use a new output directory inside the checkout and allow space for the native results, reports and archive.

```powershell
python scripts/p20_release.py freeze --raw status/p20_sources --out status/p20/new_cohort
python scripts/p20_release.py forecast --raw status/p20_sources --out status/p20/new_cohort
python scripts/p20_release.py score --raw status/p20_sources --out status/p20/new_cohort
python scripts/p20_release.py archive --raw status/p20_sources --out status/p20/new_cohort
```

Registration reads plan coordinates and surveyed terrain, then freezes event roles, source rows and criteria. Forecasting reads only the outlet measurement and computes both spacings. After an interrupted batch, rerunning forecast reuses completed case receipts. Scoring checks both reaches, every event and the native HDFs before reading interior observations. Each residual and unmet criterion is preserved. Archiving builds both Complete and Minimal native packages from the existing coarse results at each site, then verifies the ZIP contents. Start with `START_HERE.txt` and `scores.json` inside `P20_blind_validation.zip`. The archive contains both native spacings, bilingual reports in the Complete packages and the original USGS files. This benchmark uses native-only delivery. [Event results and applicable scope](PRODUCTION_ROADMAP_EN.md)

## P19 steady-flow applicability

In feasibility for an editable reach, open **Check flood timing with a USGS discharge record**. Select the modeled profile, event date in UTC and the event station’s USGS continuous discharge GeoJSON. The check identifies the station, units, approved records, pagination, event-day gaps and the longest observed interval near the modeled discharge. Verify station applicability and compare the duration with reach travel time. After calculation, the results page, bilingual reports and handoff notes also identify boundary influence, changes in overbank conveyance and conditions that call for a different hydraulic method.

`python scripts/p19_release.py --hydrograph <Turkey_2016.json> --archive <project-workspace> --p17 <P17-release.json>`

## P18 location-specific field requests

In a calculated river edition open **Review → Import a field return and compare changes → Request historical surveys at specific locations**. Set the applicable survey dates and optionally add RS identifiers. Download the ZIP. Take the GeoJSON to the field in WGS84 and use the model datum listed on each feature for reported elevations. Model centers identify search areas. Always use the actual coordinates and time of a recovered water level. For profiles return the included CSV, original record, date, method and uncertainty in ft (leave unknown accuracy blank). Import the original stage table separately. A return goes into a new revision. An out-of-period survey needs a separately dated edition.

Run `python scripts/p18_release.py --p17 <P17 release.json> --p11-workspace <archived P11 checkout> --p11-receipt <P11 release.json> --measurements <Washington field CSV>` in the isolated checkout containing the P17 jobs. The receipt records the Floyd and Turkey packets, the actual Washington source row and the affected hydraulic inputs.

[简体中文](LOCAL_RELEASE_CN.md) · [Production priorities and acceptance criteria](PRODUCTION_ROADMAP_EN.md)

## P17 single-factor stage diagnostics

On a computed river's results review page, open **Test one explanation for a stage error**. Select an event and one physically supported change, then freeze and preview. Queue additional factors for the same parent and event before confirming the batch. Each case starts from the parent geometry.

- For terrain vintage, supply a georeferenced GeoTIFF and verify its elevation units and vertical datum. The two surfaces are sampled at the same section stations, retaining the original bed-to-surface correction.
- For bed sensitivity, enter a signed change in feet at midchannel. It tapers to zero at the banks. For an existing known-stage outlet, supply the absolute event stage in the parent datum.
- Refine adjacent sections from the DEM or supply nested geometry JSON in the same CRS, datum and units. Check the retained sections, main-channel length and changes in mapped overbank path lengths.
- An optional diagnostic comparison CSV uses `profile,rs,stage_ft,flow_cfs,vertical_datum,source_record`. Include non-outlet locations and the original event record. Eligible observations already assigned to a single-profile parent can also be reused. The comparison is retrospective.

Inspect observed errors, signed differences at common sections, wet-limit locations and complete native warning counts. A worse observed error calls for retaining the parent. Unavailable warning exports are marked explicitly. Reproduce the cases in an isolated checkout with `scripts/p17_release.py <P12 checkout>`; `--resume <acceptance directory>` reuses the verified local baselines.

## P16 event flood marks

In a river project with located sections and a centerline, open **Find USGS event flood marks**. Enter the flood year and official river name, select the original event and download the marks. The map uses the surveyed mark coordinates. The table identifies original rows, nearest sections, distances, crossing sides, datums and quality. Review the source before saving a location role. Check event timing, independence and vertical reference before adopting measurements through the field-table intake. Select an earlier frozen search to replay offline. Registered remote gages show their distance to the outlet and the transfer requirement.

In an isolated checkout run `scripts/p16_release.py <P12 checkout> --live --browser --soquel <P11 checkout>` with the project Python. Omitting the optional arguments checks the original event records offline. The Iowa originals, Soquel project and local receipts stay on the workstation. The receipt is under `status/p16`.

## P14 client handoff and P15 storage

Use an isolated workstation checkout with the P4 Dexter survey, later field return, georeferenced imagery and the configured native tools. For the storage comparison provide another local checkout of commit `8781730`. The driver verifies the old implementation's fingerprints. Substitute the paths to your files and replace `<batch>` with the P14 directory printed at completion.

```powershell
.\.venv\Scripts\python.exe scripts/p14_release.py --survey D:\Dexter\survey --observation D:\Dexter\event_return.csv --imagery D:\Dexter\imagery
.\.venv\Scripts\python.exe scripts/p15_release.py --journey status/p14/<batch>/journey/release.json --reference-root D:\SteadyReach_8781730
```

P14 operates the public project pages, verifies both reports on page one and checks both native results in a detached customer directory. P15 operates the storage estimate, compares full ownership and candidate lists, records the physical volume change during retirement and verifies restored member hashes. The mid-restore fault and one-byte-short batch boundary are controlled test conditions. Receipts are under `status/p14` and `status/p15`. Test copies and native packages stay local.

**Workstation result, 2026-11-26.** At Dexter the revised run was +0.246 ft above the October 2015 observation at RS 500 and 1,540 cfs. Survey uncertainty remains outstanding. Both languages in the detached customer folder matched the selected native run. In the storage scale test, three-sweep median inventories at 1, 24 and 171 editions took 0.073, 0.111 and 0.345 s, compared with 0.147, 0.185 and 0.405 s on the reference implementation. At 171 editions archive plus retirement took 3.180 s (formerly 3.470 s). Restore took 0.622 s (formerly 0.612 s). Timing is workload-specific. The cleanup step freed 15.82 MiB on the test volume. With the new archive retained on the same drive, free space fell by 20.61 MiB overall. After a forced interruption one member had been restored and the remaining 126 were restored on retry. All member hashes matched. The one-byte-short full-pilot rehearsal started zero jobs.

## P11 original measurement intake

Configure HEC-RAS 7.0.1, QGIS and the report converter in a fresh isolated checkout on the acceptance workstation. Supply the completed P10 workspace, the workspace containing the original Soquel edition, and a frozen USGS site 11160000 field-measurements GeoJSON. Save the original response from the [USGS 2024 visits endpoint](https://api.waterdata.usgs.gov/ogcapi/v0/collections/field-measurements/items?f=json&monitoring_location_id=USGS-11160000&datetime=2024-01-01%2F2024-12-31&limit=1000). Replace the three paths in this example.

```powershell
.\.venv\Scripts\python.exe scripts/p11_release.py --p10-workspace D:\P10 --soquel-workspace D:\SoquelSource --soquel-visits D:\FieldData\soquel_2024.json
```

The gate copies the registered cases into the isolated checkout. An automated local browser reviews source rows and runs Washington with the outlet, followed by the interior-observation revision. It verifies both native results and both mapped delivery pairs. Soquel exercises remote gage exclusion. Midway exercises missing inverts and a single-end software rehearsal. The receipt is `status/p11/<batch>/release.json`. Source materials, project editions and generated deliveries stay on the workstation. [Engineer instructions](HYDRAULIC_INTAKE_EN.md)

## P9 distribution, upgrade and queue recovery

Start with the P8 inputs below. Replace `--p8` with `--p9 --p9-fixture <administrator-fixture.json>`. The local fixture identifies the signed release directory (`release`), independently pinned public key (`trusted_key`), base interpreter (`python`), two historic installation directories (`previous_installations`), and the installed `qgis`, `converter` and `runtime` paths. Keep signing keys and project data on the workstation. Inspect the migration and queue receipts under `p9/` and verify the two packages for every recovered calculation. A successful export retry must preserve the original hydraulic run and HDF. [Administrator instructions](OPERATIONS_EN.md)

## P8 team review and recipient scope

Use the P7 command and its frozen inputs below, replacing `--p7` with `--p8`. Inspect `p8/release.json` alongside the overall release record. The test uses separate local browser sessions for a submission and an offline station comment. It follows the returned edition through a new solve, review, selected delivery and withdrawal. Trace the two recipient manifests, both native HDFs and both report languages to the same run. The retained source documents can be inspected in the internal project. [Team review guide](TEAM_REVIEW_EN.md)

## P7 station evidence and flow range

Use the P6 fixtures below and add the frozen USGS field visits. Replace `--p6` with `--p7 --p7-visits <frozen-visit-directory>`. Check the overall release status and the P7 receipt in the same run. It links each modeled comparison to the native output, observation role and station. It also records the displayed limits in both report languages, the two packages, the station map and the offline handoff. Require a separate observation when a disclosed event informs a revised hydraulic input. [Freezing the events and interpreting the results](STATION_EVIDENCE_EN.md)

## P6 intake and offline replay gate

In an isolated checkout on the same workstation, use the full P5 command with `--p6` in place of `--p5`. Retain the independent survey, private Midway fixture, Dexter observation, imagery, archive directory and `--historical-root`. The historical root must contain the registered Soquel source edition and receipt. Require both `status=SOFTWARE_CHECKS_PASSED` and `p6.status=PASSED`. Open `status/release_checks/<run>/p6/release.json` for site-specific gaps and boundary findings, evidence hashes, carried confirmations, browser input counts and the fresh replay run ID.

This gate covers missing Midway inverts, an off-site Soquel gage and the Dexter surveyed reach with a paired event discharge. Geometry returns and independent observation returns are scored separately. Frozen intake reconstruction blocks DNS and socket connections. During a fresh solve from the recovered survey, Python application processes allow only loopback connections. Install the solver and GIS tools beforehand. Human, second-machine and independent engineering acceptance are separate. [Engineering intake guide](HYDRAULIC_INTAKE_EN.md)

**Same-workstation results, November 25, 2026.** All three inventories reproduced their frozen fingerprints offline. The final source tree passed 502 Python checks and 44 page tests. Midway returns were explicitly assumed test values. Dexter discharge and independent stage came from the measured event.

| Site | Acceptance case | Result |
|---|---|---|
| Midway | Missing inverts, wrong datum, partial and complete returns | The intake requested both inverts and barrel length. A wrong-datum return was blocked. A one-end return reopened 1 field and retained 312. A two-end return reopened 2 and retained 311. Zero unchanged hydraulic values were re-entered. |
| Soquel | Off-site gage and detached historical sources | USGS 11160000 matched RS 1700, 714.39 m from the downstream section center. The station lists NGVD29 and the model uses NAVD88. An event-specific transferred stage was unavailable. All 16 frozen objects replayed after removal of the staged original project. |
| Dexter | Measured reach, independent observation return and fresh frozen-input solve | Returning the RS 500 holdout retained all 126 hydraulic inputs. A new HEC-RAS project prepared from the recovered survey and local imagery reproduced 1,540 cfs across nine sections, with maximum stage and discharge differences of 0.000 ft and 0.000 cfs. The Complete package contained 96 files and the Minimal package 20. Both report languages opened with 10 pages each. |

Replay differences compare two native calculations. Dexter's independent stage still lacks measurement uncertainty and its purpose decision remains `NEED_EVIDENCE`. The P6-specific receipt has SHA-256 `f2a68065be4916e14487e5484c8f290340064a0bd7890f899a163c7ffbcae445`.

## P5 baseline on one workstation

On 2026-11-25 the isolated release gate passed 492 Python tests, 44 page tests and the inherited native regressions. It retired and restored two river editions through the browser. While each was archived, HEC-RAS 7.0.1 opened the Complete and Minimal projects from detached copies. QGIS 3.44.15 reopened each Complete project with six valid layers and both exhibit layouts. After restoration, each site generated new paired packages from a fresh native run.

| Edition | Logical MiB | ZIP MiB | Actual MiB gained during cleanup | Net MiB gained including same-drive ZIP | Removed and restored files | Verified files |
|---|---:|---:|---:|---:|---:|---:|
| Dexter | 120.91 | 37.13 | 16.64 | −20.50 | 132 | 468 |
| Big River / Rockford | 88.96 | 25.48 | 14.09 | −11.40 | 121 | 412 |

Across nine station/profile pairs per site, the largest change in native stage was 0.000 ft and in flow was 0.000 cfs. The receiver opened and verified both local handoff entry pages. The detailed local receipt is identified by SHA-256 `20de9ecfe535604a7fd8b365c6cc1d5da66b92756f41e54f077969109b8f0111`. Human and cross-machine acceptance are deferred.

## Archive and recover one edition

1. From **Saved projects**, expand the project family and the edition’s **Manage this version → Storage and recovery by edition**. Select **Inspect edition storage**. The same panel is available from the project page. Logical bytes include referenced inputs. Exclusive and shared bytes add up to logical bytes. Adding totals across editions counts their shared files more than once. Expand the candidate list to see each path.
2. Select **Pin edition** to keep its working files online. A dependent edition, a missing or changed registered original, or a running calculation also protects the project. The two published packages and registered field originals stay at their existing paths. The **Delete project** action in project management moves the entry to the recycle bin and retains its disk usage.
3. Enter an existing local directory outside the checkout and choose **Create verified archive**. Keep the registered ZIP and the checkout’s edition catalog together in your backup policy. A separate drive gives the largest space saving. When using the same drive, inspect the estimated net saving after the ZIP. Archive creation requires temporary headroom up to approximately the uncompressed inventory size.
4. Expand **Release archived working files** and confirm the edition. The program checks the ZIP and current file hashes before deletion. The home page then lists the archived edition in its original project family. Its published handoff opens offline while archived. An interrupted cleanup offers **Resume verified cleanup** or **Restore this edition**.
5. From that family, select **Restore this edition** with the registered drive mounted. The program checks available space, compares existing files, then restores missing members. A conflict shows the path. Preserve independent edits separately and restore the matching bytes before retrying. If the source edition is missing, recover it first. Open the restored edition and use an editable revision for a new calculation. A full-checkout backup remains the recovery path for a lost checkout or archive catalog.

**Same-machine release check.** In an isolated checkout, use the P4 command below with `--p5 --p5-archive-dir <existing-local-directory-outside-checkout>`. The gate includes the P4 cases and exercises two mapped river editions through the storage controls. Inspect `p5/release.json` for bytes before and after, verified members, package checks, native run IDs, and station-level reproduction. Disk-free readings are volume-wide and include other disk activity. Unit regressions cover low space, interruption, inactive or referenced versions, and shared terrain.

The P4 gate includes the complete P3 gate. Add `--p4 --dexter-survey <survey-folder> --dexter-observation <event_return.csv> --dexter-imagery <NAIP-folder> --historical-root <archived-project-checkout>` to the P3 command. The archive contains the original Pagosa and Merced project trees and native evidence. It is read only. Use an isolated checkout for the release run.

Inspect the release manifest and the three receipts under `p4/`. They cover the new-site holdout, wrong-datum / partial / assumed Midway returns, Siletz’s measured-event decision and the station-level historical comparisons. The Dexter receipt records automated interaction counts; live engineer time and second-machine acceptance are separately deferred. [Frozen sources and preparation](../examples/dexter_or/README.md)


Open **Handoff, local files and optional pilot timing** on the project page. Inspect the registered attachments and their inclusion in each package, additional sources, coordinates and PDFs. If a single PDF changes, restore its registered bytes using the button beside its name. The model and other exports keep the same run ID. For older deliveries without an identical copy, restore a verified backup or publish a new edition. Original project files and re-downloadable setup archives appear separately.

To run an actual same-machine release replay with a frozen Siletz review packet, add `--packet <packet_folder> --fresh-benchmark` to the release command. The checker imports the fingerprinted survey into a new project, confirms that its inputs are complete, invokes HEC-RAS, verifies both new mapped packages and compares all station flows and water levels to the frozen HDF. Both packages must trace to the new run. The 0.002 ft / 0.002 cfs reproducibility tolerances apply to repeat calculation with identical inputs. The separate observed-stage investigation threshold remains 0.15 m.

In the map comparison, select a station to see recorded field observations, signed boundary responses and native warnings together. The map initially opens at the largest comparable water-level change. You can keep the first model as the comparison reference, register a survey request at the selected station or create an editable revision using the second model’s verified geometry. The workspace retains the two original calculations.

During a timed pilot, choose engineering work or external waiting, pause when leaving, and record developer assistance as it occurs. Discard an open interval that accidentally includes unattended time. The release checker reads saved intervals directly. Repeated field submissions include deliberate changes as well as re-entry. Native worker time includes compute and extraction.

For a pilot across multiple sites, pass `--cohort sites.json`. Use an object such as `{"Site A":["project_id","revision_id"],"Site B":["other_project_id"]}` with your actual local project IDs. Each site counts once. The release receipt shows the first solver attempt with its original mapped-package outcome, eligible sites and sites with unknown outcomes. It reports the duration of the native compute call separately from the native worker and total machine tasks.

Use this procedure for a Windows workstation with the supported HEC-RAS and QGIS installations. Independent engineering review of a specific site remains a separate decision.

**Before building geometry.** Select the intended use and review the starting information panel. Check the submerged bed, event discharge, survey datum, separate culvert dimensions and inverts, and each required boundary. A gage near the pin may be hundreds of metres from the modeled outlet. Keep the survey, timing, datum, discharge range and transfer basis together. Resolve a conflicting vertical datum or change the modeled scope before computing.

**Compare results.** On the results page open the comparison of model editions and mapped flood edges. Choose two runs for a native geometry comparison, or select a dated WGS84 GeoJSON, KML or KMZ observation. For a multilayer KML select one flood folder. Inspect signed stage changes, native warnings, outer wet limits and overbank shares at the same station. Stage differences require equal discharge, a common vertical datum and center locations within one metre. Edges used to adjust geometry are recorded as such. An unmatched event provides spatial context. Rows with ambiguous or missing crossings stay out of edge statistics.

**Prepare the review.** The report cover identifies the run, intended interpretation and priority sections. The full package includes both reports and layouts. The minimal package includes the matching HEC-RAS result and English exhibit when mapped. To verify a copied pair, run the following from the checkout root.

```powershell
.\.venv\Scripts\python.exe -m ras_workflow.delivery_pair D:\delivery\Complete D:\delivery\Minimal
```

**Back up local data.** Close the SteadyReach server and native editors before writing an offline snapshot. The snapshot contains the projects, data, status and examples directories, including attachments and shared terrain. Its size can be substantial. Choose a new archive outside the checkout. Restore into a new folder, inspect the checksum result and retain the original working data until the restored project opens. The installed software and Python environment are separate.

```powershell
.\.venv\Scripts\python.exe -m ras_workflow.local_backup size
.\.venv\Scripts\python.exe -m ras_workflow.local_backup write D:\Backups\SteadyReach.zip
.\.venv\Scripts\python.exe -m ras_workflow.local_backup verify D:\Backups\SteadyReach.zip
.\.venv\Scripts\python.exe -m ras_workflow.local_backup restore D:\Backups\SteadyReach.zip D:\RestoredData
```

**Same-machine release gate.** Use a dedicated checkout with HEC-RAS, QGIS, PDF conversion, Node.js and Edge or Chrome. The command runs unit and browser checks, then three independent Midway Q100 calculations from the original materials: the initial model, the road-memo revision and a wet-section geometry revision. The browser also downloads an invert worksheet, pauses, and imports an explicitly assumed reply into a separate draft. It compares editions, reopens the baseline, selects the revision and exports the recipient folder. A detached copy must resolve both entry pages and match the selected native HDF and reports. Missing, edited and mixed-edition files must fail verification. A missing private fixture leaves the gate open. For unit checks run `python -m unittest discover -s tests`. Add `--packet <review folder>` for the Siletz and East Fork benchmarks or `--project <id>` for pilot metrics.

```powershell
.\.venv\Scripts\python.exe scripts\release_check.py --midway-fixture D:\ReleaseInputs\Midway\fixture.json
```

**Private fixture.** Keep the manifest and licensed sources together outside Git. Each file entry has a plain `file` name and its SHA-256. `originals` contains four JPGs, the site KMZ and StreamStats PDF. `supplement` is the original roadway DOCX and `brief` is the accompanying site text. `terrain`, `terrain_source` and `aerial` identify the cached USGS DEM, its original receipt with `raster.sha256`, and the corresponding NAIP raster. `picks.inlet` and `picks.outlet` are prior operator interpretations in the DEM projection. The browser marks only those two points. The DEM supplies every exterior anchor and section. `spacing` is the assumed wall gap in feet. Use an aerial covering the entire mapped reach; an optional `aerial_source` entry binds its acquisition receipt to the raster SHA-256. In the child draft, the browser compares the memo and both road profiles, then adopts the six linked inputs together. The nominal width remains conditional for overflow modeling. See `midway.json` and `release.json` under `status/release_checks`.

Machine elapsed time comes from saved task timestamps. Active engineering time, external waiting and developer interventions are unknown unless measured. To include a timed session, pass `--session <json>` with a selected project. Its fields are `project_id`, `intervals` (ordered `kind` of `engineer` or `external_wait` with timezone-aware `started_utc` and `finished_utc`) and `developer_interventions` (list of recorded interventions). An explicit empty list records zero interventions for that session.

During a pilot, **Record a sticking point** captures the page, project phase, edition and topic. **Record developer assistance** adds an intervention. Opening the clock leaves it paused until explicitly started. Automated checks carry no human timing or independent acceptance claim.

After `release_check.py --packet` with the frozen field packet, open `Field_review.md` beside the new release.json. For Siletz the check reselects the withheld event from archived discharge and sensor series and reads the interior station from the native HDF. Its investigation threshold is 0.15 m. For East Fork the check uses a separate event with the previously selected roughness and scores three nonboundary sections. Both exclude the prescribed outlet from accuracy statistics.

Before copying the two packages, the exporter checks free space against known native copies and input snapshots. GIS, reports and temporary files need additional space. Backup restore checks the uncompressed file sizes before extracting. When space runs low, retain the archive and solver outputs, free space on the destination drive or restore the backup into a new folder on another volume.

## Run the P2 gate

In a dedicated local checkout with the supported native tools, supply the private Midway source manifest and the frozen independent field packet. The command creates fresh projects. It checks the Python and page suites, the Siletz baseline and independent revision, and the Midway lifecycle including recipient-side file verification.

```powershell
.\.venv\Scripts\python.exe scripts\release_check.py --p2 --packet D:\ReleaseInputs\Independent_Review --midway-fixture D:\ReleaseInputs\Midway\fixture.json
```

Open `status/release_checks/<run>/release.json`. Check `release_gate`, both software test results, `fresh_benchmark.p2.field` for the fresh interior residual and `midway.json` for the selected inputs, calculated runs and detached transfer. A reproduced calculation may still exceed the observed-stage investigation threshold. `engineering_approval` records the independent review status.

## Required local release gate (P3)

Use the `release.json` written by the command below. Require `release_gate = P3`, `status = SOFTWARE_CHECKS_PASSED`, `p3.status = PASSED`, `midway.status = PASSED` and the linked receipts. P2 and component commands remain available for development checks. Track human and cross-machine qualification separately. The Midway source-folder journey also requires the hashed `aerial_source` receipt for the imagery used to interpret the channel.

Run `python scripts/release_check.py --p3 --packet "<frozen review folder>" --midway-fixture "<private fixture.json>" --transfer-survey "<independent survey folder>"` from the checkout with local HEC-RAS, QGIS, PDF conversion and Chromium configured. Each invocation creates isolated project IDs. Keep original survey files outside the public repository. The transfer survey uses a different site with documented geometry and discharge. The checks read the frozen East Fork holdout, retain the P2 lifecycle and exercise new browser entries for incomplete Midway materials, the Siletz event and the transfer site. Inspect `p3/journeys.json` and both detached reading guides. Software elapsed times exclude engineer effort. Human and second-machine acceptance are tracked separately.

For a repeatable offline export, add `--transfer-imagery "<folder containing Aerial.tif and acquisition.json>"`. The Siletz run uses the hashed NAIP originals in the frozen review folder.

For deeply nested input snapshots, `Complete/Evidence/input_paths.json` maps the original relative path to the shorter copy under `Complete/Evidence/InputFiles` with its byte length and SHA-256. If a Windows browser cannot read a long path, copy the whole handoff folder near the drive root and check that copy.

[Enterprise pilot scope and operator guide](PILOT_EN.md)
