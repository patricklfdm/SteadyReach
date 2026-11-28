import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
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

    def test_each_crossing_record_has_an_intact_original_and_matching_elevation_datum(self):
        with tempfile.TemporaryDirectory() as tmp, patch('ras_workflow.common.ROOT', Path(tmp)):
            original = Path(tmp) / 'survey.txt'
            original.write_bytes(b'structured test survey')
            ref = dict(path=original.name, size_bytes=original.stat().st_size,
                       sha256=hashlib.sha256(original.read_bytes()).hexdigest())
            group = dict(shape='box', count=3, span_ft=8, rise_ft=6, length_ft=50,
                         us_invert_ft=102, ds_invert_ft=101)
            road = dict(station_ft=[0, 50], elevation_ft=[111, 112])
            geometry = dict(vertical_datum='NAVD88', structure=dict(groups=[group], road=road))
            answers = {}
            for prefix, values in [('g.structure.groups.0.', group), ('g.structure.road.', road)]:
                for field, value in values.items():
                    answers[prefix + field] = dict(evidence_class='as_built',
                        candidate_record=dict(source=ref, value=value, datum='NAVD 1988'))
            self.assertTrue(crossing_records(geometry, answers, [ref])['documented'])
            us, ds = (answers['g.structure.groups.0.' + end]['candidate_record']
                      for end in ('us_invert_ft', 'ds_invert_ft'))
            us['datum'] = 'NGVD29'
            ds['source'] = dict(ref, path='absent.txt')
            proof = crossing_records(geometry, answers, [ref, ds['source']])
            self.assertEqual(set(proof['missing']), {'g.structure.groups.0.us_invert_ft',
                                                      'g.structure.groups.0.ds_invert_ft'})

    def test_missing_native_value_and_measurement(self):
        s=self.summary('single_culvert_v1','review')
        s['configuration']['acceptance_geometry']=dict(documented=True,crossing=dict(documented=True))
        self.assertEqual(evaluate(s)['state'],'NEED_EVIDENCE')
        s['hydraulics']['profiles'][0]['metrics']['roadway_flow_software_cfs']=0
        self.assertEqual(evaluate(s)['state'],'CONDITIONS_MET')
        proof=crossing_records({'structure':{'groups':[{}],'road':{'profile_mode':'distinct'}}},{},[])
        self.assertFalse(proof['documented'])
        self.assertIn('g.structure.road.downstream_elevation_ft',proof['missing'])
