"""Read paired delivery evidence and run conditional/native-only pilot entries."""
from pathlib import Path
from pypdf import PdfReader

from ras_workflow import app_core, cli, native_review
from ras_workflow.common import ROOT, item, intact, read, save, sha
from ras_workflow.delivery_pair import check
from ras_workflow.qa import verified_profiles
from ras_workflow.site_delivery import verify


class FalseRelease(ValueError):
    """An input gate actually admitted a preregistered blocker."""


def receipt_pair(receipt_path, expect_mapped):
    receipt=read(receipt_path)
    if not intact([receipt['summary']]):
        raise ValueError('Pilot run summary changed')
    source=read(ROOT/receipt['summary']['path'])
    native=source['hydraulics']
    profiles=verified_profiles(native)
    delivery=receipt['delivery']
    packs={k:ROOT/delivery[k]['path'] for k in ('complete','minimal')}
    verified={k:verify(folder)['files'] for k,folder in packs.items()}
    pair=check(packs['complete'],packs['minimal'])
    if (receipt.get('errors') or pair['mapped']!=expect_mapped or pair['run_id']!=native['run_id']
            or pair['native_hdf_sha256']!=native['raw_hdf']['sha256']):
        raise ValueError('Unexpected mapping scope, native result, or incomplete job')
    lang={}
    for name in ('EN','CN'):
        pdf=packs['complete']/'Reports'/('Report_'+name+'.pdf')
        lang[name]=dict(pages=len(PdfReader(pdf).pages),sha256=sha(pdf))
        if not lang[name]['pages']:
            raise ValueError('Unreadable report '+str(pdf))
    data=read(packs['complete']/'Reports/report_data.json')
    purpose=data['purpose_decision']
    if delivery.get('status')!=('READY_FOR_REVIEW' if expect_mapped else 'READY_NATIVE_ONLY'):
        raise ValueError('Delivery has not passed file-level technical review')
    if source['gate']['engineering_acceptance_status']!='NOT_ASSESSED' or delivery['engineering_acceptance']!='NOT_ASSESSED':
        raise ValueError('Automated package attributed independent engineering approval')
    return dict(run=native['run_id'],native_hdf=native['raw_hdf']['sha256'],profiles={n:len(v) for n,v in profiles.items()},
        receipt=item(receipt_path),mapped=pair['mapped'],flows_cfs={p['profile_id']:p['flow_cfs'] for p in native['profiles']},
        packages={k:str(v) for k,v in packs.items()},package_files=verified,
        reports=lang,decision=purpose['state'],limitations=purpose.get('open_items',[]),verified_pair=True,
        solver_reused=receipt.get('solver_reused'),first_pass_pair=not receipt.get('export_from'),stage_seconds=receipt.get('stage_seconds'),
        field_events=(data.get('river_checks') or {}).get('events',[]))


def edition_pair(key):
    edition=app_core.model(key)
    summary=ROOT/edition['summary']['path']
    if not intact([edition['summary']]):
        raise ValueError('Edition summary changed')
    result=receipt_pair(summary.parent/'attempt_receipt.json',True)
    result['edition']=key
    return result


def run_config(path,scenario,out,mapped):
    receipt=out/'pilot_attempt.json'
    result=cli.execute(path,scenario,fresh=True,receipt_path=receipt)
    if not receipt.is_file() or result!=0:
        raise ValueError('Pilot job failed; see '+str(receipt))
    return receipt_pair(receipt,mapped)


def native_input(source,kind,out,tamper=False):
    if kind=='spring':
        title='USACE Spring Creek example 3';unit='international ft';datum='Published local reference; model-space reproduction only'
        basis='USACE HEC-RAS Application Guide Example 3, TWINPIPE.p01. English-unit foot convention assumed for model-space comparison.'
    else:
        title='Phelps Brook, River Road';unit='US survey foot';datum='NAVD88'
        basis='USGS field-based hydraulic models version 2.0, https://doi.org/10.5066/P14HJGZI. Explicit original p01.'
    review=native_review.prepare(source,out/'review',selected_plan='p01')
    packet=read(review)
    decision=dict(project_id='pilot_'+kind,title=title,source=basis,native_length_unit=unit,vertical_datum=datum,approve=True)
    if tamper:
        path=ROOT/packet['files']['geometry']['path']
        before=sha(path)
        with path.open('ab') as f:f.write(b'\r\n')
        try:native_review.approve(review,decision,direct_start=True)
        except ValueError as error:
            if 'Native source files changed' not in str(error):raise
            return dict(outcome='BLOCKED',reason=str(error),original=before,changed=sha(path),review=item(review))
        raise FalseRelease('Altered model advanced through the review gate')
    config=native_review.approve(review,decision,direct_start=True)
    result=run_config(config,'baseline',out,False)
    summary=read(ROOT/read(ROOT/result['receipt']['path'])['summary']['path'])
    if kind=='spring':
        stages=verified_profiles(summary['hydraulics'])
        boundary={row['profile_number']:row['downstream']['stage_ft'] for row in packet['boundaries']}
        observed=[(p['id'],boundary[i+1],stages[p['id']][packet['expected_native']['xs_stations'][-1]])
                  for i,p in enumerate(packet['profiles'])]
        if any(abs(a-b)>.002 for _,a,b in observed):raise ValueError('Fixed boundary level differs from source')
        result['prescribed_outlet_ft']=observed
    else:
        from ras_workflow.common import safe_path
        field=read(ROOT/'examples/phelps_brook/published_reference.json')
        native=summary['hydraulics'];levels=verified_profiles(native)[field['profile']]
        checks={}
        for metric in field['metrics']:
            if metric['variable']=='W.S. Elev':
                value=next(v for k,v in levels.items() if float(k)==float(metric['station']))
            else:
                from ras_workflow.results import value as native_value
                controller=read(safe_path(ROOT,native['raw_controller']['path']))
                row, = [entry for entry in controller['rows'] if entry['profile']==field['profile']
                        and entry['node_type']==metric['node_type'] and entry['updn_argument']==0
                        and float(entry['station'])==float(metric['station'])]
                value = native_value(row['metrics'][metric['variable']])
                if value is None:
                    raise ValueError('Missing published comparison variable '+metric['variable'])
            reference=field['values'][metric['column']]
            checks[metric['column']]=dict(observed_model_output=value,published_model_value=reference,tolerance=metric['tolerance'])
            if abs(value-reference)>metric['tolerance']:
                raise ValueError('Phelps source model reproduction differs at '+metric['station'])
        result['published_model_comparison']=checks
    return result
