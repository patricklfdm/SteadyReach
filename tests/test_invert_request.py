import csv
import io
from unittest import TestCase
from unittest.mock import patch

from ras_workflow import invert_request


class InvertRequest(TestCase):
    def setUp(self):
        groups=[dict(name=name,count=1,shape='box',span_ft=8,rise_ft=6,centers_ft=[offset],
                     us_invert_ft=10,ds_invert_ft=9) for name,offset in [('A',1),('B',12)]]
        self.geometry=dict(vertical_datum='NAVD88',structure=dict(groups=groups))
        self.child=dict(parent_revision=dict(summary=dict(sha256='edition')))
        frozen=dict(summary=dict(sha256='edition'))
        summary=dict(hydraulics=dict(run_id='q100'))
        with patch('ras_workflow.result_guidance.load_evidence',return_value=(frozen,None,summary,None,None,None)), \
             patch.object(invert_request,'bound_inputs',return_value=({},self.geometry,[])):
            worksheet=invert_request.issue('site',{})
        self.rows=list(csv.DictReader(io.StringIO(worksheet['csv'])))

    def test_rows_separate_prior_estimate_from_answer_and_bind_both_ends(self):
        self.assertEqual([(r['opening_group'],r['end']) for r in self.rows],
                         [('1','inlet'),('1','outlet'),('2','inlet'),('2','outlet')])
        for row in self.rows:
            self.assertEqual(row['value'],'')
            self.assertNotEqual(row['prior_ft'],'')
            invert_request.match(dict(row,value='9',source='Trial estimate',evidence_class='assumed'),
                                 self.child,self.geometry)
        invert_request.match(dict(field='legacy',value='2'),{},{})

    def test_wrong_edition_group_end_unit_datum_or_missing_basis_stays_unmatched(self):
        first=dict(self.rows[0],source='Survey log')
        for change in [dict(request_summary='other'),dict(opening_group='0'),dict(opening_group='2'),
                       dict(opening_group='99'),dict(end='outlet'),dict(field=self.rows[2]['field']),
                       dict(unit='m'),dict(datum='LOCAL'),dict(source=' '),dict(evidence_class='')]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                invert_request.match(dict(first,**change),self.child,self.geometry)
        self.geometry['structure']['groups'][0]['centers_ft']=[7]
        with self.assertRaisesRegex(ValueError,'group has changed'):
            invert_request.match(first,self.child,self.geometry)
