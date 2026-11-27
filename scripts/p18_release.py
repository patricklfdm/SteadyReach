"""Verify mapped historical requests, return dates and independence using local survey originals."""
import argparse
import base64
import csv
import io
import json
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from p11_release import copy_baseline,preview,page_action
from ras_workflow import app_core as core, app_parameters, field_packet, raw_intake
from ras_workflow.common import intact, read, save, sha, unique_id


def archive(key, start, end, extra, folder):
    m=core.model(key)
    result=field_packet.issue(key,dict(summary_hash=m['summary']['sha256'],start=start,end=end,stations=extra))
    file=folder/result['file']
    file.write_bytes(base64.b64decode(result['content'],validate=True))
    with ZipFile(file) as z:
        assert z.testzip() is None
        manifest=json.loads(z.read('Manifest.json'))
        features=json.loads(z.read('Survey_locations.geojson'))['features']
        assert manifest['features']==features and manifest['summary']==m['summary']
        assert any(f['properties']['topic']=='stage' for f in features)
        for feature in features:
            geom=feature['geometry']
            pts=[geom['coordinates']] if geom['type']=='Point' else geom['coordinates']
            assert all(-180<x<180 and -90<y<90 for x,y in pts)
        content=z.read('Field_values.csv').decode('utf-8-sig')
    return dict(zip=file.name,sha256=sha(file),features=[(f['properties']['rs'],f['properties']['topic']) for f in features]),content


def run(args):
    out=ROOT/'status/p18'/unique_id()
    out.mkdir(parents=True)
    records={}
    p17=read(args.p17)['events']
    for river,year,extra in [('Floyd','2024',''),('Turkey','2016','16311.01')]:
        key=p17[river]['project']
        original=sha(core.folder(key)/'app.json')
        hit,content=archive(key,year+'-01-01',year+'-12-31',extra,out)
        page_action(key,'mapped-field-request',start=year+'-01-01',end=year+'-12-31',stations=extra)
        if river=='Floyd':
            assert ('5032.6','tie') in hit['features']
        else:
            assert ('16889.98','profile') in hit['features'] and ('16311.01','profile') in hit['features']
        m=core.model(key)
        table=csv.DictReader(io.StringIO(content))
        row=next(table)
        row.update(value=row['prior'],survey_date='2026-01-01',method='Regression check of date gate only')
        buf=io.StringIO()
        writer=csv.DictWriter(buf,fieldnames=table.fieldnames)
        writer.writeheader()
        writer.writerow(row)
        try:
            field_packet.evidence(key,buf.getvalue(),m['summary']['sha256'])
        except ValueError as e:
            assert 'historical window' in str(e)
        else:
            raise ValueError('Contemporary survey passed the historical gate')
        assert sha(core.folder(key)/'app.json')==original
        records[river]=hit
    wsp=read(args.p11_receipt)['washington']
    key=copy_baseline(args.p11_workspace,wsp['draft'])
    parent=core.model(key)
    original=sha(core.folder(key)/'app.json')
    hit,_=archive(key,'2019-02-06','2019-02-06','',out)
    assert sha(args.measurements)==wsp['original_sha256']
    body,check=preview(key,args.measurements,'stage',dict(profile='Feb06',event='Feb06',date='2019-02-06',flow=41,
                        flow_unit='m3/s',crs='EPSG:32615',datum='NAVD88',unit='m'))
    assert len(check['selectable'])==8
    # Apply just one actual returned survey row and compare the other inputs.
    row=check['selectable'][0]
    child=core.model(raw_intake.action(key,dict(body,lines=[row],confirmed=True,independent=True,token=check['token']),'apply')['id'])
    report=app_parameters.review(child)
    assert report['return_scope']['mode']=='CHANGES_ONLY' and not report['return_scope']['affected']
    assert report['ready'] and sha(core.folder(key)/'app.json')==original and intact([parent['summary']])
    assert intact(child['intake_return']['sources'])
    records['Washington']=dict(**hit,row=row,original=sha(args.measurements),child=child['id'],parent=parent['summary'],
                               reopened_inputs=report['return_scope']['affected'],hydraulic_inputs_retained=len(report['return_scope']['retained']))
    save(out/'release.json',dict(status='PASSED',cases=records,received_new_iowa_measurements=False))
    print(out/'release.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for option in ('p17','p11-workspace','p11-receipt','measurements'):
        p.add_argument('--'+option,type=Path,required=True)
    run(p.parse_args())
