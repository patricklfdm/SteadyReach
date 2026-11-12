# Third-party materials and external software

**English** | [简体中文](THIRD_PARTY_NOTICES.zh-CN.md)

The [MIT License](LICENSE) covers this application's original code and documentation. It does not relicense the following third-party materials or programs.

| Material | Source and treatment |
|---|---|
| `examples/phelps_brook/inputs/*` and published reference values | USGS, *Hydraulic models and supplementary data for 30 stream crossing sites in Massachusetts*, version 2.0, DOI [10.5066/P14HJGZI](https://doi.org/10.5066/P14HJGZI). The [USGS record](https://www.usgs.gov/data/hydraulic-models-and-supplementary-data-30-stream-crossing-sites-massachusetts-0) marks the release CC0 1.0 Universal. The example retains exact original inputs, archive/member hashes and a separate reference extract. |
| `ras_workflow/templates/MULTCULV.*` | USACE HEC-RAS example-project native input templates, Applications Guide Example 4. Source and original hashes are in the adjacent `manifest.json`. They are model data, not HEC-RAS engine source. See [HEC distribution policy](https://www.hec.usace.army.mil/software/distribution_policy.aspx) and [terms](https://www.hec.usace.army.mil/software/terms_and_conditions.aspx). |
| HEC-RAS and QGIS | Separately installed from their publishers; no installer or engine is included here. HEC-RAS remains subject to HEC terms; QGIS is distributed under its own license. This application is not endorsed by USACE or USGS. |
| Python packages and setup tools | Downloaded at setup from the pinned sources in `requirements.lock.txt` and `scripts/setup_downloads.json`. Python, uv, 7-Zip, Microsoft runtime and LibreOffice retain their own licenses. Download caches/binaries are local and excluded from this repository. |

The interface resource contains inspected method/type signatures for the supported installation; actual installed software is checked at runtime. No private field-study materials, credentials, software installers or historical calculation outputs are included in this source distribution.
