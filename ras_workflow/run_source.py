"""Keep one copy of the exact workflow sources shared by matching native runs."""
import hashlib
from tempfile import NamedTemporaryFile
from pathlib import Path
from zipfile import ZIP_DEFLATED,ZipFile
from .common import ROOT,digest,item,lock


def freeze(entries):
    folder=ROOT/'status/run_sources'
    folder.mkdir(parents=True,exist_ok=True)
    key=digest(entries)
    dest=folder/(key+'.zip')
    with lock(folder/(key+'.lock')):
        if dest.exists():
            with ZipFile(dest) as archive:
                if archive.namelist()!=[r['path'] for r in entries] or any(
                    hashlib.sha256(archive.read(r['path'])).hexdigest()!=r['sha256'] for r in entries):
                    raise ValueError('Restore the exact workflow source archive before running')
            return item(dest,'workflow_source_archive')
        with NamedTemporaryFile(dir=folder,suffix='.partial',delete=False) as stream:
            tmp=Path(stream.name)
        try:
            with ZipFile(tmp,'w',compression=ZIP_DEFLATED) as archive:
                for r in entries:
                    raw=(ROOT/r['path']).read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('Workflow sources changed during setup')
                    archive.writestr(r['path'],raw)
            tmp.replace(dest)
        finally:tmp.unlink(missing_ok=True)
    return item(dest,'workflow_source_archive')
