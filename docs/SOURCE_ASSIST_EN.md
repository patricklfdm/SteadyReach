# Find and use source material

**English** | [简体中文](SOURCE_ASSIST_CN.md) | [No-model guide](NO_MODEL_GUIDE_EN.md)

The Model page combines public-source lookup, document import, parameter candidates and survey-map inspection. No AI account or reviewer-name form is required. The original documents and extraction record are kept locally and included in the calculation's provenance.

## The usual sequence

1. Create a project with coordinates. Preparation attempts USGS terrain and public source discovery. Existing projects use **Find available data automatically / Retry public search + analyze**. During processing, the phase and file counter are shown; keep the launcher open.
2. Expand **Public search coverage and attempts** to distinguish a matching record from a timeout, unsupported provider, or failed download. A catalog footprint can cover a whole state; a search hit alone is not a verified crossing.
3. Add available PDFs, photos or CSV files with **Save and extract selected files**. For an already downloaded survey, paste its **single-site folder** into **Import this folder and analyze**. Subfolders are read automatically; no QGIS import is needed just to inspect points. The app copies supported documents without changing originals, skips native models and deduplicates identical content. Limits are 15 MB/file and 100 files/100 MB per folder.
4. Read the document/candidate/point counts. Open **Original documents and extracted text** to compare recognized text with the original. Failed extraction does not delete the source or stop other documents. Handwriting/OCR values are unverified estimates, never surveyed measurements.
5. Use **Find a parameter / missing item** to filter required missing fields, source conflicts, candidate fields or all parameters. Selecting a field opens its collapsed group. Each field's source details show its acquisition route, attempted operations and next useful input.
6. Adopt an applicable candidate or edit the current value. Existing input is never overwritten by discovery. Only one consistent Q100 inventory value from a single supported site within 25 m can fill an empty flow field automatically; it remains a source-reported regional estimate requiring final review. Other dimensions, assumptions and text matches require explicit selection. A different source value is displayed as a conflict, not silently reconciled.
7. Check map/sections and remaining engineering inputs. Open **Review all parameters**. Missing-input errors, assumptions and the full editable list are grouped/collapsed. Expand the relevant groups, then make the one final confirmation before HEC-RAS runs. New source interpretation or modified files invalidate earlier confirmation.

## Current automatic routes and limits

| Information | Implemented route | Remaining decision |
|---|---|---|
| US terrain and metadata | Existing USGS DEM query/download, CRS and vertical metadata candidates | Site extent, vertical interpretation and terrain suitability |
| Public site information | Bounded ScienceBase search; coordinate match against the USGS Massachusetts 30-crossing inventory (release DOI 10.5066/P14HJGZI) | Confirm the same crossing/event; coverage is not nationwide parameter extraction |
| Survey documents | Selective ZIP reads for the matched site when the official endpoint supports public range access | The public catalog form is used, not the authenticated File Manager URL; a CAPTCHA pauses automatic download and leaves local import available |
| Q100 | Supported inventory PK1AEP; explicitly labelled Q100 + cfs or m³/s in text/PDF/OCR | Applicable hydrology and event; no discharge estimated from DEM |
| Other parameters | Explicit field/value CSV for every current field; labelled channel/bank roughness, barrel length and road width in text | Verify site/group and units; arbitrary prose is not a reliable structured model |
| Survey XYZ | CSV column inference or user column mapping; projected-coordinate transform into the DEM map | CRS/units/datum; descriptions such as CROWN, CH or ABUT require feature interpretation |
| Survey control | Two matching OPUS NAD83(2011), Massachusetts Mainland, NAVD88 control rows can propose EPSG:6492 and US survey feet after a 0.03 m consistency check | This specific recognizer is not a general CRS solver; other surveys need explicit metadata |
| Length/span/road width | Plan distance between two user-identified survey endpoints, converted to international feet | Feature identity, wall thickness, skew and difference from hydraulic length |
| Invert | One user-identified invert point with matching datum, converted to international feet; existing conditional DEM alternatives remain available where applicable | Interior invert identity; a crown is not automatically converted to an invert |
| Road, sections and banks | Explicit road/flow lines, DEM sampling, geometry QA and bank candidates | Flow direction, overtopping crest, submerged terrain and uncertain bank positions |
| Boundary/roughness/losses | Existing terrain slope candidates and referenced engineering ranges; explicit CSV/text inputs | Hydraulic applicability and sensitivity; ranges are not site confidence intervals |

The catalog search is not an exhaustive Internet search. `No extracted value` means these supported attempts did not yield an unambiguous usable value. It does **not** mean no data exists online. Municipal PDFs, drawings, additional inventory schemas and photographs may still need an engineer's interpretation. Authentication and Windows security settings are not changed automatically.

## Survey map and point identification

Expand the survey card. If a coordinate candidate is available, inspect its basis. Otherwise select the X/Y/Z/point/code columns and enter the documented projected CRS, elevation unit and datum; choose **Use this coordinate / column interpretation**. Do not guess EPSG codes from plausible-looking coordinates.

In **B · DEM, sections and banks**, load the DEM. Survey points appear with point IDs, codes, original elevations and datum. Zoom in before choosing closely spaced points. With no reach-picking mode active, clicking a point or focusing it and pressing Enter adds its ID to the survey selection. With a reach/road picking mode active, the point supplies an exact map anchor instead.

In the survey card's point table, choose the target field. Select one actual invert point, or two endpoints for a dimension. **Create candidate from identified points** computes a candidate; it does not adopt it. Compare it with current and inventory values before selecting it. Crown subtraction, inlet-only sediment and a uniform blockage depth are not interchangeable assumptions.

The survey CRS is separate from the model/DEM CRS. Plan coordinates can be transformed for display, but no automatic vertical datum transformation is performed. An invert candidate needs a model elevation datum that matches the survey datum. Model hydraulic elevations are international feet; original survey values/units remain visible.

## Optional structured parameter import

Download the blank **parameter CSV template** from the import card. It lists the current project's field keys and required units. Fill only values actually available. Do not invent missing rows to make the file complete.

Columns are `field,value,unit,datum,evidence_class,source`. Use the exact displayed unit, including `Manning n`; dimensionless text/settings leave unit blank. Arrays/matrices use JSON inside properly quoted CSV cells. Elevation/invert rows require a datum matching the current model. Use `assumed` for conditional assumptions; other rows are treated as source-reported, not independently verified. Empty values are ignored; unsupported fields, malformed numbers and mismatched units are reported. Add the needed opening groups first so their fields exist, then download a fresh template.

Import the completed CSV through the same source card. Values become reviewable candidates rather than silently replacing your draft. This is optional: normal source lookup, direct editing and survey/map selection remain available.

## When something fails

- **Network timeout:** saved local documents are still parsed. Retry public search later; no missing-value default is inserted.
- **Public download / File Manager:** open the [USGS catalog page](https://www.sciencebase.gov/catalog/item/6a6266c11ba49bb7d9d0603a), find **Attached Files**, and click **Field-Based Hydraulic Model Survey Data.zip**. The catalog download uses a public form. `/manager/item/.../file/...` is a separate File Manager page and must not be described as an anonymous direct download. You do not need a File Manager account for the public route. If a CAPTCHA appears, complete it yourself in the browser, then extract and import the single-site folder. SteadyReach detects the verification page and pauses that download; it does not solve or bypass it, request credentials, or silently download the full archive.
- **OCR unavailable / no readable text:** open the retained original and supply the necessary interpretation. OCR uses installed Windows languages; it does not install language packs or relax script policy.
- **Unknown CSV columns:** use the dropdown mapping. Raw survey columns are not interpreted as model parameters.
- **Values differ:** inspect source date, interior/exterior dimensions, opening group, units and datum; explicitly select or edit the intended value.
- **Missing critical input:** leave it unresolved or choose an explicitly conditional estimate supported by site evidence. The solver remains paused until the final input gate and confirmation pass.
