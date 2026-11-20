"""Bounded best-first review of actual native steady-flow messages and DEM alternatives."""
from collections import Counter

from pyproj import CRS

from . import app_outputs, study
from .common import ROOT, digest, intact, item, lock, read, save, unique_id, utc
from .coverage_study import case_configuration
from .inputs import dependencies, geometry_errors
from .qa import verified_profiles
from .result_atlas import native_rows
from .revision_inputs import bound_inputs, station_key
from .river import is_river
from .section_spacing import confirm_geometry
from .terrain_auto import Sampler
from .warning_geometry import extend_ends, infill, validate_layout

KIND = 'native_warning_review'
CRITICAL = {'NATIVE_ENERGY_NOT_BALANCED','NATIVE_CRITICAL_DEPTH_FALLBACK','NATIVE_SLOPE_AREA_FALLBACK'}
NUMERICAL = {'NATIVE_VELOCITY_HEAD_CHANGE','NATIVE_LARGE_ENERGY_LOSS','NATIVE_CONVEYANCE_CHANGE'}
CLEARANCE = .30


def category(row):
    text = row['text'].lower()
    if 'slope too steep for slope area' in text:
        return 'NATIVE_SLOPE_AREA_FALLBACK'
    if 'multiple critical depths' in text:
        return 'NATIVE_MULTIPLE_CRITICAL_DEPTH'
    if 'extended vertically during the critical depth calculations' in text:
        return 'NATIVE_VERTICAL_EXTENSION_CRITICAL_SEARCH'
    if 'parabolic search method failed' in text:
        return 'NATIVE_CRITICAL_SEARCH_METHOD_CHANGE'
    return row['code']


def assessment(summary, entry, reference=None):
    hyd = summary['hydraulics']
    verified_profiles(hyd)
    if not summary.get('native_supplement'):
        raise ValueError('Full native warnings export required / 请先补齐原生警告导出')
    bundle = app_outputs.validate(summary['native_supplement'])
    if bundle['warning_scope'] not in app_outputs.FULL_SCOPES or not bundle['warnings']:
        raise ValueError('Native warning coverage is incomplete / 原生警告范围不完整')
    bound = read(ROOT/bundle['summary']['path'])['hydraulics']
    if (bound['run_id'], bound['raw_hdf']) != (hyd['run_id'], hyd['raw_hdf']):
        raise ValueError('Warning export belongs to a different solver run')
    records = [dict(r, category=category(r)) for r in bundle['warnings']['records']]
    warnings = [r for r in records if r['severity']=='WARNING']
    severity = Counter(r['severity'] for r in records)
    codes = Counter(r['category'] for r in warnings)
    affected = {(r['profile'],station_key(r['station'])) for r in warnings if r['category'] in CRITICAL}
    stages, envelope, margins = {}, {}, []
    for row in native_rows(hyd):
        rs = station_key(row['rs'])
        w = row['wse_ft']
        stages.setdefault(row['profile'], {})[rs] = w
        envelope[rs] = max(w, envelope.get(rs,w))
        for z in (row['elevation_ft'][0],row['elevation_ft'][-1]):
            margins.append(z-w)
            if z<w:
                affected.add((row['profile'],rs))
    delta, at = 0., None
    if reference is not None:
        if set(reference)!=set(stages):
            raise ValueError('Profile inventory changed')
        for profile, values in reference.items():
            for rs, original in values.items():
                difference = stages[profile][rs]-original
                if abs(difference)>abs(delta):
                    delta, at = difference, [profile,rs]
    critical = sum(codes[k] for k in CRITICAL)
    numerical = sum(codes[k] for k in NUMERICAL)
    metrics = dict(affected_locations=len(affected), warnings=len(warnings), notes=severity['NOTE'], errors=severity['ERROR'], critical=critical,
                   numerical=numerical, divided=codes['NATIVE_DIVIDED_FLOW'], wet_ends=sum(v<0 for v in margins),
                   low_ends=sum(v<=CLEARANCE for v in margins), min_margin_ft=min(margins),
                   section_count=len(envelope), max_wse_delta_ft=abs(delta), signed_delta_ft=delta, delta_at=at)
    return dict(summary=entry, run_id=hyd['run_id'], hdf=hyd['raw_hdf'], native_file=bundle['warnings']['source'],
                warning_coverage=bundle['warning_scope'], metrics=metrics, codes=dict(codes), records=records,
                stages=stages, envelope=envelope)


def rank(row):
    m = row['metrics']
    return tuple(m[k] for k in ('errors','affected_locations','critical','wet_ends','numerical','low_ends','warnings','max_wse_delta_ft'))


def proposals(action, geometry, audit, sampler, maximum):
    if action=='joint_overbank':
        from .warning_overbank import sweep
        return sweep(geometry,{float(k):v for k,v in audit['envelope'].items()},sampler,maximum,CLEARANCE)
    if action.startswith('extent'):
        water = {float(k):v for k,v in audit['envelope'].items()}
        return extend_ends(geometry, water, sampler, maximum, CLEARANCE, action=='extent_bend')
    targets = Counter()
    upstream = {b['rs']:a['rs'] for a,b in zip(geometry['cross_sections'],geometry['cross_sections'][1:])}
    for r in audit['records']:
        if r['severity']!='WARNING' or r['category'] not in CRITICAL | NUMERICAL:
            continue
        rs = float(r['station'])
        if action=='infill_upstream':
            rs = upstream.get(rs)
        if rs is not None:
            targets[rs] += 3 if r['category'] in CRITICAL else 1
    return infill(geometry, targets, sampler)


def make_plan(model, body, folder):
    if not intact([model['summary']]):
        raise ValueError('Baseline result changed')
    summary = read(ROOT/model['summary']['path'])
    config, geometry, refs = bound_inputs(summary)
    source = ROOT/model['active_project']
    if not is_river(geometry) or len(geometry.get('flowlines',[]))!=1:
        raise ValueError('Single continuous workflow-built river reach required / 仅支持工作流构建的单一连续河段')
    if read(source)!=config or read(source.parent/config['geometry'])!=geometry:
        raise ValueError('Current inputs differ from the computed baseline')
    rounds = body.get('maximum_rounds',8)
    maximum = body.get('maximum_width_ft',2000)
    if type(rounds) is not int or not 1<=rounds<=12 or type(maximum) not in (int,float) or not 120<=maximum<=2000:
        raise ValueError('Choose 1–12 computations and a 120–2000 ft width limit / 请核对轮数及宽度')
    base = assessment(summary,model['summary'])
    spec = dict(type=KIND, policy_version=1, maximum_rounds=rounds, maximum_width_ft=maximum, clearance_ft=CLEARANCE,
                actions=['extent_bend','joint_overbank','infill_downstream','infill_upstream','extent_straight'], added_per_round=10,
                channel_geometry_basis=geometry.get('channel_geometry_basis'), metrics=base['metrics'],
                kept_fixed=['discharge','Manning coefficients','boundaries','flow regime','original channel and banks'])
    save(folder/'specification.json', spec)
    plan = dict(id=KIND, analysis_kind=KIND, case_kind=config['case_kind'],project_id=config['project_id'],
                scenario_id=model['scenario'], status='DRAFT_REQUIRES_REVIEW', specification=item(folder/'specification.json'),
                source_project=item(source), source_geometry=item(source.parent/config['geometry']),
                source_inputs=dependencies(source,config), evidence=[model['summary'],base['native_file'],base['hdf']]+refs,
                policy=spec,cases=[],measurement_topics=[],engineering_acceptance='NOT_ASSESSED')
    save(folder/'study.json',plan)
    return dict(entry=item(folder/'study.json'),plan=plan,token=item(folder/'study.json')['sha256'])


def prepare(model,body):
    from . import app_core as core
    packet = make_plan(model, body, core.folder(model['id'])/'warning_reviews'/unique_id())
    model['pending_study'] = packet['entry']
    core.persist(model,'PREPARE_WARNING_REVIEW')
    return packet


def physical_id(geometry):
    return digest([[r.get(k) for k in ('rs','station_ft','elevation_ft','cutline_xy','bank_stations_ft','reach_lengths_ft')]
                   for r in geometry['cross_sections']])


def save_once(path,value):
    if path.exists() and read(path)!=value:
        raise ValueError('Warning trial evidence changed: '+str(path))
    if not path.exists():
        save(path,value)


def run(sp, plan, rp, review, timeout):
    folder = sp.parent
    with lock(folder/'study.lock'):
        return search(folder,sp,plan,rp,review,timeout)


def search(folder,sp,plan,rp,review,timeout):
    spec = read(ROOT/plan['specification']['path'])
    if spec.get('policy_version')!=1 or spec!=plan['policy']:
        raise ValueError('Preview the current warning review policy again')
    journal_path = folder/'execution.json'
    journal = read(journal_path) if journal_path.exists() else dict(study=item(sp),review=item(rp),cases=[],started_utc=utc())
    if journal['study']!=item(sp) or journal['review']!=item(rp):
        raise ValueError('Study/review changed')
    source = plan['evidence'][0]
    base = read(ROOT/source['path'])
    config, geometry, _ = bound_inputs(base)
    sampler = Sampler(base['terrain'],config['terrain']['vertical_unit'],geometry['vertical_datum'])
    terrain_datum=config['terrain'].get('vertical_datum')
    if terrain_datum and terrain_datum!=geometry['vertical_datum']:
        raise ValueError('Terrain and model vertical datums differ')
    if not sampler.crs.equals(CRS.from_user_input(geometry['horizontal_crs'])):
        raise ValueError('Terrain and geometry must use the same projected coordinates')
    a = assessment(base, source)
    cases = {'baseline': (geometry,a)}
    tried, seen = set(), {physical_id(geometry)}
    attempts, skips = [], []
    recommendation = 'baseline'
    maximum = spec['maximum_width_ft']
    stop = 'BUDGET_REACHED'
    for number in range(1,spec['maximum_rounds']+1):
        best = cases[recommendation][1]['metrics']
        if not best['warnings'] and not best['errors'] and not best['low_ends']:
            stop = 'ZERO_WARNINGS_AND_CLEAR_ENDS'
            break
        if best['errors']:
            stop = 'NATIVE_ERROR_REVIEW'
            break
        candidate = None
        def explore(key):
            metrics=cases[key][1]['metrics']
            # Allow a promising reduction in warning count to lead to a later geometric repair.
            if number%3==0:
                return (metrics['errors'],metrics['warnings'],rank(cases[key][1]))
            return rank(cases[key][1])
        for parent in sorted(cases,key=explore):
            g, current = cases[parent]
            for action in spec['actions']:
                if (parent,action) in tried:
                    continue
                tried.add((parent,action))
                if action.startswith('infill') and g.get('channel_geometry_basis')!='conditional_surface_dem':
                    skips.append(dict(parent=parent,action=action,reason='PRESERVE_REVIEWED_BATHYMETRY'))
                    continue
                new,changes,omitted = proposals(action,g,current,sampler,maximum)
                if not changes:
                    skips.append(dict(parent=parent,action=action,reason='NO_FEASIBLE_CHANGE',omitted=omitted))
                    continue
                signature = physical_id(new)
                if signature in seen:
                    continue
                seen.add(signature)
                if not validate_layout(g,new):
                    skips.append(dict(parent=parent,action=action,reason='GEOMETRY_CONFLICT'))
                    continue
                from .bank_reach import refresh
                from .bank_review import profile_context
                old_rows={r['rs']:r for r in g['cross_sections']}
                for row in new['cross_sections']:
                    old=old_rows.get(row['rs'])
                    if old and row['station_ft']!=old['station_ft'] and old.get('bank_candidates'):
                        prior=old['bank_candidates']
                        row['bank_candidates']=dict(method='retained_plan_banks',confidence=prior.get('confidence','LOW'),
                            evidence_class=prior.get('evidence_class','inferred'),reasons=prior.get('reasons',[]),
                            profile_context=profile_context(row),parent_method=prior.get('method'),
                            basis='Previously saved banks retained at the same plan coordinates; original evidence is in the parent case.')
                if new.get('bank_reach_summary'):
                    refresh(new)
                errors = geometry_errors(confirm_geometry(new,item(rp),review['basis']),plan['case_kind']=='software_validation')
                if errors:
                    skips.append(dict(parent=parent,action=action,reason='INPUT_GATE',errors=errors))
                    continue
                candidate = parent,action,new,changes,omitted
                break
            if candidate:
                break
        if not candidate:
            stop = 'NO_MORE_DISTINCT_ELIGIBLE_GEOMETRIES'
            break
        parent,action,new,changes,omitted = candidate
        key = f'trial_{number:02d}'
        dest = folder/'cases'/key
        if not intact([plan['source_project'], plan['source_geometry'], *plan['source_inputs']]):
            raise ValueError('Baseline inputs changed during the warning batch')
        cfg = case_configuration(plan,dest,key)
        chosen = [s for s in config['scenarios'] if s['id']==plan['scenario_id']]
        if cfg['scenarios']!=chosen:
            raise ValueError('The baseline hydraulic scenario changed')
        cfg['title'] = config['title']+' / '+key
        save_once(dest/'project.draft.json',cfg)
        save_once(dest/'geometry.json',new)
        save_once(dest/'proposal.json',dict(parent=parent,action=action,changes=changes,omitted=omitted))
        case = dict(id=key,draft=item(dest/'project.draft.json'),geometry=item(dest/'geometry.json'))
        previous = next((r for r in journal['cases'] if r['id']==key),None)
        rec = previous if previous and previous['status']=='COMPUTED' else study.run_case(sp,plan,rp,review,case,journal,journal_path,timeout)
        if rec['status']!='COMPUTED':
            stop = 'COMPUTATION_INCOMPLETE'
            break
        _,summary,_ = study.verified_case(rec,dest/'project.json',read(dest/'project.json'))
        _,actual,_ = bound_inputs(summary)
        if actual!=confirm_geometry(new,item(rp),review['basis']) or summary['configuration']['scenarios']!=cfg['scenarios']:
            raise ValueError('Solved inputs differ from the reviewed trial')
        try:
            audit = assessment(summary,rec['summary'],a['stages'])
        except (ValueError,KeyError,OSError) as exc:
            stop = 'NATIVE_EVIDENCE_INCOMPLETE'
            skips.append(dict(parent=parent,case=key,reason=stop,error=str(exc)))
            break
        cases[key] = (new,audit)
        attempts.append(dict(id=key,parent=parent,action=action,proposal=item(dest/'proposal.json')))
        recommendation = min(cases,key=lambda k:rank(cases[k][1]))
    best = cases[recommendation][1]
    if not best['metrics']['warnings'] and not best['metrics']['errors'] and not best['metrics']['low_ends']:
        stop='ZERO_WARNINGS_AND_CLEAR_ENDS'
    lowest = min(cases,key=lambda k:(cases[k][1]['metrics']['errors'],cases[k][1]['metrics']['warnings'],rank(cases[k][1])))
    journal.update(finished_utc=utc(),stop=stop)
    save(journal_path,journal)
    summaries=[]
    for k,(_,audit) in cases.items():
        dest = folder/'evidence'/(k+'.json')
        save_once(dest,audit)
        project = (ROOT/audit['hdf']['path']).with_suffix('').with_suffix('.prj')
        summaries.append(dict(id=k,metrics=audit['metrics'],codes=audit['codes'],audit=item(dest),native_file=audit['native_file'],project=item(project)))
    residual = [r for r in best['records'] if r['severity']!='NOTE']
    from .warning_paths import review as review_paths
    paths=review_paths(cases[recommendation][0],best,sampler)
    save(folder/'divided_paths.json',paths)
    screened=[v['tests'].get('100',{}) for v in paths['intervals']]
    path_counts=dict(locations=paths['locations'],intervals=len(screened),connected=sum(v.get('at_stage') is True for v in screened),
                     complete=sum(v.get('status')=='COMPLETE' for v in screened),unavailable_locations=paths['unavailable'],status=paths['status'])
    result=dict(path_counts=path_counts,divided_paths=item(folder/'divided_paths.json'),analysis_kind=KIND,status='INCOMPLETE' if stop in ('COMPUTATION_INCOMPLETE','NATIVE_EVIDENCE_INCOMPLETE') else 'REVIEW_REQUIRED',
                stop=stop,baseline=source,study=item(sp),review=item(rp),execution=item(journal_path),cases=summaries,
                attempts=attempts,skipped=skips,recommended=recommendation,lowest_count=lowest,residual=residual,
                engineering_acceptance='NOT_ASSESSED')
    save(folder/'analysis.json',result)
    return result
