"""Traceable interval proposals, not error diagnosis or engineering acceptance."""

from .common import finite


LIMITATION = ('Selection screens native energy-head changes and channel Froude transitions, '
              'not a proof that spacing caused the warnings. Unselected or excluded intervals '
              'remain untested; bank, bed, boundary and flow-path interpretations remain open.')


def native_index(geometry, native):
    """Reject stale/mismatched profiles before using outputs to choose geometry."""
    sections = geometry['cross_sections']
    expected = [float(r['rs']) for r in sections]
    profiles = {}
    for row in native:
        profiles.setdefault(row['profile'], []).append(row)
    if not profiles:
        raise ValueError('No verified native sections available for spacing selection')
    reaches = {(r['river'], r['reach']) for r in native}
    if len(reaches) != 1:
        raise ValueError('Automatic spacing selection requires one native reach')
    for rows in profiles.values():
        if [float(r['rs']) for r in rows] != expected:
            raise ValueError('Current geometry and computed section identities differ')
        for section, row in zip(sections, rows):
            for field, source in [('station_ft', 'station_ft'), ('elevation_ft', 'elevation_ft'),
                                  ('bank_stations_ft', 'banks_ft')]:
                a, b = section[field], row[source]
                if len(a) != len(b) or any(not finite(x) or not finite(y) or abs(x-y) > .011 for x,y in zip(a,b)):
                    raise ValueError('Current geometry differs from native results at RS '+str(section['rs']))
    return profiles


def recommend(geometry, issues, native, spacing_codes):
    profiles = native_index(geometry, native)
    flagged = {}
    valid_profiles = set(profiles)
    river, reach = native[0]['river'], native[0]['reach']
    unlocated = []
    for issue in issues:
        if issue.get('code') not in spacing_codes:
            continue
        evidence = issue.get('evidence') or {}
        try:
            station = float(issue['station'])
        except (KeyError, TypeError, ValueError):
            station = None
        if (issue.get('profile') not in valid_profiles or station not in [float(s['rs']) for s in geometry['cross_sections']]
                or any(evidence.get(k) and evidence[k] != v for k,v in [('river',river),('reach',reach)])):
            unlocated.append(issue)
            continue
        flagged.setdefault(station, []).append(issue)
    proposals = []
    for i, (a,b) in enumerate(zip(geometry['cross_sections'],geometry['cross_sections'][1:])):
        warnings = flagged.get(float(a['rs']), []) + flagged.get(float(b['rs']), [])
        observations = []
        for profile, rows in profiles.items():
            up, down = rows[i:i+2]
            energy_loss = up['egl_ft']-down['egl_ft'] if all(finite(r.get('egl_ft')) for r in (up,down)) else None
            heads = [r['egl_ft']-r['wse_ft'] if all(finite(r.get(k)) for k in ('egl_ft','wse_ft')) else None for r in (up,down)]
            # EGL-WSE is the native weighted velocity head; never substitute V_channel^2/2g.
            head_change = abs(heads[0]-heads[1]) if all(finite(v) and v>=-.001 for v in heads) else None
            fr = [up.get('froude'),down.get('froude')]
            transition = all(finite(v) and v>=0 for v in fr) and min(fr)<.9 and max(fr)>1.1
            triggers = []
            if energy_loss is not None and energy_loss>1.:triggers.append('ENERGY_LOSS_GT_1_FT')
            if head_change is not None and head_change>.5:triggers.append('VELOCITY_HEAD_CHANGE_GT_0_5_FT')
            if transition:triggers.append('CHANNEL_FROUDE_TRANSITION')
            observations.append(dict(profile=profile,energy_loss_ft=energy_loss,velocity_head_change_ft=head_change,
                                     upstream_froude=fr[0],downstream_froude=fr[1],triggers=triggers))
        reasons = sorted({v['code'] for v in warnings} | {t for v in observations for t in v['triggers']})
        if not reasons:continue
        severe = any('BALANC' in r or 'MINIMUM_ERROR' in r or 'CRITICAL' in r or 'JUMP' in r for r in reasons)
        tier = 3 if severe else 2 if warnings else 1
        # A work ordering, not a risk score. Native solver difficulty precedes spacing advisories,
        # then observations without native advisories; channel length breaks equal-priority ties.
        proposals.append(dict(upstream_rs=a['rs'],downstream_rs=b['rs'],channel_length_ft=a['reach_lengths_ft'][1],
            reasons=reasons,priority_tier=tier,observations=observations,
            warning_ids=sorted({v['id'] for v in warnings if v.get('id')})))
    proposals.sort(key=lambda v:(-v['priority_tier'],-v['channel_length_ft'],-v['upstream_rs']))
    for i,row in enumerate(proposals):row['selection_order']=i+1
    return proposals, dict(policy='native_spacing_screen_v1',energy_loss_trigger_ft=1.,velocity_head_change_trigger_ft=.5,
        channel_froude_band=[.9,1.1],unlocated_spacing_issues=unlocated,limitation=LIMITATION,
        source_url='https://www.hec.usace.army.mil/confluence/rasdocs/hgt/latest/tutorials/1d-steady-flow/troubleshooting-with-hec-ras')


def eligible(geometry, candidates, cell_ft):
    """Cheap necessary conditions. Exact two-level DEM feasibility is checked afterwards."""
    by_rs={r['rs']:r for r in geometry['cross_sections']}
    accepted=[]; excluded=[]
    for row in candidates:
        a,b=by_rs[row['upstream_rs']],by_rs[row['downstream_rs']]
        reason=None
        if any(s.get(k) for s in (a,b) for k in ('manning_segments','ineffective_left','ineffective_right')):
            reason='SECTION_SPECIFIC_CONTROLS'
        elif any(len(s.get('cutline_xy',[]))!=2 for s in (a,b)):
            reason='BENT_CUTLINE'
        elif not finite(row['channel_length_ft']) or row['channel_length_ft']<8*cell_ft:
            reason='BELOW_TWO_CELL_NESTED_SPACING'
        elif len({round(a['rs']+(b['rs']-a['rs'])*fraction,2) for fraction in (0,.25,.5,.75,1)})!=5:
            reason='NATIVE_STATION_PRECISION'
        (excluded if reason else accepted).append(dict(row,reason_code=reason) if reason else row)
    return accepted,excluded


def limit_candidates(geometry, candidates, limit):
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=100:
        raise ValueError('Automatic spacing interval limit must be an integer from 1 to 100')
    capacity=max(0,(500-len(geometry['cross_sections']))//3)
    count=min(limit,capacity)
    return candidates[:count],[dict(row,reason_code='CONFIRMED_SEARCH_LIMIT' if i>=limit else 'SECTION_COUNT_LIMIT')
                               for i,row in enumerate(candidates) if i>=count]
