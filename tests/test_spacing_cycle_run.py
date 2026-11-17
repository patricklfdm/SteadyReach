"""Orchestration failure/restart tests, with synthetic calculation checkpoints."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ras_workflow import spacing_cycle as cycle
from ras_workflow.common import ROOT, item, read, save


class SpacingCycleRunTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='test_spacing_cycle_',dir=ROOT/'status')
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.sp=self.folder/'study.json';self.rp=self.folder/'review.json'
        self.plan=dict(coverage_policy=dict(maximum_rounds=2,maximum_width_ft=2000))
        self.review={'confirmed':True};save(self.sp,self.plan);save(self.rp,self.review)
        self.calls=[]

    def child(self,sp,plan,rp,prior,proposal,number):
        folder=self.folder/'rounds'/str(number)/'prepared'
        save(folder/'study.json',plan);save(folder/'review.json',self.review)
        return folder/'study.json',plan,folder/'review.json',self.review

    def computation(self,sp,plan,rp,review,timeout,wet=True,failed=False):
        number=0 if sp==self.sp else int(sp.parent.parent.name)
        self.calls.append(number)
        records=[dict(id=name,status='FAILED' if failed and name=='refinement_2' else 'COMPUTED',wet_sections=[350] if wet and name!='baseline' else [])
                 for name in ('baseline','refinement_1','refinement_2')]
        execution=sp.parent/'execution.json';save(execution,dict(study=item(sp),review=item(rp),cases=records))
        return dict(study=item(sp),review=item(rp),execution=item(execution),cases=records,
                    status='INCOMPLETE' if failed else 'NOT_CONVERGED',failed_cases=['refinement_2'] if failed else [])

    def run_with(self,compute,finish=None):
        proposal=dict(changes=[dict(rs=350)])
        with patch('ras_workflow.study.run_fixed',side_effect=compute), \
             patch.object(cycle,'child_study',side_effect=self.child), \
             patch.object(cycle,'next_proposal',return_value=(proposal,{})):
            if finish:
                with patch.object(cycle,'finish',side_effect=finish):
                    return cycle.run(self.sp,self.plan,self.rp,self.review,180)
            return cycle.run(self.sp,self.plan,self.rp,self.review,180)

    def test_round_limit_and_completed_resume_do_not_run_extra_cases(self):
        result=self.run_with(self.computation)
        self.assertEqual(self.calls,[0,1,2])
        self.assertEqual(result['coverage_batch']['status'],'ROUND_LIMIT_REVIEW_REQUIRED')
        with patch('ras_workflow.study.run_fixed') as run,patch.object(cycle,'verify',return_value=[]) as verify:
            self.assertEqual(cycle.run(self.sp,self.plan,self.rp,self.review,180),result)
            run.assert_not_called();verify.assert_called_once()

    def test_interrupted_child_resumes_without_repeating_finished_round(self):
        def crash(*args):
            if args[0]!=self.sp:raise RuntimeError('simulated interruption')
            return self.computation(*args)
        with self.assertRaisesRegex(RuntimeError,'interruption'):self.run_with(crash)
        result=self.run_with(lambda *args:self.computation(*args,wet=False))
        self.assertEqual(self.calls,[0,1])
        self.assertEqual(result['coverage_batch']['status'],'COVERAGE_RESOLVED_REVIEW_REQUIRED')

    def test_interruption_after_checkpoint_obeys_stop_before_more_calculation(self):
        with self.assertRaisesRegex(RuntimeError,'finish interrupted'):
            self.run_with(lambda *args:self.computation(*args,wet=False),lambda *args:(_ for _ in ()).throw(RuntimeError('finish interrupted')))
        result=self.run_with(self.computation)
        self.assertEqual(self.calls,[0])
        self.assertEqual(result['coverage_batch']['status'],'COVERAGE_RESOLVED_REVIEW_REQUIRED')

    def test_failed_round_retains_its_snapshot_and_retries_same_number(self):
        first=self.run_with(lambda *args:self.computation(*args,failed=True))
        self.assertEqual(first['coverage_batch']['status'],'INCOMPLETE')
        old=read(self.folder/'cycle.json')['final_analysis'];old_bytes=(ROOT/old['path']).read_bytes()
        second=self.run_with(lambda *args:self.computation(*args,wet=False))
        self.assertEqual(self.calls,[0,0])
        self.assertEqual(second['coverage_batch']['status'],'COVERAGE_RESOLVED_REVIEW_REQUIRED')
        self.assertEqual((ROOT/old['path']).read_bytes(),old_bytes)
        journal=read(self.folder/'cycle.json')
        self.assertEqual(len(journal['attempts']),2)
        self.assertNotEqual(journal['attempts'][0]['analysis'],journal['attempts'][1]['analysis'])


if __name__=='__main__':unittest.main()
