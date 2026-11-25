from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ras_workflow.common import ROOT, item, rel, save
from ras_workflow.return_scope import assess


class ReturnScope(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name)
        def store(name,data):
            path=base/name;save(path,data);return item(path)
        self.original=store('source.json',{'survey':'test'})
        self.key='g.structure.groups.0.us_invert_ft'
        self.fields=[dict(key=self.key,value=10.0,answer={'candidate_record':{'source':self.original}}),
                     dict(key='g.structure.groups.0.ds_invert_ft',value=9.0)]
        self.packet=dict(fields=self.fields,inputs={'project_id':'parent','sources':[self.original]},fingerprint='frozen')
        self.review=store('parent/parameters.json',self.packet)
        self.confirmation=store('parent/confirmation.json',{'review':self.review,'reviewed_fingerprint':'frozen'})
        summary=store('parent/summary.json',{'run':'parent-run'})
        self.model=dict(project=rel(base/'draft/project.json'),parent_revision={'project_id':'parent','summary':summary},
                        intake_return=dict(confirmation=self.confirmation,review=self.review,summary=summary,
                           parent_project=rel(base/'parent/project.json'),fields=[],sources=[],mode='observation'))
        self.store=store

    def test_returned_field_keeps_siblings_and_revalidates_source_metadata(self):
        data=assess(self.model,self.fields)
        self.assertEqual(data['affected'],[]);self.assertEqual(len(data['retained']),2)
        self.model['intake_return']['fields']=[self.key]
        self.assertEqual(assess(self.model,self.fields)['affected'],[{'key':self.key,'reason':'RETURNED'}])
        self.model['intake_return']['fields']=[]
        note=self.store('note.json',{'unit':'ft'})
        self.model['intake_source_notes']=[dict(note,role='source_metadata_note',source_key=['structure',self.original['sha256']])]
        self.assertEqual(assess(self.model,self.fields)['affected'],[{'key':self.key,'reason':'SOURCE_METADATA_CHANGED'}])

    def test_other_edition_or_damaged_confirmation_requires_full_review(self):
        self.model['parent_revision']['project_id']='other'
        self.assertEqual(assess(self.model,self.fields)['mode'],'FULL_REVIEW')
        self.model['parent_revision']['project_id']='parent'
        (ROOT/self.confirmation['path']).write_bytes(b'{}')
        self.assertEqual(assess(self.model,self.fields)['mode'],'FULL_REVIEW')
