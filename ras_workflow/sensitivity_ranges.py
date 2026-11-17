"""Source-bound sensitivity suggestions from the calculation's adopted inputs.

Ranges remain conditional experiments, never confidence intervals. No generic
percentages or undocumented blockage assumptions are introduced here.
"""
from pathlib import Path

from .common import ROOT, digest, finite, intact, item, read, save, unique_id, utc
from .revision_inputs import bound_inputs
from .river import is_river


def controls(config, geometry, scenario_id):
    scenario_index = next(i for i, s in enumerate(config['scenarios']) if s['id'] == scenario_id)
    scenario = config['scenarios'][scenario_index]
    rows = []
    def add(path, key, value, en, zh, unit):
        rows.append(dict(path=path, field=key, value=value, label=dict(en=en, zh=zh), unit=unit))
    for field, en, zh in [('channel_n', 'Channel Manning n', '主槽糙率'),
                          ('overbank_n', 'Overbank Manning n', '漫滩糙率')]:
        add('scenario.'+field, f'c.scenarios.{scenario_index}.'+field, scenario[field], en, zh, 'Manning n')
    for side, en, zh in [('upstream', 'Upstream normal-depth slope', '上游正常水深坡降'),
                         ('downstream', 'Downstream normal-depth slope', '下游正常水深坡降')]:
        if side == 'upstream' and geometry.get('flow_regime') == 'subcritical':
            continue
        if is_river(geometry) and geometry.get('boundaries', {}).get(side, {}).get('type') != 'normal_depth':
            continue
        add('boundary_slopes.'+side, 'g.boundary_slopes.'+side,
            geometry.get('boundary_slopes', {}).get(side), en, zh, 'ft/ft')
    if is_river(geometry) and geometry.get('boundaries', {}).get('downstream', {}).get('type') == 'known_stage':
        for i, value in enumerate(geometry['boundaries']['downstream']['stages_ft']):
            add(f'boundaries.downstream.stages_ft.{i}', f'g.boundaries.downstream.stages_ft.{i}', value,
                scenario['profiles'][i]['id']+' downstream WSE', scenario['profiles'][i]['id']+' 下游水位', 'ft')
    for i, group in enumerate(geometry.get('structure', {}).get('groups', [])):
        add(f'groups.{i}.depth_blocked_ft', f'g.structure.groups.{i}.depth_blocked_ft', group.get('depth_blocked_ft'),
            f'Group {i+1} uniform bottom fill', f'第 {i+1} 组全涵长底部填塞', 'ft')
    for row in rows:
        row['inactive'] = bool(row['path'].startswith('scenario.') and
                               any(r.get('manning_segments') for r in geometry['cross_sections']))
    return rows


def evidence(candidate):
    entries = ([candidate['source']] if candidate.get('source') else [])+candidate.get('sources', [])
    if entries and not intact(entries):
        raise ValueError('Range source file is missing or changed')
    return entries


def range_option(candidate, origin, baseline):
    bounds = candidate.get('range')
    if not isinstance(bounds, list) or len(bounds) != 2 or not all(finite(v) for v in bounds) or bounds[0] >= bounds[1]:
        return None
    if candidate.get('value') != baseline or not bounds[0] <= baseline <= bounds[1]:
        return None
    if not candidate.get('basis'):
        return None
    sources = evidence(candidate)
    value = dict(low=bounds[0], high=bounds[1], origin=origin, basis=candidate['basis'],
                 condition=candidate.get('condition'), sources=sources, url=candidate.get('url'),
                 source_locus=candidate.get('source_locus'), evidence_class=candidate.get('evidence_class', 'assumed'),
                 applicability_confirmed=origin == 'ADOPTED_RANGE')
    value['id'] = digest(value)
    return value


def parameter_rows(config, geometry, scenario, answers, fields):
    fields = {row['key']: row for row in fields}
    rows = controls(config, geometry, scenario)
    for row in rows:
        row.update(options=[], recommended_id=None, notes=[])
        if row['inactive']:
            row['status'] = 'SECTION_ROUGHNESS_OVERRIDES_SCENARIO'
            continue
        adopted = answers.get(row['field'], {})
        # A changed/manual value must not inherit an earlier selected range.
        candidate = adopted.get('candidate_record', {}) if adopted.get('value') == row['value'] else {}
        if candidate:
            try:
                option = range_option(candidate, 'ADOPTED_RANGE', row['value'])
                if option:
                    row['options'].append(option)
                    row['recommended_id'] = option['id']
            except ValueError as error:
                row['notes'].append(str(error))
        field = fields.get(row['field'], {})
        if field.get('value') == row['value']:
            for candidate in field.get('parameter_candidates', []):
                # Offer matching document candidates for an explicit applicability
                # choice. A coincident number alone never selects the source.
                if not candidate.get('source'):
                    continue
                try:
                    option = range_option(candidate, 'UNSELECTED_SOURCE_RANGE', row['value'])
                    if option and not any(o['low'] == option['low'] and o['high'] == option['high'] and
                                          o['sources'] == option['sources'] and o['basis'] == option['basis']
                                          for o in row['options']):
                        row['options'].append(option)
                except ValueError as error:
                    row['notes'].append(str(error))
        row['status'] = 'ADOPTED_RANGE_AVAILABLE' if row['recommended_id'] else 'SOURCE_CHOICE_REQUIRED' if row['options'] else 'NO_DOCUMENTED_RANGE'
    return rows


def load_context(model):
    if not model.get('summary') or not intact([model['summary']]):
        raise ValueError('An intact computed baseline is required')
    summary = read(ROOT/model['summary']['path'])
    config, geometry, sources = bound_inputs(summary)
    if summary['configuration'] != read(ROOT/model['active_project']):
        raise ValueError('Active configuration changed since calculation')
    if read((ROOT/model['active_project']).parent/config['geometry']) != geometry:
        raise ValueError('Active geometry changed since calculation')
    sources = [model['summary'], *sources]
    manifest = read(ROOT/sources[1]['path'])
    sources += [item(ROOT/model['active_project']), item((ROOT/model['active_project']).parent/config['geometry'])]
    authorization = Path(config.get('authorization') or '').name
    entries = [e for e in manifest['input_snapshots'] if authorization and Path(e['path']).name == authorization]
    answers, fields, notes = {}, [], []
    if len(entries) != 1:
        notes.append('No unique sealed parameter decision; enter explicit ranges where needed.')
        return config, geometry, answers, fields, sources, notes
    sources += entries
    decision_entry = read(ROOT/entries[0]['path']).get('decision')
    if not decision_entry or not intact([decision_entry]):
        notes.append('The calculation decision is unavailable or changed; saved candidate ranges are not reused.')
        return config, geometry, answers, fields, sources, notes
    decision = read(ROOT/decision_entry['path'])
    if decision.get('project_id') != config['project_id'] or decision.get('scenario') != model['scenario']:
        raise ValueError('Parameter decision belongs to a different baseline')
    sources.append(decision_entry)
    answers = decision.get('answers', {})
    reviews = [e for e in decision.get('uploads', []) if Path(e['path']).name == 'parameters.json']
    confirmations = [e for e in decision.get('uploads', []) if Path(e['path']).name == 'confirmation.json']
    matching = []
    for entry in confirmations:
        if not intact([entry]):
            continue
        confirmation = read(ROOT/entry['path'])
        review_entry = confirmation.get('review')
        if review_entry not in reviews or not intact([review_entry]):
            continue
        review = read(ROOT/review_entry['path'])
        if (review.get('project_id') == config['project_id'] and
                confirmation.get('action') == 'CONFIRM_DISPLAYED_PARAMETERS_AND_RUN' and
                confirmation.get('reviewed_fingerprint') == review.get('fingerprint') and review.get('ready') is True):
            matching.append((review, review_entry, entry))
    if len(matching) == 1:
        review, review_entry, confirmation_entry = matching[0]
        fields = review.get('fields', [])
        sources += [review_entry, confirmation_entry]
    if not fields:
        notes.append('Only adopted ranges are available; the final candidate-review snapshot could not be verified.')
    return config, geometry, answers, fields, sources, notes


def suggest(key, body):
    from . import app_core as core
    model = core.model(key)
    core.require_idle(model)
    if body.get('revision') != model['revision'] or model.get('native_review') or not model.get('active_project'):
        raise ValueError('Reload a completed workflow-built model before suggesting ranges')
    config, geometry, answers, fields, sources, notes = load_context(model)
    rows = parameter_rows(config, geometry, model['scenario'], answers, fields)
    for row in rows:
        for option in row['options']:
            sources += option['sources']
    sources = list({e['path']: e for e in sources}.values())
    packet = dict(schema_version='sensitivity_ranges_1', project_id=key, baseline=model['summary'],
                  active_project=model['active_project'], sources=sources, parameters=rows, notes=notes,
                  created_utc=utc(), maximum_parameters=4, solver_run=False,
                  limitation='One-at-a-time conditional ranges; no probability, calibration, interaction or engineering acceptance.')
    path = core.folder(key)/'sensitivity_suggestions'/unique_id()/'ranges.json'
    save(path, packet)
    model['sensitivity_suggestions'] = item(path)
    core.persist(model, 'SUGGEST_SENSITIVITY_RANGES', dict(suggestions=model['sensitivity_suggestions']))
    return dict(**packet, token=model['sensitivity_suggestions']['sha256'])


def current(model, strict=False):
    entry = model.get('sensitivity_suggestions')
    if not entry:
        return None
    try:
        if not intact([entry]):
            raise ValueError('Range preview changed; suggest ranges again')
        packet = read(ROOT/entry['path'])
        if packet['baseline'] != model.get('summary') or packet['active_project'] != model.get('active_project') or not intact(packet['sources']):
            raise ValueError('Range inputs changed; suggest ranges again')
        return dict(**packet, token=entry['sha256'])
    except ValueError:
        if strict:
            raise
        return None


def resolve(model, body):
    packet = current(model, strict=True)
    if not packet or body.get('range_token') != packet['token']:
        raise ValueError('Range preview is stale; suggest and review the current ranges')
    choices = body.get('parameters', [])
    if not isinstance(choices, list) or not 1 <= len(choices) <= packet['maximum_parameters']:
        raise ValueError('Select one to four parameters')
    rows = {row['path']: row for row in packet['parameters']}
    resolved, seen = [], set()
    for choice in choices:
        path = choice.get('path')
        if path not in rows or path in seen or rows[path]['inactive']:
            raise ValueError('Invalid, repeated or inactive sensitivity parameter')
        seen.add(path)
        row = rows[path]
        option = next((o for o in row['options'] if o['id'] == choice.get('option_id')), None)
        if choice.get('option_id') and not option:
            raise ValueError('Range source option is stale')
        low, high = choice.get('low'), choice.get('high')
        if not all(finite(v) for v in (low, high)) or not low < high:
            raise ValueError('Enter finite low < high values for every selected parameter')
        edited = not option or [low, high] != [option['low'], option['high']]
        basis = ('User-edited conditional sensitivity range' if edited else 'Selected documented conditional sensitivity range')
        if option:
            basis += '; reference: '+option['basis'].rstrip('. ')
        basis += '. Tested endpoints are assumptions, not a confidence interval.'
        resolved.append(dict(path=path, low=low, high=high, basis=basis,
            range_record=dict(option=option, edited=edited, baseline=row['value'], selected_bounds=[low, high],
                              source_applicability='CONFIRM_WITH_BATCH' if option else 'USER_ENTERED_RANGE', field=row['field'])))
    return resolved, [model['sensitivity_suggestions'], *packet['sources']]
