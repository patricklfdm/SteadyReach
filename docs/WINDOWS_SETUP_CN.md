# Windows 安装与修复

[English](WINDOWS_SETUP_EN.md) | **简体中文** | [首页](../README.zh-CN.md)

## 1. 解压程序

下载仓库 ZIP 并完整解压，或 clone 仓库。选择本机可写目录，例如 `C:\Work\SteadyReach`，不限定盘符。不要在压缩包内运行。软件需要数 GB 空间，地形和结果另需空间。正常启动路径不要求提前安装 Python 或输入命令。

## 2. 安装 HEC-RAS

打开官方 [HEC-RAS 下载页](https://www.hec.usace.army.mil/software/hec-ras/download.aspx)，在 **Archived Versions** 中选择 Windows 原生 **HEC-RAS 7.0.1 Setup Package**。按厂家安装器正常安装，完成后打开一次 HEC-RAS。程序核对已适配的 7.0.1 可执行文件及控制接口；更新版本不自动视为兼容，不要改哈希白名单绕过检查。

运行计算前请保存并关闭正在编辑的工程。若已有工程阻碍独立求解会话，程序会停止并说明问题，不覆盖它。

## 3. 需要地图时安装 QGIS

从 [QGIS 下载页](https://qgis.org/download/)取得 **QGIS 3.44 LTR** 系列的 Windows 独立安装器。程序已在 3.44.15 上运行过，其他版本需另做兼容性检查。正常启动一次 QGIS。安装程序询问路径时，选择同时包含 `bin` 和 `apps` 的 QGIS 根目录，不选 exe、开始菜单快捷方式或单独的 `bin` 文件夹。

可编辑布局和地图交付需要 QGIS。若只练习原生模型与报告，可暂缓 QGIS 并在项目里取消 GIS；完整环境检查仍会提示地图交付不可用。

## 4. 双击 start_workflow.cmd

首次启动调用 `setup_workflow.cmd`，在本目录准备 Python 3.12 虚拟环境、固定版本依赖、求解器运行库和便携 LibreOffice PDF 转换器，校验下载哈希，日志保存到 `status/setup`。HEC-RAS／QGIS 仍单独安装。程序安装过程不要求提权或修改安全策略。

下载可能持续数分钟，请查看字节数、百分比和进度提示，不要反复启动多个安装窗口。下载停滞或失败时保留日志后重新运行安装；已校验完成的下载会复用，失败的 partial 文件不算成功。

询问 QGIS 时选择根目录，或回车暂缓。完成后浏览器打开本地应用，保持控制台运行。在控制台最终“按任意键继续”提示处按键会关闭已结束的启动窗口，不会卸载环境或删除项目。

## 5. 后续使用和修复

- **日常启动：**双击 `start_workflow.cmd`。
- **修复依赖或重选 QGIS：**双击 `setup_workflow.cmd`。
- **检查安装、实际 PDF 转换及 QGIS 导出：**双击 `check_environment.cmd`，详细结果位于 `status/doctor.json`。

环境检查不运行水力计算，也不批准设计。若 `.venv` 不完整，先保留用于诊断；仅在所有程序／安装窗口停止后将其改名另存，再重新安装。不要为修复 Python 删除已保存项目。

软件路径改变后重新运行安装。路径保存在 `.tools/workflow_tools.json`，仅供本机使用，不应公开。更多见[常见问题](TROUBLESHOOTING_CN.md)。
