# 本机生产复核

## P20 新河段留出事件核验

使用独立的 Windows 检出目录及已配置的 HEC-RAS 和报告转换器。按 `examples/enterprise_pilot/big_river_sources.json` 的文件名将 USGS 原件存入 `status/p20_sources`，保留压缩 DEM 和原始 CSV。以下命令会核对九个原件的 SHA-256。验收目录应为本次新建，放在当前检出目录内。开始前留出原生结果、报告和归档所需的空间。

```powershell
python scripts/p20_release.py freeze --raw status/p20_sources --out status/p20/new_cohort
python scripts/p20_release.py forecast --raw status/p20_sources --out status/p20/new_cohort
python scripts/p20_release.py score --raw status/p20_sources --out status/p20/new_cohort
python scripts/p20_release.py archive --raw status/p20_sources --out status/p20/new_cohort
```

第一步仅读取平面坐标和实测地形，登记事件、行号、角色和标准。出口与内点分开。第二步先读取出口，按冻结的工况实算两级间距；中断时重复 forecast 可以沿用完整的单次计算回执。第三步先核对两处河段、全部工况和原生 HDF，再读取内点列，保存每个误差和未满足的条件。第四步从已有原生结果生成两处河段各自的完整和最小原生交付包，回读校验归档。打开 `P20_blind_validation.zip`，从 `START_HERE.txt` 和 `scores.json` 开始。包内包含两级原生模型、完整包的双语报告、USGS 原件；本项核验采用原生交付模式。各事件数值及用途见[实测结果](PRODUCTION_ROADMAP_CN.md)。

## P19 恒定流方法适用性

在可编辑河段的可行性检查中打开「用 USGS 流量过程核对恒定流假设」。选择工况、UTC 事件日期和该测站的 USGS 连续流量 GeoJSON。页面检查测站、单位、批准状态、分页、事件日缺口和接近模型流量的最长连续时段。确认测站与河段的联系，结合传播时间判断用途。计算后的结果页、双语报告和收件说明还会标出边界影响到的断面、版本间漫滩输水变化及应采用其他水力方法的情形。

`python scripts/p19_release.py --hydrograph <Turkey_2016.json> --archive <project-workspace> --p17 <P17-release.json>`

## P18 按位置索取历史测量原件

计算完成后进入 **复核 → 导回补测并核对变化 → 按位置索取历史测量原件**。填可用测量日期范围，如需额外测线可填 RS，下载 ZIP。GeoJSON 使用 WGS84 经纬度，各要素列明模型高程基准。模型中心仅标明搜索位置，原始水位应按真实坐标及时间导入。回传剖面时填写包内 CSV，附原件、实测日期、方法和精度（ft，未知留空）。水位则走原始测量表入口。回传进入独立修订；历史时段以外的调查另立对应年代版本。

在包含 P17 实算的隔离目录运行 `python scripts/p18_release.py --p17 <P17 release.json> --p11-workspace <P11 工作区> --p11-receipt <P11 release.json> --measurements <Washington 水位原表>`。回执保留两河段补测包、Washington 的实际原始行及影响的水力参数。

[English](LOCAL_RELEASE_EN.md) · [生产化开发顺序与验收标准](PRODUCTION_ROADMAP_CN.md)

## P17 单因素水位误差诊断

在已计算纯河道的结果复核页展开「单独检验一种水位偏差原因」。选择事件，录入一个有物理依据的变化，然后点击「冻结输入并预览试算」。可以添加同一父版和事件的其他因素，最后一次确认队列。每个工况分别从原始几何起算。

- 更换地形时提供带水平坐标系的 GeoTIFF，核实垂直单位及基准。新旧地形在原断面同一位置采样，保留原河床相对于地表的修正。
- 河床试算使用一个有符号的英尺变化量，在主槽中央达到指定值、两岸处归零。出口试算使用已有已知水位边界同事件、同基准的绝对水位。
- 断面间距可直接从 DEM 在相邻断面之间加密，也可提供同坐标系、单位及基准的嵌套几何 JSON。核对原断面、主槽流程长度与新增漫滩路径长度。
- 可附诊断比较 CSV，列为 `profile,rs,stage_ft,flow_cfs,vertical_datum,source_record`。列出同一事件的非出口测点及原始记录。系统也可沿用该单工况已登记的可比内点。该动作产生回溯性诊断资料。

计算后查看测点偏差、共同断面的逐站差值、两版的湿端位置及完整原生警告数。实测偏差加大时保留父版并列出需要核查的位置。若警告导出缺失，会明确显示缺件。隔离复验命令为 `scripts/p17_release.py <P12工作目录>`；复用已生成的同机基准可附 `--resume <本次验收目录>`。

## P16 事件洪痕定位

在已保存河线和断面的纯河道项目中展开「查找 USGS 事件洪痕」。输入事件年份及官方英文河名，选择原始事件，点击下载、定位并冻结。地图使用洪痕坐标；表格给出原始行号、最近断面、距离、桥侧、高程基准和质量。查看原件后可按组保存用途。候选内点仍需核实事件、独立性和高程依据，再通过原始测量表入口采用。选择以前的冻结查询可以离线重放。已登记的异地水尺会显示至出口的距离和传递要求。

在独立检出的仓库用本机 Python 运行 `scripts/p16_release.py <P12工作目录> --live --browser --soquel <P11工作目录>`。移去三个可选参数可执行纯离线原件复核。原始 Iowa 文件、Soquel 项目及工作报告保存在本机；发版记录在 `status/p16`。

## P14 客户交接及 P15 存储复验

使用独立检出、P4 的 Dexter 测量原件、后到的水位资料、带空间参考的航片，以及已配置的本机原生软件。存储对照另需一份提交 `8781730` 的本地旧版检出，脚本会核对旧实现的文件指纹。请替换数据路径，第二条命令中的 `<batch>` 换成第一条命令完成时输出的批次目录名。

```powershell
.\.venv\Scripts\python.exe scripts/p14_release.py --survey D:\Dexter\survey --observation D:\Dexter\event_return.csv --imagery D:\Dexter\imagery
.\.venv\Scripts\python.exe scripts/p15_release.py --journey status/p14/<batch>/journey/release.json --reference-root D:\SteadyReach_8781730
```

P14 通过项目页面完成操作，核对两份报告首页以及单独客户目录中两包的原生结果。P15 操作存储预估页面，对照完整文件归属和可清理清单，记录实体清理时的卷空间增量，并逐文件校验恢复结果。恢复中途空间不足和批次预算差一字节属于受控故障演练。回执分别在 `status/p14` 和 `status/p15`，算例副本及原生交付包留在本机。

**2026 年 11 月 26 日本机实测。** Dexter 修订版在 2015 年 10 月事件、1,540 cfs、RS 500 的水位高估 0.246 ft，仍需补水位测量精度。独立客户目录的两种语言均对应所选原生运行。1、24、171 版规模测试中，各盘点三次的中位数分别由 0.147、0.185、0.405 秒降至 0.073、0.111、0.345 秒。171 版时，归档加清理由 3.470 秒降至 3.180 秒，恢复由 0.612 秒变为 0.622 秒。耗时取决于本次负载。清理步骤释放 15.82 MiB，但新建归档保存在同盘，合计可用空间减少 20.61 MiB。模拟恢复中途磁盘已满后，已恢复的 1 个文件保留，重试补齐其余 126 个，所有文件指纹一致。完整试点预算差 1 字节时启动任务数为 0。

## P11 原始测量表验收

在新的同机隔离检出中，先按安装指南配置 HEC-RAS 7.0.1、QGIS 和报告转换器。准备原 P10 验收工作区、保留 Soquel 原版的工作区，以及冻结的 USGS 11160000 现场测验 GeoJSON。可从[USGS 2024 年测验接口](https://api.waterdata.usgs.gov/ogcapi/v0/collections/field-measurements/items?f=json&monitoring_location_id=USGS-11160000&datetime=2024-01-01%2F2024-12-31&limit=1000)取得并保存原始响应。运行下方命令时替换三个输入路径。

```powershell
.\.venv\Scripts\python.exe scripts/p11_release.py --p10-workspace D:\P10 --soquel-workspace D:\SoquelSource --soquel-visits D:\FieldData\soquel_2024.json
```

脚本在空白隔离检出里复制正式案例，通过本机自动化浏览器核对原始行并实际运行 Washington 出口工况和内点回传修订。两次均校验原生 HDF 和带地图的双包。Soquel 检查异地水尺，Midway 检查空白和单端回传，所用单端数值属于验收模拟。回执在 `status/p11/<批次>/release.json`。原件、模型、报告和验收目录保留在本机。[工程师页面操作](HYDRAULIC_INTAKE_CN.md)

## P9 离线发行、升级与队列恢复

沿用下方 P8 的现场资料，将 `--p8` 换为 `--p9 --p9-fixture <管理员验收配置.json>`。此本机配置记录签名发行目录（`release`）、独立信任的公钥（`trusted_key`）、基础 Python（`python`）、两个历史软件安装目录（`previous_installations`），以及已安装的 `qgis`、`converter` 与 `runtime` 路径。签名私钥和工程数据留在本机。查看同一批次 `p9/` 下的迁移和队列回执，逐一核对恢复任务的两个交付包。重试出图后，水力运行编号和原生 HDF 须与失败前的计算一致。[管理员操作说明](OPERATIONS_CN.md)

## P8 团队复核与外发范围

沿用下方 P7 的命令和冻结资料，将 `--p7` 换成 `--p8`。同时查看总回执和 `p8/release.json`。验收使用独立的本机浏览器会话提交版本并离线回传断面意见，随后在修订版中补资料、重算、复核、生成所选版的交付包并演练撤回。可在记录中将客户和内部清单、两份原生 HDF 及双语报告逐一对应到同一次求解，原始文档留在内部工程中。[团队复核操作指南](TEAM_REVIEW_CN.md)

## P7 断面实测支持与流量范围

沿用下方 P6 的实测资料和本机配置，另准备已冻结的 USGS 流量测验记录。把 `--p6` 换成 `--p7 --p7-visits <冻结测验记录目录>`。打开同一次运行的总回执与 P7 专项回执，核对原生结果、实测用途、断面位置、中英文报告和两种交付包。若已公开的观测参与水力参数调整，修订版需要另一个独立观测事件。[冻结事件与解读结果](STATION_EVIDENCE_CN.md)

## P6 资料清单与离线重放验收

在同机隔离副本中沿用完整 P5 命令，将 `--p5` 改为 `--p6`。保留独立测量包、Midway 原件、Dexter 观测、航片、归档目录与 `--historical-root`。历史目录须含已登记的 Soquel 版本及其来源回执。验收通过的标志为总回执 `status=SOFTWARE_CHECKS_PASSED` 且 `p6.status=PASSED`。在 `status/release_checks/<本次编号>/p6/release.json` 查看各站缺项和边界判定、资料指纹、沿用数、页面输入记录及离线重算的运行编号。

本机验收分别覆盖缺涵底的 Midway、异地测站 Soquel、实测地形与已配对流量事件的 Dexter。水力参数回传和独立观测回传分别核对。冻结资料清单重放时禁止 DNS 和网络连接；从恢复出的实测包重新计算时，本项目的 Python 进程只允许本机回环通信。求解器和 GIS 仍须预先安装。真人、跨机器和独立工程签审另行安排。[工程师操作步骤](HYDRAULIC_INTAKE_CN.md)

**2026-11-25 同机实测。** 三个站点离线重建的清单指纹与冻结时一致。最终代码通过 502 项 Python 检查和 44 项页面测试。下表中 Midway 的回传为注明假设的测试回传，Dexter 的流量和独立水位取自实测事件。

| 场地 | 验收情景 | 实测结果 |
|---|---|---|
| Midway | 涵底缺项、基准错误、按端别补件 | 提示索取进出口涵底和涵长。错基准回传被拦截。单端回传重开 1 项、沿用 312 项；双端重开 2 项、沿用 311 项。未变水力字段重复填报 0 项。 |
| Soquel | 异地测站及历史资料离线复用 | USGS 11160000 对应 RS 1700，距下游断面中心 714.39 m。站点 NGVD29 与模型 NAVD88 不同；缺少对应事件的传递水位。移除隔离副本的原始项目后，仍可独立重放 16 个冻结资料对象。 |
| Dexter | 实测河段、仅补独立观测、从冻结原件复算 | 补 RS 500 独立观测后沿用 126 项水力输入。从冻结原始实测包和本地航片另建项目，在 1,540 cfs 下重新计算，9 个断面的最大水位差 0.000 ft、最大流量差 0.000 cfs。完整包 96 个文件、最小包 20 个文件，中英文报告各 10 页。 |

同机复现的比较对象为两次原生计算。Dexter 独立水位仍缺观测不确定度，用途判定为 `NEED_EVIDENCE`。本次 P6 专项回执的 SHA-256 为 `f2a68065be4916e14487e5484c8f290340064a0bd7890f899a163c7ffbcae445`。

## P5 同机实测基准

2026-11-25，隔离副本通过 492 项 Python 测试、44 项页面测试和前序原生计算回归。验收通过浏览器分别归档、清理和恢复两个河道版本。归档期间，HEC-RAS 7.0.1 从独立交付副本打开两个地点的完整包和最小包工程。QGIS 3.44.15 打开各完整包，均读到 6 个有效图层和两套展示布局。恢复后，两个地点均使用全新的真实计算生成了两种交付包。

| 版本 | 逻辑占用 MiB | ZIP MiB | 清理时实际释放 MiB | 计入同盘 ZIP 后净释放 MiB | 清理并恢复文件数 | 已逐一核验文件数 |
|---|---:|---:|---:|---:|---:|---:|
| Dexter | 120.91 | 37.13 | 16.64 | −20.50 | 132 | 468 |
| Big River / Rockford | 88.96 | 25.48 | 14.09 | −11.40 | 121 | 412 |

每个地点比较了 9 个断面与工况组合，原生水位最大变化均为 0.000 ft，流量最大变化均为 0.000 cfs。离线浏览器验收打开并核验了两种语言的交接入口。本机详细回执的 SHA-256 为 `20de9ecfe535604a7fd8b365c6cc1d5da66b92756f41e54f077969109b8f0111`。真人和跨机器验收继续暂缓。

## 按版本归档、释放空间和恢复

1. 在首页展开 **已保存的项目 → 对应版本 → 管理此版本 → 版本存储与恢复**，点击 **查看版本占用**。项目页也有这个入口。逻辑占用包含版本引用的输入，等于独占与共享字节之和。多个版本合计时，共享文件会被重复计数。展开清理候选可查看每条文件路径。
2. 需要随时打开工作模型时，点击 **固定版本**。其他版本仍引用本版、已登记原件缺失或指纹变化，以及计算任务运行中，都会限制清理。已发布双包和已登记现场原件保留在原路径。项目管理中的 **删除项目** 会将版本移入回收站，文件继续占用空间。
3. 填入工作目录外已有的本机文件夹，点击 **创建并校验归档**。备份时请同时保管登记的 ZIP 与工作目录中的版本目录记录。优先选择其他磁盘。同盘归档时，请查看计入 ZIP 后的预计净释放量。创建时目标盘需要预留接近全部未压缩文件大小的临时空间。
4. 展开 **释放已归档的工作文件**，核对并确认当前版本。程序会核验 ZIP 和当前文件指纹后再清理。归档版本继续列在首页的原项目组里，已发布交付包可离线打开。若清理中断，可选择 **继续已核验的清理** 或 **恢复此版本**。
5. 将归档盘接回登记位置，在原项目组中点击 **恢复此版本**。程序会检查可用空间、核对现有文件并恢复缺失成员。若提示文件冲突，先另存独立修改，再找回提示路径对应的原版本后重试。若来源版本缺失，请先恢复来源版本。打开已恢复版本，创建可编辑修订版发起新计算。若整个工作目录或版本目录记录丢失，请使用整库备份恢复。

**同机发版验收。** 在隔离副本中，给下文 P4 命令增加 `--p5 --p5-archive-dir <工作目录外已有的本机目录>`。验收继承 P4，通过页面归档和恢复两个带 GIS 交付包的河道版本。`p5/release.json` 记录清理前后字节数、验证文件数、双包校验、真实运行编号和逐断面复算结果。磁盘剩余空间实测包含同盘其他写入活动。回归用例另测空间不足、中断、受引用或被固定版本及共用地形。

P4 发版检查包含完整 P3。沿用 P3 命令，增加 `--p4 --dexter-survey <测量目录> --dexter-observation <event_return.csv> --dexter-imagery <NAIP目录> --historical-root <归档项目根目录>`。归档目录含原 Pagosa、Merced 项目及原生输出，检查以只读方式使用。请在独立副本内运行发版检查。

查看发版清单与 `p4/` 下三份验收记录，分别核对新地点留出事件、Midway 的错误高程基准／部分补测／假设值回传、Siletz 实测事件判定及历史断面比较。Dexter 记录了自动操作次数。工程师实际用时和第二台机器验收另行安排。[冻结数据及准备说明](../examples/dexter_or/README.zh-CN.md)


在项目页展开 **交付预览、本地文件与可选试点计时**。可查看每种包包含哪些已登记附件、其他来源、位置文件和 PDF。单个 PDF 损坏时，点击该行即可从指纹一致的副本恢复，交付版本和其余文件保持一致。历史交付若没有对应副本，可从已核验备份恢复或基于原计算发布新版。界面分别列出须保留的项目原件和可重新下载的安装缓存。

如需用冻结的 Siletz 复核包做同机真实发版回归，在发版命令加上 `--packet <复核包目录> --fresh-benchmark`。工具将在独立新项目导入已校验的测量资料，确认输入完整后调用 HEC-RAS，再核对新双包与运行编号、逐断面流量和水位。同输入复算容许差为 0.002 ft 和 0.002 cfs，实测水位的调查门槛仍为 0.15 m。

在地图对照页选择断面可同时检查实测点、边界工况水位响应与原生警告。页面默认定位共有断面中水位变化最大的位置。可保留首个计算作为对照、登记该站补测或用第二方案已核验的几何建立可编辑修订版。两个原始计算均可回看。

试点时可分别计工程师操作和等待外部资料的时间，离开时暂停，开发者介入时记一次。误计离开时间可舍弃当前时段。发版检查会直接读取已保存时段。字段重复提交包括有意修改，原生运行用时包括求解与提取。

如需统计多个场地，加 `--cohort sites.json`，内容形如 `{"场地甲":["项目ID","修订ID"],"场地乙":["另一个项目ID"]}`，使用本机真实 ID。每个地点只计一次；回执给出首次计算当时的双包状态、可统计地点数和未知数量，并分列原生计算调用、原生工作进程和全部机器任务耗时。

本指南适用于已安装受支持版本 HEC-RAS 和 QGIS 的 Windows 工作站。具体场地的工程接受状态由独立工程复核确定。

**布置断面前。** 选择拟用场景，查看开工资料面板。核对水下河床、事件流量、测量基准、涵孔尺寸与进出口涵底，以及所需边界。靠近地址的测站可能距离模型出口数百米。核对测量位置、时间、基准、流量范围及向模型边界的传递依据。基准冲突或项目超出当前模型适用范围时，先处理再计算。

**对照结果。** 在结果页打开“比较模型版本与历史洪水边线”。可选两个原生运行比较几何修订，也可加入带日期的 WGS84 GeoJSON、KML 或 KMZ 观测边线。多层 KML 指定单个洪水文件夹。按站号检查水位变化、原生警告、最外湿边和漫滩分流。同流量、同高程基准且断面中心相距不超过 1 m 才计算版本水位差。参与过几何调整的边线需记录用途，事件无法匹配时仅供空间参照。多解及无相交的断面排除在边线统计之外。

**交付复核。** 报告首页列出运行标识、可支持的解释和优先检查的断面。完整包含双语报告和布局，出图成功时最小包含原生 HEC-RAS 结果与英文展图。可从仓库根目录核对已复制的两个包。

```powershell
.\.venv\Scripts\python.exe -m ras_workflow.delivery_pair D:\delivery\Complete D:\delivery\Minimal
```

**本地备份。** 写离线备份前关闭 SteadyReach 服务及原生编辑器。备份包括 projects、data、status、examples 四个目录，包括唯一附件和共享地形。先检查所需空间，在仓库外选择新的归档文件，再还原到新目录。原工作数据应保留到还原后的项目已验证能打开。软件安装和 Python 环境需单独准备。

```powershell
.\.venv\Scripts\python.exe -m ras_workflow.local_backup size
.\.venv\Scripts\python.exe -m ras_workflow.local_backup write D:\Backups\SteadyReach.zip
.\.venv\Scripts\python.exe -m ras_workflow.local_backup verify D:\Backups\SteadyReach.zip
.\.venv\Scripts\python.exe -m ras_workflow.local_backup restore D:\Backups\SteadyReach.zip D:\RestoredData
```

**同机发版必测。** 在独立检出目录准备 HEC-RAS、QGIS、PDF 转换器、Node.js 与 Edge 或 Chrome。下方命令先执行单元和页面回归，再用 Midway 原件分别实算 Q100 初版、道路补件修订版和湿端断面修订版。浏览器还会下载涵底索资单，暂停项目，将明确标注为假设的回传值导入独立草稿，然后对比选版、重开基准版并为选定的修订版生成交接目录。脱离项目的副本须能从双语入口打开文件，报告和原生 HDF 须匹配所选版本。缺件、文件被改、混入其他版本均须检出。缺少私有资料时发版检查保持待办。可用 `python -m unittest discover -s tests` 单测，加 `--packet <复核目录>` 检查 Siletz、East Fork 基准，或加 `--project <项目ID>` 记录试点指标。

```powershell
.\.venv\Scripts\python.exe scripts\release_check.py --midway-fixture D:\ReleaseInputs\Midway\fixture.json
```

**私有基准资料。** 清单和有使用权的原件放在 Git 之外的同一目录，每个文件条目含文件名 `file` 和 `sha256`。`originals` 为四张 JPG、地点 KMZ、StreamStats PDF。`supplement` 为原始道路备忘录 DOCX，`brief` 为随附场地说明 TXT。`terrain`、`terrain_source`、`aerial` 分别为缓存的 USGS DEM、含 `raster.sha256` 的原地形记录和 NAIP 航片。`picks.inlet` 和 `picks.outlet` 为此前判读的两个洞口中心（DEM 投影坐标）。浏览器只标记这两点，上下游外部锚点和断面完全由 DEM 生成。`spacing` 为假设的孔间壁宽（ft）。航片须覆盖整个出图范围；可用 `aerial_source` 条目绑定下载记录及栅格 SHA-256。浏览器在独立修订版中对照备忘录和两条道路剖面，一次采用六项关联输入。名义路宽用作有效越流宽度时保留假设标记。 验收记录见 `status/release_checks` 下的 `midway.json` 和 `release.json`。

机器耗时取自任务记录。工程师操作、外部等待及开发者介入只有经过记录才能统计。可用 `--session <json>` 为所选项目附加计时。字段为 `project_id`、`intervals`（按时序记录 `kind` 为 `engineer` 或 `external_wait`，`started_utc` 和 `finished_utc` 带时区）和 `developer_interventions`（介入事项清单）。显式空清单表示该次观测确认零介入。

试点时可只点“记下卡点”，软件会保存页面、项目阶段、版本和问题类别。只有点“记录一次开发者介入”才新增介入记录。打开计时面板不会启动计时。自动化回归与操作耗时、独立完成、工程签审分别记录。

带冻结复核包执行 `release_check.py --packet` 后，在此次 release.json 旁打开 `Field_review.zh-CN.md`。Siletz 重新从归档水位和流量记录选择留出事件，按原生 HDF 检查内点高程，0.15 m 为本例调查门槛。East Fork 使用另一天的观测和训练时选定的糙率，在三个非边界断面计算偏差。两个例子均排除作为边界的测点。

交付开始时会检查目标盘能否容纳已知的原生文件副本和输入快照；GIS、报告和临时文件还需额外空间。恢复备份前会检查解压文件所需的空间。如遇容量不足，请保留原档案和已完成计算，释放目标盘空间或将备份还原到另一个新目录。

## 运行 P2 发版检查

在具备原生软件的独立检出目录中，指定 Midway 私有原件清单和冻结的独立实测复核包。命令会新建项目，检查 Python 和页面回归、Siletz 基准版及独立修订版、Midway 原件到交接的全程，以及收件人端的逐文件校验。

```powershell
.\.venv\Scripts\python.exe scripts\release_check.py --p2 --packet D:\ReleaseInputs\Independent_Review --midway-fixture D:\ReleaseInputs\Midway\fixture.json
```

查看 `status/release_checks/<运行号>/release.json` 中的 `release_gate` 和两组测试状态。`fresh_benchmark.p2.field` 给出本次实算相对真实内点观测的偏差；同目录的 `midway.json` 记录采用的输入、各次计算和脱离项目后的目录校验。复算一致的项目仍可能超出实测调查门槛，独立签审状态另见 `engineering_approval`。

## 当前版本发版必测（P3）

以本节命令生成的 `release.json` 为准。记录须同时包含 `release_gate = P3`、`status = SOFTWARE_CHECKS_PASSED`、`p3.status = PASSED`、`midway.status = PASSED` 及对应回执。P2 与单项命令可用于开发排错；真人试用和跨机器验收单独记录。Midway 原件入口还需要 `aerial_source` 的 SHA-256，以核对实际用于判读的航片。

在已配置 HEC-RAS、QGIS、PDF 转换器和 Chromium 的仓库中运行 `python scripts/release_check.py --p3 --packet "<冻结复核目录>" --midway-fixture "<私有 fixture.json>" --transfer-survey "<另一地点的测量资料目录>"`。每次运行新建隔离项目。转移测试使用有实际几何、流量和原件的其他地点，私有资料保留在本机。检查覆盖冻结的 East Fork 留出事件、P2 完整链路，以及从首页开始的 Midway 缺资料、Siletz 实测对比和另一地点交接。从 `p3/journeys.json` 核查运行编号、交接目录和分步耗时。所记录时间是软件操作耗时，真人和第二台机器的验收另行安排。

要在离线条件下稳定复核另一地点的地图，增加 `--transfer-imagery "<同时含 Aerial.tif 和 acquisition.json 的目录>"`。Siletz 使用冻结复核资料中已校验的 NAIP 原件。

完整包把层级过深的输入快照存到 `Complete/Evidence/InputFiles`，在 `Complete/Evidence/input_paths.json` 记录原相对路径、包内位置、字节数和 SHA-256。若收件人在 Windows 上遇到长路径读取失败，可将整个交接目录复制到盘符根目录附近后重新校验。

[企业试点范围与操作说明](PILOT_CN.md)
