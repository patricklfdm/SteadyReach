from unittest import TestCase
from unittest.mock import patch

from ras_workflow import field_feedback as field, field_results as results


def point(rs='100',role='boundary',**changes):
    row=dict(point_id=rs,event='flood A',date='2019-02-21',rs=rs,role=role,stage_ft=17.,datum='NAVD88',flow_cfs=450.,
             original_source='field notes, sheet 1',point_type='measured',basis='documented',uncertainty_ft=.20,reference='GNSS check A')
    return {**row,**changes}


class FieldFeedbackTests(TestCase):
    def test_partial_csv_keeps_other_station_and_cannot_change_original(self):
        first,second=point(),point('200','holdout')
        edited=dict(second,basis='assumed',reference='test, quoted "note"',uncertainty_ft=.1)
        rows=field.merge_feedback([first,second],field.csv_text([edited]))
        self.assertEqual(rows,[first,edited])
        # Browsers serialize whole numbers without trailing .0.
        self.assertEqual(field.merge_feedback([first],field.csv_text([dict(first,flow_cfs=450)])),[first])
        for bad in [[dict(first,flow_cfs=451)],[dict(first,event='other')],[dict(first,point_id='unknown')],[first,first]]:
            with self.assertRaises(ValueError):field.merge_feedback([first],field.csv_text(bad))

    def test_traceable_positive_uncertainty_and_known_point_type_required(self):
        p=point()
        for invalid in [dict(uncertainty_ft='nan'),dict(uncertainty_ft=0),dict(uncertainty_ft=-1),
                        dict(reference=''),dict(basis='unknown'),dict(point_type='maybe')]:
            with self.assertRaises(ValueError):field.merge_feedback([p],field.csv_text([{**p,**invalid}]))
        self.assertEqual(field.event_spec([dict(p,point_type='interpolated')])['blockers'],['BOUNDARY_ACCURACY'])

    def test_no_automatic_gage_transfer_and_no_conflicting_event(self):
        self.assertIn('BOUNDARY_OBSERVATION',field.event_spec([point('200','holdout')])['blockers'])
        self.assertIn('CONFLICTING_CONTROLS',field.event_spec([point(),point(stage_ft=18)])['blockers'])
        self.assertIn('EVENT_FLOW',field.event_spec([point(),point('200','holdout',flow_cfs=451)])['blockers'])
        self.assertIn('MIXED_EVENT_ROLES',field.event_spec([point(),point('200','holdout'),point('300','calibration')])['blockers'])

    def test_profiles_derived_from_event_stage_and_reported_uncertainty(self):
        spec=field.event_spec([point(),point('200','holdout')])
        self.assertEqual(spec['blockers'],[])
        self.assertEqual([(r['profile'],r['stage_ft']) for r in spec['stages']],
                         [('EventBase',17.),('TailLow',16.8),('TailHigh',17.2)])
        self.assertFalse(spec['assumed'])
        self.assertEqual(spec['uses']['documented'],['100','200'])

    def test_only_documented_measured_points_can_support_field_comparison(self):
        observations=[point(residual_ft=None),point('200','holdout',residual_ft=.04),
                      point('300','holdout',residual_ft=.01,point_type='interpolated')]
        data=dict(mode='event',assumed=False,observations=observations)
        rows=results.verified_observations(data)
        self.assertEqual([r['location']['rs'] for r in rows],['100','200'])
        self.assertIsNone(rows[0]['residual_ft'])
        self.assertEqual(results.verified_observations(dict(data,assumed=True)),[])

    def test_switching_events_restores_only_the_record_for_the_requested_source_and_scope(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from ras_workflow import common
        with TemporaryDirectory() as directory:
            root=Path(directory);reviews=root/'field_followups'
            model=dict(id='parent',summary='run',river_observations='csv',assessment_area='scope')
            with patch.object(common,'ROOT',root),patch.object(field,'ROOT',root),patch.object(field.core,'folder',return_value=root):
                for event in ('A','B'):
                    record=reviews/event/'review.json'
                    common.save(record,dict(event=event,date='2019-02-21',parent_summary='run',area_record='scope',parent_observations='csv'))
                    ref=common.item(record)
                    common.save(reviews/'events'/(common.digest([event,'2019-02-21'])+'.json'),ref)
                    common.save(reviews/'latest_event.json',ref)
                self.assertEqual(field.latest(model,'event')['review']['event'],'B')
                self.assertEqual(field.latest(model,'event','A','2019-02-21')['review']['event'],'A')
                self.assertIsNone(field.latest(model,'event','A','2020-02-21'))
                self.assertIsNone(field.latest(dict(model,assessment_area='different'),'event','A','2019-02-21'))
                self.assertIsNone(field.latest(dict(model,river_observations='new CSV'),'event','A','2019-02-21'))
                common.save(reviews/'A'/'review.json',{})
                with self.assertRaisesRegex(ValueError,'changed'):field.latest(model,'event','A','2019-02-21')

    def test_one_native_event_series_covers_two_directions_of_its_baseline(self):
        from ras_workflow.result_assessment import boundary_findings
        water={'100':5.,'200':5.,'300':5.}
        profiles=['EventBase','TailLow','TailHigh']
        hyd=dict(profiles=[dict(profile_id=p) for p in profiles],flow_regime='subcritical')
        area=dict(stations=['300','200','100'],selected=['300','200'])
        data=dict(mode='event',assumed=True,responses=[
            dict(profile='TailLow',threshold_ft=.1,by_rs={'100':-.2,'200':-.15,'300':-.05}),
            dict(profile='TailHigh',threshold_ft=.1,by_rs={'100':.2,'200':.16,'300':.05})])
        findings,cases=boundary_findings([],hyd,'sensitivity',{p:water for p in profiles},area,data)
        self.assertEqual([f['code'] for f in findings],['BOUNDARY_INFLUENCE'])
        self.assertEqual(cases[0]['area'],dict(station='200',affected=1,compared=2,delta_ft=-.15))
        hyd['flow_regime']='mixed'
        findings,_=boundary_findings([],hyd,'sensitivity',{p:water for p in profiles},area,data)
        self.assertEqual(findings[-1]['facts']['missing'],['upstream / EventBase'])

    def test_native_tailwater_check_and_signed_area_differences(self):
        obs=[point(),point('200','holdout')]
        spec=dict(field.event_spec(obs),mode='event',date=obs[0]['date'],event=obs[0]['event'],area=['200'],
                  child='field_case',parent_summary={},geometry_summary={},sources=[{}],engineering_acceptance='NOT_ASSESSED')
        ref={'path':'review.json'}
        hyd={'profiles':[dict(profile_id=p['profile'],flow_cfs=450.) for p in spec['stages']],'run_id':'test'}
        summary=dict(configuration={'field_feedback':ref,'project_id':'field_case'},hydraulics=hyd)
        stages=dict(EventBase={'100':17.,'200':19.},TailLow={'100':16.8,'200':18.85},TailHigh={'100':17.2,'200':19.08})
        with patch.object(results,'intact',return_value=True),patch.object(results,'read',return_value=spec),patch.object(results,'verified_profiles',return_value=stages):
            data,_=results.collect(summary)
            self.assertEqual(data['responses'][0]['affected'],['200'])
            self.assertEqual(data['responses'][1]['affected'],[])
            self.assertAlmostEqual(data['responses'][0]['delta_ft'],-.15)
            self.assertIsNone(data['observations'][0]['residual_ft'])
            stages['TailLow']['100']=18.
            with self.assertRaisesRegex(ValueError,'Native tailwater'):results.collect(summary)
