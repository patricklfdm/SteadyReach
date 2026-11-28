# Install a verified release and recover a queue

[简体中文](OPERATIONS_CN.md) · [Local release checks](LOCAL_RELEASE_EN.md) · [Project diagnostics](ENGINEERING_DECISIONS_EN.md)

## Estimate disk space before a batch

On a completed edition, open **Storage and recovery by edition → Inspect edition storage**. Enter the archive directory, expand **Estimate space for similar runs**, enter the number of comparable editions and select **Estimate peak space**. The result shows the working-volume peak, archive allowance, restore reserve and shortage on each drive. The estimate allows one retained copy per edition, one temporary copy for serial work and one restore. For larger terrain, choose a larger representative edition.

Before starting the fixed 26-job P10 acceptance run, the launcher writes `capacity.json`. It budgets the measured 7,147,333,505-byte working peak, 66,153,326 bytes of archives and 18,061,750 bytes to restore one edition. On a shared volume all three are added. If space is insufficient, `release.json` records `LOW_SPACE` and zero started jobs. Free space or choose another archive drive, then retry. An interrupted restore can resume from the same registered archive.

Use this procedure to administer a single Windows workstation. The normal project entry point remains `start_workflow.cmd`. Close applications using the two project installations before switching versions. Keep project data, the release distribution and the migration backup in separate directories.

## Install from the offline bundle

Obtain the release directory and the administrator's independently pinned public key. Run these commands from a trusted SteadyReach checkout. Replace the example paths with the locations on the workstation. The release contains application source, the locked Windows wheels, an SBOM with component versions and hashes, and the project and dependency license inventories. Provide Windows x64 Python 3.12.14, registered HEC-RAS, QGIS LTR, LibreOffice and the pinned Microsoft solver runtime locally.

```powershell
$Tool = 'D:\SteadyReachAdmin\.venv\Scripts\python.exe'
$Release = 'D:\Releases\SteadyReach'
$Key = 'D:\Trust\SteadyReach.pub.xml'
$Candidate = 'D:\Applications\SteadyReach_candidate'
$BasePython = 'D:\Runtimes\Python312\python.exe'
& $Tool scripts/software_release.py verify --release $Release --trusted-key $Key
& $Tool scripts/software_release.py install --release $Release --trusted-key $Key --destination $Candidate --python $BasePython
& "$Candidate\.venv\Scripts\python.exe" "$Candidate\scripts\bind_release_tools.py" --installation $Candidate --qgis 'D:\Applications\QGIS-LTR' --converter 'D:\Applications\LibreOffice\program\soffice.exe' --runtime 'D:\Runtimes\msvcr100.dll'
```

Verification prints the signed Git commit. Stop on an error. The installer checks the signature and every artifact, creates the environment in the final application path, installs from the supplied wheel bundle and runs `pip check`. The tool-binding command tests the registered solver, QGIS Python and PDF converter and records the selected components in `INSTALLED_TOOLS.json`. If installation stops halfway, keep the diagnostic output and repeat with a new destination. Only completed installations can be promoted.

## Move projects and select the installation

The previous installation needs a working local Python environment. Keep any external archived project editions connected. Select an unused backup path and a control directory outside both installations. Use the same paths when resuming an interrupted preparation.

```powershell
$Previous = 'D:\Applications\SteadyReach_previous'
$Control = 'D:\SteadyReachAdmin\active'
$Backup = 'D:\Backups\previous_projects.zip'
$Migration = & $Tool scripts/deployment.py prepare --previous $Previous --candidate $Candidate --control $Control --archive $Backup --release $Release --trusted-key $Key
if ($LASTEXITCODE -ne 0) { throw 'Migration preparation failed' }
$Token = ($Migration | ConvertFrom-Json).token
& $Tool scripts/deployment.py switch --control $Control --token $Token
& $Tool scripts/deployment.py open --control $Control
```

Preparation verifies the backup, the migrated files, source attachments, native results and available delivery pairs with each version's own project reader. Switching updates the administrator's active-installation pointer. Open the service through the control command to use that pointer. After closing the candidate, use `rollback --control $Control --token $Token` in place of `switch` to select the previous installation. Work created after switching remains in the candidate directory. Preserve that work separately when rolling back.

## Recover a queued job

Use the same specification and output directory for each retry. The specification uses project paths relative to the checkout and a unique job ID per entry. In the examples below, `$Queue` names the queue JSON file and `$Output` its output directory inside the checkout. Run commands with the current installation's Python from that installation.

```powershell
$Queue = 'status/operator/queue.json'
$Output = 'status/operator/jobs'
& $Tool workflow.py queue-run --queue $Queue --output $Output
& $Tool workflow.py queue-status --output $Output
& $Tool workflow.py queue-cancel --output $Output --job reach_a
& $Tool workflow.py queue-resume --output $Output --job reach_a
& $Tool workflow.py queue-run --queue $Queue --output $Output
```

For a running queue, send the cancellation from another terminal. Resume clears the operator's cancellation request. Run the queue again to process outstanding work. On insufficient space, free space or wait for another reservation, then retry. An optional positive integer `reserve_bytes` on the job requests more space for large terrain. A completed solver result with a failed export can be reused once the blocking file is closed or the export tool is available. An interrupted solver receives a new solve. Each attempt records the status, stage durations and native run identity. Completed jobs with matching inputs and intact evidence are skipped.

## Preview a support bundle

```powershell
$Preview = & $Tool workflow.py queue-support --output $Output | ConvertFrom-Json
$Preview.preview | ConvertTo-Json -Depth 8
& $Tool workflow.py queue-support --output $Output --save 'D:\Support\queue_support.zip' --preview-token $Preview.token
```

The default bundle contains numbered attempts, statuses, stage durations and native reuse flags. Its preview token binds the data actually exported. Use a new filename for each support archive. Field files, paths and log text stay on the workstation.

## Prepare a distribution

On the release workstation, protect the signing identity under the Windows account responsible for releases. Keep the private key out of the release directory and Git. Publish the public-key fingerprint through an independently trusted channel. Build from a specific committed revision and an inventory of Windows wheels that exactly matches `requirements.lock.txt`.

```powershell
powershell -NoProfile -File scripts/release_signature.ps1 -Action create-key -PublicKey D:\Trust\SteadyReach.pub.xml -PrivateKey D:\Signing\SteadyReach.dpapi
& $Tool scripts/software_release.py build --revision $Commit --version $Version --wheels $Wheels --private-key D:\Signing\SteadyReach.dpapi --trusted-key D:\Trust\SteadyReach.pub.xml --output $NewRelease
```

Generate a key only when establishing a new signing identity. Keep its fingerprint and access policy with the organization’s release records. The local signature authenticates the manifest against that key. Vendor software and workstation qualification follow their own deployment and acceptance processes.
