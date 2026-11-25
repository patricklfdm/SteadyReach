"""Compare already modeled survey events against the inputs frozen for this run."""
import csv
import io
from pathlib import Path

from .common import ROOT, intact, read, sha
from .river_observations import COLUMNS, datum, screen
from .revision_inputs import bound_inputs, station_key


def suggestion(manifest,files):
    import hashlib
    protocol=ROOT/'examples/siletz_or/protocol.json'
    if ('protocol.json' in files and protocol.is_file() and
            hashlib.sha256(files['protocol.json']).hexdigest()==sha(protocol) and
            any(p['id']=='Holdout' for p in manifest['scenario']['profiles'])):
        return dict(profile='Holdout',event='Holdout',rs='44056',max_residual_ft=.15/.3048,
                    basis='protocol.json · internal investigation threshold 0.15 m')
    return None


def published_series(folder):
    from examples.siletz_or.prepare import archived_input, published_flows, select_events
    changes = published_flows((folder/'flow_inputs.f01').read_text().splitlines())
    events = select_events(folder, changes[44506]/changes[19532], archived_input(folder))
    if events != read(folder/'events.json')['events']:
        raise ValueError('The selected field event differs from the original discharge or stage series.')
    return events


def records(summary):
    _,geometry,_=bound_inputs(summary)
    refs=[r for r in geometry.get('provenance',[]) if isinstance(r,dict) and r.get('role') in ('survey_manifest','survey_source')]
    if refs and not intact(refs):
        raise ValueError('Restore the original survey files before comparing observed events.')
    refs=list({r['path']:r for r in refs}.values())
    manifests = [r for r in refs if r.get('role') == 'survey_manifest']
    if len(manifests) != 1:
        return [], []
    manifest = ROOT/manifests[0]['path']
    named = {Path(r['path']).name: ROOT/r['path'] for r in refs if r.get('role') == 'survey_source'}
    if 'observed_profiles.csv' in named:
        reader = csv.DictReader(io.StringIO(named['observed_profiles.csv'].read_text('utf-8-sig')))
        if set(reader.fieldnames or []) != set(COLUMNS) | {'profile'} or len(reader.fieldnames) != len(COLUMNS)+1:
            raise ValueError('observed_profiles.csv requires the observation template plus profile.')
        groups = {}
        for index,raw in enumerate(reader,1):
            if index>2000:
                raise ValueError('Use a maximum of 2,000 survey observations.')
            if None in raw or any(v is None for v in raw.values()):
                raise ValueError('Incomplete observed profile CSV row')
            profile = raw.pop('profile').strip()
            row = {k:v.strip() for k,v in raw.items()}
            groups.setdefault((profile,row['event'],row['date']),[]).append(row)
        rows=[]
        for (profile,event,date),observations in groups.items():
            spec=dict(profile=profile,event=event,date=date)
            matched=screen(observations,summary,spec)
            ambiguous=sum(k[0]==profile for k in groups)>1
            boundary_mismatch=any(r['role']=='boundary' and (r['issues'] or r['model_ft'] is None or
                                  r['observed_ft'] is None or abs(r['model_ft']-r['observed_ft'])>.002) for r in matched)
            for r in matched:
                for applies,issue in [(ambiguous,'MULTIPLE_EVENTS_FOR_PROFILE'),(boundary_mismatch,'OBSERVED_BOUNDARY_MISMATCH')]:
                    if applies:
                        r['issues'].append(issue)
                        r.update(model_ft=None,residual_ft=None,event_eligible=False)
                rows.append(dict(r,profile=profile,source_file='observed_profiles.csv'))
        return rows, refs
    protocol = ROOT/'examples/siletz_or/protocol.json'
    if 'protocol.json' not in named or not protocol.is_file() or sha(named['protocol.json']) != sha(protocol):
        return [], []
    required = {'flow_inputs.f01','events.json','Calculated Data.csv','Site Information.csv','Siletz River Surface Water Elevation.xml'}
    if not required <= named.keys():
        raise ValueError('Restore the original stage, flow and station metadata named in the Siletz protocol.')
    from examples.siletz_or.prepare import INTERIOR, OUTLET, STAGE, archived_input
    folder = manifest.parent
    archive = archived_input(folder)
    if not archive or archive not in named.values():
        raise ValueError('Restore the discharge series cited by the survey manifest.')
    frozen = read(manifest)['geometry']
    sections = {station_key(s['rs']):s for s in geometry['cross_sections']}
    original = {station_key(s['rs']):s for s in frozen['cross_sections']}
    hyd = summary['hydraulics']
    from .qa import verified_profiles
    water = verified_profiles(hyd)
    import h5py
    with h5py.File(ROOT/hyd['raw_hdf']['path']) as native:
        base = native['Results/Steady/Output/Output Blocks/Base Output/Steady Profiles']
        flows = {name.decode().strip():q for name,q in zip(base['Profile Names'][:],base['Cross Sections/Flow'][:],strict=True)}
    vertical_ok = 'NAVD 88' in named['Siletz River Surface Water Elevation.xml'].read_text('utf-8-sig') and datum(geometry.get('vertical_datum'))=='NAVD88'
    rows = []
    for event in published_series(folder):
        profile = event['id']
        if profile not in water:
            continue
        stages = {station_key(k):v for k,v in water[profile].items()}
        for rs, sensor, role in [('34913',OUTLET,'boundary'),('44056',INTERIOR,'holdout' if profile=='Holdout' else 'calibration')]:
            issues = []
            if not vertical_ok or hyd.get('unit') != 'international ft':
                issues.append('VERTICAL_DATUM_OR_UNIT_MISMATCH')
            if rs not in sections or rs not in original or any(sections[rs].get(k)!=original[rs].get(k) for k in ('center_xy','cutline_xy')) or rs not in stages:
                issues.append('SURVEY_STATION_MOVED_OR_MISSING')
            if not all(abs(float(q)-event['reach_cfs'])<=.002 for q in flows[profile]):
                issues.append('EVENT_DISCHARGE_MISMATCH')
            if (geometry.get('boundaries',{}).get('downstream',{}).get('type')!='known_stage' or
                    '34913' not in stages or abs(stages['34913']-event['stage_m'][OUTLET]/.3048)>.002):
                issues.append('OBSERVED_BOUNDARY_MISMATCH')
            observed = event['stage_m'][sensor]/.3048
            value = stages.get(rs) if not issues else None
            rows.append(dict(profile=profile,event=profile,date=event['date'],kind='stage',role=role,
                location=dict(rs=rs),source=f'{STAGE} · Calculated Data.csv · PT {sensor}',source_file='Calculated Data.csv',flow_cfs=event['reach_cfs'],
                observed_datum='NAVD88' if vertical_ok else None,observed_ft=observed,model_ft=value,
                residual_ft=value-observed if value is not None and role!='boundary' else None,
                issues=issues,uncertainty_ft=None))
    return rows, refs
