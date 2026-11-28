import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from ras_workflow import hydraulic_triage as triage, operator_log, project_support as support
from ras_workflow.common import save
from ras_workflow.release_metrics import metrics


class EngineeringDecisionTests(unittest.TestCase):
    def test_stable_grid_must_match_the_failing_profile(self):
        field=dict(en='source text',zh='来源',state='exceeded',action=dict(tool='observations'),
                   field_check=dict(profile='Q100',limit_ft=1,rs=200,residual_ft=-1.45))
        decision=dict(rows=[field],state='REVISE',en='review',zh='复核')
        for name,expected in [('Q100',True),('Q500',False)]:
            studies=[dict(convergence=dict(threshold_ft=.1,rows=[dict(profile=name,status='STABLE_AT_REVIEW_THRESHOLD')]))]
            result=triage.recommendation(decision,studies=studies)
            self.assertEqual(result['code'],'CHECK_FIELD_CONTROL')
            self.assertEqual('spacing series' in result['en'],expected)
            self.assertNotIn('source text',result['en'])
            self.assertIn('RS 200',result['zh'])
        regression=dict(en='Different fit',zh='偏差扩大',action=dict(tool='comparison'))
        self.assertEqual(triage.recommendation(decision,comparison={'review':{'field_regression':regression}})['code'],'KEEP_REFERENCE')

    def test_survey_accuracy_and_competing_flow_paths_have_distinct_actions(self):
        row=dict(state='missing',action=dict(tool='observations'),en='Missing accuracy.',zh='缺少精度。')
        decision=dict(rows=[row],state='NEEDS_EVIDENCE',en='Review.',zh='复核。')
        self.assertEqual(triage.recommendation(decision)['code'],'COMPLETE_FIELD_EVIDENCE')
        comparison={'review':dict(flags=['CHECK_WATER_LEVEL_CHANGE'],investigation=[dict(kind='overbank_share',en='Slope',zh='坡降')])}
        self.assertEqual(triage.recommendation(decision,comparison=comparison)['code'],'VERIFY_FLOW_PATH')

    def test_successful_repeat_is_bound_to_the_same_review_identity(self):
        with TemporaryDirectory() as directory:
            folder=Path(directory)
            for token in ['a','a','b']:
                cid=operator_log.confirmation_id('start',dict(review_token=token))
                operator_log.record(folder,'start',{'compute_consents':1},'local_api',confirmation=cid)
            save(folder/'tasks'/'one'/'task.json',dict(action='delivery',started_utc='2020-01-01T01:00:00Z',finished_utc='2020-01-01T01:00:10Z'))
            result=metrics(folder)
            self.assertEqual(result['interaction_receipts']['repeated_confirmations'],1)
            self.assertEqual(result['machine_by_action']['delivery']['completed_seconds'],10)
            self.assertIsNone(result['active_engineer_seconds'])

    def test_support_binds_edition_and_rejects_changed_preview(self):
        model=dict(id='sensitive_project_name',revision=8,errors=['QGIS export exceeded 9 s: secret-drive-path'])
        with patch.object(support.app_core,'model',return_value=model):
            body=dict(page='delivery')
            preview=support.preview(model['id'],body)
            record=support.export(model['id'],dict(**body,token=preview['token']))
            self.assertEqual(record['incident'],'EXPORT_TIMEOUT')
            self.assertNotIn('secret-drive',json.dumps(record))
            self.assertNotIn(model['id'],json.dumps(record))
            model['revision']+=1
            with self.assertRaises(ValueError):support.export(model['id'],dict(**body,token=preview['token']))
