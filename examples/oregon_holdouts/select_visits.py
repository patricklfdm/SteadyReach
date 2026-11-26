"""Freeze approved USGS field visits selected by the predeclared sampling protocol."""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path
from statistics import quantiles
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

PROTOCOL=Path(__file__).with_name('protocol.json')
BASE='https://api.waterdata.usgs.gov/ogcapi/v0/collections/field-measurements/items'


def select(pages,station,previous,count):
    visits=defaultdict(lambda:defaultdict(list))
    for data in pages:
        for feature in data['features']:
            p=feature['properties']
            if p['monitoring_location_id']!=station:raise ValueError('Unexpected station in USGS response')
            if p['approval_status']=='Approved':
                visits[p['field_visit_id']][p['reading_type']].append(p)
    pairs=[]
    for visit,types in visits.items():
        flow,stage=types['Discharge'],types['MeanGageHeight']
        if len(flow)!=1 or len(stage)!=1:continue
        q,z=flow[0],stage[0]
        if (q['unit_of_measure'],z['unit_of_measure'])!=('ft^3/s','ft') or q['time'][:10]!=z['time'][:10]:continue
        v=float(q['value']);h=float(z['value'])
        if not math.isfinite(v) or v<=0 or not math.isfinite(h):continue
        pairs.append(dict(visit=visit,date=q['time'][:10],flow_cfs=v,gage_height_ft=h))
    threshold=quantiles([r['flow_cfs'] for r in pairs],n=10,method='inclusive')[8] if len(pairs)>1 else None
    selected=[]
    for r in sorted(pairs,key=lambda x:(-x['flow_cfs'],x['visit'])):
        day=date.fromisoformat(r['date'])
        if all(abs((day-d).days)>=30 for d in previous):
            previous.append(day)
            selected.append(dict(r,station=station,above_sample_p90=threshold is not None and r['flow_cfs']>=threshold,
                                 modeled_residual_ft=None,status='PENDING_MATCHED_MODEL_AND_VERTICAL_EVIDENCE'))
        if len(selected)==count:break
    return dict(paired_visits=len(pairs),visit_p90_cfs=threshold,events=selected)


def main(folder,offline):
    folder.mkdir(parents=True,exist_ok=True)
    protocol=PROTOCOL.read_bytes();spec=json.loads(protocol);pin=folder/'preregistered.json'
    if pin.exists() and pin.read_bytes()!=protocol:raise ValueError('Preregistered protocol changed')
    if not pin.exists():
        if offline:raise ValueError('Missing frozen preregistration')
        pin.write_bytes(protocol)
    receipt=dict(protocol_sha256=hashlib.sha256(protocol).hexdigest(),stations={},sources={});previous=[]
    for site in spec['stations']:
        station=site['id']
        url=BASE+'?'+urlencode(dict(f='json',monitoring_location_id=station,datetime=spec['start']+'/'+spec['end'],limit=10000))
        pages=[];seen=set()
        while url:
            if url in seen or urlsplit(url).netloc!='api.waterdata.usgs.gov':raise ValueError('Unexpected USGS pagination')
            seen.add(url);path=folder/(station+'_'+str(len(pages))+'.json')
            if not offline:
                with urlopen(url,timeout=90) as response:raw=response.read(20000001)
                if len(raw)>20000000:raise ValueError('Unexpected USGS response size')
                if path.exists() and path.read_bytes()!=raw:raise ValueError('Choose a new freeze folder')
                path.write_bytes(raw)
            raw=path.read_bytes();data=json.loads(raw);pages.append(data)
            receipt['sources'][path.name]=dict(url=url,sha256=hashlib.sha256(raw).hexdigest())
            url=next((r['href'] for r in data['links'] if r['rel']=='next'),None)
        receipt['stations'][station]=select(pages,station,previous,site['events'])
    path=folder/'selection.json'
    if offline and json.loads(path.read_text())!=receipt:raise ValueError('Frozen selection differs')
    if not offline:path.write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt['stations'],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path);parser.add_argument('--offline',action='store_true')
    args=parser.parse_args();main(args.folder,args.offline)
