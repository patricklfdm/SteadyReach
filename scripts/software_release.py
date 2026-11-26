"""Build or verify a signed Windows source and wheel release from a pinned Git commit."""
import argparse
import email
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

CODE = Path(__file__).resolve().parents[1]
SIGNER = Path(__file__).with_name('release_signature.ps1')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path,record):
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2,sort_keys=True),encoding='utf-8')


def signature(action,key,manifest,signature_file,private=None):
    command=['powershell.exe','-NoProfile','-NonInteractive','-File',str(SIGNER),'-Action',action,
             '-PublicKey',str(key.resolve()),'-Manifest',str(manifest.resolve()),'-Signature',str(signature_file.resolve())]
    if private is not None:
        command+=['-PrivateKey',str(private.resolve())]
    subprocess.run(command,check=True,capture_output=True)


def normalize(name):
    return re.sub(r'[-_.]+','-',name).lower()


def wheel_inventory(folder,lock):
    pinned={}
    for line in lock.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        name,version=line.split(';',1)[0].strip().split('==')
        pinned[normalize(name)]=version
    packages=[]
    for wheel in sorted(folder.glob('*.whl')):
        with ZipFile(wheel) as contents:
            names=contents.namelist()
            meta,=[n for n in names if n.endswith('.dist-info/METADATA')]
            metadata=email.message_from_bytes(contents.read(meta))
            name=normalize(metadata['Name'])
            if pinned.pop(name,None)!=metadata['Version']:
                raise ValueError('Unexpected wheel or version: '+wheel.name)
            license_files=[n for n in names if n.startswith(meta.rsplit('/',1)[0]+'/') and
                           ('/licenses/' in n.lower() or 'license' in Path(n).name.lower() or 'copying' in Path(n).name.lower())]
            licenses=metadata.get_all('License-Expression') or [v for v in metadata.get_all('Classifier',[]) if v.startswith('License ::')]
            if not licenses and metadata.get('License'):
                licenses=[metadata['License'].splitlines()[0]]
            packages.append(dict(name=metadata['Name'],version=metadata['Version'],
                purl='pkg:pypi/'+name+'@'+metadata['Version'],file=wheel.name,sha256=sha(wheel),
                declared_license=licenses or ['See wheel metadata'],license_files=license_files))
    if pinned:
        raise ValueError('Missing locked wheels: '+', '.join(sorted(pinned)))
    return packages


def build(args):
    out=args.output.resolve();out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():
        raise ValueError('Choose a new artifact directory')
    repository=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=CODE,text=True).strip())
    commit=subprocess.check_output(['git','rev-parse','--verify',args.revision+'^{commit}'],cwd=repository,text=True).strip()
    with tempfile.TemporaryDirectory(dir=out.parent) as temp:
        stage=Path(temp)/'release';stage.mkdir()
        software=stage/'SteadyReach.zip'
        subprocess.run(['git','archive','--format=zip','--output',str(software),commit],cwd=repository,check=True)
        with ZipFile(software) as z:
            lock=z.read('requirements.lock.txt').decode('utf-8-sig')
            if any(n.startswith(('projects/','status/','.tools/','.venv/','.git/')) for n in z.namelist()):
                raise ValueError('Private or generated data present in the distribution tree')
        wheels=wheel_inventory(args.wheels,lock)
        with ZipFile(stage/'Windows_wheels.zip','w',compression=ZIP_DEFLATED,compresslevel=1) as z:
            for wheel in wheels:
                z.write(args.wheels/wheel['file'],wheel['file'])
        software_license=subprocess.check_output(['git','show',commit+':LICENSE'],cwd=CODE)
        (stage/'LICENSE.txt').write_bytes(software_license)
        write(stage/'SBOM.json',dict(product='SteadyReach',version=args.version,git_commit=commit,platform='Windows x64',
            python='3.12.14',components=wheels,external=['HEC-RAS','QGIS','PDF converter','Microsoft solver runtime']))
        write(stage/'LICENSES.json',dict(project='MIT',license_file='LICENSE.txt',components=[
            {k:p[k] for k in ('name','version','file','declared_license','license_files')} for p in wheels]))
        manifest=stage/'RELEASE.json'
        write(manifest,dict(schema='steadyreach_release_1',version=args.version,git_commit=commit,python='3.12.14',
            architecture='win_amd64',signing_key_sha256=sha(args.trusted_key),
            files={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in stage.iterdir()}))
        signature('sign',args.trusted_key,manifest,stage/'RELEASE.sig',args.private_key)
        verify(stage,args.trusted_key)
        stage.rename(out)
    return out


def verify(release,key):
    release=release.resolve()
    if key.resolve().is_relative_to(release):
        raise ValueError('Select the administrator-pinned public key outside the release folder')
    signature('verify',key,release/'RELEASE.json',release/'RELEASE.sig')
    manifest=json.loads((release/'RELEASE.json').read_text(encoding='utf-8'))
    expected={'LICENSE.txt','SBOM.json','LICENSES.json','SteadyReach.zip','Windows_wheels.zip'}
    if (manifest.get('schema')!='steadyreach_release_1' or manifest['signing_key_sha256']!=sha(key)
            or set(manifest['files'])!=expected or {p.name for p in release.iterdir()}!=expected|{'RELEASE.json','RELEASE.sig'}):
        raise ValueError('Release inventory or trusted key differs')
    for name,entry in manifest['files'].items():
        path=release/name
        if path.resolve()!=path or path.stat().st_size!=entry['bytes'] or sha(path)!=entry['sha256']:
            raise ValueError('Release artifact changed: '+name)
    return manifest


def unpack(blob,destination):
    with ZipFile(blob) as archive:
        seen=set()
        for info in archive.infolist():
            name=PurePosixPath(info.filename)
            if (not name.parts or name.is_absolute() or '..' in name.parts or any(':' in s or '\\' in s for s in name.parts)
                    or info.filename.casefold() in seen or info.external_attr>>28==10):
                raise ValueError('Unexpected member: '+info.filename)
            seen.add(info.filename.casefold())
            target=destination.joinpath(*name.parts)
            if info.is_dir():
                target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(info) as src,target.open('xb') as dst:
                    shutil.copyfileobj(src,dst)


def install(release,key,destination,python):
    manifest=verify(release,key)
    identity=subprocess.check_output([str(python),'-I','-c',
        'import platform,struct;print(platform.python_version(),platform.system(),struct.calcsize("P")*8)'],text=True).strip()
    if identity!=manifest['python']+' Windows 64':
        raise ValueError('Select Windows x64 Python '+manifest['python'])
    destination=destination.resolve();destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        raise ValueError('Use an unused installation directory')
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        temp=Path(temporary);stage=temp/'app';stage.mkdir()
        unpack(release/'SteadyReach.zip',stage)
        wheels=temp/'wheels';wheels.mkdir();unpack(release/'Windows_wheels.zip',wheels)
        known=wheel_inventory(wheels,(stage/'requirements.lock.txt').read_text(encoding='utf-8'))
        sbom=json.loads((release/'SBOM.json').read_text(encoding='utf-8'))
        if known!=sbom['components']:
            raise ValueError('Offline dependency inventory mismatch')
        # Windows launcher scripts include their final absolute interpreter path.
        stage.rename(destination)
        pending = destination/'INSTALL_IN_PROGRESS.json'
        write(pending,dict(manifest_sha256=sha(release/'RELEASE.json'),status='INSTALLING'))
        subprocess.run([str(python),'-I','-m','venv',str(destination/'.venv')],check=True)
        executable=destination/'.venv/Scripts/python.exe'
        subprocess.run([str(executable),'-I','-m','pip','--isolated','install','--disable-pip-version-check',
                        '--no-index','--no-cache-dir','--find-links',str(wheels),'-r',str(destination/'requirements.lock.txt')],check=True)
        subprocess.run([str(executable),'-I','-m','pip','check'],check=True)
        examples = {p.relative_to(destination).as_posix():sha(p) for p in (destination/'examples').rglob('*') if p.is_file()}
        write(destination/'INSTALLED_RELEASE.json',dict(version=manifest['version'],git_commit=manifest['git_commit'],
              manifest_sha256=sha(release/'RELEASE.json'),trusted_key_sha256=sha(key),shipped_examples=examples))
        pending.unlink()
    return destination


def verify_installation(installation,release,key):
    manifest=verify(release,key)
    if (installation/'INSTALL_IN_PROGRESS.json').exists():
        raise ValueError('Offline installation did not finish')
    record=json.loads((installation/'INSTALLED_RELEASE.json').read_text(encoding='utf-8'))
    if record['manifest_sha256']!=sha(release/'RELEASE.json') or record['git_commit']!=manifest['git_commit']:
        raise ValueError('Installed release identity differs')
    expected=set()
    with ZipFile(release/'SteadyReach.zip') as contents:
        for info in contents.infolist():
            if info.is_dir():continue
            target=installation/info.filename
            expected.add(info.filename)
            if target.resolve()!=target or not target.is_file() or target.stat().st_size!=info.file_size:
                raise ValueError('Installed software member changed: '+info.filename)
            with contents.open(info) as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=sha(target):
                    raise ValueError('Installed software checksum differs: '+info.filename)
    # Python modules and templates can change runtime behavior even if the extra file
    # never appeared in a release. Local project and storage directories are separate.
    for name in ('ras_workflow','scripts'):
        for p in (installation/name).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.relative_to(installation).as_posix() not in expected:
                raise ValueError('Unexpected installed software member: '+str(p.relative_to(installation)))
    return manifest


def main():
    cli=argparse.ArgumentParser(description=__doc__);sub=cli.add_subparsers(dest='action',required=True)
    build_cmd=sub.add_parser('build')
    for n in ('wheels','private-key','trusted-key','output'):
        build_cmd.add_argument('--'+n,type=Path,required=True)
    build_cmd.add_argument('--revision',required=True);build_cmd.add_argument('--version',required=True)
    for a in ('verify','install'):
        cmd=sub.add_parser(a);cmd.add_argument('--release',required=True,type=Path);cmd.add_argument('--trusted-key',required=True,type=Path)
        if a=='install':
            cmd.add_argument('--destination',required=True,type=Path);cmd.add_argument('--python',required=True,type=Path)
    args=cli.parse_args()
    if args.action=='build':
        args.wheels=args.wheels.resolve(strict=True)
        print(build(args))
    elif args.action=='verify':print(verify(args.release,args.trusted_key)['git_commit'])
    else:print(install(args.release,args.trusted_key,args.destination,args.python))


if __name__=='__main__':
    main()
