import unittest
from copy import deepcopy

from ras_workflow.hydraulic_confidence import assess, study_effects
from ras_workflow.validation_plan import normalize, score, scope_update, usable


class IndependentEvents(unittest.TestCase):
    def setUp(self):
        self.spec=dict(event='visit',profile='Q',date='2015-10-01',rs='500.00',
                       role='holdout',tolerance_ft=.5,basis='Field comparison protocol')
        self.scope={'validation_plan':normalize([self.spec])}
        self.summary=dict(configuration=dict(production_scope=self.scope),
                          hydraulics=dict(run_id='run',profiles=[dict(profile_id='Q',flow_cfs=50,
                                                                     headwater_rs=900,tailwater_rs=100)]))
        self.event=dict(event='visit',profile='Q',date='2015-10-01',location=dict(rs=500),kind='stage',
                        role='holdout',observed_ft=100.,model_ft=100.25,residual_ft=.25,flow_cfs=50.,uncertainty_ft=.1)

    def outcome(self,**changes):
        return score(self.summary,[dict(self.event,**changes)],{('Q','500'):50.})[0]

    def test_uncertainty_and_exceedance(self):
        self.assertEqual(self.outcome()['state'],'WITHIN')
        self.assertEqual(self.outcome(uncertainty_ft=None)['state'],'PENDING')
        self.assertEqual(self.outcome(uncertainty_ft=.4)['state'],'PENDING')
        self.assertEqual(self.outcome(uncertainty_ft=None,model_ft=99.,residual_ft=-1.)['state'],'EXCEEDED')

    def test_wrong_event_flow_role_station_and_duplicate(self):
        for change in [dict(flow_cfs=40),dict(event='other'),dict(date='2015-10-02'),dict(location=dict(rs=501)),
                       dict(issues=['DATUM']),dict(role='boundary'),dict(role='calibration'),dict(residual_ft=-.25)]:
            with self.subTest(change=change):
                self.assertEqual(self.outcome(**change)['count'],0)
        self.assertEqual(score(self.summary,[self.event,self.event])[0]['state'],'PENDING')
        self.scope['validation_plan'][0]['rs']='900'
        self.assertEqual(self.outcome(location=dict(rs=900))['state'],'BOUNDARY')

    def test_section_flow_must_match_even_when_profile_discharge_matches(self):
        row,=score(self.summary,[self.event],{('Q','500'):35.})
        self.assertEqual((row['state'],row['count']),('PENDING',0))
        self.assertEqual(score(self.summary,[self.event],{})[0]['state'],'PENDING')

    def test_clearing_reservations_does_not_restore_unrestricted_scoring(self):
        cleared=scope_update(self.scope,{})
        self.assertTrue(cleared['validation_protocol_active'])
        self.assertEqual(usable([self.event],cleared)[0]['role'],'context')

    def test_calibration_history_survives_deletion_and_rename(self):
        old={'validation_plan':normalize([dict(self.spec,role='calibration')])}
        empty=scope_update(old,{'validation_plan':[]})
        with self.assertRaises(ValueError):
            scope_update(empty,{'validation_plan':normalize([dict(self.spec,event='new alias')])})
        self.assertEqual(usable([self.event],empty)[0]['role'],'calibration')
        self.assertEqual(usable([dict(self.event,event='different')],self.scope)[0]['role'],'context')

    def test_flow_redistribution_remains_visible_at_stable_stage(self):
        sections=[dict(rs=500,elevation_ft=[102,100,102],profiles=dict(Q=dict(wse_ft=101,flow_cfs=50,overbank_percent=[40,1])))]
        summary=deepcopy(self.summary)
        summary['hydraulics']['profiles'][0]['profile_id']='Q100'
        sections[0]['profiles']['Q100']=sections[0]['profiles'].pop('Q')
        rev=dict(overbank_changes=dict(rows=[dict(station='500.0',delta_points=[20,1])]))
        result=assess(summary,sections,[],revision=rev)['profiles'][0]['sections'][0]
        self.assertEqual(result['decision'],'INVESTIGATE')
        self.assertIn('REVIEW_REVISED_OVERBANK_SHARE',result['messages'])

    def test_spacing_compares_successive_levels_in_selected_intervals(self):
        study=dict(analysis={'sha256':'evidence'},convergence={'status':'NOT_CONVERGED'},
                   cases=[dict(id='baseline'),dict(id='one'),dict(id='two')],
                   intervals=[dict(upstream_rs=600,downstream_rs=400)],
                   spacing_steps=[dict(case='one',previous='baseline',differences=[
                       dict(profile='Q',station=500,delta_wse_ft=.1),dict(profile='Q',station=700,delta_wse_ft=.1)]),
                       dict(case='two',previous='one',differences=[dict(profile='Q',station=500,delta_wse_ft=-.3)])])
        effects=study_effects([study]);self.assertEqual(set(effects),{('Q','500')})
        self.assertEqual([(r['previous'],r['delta_ft']) for r in effects['Q','500']],[('baseline',.1),('one',-.3)])
