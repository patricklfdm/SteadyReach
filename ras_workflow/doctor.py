"""Installation checks and optional software-only runtime probes; no site solve."""
import argparse
import importlib.metadata
import json
import platform
import site
import sys
from pathlib import Path
from .common import ROOT, item, save, safe_path, utc


def timezone_check():
    """Loading real IANA rules catches missing/corrupt data even with package metadata."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        zone=ZoneInfo.no_cache('America/Los_Angeles')
        offsets=[datetime(2026,m,1,tzinfo=zone).utcoffset().total_seconds() for m in (1,7)]
        return dict(status='READY',key=zone.key,winter_summer_offsets_seconds=offsets)
    except Exception as e:
        return dict(status='BLOCKED',key='America/Los_Angeles',error=str(e))


def inspect(tools_config=None, *, full=False, require_delivery=False):
    packages=[]; blockers=[]
    for line in (ROOT/'requirements.txt').read_text(encoding='utf-8').splitlines():
        line=line.split('#')[0].strip()
        if not line:continue
        name,expected=line.split(';')[0].strip().split('==')
        try:actual=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:actual=None
        packages.append(dict(name=name,expected=expected,actual=actual,status='READY' if actual==expected else 'BLOCKED'))
        if actual!=expected:blockers.append('Python dependency mismatch: '+name+' requires '+expected+', found '+str(actual))
    if platform.system()!='Windows' or sys.maxsize<=2**32 or sys.version_info[:2]!=(3,12):
        blockers.append('Validated platform requires Windows x64 Python 3.12')
    try:
        from .native import discover
        solver=discover()
    except Exception as e:solver=dict(status='BLOCKED',blocking_items=[str(e)])
    try:
        from .report_tools import discover as reports
        report=reports(tools_config)
    except Exception as e:report=dict(status='BLOCKED',blocking_items=[str(e)])
    cfg=Path(sys.prefix)/'pyvenv.cfg'
    try:
        from .qgis_runtime import environment
        q,_=environment(tools_config=tools_config);delivery_tools=dict(status='AVAILABLE_NOT_EXECUTED',qgis_root=str(q),scope='Path checks only; use --full to test loading and export')
    except (ValueError,OSError) as e:delivery_tools=dict(status='NOT_AVAILABLE',error=str(e),scope='Mapped delivery waits; calculation and reports remain available')
    isolated=cfg.exists() and 'include-system-site-packages = false' in cfg.read_text(encoding='utf-8').lower()
    if not isolated:blockers.append('An isolated project virtual environment is required')
    timezone=timezone_check()
    if timezone['status']!='READY':blockers.append('Timezone: cannot load America/Los_Angeles; '+timezone['error'])
    blockers+=['Solver: '+x for x in solver.get('blocking_items',[])]+['Reports: '+x for x in report.get('blocking_items',[])]
    ocr=dict(status='NOT_EXECUTED',scope='Use --full for an actual OCR recognition probe')
    probes=None
    if full:
        from .local_ocr import probe as ocr_probe
        ocr=ocr_probe()
        from .environment_probe import run
        probes=run(tools_config,reports=report.get('status')=='READY',qgis=delivery_tools['status']=='AVAILABLE_NOT_EXECUTED')
        if probes['reports']['status']=='FAILED':blockers.append('Report runtime: '+probes['reports']['error'])
        if probes['qgis']['status']=='PASSED':delivery_tools.update(status='READY',version=probes['qgis']['version'],scope='Actual QGIS loading, PDF export and project reopen passed; site mapping still needs review')
        elif probes['qgis']['status']=='FAILED':delivery_tools.update(status='BLOCKED',error=probes['qgis']['error'])
    if require_delivery and delivery_tools['status'] not in ('READY','AVAILABLE_NOT_EXECUTED'):
        blockers.append('Mapped delivery: '+delivery_tools.get('error','QGIS unavailable'))
    return dict(status='BLOCKED' if blockers else 'READY',checked_at_utc=utc(),blocking_items=blockers,
         python=dict(executable=sys.executable,version=sys.version,prefix=sys.prefix,base_prefix=sys.base_prefix,
                     isolated_venv=isolated,site_packages=site.getsitepackages()),
         os=platform.platform(),requirements=item(ROOT/'requirements.txt'),packages=packages,solver=solver,reports=report,delivery_tools=delivery_tools,
         timezone=timezone,ocr=ocr,runtime_checks=probes,require_delivery=require_delivery,
         limitation='Environment checks only. --full converts a software-only document and exports a QGIS test layout. No HEC-RAS solve, site mapping review, hydraulic QA or engineering acceptance is implied.')


def remedies(result):
    actions=[]
    if not result['python']['isolated_venv']:
        actions.append(dict(en='Isolate and repair the checkout Python environment.',zh='隔离并修复本仓库 Python 环境。',command=r'.\setup_workflow.cmd',guide='docs/WINDOWS_SETUP_EN.md'))
    if any(p['status']!='READY' for p in result['packages']):
        actions.append(dict(en='Repair the project Python dependencies, then rerun the check.',zh='修复项目虚拟环境依赖后重新检查。',command=r'.\setup_workflow.cmd',guide='docs/WINDOWS_SETUP_EN.md'))
    if result['solver'].get('status')!='READY':
        actions.append(dict(en='Check the registered supported HEC-RAS installation and project runtime. Keep failed logs; do not change executable hashes or security settings.',zh='检查已注册的受支持 HEC-RAS 安装及项目运行库。保留失败日志，不修改哈希白名单或安全设置。',guide='docs/GETTING_STARTED_EN.md',step='3–4'))
    if result['reports'].get('status')!='READY':
        actions.append(dict(en='Prepare the portable PDF converter and its tool configuration.',zh='准备便携 PDF 转换器及工具配置。',command=r'.\setup_workflow.cmd',guide='docs/WINDOWS_SETUP_EN.md'))
    if result['timezone']['status']!='READY':
        actions.append(dict(en='Repair IANA timezone data, including damaged package files.',zh='修复 IANA 时区数据，包括损坏的包文件。',command=r'.\setup_workflow.cmd',guide='docs/WINDOWS_SETUP_EN.md'))
    if result['delivery_tools']['status'] not in ('READY','AVAILABLE_NOT_EXECUTED'):
        actions.append(dict(en='Run setup_workflow.cmd to select QGIS; a path alone is not a runtime test.',zh='运行 setup_workflow.cmd 选择 QGIS；仅路径存在不等于能够运行。',command=r'.\setup_workflow.cmd',guide='docs/WINDOWS_SETUP_EN.md'))
    if (result.get('runtime_checks') or {}).get('reports',{}).get('status')=='FAILED':
        actions.append(dict(en='Inspect the retained converter log; rerun setup/check after resolving the cause.',zh='查看保留的转换器日志，修复后重新安装检查。',command=r'.\check_environment.cmd',guide='docs/WINDOWS_SETUP_EN.md'))
    if result['status']!='READY' and not actions:
        actions.append(dict(en='Use Windows x64 Python 3.12 in the project virtual environment.',zh='使用项目虚拟环境中的 Windows x64 Python 3.12。',guide='docs/GETTING_STARTED_EN.md',step='2'))
    return actions


def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description='Windows environment checks; --full writes software-only probe artifacts, never site results')
    p.add_argument('--tools');p.add_argument('--output');p.add_argument('--brief',action='store_true')
    p.add_argument('--full',action='store_true',help='Actually convert a document and export/reopen a QGIS test project in status/environment_checks')
    p.add_argument('--require-delivery',action='store_true',help='Treat missing/broken QGIS as an environment blocker')
    a=p.parse_args(argv)
    result=inspect(a.tools,full=a.full,require_delivery=a.require_delivery)
    result['next_actions']=remedies(result)
    if a.output:save(safe_path(ROOT,a.output),result)
    if a.brief:
        print('Environment / 环境: '+result['status'])
        print('  Timezone / 时区: '+result['timezone']['status'])
        print('  HEC-RAS installation / 安装检查: '+result['solver']['status'])
        print('  QGIS: '+result['delivery_tools']['status'])
        print('  Local OCR / 本地识别: '+result['ocr']['status'])
        if result['ocr'].get('error'):print('  '+result['ocr']['error'])
        if result['runtime_checks']:
            print('  PDF conversion / 实际转换: '+result['runtime_checks']['reports']['status'])
            print('  Evidence / 检查证据: '+result['runtime_checks']['folder'])
        for problem in result['blocking_items']:print('  '+problem)
        for action in result['next_actions']:
            print(action['en']+' / '+action['zh']);print(action.get('command') or action['guide']+' (step '+action.get('step','2')+')')
        print('Diagnostic / 诊断文件: '+a.output if a.output else 'Full check / 完整检查: .\\check_environment.cmd')
    else:print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='READY' else 2
