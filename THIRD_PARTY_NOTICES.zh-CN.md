# 第三方资料与外部软件

[English](THIRD_PARTY_NOTICES.md) | **简体中文**

[MIT 许可证](LICENSE)适用于本应用原创代码与文档，不改变以下第三方材料或程序的原有授权。

| 材料 | 来源及处理 |
|---|---|
| `examples/phelps_brook/inputs/*` 及公开参考值 | USGS《Hydraulic models and supplementary data for 30 stream crossing sites in Massachusetts》2.0，DOI [10.5066/P14HJGZI](https://doi.org/10.5066/P14HJGZI)。[USGS 页面](https://www.usgs.gov/data/hydraulic-models-and-supplementary-data-30-stream-crossing-sites-massachusetts-0)标记 CC0 1.0 Universal；保留准确原始输入、压缩包／成员哈希及独立参考摘录。 |
| `ras_workflow/templates/MULTCULV.*` | USACE HEC-RAS 官方示例原生输入模板，Applications Guide Example 4。相邻 `manifest.json` 保存来源与原始哈希。它们是模型数据，不是 HEC-RAS 引擎源码。参见 [HEC 分发政策](https://www.hec.usace.army.mil/software/distribution_policy.aspx)和[使用条款](https://www.hec.usace.army.mil/software/terms_and_conditions.aspx)。 |
| HEC-RAS／QGIS | 从厂家分别安装，本仓库不附带安装器或引擎。HEC-RAS 适用 HEC 条款，QGIS 保留自身许可证；本应用不代表 USACE／USGS 背书。 |
| Python 依赖及安装工具 | 安装时根据 `requirements.lock.txt` 和 `scripts/setup_downloads.json` 的固定来源下载。Python、uv、7-Zip、Microsoft 运行库和 LibreOffice 保留各自授权；缓存及二进制留在本机，不纳入仓库。 |

接口资源包含受支持版本已检查的方法／类型签名，实际安装软件在运行时另行核对。本源码目录不含私有场地材料、凭据、软件安装器或历史计算结果。
