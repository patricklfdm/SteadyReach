"""Screen straight cuts against the local directed channel at two reach scales."""
import math

import numpy as np


def difference(angle):
    """Signed difference between undirected line axes, in degrees."""
    return (angle + 90.) % 180. - 90.


def assess(geometry):
    from .section_joint import flow_crossing

    lines = {line['id']: np.asarray(line['xy'], dtype=float) for line in geometry.get('flowlines', [])}
    observations = []
    for index, row in enumerate(geometry['cross_sections']):
        result = dict(index=index, rs=row.get('rs'), reach_id=row.get('reach_id'), status='INSPECT_CROSSING')
        observations.append(result)
        line = lines.get(row.get('reach_id'))
        cut = np.asarray(row.get('cutline_xy', []), dtype=float)
        if line is None or len(line) < 2 or cut.shape != (2, 2) or not np.isfinite(cut).all():
            continue
        position = flow_crossing(cut, line)
        if position is None:
            result['status'] = 'NO_UNIQUE_CROSSING'
            continue
        if np.linalg.norm(cut[1]-cut[0]) <= 1e-8:
            continue
        axis = math.degrees(math.atan2(*(cut[1]-cut[0])[::-1]))
        result.update(chain=position, cut_axis_deg=axis)
    for i, result in enumerate(observations):
        if 'chain' not in result:
            continue
        neighbors = [other for other in observations[max(0, i-1):i] + observations[i+1:i+2]
                     if other['reach_id'] == result['reach_id'] and 'chain' in other]
        if not neighbors:
            continue
        pos = result['chain']
        span = min(abs(other['chain']-pos) for other in neighbors)
        if span < 1e-6:
            continue
        line = lines[result['reach_id']]
        distances = np.r_[0., np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
        angles = []
        for radius in (.45*span, .9*span):
            ends = np.array([np.interp([pos-radius, pos+radius], distances, coord) for coord in line.T])
            dx, dy = ends[:, 1]-ends[:, 0]
            if math.hypot(dx, dy) <= 1e-8:
                break
            angles.append(math.degrees(math.atan2(dy, dx)) + 90.)
        if len(angles) != 2:
            continue
        disagreement = abs(difference(angles[1]-angles[0]))
        offset = difference(angles[0]-result['cut_axis_deg'])
        wide_offset = difference(angles[1]-result['cut_axis_deg'])
        turn = max(abs(difference(other['cut_axis_deg']-result['cut_axis_deg'])) for other in neighbors)
        # These are review triggers relative to local geometry, not hydraulic criteria.
        status = 'FOLLOWS_CHANNEL'
        if disagreement > 12.:
            status = 'BEND_SCALE_AMBIGUOUS'
        elif abs(offset) >= 22. and abs(wide_offset) >= 18. and offset*wide_offset > 0:
            status = 'SKEW_SUPPORTED_AT_TWO_SCALES'
        elif turn >= 20. and abs(offset) <= 12.:
            status = 'TURN_FOLLOWS_CHANNEL'
        result.update(status=status, normal_offset_deg=round(offset, 3), wide_offset_deg=round(wide_offset, 3),
                      scale_difference_deg=round(disagreement, 3), neighbor_turn_deg=round(turn, 3))
    return observations


def crossing_issues(geometry):
    """Block generated straight river cuts that lack a unique crossing."""
    if geometry.get('model_type') != 'river':
        return []
    return [dict(code='NO_UNIQUE_CROSSING', sections=[r['index']], rs=r['rs'], blocking=True,
                 message='The section must cross its reach centerline once.', zh='断面需与所属河段中心线相交一次。')
            for r in assess(geometry) if r['status'] == 'NO_UNIQUE_CROSSING']


def rotation_controls(rows, answers):
    fixed = set()
    selected = {'LOCAL_SELECTION_NO_ENGINEERING_REVIEW', 'BATCH_MORPHOLOGY_SELECTION_NO_ENGINEERING_REVIEW'}
    for i, row in enumerate(rows):
        answer = answers.get(f'g.cross_sections.{i}.bank_stations_ft') or {}
        recorded = answer.get('value') is not None and not any(answer.get(k) for k in
            ('automatic_preparation', 'automatic_bank_preparation', 'inherited_spacing_bank'))
        field_evidence = (row.get('bank_candidates') or {}).get('evidence_class')
        if recorded or field_evidence in ('measured','surveyed') or (row.get('terrain_review') or {}).get('identity') in selected:
            fixed.add(i)
    return fixed


def cost(observation, rotation):
    if observation.get('status') != 'SKEW_SUPPORTED_AT_TWO_SCALES':
        return 0.
    # Favor a minimal rotation that aligns both scales. Coverage has first priority.
    residual = max(abs(difference(observation[k]-rotation)) for k in ('normal_offset_deg','wide_offset_deg'))
    return 2.*max(0., residual-8.)
