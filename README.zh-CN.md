# SteadyReach

[English](README.md) | **简体中文**

基于 HEC-RAS 的 Windows 本地一维恒定流涵洞分析工具。通过浏览器的 **项目 → 模型 → 结果** 三屏完成操作，无需 AI 服务。

## 从这里开始

1. 下载本仓库 ZIP 并解压到可写目录，或 clone 仓库。活动计算建议使用本地磁盘，避免 OneDrive／网络同步目录。
2. 安装 **HEC-RAS 7.0.1**；需要可编辑 GIS 和展示图时安装 **QGIS 3.44 LTR**。参阅[安装说明](docs/WINDOWS_SETUP_CN.md)，此适配器不能直接假定兼容更新的 HEC-RAS 版本。
3. 双击 **start_workflow.cmd**。首次运行会准备本地 Python 和依赖，按提示选择 QGIS 路径；保持启动窗口打开。
4. 先试用内附的 [Phelps Brook 公开示例](examples/phelps_brook/README.zh-CN.md)，自己的地点参阅[没有现成模型时的指南](docs/NO_MODEL_GUIDE_CN.md)。
5. 集中检查全部参数，修改数值或假设，明确确认后才启动真实求解。在结果页打开报告及 **Minimal／Complete** 交付目录。

[用户手册](docs/USER_GUIDE_CN.md) · [安装与修复](docs/WINDOWS_SETUP_CN.md) · [常见问题](docs/TROUBLESHOOTING_CN.md) · [适用范围与限制](docs/LIMITATIONS_CN.md)

## 主要功能

- 为美国地点查询 USGS DEM，准备地形、采样断面并提供左右岸候选。
- 导入支持的已有恒定流模型，或利用填写参数与地形数据新建模型。
- 标注建议／估算值，没有依据的必填项留空；无模型数值字段可修改，运算前集中确认。
- 真实调用 HEC-RAS，核验输出身份、保留警告，生成中英 DOCX／PDF 技术报告和英文摘要。
- 生成最小原生模型包和完整包；开启 GIS 且资料、软件可用时，包含 Mapper 地形／等高线、QGIS 布局和展示图。

计算范围为单河段、单个箱涵或圆管交叉口，可含多个涵孔组。地表 DEM 不能确认埋藏涵底；计算或打包成功不等于工程设计合格。

## 数据保存在本机

工作项目、下载数据、本机软件和报告运行时生成，由 `.gitignore` 排除。需要时备份整个工作项目；不要强制将被忽略的用户附件、计算结果或机器配置提交到公开仓库。

程序代码和原创文档采用 [MIT 许可证](LICENSE)。公开示例、原生模板和外部程序保留各自条款，见[第三方说明](THIRD_PARTY_NOTICES.zh-CN.md)。

## 资料辅助输入

模型页面可查询支持的公开资料、解析测量 CSV／PDF／文本、尝试本机 OCR、将测点叠加 DEM，并提出带来源的候选。保留已有参数，区分冲突与失败，采用折叠分组和缺失项导航。详见[资料辅助指南](docs/SOURCE_ASSIST_CN.md)。资料源覆盖有限，未支持或有歧义的现场信息仍需工程师判断。
