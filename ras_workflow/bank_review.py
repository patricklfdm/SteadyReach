"""Current-section bank review inventory; never changes or approves bank positions."""
from collections import Counter

from .common import digest, finite


def profile_context(row):
    return digest({k:row.get(k) for k in ('rs','reach_id','center_xy','cutline_xy','station_ft','elevation_ft')})


def spacing_metadata(row, bracket):
    """Attach the conditional bank derivation to newly generated spacing sections."""
    banks = row.get('bank_stations_ft') or []
    samples = row['station_ft']
    return dict(method='adjacent_bank_fraction_v1', confidence='LOW', evidence_class='assumed',
        selected_indices=[samples.index(v) for v in banks] if len(banks)==2 and all(v in samples for v in banks) else None,
        reasons=['INFERRED_SPACING_BANKS_REQUIRE_REVIEW'], profile_context=profile_context(row),
        bracket=list(bracket), basis='Bank fractions inferred from adjacent confirmed sections for a conditional spacing trial; DEM sampling does not independently locate the banks.',
        basis_zh='条件性加密试算按相邻已确认断面岸站比例推定；DEM 采样并未独立确定这些岸站。')


def inventory(geometry, answers=None):
    answers = answers or {}
    rows = []
    sections = geometry.get('cross_sections', [])
    for index, row in enumerate(sections):
        method = row.get('bank_candidates') or {}
        answer = answers.get(f'g.cross_sections.{index}.bank_stations_ft', {})
        banks = row.get('bank_stations_ft')
        samples = row.get('station_ft') or []
        valid = (isinstance(banks, list) and len(banks)==2 and all(finite(v) for v in banks)
                 and len(samples)>1 and all(finite(v) for v in (samples[0], samples[-1]))
                 and samples[0]<banks[0]<banks[1]<samples[-1])
        reasons = []
        if not valid:
            reasons.append('MISSING_OR_INVALID_BANKS')
        from .geometry_qa import section_fingerprint
        review = row.get('terrain_review') or {}
        local_choice = (valid and review.get('identity')=='LOCAL_SELECTION_NO_ENGINEERING_REVIEW'
                        and review.get('fingerprint')==section_fingerprint(row))
        inherited = not local_choice and (bool(row.get('spacing_assumptions')) or method.get('method')=='adjacent_bank_fraction_v1')
        if inherited:
            reasons.append('INFERRED_SPACING_BANKS_REQUIRE_REVIEW')
        if not local_choice and method.get('profile_context') and method['profile_context']!=profile_context(row):
            reasons.append('STALE_BANK_PROFILE_CONTEXT')
        if not local_choice and method.get('confidence') in ('LOW','UNRESOLVED'):
            reasons.extend(method.get('reasons') or ['AMBIGUOUS_TERRAIN_BANKS'])
        elif not local_choice and not method.get('confidence') and not inherited:
            reasons.append('BANK_METHOD_NOT_RECORDED')
        reasons = list(dict.fromkeys(reasons))
        categories = []
        if not valid: categories.append('missing')
        if inherited: categories.append('inferred')
        if 'STALE_BANK_PROFILE_CONTEXT' in reasons: categories.append('stale')
        if not local_choice and method.get('confidence') in ('LOW','UNRESOLVED') and any(r!='INFERRED_SPACING_BANKS_REQUIRE_REVIEW' for r in reasons):
            categories.append('ambiguous')
        if 'BANK_METHOD_NOT_RECORDED' in reasons:categories.append('unrecorded')
        priority = 0 if not valid else 1 if 'stale' in categories else 2 if 'CONTINUITY_WEIGHT_SENSITIVE' in reasons else 3 if inherited else 4 if reasons else 5
        rows.append(dict(index=index,rs=row.get('rs'),reach_id=row.get('reach_id'),
            field=f'g.cross_sections.{index}.bank_stations_ft',banks_ft=banks,valid_pair=valid,
            confidence='USER_SELECTED' if local_choice else 'LOW' if inherited else method.get('confidence','UNRECORDED'),
            categories=categories,reasons=reasons,needs_attention=bool(reasons),priority=priority,
            evidence_class='assumed' if inherited else answer.get('evidence_class',method.get('evidence_class','unrecorded')),
            basis=answer.get('basis') or method.get('basis') or row.get('spacing_assumptions',{}).get('bank_basis'),
            profile_context=profile_context(row)))
    saved = geometry.get('bank_reach_summary') or {}
    ids = [dict(index=i,reach_id=r.get('reach_id'),rs=r.get('rs')) for i,r in enumerate(sections)]
    if not saved:
        summary_status='NOT_AVAILABLE'
    elif saved.get('section_ids')==ids and saved.get('section_count')==len(sections):
        from .bank_reach import signature
        summary_status='CURRENT' if saved.get('input_hash')==signature(geometry,set(saved.get('locked_indices',[]))) else 'STALE'
    else:
        summary_status='STALE'
    return dict(schema_version='bank_review_1.0',section_count=len(rows),sections=rows,
        priority_indices=[r['index'] for r in sorted(rows,key=lambda r:(r['priority'],r['index'])) if r['needs_attention']],
        attention_count=sum(r['needs_attention'] for r in rows),
        category_counts=dict(Counter(c for r in rows for c in r['categories'])),
        reason_counts=dict(Counter(c for r in rows for c in r['reasons'])),
        reach_summary_status=summary_status,
        geometry_changed=False,engineering_acceptance='NOT_ASSESSED')
