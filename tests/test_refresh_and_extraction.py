"""Regressions for the user-facing refresh and long-document paths."""
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ras_workflow import app_core, source_extract


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.model = dict(id='test', summary={'path': 'summary.json'},
                          latest_delivery=dict(mapped=True, complete={'path': 'old/Complete'}))
        self.saved = []

    def run_refresh(self, action, delivery_error=None, delivery_result=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (patch.object(app_core, 'ROOT', root),
                  patch.object(app_core, 'model', return_value=copy.deepcopy(self.model)),
                  patch.object(app_core, 'folder', return_value=root/'project'),
                  patch.object(app_core, 'rel', side_effect=lambda p: str(p.relative_to(root))),
                  patch.object(app_core, 'intact', return_value=True),
                  patch.object(app_core, 'persist', side_effect=lambda m, *args: self.saved.append(copy.deepcopy(m))),
                  patch('ras_workflow.report.generate') as report,
                  patch('ras_workflow.site_delivery.generate', side_effect=delivery_error,
                        return_value=delivery_result or {'status': 'READY_FOR_REVIEW'}) as delivery):
                if delivery_error:
                    with self.assertRaisesRegex(ValueError, 'mapping'):
                        app_core.regenerate('test', action)
                else:
                    app_core.regenerate('test', action)
                return report.call_count, delivery.call_count, delivery.call_args

    def test_delivery_refreshes_reports_even_without_dirty_flag(self):
        report, delivery, args = self.run_refresh('delivery')
        self.assertEqual((report, delivery), (1, 1))
        self.assertEqual(args.kwargs['reuse_package'], 'old/Complete')
        self.assertFalse(self.saved[-1]['exports_need_refresh'])

    def test_failed_delivery_retains_new_reports_and_previous_package(self):
        self.run_refresh('delivery', ValueError('mapping failed'))
        self.assertIn('latest_reports', self.saved[-1])
        self.assertEqual(self.saved[-1]['previous_delivery'], self.model['latest_delivery'])
        self.assertTrue(self.saved[-1]['exports_need_refresh'])
        self.assertNotIn('latest_delivery', self.saved[-1])
        self.assertTrue(app_core.current_refreshed_reports(self.saved[-1]))

    def test_changed_result_or_study_hides_previous_reports(self):
        self.run_refresh('report')
        current=self.saved[-1]
        self.assertTrue(app_core.current_refreshed_reports(current))
        for key in ('summary','latest_study','latest_spacing','latest_coverage','latest_coverage_exports'):
            changed=copy.deepcopy(current);changed[key]={'path':'new.json','sha256':'changed'}
            self.assertFalse(app_core.current_refreshed_reports(changed),key)
        old=copy.deepcopy(current);old.pop('latest_reports_binding')
        self.assertFalse(app_core.current_refreshed_reports(old))

    def test_report_only_preserves_package_as_previous_edition(self):
        report, delivery, _ = self.run_refresh('report')
        self.assertEqual((report, delivery), (1, 0))
        self.assertTrue(self.saved[-1]['exports_need_refresh'])

    def test_incomplete_delivery_receipt_keeps_actionable_status(self):
        self.run_refresh('delivery',delivery_result={'status':'INCOMPLETE','error':'Map coverage incomplete'})
        self.assertEqual(self.saved[-1]['status'],'RESULTS_READY_MAP_PENDING')
        self.assertEqual(self.saved[-1]['errors'],['Map coverage incomplete'])
        self.assertTrue(self.saved[-1]['exports_need_refresh'])

    def test_unknown_action_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            app_core.regenerate('test', 'unexpected')


class PdfExtractionTests(unittest.TestCase):
    def extract(self, count, text='Hydraulic source text. ' * 8, **limits):
        pages = [SimpleNamespace(extract_text=lambda: text) for _ in range(count)]
        limits.setdefault('PDF_TEXT_LIMIT', source_extract.PDF_TEXT_LIMIT)
        with tempfile.TemporaryDirectory() as temp:
            with patch('pypdf.PdfReader', return_value=SimpleNamespace(pages=pages)):
                with patch.multiple(source_extract, **limits):
                    return source_extract.document_text(Path(temp)/'source.pdf', temp, ocr=False)

    def test_reads_later_pages_of_a_95_page_source(self):
        result = self.extract(95)
        self.assertIn('[Page 78; PDF text]', result['text'])
        self.assertIn('[Page 95; PDF text]', result['text'])
        self.assertEqual(result['coverage']['status'], 'COMPLETE_TEXT_PASS')

    def test_page_limit_is_explicit(self):
        result = self.extract(201)
        self.assertEqual(result['coverage']['inspected_pages'], 200)
        self.assertEqual(result['coverage']['status'], 'PARTIAL')
        self.assertTrue(any('200 of 201' in w for w in result['warnings']))

    def test_short_text_requires_visual_review(self):
        result = self.extract(1, text='Image only')
        self.assertEqual(result['coverage']['status'], 'PARTIAL')

    def test_character_limit_is_reported(self):
        result = self.extract(3, PDF_TEXT_LIMIT=100)
        self.assertEqual(result['coverage']['status'], 'PARTIAL')
        self.assertLessEqual(len(result['text']), 100)
        self.assertTrue(any('character' in w for w in result['warnings']))

    def test_previous_extractor_cache_is_reprocessed(self):
        cached = dict(status='INSPECTED', extractor_version=2, warnings=[])
        self.assertFalse(source_extract.reuse_document(cached, False, {}))


class FirstPageFieldResult(unittest.TestCase):
    def test_cover_uses_eligible_field_residuals_only_in_both_languages(self):
        from docx import Document
        from ras_workflow.report_decision import add
        rows=[dict(date='2019-02-21',role='holdout',kind='stage',issues=[],location={'rs':'500'},
                   residual_ft=-.125,uncertainty_ft=None)]
        rows.extend([dict(rows[0],role='boundary',residual_ft=40),dict(rows[0],issues=['VERTICAL_DATUM_MISMATCH'],residual_ft=20)])
        data=dict(summary=dict(hydraulics={},configuration={}),river_checks={'events':rows})
        for cn in (False,True):
            doc=Document();add(doc,data,cn)
            text=' '.join(p.text for p in doc.paragraphs)
            for expected in ('2019-02-21','RS 500','-0.125 ft','1 笔缺少' if cn else 'without stated vertical uncertainty: 1'):
                self.assertIn(expected,text)
            self.assertNotIn('40.000',text)
            self.assertNotIn('20.000',text)


if __name__ == '__main__':
    unittest.main()
