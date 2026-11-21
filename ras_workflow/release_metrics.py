"""Same-machine operational measures; missing timestamps remain unknown."""
from datetime import datetime
from pathlib import Path
from .common import intact, read
from .operator_log import inventory


def seconds(row):
    start=row.get('started_utc');finish=row.get('finished_utc')
    if not start or not finish:return None
    return (datetime.fromisoformat(finish)-datetime.fromisoformat(start)).total_seconds()


def metrics(project,session=None):
    folder=Path(project)
    tasks=[read(p) for p in sorted((folder/'tasks').glob('*/task.json'))]
    elapsed=[seconds(t) for t in tasks]
    attempts=[]
    for path in sorted((folder/'approved').glob('*/jobs/*/summary.json')):
        r=read(path)
        delivery=path.parent/'delivery'/'delivery.json'
        pack=read(delivery) if delivery.is_file() else {}
        h=r.get('hydraulics') or {}
        manifests=[(pack.get(k) or {}).get('manifest') for k in ('complete','minimal')]
        pair=bool(pack.get('status')=='READY_FOR_REVIEW' and pack.get('mapped') is True and h.get('run_id') and
                  h['run_id']==pack.get('run_id') and all(manifests) and intact(manifests))
        attempts.append(dict(attempt=r.get('attempt_id'),computed=r.get('calculation_status'),delivery=pack.get('status'),
                            mapped=pack.get('mapped'),first_attempt_pair_registered=pair,finished=r.get('finished_at_utc')))
    clock=folder/'pilot_session.json'
    if session is None and clock.is_file():session=read(clock)
    session=session or {}
    tagged=session.get('intervals',[])
    result={}
    previous=None
    for row in tagged:
        if row['kind'] not in ('engineer','external_wait'):raise ValueError('Unknown session interval')
        start=datetime.fromisoformat(row['started_utc']);end=datetime.fromisoformat(row['finished_utc'])
        if not start.tzinfo or not end.tzinfo or end<start or previous and start<previous:
            raise ValueError('Measured intervals must be ordered, timezone-aware and nonoverlapping')
        result[row['kind']]=result.get(row['kind'],0)+(end-start).total_seconds()
        previous=end
    if session and session.get('project_id')!=folder.name:raise ValueError('Timing session refers to a different project')
    interventions=session.get('developer_interventions')
    if interventions is not None and (not isinstance(interventions,list) or not all(isinstance(x,str) and x.strip() for x in interventions)):
        raise ValueError('Document each developer intervention')
    marker_only=bool(session.get('checkpoints')) and not (tagged or session.get('open') or interventions)
    solver=[];compute=[]
    for path in sorted((folder/'approved').glob('*/jobs/*/solver__*/execution.json')):
        native=read(path)
        start=native.get('started_utc') or native.get('started_at_utc')
        end=native.get('finished_utc') or native.get('finished_at_utc')
        solver.append(seconds(dict(started_utc=start,finished_utc=end)))
        stages={row['stage']:row['time_utc'] for row in native.get('stages',[])}
        if native.get('solver_invoked'):
            compute.append(seconds(dict(started_utc=stages.get('compute_invoked'),finished_utc=stages.get('compute_returned'))))
    return dict(project_id=folder.name,tasks=len(tasks),machine_task_seconds=round(sum(elapsed),2) if tasks and None not in elapsed else None,
        native_solver_wall_seconds=sum(solver) if solver and None not in solver else None,
        compute_call_wall_seconds=sum(compute) if compute and None not in compute else None,
        unfinished_interval=session.get('open'),
        pilot_checkpoints=session.get('checkpoints',[]),human_acceptance='NOT_ASSESSED',
        active_engineer_seconds=result.get('engineer'),external_wait_seconds=result.get('external_wait'),
        developer_interventions=len(interventions) if interventions is not None and not marker_only else None,
        first_mapped_delivery=attempts[0]['first_attempt_pair_registered'] if attempts else None,
        attempts=attempts,interaction_receipts=inventory(folder))


def cohort(groups,projects):
    """Count each explicitly named site once across its listed project editions."""
    if not isinstance(groups,dict) or not groups:raise ValueError('Specify a nonempty site-to-project list')
    by_key={row['project_id']:row for row in projects};seen=set();sites=[]
    for name,keys in groups.items():
        if not name.strip() or not isinstance(keys,list) or not keys or not all(isinstance(k,str) and k in by_key for k in keys):
            raise ValueError('List each site and its selected projects in the cohort')
        if seen.intersection(keys) or len(keys)!=len(set(keys)):raise ValueError('Each project belongs to exactly one site')
        seen.update(keys)
        attempts=[a for key in keys for a in by_key[key]['attempts']]
        known=bool(attempts) and all(a.get('finished') for a in attempts)
        first=min(attempts,key=lambda a:datetime.fromisoformat(a['finished'])) if known else {}
        sites.append(dict(site=name,project_ids=keys,solver_attempts=len(attempts),first_attempt=first.get('attempt'),
                          first_mapped_pair=first.get('first_attempt_pair_registered')))
    eligible=[s for s in sites if s['first_mapped_pair'] is not None]
    successes=sum(s['first_mapped_pair'] for s in eligible)
    return dict(sites=sites,eligible_sites=len(eligible),first_successes=successes,unknown_sites=len(sites)-len(eligible),
                first_success_rate=successes/len(eligible) if eligible else None,
                definition='First recorded completed or failed solver attempt per declared site, both mapped package manifests registered for the same run. Unobserved attempts are unknown.')
