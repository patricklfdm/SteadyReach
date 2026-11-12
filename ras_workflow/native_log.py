"""Conservative adapter for the inspected HEC-RAS 7.0.1 English steady log.

Final group summaries are distinct from iterative NTRL rows. Printed flow
resolution is 0.1 cfs. Logs do not replace the complete native warning table.
Ambiguous mixed-pass output and unknown layouts remain unavailable.
"""
import re
import copy
import h5py
from .common import item, read, sha
from .qa import number


def parse(text, expected, profiles, controller):
    if 'HEC-RAS 7.0.1 June 2026' not in text:
        raise ValueError('Uninspected native log version')
    blocks = re.split(r'^PROFILE #\s+(\d+)\s*$', text, flags=re.M)
    if [int(blocks[i]) for i in range(1,len(blocks),2)] != list(range(1,len(profiles)+1)):
        raise ValueError('Missing, repeated or reordered log profile blocks')
    output=[]
    for index, p in enumerate(profiles):
        block=blocks[2*index+2]
        # One final structure block per profile is the validated scope. Do not
        # select the last iteration/pass merely because its values look plausible.
        if block.count('**** EXIT CULVERT ****') != 1:
            raise ValueError('Ambiguous/missing structure passes; native detail review required')
        endings=re.findall(r'^\s*Q & EG EACH CULVERT\s+([^\r\n]+)\s*\r?\n\s*\r?\nFor CULVERT\s+(\S+)\s+the\s+EG\s+is\s+([-\d.]+)\s*\r?\n\s*\r?\n\s*\*\*\*\* EXIT CULVERT \*\*\*\*',block,re.M)
        if len(endings)!=1 or float(endings[0][1])!=float(expected['structure_rs']):
            raise ValueError('Final group summary/station identity unavailable')
        tokens=endings[0][0].split();groups=expected['groups']
        if len(tokens)!=3*len(groups):
            raise ValueError('Unsupported wrapped/missing group layout')
        names=re.findall(r'^\s*(\d+)\s+CULVERT\s+([^\r\n]+)',block,re.M)
        if not (len(groups)==1 and not names) and [(int(i),name.strip()) for i,name in names] != [(i+1,g['name']) for i,g in enumerate(groups)]:
            raise ValueError('Log group names/order differ from verified geometry')
        values=[]
        for i,g in enumerate(groups):
            gid,q,eg=tokens[3*i:3*i+3]
            if (gid!=str(i+1) or not re.fullmatch(r'\d+\.\d',q) or
                not re.fullmatch(r'-?\d+\.\d{2}',eg)):
                raise ValueError('Uninspected group numeric precision or identifier')
            values.append(dict(group_id=i,name=g['name'],flow_cfs=float(q),control_egl_ft=float(eg),
                               flow_resolution_cfs=.1,egl_resolution_ft=.01))
        actual=[r for r in controller['rows'] if r['profile']==p['id'] and r['node_type']=='Culv'
                and float(r['station'])==float(expected['structure_rs']) and r['updn_argument']==0]
        if len(actual)!=1:
            raise ValueError('No unique matching controller structure')
        first=number(actual[0]['metrics'].get('Q Culv Group'))
        if first is None or abs(first-values[0]['flow_cfs'])>.0501:
            raise ValueError('Final log group flow disagrees with independent COM readback')
        totals=re.findall(r'Q-CULVERT =\s+(\d+\.\d)\s*$',block,re.M)
        if not totals or abs(float(totals[-1])-sum(g['flow_cfs'] for g in values))>.0501*(len(groups)+1):
            raise ValueError('Final log culvert total/group consistency failed')
        qt=re.findall(r'^\s*QTOTAL\s+(\d+\.\d+)\s*$',block,re.M)
        if len(qt)!=1 or abs(float(qt[0])-p['flow_cfs'])>.002:
            raise ValueError('Log flow/profile identity mismatch')
        output.append(dict(profile_id=p['id'],groups=values,total_flow_cfs=float(totals[-1]),
                           flow_resolution_cfs=.1,warning_coverage='NOT_A_COMPLETE_WARNING_TABLE'))
    return output


def extract(project, expected, profiles):
    log=project.with_suffix('.LOG');execution=read(project.parent.parent/'execution.json')
    if not log.is_file():
        return dict(status='NOT_AVAILABLE',reason='Native log was not generated',profiles=[])
    if log.stat().st_size>32_000_000:
        return dict(status='UNSUPPORTED',reason='Native log exceeds bounded parser size',profiles=[],source=item(log))
    if (not execution.get('output_written_this_run') or execution.get('native_log')!=item(log) or
        execution.get('hdf_sha256')!=sha(project.with_suffix('.p01.hdf'))):
        return dict(status='UNVERIFIED',reason='Log is not sealed by matching fresh solver execution',profiles=[])
    try:
        inspected=copy.deepcopy(expected)
        with h5py.File(project.with_suffix('.p01.hdf')) as h:
            attrs=h['Geometry/Structures/Culvert Groups/Attributes'][:]
        if len(attrs)!=len(inspected['groups']):raise ValueError('HDF/log group count mismatch')
        for group,actual in zip(inspected['groups'],attrs):
            name=actual['Name'].decode('ascii').strip()
            if group.get('name') and group['name']!=name:raise ValueError('HDF/input group name mismatch')
            group['name']=name
        data=parse(log.read_text(encoding='ascii'),inspected,profiles,read(project.parent/'controller_output.json'))
    except (ValueError,UnicodeError) as e:
        return dict(status='UNSUPPORTED',reason=str(e),profiles=[],source=item(log))
    return dict(status='VERIFIED_PRINTED_PRECISION',source=item(log),profiles=data,
                limitations=['Only unambiguous final group flow/controlling EGL are extracted',
                             'No group velocities or full inlet/outlet-control details',
                             'Missing roadway flow remains null; this log is not a complete warning export'])


def supplement(rows, profile):
    """Retain full-precision first-group COM output; fill other group flow only."""
    for row, observed in zip(rows,profile['groups']):
        row['name']=observed['name']
        row['native_log_flow_cfs']=observed['flow_cfs']
        row['native_log_flow_resolution_cfs']=observed['flow_resolution_cfs']
        row['native_log_control_egl_ft']=observed['control_egl_ft']
        if row['group_id']==0:
            continue
        row.update(flow_cfs=observed['flow_cfs'],representative_barrel_flow_cfs=None,
                   flow_basis='NATIVE_LOG_FINAL_GROUP_PRINTED_0.1_CFS',detail_coverage='NATIVE_LOG_FLOW_ONLY')
    return rows
