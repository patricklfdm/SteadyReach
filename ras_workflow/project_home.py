"""One project entry, with independent computation, input and QA states."""
from .common import ROOT, digest, intact, item, lock, read, rel, safe_path, save, unique_id, utc
from . import inputs, intake


def inspect(project):
    requested=safe_path(ROOT,project);path=intake.resolve(requested);path,c=inputs.load(path)
    state=read(path.parent/'state.json') if (path.parent/'state.json').exists() else {}
    active=intake.control(path)
    result=dict(schema_version='project_home_1.0',checked_utc=utc(),project=rel(requested),active_project=rel(path),
        project_id=c['project_id'],title=c['title'],workflow_status=state.get('workflow_status',state.get('status','NOT_STARTED')),
        calculation_status=state.get('calculation_status','NOT_STARTED'),input_adequacy='NOT_ASSESSED',
        hydraulic_qa_status='NOT_STARTED',review_status='NOT_STARTED',engineering_acceptance='NOT_ASSESSED',
        issues=[],reports=[],artifacts=[],next_actions=[],latest_summary=state.get('latest_summary'),run_id=None)
    scenario=c['scenarios'][0]['id'] if c.get('scenarios') else None
    gate=inputs.gate(path,c,c['scenarios'][0])[0] if scenario else dict(status='BLOCKED',blocking_items=['No scenario'])
    result['input_adequacy']=gate.get('input_adequacy_status','INCOMPLETE')
    result['input_gaps']=gate.get('blocking_items',[])
    if active:result['intake_status']=active['status']
    if active and active['status']=='CANCELLED':result['workflow_status']='CANCELLED'
    elif (active and active['status']==intake.WAITING) or gate['status']=='BLOCKED':result['workflow_status']=intake.WAITING
    if result['workflow_status'] in [intake.WAITING,'CANCELLED']:
        result['next_actions'].append(dict(kind='INPUT_REVIEW',command='workflow.py intake --project "'+rel(requested)+'" --scenario '+str(scenario)+(' --refresh' if result['workflow_status']=='CANCELLED' else '')))
    latest=state.get('latest_summary')
    if latest and not intact([latest]):
        result['issues'].append('LATEST_SUMMARY_CHANGED');result['calculation_status']='EVIDENCE_CHANGED'
    elif latest:
        summary=read(ROOT/latest['path']);hyd=summary.get('hydraulics')
        # Older state files omit calculation_status. The verified latest
        # summary is authoritative; do not display a real legacy run as unstarted.
        result['calculation_status']=summary.get('calculation_status',result['calculation_status'])
        result['artifacts'].append(latest)
        result['scenario_ids']=[p['profile_id'] for p in hyd['profiles']] if hyd else []
        result['report_units']={k:hyd.get(k) for k in ['unit','datum']} if hyd else None
        result['run_input_adequacy']=summary.get('gate',{}).get('input_adequacy_status')
        if hyd:
            result.update(run_id=hyd['run_id'],hydraulic_qa_status=hyd['hydraulic_qa_status'],review_status='WAITING_FOR_QA_REVIEW')
            if not intact([summary['hydraulic_results'],hyd['raw_hdf'],hyd['raw_controller']]):result['issues'].append('SOLVER_EVIDENCE_CHANGED')
            if not intact(state.get('current_input_manifest',[])):result['issues'].append('INPUTS_CHANGED_SINCE_RUN')
        from .report_catalog import inspect as report_editions
        catalog=report_editions(ROOT/latest['path']);result['issues']+=catalog['issues']
        result['report_history']=[{k:v for k,v in e.items() if k!='content'} for e in catalog['history']]
        if catalog['latest']:
            rm=catalog['latest']['content']
            if rm:
                for report in rm['reports']:
                    for kind in ['pdf','docx']:
                        e=report[kind];result['reports'].append(dict(e,format=kind,language=report.get('language'),detail=report.get('detail'),verified=intact([e]),visual_review=rm.get('visual_review','NOT_RECORDED')))
                result['artifacts']+=result['reports']
        checkpoint=path.parent/'review_checkpoint.json'
        if checkpoint.exists():
            cp=read(checkpoint);result['checkpoint']=cp
            if cp.get('run_id')==result['run_id'] and cp.get('session'):
                from .qa_session import load
                try:
                    sp,s,p=load(ROOT/cp['session']);result['review_status']=s['status'];result['qa_session']=rel(sp)
                    if s['submissions']:
                        last=s['submissions'][-1]
                        if intact([last['spec'],last['closure']]):
                            result['artifacts'] += [last['spec'],last['closure']]
                            result['qa_decisions']=last['spec']
                            if s['status']==last['status']:
                                result['hydraulic_qa_status']=read(ROOT/last['closure']['path'])['hydraulic_qa_status']
                        else:result['issues'].append('REVIEW_SUBMISSION_CHANGED')
                except (ValueError,OSError,KeyError) as e:result['issues'].append('REVIEW_EVIDENCE_CHANGED: '+str(e))
            elif cp.get('run_id')!=result['run_id']:result['issues'].append('PREVIOUS_REVIEW_BELONGS_TO_ANOTHER_RUN')
        if hyd:result['next_actions'].append(dict(kind='QA_REVIEW',command='workflow.py project-open --project "'+rel(requested)+'"'))
    if result['issues']:
        result['review_status']='STALE_OR_CHANGED_EVIDENCE'
        result['hydraulic_qa_status']='REVIEW_REQUIRED'
    if not latest and gate['status']!='BLOCKED':
        result['next_actions'].append(dict(kind='RUN',command='workflow.py run --project "'+rel(requested)+'" --scenario '+str(scenario)))
    result['artifacts']=[dict(e,id=digest(e)) for e in result['artifacts']]
    result['scenario_id']=scenario
    result['scenarios']=[s['id'] for s in c.get('scenarios',[])]
    result['project_sha256']=item(path)['sha256']
    result['progress']=[
        dict(stage='INPUT',status=result['input_adequacy'],action='INPUT_REVIEW'),
        dict(stage='CALCULATION',status=result['calculation_status'],action='RUN'),
        dict(stage='QA',status=result['review_status'],action='QA_REVIEW'),
        dict(stage='REPORT',status='AVAILABLE' if result['reports'] else 'NOT_AVAILABLE',action='REPORT')]
    result['recovery']=[]
    result['previous_runs']=[]
    seen_runs={result['run_id']}
    for sp in sorted((path.parent/'jobs').glob('*/summary.json'),reverse=True):
        if latest and rel(sp)==latest['path']:continue
        try:
            old=read(sp);oh=old.get('hydraulics')
            if oh and oh['run_id'] not in seen_runs and oh['project_id']==c['project_id'] and intact([old['hydraulic_results'],oh['raw_hdf'],oh['raw_controller']]):
                result['previous_runs'].append(dict(summary=item(sp),run_id=oh['run_id'],finished_at_utc=old['finished_at_utc']))
                seen_runs.add(oh['run_id'])
        except (ValueError,OSError,KeyError):continue
    if latest and intact([latest]):
        result['recovery'].append(dict(kind='REPORT',command='workflow.py report --summary "'+latest['path']+'" --output "reports/recovery_'+unique_id()+'"'))
        if result['run_id']:
            from .site_delivery import latest as delivery_latest, settings_for
            result['delivery_settings']=settings_for(path)
            result['delivery_mapped']=c.get('terrain',{}).get('mode')!='not_applicable'
            result['delivery']=state.get('delivery') or dict(status='NOT_STARTED')
            try:
                package=delivery_latest(ROOT/latest['path'])
                if package:
                    result['delivery']=package
                    if result['workflow_status']=='WAITING_FOR_DELIVERY_REVIEW':result['workflow_status']='COMPLETED_PENDING_REVIEWS'
            except (ValueError,OSError,KeyError) as e:result['delivery']=dict(status='EVIDENCE_CHANGED',error=str(e))
            result['progress'].append(dict(stage='DELIVERY',status=result['delivery']['status'],action='DELIVERY'))
            result['recovery'].append(dict(kind='DELIVERY',command='workflow.py site-delivery --summary "'+latest['path']+'" --output "deliveries/'+c['project_id']+'_'+unique_id()+'"'))
            for key in ['complete','minimal']:
                if result['delivery'].get(key):
                    folder=ROOT/result['delivery'][key]['path']
                    for p in [folder/'READ_ME.txt',folder/'PACKAGE_MANIFEST.json',folder/'Graph/Exhibit_EN.pdf']:
                        if p.is_file():
                            entry=item(p);result['artifacts'].append(dict(entry,id=digest(entry)))
    if state.get('errors'):
        result['recovery'].append(dict(kind='RETRY',errors=state['errors'],command='workflow.py run --project "'+rel(requested)+'" --scenario '+str(scenario)))
    return result


def register(project, summary_path):
    """Cheap checkpoint after each calculation; never edits an old run receipt."""
    path=safe_path(ROOT,project);summary=read(summary_path);hyd=summary.get('hydraulics')
    if not hyd:return
    cp=path.parent/'review_checkpoint.json';old=read(cp) if cp.exists() else {}
    save(cp,dict(schema_version='review_checkpoint_1.0',updated_utc=utc(),project=rel(path),
        summary=item(summary_path),run_id=hyd['run_id'],status='WAITING_FOR_QA_REVIEW',
        session=old.get('session') if old.get('run_id')==hyd['run_id'] else None))


def prepare(project, warnings=None, baseline=None, baseline_warnings=None):
    from . import qa_review, qa_session
    requested=safe_path(ROOT,project);path=intake.resolve(requested)
    with lock(path.parent/'project.lock'):
        home=inspect(requested)
        if home['issues']:
            home.pop('qa_session',None)
            return home
        if home['run_id']:
            if home.get('qa_session') and not any([warnings,baseline,baseline_warnings]):return home
            out=path.parent/'reviews'/unique_id()
            qa_review.prepare(home['latest_summary']['path'],out/'packet',baseline,warnings,baseline_warnings)
            qa_session.prepare(out/'packet/review_packet.json',out/'session',path)
            save(path.parent/'review_checkpoint.json',dict(schema_version='review_checkpoint_1.0',updated_utc=utc(),
                project=rel(path),summary=home['latest_summary'],run_id=home['run_id'],status='WAITING_FOR_QA_REVIEW',session=rel(out/'session/session.json')))
    return inspect(requested)
