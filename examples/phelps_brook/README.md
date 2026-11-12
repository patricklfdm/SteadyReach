# Phelps Brook: first model and report

**English** | [简体中文](README.zh-CN.md) | [Home](../../README.md)

This public USGS field-based model represents Phelps Brook at River Road, Monroe, Massachusetts. The included files are original public **inputs**, not previous solver output. [Source and exact hashes](source.json), [USGS data release](https://doi.org/10.5066/P14HJGZI), version 2.0.

## Run the example

1. Complete [installation](../../docs/WINDOWS_SETUP_EN.md), then open `start_workflow.cmd`.
2. Choose **Existing model** and give it a new name, such as `Phelps first run`. For this first exercise **uncheck GIS** and leave coordinates and flow blank. This produces a native-only delivery and reports without requiring a verified projection or terrain download.
3. Select the four files together from this example's `inputs` folder: `Phelps_River.prj`, `.p01`, `.g01`, `.f01`. Choose **p01** as the intended plan. The original project saves **p04**, which is deliberately not included. The preview must show p01 as selected; do not attempt to load p04.
4. Enter native length unit **US survey foot** and vertical datum **NAVD88**. Native model values are retained; no roughness or flow replacement is needed. Check the preview against the table below.
5. Open **Review all parameters**, review the native inspection and source files, tick the confirmation, then **Confirm and run HEC-RAS**.
6. Wait for Results. Open English/Chinese reports and the Minimal/Complete folders. Both packages come from this new calculation; GIS was unchecked, so this exercise does not produce terrain, aerial imagery or an exhibit.
7. Compare the **1% AEP** profile with [published_reference.json](published_reference.json). The reported source unit is US survey foot; compare unrounded extracted values where available. Do not compare the largest 0.2% AEP profile by mistake.

| Input | Source value |
|---|---|
| Location, WGS84 | 42.72205615, -72.94222811 |
| Plan / geometry / flow | p01 / g01 / f01 |
| Steady regime | Subcritical |
| Profiles, cfs | 10% AEP 203; 4% AEP 291; 2% AEP 369; 1% AEP 456; 0.2% AEP 701 |
| Structure | One circular barrel, 4.5 ft diameter, 65.5 ft long |
| Inlet / outlet invert | 1097.171 / 1091.259, source US survey feet in NAVD88 |
| Downstream normal-depth slope | 0.175, preserved from the source; not a generic recommendation |

## Published comparison values

| Q100 / 1% AEP metric | Published value | Unit |
|---|---:|---|
| RS 189 water surface | 1113.22 | US survey ft |
| RS 110 water surface | 1113.19 | US survey ft |
| RS 42 water surface | 1094.40 | US survey ft |
| RS 14 water surface | 1082.35 | US survey ft |
| Culvert upstream velocity | 18.25 | source ft/s |
| Culvert downstream velocity | 31.15 | source ft/s |

The published precision is 0.01; the reference file records the reproduction tolerance of 0.00501. This is a numerical reproduction criterion, not an engineering accuracy standard. Review unresolved hydraulic warnings even when numbers match.

For mapped work, create a separate project with GIS enabled and the documented native projected CRS, DEM elevation unit and matching vertical datum. Do not infer the native CRS from these coordinates alone. For building a new model rather than importing this one, follow the [no-model guide](../../docs/NO_MODEL_GUIDE_EN.md).
