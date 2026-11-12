"""Recoverable operator work outside immutable QA packets and solver receipts."""
import base64
from collections import Counter
from pathlib import Path
from .common import ROOT, digest, intact, item, lock, read, rel, safe_path, save, unique_id, utc
from . import qa_review, inputs

WAITING='WAITING_FOR_QA_REVIEW'
STATES=['OPEN','INVESTIGATE','EXPLAINED_CONDITIONAL','RESOLVED_BY_RERUN']
MAX_UPLOAD=10_000_000


def packet_check(path):
    path=safe_path(ROOT,path);p=read(path);m=read(path.parent/'manifest.json')
    if p.get('schema_version')!='qa_review_1.0' or not intact(m['files']+m['sources']):
        raise ValueError('QA packet or source changed; prepare a new packet / QA 证据已变化，请重新生成')
    keys=[r['key'] for r in p['issues']]
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate issue identity in QA packet')
    return p


def prepare(packet_path, output, project=None):
    pp=safe_path(ROOT,packet_path);packet_check(pp)
    folder=safe_path(ROOT,output);sp=folder/'session.json'
    if sp.exists():
        s=read(sp)
        if s['packet']!=item(pp):raise ValueError('Session belongs to another packet')
        return view(sp)
    folder.mkdir(parents=True,exist_ok=True)
    with lock(folder/'session.lock'):
        if sp.exists():raise ValueError('Session was created concurrently; reopen it')
        spec=read(pp.parent/'decisions.template.json')
        if spec['packet']!=item(pp):raise ValueError('Decision template binding changed')
        save(sp,dict(schema_version='qa_session_1.0',packet=item(pp),status=WAITING,revision=0,
            project=rel(safe_path(ROOT,project)) if project else None,created_utc=utc(),updated_utc=utc(),
            project_inputs=inputs.dependencies(safe_path(ROOT,project),read(safe_path(ROOT,project))) if project else [],
            reviewer='',decisions=spec['decisions'],uploads=[],submissions=[],events=[]))
    return view(sp)


def load(session_path, revision=None):
    sp=safe_path(ROOT,session_path);s=read(sp)
    if s.get('schema_version')!='qa_session_1.0' or not intact([s['packet']]):raise ValueError('QA session packet changed')
    pp=ROOT/s['packet']['path'];p=packet_check(pp)
    if s.get('project'):
        if not intact(s['project_inputs']):raise ValueError('Project inputs changed; review is historical / 输入已变化，当前复核属于历史运行')
        state_path=(ROOT/s['project']).parent/'state.json'
        if state_path.exists():
            latest=read(state_path).get('latest_summary')
            if latest and (not intact([latest]) or (read(ROOT/latest['path']).get('hydraulics') or {}).get('run_id')!=p['run_id']):
                raise ValueError('Project has another latest attempt; reopen its project entry / 项目已有新运行，请重新打开项目入口')
    if revision is not None and (type(revision)!=int or revision!=s['revision']):
        raise ValueError('Draft changed in another tab; reload before editing / 草稿已变化，请刷新')
    if s['uploads'] and not intact(s['uploads']):raise ValueError('Uploaded evidence changed')
    return sp,s,p


def hotspots(packet):
    groups={}
    for row in packet['issues']:
        i=row['issue'];key=(i.get('profile'),i.get('station'))
        g=groups.setdefault(key,dict(profile=key[0],station=key[1],count=0,codes=Counter(),actions=[],figure=row.get('figure')))
        g['count']+=1;g['codes'][i['code']]+=1
        a=i['recommended_action']
        if a not in g['actions']:g['actions'].append(a)
    # Counts are ledger entries, not independent defects or an engineering risk score.
    return sorted(groups.values(),key=lambda g:(-g['count'],str(g['profile']),str(g['station'])))


def view(session_path):
    sp,s,p=load(session_path)
    result=dict(s,session=rel(sp),run_id=p['run_id'],project_id=p['project_id'],issues=p['issues'],
        warning_coverage=p['warning_coverage'],hotspots=hotspots(p),
        preview=qa_review.closure_status(p,s['decisions']),engineering_acceptance='NOT_ASSESSED')
    result['artifacts']=artifacts(sp,s,p)
    result['section_locator']=p.get('section_locator')
    warning_template=(ROOT/s['packet']['path']).parent/'native_warning_review/selection.template.json'
    result['warning_assistant']=read(warning_template) if warning_template.exists() else None
    from .investigations import guide
    result['investigation_guides']={r['key']:guide(r['issue']) for r in p['issues']}
    result['investigations']=s.get('investigations',[])
    result['scenario_id']=next((read(ROOT/e['path'])['hydraulics']['scenario_id'] for e in p.get('sources',[]) if e['path'].endswith('/summary.json') and intact([e]) and (read(ROOT/e['path']).get('hydraulics') or {}).get('run_id')==p['run_id']),None)
    return result


def prepare_investigation(session_path,body):
    from .investigations import prepare as prepare_study
    sp=safe_path(ROOT,session_path)
    with lock(sp.parent/'session.lock'):
        sp,s,p=load(sp,body['revision'])
        if s['status']=='REVIEW_CANCELLED':raise ValueError('Resume review before preparing an investigation')
        if not s.get('project'):raise ValueError('Open this QA packet from its project before preparing a study')
        evidence=[e for e in s['uploads'] if digest(e) in body.get('evidence_ids',[])]
        if not evidence:raise ValueError('Select uploaded evidence supporting the proposed range')
        folder=sp.parent/'investigations'/unique_id();folder.mkdir(parents=True)
        request=dict(issue_keys=body.get('issue_keys'),reviewer=body.get('reviewer'),hypothesis=body.get('hypothesis'),ranges=body.get('ranges'),sources=evidence)
        save(folder/'request.json',request)
        result=prepare_study(s['packet']['path'],s['project'],body['scenario'],folder/'request.json',folder/'prepared')
        entry=item(folder/'prepared/investigation.json');s.setdefault('investigations',[]).append(entry)
        update(sp,s,'INVESTIGATION_PREPARED');return dict(result,revision=s['revision'])


def artifacts(sp,s,p):
    entries={e['path']:e for e in s['uploads']}
    if p.get('section_locator'):
        e=p['section_locator']
        if not intact([e]):raise ValueError('Section location evidence changed')
        entries[e['path']]=e
    for e in s.get('investigations',[]):
        if not intact([e]):continue
        binding=read(ROOT/e['path'])
        for child in [e,binding['request'],binding['study']]:
            if intact([child]):entries[child['path']]=child
        template=(ROOT/binding['study']['path']).parent/'review.template.json'
        if template.exists():entries[rel(template)]=item(template,'pending_study_review_template')
    folder=(ROOT/s['packet']['path']).parent
    for row in p['issues']:
        if row.get('figure'):
            f=safe_path(folder,row['figure'])
            if not f.is_relative_to(folder):raise ValueError('Figure leaves QA packet')
            entries[rel(f)]=item(f,'computed_figure')
    for e in s['submissions']:
        for key in ['spec','closure']:
            if e.get(key):entries[e[key]['path']]=e[key]
    return [dict(e,id=digest(e)) for e in entries.values()]


def update(sp,s,event):
    s['revision']+=1;s['updated_utc']=utc()
    s['events'].append(dict(at_utc=s['updated_utc'],revision=s['revision'],event=event))
    save(sp,s)
    return dict(status=s['status'],revision=s['revision'],session=rel(sp))


def save_draft(session_path, body):
    sp=safe_path(ROOT,session_path)
    with lock(sp.parent/'session.lock'):
        sp,s,p=load(sp,body['revision'])
        if s['status']=='REVIEW_CANCELLED':raise ValueError('Resume the cancelled review before editing')
        reviewer=body.get('reviewer','')
        if not isinstance(reviewer,str) or len(reviewer)>300:raise ValueError('Reviewer must be text, at most 300 characters')
        current={d['key']:d for d in s['decisions']};seen=set();allowed={digest(e) for e in s['uploads']}
        changes=body.get('changes',[])
        if not isinstance(changes,list) or len(changes)>len(current):raise ValueError('Invalid issue changes')
        if 'investigation_drafts' in body:
            drafts=body['investigation_drafts'];fields={'parameter','low','high','basis','hypothesis','measurement','evidence'}
            if not isinstance(drafts,dict) or not set(drafts)<=set(current):raise ValueError('Unknown investigation draft issue')
            for draft in drafts.values():
                if not isinstance(draft,dict) or not set(draft)<=fields or any(not isinstance(v,str) or len(v)>10000 for v in draft.values()):raise ValueError('Invalid investigation form draft')
            s['investigation_drafts']=drafts
        for d in changes:
            if not isinstance(d,dict) or d.get('key') not in current or d['key'] in seen:raise ValueError('Unknown or repeated issue key')
            seen.add(d['key'])
            if d.get('disposition') not in STATES:raise ValueError('Unsupported disposition')
            for k in ['reason','action']:
                if not isinstance(d.get(k),str) or len(d[k])>10000:raise ValueError('Reason/action must be text, at most 10000 characters')
            evidence=d.get('evidence',[])
            if not isinstance(evidence,list) or len(evidence)>50 or any(digest(e) not in allowed for e in evidence):raise ValueError('Attach uploaded evidence only')
            current[d['key']]={k:d[k] for k in ['key','disposition','reason','action']};current[d['key']]['evidence']=evidence
        s.update(reviewer=reviewer,decisions=list(current.values()),status=WAITING)
        return update(sp,s,'DRAFT_SAVED')


def upload(session_path, revision, name, content):
    sp=safe_path(ROOT,session_path)
    if not isinstance(name,str) or Path(name).name!=name or any(c in name for c in '/\\:') or len(name)>160:
        raise ValueError('Use a plain evidence filename')
    suffix=Path(name).suffix.lower()
    if suffix not in ['.pdf','.png','.jpg','.jpeg','.txt','.csv','.json']:raise ValueError('Evidence: PDF, PNG, JPG, TXT, CSV or JSON')
    if not isinstance(content,str) or len(content)>MAX_UPLOAD*4//3+8:raise ValueError('Evidence exceeds 10 MB')
    try:raw=base64.b64decode(content,validate=True)
    except Exception as e:raise ValueError('Invalid evidence encoding') from e
    if not 0<len(raw)<=MAX_UPLOAD:raise ValueError('Evidence must contain 1 byte to 10 MB')
    if suffix=='.pdf' and not raw.startswith(b'%PDF-'):raise ValueError('Not a PDF file')
    if suffix=='.png' and not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Not a PNG file')
    if suffix in ['.jpg','.jpeg'] and not raw.startswith(b'\xff\xd8\xff'):raise ValueError('Not a JPEG file')
    with lock(sp.parent/'session.lock'):
        sp,s,p=load(sp,revision)
        if s['status']=='REVIEW_CANCELLED':raise ValueError('Resume the cancelled review first')
        if sum(e['size_bytes'] for e in s['uploads'])+len(raw)>100_000_000:raise ValueError('Session evidence exceeds 100 MB')
        target=sp.parent/'evidence'/(unique_id()+suffix);target.parent.mkdir(exist_ok=True);target.write_bytes(raw)
        e=item(target,'operator_uploaded_evidence');s['uploads'].append(e)
        s.setdefault('upload_names',{})[e['path']]=name
        result=update(sp,s,'EVIDENCE_UPLOADED');result['evidence']=e;return result


def submit(session_path, revision):
    sp=safe_path(ROOT,session_path)
    with lock(sp.parent/'session.lock'):
        sp,s,p=load(sp,revision)
        if s['status']=='REVIEW_CANCELLED':raise ValueError('Resume the cancelled review first')
        spec=dict(schema_version='qa_decisions_1.0',packet=s['packet'],reviewer=s['reviewer'],decisions=s['decisions'])
        qa_review.validate_decisions(ROOT/s['packet']['path'],spec)
        out=sp.parent/'submissions'/unique_id();out.mkdir(parents=True)
        save(out/'decisions.json',spec)
        result=qa_review.closure(ROOT/s['packet']['path'],out/'decisions.json',out/'review')
        s['status']=result['status'];s['submissions'].append(dict(created_utc=utc(),spec=item(out/'decisions.json'),
            closure=item(out/'review/closure.json'),status=result['status']))
        response=update(sp,s,'REVIEW_SUBMITTED');response['closure']=result;return response


def cancel(session_path, revision, reviewer, reason, confirmed):
    if confirmed is not True or not isinstance(reviewer,str) or not reviewer.strip() or not isinstance(reason,str) or not reason.strip():
        raise ValueError('Explicit reviewer, reason and confirmation required to stop review')
    if len(reviewer)>300 or len(reason)>10000:raise ValueError('Cancellation text exceeds limit')
    sp=safe_path(ROOT,session_path)
    with lock(sp.parent/'session.lock'):
        sp,s,p=load(sp,revision);s.update(status='REVIEW_CANCELLED',reviewer=reviewer,cancellation=dict(reason=reason,at_utc=utc()))
        return update(sp,s,'REVIEW_CANCELLED_RESULTS_PRESERVED')


def resume(session_path, revision):
    sp=safe_path(ROOT,session_path)
    with lock(sp.parent/'session.lock'):
        sp,s,p=load(sp,revision);s['status']=WAITING
        return update(sp,s,'REVIEW_RESUMED')


def import_warnings(session_path, body):
    """Observed scope is explicit; new evidence produces a new packet/session."""
    from .native_warnings import import_export
    sp=safe_path(ROOT,session_path)
    with lock(sp.parent/'session.lock'):
        sp,s,p=load(sp,body['revision'])
        if s['status']=='REVIEW_CANCELLED':raise ValueError('Resume the cancelled review first')
        if body.get('scope_confirmed') is not True:raise ValueError('Confirm the actual native selection before importing')
        template=(ROOT/s['packet']['path']).parent/'native_warning_review/selection.template.json'
        if not template.exists():raise ValueError('This packet already has a complete warning export')
        by_id={digest(e):e for e in s['uploads']}
        text=by_id[body['text_id']];ui=[by_id[k] for k in body.get('ui_ids',[])]
        if not ui or any(Path(e['path']).suffix.lower() not in ['.png','.jpg','.jpeg','.pdf'] for e in ui):
            raise ValueError('Attach actual native selection screenshots or PDF')
        if Path(text['path']).suffix.lower()!='.txt':raise ValueError('Select a native TXT warning export')
        selected=read(template);selected.update(observer=body.get('observer'),ui_evidence=ui,
            empty_table_observed=body.get('empty_table_observed') is True)
        if body.get('method')=='Clipboard':
            selected.update(method='HEC-RAS Summary Errors Warnings Notes / Clipboard',plan_label=body.get('plan_label_observed'))
        elif body.get('method')!='File':raise ValueError('Select the observed File or Clipboard export method')
        out=sp.parent/'warning_imports'/unique_id();out.mkdir(parents=True)
        save(out/'selection.json',selected)
        summary_path=ROOT/p['sources'][0]['path']
        import_export(summary_path,ROOT/text['path'],out/'selection.json',out/'bundle.json',body.get('encoding','utf-8-sig'))
        qa_review.prepare(summary_path,out/'packet',warnings=out/'bundle.json')
        next_view=prepare(out/'packet/review_packet.json',out/'session',s.get('project'))
        s['events'].append(dict(event='WARNINGS_IMPORTED_NEW_PACKET',at_utc=utc(),session=next_view['session']))
        update(sp,s,'OLD_DECISIONS_RETAINED_WITH_OLD_PACKET')
        if s.get('project'):
            project=ROOT/s['project']
            with lock(project.parent/'project.lock'):
                # Recheck after the potentially long plot preparation.
                load(sp)
                save(project.parent/'review_checkpoint.json',dict(schema_version='review_checkpoint_1.0',updated_utc=utc(),
                    project=rel(project),summary=item(summary_path),run_id=p['run_id'],status=WAITING,session=next_view['session']))
        return dict(status=WAITING,session=next_view['session'],prior_session=rel(sp),decisions_transferred=False,
                    note='New warning evidence has a new ledger; prior decisions and comparison remain in the prior packet')
