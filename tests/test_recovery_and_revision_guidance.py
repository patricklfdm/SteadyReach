import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ras_workflow import app_core, calculation_recovery, revision_review, source_extract
from ras_workflow.common import ROOT, item, rel, save


class EditionRecovery(unittest.TestCase):
    def test_repeated_confirmed_resume_returns_same_task(self):
        model = dict(task='projects/site/tasks/resumed/task.json', revision=7, status='PROCESSING')
        original = 'projects/site/tasks/interrupted/task.json'
        body = dict(mode='RESUME_COMPUTATION', confirmed=True, task=original, revision=7)
        for status in ('RUNNING', 'FINISHED'):
            job = dict(action='resume-run', resume_of=original, status=status)
            with self.subTest(status=status), patch.object(app_core, 'model', return_value=model), \
                    patch.object(calculation_recovery, 'read', return_value=job), \
                    patch.object(app_core, 'task_alive', return_value=True), patch.object(app_core, 'launch') as launch:
                result = calculation_recovery.request('site', body)
                self.assertEqual(result['task'], model['task'])
                self.assertTrue(result['reused_request'])
                launch.assert_not_called()

    def test_recovery_checks_original_confirmed_bytes_and_edition(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as temp, patch.object(app_core,'BASE',Path(temp)):
            root=Path(temp)
            config=root/'site'/'approved'/'project.json'
            confirmation=config.parent/'confirmation.json'
            save(confirmation,{'revision':3})
            save(config,{'project_id':'site'})
            model=dict(id='site',revision=3,scenario='q100',run_scenario='q100',active_project=rel(config),run_confirmation=item(confirmation))
            model['compiled_checkpoint']=calculation_recovery.seal(model,config)
            self.assertEqual(calculation_recovery.inspect(model)['mode'],'RESUME_COMPUTATION')
            self.assertEqual(calculation_recovery.inspect(dict(model,revision=4))['mode'],'RESTORE_EVIDENCE')
            save(config,{'project_id':'site','edited':True})
            self.assertEqual(calculation_recovery.inspect(model)['mode'],'RESTORE_EVIDENCE')

    def test_warning_drop_and_missing_export(self):
        old=dict(status='VERIFIED',wet_ends=[],severity={'WARNING':5,'ERROR':0},counts={})
        new=dict(status='VERIFIED',wet_ends=[{}],severity={'WARNING':2,'ERROR':0},counts={'ENERGY_BALANCE_ERROR':1})
        result=revision_review.interpret(dict(previous=old,current=new),[],True,.1)
        self.assertEqual(result['warning_delta'],-3)
        self.assertEqual(result['flags'][0],'FEWER_WARNINGS_OTHER_CHANGES')
        for has_evidence,match in [(False,True),(True,False)]:
            current=new if has_evidence else dict(new,severity=None)
            result=revision_review.interpret(dict(previous=old,current=current),[],match,.1)
            self.assertIsNone(result['warning_delta'])
            self.assertIn('CHECK_WARNING_COVERAGE',result['flags'])

    def test_returned_worksheet_preserves_assumed_zero_and_rejects_unknown_origin(self):
        fields={'fill':dict(kind='number',unit='ft')}
        def parse(label):
            return source_extract.parameter_rows([dict(field='fill',value='0',unit='ft',evidence_class=label)],fields)
        values,errors=parse(' Assumed ')
        self.assertEqual((values[0]['value'],values[0]['evidence_class'],errors),(0,'assumed',[]))
        values,errors=parse('guess')
        self.assertFalse(values)
        self.assertIn('evidence_class',errors[0]['error'])

    def test_structured_extraction_warning_does_not_break_cache(self):
        record=dict(status='INSPECTED',extractor_version=source_extract.EXTRACTOR_VERSION,warnings=[{'row':3,'error':'Unit mismatch'}])
        self.assertTrue(source_extract.reuse_document(record,False,{}))
