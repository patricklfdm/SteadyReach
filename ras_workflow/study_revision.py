"""Recover editable inputs from one authenticated, actually computed study case."""
import copy

from .common import ROOT, intact, item, read, safe_path
from .inputs import dependencies
from .qa_review import load_summary
from .study import reviewed


def resolve(parent, body):
    kind = body.get('study_kind')
    field = {'coverage': 'latest_coverage', 'spacing': 'latest_spacing'}.get(kind)
    entry = parent.get(field) if field else None
    if not entry or entry['sha256'] != body.get('study_token') or not intact([entry]):
        raise ValueError('Study result changed; reopen the current result before continuing')
    analysis = read(ROOT/entry['path'])
    cycle_sources = []
    if analysis.get('coverage_batch'):
        from .spacing_cycle import verify
        cycle_sources = verify(analysis)
    _, plan, _, _ = reviewed(analysis['study']['path'], analysis['review']['path'])
    expected_kind = {'coverage': 'coverage_repair', 'spacing': 'section_spacing'}[kind]
    if plan.get('analysis_kind') != expected_kind or parent['summary'] not in plan['evidence']:
        raise ValueError('Study belongs to a different baseline or analysis kind')
    if not intact([analysis['study'], analysis['review'], analysis['execution']]):
        raise ValueError('Study confirmation or execution changed')
    journal = read(ROOT/analysis['execution']['path'])
    if journal['study'] != analysis['study'] or journal['review'] != analysis['review']:
        raise ValueError('Study execution identity differs')
    cases = journal['prepared_cases'] if kind == 'coverage' else plan['cases']
    matches = [c for c in cases if c['id'] == body.get('case_id')]
    records = [r for r in journal['cases'] if r['id'] == body.get('case_id')]
    if len(matches) != 1 or len(records) != 1 or records[0]['status'] != 'COMPUTED':
        raise ValueError('Select one successfully computed case')
    case, record = matches[0], records[0]
    analysis_rows = [r for r in analysis['cases'] if r['id'] == case['id']]
    if len(analysis_rows) != 1 or analysis_rows[0].get('summary') != record['summary']:
        raise ValueError('Selected case differs from the displayed study result')
    if not intact([record['summary'], case['draft'], case['geometry']]):
        raise ValueError('Computed study inputs or summary changed')
    _, summary, hyd = load_summary(record['summary']['path'])
    config_path = (ROOT/case['draft']['path']).parent/'project.json'
    config = read(config_path)
    if config != summary['configuration'] or config['project_id'] != plan['project_id']:
        raise ValueError('Computed study configuration differs')
    manifest_path = (ROOT/hyd['raw_hdf']['path']).parent.parent/'manifest.json'
    manifest = read(manifest_path)
    bound = manifest['source_inputs']+manifest['input_snapshots']+manifest['native_before']+manifest['outputs']
    if manifest['source_inputs'] != dependencies(config_path, config) or not intact(bound):
        raise ValueError('Study native inputs or results changed')
    geometry_path = safe_path(config_path.parent, config['geometry'])
    sources = [entry, analysis['study'], analysis['review'], analysis['execution'], record['summary'],
               item(config_path), item(geometry_path), item(manifest_path)]+bound+cycle_sources
    return dict(config_path=config_path, config=config, geometry=read(geometry_path),
                summary=record['summary'], terrain=summary['terrain'],
                geometry_source=item(geometry_path), sources=sources,
                kind=kind, case_id=case['id'], analysis=entry,
                maximum_width_ft=analysis.get('coverage_batch', {}).get('policy', plan.get('policy', {})).get('maximum_width_ft', 2000.))


def answers(previous, old_config, old_geometry, config, geometry, scenario, source):
    """Carry provenance by section/profile identity while retaining computed values."""
    from . import intake
    result = {}
    old_sections = {(row['reach_id'], row['rs']): i for i, row in enumerate(old_geometry['cross_sections'])}
    old_scenarios = {row['id']: i for i, row in enumerate(old_config['scenarios'])}
    for field in intake.fields(config, geometry, scenario):
        value = field['value']
        if value in (None, '', []):
            continue
        parts = field['key'].split('.')
        prior_key = field['key']
        if parts[:2] == ['g', 'cross_sections']:
            row = geometry['cross_sections'][int(parts[2])]
            index = old_sections.get((row['reach_id'], row['rs']))
            prior_key = '.'.join(parts[:2]+[str(index)]+parts[3:]) if index is not None else None
        elif parts[:2] == ['c', 'scenarios']:
            row = config['scenarios'][int(parts[2])]
            index = old_scenarios.get(row['id'])
            if index is not None:
                parts[2] = str(index)
                if len(parts) > 4 and parts[3] == 'profiles':
                    profile = row['profiles'][int(parts[4])]['id']
                    old_profiles = {p['id']: i for i, p in enumerate(old_config['scenarios'][index]['profiles'])}
                    parts[4] = str(old_profiles.get(profile, -1))
                prior_key = '.'.join(parts)
            else:
                prior_key = None
        prior = previous.get(prior_key, {})
        if prior.get('value') == value:
            answer = copy.deepcopy(prior)
        else:
            answer = dict(value=value, evidence_class='assumed',
                          basis='Carried from the computed '+source['case_id']+' case. Review the saved study assumptions and current geometry.')
            if prior:
                answer['prior_input'] = copy.deepcopy(prior)
        answer.update(confirmed=False, source_case=source['summary'])
        # Only newly introduced spacing banks are replaceable by automatic
        # morphology preparation. Retained choices and later manual edits stay fixed.
        if (parts[:2] == ['g', 'cross_sections'] and parts[-1] == 'bank_stations_ft'
                and index is None and row.get('spacing_assumptions')):
            answer['inherited_spacing_bank'] = True
        # These are the chosen case inputs. Future edits may replace them through
        # the normal explicit or missing-value candidate paths.
        answer.pop('automatic_preparation', None)
        result[field['key']] = answer
    return result
