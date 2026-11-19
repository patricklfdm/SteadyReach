"""Local, per-edition counts of requests initiated at the workflow interface."""
from collections import Counter

from .common import read, save, unique_id, utc


def classify(route, body):
    """Never record form values, coordinates, attachments or identifiable user data."""
    counts = Counter()
    confirmations = {'revision','start','study-start','checks-start','geometry/auto-apply','geometry/repair-apply',
                     'geometry/bank-proposal-apply','resolve-dependencies','candidate','use-native-values'}
    requests = {'create','prepare','automatic-prepare','acquire','analyze','attach','catalog-import','native',
                'sources/folder','sources/survey','sources/points','opening-associations','review','next-review',
                'study-prepare','checks-prepare','study-suggest','revision','report','delivery','native-export','native-outputs',
                'geometry/auto-prepare','geometry/repair-preview','geometry/banks','geometry/generate','geometry/picks',
                'geometry/bank-proposal-prepare','save'}
    if route not in requests | confirmations:
        return None
    if route=='save' and not any(body.get(k) for k in ('values','metadata','classes')) and 'gis' not in body:
        return None
    if route=='create':
        counts['manual_hydraulic_fields'] = sum(body.get(k) not in (None,'') for k in ('flow_cfs','channel_n','overbank_n'))
        counts['location_submissions'] = int(body.get('latitude') not in (None,''))
    if route=='save':
        def numeric(value):
            if isinstance(value,(float,int)):
                return not isinstance(value,bool)
            if isinstance(value,list):
                return any(numeric(v) for v in value)
            if isinstance(value,str):
                try:float(value)
                except ValueError:return False
                return True
            return False
        counts['manual_hydraulic_fields'] = sum(numeric(v) for v in body.get('values',{}).values())
    if route=='geometry/auto-prepare' and 'reach_option' in body:
        counts['reach_selections'] = 1
    if route=='geometry/banks':
        counts['bank_pairs_submitted'] = len(body.get('sections',[]))
    if route=='geometry/auto-apply':
        counts['bank_pairs_submitted'] = len(body.get('banks',{}))
    if route=='geometry/picks':
        counts['map_save_requests'] = 1
    if route=='geometry/repair-preview':
        counts['section_adjustments_submitted'] = len(body.get('changes',[]))
    if route in confirmations:
        counts['decision_requests'] = 1
    if route in ('start','study-start','checks-start'):
        counts['compute_consents'] = 1
    return dict(counts)


def record(folder, route, counts, client):
    path = folder/'operator_actions'/(unique_id()+'.json')
    save(path,dict(route=route,counts=counts,at=utc(),client=client))


def inventory(folder, through=None):
    files = sorted((folder/'operator_actions').glob('*.json'))
    totals, actions, clients = Counter(),Counter(),Counter()
    unreadable = 0
    for file in files:
        try:
            event = read(file)
            if through and event['at']>through:
                continue
            route, client, counts = event['route'], event['client'], event['counts']
            if not isinstance(counts,dict) or not all(type(v) is int and v>=0 for v in counts.values()):
                raise ValueError('Invalid counts')
            if not isinstance(route,str) or not isinstance(client,str):
                raise ValueError('Invalid receipt')
        except (ValueError, OSError, TypeError, KeyError):
            unreadable += 1
            continue
        totals.update(counts)
        actions[route] += 1
        clients[client] += 1
    return dict(recorded_requests=sum(actions.values()),unreadable=unreadable,coverage='PARTIAL_HISTORY' if unreadable else 'FROM_CREATION' if actions['create'] or actions['revision'] else
                'RECORDED_REQUESTS_ONLY' if actions else 'NO_RECORDED_HISTORY',
                counts=dict(totals),routes=dict(actions),clients=dict(clients))


def lineage(model):
    """Count only this edition and the ancestors up to each branch time."""
    from .app_core import folder
    seen = set()
    editions = []
    through = None
    complete = True
    totals = Counter()
    while model['id'] not in seen:
        key = model['id']
        seen.add(key)
        entry = inventory(folder(key),through)
        editions.append(dict(id=key,through=through,**entry))
        totals.update(entry['counts'])
        complete = complete and entry['coverage']=='FROM_CREATION'
        parent = model.get('parent_revision') or {}
        if not parent.get('project_id'):
            break
        through = parent.get('created_utc')
        file = folder(parent['project_id'])/'app.json'
        if not through or not file.is_file() or parent['project_id'] in seen:
            complete = False
            break
        model = read(file)
    return dict(editions=editions,complete=complete,counts=dict(totals),
                recorded_requests=sum(v['recorded_requests'] for v in editions))
