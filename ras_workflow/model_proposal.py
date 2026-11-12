from .common import runtime_scratch
"""Explicit source-to-configuration proposals, reviewed before conditional use.

Never synthesizes missing structures or treats map clicks as authorization.
"""
import copy
import math
import os
import tempfile
from pathlib import Path
import numpy as np

from .common import ROOT, finite, intact, item, read, rel, safe_path, save, sha, utc
from .inputs import load, gate, geometry_errors
from .site_review import apply_review
from .sections import intersect

GROUP_NUMBERS={'count','span_ft','rise_ft','length_ft','us_invert_ft','ds_invert_ft',
               'entrance_loss','exit_loss','depth_blocked_ft','distance_us_ft'}
ELEVATIONS={'us_invert_ft','ds_invert_ft'}
LENGTHS={'span_ft','rise_ft','length_ft','us_invert_ft','ds_invert_ft','depth_blocked_ft','distance_us_ft'}
FACTORS={'international_ft':1.,'US_survey_ft':(1200/3937)/.3048,'m':1/.3048}


def verified_review(path):
    path=safe_path(ROOT,path);r=read(path)
    if r.get('schema_version')!='reviewed_site_inputs_1.0' or not intact(r.get('sources',[])):
        raise ValueError('Reviewed inputs or their source packet changed')
    with tempfile.TemporaryDirectory(prefix='review_promotion_',dir=runtime_scratch()) as tmp:
        actual=apply_review(r['sources'][0]['path'],r['sources'][1]['path'],Path(tmp)/'check.json')
    strip=lambda d:{k:v for k,v in d.items() if k!='created_utc'}
    if strip(actual)!=strip(r):raise ValueError('Reviewed values differ from the bound original decisions')
    packet=read(ROOT/r['sources'][0]['path'])
    return r,packet


def mapping_template(project, reviewed, output):
    path,c=load(project);rp=safe_path(ROOT,reviewed);r,p=verified_review(rp)
    if p['source_project']!=item(path):raise ValueError('Review belongs to a different project snapshot')
    out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Choose a new mapping specification')
    value=dict(schema_version='model_mapping_1.0',project=item(path),reviewed_inputs=item(rp),purpose=None,
        mappings=[],available_selected_items=[dict(id=f['id'],candidate=f['selected_candidate']) for f in r['fields'] if f['decision']=='RETAIN_CANDIDATE'],
        instructions='Add mappings with review_id, target, basis, source_unit and source_datum where required. No free-form replacement values are accepted.')
    save(out,value);return value


def converted(candidate,mapping,field):
    raw=candidate.get('raw_value')
    if isinstance(raw,bool):raise ValueError('Boolean source value is not numeric')
    try:value=float(raw)
    except (TypeError,ValueError):raise ValueError('Selected source has no numeric raw_value')
    if not finite(value):raise ValueError('Nonfinite source value')
    source_unit=mapping.get('source_unit')
    observed=candidate.get('unit')
    if field in LENGTHS:
        allowed={'ft':{'international_ft','US_survey_ft'},'international ft':{'international_ft'},
                 'international_ft':{'international_ft'},'US survey foot':{'US_survey_ft'},'m':{'m'}}
        if source_unit not in allowed.get(observed,set()):raise ValueError('Source length unit missing, ambiguous or inconsistent; record an explicit supported interpretation')
        value*=FACTORS[source_unit]
    elif field=='count':
        if source_unit!='count' or observed not in [None,'count'] or not value.is_integer():raise ValueError('Barrel count must be an integer with explicit count interpretation')
        value=int(value)
    elif source_unit!='dimensionless' or observed not in [None,'dimensionless']:
        raise ValueError('Loss coefficient requires explicit dimensionless source interpretation')
    return value


def apply_mapping(config,geometry,mapping,selected,packet):
    if set(mapping)-{'review_id','target','basis','source_unit','source_datum'}:
        raise ValueError('Unknown mapping fields; values must come from selected evidence')
    if not isinstance(mapping.get('basis'),str) or not mapping['basis'].strip():raise ValueError('Mapping interpretation/basis required')
    chosen=selected.get(mapping.get('review_id'))
    if not chosen or chosen['decision']!='RETAIN_CANDIDATE' or chosen['selected_candidate'] is None:
        raise ValueError('Mapping requires an explicitly retained existing candidate')
    value=chosen['selected_candidate'];parts=mapping.get('target','').split('.')
    if config['case_kind']!='software_validation' and value.get('evidence_class')=='synthetic':raise ValueError('Synthetic candidate cannot become a site input')
    original=value;kind=next(f['kind'] for f in packet['map']['features']+packet['fields'] if f['id']==chosen['id'])
    if parts[:2]==['geometry','structure'] and len(parts)==5 and parts[2]=='groups' and parts[3].isdigit() and parts[4] in GROUP_NUMBERS:
        if geometry is None or kind!='parameter':raise ValueError('Structure mapping requires complete base geometry and a parameter source')
        index=int(parts[3]);field=parts[4]
        if index>=len(geometry['structure']['groups']):raise ValueError('Unknown target culvert group')
        if field in ELEVATIONS:
            datum=value.get('vertical_datum')
            if not datum or datum!=mapping.get('source_datum') or datum!=geometry['vertical_datum']:
                raise ValueError('Invert source and geometry datum must be known and equal; no implicit offset')
        parent=geometry['structure']['groups'][index];new=converted(value,mapping,field)
    elif len(parts)==4 and parts[:2]==['geometry','cross_sections'] and parts[2].isdigit() and parts[3]=='bank_stations_ft':
        if geometry is None or kind!='section':raise ValueError('Bank mapping requires complete base geometry and a retained section')
        index=int(parts[2]);field=parts[3]
        if index>=len(geometry['cross_sections']):raise ValueError('Unknown target section')
        parent=geometry['cross_sections'][index]
        if any(value.get(k)!=parent.get(k) for k in ['cutline_xy','station_ft','elevation_ft']):
            raise ValueError('Selected cutline/samples differ from target section; complete geometry must be reviewed separately')
        if mapping.get('source_unit')!='international_ft':raise ValueError('Sampled bank station unit must be international_ft')
        new=value.get('bank_stations_ft')
        if not isinstance(new,list) or len(new)!=2:raise ValueError('Two selected bank stations required')
    elif len(parts)==5 and parts[0]=='scenarios' and parts[2]=='profiles' and parts[4]=='flow_cfs':
        if kind!='hydrology' or mapping.get('source_unit')!='cfs':raise ValueError('Flow requires a reviewed hydrology candidate in cfs')
        scenario=next((s for s in config['scenarios'] if s['id']==parts[1]),None)
        parent=next((p for p in scenario['profiles'] if p['id']==parts[3]),None) if scenario else None
        if parent is None:raise ValueError('Unknown target scenario/profile')
        field='flow_cfs';new=value.get('flow_cfs')
        if not finite(new) or new<=0:raise ValueError('Selected hydrology has no positive cfs value')
        if value.get('raw_unit') not in ['ft^3/s','cfs','m^3/s']:raise ValueError('Hydrology source unit unavailable')
    else:raise ValueError('Unsupported mapping target: '+mapping.get('target',''))
    before=copy.deepcopy(parent.get(field));parent[field]=copy.deepcopy(new)
    if field=='flow_cfs':
        parent['source']='Reviewed source '+chosen['id']+'; '+str(value.get('locator'))
        parent['review_status']='CONDITIONALLY_REVIEWED';parent['approved_for_model']=True
    return dict(target=mapping['target'],review_id=chosen['id'],before=before,after=new,basis=mapping['basis'],
        source_candidate=original,source_unit=mapping.get('source_unit'),source_datum=mapping.get('source_datum'),
        target_unit='cfs' if field=='flow_cfs' else 'international_ft' if field in LENGTHS or field=='bank_stations_ft' else mapping.get('source_unit'))


def prepare(project,reviewed,mapping_path,output):
    path,c=load(project);rp=safe_path(ROOT,reviewed);mp=safe_path(ROOT,mapping_path);r,p=verified_review(rp);mapping=read(mp)
    if c.get('native_project'):raise ValueError('Promotion applies to explicit builder configurations, not native benchmarks')
    if p['source_project']!=item(path) or r['project_id']!=c['project_id']:raise ValueError('Site review/project snapshot mismatch')
    if mapping.get('schema_version')!='model_mapping_1.0' or mapping.get('project')!=item(path) or mapping.get('reviewed_inputs')!=item(rp):raise ValueError('Mapping source identity mismatch')
    if not mapping.get('purpose') or not isinstance(mapping.get('mappings'),list):raise ValueError('Explicit purpose and mappings required')
    geometry_path=safe_path(path.parent,c['geometry']) if c.get('geometry') else None
    g=read(geometry_path) if geometry_path else None;draft=copy.deepcopy(c);changes=[];seen=set();selected={f['id']:f for f in r['fields']}
    for m in mapping['mappings']:
        if m.get('target') in seen:raise ValueError('Duplicate mapping target')
        seen.add(m.get('target'));changes.append(apply_mapping(draft,g,m,selected,p))
    blockers=geometry_errors(g,c['case_kind']=='software_validation') if g else ['Complete reviewed external geometry and structure inputs remain missing']
    if g:
        if c.get('terrain',{}).get('vertical_datum') and c['terrain']['vertical_datum']!=g['vertical_datum']:blockers.append('Terrain/geometry datum mismatch')
        cuts=[np.asarray(s['cutline_xy'],dtype=float) for s in g['cross_sections']]
        for i,a in enumerate(cuts):
            for b in cuts[i+1:]:
                if any(intersect(*a[k:k+2],*b[j:j+2]) for k in range(len(a)-1) for j in range(len(b)-1)):blockers.append('Intersecting external cross sections');break
    folder=safe_path(ROOT,output);folder.mkdir(parents=True,exist_ok=False)
    if g:
        if g==read(geometry_path):(folder/'geometry.json').write_bytes(geometry_path.read_bytes())
        else:save(folder/'geometry.json',g)
    for key in ['raster','provenance']:
        if draft.get('terrain',{}).get(key):draft['terrain'][key]=os.path.relpath(safe_path(path.parent,draft['terrain'][key]),folder)
    draft.update(geometry='geometry.json' if g else None,authorization=None,model_proposal_pending=True)
    draft.pop('configuration_approval',None)
    for key in ['reference_results','benchmark_preparation']:draft.pop(key,None)
    save(folder/'project.draft.json',draft)
    for scenario in draft['scenarios']:
        check,_=gate(folder/'project.draft.json',draft,scenario)
        blockers.extend(x for x in check['blocking_items'] if x not in ['Model configuration proposal is pending explicit conditional approval','Site-specific conditional scenario authorization/evidence; no inherited site approval'])
    sources=[item(path),item(rp),item(mp)]+r['sources']+p['sources']
    if geometry_path:sources.append(item(geometry_path))
    result=dict(schema_version='model_proposal_1.0',created_utc=utc(),status='BLOCKED' if blockers else 'PROPOSED_REQUIRES_CONDITIONAL_APPROVAL',
        project_id=c['project_id'],case_kind=c['case_kind'],purpose=mapping['purpose'],sources=sources,
        files=[item(folder/'project.draft.json')]+([item(folder/'geometry.json')] if g else []),changes=changes,
        blocking_items=sorted(set(blockers)),unmapped_retained_items=[i for i,v in selected.items() if v['decision']=='RETAIN_CANDIDATE' and i not in {m['review_id'] for m in mapping['mappings']}],
        engineering_acceptance='NOT_ASSESSED')
    save(folder/'proposal.json',result)
    save(folder/'approval.template.json',dict(schema_version='model_approval_1.0',proposal=item(folder/'proposal.json'),decision='PENDING',reviewer=None,basis=None,authority_evidence=[]))
    for lang,title in [('EN','Proposed model input changes'),('CN','模型输入修改提案')]:
        lines=['# '+title,'','[English](DIFF_EN.md) | [简体中文](DIFF_CN.md)','',result['status'],'',mapping['purpose'],'',
               '| Target / 目标 | Before / 原值 | After / 新值 | Unit / 单位 | Source / 来源 |','|---|---|---|---|---|']
        for change in changes:lines.append('| '+' | '.join(str(change[k]).replace('|','/') for k in ['target','before','after','target_unit','review_id'])+' |')
        lines+=['','## Blocking items / 阻塞项','']+['- '+x for x in result['blocking_items']]
        lines+=['','Conditional configuration approval is separate from engineering acceptance.' if lang=='EN' else '条件性配置使用授权与工程接受分别记录。']
        (folder/f'DIFF_{lang}.md').write_text('\n'.join(lines),encoding='utf-8')
    return result


def approve(proposal_path,approval_path,output):
    pp=safe_path(ROOT,proposal_path);ap=safe_path(ROOT,approval_path);p=read(pp);a=read(ap)
    if p.get('schema_version')!='model_proposal_1.0' or p['blocking_items'] or p['status']!='PROPOSED_REQUIRES_CONDITIONAL_APPROVAL':raise ValueError('Proposal has unresolved input blockers')
    if not intact(p['sources']+p['files']):raise ValueError('Proposal inputs changed; prepare and review again')
    if a.get('schema_version')!='model_approval_1.0' or a.get('proposal')!=item(pp) or a.get('decision')!='APPROVE_CONDITIONAL_CONFIGURATION':raise ValueError('Exact proposal and explicit conditional decision required')
    if not isinstance(a.get('reviewer'),str) or not a['reviewer'].strip() or not a.get('basis') or not intact(a.get('authority_evidence',[])):raise ValueError('Named reviewer, basis and intact authority evidence required')
    # Rebuild from the original mapped evidence before accepting even an intact proposal.
    with tempfile.TemporaryDirectory(prefix='review_proposal_',dir=runtime_scratch()) as tmp:
        rebuilt=prepare(p['sources'][0]['path'],p['sources'][1]['path'],p['sources'][2]['path'],Path(tmp)/'proposal')
        if rebuilt['changes']!=p['changes'] or rebuilt['blocking_items']!=p['blocking_items']:raise ValueError('Proposal differs from source-derived changes')
        if read(Path(tmp)/'proposal/geometry.json')!=read(pp.parent/'geometry.json'):raise ValueError('Proposal geometry differs from reviewed inputs')
        original=read(pp.parent/'project.draft.json');other=read(Path(tmp)/'proposal/project.draft.json')
        for key in ['raster','provenance']:
            if original.get('terrain',{}).get(key):
                original['terrain'][key]=str(safe_path(pp.parent,original['terrain'][key]));other['terrain'][key]=str(safe_path(Path(tmp)/'proposal',other['terrain'][key]))
        if original!=other:raise ValueError('Proposal project differs from reviewed inputs')
    folder=safe_path(ROOT,output);folder.mkdir(parents=True,exist_ok=False)
    (folder/'geometry.json').write_bytes((pp.parent/'geometry.json').read_bytes())
    c=read(pp.parent/'project.draft.json')
    for key in ['raster','provenance']:
        if c.get('terrain',{}).get(key):c['terrain'][key]=os.path.relpath(safe_path(pp.parent,c['terrain'][key]),folder)
    c.update(authorization='authorization.json',model_proposal_pending=False,geometry_review=a['basis'],configuration_approval='approval_receipt.json')
    save(folder/'authorization.json',dict(project_id=p['project_id'],allowed_geometry_sha256=sha(folder/'geometry.json'),scope='conditional configuration only',
        proposal=item(pp),review=item(ap),authority=a['reviewer'],basis=a['basis'],authority_evidence=a['authority_evidence'],engineering_acceptance='NOT_ASSESSED'))
    save(folder/'project.json',c)
    receipt=dict(status='CONDITIONALLY_AUTHORIZED_NOT_ENGINEERING_ACCEPTED',created_utc=utc(),sources=[item(pp),item(ap)]+p['sources']+p['files']+a['authority_evidence'],
        files=[item(folder/n) for n in ['project.json','geometry.json','authorization.json']],reviewer_identity='OPERATOR_ATTESTED',engineering_acceptance='NOT_ASSESSED')
    save(folder/'approval_receipt.json',receipt)
    for s in c['scenarios']:
        check,_=gate(folder/'project.json',c,s)
        if check['status']!='READY_CONDITIONAL':raise ValueError('Approved configuration fails input gates: '+str(check['blocking_items']))
    return folder/'project.json'
