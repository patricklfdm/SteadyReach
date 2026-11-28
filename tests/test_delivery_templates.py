import unittest
from ras_workflow.feasibility import scope
from ras_workflow.delivery_templates import validate, crossing_records
from ras_workflow.edition_brief import build
from ras_workflow.purpose_acceptance import evaluate


class DeliveryTemplates(unittest.TestCase):
    def summary(self, key, purpose):
        intent=scope(dict(delivery_template=key,purpose=purpose,flow_paths='single'))
        model='river' if key=='between_bridges_v1' else 'culvert'
        profile=dict(profile_id='Q100',flow_cfs=100,qa=dict(wet_edges=[]),metrics={})
        return dict(configuration=dict(production_scope=intent),hydraulics=dict(model_type=model,run_id='test',profiles=[profile]))

    def test_explicit_scope_legacy_and_kind(self):
        self.assertNotIn('criteria',scope({}))
        with self.assertRaises(ValueError):validate('single_culvert_v1','river')
        with self.assertRaises(ValueError):scope({'delivery_template':'unknown'})
        for key in ['single_culvert_v1','between_bridges_v1']:
            for purpose in ['screening','comparison','review']:
                s=self.summary(key,purpose);d=evaluate(s);brief=build(s,d,[])
                self.assertTrue(s['configuration']['production_scope']['criteria']['dry_ends'])
                self.assertTrue(any(r['heading']['en']=='Agreed delivery scope' for r in brief['rows']))
                self.assertEqual(d['state'],'CONDITIONS_MET' if purpose=='screening' else 'NEED_EVIDENCE')
        river=evaluate(self.summary('between_bridges_v1','review'))
        self.assertTrue({'observations','sensitivity','field-feedback'}.issubset({r['action']['tool'] for r in river['rows'] if 'action' in r}))

    def test_missing_native_value_and_measurement(self):
        s=self.summary('single_culvert_v1','review')
        s['configuration']['acceptance_geometry']=dict(documented=True,crossing=dict(documented=True))
        self.assertEqual(evaluate(s)['state'],'NEED_EVIDENCE')
        s['hydraulics']['profiles'][0]['metrics']['roadway_flow_software_cfs']=0
        self.assertEqual(evaluate(s)['state'],'CONDITIONS_MET')
        proof=crossing_records({'structure':{'groups':[{}],'road':{'profile_mode':'distinct'}}},{},[])
        self.assertFalse(proof['documented'])
        self.assertIn('g.structure.road.downstream_elevation_ft',proof['missing'])
