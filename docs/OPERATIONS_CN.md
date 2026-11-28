# 安装经过校验的版本与恢复队列

[English](OPERATIONS_EN.md) · [本机发布检查](LOCAL_RELEASE_CN.md) · [项目诊断](ENGINEERING_DECISIONS_CN.md)

## 批次开始前预估空间

在一个已完成的代表版本中，打开 **版本存储与恢复 → 查看版本占用**。填好实际归档目录，展开 **预估同类批次所需空间**，输入同类版本数并点 **预估空间峰值**。页面列出工作盘峰值、归档用量、单版恢复预留及两块盘各自的缺口。估算按串行处理、每版保留一份与所选版相当的结果、额外一份临时工作副本计算。地形更大的项目应另选代表版本。

运行完整的 P10 固定 26 项验收前，程序自动保存 `capacity.json`。依据为实测工作峰值 7,147,333,505 字节、归档 66,153,326 字节及单版恢复预留 18,061,750 字节。同盘时三项合计计入工作盘。空间不足时 `release.json` 记录 `LOW_SPACE` 和已启动任务 0 项。释放空间或更换归档盘后可重试。版本恢复中断时，可从原登记归档继续恢复。

本说明供单台 Windows 工作站管理员使用。工程师日常仍可双击 `start_workflow.cmd`。升级时先关闭正在使用两个安装目录的应用。软件发行包、工程数据和迁移备份分别存放。

## 离线安装

准备发行目录，以及通过独立可信渠道取得的管理员公钥。在受信任的 SteadyReach 代码目录执行下列命令，将示例绝对路径替换为本机路径。发行目录含软件源码、锁定版本的 Windows 依赖包、组件及哈希清单、项目和依赖许可证。本机还需准备 Windows x64 Python 3.12.14、已注册的 HEC-RAS、QGIS LTR、LibreOffice 和匹配的微软求解器运行库。

```powershell
$Tool = 'D:\SteadyReachAdmin\.venv\Scripts\python.exe'
$Release = 'D:\Releases\SteadyReach'
$Key = 'D:\Trust\SteadyReach.pub.xml'
$Candidate = 'D:\Applications\SteadyReach_candidate'
$BasePython = 'D:\Runtimes\Python312\python.exe'
& $Tool scripts/software_release.py verify --release $Release --trusted-key $Key
& $Tool scripts/software_release.py install --release $Release --trusted-key $Key --destination $Candidate --python $BasePython
& "$Candidate\.venv\Scripts\python.exe" "$Candidate\scripts\bind_release_tools.py" --installation $Candidate --qgis 'D:\Applications\QGIS-LTR' --converter 'D:\Applications\LibreOffice\program\soffice.exe' --runtime 'D:\Runtimes\msvcr100.dll'
```

核验成功会打印签名对应的 Git 提交号。遇到错误先停下看具体文件或软件名称。安装程序校验签名和全部发行文件，在最终目录建立 Python 环境，从随包依赖离线安装并执行 `pip check`。最后一条命令实际检查求解器、QGIS 的 Python 环境和 PDF 转换器，把结果写入 `INSTALLED_TOOLS.json`。安装中断时保留诊断输出，换一个空目录重试。

## 迁移工程和回滚

旧安装需保有可运行的 Python 环境。工程版本归档如存于外置盘，先接好该盘。备份文件使用新路径，控制目录设在两个安装目录之外。中途中断后，用同一组路径再次执行准备命令。

```powershell
$Previous = 'D:\Applications\SteadyReach_previous'
$Control = 'D:\SteadyReachAdmin\active'
$Backup = 'D:\Backups\previous_projects.zip'
$Migration = & $Tool scripts/deployment.py prepare --previous $Previous --candidate $Candidate --control $Control --archive $Backup --release $Release --trusted-key $Key
if ($LASTEXITCODE -ne 0) { throw '迁移准备失败' }
$Token = ($Migration | ConvertFrom-Json).token
& $Tool scripts/deployment.py switch --control $Control --token $Token
& $Tool scripts/deployment.py open --control $Control
```

准备步骤校验备份及迁移文件，并分别用旧版和新版的工程读取器核对原始附件、水力结果和已有的两种交付包。`switch` 更新管理员的当前版本记录，随后用 `open` 打开所选安装。需要回滚时关闭新版服务，将上面的 `switch` 改为 `rollback`，使用原令牌。切换后新增的工作仍在新版目录，回滚前单独保存这部分修改。

## 恢复队列任务

同一队列每次重试均指定原配置和输出目录。队列配置使用相对于安装目录的工程路径，每个任务有一个独立 ID。下面的 `$Queue` 是队列 JSON，`$Output` 是安装目录下的队列输出位置。请在当前使用的安装目录里，用其 Python 执行命令。

```powershell
$Queue = 'status/operator/queue.json'
$Output = 'status/operator/jobs'
& $Tool workflow.py queue-run --queue $Queue --output $Output
& $Tool workflow.py queue-status --output $Output
& $Tool workflow.py queue-cancel --output $Output --job reach_a
& $Tool workflow.py queue-resume --output $Output --job reach_a
& $Tool workflow.py queue-run --queue $Queue --output $Output
```

取消正在运行的任务时，在另一个终端发送取消命令。`queue-resume` 清除人工取消标记，随后重新执行队列，处理未完成任务。磁盘不足时等待其他任务释放预留空间，或腾出空间后重试。大地形可在该任务配置中填写正整数 `reserve_bytes`。若求解已完成而出图失败，关闭占用文件或恢复出图软件后重试，程序会核对并复用原计算。求解中断的任务会重新计算。每次尝试都记录状态、分阶段用时和求解批次；输入匹配且记录完整的已完成任务会跳过。

## 预览支持包

```powershell
$Preview = & $Tool workflow.py queue-support --output $Output | ConvertFrom-Json
$Preview.preview | ConvertTo-Json -Depth 8
& $Tool workflow.py queue-support --output $Output --save 'D:\Support\queue_support.zip' --preview-token $Preview.token
```

默认支持包只含编号、尝试状态、分阶段用时和求解复用情况。导出时核对预览令牌。每次导出选用新文件名。现场原件、路径与日志原文留在本机。

## 管理员制作发行包

由负责发行的 Windows 账户保管签名密钥。私钥文件置于发行目录和 Git 之外。通过独立可信渠道发布公钥指纹。选定已提交的 Git 版本，准备与 `requirements.lock.txt` 完全匹配的 Windows 依赖目录，再制作新发行包。

```powershell
powershell -NoProfile -File scripts/release_signature.ps1 -Action create-key -PublicKey D:\Trust\SteadyReach.pub.xml -PrivateKey D:\Signing\SteadyReach.dpapi
& $Tool scripts/software_release.py build --revision $Commit --version $Version --wheels $Wheels --private-key D:\Signing\SteadyReach.dpapi --trusted-key D:\Trust\SteadyReach.pub.xml --output $NewRelease
```

建立新签名身份时才执行生成密钥命令。公钥指纹和使用权限应随组织的发行管理记录保存。管理员可用此公钥追溯本地发行包。第三方软件部署与工程工作站验收按各自流程办理。
