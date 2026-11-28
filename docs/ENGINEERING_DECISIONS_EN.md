# From a model input to an engineering decision

[简体中文](ENGINEERING_DECISIONS_CN.md) · [Getting started](GETTING_STARTED_EN.md) · [Operations](OPERATIONS_EN.md)

## Before a run

Open **Input decisions and field requests** in model preparation. Resolve contradictions first. Expand a group to inspect its fields and open the underlying input, source and candidate values. If a field needs a site record, export its request list. Opening the editor keeps the selected candidate pending. Save the intended values and explicitly confirm the run on the review page.

A field-return edition compares each input with its confirmed parent. The decision list shows affected fields and the number of confirmations carried forward. A return that adds evidence can leave every hydraulic value unchanged. If the parent confirmation cannot be verified, the workflow opens a full review.

## Follow the main issue to an edition decision

In Results, expand **Follow this issue through edition selection** and choose **Track this issue** to bind the question to the source run. Request evidence or pause. Review the returned worksheet and original records, check the affected inputs in a separate revision, then confirm the calculation. Preparation, confirmation and reporting retain the original question and run ID. Identify an unmeasured perturbation as an assumption.

Compare the affected controls and explicitly choose the working revision, retain the previous run or wait for records. Refresh reports and delivery from the existing calculation after choosing a working edition. Open a selected baseline through the edition choice to transfer its files. Quote revision differences only at listed common centers. Added, removed, shifted and unverified stations limit reach-wide comparisons. Engineering review of a mixed-flow reach requires separate upstream and downstream perturbations covering the native sections for each requested profile. Results and the section atlas identify affected locations. Verify the event boundary before citing a sensitive stage.

## After a run

Read **Next engineering decision** on the results summary. The bilingual technical reports and offline handoff include the same advice for the selected evidence snapshot. Refresh the reports and delivery after adding observations or a study. Compare the run identifiers before sending a package.

| What the evidence shows | What to do |
| --- | --- |
| Fewer warnings but a larger absolute error against the same independent reading | Retain the reference for that observation. Verify the datum, geometry and boundary control before selecting the revision. |
| A section-spacing series meets its threshold while an observed stage exceeds the project limit | Check the event time, datum tie and outlet level. Obtain local underwater geometry or flow-split evidence where it can distinguish competing explanations. |
| A revision moves appreciable discharge onto a floodplain and changes water levels | Trace the route across adjacent sections and openings. Check the banks or survey the controlling section before adopting it. |
| Numerical criteria look satisfactory but observations have undocumented accuracy | Limit screening to the registered flows, locations and reach. Request the measurement accuracy before field validation. |

The responsible engineer sets the intended use and its thresholds. Release for design requires a separate engineering decision.

## Workload and support

Under **Reports and maps**, open the pilot timing panel and choose **Show measured workload**. Successful action receipts describe interactions. Repeated confirmations refer to the same recorded confirmation identity. Machine-task time, solver compute time, engineering time and external wait are separate measurements and can overlap. Unrecorded times and historical confirmation identities appear as unmeasured.

Open **Project diagnostics**, or use the button beside a failed request. Preview the category, edition, software fingerprint and registered result identity, then download the JSON if you want to share it. If a returned worksheet belongs to another calculation, download the current worksheet and reconcile the source against its station order and datum. For a QGIS timeout, open **Reports and maps** and regenerate the delivery from the saved hydraulic result. Verify both package manifests and the selected run before transfer.

An administrator can inspect an existing signed upgrade or rollback by running `python scripts/deployment.py support --control <control-folder> --token <migration-token>` with the environment for SteadyReach. This checks the active checkout, registered project inventory and retained backup. Use the [operations guide](OPERATIONS_EN.md) for the actual switch and rollback commands.
