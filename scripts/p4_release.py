"""One-workstation P4 holdout. Operate the public pages and check the native outputs."""
import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ras_workflow import app_core as core
from ras_workflow.common import ROOT, intact, read, save, sha, unique_id
from ras_workflow.delivery_pair import check
from ras_workflow.qa import verified_profiles
from midway_release import need, page_action


def run(survey,observation,imagery,directory):
    from pypdf import PdfReader
    directory.mkdir(parents=True,exist_ok=False)
    source=read(ROOT/'examples/dexter_or/frozen_sources.json')
    need(sha(survey/'survey.json')==source['survey.json'] and sha(observation)==source['event_return.csv'],'Frozen source selection differs')
    for row in read(survey/'survey.json')['files']:
        need(sha(survey/row['name'])==row['sha256'],'Survey member differs')
    result=dict(status='RUNNING',steps=[],human_acceptance='DEFERRED',cross_machine='DEFERRED')
    def save_result():
        save(directory/'release.json',result)
    def page(key,mode,**args):
        path=directory/(str(len(result['steps']))+'_'+mode+'.json')
        result['steps'].append(dict(project=key,mode=mode));save_result()
        return page_action(key,mode,metrics=str(path),**args)
    try:
        protocol=read(ROOT/'examples/dexter_or/protocol.json')
        profile='Visit20151001'
        criteria={'accept-profile':profile,'accept-event':profile,'accept-rs':'500','accept-error':protocol['threshold_ft'],'accept-basis':protocol['threshold_basis']}
        import shutil
        from ras_workflow.survey_import import make_manifest
        baseline_inputs=directory/'baseline_inputs';baseline_inputs.mkdir()
        manifest=read(survey/'survey.json')
        numbers=read(survey/'measurements.json')
        event=[v for v in numbers['features'] if v['properties']['reading_type']=='Discharge'
               and v['properties']['field_visit_id']=='4a960721-bade-9752-e053-0100007fd102']
        need(len(event)==1 and float(event[0]['properties']['value'])==1540,'Frozen event discharge differs')
        save(baseline_inputs/'Discharge.json',event[0]['properties'])
        citations=[]
        for ref in manifest['files']:
            filename=ref['name']
            if filename=='measurements.json':
                filename='Discharge.json'
            else:shutil.copyfile(survey/filename,baseline_inputs/filename)
            citations.append((baseline_inputs/filename,ref['source']))
        shutil.copyfile(survey/'definition.json',baseline_inputs/'definition.json')
        make_manifest(baseline_inputs/'definition.json',citations)
        masked=read(baseline_inputs/'survey.json')
        need(all(masked[k]==manifest[k] for k in ('scenario','geometry','location','terrain')),'Blinding changed the hydraulic model')
        result['blinded_baseline_sha256']=sha(baseline_inputs/'survey.json')
        key=page(None,'home-survey',title='Dexter · independent field review',folder=str(baseline_inputs),criteria=criteria,
                 rasters=[str(imagery/n) for n in ('Aerial.tif','acquisition.json')])
        result['baseline']=key;save_result()
        page(key,'survey-solve')
        def inspect(project):
            model=core.model(project)
            need(model.get('summary') and intact([model['summary']]),'No matching native calculation')
            return read(ROOT/model['summary']['path'])
        first=inspect(key);water=verified_profiles(first['hydraulics'])
        need(len(water[profile])==9 and first['hydraulics']['profiles'][0]['flow_cfs']==1540,'Native flow or sections differ')
        result['baseline_priority']=page(key,'priority-read')
        child=page(key,'field-return',kind='observation',file=str(observation),document=str(survey/'measurements.json'),expect='500')
        result['revision']=child;save_result()
        page(child,'survey-solve')
        second=inspect(child);hyd=second['hydraulics']
        need(hyd['run_id']!=first['hydraulics']['run_id'] and verified_profiles(hyd)==water,'Evidence-only revision changed stage or reused the run')
        result['revision_priority']=page(child,'priority-read')
        folder=ROOT/page(child,'transfer-current',selection='Use the independent field comparison for diagnostic engineering review.')
        pair=check(folder/'Complete',folder/'Minimal')
        need(pair['mapped'] and pair['native_hdf_sha256']==hyd['raw_hdf']['sha256'],'Mapped handoff and native run differ')
        page(None,'recipient-copy',url_override=(folder/'Start_EN.html').as_uri(),run_id=hyd['run_id'],folder=str(folder))
        data=read(folder/'Complete/Reports/report_data.json')
        measured,=data['river_checks']['events'];decision=data['purpose_decision']
        expected_stage=3.14+592.30+1.102/.3048
        local,=[v for k,v in water[profile].items() if float(k)==500]
        need(abs(measured['observed_ft']-expected_stage)<.00001 and abs(measured['residual_ft']-(local-expected_stage))<.00001,
             'Independent datum arithmetic or native interior stage differs')
        expected='REVISE' if abs(measured['residual_ft'])>protocol['threshold_ft'] else 'NEED_EVIDENCE'
        need(decision['state']==expected and measured['uncertainty_ft'] is None and measured['location']['rs']=='500','Observed purpose verdict differs')
        delta=f"{measured['residual_ft']*.3048:+.4f}"
        need(delta in result['revision_priority'] or '500' in result['revision_priority'],'Missing event on the result page')
        for pdf,html in [('Report_EN.pdf','Start_EN.html'),('Report_CN.pdf','Start_zh-CN.html')]:
            words=' '.join(p.extract_text() or '' for p in PdfReader(folder/'Complete/Reports'/pdf).pages)
            guide=(folder/html).read_text('utf-8')
            need(delta in words and delta in guide and hyd['run_id'] in guide and 'observed_profiles.csv' in guide,'Field evidence missing from '+pdf+' or '+html)
        originals=second['configuration'].get('returned_observation_originals',[])
        need(len(originals)==1 and originals[0]['sha256']==sha(survey/'measurements.json'),'Missing original measurement identity')
        counts=Counter();operator=Counter();clicks=0
        for path in directory.glob('*_*.json'):
            events=read(path);counts.update(events['entries']);operator.update(events['enteredFields']);clicks+=events['clicks']
        result.update(status='PASSED',run=hyd['run_id'],baseline_run=first['hydraulics']['run_id'],handoff=str(folder),
            decision=decision['state'],event=measured,native_hdf=hyd['raw_hdf'],clicks=clicks,
            entered_fields=sum(operator.values()),repeated_explicit_entries={k:v-1 for k,v in operator.items() if v>1},
            repeated_input_events={k:v-1 for k,v in counts.items() if v>1},manual_project_json_edits=0)
    except Exception as e:
        result.update(status='FAILED',error=str(e));raise
    finally:save_result()


def midway_returns(project,directory):
    """Three independent operator returns at one sealed Midway baseline."""
    import csv
    import io
    from ras_workflow import field_return
    m=core.model(project);original=m['summary'].copy()
    identity=dict(summary_hash=original['sha256'])
    source=field_return.perform(project,identity,'request')['csv']
    cases={}
    for name,fields,wrong in [('wrong_datum',1,True),('partial',1,False),('both_assumed',2,False)]:
        table=list(csv.DictReader(io.StringIO(source)))
        elevations=[r for r in table if r['field'].endswith(('.us_invert_ft','.ds_invert_ft'))]
        need(len(elevations)>=2,'Midway must expose both invert elevations')
        for r in elevations[:fields]:
            r.update(value=str(round(float(r['prior'])+.05,4)),evidence_class='assumed',
                     source='Isolated training return +0.05 ft. No field measurement.')
            if wrong:r['datum']='NGVD29'
        path=directory/(name+'.csv')
        with path.open('w',encoding='utf-8-sig',newline='') as out:
            writer=csv.DictWriter(out,fieldnames=field_return.COLUMNS);writer.writeheader();writer.writerows(table)
        args=dict(kind='geometry',file=str(path))
        if wrong:
            need(page_action(project,'field-return',error='supply ft',**args)=='BLOCKED','Wrong datum accepted')
            cases[name]='BLOCKED';continue
        child=page_action(project,'field-return',expect='Group 1',**args)
        c=core.model(child)
        from ras_workflow.common import read
        draft=read((ROOT/c['session']).parent/'draft.json')
        for r in elevations[:fields]:
            answer=draft['answers'][r['field']]
            need(answer['evidence_class']=='assumed' and answer['value']==float(r['value']),'Incorrect returned invert classification')
        if fields==1:
            other=elevations[1]
            need(float(draft['answers'][other['field']]['value'])==float(other['prior']),'Partial return overwrote the other invert')
        cases[name]=dict(project=child,fields=fields)
        if fields==2:
            page_action(child,'survey-solve',metrics=str(directory/'midway_both_solve_page.json'))
            summary=read(ROOT/core.model(child)['summary']['path'])
            need(summary['hydraulics']['run_id']!=read(ROOT/original['path'])['hydraulics']['run_id'],'Revision did not recalculate')
            from ras_workflow.revision_inputs import bound_inputs
            _,geometry,_=bound_inputs(summary)
            for r in elevations[:fields]:
                group=geometry['structure']['groups'][int(r['field'].split('.')[3])]
                need(abs(group[r['field'].split('.')[-1]]-float(r['value']))<.000001,'Calculated geometry lost the returned elevation')
            cases[name]['run']=summary['hydraulics']['run_id']
            cases[name]['priorities']=page_action(child,'priority-read')
    need(core.model(project)['summary']==original and intact([original]),'Original Midway changed')
    save(directory/'midway_returns.json',cases)
    return cases


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for arg in ('survey','observation','imagery'):p.add_argument('--'+arg,type=Path,required=True)
    a=p.parse_args();out=ROOT/'status/p4_release'/unique_id()
    print(out,flush=True);run(a.survey.resolve(),a.observation.resolve(),a.imagery.resolve(),out)
