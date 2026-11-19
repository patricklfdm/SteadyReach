"""Resume contracts; synthetic test records are not hydraulic evidence."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ras_workflow import study
from ras_workflow.common import ROOT, item, save


class StudyResumeTests(unittest.TestCase):
    def run_case(self, previous, *, evidence_error=False, reports=True, report_error=False, journal=None, folder=None, allow_solver=False):
        if folder is None:
            self.addCleanup(self.temp.cleanup)
            folder = Path(self.temp.name)
        save(folder/'project.draft.json', {'title':'resume test','geometry':'geometry.json'})
        save(folder/'geometry.json', {'fixture': True})
        save(folder/'study.json', {'fixture': True})
        save(folder/'review.json', {'fixture': True})
        save(folder/'state.json', dict(latest_summary={'path':'fresh-summary'},errors=[]))
        case = dict(id='baseline',draft=item(folder/'project.draft.json'), geometry=item(folder/'geometry.json'))
        journal = journal or dict(cases=[copy.deepcopy(previous)])
        latest = dict(manifest={'path':'reports'}) if reports else None
        receipt = dict(reports={'path':'new-reports'})
        with patch.object(study,'verified_case',side_effect=ValueError('native changed') if evidence_error else None,
                 return_value=(folder/'summary.json',{},dict(run_id='unchanged-run'))) as verified, \
             patch('ras_workflow.report_catalog.inspect',return_value=dict(latest=latest,issues=[])), \
             patch.object(study,'recover_case_reports',side_effect=RuntimeError('converter busy') if report_error else None,
                 return_value={'path':'recovery'}) as recover, \
             patch('ras_workflow.cli.execute',return_value=0) as execute:
            original_read=study.read
            with patch.object(study,'read',side_effect=lambda path: receipt if Path(path).name=='recovery' else original_read(path)):
                result=study.run_case(folder/'study.json',dict(project_id='test',case_kind='conditional_site',scenario_id='q100'),
                    folder/'review.json',dict(basis='test confirmation',reviewer=None),case,journal,folder/'execution.json',180)
            if allow_solver:
                execute.assert_called_once_with(str(folder/'project.json'),'q100',timeout=180)
            else:
                execute.assert_not_called()
            return result,journal,verified.call_count,recover.call_count

    def setUp(self):
        (ROOT/'status').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='test_resume_', dir=ROOT/'status')
        self.previous = dict(id='baseline',status='COMPUTED',summary={'path':'summary','sha256':'old'},errors=[],finished_utc='original')

    def test_completed_case_reuses_original_summary_and_reports_without_solver(self):
        result,journal,verified,recovered=self.run_case(self.previous)
        self.assertEqual(result['status'],'COMPUTED')
        self.assertEqual(result['summary'],self.previous['summary'])
        self.assertEqual(result['run_id'],'unchanged-run')
        self.assertTrue(result['reports_reused']);self.assertTrue(result['reused_calculation'])
        self.assertFalse(result['solver_started']);self.assertEqual((verified,recovered),(1,0))
        self.assertEqual(journal['attempt_history'],[self.previous])

    def test_missing_reports_regenerate_without_solver(self):
        result,_,_,recovered=self.run_case(self.previous,reports=False)
        self.assertEqual(result['status'],'COMPUTED')
        self.assertFalse(result['reports_reused']);self.assertEqual(recovered,1)
        self.assertEqual(result['reports'],{'path':'new-reports'})

    def test_failed_report_can_reuse_already_registered_edition_after_interruption(self):
        before=dict(self.previous,status='FAILED',errors=['Report: converter busy'])
        result,_,_,recovered=self.run_case(before)
        self.assertEqual(result['status'],'COMPUTED');self.assertEqual(recovered,0)

    def test_changed_evidence_never_falls_back_to_solver_on_repeat_retry(self):
        folder=Path(self.temp.name);self.addCleanup(self.temp.cleanup)
        failed,journal,_,recovered=self.run_case(self.previous,evidence_error=True,folder=folder)
        self.assertEqual(failed['status'],'FAILED');self.assertEqual(recovered,0)
        self.assertEqual(failed['failure_stage'],'evidence');self.assertTrue(failed['resume_native'])
        again,_,_,_=self.run_case(failed,evidence_error=True,journal=journal,folder=folder)
        self.assertEqual(again['status'],'FAILED');self.assertFalse(again['solver_started'])

    def test_report_retry_failure_retains_native_checkpoint(self):
        result,_,_,_=self.run_case(self.previous,reports=False,report_error=True)
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(result['summary'],self.previous['summary'])
        self.assertEqual(result['failure_stage'],'report')
        self.assertTrue(study.report_retry_candidate(result))

    def test_unfinished_calculation_still_uses_normal_solver_path(self):
        before=dict(self.previous,status='FAILED',summary=None,errors=['Solver: incomplete'])
        result,_,verified,recovered=self.run_case(before,allow_solver=True)
        self.assertEqual(result['status'],'COMPUTED')
        self.assertEqual(result['summary'],{'path':'fresh-summary'})
        self.assertEqual((verified,recovered),(0,0))


if __name__ == '__main__': unittest.main()
