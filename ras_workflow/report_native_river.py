"""Read the river-only cards supported by the native builder for reporting.

This reader does not expand the culvert importer's accepted scope.
"""
import re
from pathlib import Path
from .native_review import text, card, fixed


def inspect(project):
    project = Path(project)
    prj = text(project).splitlines()
    current = card(prj, 'Current Plan')
    if not re.fullmatch(r'p\d{2}', current) or 'English Units' not in prj:
        raise ValueError('River appendix requires a saved English-unit steady plan')
    plan = text(project.with_suffix('.' + current)).splitlines()
    geom, flow = card(plan, 'Geom File'), card(plan, 'Flow File')
    if not re.fullmatch(r'g\d{2}', geom) or not re.fullmatch(r'f\d{2}', flow):
        raise ValueError('River appendix requires steady geometry and flow files')
    for key, value in [('Plan File', current), ('Geom File', geom), ('Flow File', flow)]:
        if prj.count(key + '=' + value) != 1:
            raise ValueError('Ambiguous river native input reference')
    geometry = text(project.with_suffix('.' + geom))
    river = card(geometry.splitlines(), 'River Reach')
    blocks = re.split(r'^Type RM Length L Ch R =', geometry, flags=re.M)[1:]
    if len(blocks) < 2 or any(int(b.split(',', 1)[0]) != 1 for b in blocks):
        raise ValueError('River appendix supports one reach with cross sections only')
    if re.search(r'^(Junct Name|Storage Area|2D Flow Area|Lateral Structure)=', geometry, re.M):
        raise ValueError('River appendix does not support additional hydraulic domains')
    sections = []
    for block in blocks:
        lines = block.splitlines()
        start = next(i for i, v in enumerate(lines) if v.startswith('#Mann='))
        count = int(card(lines, '#Mann').split(',')[0])
        rough, _ = fixed(lines, start + 1, count * 3)
        sections.append(dict(rs=lines[0].split(',')[1].strip(),
            manning=[rough[i:i+3] for i in range(0, len(rough), 3)],
            banks=[float(v) for v in card(lines, 'Bank Sta').split(',')],
            ineffective_areas=any(v.startswith('#XS Ineff=') for v in lines)))
    fl = text(project.with_suffix('.' + flow)).splitlines()
    names = card(fl, 'Profile Names').split(',')
    count = int(card(fl, 'Number of Profiles'))
    locations = [i for i, v in enumerate(fl) if v.startswith('River Rch & RM=')]
    if len(names) != count or len(locations) != 1:
        raise ValueError('River appendix requires constant discharge along one reach')
    flows, _ = fixed(fl, locations[0] + 1, count)
    boundaries = []
    for i, line in enumerate(fl):
        if not line.startswith('Boundary for River Rch & Prof#='): continue
        end = next((j for j in range(i+1, len(fl)) if fl[j].startswith('Boundary for River Rch & Prof#=')), len(fl))
        chunk = fl[i+1:end]
        bc = dict(profile_number=int(line.rsplit(',', 1)[1]))
        for side, prefix in [('upstream', 'Up'), ('downstream', 'Dn')]:
            typ = int(card(chunk, prefix + ' Type')); value = dict(type=typ)
            if typ == 3: value['slope'] = float(card(chunk, prefix + ' Slope'))
            elif typ == 1 and side == 'downstream': value['stage_ft'] = float(card(chunk, prefix + ' Known WS'))
            elif typ != 0: raise ValueError('Unsupported river boundary in report appendix')
            bc[side] = value
        boundaries.append(bc)
    regimes = [v.strip() for v in plan if v.strip() in ('Subcritical Flow', 'Supercritical Flow', 'Mixed Flow')]
    if len(regimes) != 1 or [v['profile_number'] for v in boundaries] != list(range(1, count+1)):
        raise ValueError('Ambiguous river regime or boundary profiles')
    return dict(model_type='river', regime=regimes[0], river_reach=river, sections=sections,
                profiles=[dict(id=n.strip(), flow_cfs=q) for n, q in zip(names, flows)], boundaries=boundaries)
