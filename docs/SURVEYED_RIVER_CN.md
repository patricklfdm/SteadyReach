# 导入实测河段

[English](SURVEYED_RIVER_EN.md) | **简体中文** | [用户手册](USER_GUIDE_CN.md)

这条路线适用于有完整测量与地理坐标、河段内不建结构物的项目。测量或 GIS 人员先整理一次资料包，随后工程师可直接从普通项目页面导入和修改。只有零散资料或地表 DEM 时，仍可从坐标起步。

## 打开已有资料包

1. 首页「起始资料」选择「已整理的实测河道资料包」，填项目名称。一次选中 `survey.json`、实测地形 GeoTIFF 或工程裁剪版，以及清单所列的全部来源。单文件最多 15 MB，合计最多 50 MB。
2. 点击「准备项目」。程序核对文件名、SHA-256、投影、场地在栅格中的位置、高程单位、断面顺序、流量和水力输入。错误会指出应更正的字段或来源。工程单独保存一份原件。
3. 在模型页核实河线、实测河床覆盖、岸站、糙率、事件流量与尾水。集中核对完整参数后启动真实计算。工况名称和流量取自本包。
4. 在结果页核对原生水位、警告及制图。导入另一场洪水的观测 CSV 时，填写事件日期、同期实测流量、单位、基准、位置及测量不确定度。下游已知水位选边界角色，未参与校准的内部点选留出检验。比较前锁定糙率和几何。用同一计算版做上下限边界与全河段连续两级加密，保存两种制图交付包。

## 整理资料包

准备一份 UTF-8 的 `definition.json`，按下表填写。测量、插值、校准与经验假设分别保留原始依据。

| 对象 | 内容 |
|---|---|
| `location` | 栅格范围内的 `latitude` 与 `longitude`，WGS84 十进制度。 |
| `terrain` | `raster` 为 GeoTIFF 文件名，`vertical_datum` 为高程基准，`vertical_unit` 选 `m`、`US survey foot` 或 `international foot`。采用与断面相同投影的单波段栅格，最多 1600 万像元。裁剪或拼合数据时附原始来源及处理说明。 |
| `geometry` | `schema_version` 为 `1.0`，`model_type` 为 `river`，`hydraulic_unit` 为 `international_ft`。给出 `river`、`reach`、投影 `horizontal_crs`（EPSG 或 WKT）、`vertical_datum`、`flow_regime`。河床依据 `channel_geometry_basis` 选 `surveyed_channel` 或 `combined_survey_and_dem`。在 `flowlines` 中给出唯一一条由上游至下游的河线，含 `id` 和投影坐标数组 `xy`。 |
| `geometry.cross_sections` | 4–500 条断面。填写向下游递减的数字站号 `rs`、中心 `center_xy`、面向下游从左至右的断面线 `cutline_xy`、桩距 `station_ft`、高程 `elevation_ft`、落在采样桩距的两岸值 `bank_stations_ft`、到下一断面的三条流程长度 `reach_lengths_ft`（左／主槽／右，末断面均为零）、扩散和收缩系数 `expansion_contraction`（按此顺序）。XY 使用投影原单位，水力数组用国际英尺。岸站、流程和损失系数的判读写入附件。 |
| `geometry.boundaries` | 给出该流态所需的边界。正常水深用 `type: normal_depth`，正坡降写在对应侧 `boundary_slopes`。下游已知水位用 `type: known_stage`，`stages_ft` 按工况顺序填写本模型基准下的绝对水位。附日期、水尺零点及来源。 |
| `scenario` | 小写 `id`、`channel_n`、`overbank_n`、糙率依据 `parameter_source`，以及 `profiles`。每个工况给出独立简短的 ASCII 名称 `id`、正流量 `flow_cfs` 与 `source`。注明流量与测量日期及选定糙率的事件。 |

将下列命令中的路径和说明换成真实资料。在仓库根目录的 PowerShell 中运行一次，原件与定义文件放在同一文件夹。每份原件单列一个 `--source`。工具会生成并验证含 SHA-256 的 `survey.json`。同一目录已有清单时，先将其存档，或在新文件夹准备下一版。

```powershell
.\.venv\Scripts\python.exe -m ras_workflow.survey_import .\field\definition.json --source .\field\bed.tif "测量日期、单位、高程基准和提供方" --source .\field\field_notes.pdf "测量方法、水尺零点和现场测量不确定度"
```

栅格可能同时包含实测和插值区域。独立事件用水面高程或已换算为同一基准的水尺读数校核水位；河床测点用于核对几何。下游强制水位从独立误差统计中排除。来源缺少测量不确定度时留空，页面会分别列出缺精度和偏差超过精度的测点数，并指出待复核测点中偏差最大的位置。同一事件重复计算时，观测数只统计一次。
