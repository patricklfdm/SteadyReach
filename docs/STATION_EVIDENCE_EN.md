# Checking a modeled stage against field evidence

[简体中文](STATION_EVIDENCE_CN.md)

Before calculating a river edition, open the project purpose and delivery conditions. Enter the event identifier as it appears in the field record, its date, modeled profile, river station, comparison role, maximum stage error in feet and the basis for that tolerance. Add each station event and save the conditions. Choose an interior measurement independent of the inputs for a holdout. A measurement used as a boundary or for calibration has its own role.

Calculate the reserved profile. When the measured stage arrives, use the field return to make a separate edition. Check the event, location, flow, units, vertical reference and measurement uncertainty. In the computed section review, open **Support by station and flow**. Select the profile to see the signed error (modeled minus observed), number of independent events and measurements, and the worst matching station. Both report languages use the same bound results.

The local decision also considers native warnings, wet ends, changes in overbank flow share, and verified boundary, roughness and section-spacing comparisons. Spacing uses successive refinements within the tested intervals. A stage error larger than the specified limit needs investigation. Missing uncertainty leaves support pending even when the numerical difference is small. A point can satisfy the observation test while its sensitivity or native QA still needs work. Use findings only for the tested flow and station. Once a disclosed event is used to revise hydraulic inputs or its comparison conditions, reserve another independent event for the revision.

## Reproducing the test

Run the selector once with internet access and keep the complete output folder. The protocol is fixed before downloading field visits. Repeating the command with `--offline` reads the saved responses and verifies their fingerprints.

```powershell
python examples/oregon_holdouts/select_visits.py status/oregon_visits
python examples/oregon_holdouts/select_visits.py status/oregon_visits --offline
```

For the local release gate, use the [P6 fixtures](LOCAL_RELEASE_EN.md) and replace `--p6` with `--p7 --p7-visits status/oregon_visits`. The receipt is under `status/release_checks/<run>/p7/release.json`. The McKenzie and Willamette records contain paired field discharge and relative gage height. A matching interior section and vertical tie must be demonstrated before scoring stage. The historical Merced and Pagosa checks use their own preserved native results. [McKenzie River near Vida](https://waterdata.usgs.gov/monitoring-location/USGS-14162500/) · [Willamette River at Harrisburg](https://waterdata.usgs.gov/monitoring-location/USGS-14166000/)
