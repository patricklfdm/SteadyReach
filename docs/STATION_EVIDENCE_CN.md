# 按断面和流量核对实测水位

[English](STATION_EVIDENCE_EN.md)

在河道方案运算前展开项目用途与交付条件。按原件填写事件名称、日期、工况、河站号、观测用途、允许的水位误差（ft）和容差依据。逐项添加后保存。用于独立验证的留出事件应位于河段内部，且未用于设置计算输入。边界控制和率定观测应选各自的用途。

先计算预留工况。取得实测水位后，通过补资料建立独立版本。核对事件、位置、流量、单位、高程基准与测量不确定度。结果页展开计算断面复核，进入**断面与流量的实测支持范围**。切换工况，可查水位有符号偏差（计算减实测）、独立事件数、观测点数和偏差最大的断面。英文和中文报告引用同一次计算。

局部判定还会核对原生警告、湿端、漫滩分流变化，以及边界、糙率和间距试算。间距检查比较受测区间内相邻两级加密结果。超过项目约定误差时应调查；缺少实测不确定度时，即便差值很小，支持程度也保留待定。某点满足实测误差要求后，仍可能有敏感性或原生警告待处理。结论只适用于已测流量与断面。若在看到观测后据此修改水力参数或比较条件，须为修订版另选独立事件。

## 复现发版检查

首次联网执行选样脚本，保存完整输出目录。脚本先冻结选样协议再获取实测记录。加上 `--offline` 后，会从本机读取原始返回并核验指纹。

```powershell
python examples/oregon_holdouts/select_visits.py status/oregon_visits
python examples/oregon_holdouts/select_visits.py status/oregon_visits --offline
```

完整回归沿用 [P6 验收资料](LOCAL_RELEASE_CN.md)，将命令中的 `--p6` 换为 `--p7 --p7-visits status/oregon_visits`。记录位于 `status/release_checks/<运行号>/p7/release.json`。McKenzie 和 Willamette 的记录提供同期实测流量与相对水尺读数，需补足可比的河段内部断面与高程换算依据才能评分。Merced 与 Pagosa 的历史对照使用各自保留的原生计算。 [McKenzie River near Vida](https://waterdata.usgs.gov/monitoring-location/USGS-14162500/) · [Willamette River at Harrisburg](https://waterdata.usgs.gov/monitoring-location/USGS-14166000/)
