import unittest

from ras_workflow.purpose_acceptance import evaluate
from ras_workflow.revision_review import investigation


class SurveyDecisionTests(unittest.TestCase):
    def setUp(self):
        self.summary=dict(configuration=dict(production_scope=dict(purpose='review',criteria=dict(
            event='storm',rs='44',profile='observed',max_residual_ft=.5,basis='Project brief'))),
            hydraulics=dict(run_id='test',profiles=[dict(profile_id='observed',flow_cfs=100)]))
        self.row=dict(event='storm',date='2018-01-20',profile='observed',role='holdout',kind='stage',
            issues=[],location=dict(rs='44'),source='level book, page 2',observed_ft=100,model_ft=100.2,
            residual_ft=.2,observed_datum='NAVD88',uncertainty_ft=.1)
    def test_threshold_and_measurement_uncertainty_are_separate(self):
        complete=evaluate(self.summary,[self.row])
        self.assertEqual(complete['state'],'CONDITIONS_MET')
        for lang in ('en','zh'):
            self.assertTrue(any('+0.0610' in r[lang] and 'level book' in r[lang] for r in complete['rows']))
        self.assertEqual(evaluate(self.summary,[dict(self.row,uncertainty_ft=None)])['state'],'NEED_EVIDENCE')
        self.assertEqual(evaluate(self.summary,[dict(self.row,model_ft=101,residual_ft=1,uncertainty_ft=None)])['state'],'REVISE')
    def test_other_profile_and_unmatched_datums_do_not_score(self):
        for change in [dict(profile='another'),dict(issues=['VERTICAL_DATUM_MISMATCH']),
                       dict(issues=['EVENT_DISCHARGE_MISMATCH']),dict(role='boundary')]:
            d=evaluate(self.summary,[dict(self.row,**change)])
            self.assertEqual(d['state'],'NEED_EVIDENCE')
            self.assertFalse(any('+0.0610' in r['en'] for r in d['rows']))
    def test_persistent_wet_side_and_shifted_flow(self):
        ends=[dict(state='still_wet',profile='Q100',station='2600',side='right',previous_depth_ft=1.1784,current_depth_ft=1.21417)]
        rows=investigation(dict(endpoints=dict(rows=ends),warning_delta=-4),
            dict(rows=[dict(station=4200,previous_percent=[20,10],current_percent=[62,8],delta_points=[42,-2])]))
        self.assertEqual([(r['station'],r['side']) for r in rows],[('2600','right'),(4200,'left')])
        self.assertIn('1.178 → 1.214',rows[0]['en'])
        self.assertIn('62.00%',rows[1]['zh'])
        self.assertIn('fell by 4',rows[1]['en'])

