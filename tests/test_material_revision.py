"""Supplement changes must be explicit, current and confined to the editable child."""
import copy
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from ras_workflow import app_material_revision as material


class MaterialRevisionTests(unittest.TestCase):
    def setUp(self):
        self.model=dict(id='child', revision=2, attachments=[dict(sha256='memo')], parent_revision=dict(
            project_id='base',summary=dict(sha256='base-hdf'),inherited_sources=['old']))
        self.choice=dict(candidate='memo-width',value=26.,source=dict(sha256='memo'),basis='Nominal width.',
                         evidence_class='assumed')
        self.width=dict(key=material.WIDTH,value=25.,evidence_class='assumed',parameter_candidates=[self.choice])
        self.saved={}
        self.rows_old=[self.width]
        self.rows_new=[self.width]
        for suffix in material.DEPENDENTS:
            key=material.ROAD+suffix
            old=dict(value=1,basis='DEM based',evidence_class='assumed',candidate='old',automation_context='before')
            self.saved[key]=material.answer(old)
            row=dict(key=key,missing=False,value=1,label=dict(en=suffix,zh=suffix),answer=self.saved[key])
            self.rows_old.append(row)
            self.rows_new.append(dict(row,parameter_candidates=[dict(old,value=2,candidate='new',automation_context='after')]))
        self.binding={'terrain':'original hash'}
        stack=self.enterContext(ExitStack())
        def mocked(obj,name,**kwargs):
            return stack.enter_context(patch.object(obj,name,**kwargs))
        mocked(material.core,'model',return_value=self.model)
        mocked(material.core,'require_idle')
        mocked(material,'intact',return_value=True)
        mocked(material.params,'objects',side_effect=lambda m:('session',{},dict(answers=copy.deepcopy(self.saved)),{},'before'))
        mocked(material.params,'binding',side_effect=lambda m:self.binding)
        mocked(material.intake,'_objects',return_value=({},'after'))
        mocked(material.params,'rows',side_effect=lambda m,ctx:self.rows_old if ctx[-1]=='before' else self.rows_new)
        mocked(material,'dependency',side_effect=lambda m,g,key:g)
        self.save=mocked(material.intake,'save_draft')
        self.persist=mocked(material.core,'persist')
        self.body=dict(revision=2,candidate='memo-width')

    def preview(self):
        return material.perform('child',self.body)

    def test_preview_then_single_save_preserves_evidence(self):
        proposal=self.preview()
        self.save.assert_not_called()
        self.assertTrue(proposal['ready'])
        self.assertEqual(len(proposal['changes']),6)
        result=material.perform('child',dict(self.body,confirmed=True,token=proposal['token']),True)
        self.assertEqual(len(result['changed']),7)
        answers=self.save.call_args.args[1]['answers']
        self.assertEqual(answers[material.WIDTH]['evidence_class'],'assumed')
        self.assertEqual(answers[material.WIDTH]['candidate_record']['source'],{'sha256':'memo'})
        self.save.assert_called_once()
        self.persist.assert_called_once()

    def test_independent_value_or_competing_candidate_requires_individual_review(self):
        self.rows_old[1]['answer']={'value':1,'basis':'Survey','evidence_class':'reported'}
        self.rows_new[2]['parameter_candidates'].append(dict(self.rows_new[2]['parameter_candidates'][0],value=3))
        p=self.preview()
        self.assertFalse(p['ready'])
        self.assertEqual([r['automatic'] for r in p['changes'][:2]],[False,False])
        with self.assertRaises(ValueError):
            material.perform('child',dict(self.body,confirmed=True,token=p['token']),True)
        self.save.assert_not_called()

    def test_changed_input_or_unconfirmed_preview_cannot_save(self):
        p=self.preview()
        for confirmed in (False, True):
            if confirmed:self.binding['terrain']='changed'
            with self.assertRaises(ValueError):
                material.perform('child',dict(self.body,confirmed=confirmed,token=p['token']),True)
        self.save.assert_not_called()

    def test_excludes_inherited_sources_and_completed_projects(self):
        self.model['parent_revision']['inherited_sources'].append('memo')
        with self.assertRaisesRegex(ValueError,'new source'):self.preview()
        self.model['active_project']='compiled'
        with self.assertRaisesRegex(ValueError,'editable revision'):self.preview()
        self.save.assert_not_called()
