"""Check P7 station-level claims against original events and fresh HEC-RAS output."""
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ras_workflow import app_core as core
from ras_workflow.common import ROOT,read,save,sha
from midway_release import page_action,need


def run(gate,historical,visits):
    from p5_release import open_packages
    from pypdf import PdfReader
    from ras_workflow.report_data import collect
    out=gate/'p7';out.mkdir(exist_ok=True);record=dict(status='RUNNING',human='DEFERRED',cross_machine='DEFERRED')
    dest=out/'release.json';save(dest,record)
    try:
        selection=ROOT/'examples/oregon_holdouts/select_visits.py'
        subprocess.run([sys.executable,'-B',str(selection),str(visits),'--offline'],capture_output=True,check=True)
        cohort=read(visits/'selection.json')
        need(len(cohort['stations'])==2 and sum(e['above_sample_p90'] for s in cohort['stations'].values() for e in s['events'])==3,
             'Expected the three preregistered high-flow field visits')
        record.update(site_selection=cohort,historical=json.loads(subprocess.check_output(
            [sys.executable,'-B',str(ROOT/'scripts/p7_historical.py'),str(historical)],cwd=ROOT)))
        siletz=read(gate/'p3/journeys.json')['cases']['Siletz']['project']
        def data(key):return collect(ROOT/core.model(key)['summary']['path'])
        old=data(siletz)['river_checks']['confidence']
        held=next(p for p in old['profiles'] if p['profile']=='Holdout');peak=held['worst']
        need(peak['rs']=='44056' and abs(peak['signed_ft']*.3048-.524)<.001 and held['matched_points']==1,
             'Boundary included in Siletz scoring or residual differs')
        record['siletz']=dict(run=old['run_id'],worst=peak,count=held['matched_points'])
        dex=read(gate/'p4/release.json');key=page_action(dex['baseline'],'river-revision');record['blinded_edition']=key;save(dest,record)
        event=dict(profile='Visit20151001',event='Visit20151001',date='2015-10-01',rs='500',role='holdout',tolerance_ft=.5,basis='Frozen Dexter pilot protocol, 0.5 ft investigation limit.')
        need(page_action(key,'p7-reserve',event=event)=='RESERVED','Event plan was not saved')
        page_action(key,'survey-solve')
        need(not data(key)['river_checks'].get('events'),'Holdout disclosed before the blind solve')
        prior=core.model(dex['revision']);configuration=read(ROOT/prior['summary']['path'])['configuration']
        key=page_action(key,'field-return',kind='observation',file=str(ROOT/configuration['returned_observations'][0]['path']),
                        document=str(ROOT/configuration['returned_observation_originals'][0]['path']),expect='500')
        record['edition']=key;save(dest,record)
        page_action(key,'survey-solve');report=data(key);result=report['river_checks']['confidence']
        profile=result['profiles'][0];station=next(s for s in profile['sections'] if s['rs']=='500')
        observation,=station['observations'];need(observation['state']=='PENDING' and observation['uncertainty_ft'] is None
            and observation['count']==1 and profile['event_count']==1 and not profile['supported_points'],'Uncertain station appeared supported')
        need(observation['role']=='holdout','Observation return lost the blinded event protocol')
        need(page_action(key,'p7-map')=='MAPPED','Hydraulic confidence map did not render')
        from ras_workflow.app_revision import create_draft
        from ras_workflow.app_parameters import review
        draft=create_draft(core.model(key),{});config=report['summary']['configuration']
        index=next(i for i,s in enumerate(config['scenarios']) if s['id']==report['summary']['hydraulics']['scenario_id'])
        name=f'c.scenarios.{index}.channel_n'
        core.update(draft['id'],dict(revision=draft['revision'],values={name:.04},classes={name:'assumed'}))
        revised=review(core.model(draft['id']))['inputs']['production_scope']
        need(revised['validation_plan'][0]['role']=='calibration' and event['date'] in revised['calibration_dates'],
             'Tuned model retained its independent score')
        deleted=create_draft(core.model(key),{})
        clear_plan=dict(core.model(key)['production_scope'],validation_plan=[])
        core.update(deleted['id'],dict(revision=deleted['revision'],production_scope=clear_plan))
        removed=review(core.model(deleted['id']))['inputs']['production_scope']
        need(event['date'] in removed.get('calibration_dates',[]),'Clearing the observed reservation erased its history')
        record['tuning_counterexample']=dict(edition=draft['id'],role='calibration',replacement_required=True,
                                             deleted_plan_edition=deleted['id'],retired_dates=removed['calibration_dates'])
        handoff=ROOT/page_action(key,'transfer-current',selection='Select this edition for diagnostic station-level review.')
        pair=open_packages(handoff);need(pair['run']==result['run_id'],'Delivery run differs')
        for name,phrase in [('EN','Where the observations support this run'),('CN','实测证据适用的断面与流量')]:
            pages=PdfReader(handoff/'Complete/Reports'/('Report_'+name+'.pdf')).pages
            content=''.join(''.join((p.extract_text() or '').split()) for p in pages)
            need(''.join(phrase.split()) in content and '2015-10-01' in content,'Event evidence missing in '+name)
        record.update(status='PASSED',dexter=dict(run=pair['run'],pair=pair,handoff=str(handoff),observed=observation),
                      selection_sha256=sha(visits/'selection.json'))
    except Exception as error:
        record.update(status='FAILED',error=str(error));raise
    finally:save(dest,record)
    return dest
