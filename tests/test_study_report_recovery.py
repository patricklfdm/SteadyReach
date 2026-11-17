import unittest
from pathlib import Path
from unittest.mock import patch
from ras_workflow import study


class StudyReportRecoveryTests(unittest.TestCase):
    def test_only_report_failures_are_eligible(self):
        row=dict(status='FAILED',summary={'path':'summary'},errors=['Report: export failed'])
        self.assertTrue(study.report_retry_candidate(row))
        for update in ({'status':'COMPUTED'},{'summary':None},{'errors':[]},{'errors':['Report: x','Solver: x']}):
            self.assertFalse(study.report_retry_candidate(dict(row,**update)))

    def test_changed_inputs_or_configuration_block_recovery(self):
        for changed in ('configuration','inputs','hash'):
            config={'title':'test'};deps=[{'path':'input'}]
            summary=dict(configuration={} if changed=='configuration' else config,errors=[])
            manifest=dict(source_inputs=[] if changed=='inputs' else deps,input_snapshots=[],outputs=[])
            with patch('ras_workflow.qa_review.load_summary',return_value=(Path('summary.json'),summary,dict(raw_hdf={'path':'solver/project/p.hdf'},run_id='original'))), \
                 patch.object(study,'intact',return_value=changed!='hash'),patch.object(study,'read',return_value=manifest), \
                 patch.object(study,'dependencies',return_value=deps),patch('ras_workflow.report.generate') as generate:
                with self.assertRaises(ValueError):study.recover_case_reports({'summary':{'path':'summary'}},Path('project.json'),config)
                generate.assert_not_called()

    def test_recovery_retains_native_identity_and_failed_record(self):
        config={'title':'test'};record=dict(status='FAILED',summary={'path':'summary'},errors=['Report: optional source'])
        manifest=dict(source_inputs=[{'path':'input'}],input_snapshots=[],outputs=[])
        with patch('ras_workflow.qa_review.load_summary',return_value=(Path('summary.json'),dict(configuration=config,errors=[]),dict(raw_hdf={'path':'solver/project/p.hdf'},run_id='original'))), \
             patch.object(study,'intact',return_value=True),patch.object(study,'read',return_value=manifest), \
             patch.object(study,'dependencies',return_value=manifest['source_inputs']),patch('ras_workflow.report.generate',return_value={}) as generate, \
             patch.object(study,'save') as save,patch.object(study,'item',return_value={'path':'receipt'}):
            study.recover_case_reports(record,Path('project.json'),config)
            receipt=save.call_args.args[1]
            self.assertEqual(receipt['run_id'],'original');self.assertFalse(receipt['solver_started'])
            self.assertEqual(receipt['prior_failure'],record);self.assertEqual(record['status'],'FAILED')
            generate.assert_called_once()


if __name__=='__main__':unittest.main()
