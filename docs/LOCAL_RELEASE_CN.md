# 本机生产复核

[English](LOCAL_RELEASE_EN.md) · [生产化开发顺序与验收标准](PRODUCTION_ROADMAP_CN.md)

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
