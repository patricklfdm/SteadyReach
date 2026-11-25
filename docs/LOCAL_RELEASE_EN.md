# Local production review

[简体中文](LOCAL_RELEASE_CN.md) · [Production priorities and acceptance criteria](PRODUCTION_ROADMAP_EN.md)

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
