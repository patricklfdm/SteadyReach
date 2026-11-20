# Siletz 河实测恒定流事件

[English](README.md)

本例使用俄勒冈州 RS 44506 至 RS 34913 河段，核对冻结几何在两次实测事件中的水位表现。先读[事先约定的事件与误差规则](protocol.json)。留出事件可生成完整包和最小包，其内部测点偏差仍可能超过调查门槛。

1. 在 Windows 安装 SteadyReach，准备一个空的原始资料目录。从 USGS 目录下载 1D、2D 两份模型压缩包，保留原始 `Siletz_1D_Model.zip`。从 2D 包中提取唯一的 `Terrain/DEM_0104_ft.DEM_0104_ft.tif`，在资料目录存为 `released_terrain_ft.tif`。1D 包提供已定位的测量断面与流量变化记录。[USGS 模型发布页](https://www.sciencebase.gov/catalog/item/66049bced34e64ff15492d45)
2. 把 `Calculated Data.csv`、`Site Information.csv` 和 `Siletz River Surface Water Elevation.xml` 存入同一目录。USGS 同时提供原始探头记录。将 15 分钟流量响应保存为 `discharge.rdb`。[水位和测站资料](https://www.sciencebase.gov/catalog/item/66f43599d34e791ae5dfc34b) · [流量查询](https://nwis.waterservices.usgs.gov/nwis/iv/?format=rdb&sites=14305500&startDT=2017-09-27&endDT=2018-07-31&parameterCd=00060&siteStatus=all)
3. 制作方形展图时，将[准备脚本](prepare.py)中 `CONTEXT_URL` 返回的 USGS 地形另存为 `context_3dep_m.tif`。它补充展图背景的空值，水力运算仍使用 18 条冻结的调查断面。
4. 在仓库根目录运行以下命令。按实际位置替换原始资料目录和新的输出目录。

```powershell
.\.venv\Scripts\python.exe examples\siletz_or\prepare.py D:\Siletz\raw D:\Siletz\raw\released_terrain_ft.tif D:\Siletz\survey --profile Holdout --context D:\Siletz\raw\context_3dep_m.tif
```

5. 启动 SteadyReach，选择河道测量资料包入口，启用 GIS 交付，选择 `survey.json` 及其 `files` 表列出的全部文件。核对 18 条断面、下游已知水位、测站流量至河段的折算、主槽糙率 0.035 和漫滩糙率 0.065。确认后运行。水位须从本次新生成的原生方案 HDF 提取。
6. 复现边界拦截时，在另一空目录准备两个事件，命令去掉 `--profile Holdout`。低流量工况要求的出口水位低于该几何和流态下的临界水位，应保留失败记录。用原定的 0.15 m 调查门槛评估留出事件，排除已作为边界使用的出口测点。[USGS 原研究与表 14](https://pubs.usgs.gov/publication/sir20255063/full)

[复核材料生成脚本](review.py)接收已保存的运行记录、East Fork 留出事件记录和一个新的输出目录。它核对原始资料指纹，重新从观测表选取时间窗口，读取原生 HDF，核对交付包文件，并将失败尝试与成功运行一并列入双语复核说明。
