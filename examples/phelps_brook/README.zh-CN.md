# Phelps Brook：首次计算与报告

[English](README.md) | **简体中文** | [首页](../../README.zh-CN.md)

这是 USGS 公开的 Massachusetts 州 Monroe 镇 River Road 处 Phelps Brook 实测模型。内附文件是公开原始**输入**，不是旧计算结果。见[来源和准确哈希](source.json)、[USGS 数据发布](https://doi.org/10.5066/P14HJGZI)，版本 2.0。

## 操作步骤

1. 完成[安装](../../docs/WINDOWS_SETUP_CN.md)，打开 `start_workflow.cmd`。
2. 选择**已有模型**，名称可填 `Phelps first run`。首次练习**取消 GIS**，坐标和流量留空，以便无需确认投影或下载地形即可生成原生模型包和报告。
3. 同时选择本示例 `inputs` 文件夹里的 `Phelps_River.prj`、`.p01`、`.g01`、`.f01`。明确选择目标方案 **p01**。原 `.prj` 保存的是 **p04**，本例没有提供 p04；预览必须显示已选 p01，不要加载缺失的 p04。
4. 原生长度单位选择 **US survey foot**，高程基准填写 **NAVD88**。保留原生模型数值，无需另改糙率和流量，按下表核对预览。
5. 点击**核对全部参数**，检查原生输入和来源文件，勾选确认，再点**确认并运行 HEC-RAS**。
6. 等待结果，打开中英文报告及 Minimal／Complete。两个包均来自本次新求解；本练习取消了 GIS，因此不含地形、航片或展示图。
7. 将 **1% AEP** 工况与 [published_reference.json](published_reference.json) 比较，使用源单位 US survey foot，尽量比较未四舍五入的提取值。不要误选最大的 0.2% AEP 工况。

| 输入 | 来源值 |
|---|---|
| WGS84 坐标 | 42.72205615，-72.94222811 |
| 方案／几何／流量文件 | p01／g01／f01 |
| 恒定流流态 | Subcritical，缓流 |
| 工况流量，cfs | 10% AEP 203；4% AEP 291；2% AEP 369；1% AEP 456；0.2% AEP 701 |
| 结构 | 1 孔圆管，直径 4.5 ft，长 65.5 ft |
| 进口／出口涵底 | 1097.171／1091.259，源单位 US survey foot，NAVD88 |
| 下游正常水深坡度 | 0.175，保留原始模型值，不是其他场地通用建议 |

## 公开对比值

| Q100／1% AEP 指标 | 公开值 | 单位 |
|---|---:|---|
| RS 189 水位 | 1113.22 | US survey ft |
| RS 110 水位 | 1113.19 | US survey ft |
| RS 42 水位 | 1094.40 | US survey ft |
| RS 14 水位 | 1082.35 | US survey ft |
| 涵洞上游流速 | 18.25 | 源 ft/s |
| 涵洞下游流速 | 31.15 | 源 ft/s |

公开数据保留到 0.01，参考文件记录复现容差 0.00501。这是数值复现判据，不是工程精度标准；数值一致时仍要复核水力警告。

需要地图时另建开启 GIS 的项目，填写资料明确的原生投影 CRS、DEM 高程单位和匹配的高程基准，不能仅从经纬度猜原生投影。若希望从零建模而非导入示例，请参阅[无模型指南](../../docs/NO_MODEL_GUIDE_CN.md)。
