import unittest

from ras_workflow.edition_brief import build


class EditionBrief(unittest.TestCase):
    def test_scope_filters_field_claims_and_protects_source_notes(self):
        summary=dict(configuration=dict(production_scope=dict(calibration_dates=['2018-01-01'])),
                     hydraulics=dict(run_id='native',model_type='river',profiles=[dict(profile_id='P',flow_cfs=51)]))
        stage=dict(role='holdout',kind='stage',date='2019-01-01',event='field',profile='P',location={'rs':'500'},
                   residual_ft=0.22,flow_cfs=51,source='private-file-name.pdf')
        records=[stage,dict(stage,date='2018-01-01',location={'rs':'401'}),dict(stage,role='boundary',location={'rs':'100'})]
        result=build(summary,dict(en='Review',zh='复核'),records)
        self.assertEqual(result['run_id'],'native')
        self.assertEqual(len(result['rows']),4)
        self.assertIn('RS 500 @ 51 cfs',result['rows'][1]['en'])
        self.assertIn('测量负责人',result['rows'][3]['zh'])
        for private in ('401','RS 100','private-file-name'):
            self.assertNotIn(private,str(result))

    def test_dem_prioritizes_bathymetry_when_no_observation_is_available(self):
        summary=dict(configuration={},hydraulics=dict(model_type='river',channel_geometry_basis='conditional_surface_dem'))
        rows=build(summary,dict(en='Review',zh='复核'),[])['rows']
        self.assertIn('Independent field stage comparison is pending',rows[1]['en'])
        self.assertIn('床',rows[3]['zh'])
