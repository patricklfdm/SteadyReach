"""Resumable checkout-local setup. No elevation, installer execution or policy changes."""
import argparse
import http.client
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ras_workflow.common import ROOT, read, rel, save, sha, unique_id, utc

RUNTIME_SHA='1d1a1ae540ba132f998d60d3622f0297b6e86ae399332c3b47462d7c0f560a36'
MAX_DOWNLOAD_BYTES=600*1024**2
DOWNLOAD_SOCKET_TIMEOUT=30
DOWNLOAD_MAX_SECONDS=900
DOWNLOAD_PROGRESS_WINDOW=60
DOWNLOAD_MIN_PROGRESS_BYTES=64*1024
DOWNLOAD_DISPLAY_INTERVAL=5


def require_https(url):
    parts=urllib.parse.urlsplit(url)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:
        raise ValueError('Download requires an HTTPS URL without credentials: '+url)


class DownloadRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self,attempt,on_update=None):
        self.attempt=attempt
        self.on_update=on_update

    def redirect_request(self,req,fp,code,msg,headers,newurl):
        self.attempt.setdefault('redirects',[]).append({'from':req.full_url,'to':newurl,'status':code})
        if self.on_update:self.on_update()
        require_https(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def transfer_download(response,output,attempt,started,on_update=None):
    length=response.headers.get('Content-Length')
    expected=int(length) if length is not None else None
    if expected is not None and expected>MAX_DOWNLOAD_BYTES:
        raise ValueError('Download exceeds 600 MB safety limit')
    attempt.update(bytes=0,expected_bytes=expected)
    total=0;window_bytes=0
    window_start=last_display=time.monotonic()
    size=f'{expected/1024**2:.1f} MiB' if expected is not None else 'size unknown / 大小未知'
    print('Receiving / 接收文件: '+size+'; '+response.geturl(),flush=True)
    if on_update:on_update()
    while True:
        if time.monotonic()-started>=DOWNLOAD_MAX_SECONDS:
            raise TimeoutError(f'Download source exceeded {DOWNLOAD_MAX_SECONDS}s / 本下载来源超过最长等待时间')
        # read(n) may wait for n bytes while tiny packets keep resetting socket
        # timeouts. read1 returns after one underlying read, enabling progress checks.
        chunk=response.read1(64*1024)
        now=time.monotonic()
        if now-started>=DOWNLOAD_MAX_SECONDS:
            raise TimeoutError(f'Download source exceeded {DOWNLOAD_MAX_SECONDS}s / 本下载来源超过最长等待时间')
        if not chunk:break
        total+=len(chunk)
        attempt.update(bytes=total,last_data_utc=utc())
        if total>MAX_DOWNLOAD_BYTES:raise ValueError('Download exceeds 600 MB safety limit')
        output.write(chunk)
        if now-last_display>=DOWNLOAD_DISPLAY_INTERVAL:
            output.flush()
            percent=f' ({100*total/expected:.0f}%)' if expected else ''
            rate=(total-window_bytes)/max(now-window_start,0.001)/1024
            print(f'  {total/1024**2:.1f} / {size}{percent}; {rate:.0f} KiB/s; {now-started:.0f}s',flush=True)
            last_display=now
            if on_update:on_update()
        if now-window_start>=DOWNLOAD_PROGRESS_WINDOW:
            if total-window_bytes<DOWNLOAD_MIN_PROGRESS_BYTES:
                raise TimeoutError(f'Download stalled: less than {DOWNLOAD_MIN_PROGRESS_BYTES//1024} KiB in '
                    f'{DOWNLOAD_PROGRESS_WINDOW}s / 下载长时间无有效进展')
            window_start=now;window_bytes=total
    output.flush()
    if expected is not None and total!=expected:
        raise http.client.IncompleteRead(b'',expected-total)
    print(f'  Downloaded / 已下载 {total/1024**2:.1f} MiB; verifying SHA-256 / 正在校验。',flush=True)
    if on_update:on_update()


def download(spec,directory,trace,on_update=None):
    """Bounded publisher-listed alternatives; TLS and the pinned digest stay mandatory."""
    urls=list(dict.fromkeys([spec['url']]+spec.get('fallback_urls',[])))
    for url in urls:require_https(url)
    trace['attempts']=[]
    for index,url in enumerate(urls,1):
        partial=directory/(spec['name']+'.'+uuid.uuid4().hex+'.partial')
        attempt={'url':url,'started_utc':utc(),'status':'CONNECTING','partial_path':str(partial),'bytes':0}
        trace['attempts'].append(attempt)
        print(f"Download / 下载 ({index}/{len(urls)}): {spec['name']}\n{url}",flush=True)
        if on_update:on_update()
        started=time.monotonic()
        try:
            # Default HTTPSHandler performs normal platform certificate/hostname checks.
            opener=urllib.request.build_opener(DownloadRedirects(attempt,on_update))
            with opener.open(url,timeout=DOWNLOAD_SOCKET_TIMEOUT) as response,partial.open('xb') as output:
                final=response.geturl();require_https(final)
                attempt.update(status='DOWNLOADING',final_url=final,http_status=response.status)
                transfer_download(response,output,attempt,started,on_update)
        except (urllib.error.URLError,OSError,http.client.HTTPException) as e:
            attempt.update(status='NETWORK_FAILED',error=str(e),finished_utc=utc())
            if on_update:on_update()
            print('Download source unavailable / 下载源不可用: '+str(e),flush=True)
            if index<len(urls):print('Trying the next listed HTTPS source / 正在尝试下一个列明的 HTTPS 来源。',flush=True)
            continue
        except Exception as e:
            attempt.update(status='REJECTED',error=str(e),finished_utc=utc());raise
        digest=sha(partial);attempt['sha256']=digest
        if digest!=spec['sha256']:
            attempt.update(status='HASH_MISMATCH',finished_utc=utc())
            raise ValueError('Download hash mismatch; do not use retained file: '+str(partial))
        attempt.update(status='VERIFIED',finished_utc=utc())
        trace.update(final_url=attempt['final_url'],bytes=attempt['bytes'])
        return partial
    details='; '.join(a['url']+': '+a['error'] for a in trace['attempts'])
    raise RuntimeError('All listed HTTPS download sources failed / 所有列明的 HTTPS 下载来源均失败: '+details+
        '\nCheck Windows date/time and network/proxy certificates, then rerun setup. '
        'Do not disable certificate checks. / 请检查 Windows 日期时间及网络/代理证书后重试；不要关闭证书校验。')


def local_path(value):
    path=(ROOT/value).resolve()
    if not path.is_relative_to(ROOT):raise ValueError('Setup target leaves this checkout: '+str(path))
    return path


def fetch(spec, directory, cache=None, *, trace=None, on_update=None):
    """Never execute, replace, or reuse bytes before verifying their pinned digest."""
    trace=trace if trace is not None else {}
    target=Path(directory)/spec['name'];target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if sha(target)!=spec['sha256']:raise ValueError('Download hash mismatch; retained for inspection: '+str(target))
        return target,'verified_local_cache'
    partial=target.with_name(target.name+'.'+uuid.uuid4().hex+'.partial')
    cached=Path(cache)/spec['name'] if cache else None
    if cached and cached.is_file():
        if sha(cached)!=spec['sha256']:raise ValueError('External cache hash mismatch: '+str(cached))
        shutil.copyfile(cached,partial);origin='verified_external_cache'
    else:
        partial=download(spec,target.parent,trace,on_update)
        origin='https_download'
    if sha(partial)!=spec['sha256']:raise ValueError('Download hash mismatch; do not use retained file: '+str(partial))
    # A concurrent setup is excluded by the checkout lock in main.
    partial.rename(target)
    return target,origin


def config_path():
    return local_path(Path(os.environ.get('HECRAS_WORKFLOW_TOOLS','.tools/workflow_tools.json')))


def choose_qgis(explicit=None, interactive=True):
    from ras_workflow.qgis_runtime import environment
    if explicit:
        path,_=environment(explicit);return path
    try:
        path,_=environment();return path
    except (OSError,ValueError):pass
    candidates=[]
    for parent in [Path(os.environ[name]) for name in ['ProgramFiles'] if os.environ.get(name)]:
        for candidate in sorted(parent.glob('QGIS*')):
            try:
                path,_=environment(candidate);candidates.append(path)
            except (OSError,ValueError):pass
    if len(candidates)==1:return candidates[0]
    if not interactive:return None
    print('Select an installed QGIS LTR root (folder containing bin and apps).\n选择已安装的 QGIS LTR 根目录（包含 bin 与 apps）；仅检查并保存路径，不安装软件。')
    for i,path in enumerate(candidates,1):print(f'  {i}. {path}')
    while True:
        answer=input('Path / number, or Enter to defer / 输入路径或编号，回车暂缓: ').strip().strip('"')
        if not answer:return None
        if answer.isdecimal() and 1<=int(answer)<=len(candidates):answer=candidates[int(answer)-1]
        try:
            path,_=environment(answer);return path
        except (OSError,ValueError) as e:print(str(e))


class Setup:
    def __init__(self,args):
        self.args=args
        self.folder=local_path(Path('status/setup')/unique_id());self.folder.mkdir(parents=True)
        self.record={'status':'RUNNING','started_utc':utc(),'root':str(ROOT),'steps':[],
            'scope':'Software setup only; existing models, runs and engineering decisions are not changed'}

    def command(self,argv,timeout=1200):
        # Avoid a shell: spaces, Unicode, dollar signs and backticks are literal paths.
        with (self.folder/'setup.log').open('ab') as log:
            log.write(('\n'+subprocess.list2cmdline([str(v) for v in argv])+'\n').encode('utf-8'))
            result=subprocess.run([str(v) for v in argv],cwd=ROOT,stdout=log,stderr=log,timeout=timeout,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise RuntimeError('Command failed (exit '+str(result.returncode)+'); see '+str(self.folder/'setup.log'))

    def step(self,name,action):
        print('\n'+name,flush=True)
        record={'name':name,'status':'RUNNING'};self.record['steps'].append(record)
        save(self.folder/'setup.json',self.record)
        try:
            record['result']=action();record['status']='READY'
        except Exception as e:
            record.update(status='BLOCKED',error=str(e));print('BLOCKED / 待处理: '+str(e),flush=True)
        save(self.folder/'setup.json',self.record)
        return record['status']=='READY'

    def python(self):
        if platform.system()!='Windows' or sys.maxsize<=2**32 or sys.version_info[:2]!=(3,12):
            raise ValueError('Use Windows x64 Python 3.12; setup_workflow.cmd bootstraps the inspected build')
        target=local_path(Path('.venv'));py=target/'Scripts/python.exe'
        if target.exists():
            if not py.is_file():raise ValueError('Existing .venv is incomplete; preserve it and choose a new checkout, or have the folder reviewed before replacing it')
        else:self.command([sys.executable,'-m','venv',target],180)
        check=subprocess.run([str(py),'-I','-c',
            'import json,sys,platform;print(json.dumps(dict(prefix=sys.prefix,base=sys.base_prefix,version=list(sys.version_info[:2]),bits=64 if sys.maxsize>2**32 else 32,os=platform.system())))'],
            capture_output=True,text=True,encoding='utf-8',timeout=30,check=True)
        identity=json.loads(check.stdout)
        cfg=(target/'pyvenv.cfg').read_text(encoding='utf-8')
        if Path(identity['prefix']).resolve()!=target or identity['prefix']==identity['base'] or identity['version']!=[3,12] or identity['bits']!=64 or identity['os']!='Windows':
            raise ValueError('Existing .venv is not a compatible isolated environment; it was not replaced')
        if 'include-system-site-packages = false' not in cfg.lower():
            if 'include-system-site-packages = true' not in cfg.lower():raise ValueError('Unrecognized pyvenv.cfg; retained for inspection')
            shutil.copyfile(target/'pyvenv.cfg',self.folder/'pyvenv.before.cfg')
            lines=[('include-system-site-packages = false' if line.lower().startswith('include-system-site-packages') else line) for line in cfg.splitlines()]
            (target/'pyvenv.cfg').write_text('\n'.join(lines)+'\n',encoding='utf-8')
            identity['isolation_repaired']=True
            print('Disabled inherited global packages in this project venv; original configuration retained.\n已隔离本项目环境并备份原配置；全局 Python 保持不变。',flush=True)
        print('Installing/checking pinned packages; log / 依赖安装日志: '+str(self.folder/'setup.log'),flush=True)
        self.command([py,'-m','ensurepip','--upgrade'],180)
        self.command([py,'-m','pip','install','--disable-pip-version-check','--cache-dir',local_path(Path('.tools/pip_cache')),'-r',ROOT/'requirements.lock.txt'])
        # pip metadata can say installed while the actual tzdata directory is damaged.
        tz=subprocess.run([str(py),'-c',"from zoneinfo import ZoneInfo; print(ZoneInfo.no_cache('America/Los_Angeles'))"],capture_output=True,timeout=30)
        if tz.returncode:self.command([py,'-m','pip','install','--disable-pip-version-check','--cache-dir',local_path(Path('.tools/pip_cache')),'--force-reinstall','tzdata==2026.6'])
        self.command([py,'-m','pip','check'],120)
        return identity

    def archive(self,key):
        spec=read(ROOT/'scripts/setup_downloads.json')[key]
        record={**spec,'status':'DOWNLOADING'}
        self.record.setdefault('downloads',[]).append(record)
        try:
            path,origin=fetch(spec,local_path(Path('.tools/downloads')),self.args.download_cache,trace=record,
                on_update=lambda:save(self.folder/'setup.json',self.record))
            record.update(status='VERIFIED',path=str(path),origin=origin)
        except Exception as e:
            record.update(status='BLOCKED',error=str(e));raise
        finally:save(self.folder/'setup.json',self.record)
        return path

    def unpack(self,exe,source,target):
        # Extract into a fresh setup-owned staging directory, never over installed files.
        target.mkdir(parents=True,exist_ok=False)
        self.command([exe,'x',source,'-o'+str(target),'-y'],300)

    def extractor(self):
        if hasattr(self,'seven'):return self.seven
        small=self.archive('7zr');package=self.archive('7zip')
        stage=local_path(Path('.tools/setup_staging')/self.folder.name/'7zip')
        self.unpack(small,package,stage);self.seven=stage/'7z.exe'
        return self.seven

    def runtime(self):
        target=local_path(Path('.tools/solver_runtime/msvcr100.dll'))
        if target.is_file():
            if sha(target)!=RUNTIME_SHA:raise ValueError('Existing solver runtime has unexpected bytes; retained: '+str(target))
            return {'path':str(target),'sha256':RUNTIME_SHA,'reused':True}
        extractor=self.extractor();source=self.archive('vcredist')
        stage=local_path(Path('.tools/setup_staging')/self.folder.name)
        self.unpack(extractor,source,stage/'vc_package')
        self.unpack(extractor,stage/'vc_package/vc_red.cab',stage/'vc_dlls')
        dll=stage/'vc_dlls/F_CENTRAL_msvcr100_x64'
        if sha(dll)!=RUNTIME_SHA:raise ValueError('Extracted Microsoft runtime hash mismatch')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dll,target)
        return {'path':str(target),'sha256':sha(target),'reused':False}

    def libreoffice(self):
        path=config_path();config=read(path) if path.exists() else {}
        if config and config.get('schema_version')!='1.0':raise ValueError('Unsupported tools configuration; not overwritten')
        value=config.get('libreoffice_executable')
        executable=(ROOT/str(value)).resolve() if value else local_path(Path('.tools/LibreOfficePortable/App/libreoffice/program/soffice.com'))
        if executable.is_file():return {'path':str(executable),'reused':True}
        if value:raise ValueError('Configured LibreOffice is missing; correct its explicit path in '+str(path))
        destination=local_path(Path('.tools/LibreOfficePortable'))
        if destination.exists():raise ValueError('Existing LibreOffice folder is incomplete; preserved: '+str(destination))
        extractor=self.extractor();source=self.archive('libreoffice')
        # Keep each extracted deployment in place; Windows scanners can hold files
        # after extraction, making a directory rename fail even though reads work.
        stage=local_path(Path('.tools/portable/LibreOffice')/self.folder.name)
        self.unpack(extractor,source,stage)
        executable=stage/'App/libreoffice/program/soffice.com'
        if not executable.is_file():raise ValueError('Unexpected LibreOffice archive layout')
        if path.exists():shutil.copyfile(path,self.folder/'converter_tools.before.json')
        config.update(schema_version='1.0',libreoffice_executable=executable.relative_to(ROOT).as_posix())
        save(path,config)
        return {'path':str(executable),'reused':False}

    def qgis(self):
        selected=choose_qgis(self.args.qgis_root,not self.args.non_interactive)
        if not selected:raise ValueError('QGIS selection deferred. Install QGIS LTR normally, then rerun setup_workflow.cmd. See docs/WINDOWS_SETUP_EN.md')
        path=config_path();config=read(path) if path.is_file() else {'schema_version':'1.0'}
        if config.get('schema_version')!='1.0':raise ValueError('Unsupported tools configuration; not overwritten')
        if path.exists():shutil.copyfile(path,self.folder/'workflow_tools.before.json')
        config['qgis_root']=selected.relative_to(ROOT).as_posix() if selected.is_relative_to(ROOT) else str(selected)
        save(path,config)
        return {'path':str(selected),'configuration':str(path),'external_read_only':not selected.is_relative_to(ROOT)}

    def check(self):
        output=self.folder/'doctor.json'
        py=local_path(Path('.venv/Scripts/python.exe'))
        result=subprocess.run([str(py),str(ROOT/'workflow.py'),'doctor','--full','--require-delivery','--brief','--output',str(output)],cwd=ROOT,timeout=600)
        if result.returncode:raise RuntimeError('Environment is not ready. Read '+str(output)+'; no hydraulic result is claimed')
        return {'status':'READY','diagnostic':str(output)}


def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--non-interactive',action='store_true')
    parser.add_argument('--no-pause',action='store_true',help='Accepted by the Windows launcher')
    parser.add_argument('--qgis-root',help='Select an existing compatible QGIS installation, saved for future sessions')
    parser.add_argument('--download-cache',help='Optional read-only directory of the exact pinned archives')
    parser.add_argument('--tools-only',action='store_true',help='Legacy entry: only prepare portable runtime/converter')
    args=parser.parse_args(argv)
    from ras_workflow.common import lock
    local_path(Path('.tools')).mkdir(exist_ok=True)
    with lock(local_path(Path('.tools/setup.lock'))):
        setup=Setup(args)
        print('Setup / 安装修复: '+str(ROOT)+'\nEvidence / 日志: '+str(setup.folder),flush=True)
        python_ready=args.tools_only or setup.step('1. Project Python / 项目 Python',setup.python)
        setup.step('2. Microsoft solver runtime / 求解器运行库',setup.runtime)
        setup.step('3. Portable PDF converter / 便携 PDF 转换器',setup.libreoffice)
        if not args.tools_only:
            setup.step('4. Remember QGIS / 保存 QGIS 路径',setup.qgis)
            if python_ready:setup.step('5. Actual environment probes / 实际环境检查',setup.check)
        failed=[s for s in setup.record['steps'] if s['status']!='READY']
        setup.record.update(status='BLOCKED' if failed else 'TOOLS_PREPARED_NOT_CHECKED' if args.tools_only else 'READY',finished_utc=utc())
        save(setup.folder/'setup.json',setup.record);save(ROOT/'status/setup_latest.json',{'status':setup.record['status'],'record':rel(setup.folder/'setup.json')})
        print('\n'+setup.record['status']+' | '+str(setup.folder/'setup.json'))
        print(('Next: setup_workflow.cmd for complete installation and checking / 下一步：运行完整安装检查' if args.tools_only else 'Next: double-click start_workflow.cmd / 下一步：双击 start_workflow.cmd') if not failed else
              'Resolve the listed blockers, then rerun setup_workflow.cmd. Completed steps are reused.\n处理列出的阻塞后重新双击安装入口；已完成步骤可复用。HEC-RAS/QGIS 使用官方安装程序手动安装。')
        return 2 if failed else 0


if __name__=='__main__':raise SystemExit(main())
