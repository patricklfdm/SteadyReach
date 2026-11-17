import unittest
from docx import Document
from ras_workflow.revision_report import compose


class RevisionReportTests(unittest.TestCase):
    def test_missing_snapshot_does_not_claim_input_hash_verification(self):
        comparison=dict(status='COMPARISON_NOT_ACCEPTANCE',input_context=dict(status='UNAVAILABLE',error='Snapshot changed'),
            profiles=[],diagnostics={k:dict(status='UNAVAILABLE') for k in ('previous','current')})
        for language in ('en','zh'):
            doc=Document();compose(doc,dict(revision_comparison=comparison),lambda en,zh:en if language=='en' else zh,True)
            text='\n'.join(p.text for p in doc.paragraphs)
            self.assertIn('Snapshot changed',text)
            self.assertNotIn('input snapshots are hash-verified' if language=='en' else '输入快照经过哈希核验',text)

    def test_multiple_changes_and_position_qualification_in_both_languages(self):
        context=dict(status='VERIFIED',interpretation='MULTIPLE_INPUT_CHANGES',
            input_changes=[dict(field='boundary_slopes.downstream',previous=.011647,current=.003377)],
            geometry=dict(previous_count=32,current_count=83,changed_sections=5,moved_centers=2,moved_bank_pairs=3,unverified_centers=0))
        comparison=dict(status='COMPARISON_NOT_ACCEPTANCE',input_context=context,
            profiles=[dict(profile='Q100',maximum_at_verified_centers=dict(change=.25,station='600'))],
            diagnostics={k:dict(status='VERIFIED',native_messages=22) for k in ('previous','current')})
        for language in ('en','zh'):
            doc=Document();compose(doc,dict(revision_comparison=comparison),lambda en,zh:en if language=='en' else zh,True)
            text='\n'.join(p.text for p in doc.paragraphs)
            self.assertIn('0.250000',text)
            self.assertIn('not an isolated spacing-convergence test' if language=='en' else '不属于仅改变间距的收敛检验',text)
            self.assertIn('.003377',' '.join(c.text for table in doc.tables for row in table.rows for c in row.cells))


if __name__=='__main__':
    unittest.main()
