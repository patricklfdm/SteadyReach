import unittest

from ras_workflow.review_decisions import residual_regression, site_steps


class ReviewDecisions(unittest.TestCase):
    def setUp(self):
        self.obs=dict(event='high',date='2016-08-25',profile='Peak',source='survey row 14',
                      observed_datum='NAVD88',observed_ft=100.,flow_cfs=320.,location={'rs':'250'},
                      role='holdout',kind='stage',issues=[],model_ft=100.3,residual_ft=.3)
        self.rev=dict(self.obs,model_ft=99.,residual_ft=-1.)
        self.xs=dict(profile='Peak',station='250.0',previous=100.3,current=99.,location_status='SAME_CENTER')

    def test_warning_reduction_and_worse_fit(self):
        row=residual_regression([self.obs],[self.rev],[self.xs],-4)
        self.assertEqual(row['code'],'FIELD_REGRESSION')
        self.assertIn('-1.000 ft',row['zh'])
        self.assertIn('Retain the parent',row['en'])

    def test_only_paired_native_stages_count(self):
        for change in [dict(role='boundary'),dict(role='calibration'),dict(source='new mark'),
                       dict(observed_datum='NGVD29'),dict(date='2016-08-24'),dict(flow_cfs=420.),
                       dict(observed_ft=101.),dict(issues=['transfer']),dict(model_ft=102.)]:
            with self.subTest(change=change):
                self.assertIsNone(residual_regression([self.obs],[dict(self.rev,**change)],[self.xs],-1))
        self.assertIsNone(residual_regression([self.obs]*2,[self.rev],[self.xs],-1))
        self.assertIsNone(residual_regression([self.obs],[self.rev],[dict(self.xs,location_status='MOVED')],-1))
        self.assertIsNone(residual_regression([self.obs],[self.rev],[self.xs],None))
        self.assertIsNone(residual_regression([self.obs],[self.rev],[self.xs],0))

    def test_excluded_event_and_local_tolerance(self):
        scope={'criteria':{'max_residual_ft':.5,'event':'high','rs':'250','profile':'Peak'}}
        self.assertIn('Project limit 0.5 ft',site_steps(scope,[self.rev],[])[0]['en'])
        self.assertEqual(site_steps(dict(scope,calibration_dates=['2016-08-25']),[self.rev],[]),[])
        self.assertEqual(site_steps(scope,[dict(self.rev,role='boundary')],[]),[])
        self.assertNotIn('Project limit',site_steps({'criteria':dict(scope['criteria'],rs='350')},[self.rev],[])[0]['en'])

    def test_boundary_farthest_exceedance_in_each_direction(self):
        def study(side,changes):
            return dict(analysis={'path':'analysis'},cases=[dict(id='low',changes=[dict(path='boundary_slopes.'+side)])],
                        comparisons=[dict(case='low',cross_section_differences=[dict(profile='Peak',station=str(station),delta_wse_ft=delta) for station,delta in changes])])
        for side,rs in [('downstream',400),('upstream',100)]:
            row,=site_steps({},[],[study(side,[(100,2.),(200,0.),(300,.05),(400,-.11)])])
            self.assertIn('2/4',row['en'])
            self.assertIn(f'farthest tested exceedance was RS {rs}',row['en'])
        self.assertEqual(site_steps({},[],[study('downstream',[(100,0.)])]),[])
