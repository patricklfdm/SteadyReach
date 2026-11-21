# Siletz River observed steady events

[简体中文](README.zh-CN.md)

This Oregon example compares the frozen HEC-RAS reach at RS 44506–34913 with two dated pressure-transducer events. Read [the frozen protocol](protocol.json) before viewing predictions. A run can complete, create both mapped packages, and exceed the investigation threshold for the interior stage observation.

1. Set up SteadyReach on Windows. Create an empty input folder. Download the named files through the USGS catalog landing pages. The 1D archive supplies georeferenced survey sections and the flow-change cards. Extract the single `Terrain/DEM_0104_ft.DEM_0104_ft.tif` from the 2D archive as `released_terrain_ft.tif`. Keep `Siletz_1D_Model.zip` intact. [USGS model release](https://www.sciencebase.gov/catalog/item/66049bced34e64ff15492d45)
2. Save `Calculated Data.csv`, `Site Information.csv` and `Siletz River Surface Water Elevation.xml` alongside the archive. The original pressure series is also available for investigation. The preparation command downloads the approved discharge series from the USGS Water Data V1 API and saves the original pages and checksums in the survey folder. An existing frozen V1 archive or historical discharge.rdb can also be used offline. [USGS continuous observations](https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous) · [Pressure records](https://www.sciencebase.gov/catalog/item/66f43599d34e791ae5dfc34b)
3. For the square printed maps, save the USGS ImageServer response at `CONTEXT_URL` in [the preparation script](prepare.py) as `context_3dep_m.tif`. This supplies topography in missing exhibit cells. The 18 surveyed hydraulic sections remain frozen.
4. From the checkout root run the following, replacing `D:\Siletz\raw` and the new output directory as appropriate.

```powershell
.\.venv\Scripts\python.exe examples\siletz_or\prepare.py D:\Siletz\raw D:\Siletz\raw\released_terrain_ft.tif D:\Siletz\survey --profile Holdout --context D:\Siletz\raw\context_3dep_m.tif
```

5. Start SteadyReach. Choose the river survey-package route, enable GIS delivery, and select `survey.json` and every file named in its `files` table. Review the 18 sections, the known downstream stage, the observed gage discharge multiplied by the documented reach/gage ratio, and fixed channel/overbank n of 0.035/0.065. Confirm the inputs and run. The fresh plan HDF supplies every reported water level.
6. To reproduce the boundary rejection, prepare a second package in another empty directory with both events by omitting `--profile Holdout`. The low-flow imposed outlet is below critical elevation for the selected geometry and regime. Retain the failure record. Assess the independent event on its original threshold of 0.15 m, excluding the imposed outlet. [USGS study and table 14](https://pubs.usgs.gov/publication/sir20255063/full)

The packet generator [review.py](review.py) accepts saved run receipts, the East Fork holdout record, and a new output folder. It verifies original survey hashes, independently selects observation windows, reads the native HDF, checks package membership, records failed attempts and produces bilingual reading guides with portable evidence.
