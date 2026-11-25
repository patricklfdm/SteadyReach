import csv
import io
import unittest

from ras_workflow.app_check_batch import in_scope, question_result
from ras_workflow.field_return import apply_to_draft, changes, COLUMNS, targets, worksheet


class FieldReturns(unittest.TestCase):
    def setUp(self):
        self.g=dict(vertical_datum='NAVD88',structure=dict(groups=[dict(us_invert_ft=12,ds_invert_ft=11)],
                    road=dict(station_ft=[0,3],elevation_ft=[15,15])))
        self.fields=targets(self.g,{})
        self.rows=list(csv.DictReader(io.StringIO(worksheet(dict(summary=dict(sha256='original')),self.g,self.fields))))

    def preview(self,document=False):
        out=io.StringIO();writer=csv.DictWriter(out,fieldnames=COLUMNS);writer.writeheader();writer.writerows(self.rows)
        return changes(out.getvalue(),self.fields,self.g,'original',document)

    def test_partial_worksheet_and_classification(self):
        self.rows[0].update(value='11.9',source='Trial',evidence_class='assumed')
        rows=self.preview()
        self.assertEqual([(r['before'],r['after']) for r in rows],[(12,11.9)])
        draft=dict(answers={'g.structure.groups.0.ds_invert_ft':dict(value=11)})
        apply_to_draft({},draft,dict(mode='geometry',sources=[dict(path='test')],rows=rows))
        self.assertFalse(draft['answers'][rows[0]['key']]['confirmed'])
        self.assertEqual(draft['answers'][rows[0]['key']]['evidence_class'],'assumed')
        self.assertEqual(draft['answers']['g.structure.groups.0.ds_invert_ft'],dict(value=11))

    def test_evidence_datum_stale_and_profile_order(self):
        r=self.rows[-1]
        r.update(value='[15,16]',source='Survey record')
        with self.assertRaises(ValueError):self.preview()
        self.assertEqual(self.preview(True)[0]['after'],[15,16])
        for field,bad in [('datum','NGVD29'),('unit','m'),('request_summary','prior'),('station_axis_ft','[3,0]'),
                          ('value','[16]'),('value','[false,2]'),('prior','[15,16]')]:
            with self.subTest(field=field):
                old=r[field];r[field]=bad
                with self.assertRaises(ValueError):self.preview(True)
                r[field]=old

    def test_boundary_profile_order_and_bed_axis(self):
        g=dict(model_type='river',flow_regime='subcritical',cross_sections=[dict(rs=50,elevation_ft=[9,8],station_ft=[0,2])],
               boundaries=dict(downstream=dict(type='normal_depth')))
        fields=targets(g,dict(profiles=[dict(id='A'),dict(id='B')]))
        self.assertEqual(fields['g.cross_sections.0.elevation_ft']['axis'],[0,2])
        self.assertEqual(fields['g.boundaries.downstream.stages_ft']['count'],2)


class ReturnedEvents(unittest.TestCase):
    def test_partial_observations_and_versioned_correction(self):
        from ras_workflow.survey_events import merge_holdouts
        row=dict(profile='A',event='visit',date='2015-10-01',location=dict(rs='500'),role='holdout',observed_ft=50)
        other=dict(row,location=dict(rs='400'))
        corrected=dict(row,observed_ft=51)
        self.assertEqual(merge_holdouts([row],[other,corrected]),[corrected,other])
        self.assertEqual(row['observed_ft'],50)
        for original,incoming in [([row],[dict(row,event='other')]),([dict(row,role='boundary')],[corrected]),
                                   ([],[row,corrected])]:
            with self.assertRaises(ValueError):merge_holdouts(original,incoming)


class BoundedQuestion(unittest.TestCase):
    def test_other_studies_do_not_clear_a_boundary_question(self):
        self.assertFalse(in_scope('scenario.channel_n','boundary'))
        ref=dict(sha256='fresh');path='boundary_slopes.downstream'
        study=dict(analysis=ref,cases=[dict(id='high',changes=[dict(path=path,after=.01)])],
                   comparisons=[dict(case='high',cross_section_differences=[dict(profile='Q',station='100',delta_wse_ft=.20)])])
        plan=dict(options=dict(question='boundary',threshold_ft=.15,threshold_basis='project protocol'),
                  steps=[dict(id='sensitivity')])
        def verdict(ref):
            return question_result(plan,dict(sensitivity=dict(status='COMPLETED',analysis=ref)),[study])['status']
        self.assertEqual(verdict(dict(sha256='other')),'INSUFFICIENT_EVIDENCE')
        self.assertEqual(verdict(ref),'FIELD_REVIEW_BEFORE_ANOTHER_BATCH')
        plan['options']['threshold_ft']=.20
        self.assertEqual(verdict(ref),'STOP_WITHIN_TESTED_RANGE')
        plan['deferred_parameters']=[dict(path=path)]
        self.assertEqual(verdict(ref),'INSUFFICIENT_EVIDENCE')
