# 俄勒冈州 Dexter 河段实测对比

[English](README.md) | **简体中文**

2026 年 11 月 25 日同机发版验收中，RS 500 计算水位为 599.3010 ft，实测为 599.0555 ft NAVD88，计算减实测为 +0.2455 ft。首次和补资料后的两次原生计算在全部九条断面上水位一致。最终用途判定为 `NEED_EVIDENCE`。自动浏览器记录了 20 次控件点击、14 次主动填值或选取文件，重复主动录入和手改项目 JSON 均为 0。

本例在 USGS 14150000 测站使用一次 2015 年现场测量验证 1D 恒定流。流量 1,540 cfs，共九条断面，测站位于内部 RS 500。主槽和漫滩糙率分别假设为 0.035 和 0.065，下游正常水深坡降由测得的河床高程推算。试点预先约定 0.50 ft 为调查门槛。[冻结方案](protocol.json) · [原始文件哈希](frozen_sources.json)

将地形、水文测量、测站元数据、基准转换和地图底图分别保存为 `tb_43122h71.tif`、`measurements.json`、`gage.json`、`vertcon.json`、`background.tif`。发版验收使用与冻结哈希一致的原件；数据服务更新后另存新版。

- [NOAA Oregon lidar metadata](https://www.fisheries.noaa.gov/inport/item/62797) · [tb_43122h71.tif](https://noaa-nos-coastal-lidar-pds.s3.us-east-1.amazonaws.com/dem/OLC_willamette_river_topobathy_interp_2015_9170/tb_43122h71.tif)
- [USGS field-measurement records](https://api.waterdata.usgs.gov/ogcapi/v0/collections/field-measurements/items?f=json&monitoring_location_id=USGS-14150000&datetime=2015-09-16/2016-01-01&limit=300) · [USGS gage metadata](https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items/USGS-14150000?f=json)
- [NOAA vertical datum conversion](https://geodesy.noaa.gov/api/ncat/llh?lat=43.94568&lon=-122.83729&inDatum=NAD83%282011%29&outDatum=NAD83%282011%29&inVertDatum=NGVD29&outVertDatum=NAVD88&orthoHt=0) · [USGS map background](https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage?bbox=512350,4865250,513750,4866650&bboxSR=6339&imageSR=6339&size=700,700&format=tiff&pixelType=F32&interpolation=RSP_Bilinear&renderingRule=%7B%22rasterFunction%22%3A%22None%22%7D&f=image)

使用项目 Python 执行 `python examples/dexter_or/prepare.py <原件目录> <新建测量资料目录>`，得到测量包及同级的 `event_return.csv`。发版检查中，首次通过首页导入现场流量、地形、来源索引、基准和预定参数。首次原生计算结束后，才通过**导回补测并核对变化**导入实测水位和原件。在独立版本重新计算，逐断面核对水位，同时验证中英文报告和离线交接页引用同一残差。

水尺零点高程为 592.30 ft NGVD29，测站位置的 NOAA 基准改正为 +1.102 m。先将零点换算至 NAVD88，再加水尺读数 3.14 ft。水位测量不确定度仍缺原始说明。本例只验证该次事件。[发版验收方法](../../docs/LOCAL_RELEASE_CN.md)
