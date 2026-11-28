# Candidate installation and incident handling

[简体中文](CANDIDATE_CN.md) · [Installation, verification and rollback commands](OPERATIONS_EN.md) · [Pilot worksheet](FIRST_PILOT_EN.md)

**Deployment target.** Local Windows x64, Python 3.12.14, the inspected HEC-RAS 7.0.1 US customary adapter, QGIS 3.44 LTR and the configured LibreOffice converter. Native warning/group table export needs the supported English desktop session and clipboard. Stage a candidate alongside the current installation. Keep workstation configuration and signing credentials outside the candidate ZIP.

**Transfer to IT.** Supply the signed release directory with RELEASE.json, RELEASE.sig, the source and wheel archives, SBOM and licenses. Obtain the public-key fingerprint separately from the release administrator. Verify before installing, bind the local tools, then exercise the two project templates and validate a retained client package. Use the manifest commit to identify this build in every support ticket.

| Incident | First response | Evidence for restoration |
| --- | --- | --- |
| Offline or source unavailable | Use frozen inputs when available. Retain a missing source and resume when supplied. | Source fingerprint and selected event, units and datum agree. |
| Insufficient workspace | Inspect the storage estimate, keep the approved parent and identified outputs, change archive volume or free scratch. | The reserve check passes before a new job starts. |
| Native export unavailable on a locked or unavailable desktop | Resume the interactive export on a supported signed-in desktop. | Original native run and HDF still match. Missing tables remain unknown until verified. |
| QGIS/PDF export timeout | Reopen the saved calculation and retry delivery. | Both package manifests, the matched run and expected reports verify. |
| Upgrade regression | Preserve work added to the candidate. Switch back with the registered migration token. | The prior installation reopens its own project and package hashes. |

**Support ownership.** The pilot organization nominates a workstation administrator, hydraulic lead and release maintainer before rollout. The administrator handles installation and recovery, the lead approves project use, and the maintainer triages reproducible software failures. Review the local support JSON before sharing. Send customer materials only through an approved private channel. Record the affected build, severity, attempted recovery, owner and outcome. Agree support hours, patch response and end of support before production rollout. Respond to dependency advisories by checking the pinned SBOM, assessing impact, issuing a separately signed replacement and rehearsing rollback. Customer qualification, independent engineering approval and a contractual response time are open until separately agreed.
