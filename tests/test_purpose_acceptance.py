import unittest

from ras_workflow.feasibility import scope
from ras_workflow.purpose_acceptance import criteria, evaluate, geometry_record
from ras_workflow.source_extract import text_parameters


class PurposeAcceptance(unittest.TestCase):
    def result(self,rules,purpose='screening',**kwargs):
        summary={'configuration':{'production_scope':{'purpose':purpose,'criteria':rules}},
                 'hydraulics':{'run_id':'test','unit':'international ft','profiles':[
                     {'profile_id':'Q100','flow_cfs':10,'metrics':{'road_freeboard_ft':0},'qa':{'wet_edges':[]}}]}}
        return evaluate(summary,**kwargs)['state']

    def test_agreement_and_limits(self):
        self.assertNotIn('criteria',scope({}))
        self.assertEqual(self.result(None),'NEED_EVIDENCE')
        self.assertEqual(self.result({'min_freeboard_ft':0,'basis':'Owner brief'}),'CONDITIONS_MET')
        self.assertEqual(self.result({'min_freeboard_ft':.1,'basis':'Owner brief'}),'REVISE')
        self.assertEqual(self.result({'profile':'Q500'}),'NEED_EVIDENCE')
        for row in [{'max_residual_ft':.2},{'min_freeboard_ft':True},{'min_freeboard_ft':1},
                    {'dry_ends':'false'},{'unknown':True},{'max_residual_ft':float('nan')}]:
            with self.subTest(row=row),self.assertRaises(ValueError):
                criteria(row)

    def test_each_open_condition_routes_to_its_own_evidence(self):
        rules=dict(dry_ends=True,site_geometry=True,min_freeboard_ft=1,event='flood',
                   basis='Owner brief',max_residual_ft=.2)
        profile=dict(profile_id='Q100',flow_cfs=457,qa=dict(wet_edges=['900','800']),metrics={})
        summary=dict(configuration=dict(production_scope=dict(purpose='comparison',criteria=rules)),
                     hydraulics=dict(run_id='test',model_type='culvert',profiles=[profile]))
        rows=evaluate(summary)['rows']
        actions={r['action']['tool']:r['action'] for r in rows if r['state']!='met'}
        self.assertEqual(set(actions),{'atlas','native','comparison','invert-request','observations'})
        self.assertEqual(actions['atlas'],dict(tool='atlas',profile='Q100',stations=['900','800']))
        self.assertTrue(all('action' not in r for r in rows if r['state']=='met'))
        summary['hydraulics']['model_type']='river'
        profile['qa']['wet_edges']=[]
        tools={r['action']['tool'] for r in evaluate(summary)['rows'] if 'action' in r}
        self.assertIn('field-feedback',tools)
        self.assertNotIn('atlas',tools)

    def test_comparison_requires_shared_verified_centers_for_selected_profile(self):
        def check(rows):
            return self.result({},'comparison',comparison={'status':'COMPARISON_NOT_ACCEPTANCE','profiles':rows,
                'cross_sections':[dict(profile='Q100',station='100',location_status='SAME_CENTER')]})
        self.assertEqual(check([{'profile':'Q100','verified_center_count':1}]),'NEED_EVIDENCE')
        self.assertEqual(check([{'profile':'Q100','matched_sections':1,'verified_center_count':1}]),'CONDITIONS_MET')
        self.assertEqual(check([{'profile':'Q500','verified_center_count':10}]),'NEED_EVIDENCE')
        self.assertEqual(check([{'profile':'Q100','verified_center_count':0}]),'NEED_EVIDENCE')

    def test_observations_need_matched_event_station_role_datum_and_uncertainty(self):
        rules={'event':'storm','rs':'100','max_residual_ft':.5,'basis':'Project brief'}
        row=dict(role='holdout',kind='stage',issues=[],event='storm',location={'rs':'100.00'},
                 uncertainty_ft=.1,residual_ft=-.5)
        self.assertEqual(self.result(rules,'review',events=[row]),'CONDITIONS_MET')
        self.assertEqual(self.result(rules,'review',events=[dict(row,residual_ft=-.51)]),'REVISE')
        for changes in [dict(role='boundary'),dict(issues=['datum']),dict(uncertainty_ft=None),
                        dict(location={'rs':'200'}),dict(event='other')]:
            self.assertEqual(self.result(rules,'review',events=[dict(row,**changes)]),'NEED_EVIDENCE')

    def test_invert_evidence_and_width_extraction(self):
        ref={'path':'original.csv','sha256':'source'}
        group={'us_invert_ft':1.,'ds_invert_ft':0.}
        g={'vertical_datum':'NAVD88','structure':{'groups':[group]}}
        answers={f'g.structure.groups.0.{field}':{'evidence_class':'reported','candidate_record':dict(
            value=value,datum='NAVD88',source=ref)} for field,value in group.items()}
        self.assertTrue(geometry_record(g,answers,[ref])['documented'])
        self.assertFalse(geometry_record(g,answers,[])['documented'])
        self.assertFalse(geometry_record(dict(g,vertical_datum='UNKNOWN'),answers,[ref])['documented'])
        answers['g.structure.groups.0.ds_invert_ft']['evidence_class']='assumed'
        self.assertFalse(geometry_record(g,answers,[ref])['documented'])
        key='g.structure.road.width_ft'
        self.assertEqual(text_parameters('Roadway\n26 ft wide, per plan view',{key})[0]['evidence_class'],'assumed')
        self.assertEqual(text_parameters('Roadway\n26 ft long',{key}),[])
