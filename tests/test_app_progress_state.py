"""The live worker governs progress even when an internal substep says ready."""
import unittest
from unittest.mock import Mock, patch
from ras_workflow import app_core as core


class AppProgressStateTests(unittest.TestCase):
    def test_running_worker_keeps_polling_without_reading_mutating_draft(self):
        model=dict(id='isolated',status='INPUTS_READY',phase='Preparing DEM geometry',
                   task='task.json',session='session.json')
        with patch.object(core,'model',return_value=model), \
             patch.object(core,'deletion_record',return_value=Mock(exists=lambda:False)), \
             patch.object(core,'read',return_value=dict(status='RUNNING',action='automatic-prepare',pid=123)), \
             patch('ras_workflow.project_actions.process_alive',return_value=True), \
             patch('ras_workflow.intake.view',side_effect=AssertionError('Must not inspect mutable draft')), \
             patch.object(core,'native_preview',side_effect=AssertionError('Not needed while processing')):
            detailed=core.view('isolated')
            brief=core.view('isolated',detail=False)
        self.assertEqual(detailed['status'],'PROCESSING')
        self.assertEqual(brief['status'],'PROCESSING')
        self.assertEqual(detailed['phase'],'Preparing DEM geometry')
        self.assertEqual(model['status'],'INPUTS_READY')

    def test_dead_worker_is_interrupted_instead_of_processing_forever(self):
        with patch.object(core,'model',return_value=dict(id='isolated',status='PROCESSING',task='task.json')), \
             patch.object(core,'read',return_value=dict(status='RUNNING',pid=123)), \
             patch('ras_workflow.project_actions.process_alive',return_value=False):
            state=core.view('isolated',detail=False)
        self.assertEqual(state['status'],'INTERRUPTED')
        self.assertTrue(state['errors'])


if __name__=='__main__':
    unittest.main()
