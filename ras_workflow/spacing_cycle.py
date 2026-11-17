"""Bounded actual-water coverage corrections of compatible nested spacing cases."""
import copy
import os
from pyproj import CRS

from .common import ROOT, intact, item, read, save, unique_id, utc, lock, sha, safe_path
from .coverage_study import validate_extension
from .section_joint import repair
from .convergence import validate_nested


def policy(body):
    value = body.get('coverage_policy')
    if value is None:
        return None
    if not isinstance(value,dict):
        raise ValueError('Automatic spacing coverage needs explicit round and width limits')
    rounds, width = value.get('maximum_rounds'), value.get('maximum_width_ft')
    if type(rounds) is not int or not 1 <= rounds <= 3:
        raise ValueError('Choose 1–3 automatic spacing coverage rounds')
    if type(width) not in (int, float) or not 120 <= width <= 2000:
        raise ValueError('Choose a total section-width bound of 120–2000 ft')
    return dict(maximum_rounds=rounds, maximum_width_ft=float(width))


def nested(geometries):
    # Draft metadata is not a hydraulic input. Compare all retained section
    # controls and all three reach-length partitions through the native contract.
    for previous, current in zip(geometries, geometries[1:]):
        validate_nested(dict(cross_sections=previous['cross_sections']),
                        dict(cross_sections=current['cross_sections']))


def propose(geometries, observations, sampler, maximum):
    """Extend only added rows; project identical shared profiles into both levels."""
    if len(geometries) != 3:
        raise ValueError('Exactly one baseline and two nested refinements required')
    if any(not CRS.from_user_input(g['horizontal_crs']).equals(sampler.crs) or g['vertical_datum']!=sampler.datum for g in geometries):
        raise ValueError('Adaptive spacing DEM and geometry CRS/datum must match')
    nested(geometries)
    original = {r['rs'] for r in geometries[0]['cross_sections']}
    water = {}
    for row in observations:
        if row['left_excess_ft'] > 0 or row['right_excess_ft'] > 0:
            rs = float(row['rs'])
            water[rs] = max(water.get(rs, float('-inf')), row['wse_ft'])
    finest = geometries[-1]
    protected = [i for i, row in enumerate(finest['cross_sections']) if row['rs'] in original]
    proposed = repair(finest, sampler, water, maximum, protected=protected, allow_rotation=False)
    validate_extension(finest, proposed['geometry'], sampler, maximum)
    changed = {r['rs'] for r in proposed['changes']}
    if changed & original:
        raise ValueError('Spacing coverage attempted to change a baseline section')
    final_rows = {r['rs']: r for r in proposed['geometry']['cross_sections']}
    variants = []
    for old in geometries:
        variant = copy.deepcopy(old)
        for i, row in enumerate(old['cross_sections']):
            if row['rs'] in changed:
                updated = copy.deepcopy(final_rows[row['rs']])
                # Partition lengths differ across refinement levels. All other
                # hydraulic profile fields at a shared station must stay equal.
                updated['reach_lengths_ft'] = copy.deepcopy(row['reach_lengths_ft'])
                variant['cross_sections'][i] = updated
        validate_extension(old, variant, sampler, maximum)
        variants.append(variant)
    nested(variants)
    if variants[0] != geometries[0]:
        raise ValueError('Original baseline changed during coupled coverage correction')
    return dict(geometries=variants, changes=proposed['changes'], unresolved=proposed['unresolved'],
                search=proposed['search'], water_levels_ft={str(k):v for k,v in water.items()},
                retained_wet_sections=sorted(set(water) & original, reverse=True),
                added_wet_sections=sorted(set(water)-original, reverse=True))


def round_evidence(analysis):
    """Authenticate each native case and the saved numerical comparisons."""
    from .study import reviewed, verified_case
    from .section_spacing import confirm_geometry
    from .convergence import validate_native_series, assess
    from .qa import compare, THRESHOLDS
    from .spacing_coverage import observations, assess_coverage
    entries = [analysis['study'], analysis['review'], analysis['execution']]
    if not intact(entries):
        raise ValueError('Spacing round evidence changed')
    sp, plan, rp, review = reviewed(analysis['study']['path'], analysis['review']['path'])
    journal = read(ROOT/analysis['execution']['path'])
    if journal['study'] != item(sp) or journal['review'] != item(rp):
        raise ValueError('Spacing round execution identity changed')
    if [c['id'] for c in plan['cases']] != ['baseline','refinement_1','refinement_2']:
        raise ValueError('Three ordered spacing cases required')
    if [c['id'] for c in analysis['cases']] != [c['id'] for c in plan['cases']]:
        raise ValueError('Displayed spacing case order changed')
    records = {r['id']:r for r in journal['cases']}
    if len(records) != len(journal['cases']) or set(records)-{c['id'] for c in plan['cases']}:
        raise ValueError('Spacing round has duplicate or unrelated execution records')
    loaded, geometries, located, rows, failed = [], [], [], [], []
    baseline = [r['rs'] for r in read(ROOT/plan['cases'][0]['geometry']['path'])['cross_sections']]
    from .qa_locator import collect
    for case in plan['cases']:
        geometry = read(ROOT/case['geometry']['path']); geometries.append(geometry)
        record = records.get(case['id'], {})
        shown = next(r for r in analysis['cases'] if r['id']==case['id'])
        if shown.get('status') != record.get('status') or shown.get('section_count') != len(geometry['cross_sections']):
            raise ValueError('Displayed spacing case status or section count changed')
        if record.get('status') != 'COMPUTED':
            failed.append(case['id']); rows.append(dict(id=case['id'],status=record.get('status'))); continue
        path = (ROOT/case['draft']['path']).parent/'project.json'
        config = read(path)
        expected = read(ROOT/case['draft']['path'])
        expected.update(geometry='geometry.confirmed.json', authorization='authorization.json', geometry_review=review['basis'])
        if config != expected or read(path.parent/config['geometry']) != confirm_geometry(geometry,item(rp)):
            raise ValueError('Spacing round changed its confirmed geometry or controls')
        auth = dict(project_id=plan['project_id'],allowed_geometry_sha256=sha(path.parent/config['geometry']),
                    scope=plan['case_kind'],study=item(sp),review=item(rp),authority=review['reviewer'],basis=review['basis'])
        if read(path.parent/'authorization.json') != auth:
            raise ValueError('Spacing round authorization changed')
        actual = verified_case(record,path,config); loaded.append(actual)
        _,summary,hyd = actual
        located += collect(hyd)['rows']
        observed = observations(hyd,baseline)
        rows.append(dict(id=case['id'],status='COMPUTED',**observed))
        if shown.get('summary') != record['summary']:
            raise ValueError('Displayed spacing case differs from its native record')
        if any(shown.get(key) != value for key,value in observed.items()):
            raise ValueError('Displayed spacing coverage differs from actual water levels')
        entries += [record['summary'],case['draft'],case['geometry']]
    if failed != analysis['failed_cases']:
        raise ValueError('Spacing round failed-case list changed')
    if analysis.get('end_coverage') != assess_coverage(rows):
        raise ValueError('Spacing coverage summary differs from actual water levels')
    if not failed:
        entries += validate_native_series(loaded)
        pairs = [compare(a[0],b[0],None) for a,b in zip(loaded,loaded[1:])]
        conv = analysis['convergence']
        if not intact(conv['sources']+conv['comparisons']):
            raise ValueError('Spacing convergence sources changed')
        if pairs != [read(ROOT/e['path']) for e in conv['comparisons']] or assess(pairs,THRESHOLDS['sensitivity_hw_ft']) != conv['rows']:
            raise ValueError('Spacing convergence differs from native results')
        expected_status = 'STABLE_AT_REVIEW_THRESHOLD' if all(r['status']=='STABLE_AT_REVIEW_THRESHOLD' for r in conv['rows']) else 'NOT_CONVERGED'
        if conv['threshold_ft'] != THRESHOLDS['sensitivity_hw_ft'] or conv['status'] != expected_status or analysis['status'] != expected_status:
            raise ValueError('Spacing numerical status changed')
        entries += conv['sources']+conv['comparisons']
    elif analysis['status'] != 'INCOMPLETE':
        raise ValueError('Incomplete spacing round was reported complete')
    entries += plan['source_inputs']+plan['evidence']+[plan['specification']]
    return dict(plan=plan, geometries=geometries, observations=located, loaded=loaded, entries=entries)


def next_proposal(analysis, limits):
    from .terrain_auto import Sampler
    verified = round_evidence(analysis)
    if analysis['failed_cases']:
        return None, verified
    _,summary,_ = verified['loaded'][0]
    sampler = Sampler(summary['terrain'],summary['configuration']['terrain']['vertical_unit'],verified['geometries'][0]['vertical_datum'])
    return propose(verified['geometries'],verified['observations'],sampler,limits['maximum_width_ft']),verified


def stop_reason(analysis, proposal, number, limits):
    if analysis['failed_cases']:return 'INCOMPLETE'
    if analysis['cases'][0]['wet_sections']:return 'BASELINE_COVERAGE_REVIEW'
    if not any(c['wet_sections'] for c in analysis['cases']):return 'COVERAGE_RESOLVED_REVIEW_REQUIRED'
    if number >= limits['maximum_rounds']:return 'ROUND_LIMIT_REVIEW_REQUIRED'
    if not proposal['changes']:return 'RETAINED_OR_GEOMETRY_REVIEW'
    return None


def shifted_config(case, destination, number):
    source = ROOT/case['draft']['path']; config = read(source)
    config.update(title=config['title']+' / coverage round '+str(number),geometry='geometry.json',authorization=None)
    for field in ('raster','provenance'):
        if config['terrain'].get(field):
            config['terrain'][field] = os.path.relpath(safe_path(source.parent,config['terrain'][field]),destination)
    delivery = config.setdefault('delivery',{})
    delivery['enabled'] = False
    delivery['additional_sources'] = [os.path.relpath(safe_path(source.parent,p),destination) for p in delivery.get('additional_sources',[])]
    imagery = delivery.get('imagery',{})
    if imagery.get('raster'):
        imagery['raster'] = os.path.relpath(safe_path(source.parent,imagery['raster']),destination)
    return config


def save_once(path, content):
    if path.exists():
        if read(path) != content:raise ValueError('Prepared adaptive spacing input changed: '+str(path))
    else:
        save(path,content)


def child_study(parent_path, parent_plan, parent_review, prior, proposal, number):
    from .study import reviewed
    folder = parent_path.parent/'rounds'/str(number)/'prepared'
    save_once(folder/'proposal.json',proposal)
    spec = dict(type='section_spacing',scope=parent_plan['scope'],purpose='Shared-profile fixed-direction extension of added sections only',
                parent=item(parent_path),parent_review=item(parent_review),previous_round=prior,
                proposal=item(folder/'proposal.json'),round=number,coverage_policy=parent_plan['coverage_policy'])
    save_once(folder/'specification.json',spec)
    cases=[]
    for original, geometry in zip(parent_plan['cases'],proposal['geometries']):
        dest=folder/'cases'/original['id']
        config=shifted_config(original,dest,number)
        save_once(dest/'project.draft.json',config);save_once(dest/'geometry.json',geometry)
        case=copy.deepcopy(original)
        case.update(draft=item(dest/'project.draft.json'),geometry=item(dest/'geometry.json'))
        # Graphical previews and later editable continuation must describe the
        # repaired profiles, not the original pre-extension plot coordinates.
        by_station={r['rs']:r for r in geometry['cross_sections']}
        for row in case.get('added_sections',[]):
            actual=by_station[row['station']]
            row.update(cutline_xy=actual['cutline_xy'],station_ft=actual['station_ft'],elevation_ft=actual['elevation_ft'],
                       banks_ft=actual['bank_stations_ft'],width_ft=actual['station_ft'][-1]-actual['station_ft'][0],
                       sampled_points=len(actual['station_ft']))
        cases.append(case)
    plan=copy.deepcopy(parent_plan);plan.pop('coverage_policy',None)
    plan.update(specification=item(folder/'specification.json'),cases=cases,
                evidence=parent_plan['evidence']+[item(parent_path),item(parent_review),prior,item(folder/'proposal.json')],
                coverage_parent=item(parent_path),coverage_round=number)
    save_once(folder/'study.json',plan)
    review=copy.deepcopy(read(parent_review))
    review.update(study_sha256=sha(folder/'study.json'),basis=review['basis']+' Derived coverage round '+str(number)+'.',
                  derived_from=item(parent_review))
    save_once(folder/'local_confirmation.json',review)
    return reviewed(folder/'study.json',folder/'local_confirmation.json')


def snapshot(analysis, folder):
    """Freeze the execution record before a later retry can update its journal."""
    target=folder/'receipts'/unique_id()
    save(target/'execution.json',read(ROOT/analysis['execution']['path']))
    saved=copy.deepcopy(analysis);saved['execution']=item(target/'execution.json')
    save(target/'analysis.json',saved)
    return item(target/'analysis.json')


def finish(parent_path, journal, journal_path, entry, proposal, status):
    journal.update(status=status,finished_utc=utc(),final_analysis=entry)
    if proposal is not None:
        destination=parent_path.parent/'receipts'/unique_id()/'final_proposal.json'
        save(destination,proposal);journal['final_proposal']=item(destination)
    save(journal_path,journal)
    result=copy.deepcopy(read(ROOT/entry['path']))
    result['coverage_batch']=dict(study=journal['study'],review=journal['review'],execution=item(journal_path),
        status=status,policy=read(parent_path)['coverage_policy'],rounds=journal['rounds'],
        round_summaries=round_summaries(journal), final_proposal=journal.get('final_proposal'),engineering_acceptance='NOT_ASSESSED')
    save(parent_path.parent/'analysis.json',result)
    return result


def round_summaries(journal):
    rows=list(journal['rounds'])
    if journal['status']=='INCOMPLETE':
        rows.append(dict(round=len(rows),analysis=journal['final_analysis']))
    result=[]
    for row in rows:
        analysis=read(ROOT/row['analysis']['path'])
        result.append(dict(round=row['round'],analysis=row['analysis'],status=analysis['status'],
            wet_sections=[len(c.get('wet_sections',[])) if c.get('status')=='COMPUTED' else None for c in analysis['cases']],
            last_two_max_xs_deltas_ft=[r['last_two_max_xs_deltas_ft'] for r in analysis.get('convergence',{}).get('rows',[])]))
    return result


def run(sp, plan, rp, review, timeout):
    from .study import run_fixed
    limits=policy(plan);folder=sp.parent;path=folder/'cycle.json'
    with lock(folder/'cycle.lock'):
        journal=read(path) if path.exists() else dict(study=item(sp),review=item(rp),rounds=[],attempts=[],status='IN_PROGRESS')
        if journal['study']!=item(sp) or journal['review']!=item(rp):
            raise ValueError('Adaptive spacing confirmation changed')
        if journal['status'] not in ('IN_PROGRESS','INCOMPLETE'):
            result=read(folder/'analysis.json');verify(result);return result
        journal['status']='IN_PROGRESS';save(path,journal)
        while True:
            number=len(journal['rounds'])
            if number:
                prior=journal['rounds'][-1]['analysis']
                if not intact([prior]):raise ValueError('Prior adaptive spacing round changed')
                previous=read(ROOT/prior['path'])
                proposal,_=next_proposal(previous,limits)
                stopped=stop_reason(previous,proposal,number-1,limits)
                if stopped:return finish(sp,journal,path,prior,proposal,stopped)
                round_sp,round_plan,round_rp,round_review=child_study(sp,plan,rp,prior,proposal,number)
            else:
                round_sp,round_plan,round_rp,round_review=sp,plan,rp,review
            journal['current']=dict(round=number,study=item(round_sp),review=item(round_rp))
            save(path,journal)
            # A crash after computation but before this checkpoint reuses the
            # already verified case outputs through the normal resume path.
            analysis=run_fixed(round_sp,round_plan,round_rp,round_review,timeout)
            entry=snapshot(analysis,folder/'rounds'/str(number))
            journal['attempts'].append(dict(round=number,analysis=entry))
            proposal,_=next_proposal(read(ROOT/entry['path']),limits)
            status=stop_reason(analysis,proposal,number,limits)
            if status!='INCOMPLETE':journal['rounds'].append(dict(round=number,analysis=entry))
            save(path,journal)
            if status:return finish(sp,journal,path,entry,proposal,status)


def verify(result):
    """Re-derive every permitted correction from its bound prior native water."""
    from .study import reviewed
    batch=result['coverage_batch'];entries=[batch['study'],batch['review'],batch['execution']]
    if not intact(entries):raise ValueError('Adaptive spacing evidence changed')
    sp,plan,rp,review=reviewed(batch['study']['path'],batch['review']['path'])
    limits=policy(plan);journal=read(ROOT/batch['execution']['path'])
    if journal['study']!=batch['study'] or journal['review']!=batch['review'] or journal['rounds']!=batch['rounds'] or limits!=batch['policy']:
        raise ValueError('Adaptive spacing chain or policy changed')
    if batch['round_summaries']!=round_summaries(journal):
        raise ValueError('Displayed adaptive spacing history changed')
    sequence=list(journal['rounds'])
    if batch['status']=='INCOMPLETE':
        sequence.append(dict(round=len(sequence),analysis=journal['final_analysis']))
    if not 1<=len(sequence)<=limits['maximum_rounds']+1:
        raise ValueError('Adaptive spacing round count exceeds confirmation')
    previous=None
    for number,row in enumerate(sequence):
        if row['round']!=number or not intact([row['analysis']]):raise ValueError('Adaptive spacing round changed')
        analysis=read(ROOT/row['analysis']['path'])
        actual=round_evidence(analysis);entries += [row['analysis']]+actual['entries']
        if analysis['failed_cases'] and number!=len(sequence)-1:
            raise ValueError('Adaptive spacing continued after an incomplete round')
        if number==0:
            if analysis['study']!=batch['study'] or analysis['review']!=batch['review']:
                raise ValueError('Initial adaptive spacing series changed')
        else:
            proposal,_=next_proposal(previous,limits)
            if stop_reason(previous,proposal,number-1,limits):raise ValueError('Adaptive spacing continued past a stop condition')
            child=actual['plan'];spec=read(ROOT/child['specification']['path'])
            if child.get('coverage_parent')!=batch['study'] or child.get('coverage_round')!=number or spec['previous_round']!=journal['rounds'][number-1]['analysis']:
                raise ValueError('Derived spacing round belongs to another chain')
            if not intact([spec['proposal']]) or read(ROOT/spec['proposal']['path'])!=proposal:
                raise ValueError('Spacing extension differs from its bounded DEM proposal')
            entries += [spec['proposal']]
            if actual['geometries']!=proposal['geometries']:
                raise ValueError('Spacing correction changed unapproved geometry')
            for original,case in zip(plan['cases'],child['cases']):
                dest=(ROOT/case['draft']['path']).parent
                if read(ROOT/case['draft']['path'])!=shifted_config(original,dest,number):
                    raise ValueError('Adaptive spacing changed a configuration control')
        previous=analysis
    # For an interrupted batch, the latest failed round is kept separately.
    entry=journal['final_analysis']
    if not intact([entry]):raise ValueError('Final adaptive spacing result changed')
    if entry!=sequence[-1]['analysis']:
        raise ValueError('Final adaptive round is not the last recorded round')
    final=read(ROOT/entry['path']);proposal,verified=next_proposal(final,limits)
    number=journal['current']['round']
    if number!=len(sequence)-1 or journal['current']['study']!=final['study'] or journal['current']['review']!=final['review']:
        raise ValueError('Current adaptive round identity changed')
    expected=stop_reason(final,proposal,number,limits)
    if expected!=batch['status'] or expected!=journal['status']:
        raise ValueError('Adaptive spacing stopping condition changed')
    if {k:v for k,v in result.items() if k!='coverage_batch'}!=final:
        raise ValueError('Displayed adaptive spacing result differs from the final round')
    if proposal is not None:
        e=batch['final_proposal']
        if e!=journal.get('final_proposal') or not intact([e]) or read(ROOT/e['path'])!=proposal:
            raise ValueError('Final coverage proposal changed')
        entries += [e]
    return entries+[entry]+verified['entries']


def progress(sp, plan, review):
    path=sp.parent/'cycle.json'
    if not path.exists():return [dict(id='round_0 / '+c['id'],status='QUEUED') for c in plan['cases']]
    journal=read(path)
    if journal['study']!=item(sp) or journal['review']!=review:
        raise ValueError('Adaptive spacing progress identity changed')
    current=journal.get('current')
    if not current:return []
    if not intact([current['study'],current['review']]):raise ValueError('Current adaptive round changed')
    current_plan=read(ROOT/current['study']['path'])
    execution=(ROOT/current['study']['path']).parent/'execution.json'
    record=read(execution) if execution.exists() else None
    if record and (record['study']!=current['study'] or record['review']!=current['review']):
        raise ValueError('Current adaptive execution identity changed')
    records={r['id']:r for r in record['cases']} if record else {}
    return [dict(id='round_'+str(current['round'])+' / '+c['id'],section_count=c['section_count'],
                 status=records.get(c['id'],{}).get('status','QUEUED'),error=records.get(c['id'],{}).get('error')) for c in current_plan['cases']]
