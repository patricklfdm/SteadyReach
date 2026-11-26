"""Resume the failed delivery stage against the last intact native calculation."""
from .common import ROOT, intact, item, lock, read, rel, safe_path, save
from .delivery_pair import check
from .qa import verified_profiles


def eligible(previous,current,job):
    if not previous or previous.get('status')!='NEEDS_EXPORT':
        return None
    ref=previous.get('receipt')
    if not ref or not intact([ref]):
        raise ValueError('Restore the previous attempt receipt')
    old=previous['identity']['evidence'];now=current['evidence']
    if any(old.get(k)!=now.get(k) for k in ('job','inputs','code','engine','cancelled')):
        return None
    receipt=read(ROOT/ref['path'])
    if (receipt.get('requested_project',receipt['project'])!=rel(safe_path(ROOT,job['project'])) or
            receipt['scenario_id']!=job['scenario'] or not intact([receipt['summary']]+receipt['inputs']+receipt['code'])):
        return None
    if original_run := receipt.get('export_from'):
        if not intact([original_run]):
            raise ValueError('Earlier native export receipt changed')
    return ref


def resume(request,folder):
    import time
    from . import site_delivery
    start=time.monotonic()
    ref=request['export_from'];original=read(ROOT/ref['path'])
    if not intact([ref,original['summary']]+original['inputs']+original['code']):raise ValueError('Previous native evidence changed')
    summary_path=ROOT/original['summary']['path']
    summary=read(summary_path);h=summary['hydraulics']
    if not intact([summary['hydraulic_results']]) or read(ROOT/summary['hydraulic_results']['path'])!=h:
        raise ValueError('Native extraction no longer matches the summary')
    verified_profiles(h)
    job_root = summary_path.parent
    native_root = (ROOT/h['raw_hdf']['path']).parent.parent
    retained_roots = (job_root/'reports', job_root/'native_outputs', native_root)
    durable = [entry for entry in original['artifacts']
               if any((ROOT/entry['path']).is_relative_to(base) for base in retained_roots)]
    if not durable or not intact(durable):
        raise ValueError('Restore the original native evidence and authored reports before retrying delivery')
    destination=(ROOT/original['project']).parent/'exports'/('recovered_'+folder.name)
    with lock((ROOT/original['project']).parent/'project.lock'):
        try:
            result=site_delivery.generate(summary_path,destination)
        except (OSError,ValueError,RuntimeError) as error:
            result=dict(status='INCOMPLETE',error=str(error),recovery_kind=site_delivery.failure_kind(error))
            save(folder/'delivery_error.json',result)
    ready=result.get('status') in ('READY_FOR_REVIEW','READY_NATIVE_ONLY')
    if ready:
        pair=check(ROOT/result['complete']['path'],ROOT/result['minimal']['path'])
        if pair['run_id']!=h['run_id'] or pair['native_hdf_sha256']!=h['raw_hdf']['sha256']:
            raise ValueError('Delivery belongs to another calculation')
    artifacts = durable + [item(p) for p in destination.rglob('*') if p.is_file()]
    receipt=dict(original,workflow_status='COMPLETED' if ready else 'WAITING_FOR_DELIVERY_REVIEW',
                 export_from=ref,solver_reused=True,delivery=result,artifacts=[ref,summary['hydraulic_results'],h['raw_hdf'],*artifacts],
                 stage_seconds=dict(solver=0,delivery=round(time.monotonic()-start,3),total=round(time.monotonic()-start,3)))
    final=folder/'attempt_receipt.json';save(final,receipt)
    save(folder/'worker_result.json',dict(exit_code=0 if ready else 3,receipt=item(final)))
    return 0 if ready else 3
