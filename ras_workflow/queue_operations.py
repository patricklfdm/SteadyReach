"""Local queue reservations, explicit operator controls and shareable timing evidence."""
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED
import json
import time

from .common import ROOT, identifier, lock, read, save, unique_id, utc


class SpaceUnavailable(ValueError):
    """A queue can retry after another reservation is released."""


def seconds(start,end):
    return round((datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds(),3)


@contextmanager
def reserve(folder, required, root=ROOT):
    """Coordinate space among local queues. A dead process releases its OS lease."""
    base=root/'status/queue_space'
    lease=folder/'space.lock';record=base/(unique_id()+'.json')
    with lock(lease):
        # Inspect leases while holding the registry lock, before publishing ours.
        for retry in range(40):
            try:
                with lock(base/'registry.lock'):
                    reserved=0
                    for path in base.glob('*.json'):
                        try:other=read(path)
                        except FileNotFoundError:continue
                        target=(root/other['lease']).resolve()
                        if not target.is_relative_to(root):raise ValueError('Invalid space lease')
                        try:
                            with lock(target):pass
                        except RuntimeError:
                            reserved+=other['bytes']
                        else:
                            path.unlink(missing_ok=True)
                    free=shutil.disk_usage(folder).free
                    if required>free-reserved:
                        raise SpaceUnavailable(f'Insufficient available space / 可用空间不足: {required} bytes needed, {max(0,free-reserved)} available')
                    save(record,dict(bytes=required,lease=lease.relative_to(root).as_posix(),created=utc()))
                break
            except RuntimeError:
                if retry==39:raise
                time.sleep(.05)
        try:
            yield dict(reserved_bytes=required,free_at_start=free,other_reserved_bytes=reserved)
        finally:
            record.unlink(missing_ok=True)


def requested_bytes(job,identity):
    # Allow administrators to reserve more for unusually large terrain or packages.
    size=sum(e.get('size_bytes',0) for e in identity['evidence']['inputs'])
    value=job.get('reserve_bytes',max(256*1024**2,size*4))
    if type(value) is not int or value<1:
        raise ValueError('reserve_bytes must be a positive integer')
    return value


def control(output,job_id,action):
    from .common import safe_path
    output=safe_path(ROOT,output)
    job_id=identifier(job_id)
    if action not in ('cancel','resume'):raise ValueError('Invalid queue control')
    state=read(output/'queue_state.json')
    if job_id not in state['jobs']:raise ValueError('Unknown queue job')
    marker=output/'controls'/(job_id+'.json')
    with lock(marker.with_suffix('.lock')):
        save(marker,dict(action=action,at=utc()))
    return dict(action=action,job=job_id)


def is_cancelled(output,job_id):
    path=output/'controls'/(job_id+'.json')
    return path.is_file() and read(path).get('action')=='cancel'


def support(output):
    """Allowlist aggregate fields. Never include IDs, absolute paths, raw logs or field data."""
    from .common import safe_path
    state=read(safe_path(ROOT,output)/'queue_state.json')
    jobs=[]
    known={'IN_PROGRESS','FAILED','COMPLETED','BLOCKED','CANCELLED','INTERRUPTED','WAITING_FOR_INPUT','NEEDS_EXPORT','LOW_SPACE'}
    for seq,attempts in enumerate(state['jobs'].values(),1):
        summary=[]
        for row in attempts:
            timing={}
            for stage,amount in (row.get('stage_seconds') or {}).items():
                if stage in ('terrain','solver','reports','delivery','total') and isinstance(amount,(int,float)):
                    timing[stage]=amount
            summary.append(dict(status=row.get('status') if row.get('status') in known else 'OTHER',
                stage_seconds=timing,reused_native=bool(row.get('solver_reused'))))
        jobs.append(dict(number=seq,attempts=summary))
    return dict(schema='steadyreach_support_1',jobs=jobs,scope='Workstation queue counts, status codes and elapsed seconds')


def export_support(output,dest,expected):
    from .common import digest
    data=support(output)
    if digest(data)!=expected:raise ValueError('Preview the current support data before exporting')
    target=Path(dest)
    with ZipFile(target,'x',ZIP_DEFLATED) as archive:
        archive.writestr('Support.json',json.dumps(data,indent=2).encode())
    return target
