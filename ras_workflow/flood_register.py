"""Project-local, frozen flood-mark searches, offline replay and explicit location roles."""
import hashlib
import re

from . import app_core as core
from . import flood_marks as marks
from .common import ROOT, digest, intact, item, lock, read, save, unique_id, utc

ROLES = ('unresolved', 'outlet', 'same_crossing', 'interior_candidate', 'context')

def registered_stations(model):
    from .intake_boundary import documents, screen
    from .intake_freeze import local
    from .intake_register import context
    ctx = context(model)
    result = screen(ctx,documents(ctx,local))
    return [{k:r.get(k) for k in ('station','name','datum','source','matched_rs','lonlat',
             'distance_to_boundary_center_m','transfer_required','datum_check')} for r in result['stations']]


def freeze(folder, geometry, river, catalog_bytes, year, selected, fetch, stations=()):
    available = {r['id']: r for r in marks.catalog(catalog_bytes, year)}
    if not isinstance(selected, list) or not 1 <= len(selected) <= 8 or any(type(i) != int or i not in available for i in selected):
        raise ValueError('Choose up to eight events from the listed year / 请从该年目录中选择最多八项事件')
    ids = sorted(set(selected))
    originals = [(i, fetch(marks.event_url(i))) for i in ids]
    output = marks.screen(originals, geometry, river)
    folder.mkdir(parents=True, exist_ok=True)
    version = unique_id()
    out = folder / version
    out.mkdir()
    (out/'catalog.json').write_bytes(catalog_bytes)
    sources = []
    for event, raw in originals:
        path = out / f'event_{event}.json'
        path.write_bytes(raw)
        sources.append(dict(**item(path, 'original_usgs_event_marks'), event=event, url=marks.event_url(event)))
    save(out/'geometry.json', geometry)
    station_refs = {}
    for station in stations:
        source = station['source']
        if source['sha256'] not in station_refs:
            from .intake_freeze import local
            path = out / ('gage_'+source['sha256']+'.json')
            path.write_bytes(local(source).read_bytes())
            station_refs[source['sha256']] = item(path,'original_gage_metadata')
    receipt = dict(version=version, saved=utc(), river=river, year=year, events=[available[i] for i in ids],
                   catalog=item(out/'catalog.json'), catalog_url=marks.CATALOG, sources=sources,
                   stations=list(stations), station_files=list(station_refs.values()),
                   geometry=item(out/'geometry.json'), output_sha256=digest(output))
    save(out/'receipt.json', receipt)
    save(folder/'latest.json', item(out/'receipt.json'))
    return version


def verified_receipt(folder, version):
    if not isinstance(version,str) or not re.fullmatch(r'[0-9]{8}T[0-9]{6}_[a-f0-9]{10}', version):
        raise ValueError('Choose a frozen search / 请选择已冻结查询')
    ref = read(folder/version/'receipt.json')
    members = [ref['geometry'], ref['catalog'], *ref['sources'], *ref.get('station_files',[])]
    directory = (folder/version).resolve()
    if (ref.get('version') != version or any(not (ROOT/r['path']).resolve().is_relative_to(directory) for r in members)
            or not intact(members)):
        raise ValueError('Frozen source files have changed / 冻结原件或几何已改变')
    return ref


def replay(folder, version):
    ref = verified_receipt(folder, version)
    geometry = read(ROOT/ref['geometry']['path'])
    originals = [(s['event'], (ROOT/s['path']).read_bytes()) for s in ref['sources']]
    result = marks.screen(originals, geometry, ref['river'])
    if digest(result) != ref['output_sha256']:
        raise ValueError('Matching changed since capture / 定位结果与冻结版本不同')
    roles_file = folder/version/'roles.json'
    roles = read(roles_file) if roles_file.exists() else {}
    # Location proposals belong to this edition. They never add observations to validation scores.
    for r in result['rows']:
        r['issues'] = [] if r['datum_matches'] else ['DATUM']
        r['role'] = roles.get(r['group'], 'unresolved')
        r['has_elevation'] = r.pop('z_ft') is not None
    return dict(**result, roles=roles, version=version, token=digest([ref,roles]), sources=ref['sources'],
                events=ref['events'], river=ref['river'], saved=ref['saved'], stations=ref.get('stations',[]), geometry_sha256=ref['geometry']['sha256'])


def action(key, body, operation):
    model = core.model(key)
    if model['revision'] != body.get('revision') or model.get('native_review'):
        raise ValueError('Reopen the current project version / 请重新打开当前项目版本')
    base = core.folder(key) / 'flood_evidence'
    if operation == 'inspect':
        entries = sorted(base.glob('*/receipt.json'), reverse=True)
        return dict(versions=[p.parent.name for p in entries], year=model.get('metadata',{}).get('year'))
    if operation == 'replay':
        return replay(base, body.get('version'))
    core.require_idle(model)
    if operation == 'catalog':
        raw = marks.fetch(marks.CATALOG)
        events = marks.catalog(raw, body.get('year'))
        base.mkdir(parents=True,exist_ok=True)
        key_hash = hashlib.sha256(raw).hexdigest()
        with lock(base/'write.lock'):
            cache = base/(key_hash+'.json')
            if not cache.exists(): cache.write_bytes(raw)
        return dict(events=events, catalog_hash=key_hash)
    if operation == 'capture':
        checksum = body.get('catalog_hash')
        if not isinstance(checksum,str) or not re.fullmatch(r'[0-9a-f]{64}',checksum):
            raise ValueError('Find events first / 请先查询事件')
        raw = (base/(checksum+'.json')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != checksum:
            raise ValueError('Refresh the event catalog / 请重新查询目录')
        if model.get('summary') and intact([model['summary']]):
            from .revision_inputs import bound_inputs
            _, geom, _ = bound_inputs(read(ROOT/model['summary']['path']))
        elif model.get('summary'):
            raise ValueError('Restore the calculation results / 请先恢复计算成果')
        else:
            from .app_parameters import objects
            geom = objects(model)[4]
        geometry = marks.geometry_input(geom)
        with lock(base/'write.lock'):
            version = freeze(base,geometry,str(body.get('river') or '').strip(),raw,body.get('year'),body.get('events'),marks.fetch,registered_stations(model))
        return replay(base,version)
    if operation == 'roles':
        with lock(base/'write.lock'):
            version = body.get('version')
            previous = replay(base,version)
            roles = body.get('roles')
            groups = {r['group'] for r in previous['rows']}
            if previous['token'] != body.get('token') or not isinstance(roles,dict) or set(roles) != groups or any(v not in ROLES for v in roles.values()):
                raise ValueError('Reopen and review all source locations / 请重新打开并核对资料位置')
            save(base/version/'roles.json',roles)
        return replay(base,version)
    raise ValueError('Unknown flood evidence action')
