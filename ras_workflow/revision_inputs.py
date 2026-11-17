"""Explain revision differences using sealed calculation input snapshots."""
import math
from pathlib import Path
from pyproj import CRS
from pyproj.exceptions import CRSError
from .common import ROOT, finite, intact, item, read, safe_path


def bound_inputs(summary):
    hyd = summary['hydraulics']
    extraction = summary.get('hydraulic_results')
    if extraction and (not intact([extraction]) or read(ROOT/extraction['path']) != hyd):
        raise ValueError('Hydraulic extraction identity changed')
    path = safe_path(ROOT, hyd['raw_hdf']['path']).parent.parent/'manifest.json'
    manifest = read(path)
    if manifest.get('run_id') != hyd['run_id']:
        raise ValueError('Revision input manifest belongs to another run')
    snapshots = manifest.get('input_snapshots', [])
    if not snapshots or not intact(snapshots):
        raise ValueError('Revision input snapshots are missing or changed')
    configs = [e for e in snapshots if Path(e['path']).suffix == '.json'
               and read(ROOT/e['path']) == summary['configuration']]
    if len(configs) != 1:
        raise ValueError('Revision configuration is not uniquely bound to the run')
    name = Path(summary['configuration'].get('geometry', '')).name
    geometries = [e for e in snapshots if name and Path(e['path']).name == name]
    if len(geometries) != 1:
        raise ValueError('No unique georeferenced geometry snapshot for this revision')
    return summary['configuration'], read(ROOT/geometries[0]['path']), [item(path), configs[0], geometries[0]]


def station_key(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Nonfinite station ID prevents revision matching')
    return format(number, '.12g')


def indexed(rows):
    result = {}
    for row in rows:
        key = station_key(row['rs'])
        if key in result:
            raise ValueError('Repeated station IDs prevent unique revision matching')
        result[key] = row
    return result


def point(value):
    return isinstance(value, (list, tuple)) and len(value) == 2 and all(finite(v) for v in value)


def bank_xy(row):
    line = row.get('cutline_xy') or []
    stations = row.get('station_ft') or []
    banks = row.get('bank_stations_ft') or []
    if len(line) < 2 or not all(point(p) for p in line) or len(stations) < 2 or len(banks) != 2:
        return None
    if not all(finite(v) for v in [stations[0], stations[-1], *banks]) or stations[-1] <= stations[0]:
        return None
    lengths = [math.dist(a,b) for a,b in zip(line,line[1:])]
    total = sum(lengths)
    if total <= 0:
        return None
    result = []
    for bank in banks:
        fraction = (bank-stations[0])/(stations[-1]-stations[0])
        if not 0 <= fraction <= 1:
            return None
        target = fraction*total
        for index, length in enumerate(lengths):
            if length and (target <= length or index == len(lengths)-1):
                result.append([a+(b-a)*target/length for a,b in zip(line[index],line[index+1])])
                break
            target -= length
    return result if len(result) == 2 else None


def geometry_changes(old, new):
    previous, current = indexed(old.get('cross_sections',[])), indexed(new.get('cross_sections',[]))
    factor = None
    if old.get('horizontal_crs') and new.get('horizontal_crs'):
        a,b = CRS.from_user_input(old['horizontal_crs']), CRS.from_user_input(new['horizontal_crs'])
        if a.is_projected and a.equals(b):
            factor = a.axis_info[0].unit_conversion_factor/.3048
    rows = []
    fields = ('station_ft','elevation_ft','cutline_xy','center_xy','bank_stations_ft',
              'reach_lengths_ft','expansion_contraction','ineffective_left','ineffective_right','manning_segments')
    for key in sorted(previous.keys() & current.keys(), key=float, reverse=True):
        a,b = previous[key],current[key]
        changed = [f for f in fields if a.get(f) != b.get(f)]
        shift = math.dist(a['center_xy'],b['center_xy'])*factor if factor and point(a.get('center_xy')) and point(b.get('center_xy')) else None
        ax,bx = bank_xy(a),bank_xy(b)
        banks = [math.dist(x,y)*factor for x,y in zip(ax,bx)] if factor and ax and bx else None
        # This is a coordinate matching tolerance, not survey accuracy.
        location = 'UNVERIFIED' if shift is None else 'MOVED' if shift > .01 else 'SAME_CENTER'
        angle = None
        if factor and all(len(r.get('cutline_xy',[])) >= 2 and all(point(p) for p in r['cutline_xy']) for r in (a,b)):
            def heading(r):
                p,q=r['cutline_xy'][0],r['cutline_xy'][-1]
                return math.degrees(math.atan2(q[1]-p[1],q[0]-p[0]))
            angle = (heading(b)-heading(a)+180)%360-180
        rows.append(dict(station=key,changed_fields=changed,location_status=location,
                         center_shift_ft=shift,rotation_degrees=angle,bank_plan_shifts_ft=banks))
    return dict(previous_count=len(previous),current_count=len(current),sections=rows,
                added_stations=sorted(current.keys()-previous.keys(),key=float,reverse=True),
                removed_stations=sorted(previous.keys()-current.keys(),key=float,reverse=True),
                changed_sections=sum(bool(r['changed_fields']) for r in rows),
                moved_centers=sum(r['location_status']=='MOVED' for r in rows),
                unverified_centers=sum(r['location_status']=='UNVERIFIED' for r in rows),
                moved_bank_pairs=sum(any(v>.01 for v in r['bank_plan_shifts_ft']) for r in rows if r['bank_plan_shifts_ft']),
                unverified_bank_pairs=sum(r['bank_plan_shifts_ft'] is None for r in rows),
                coordinate_match_tolerance_ft=.01)


def hydraulic_inputs(config, geometry, scenario):
    chosen=next(s for s in config['scenarios'] if s['id']==scenario)
    values={key:chosen.get(key) for key in ('channel_n','overbank_n','culvert_n')}
    values['profiles']=[dict(id=p['id'],flow_cfs=p.get('flow_cfs')) for p in chosen['profiles']]
    for key in ('flow_regime','boundary_slopes','boundaries','structure','horizontal_crs','vertical_datum','channel_geometry_basis'):
        values[key]=geometry.get(key)
    return values


def collect(old, new):
    from .report_context import changes
    try:
        oc,og,os=bound_inputs(old)
        nc,ng,ns=bound_inputs(new)
        scalar=changes(hydraulic_inputs(oc,og,old['hydraulics']['scenario_id']),
                       hydraulic_inputs(nc,ng,new['hydraulics']['scenario_id']))
        geometry=geometry_changes(og,ng)
        return dict(status='VERIFIED',input_changes=scalar,geometry=geometry,sources=os+ns,
                    interpretation='MULTIPLE_INPUT_CHANGES' if scalar and (geometry['changed_sections'] or geometry['added_stations'] or geometry['removed_stations']) else 'REVISION_COMPARISON_ONLY')
    except (ValueError,KeyError,OSError,TypeError,StopIteration,CRSError) as error:
        return dict(status='UNAVAILABLE',error=str(error),input_changes=[],sources=[])
