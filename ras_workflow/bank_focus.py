"""Locate the bank side affected by multiscale disagreement in a bound profile."""
from .common import finite


def scale_focus(row, assessment):
    method = row.get('bank_candidates') or {}
    scales = method.get('scale_results') or []
    windows = method.get('scale_windows_ft') or []
    settings = method.get('settings') or {}
    radius = settings.get('window_ft')
    if not assessment['valid_pair'] or len(windows) != 3 or len(scales) != 3 or not finite(radius) or radius <= 0:
        return None
    if not all(finite(w) and w > 0 for w in windows) or sorted(set(windows)) != windows:
        return None
    x, z = row.get('station_ft') or [], row.get('elevation_ft') or []
    if len(x) != len(z) or not all(isinstance(scale, dict) for scale in scales):
        return None
    sides = {}
    for label, saved in zip(('left', 'right'), assessment['banks_ft']):
        peaks = {}
        leading = []
        distant_competitor = False
        for window, scale in zip(windows, scales):
            config = scale.get('settings') or {}
            ratio = config.get('competing_score_ratio')
            if config.get('window_ft') != window or not finite(ratio) or not 0 < ratio <= 1:
                return None
            options = scale.get(label, [])
            if not isinstance(options, list) or not all(isinstance(v, dict) for v in options):
                return None
            leading.append(options[0].get('station_ft') if options else None)
            for rank, value in enumerate(options):
                index = value.get('index')
                if (type(index) is not int or not 0 < index < len(x)-1 or not finite(x[index]) or not finite(z[index])
                        or value.get('station_ft') != x[index] or value.get('elevation_ft') != z[index]
                        or not finite(value.get('score')) or value['score'] <= 0):
                    return None
                if rank and value['score'] < ratio * options[0]['score']:
                    continue
                peak = peaks.setdefault(index, dict(index=index, station_ft=x[index], leading_windows_ft=[], competing_windows_ft=[]))
                peak['competing_windows_ft' if rank else 'leading_windows_ft'].append(window)
                if rank and abs(x[index] - saved) > radius:
                    distant_competitor = True
        positions = [v for v in leading if v is not None]
        maximum = max((abs(v - saved) for v in positions), default=None)
        reasons = []
        if len(positions) != len(windows):
            reasons.append('MISSING_SCALE')
        if maximum is not None and maximum > radius:
            reasons.append('SHIFTED_PEAK')
        if distant_competitor:
            reasons.append('COMPETING_PEAK')
        if 'COMPETING_'+label.upper()+'_BANKS' in assessment['reasons']:
            reasons.append('COMPETING_LOCAL_BANK')
        sides[label] = dict(saved_ft=saved, leading_ft=leading, reasons=reasons,
                            max_leader_shift_ft=maximum, options=sorted(peaks.values(), key=lambda p:p['index']))
    affected = [side for side, evidence in sides.items() if evidence['reasons']]
    return dict(focus='both' if len(affected)==2 else affected[0] if affected else 'pair',
                windows_ft=windows, tolerance_ft=radius, sides=sides)
