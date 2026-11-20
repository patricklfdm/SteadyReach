"""Review boundaries refer to real section stations in one sealed model edition."""
from .common import ROOT, intact, item, read, save, unique_id, utc
from .revision_inputs import station_key


def area(inventory, selection=None):
    stations = sorted({station_key(rs) for rs in next(iter(inventory.values()))}, key=float, reverse=True)
    if len(stations) < 2:
        return dict(stations=stations, selected=stations, subset=False)
    if selection is None:
        return dict(stations=stations, selected=stations, subset=False)
    upstream, downstream = (str(selection.get(k,'')) for k in ('upstream','downstream'))
    if upstream not in stations or downstream not in stations or stations.index(upstream)>=stations.index(downstream):
        raise ValueError('Choose two existing sections in upstream-to-downstream order / 请按上下游顺序选择两个已有断面')
    selected = stations[stations.index(upstream):stations.index(downstream)+1]
    return dict(stations=stations,selected=selected,subset=selected!=stations)


def current(model, inventory):
    entry=model.get('assessment_area')
    if not entry:
        return area(inventory)
    if not intact([entry]):
        raise ValueError('Saved area of interest has changed')
    packet=read(ROOT/entry['path'])
    if packet['summary']!=model['summary']:
        raise ValueError('Saved area belongs to another calculation')
    return area(inventory,packet)


def select(key, body):
    from . import app_core as core
    from .qa import verified_profiles
    from .result_guidance import load_evidence
    model,_,_,hyd,_,_=load_evidence(key,body)
    if hyd.get('model_type')!='river':
        raise ValueError('Choose a solved river')
    values=area(verified_profiles(hyd),body)
    path=core.folder(key)/'assessment_areas'/unique_id()/'scope.json'
    save(path,dict(summary=model['summary'],upstream=values['selected'][0],downstream=values['selected'][-1],created_utc=utc()))
    model['assessment_area']=item(path)
    core.persist(model,'SELECT_ASSESSMENT_AREA',model['assessment_area'])
    return values
