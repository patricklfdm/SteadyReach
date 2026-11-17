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

    def run_refresh(self, action, delivery_error=None):
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
                        return_value={'status': 'READY_FOR_REVIEW'}) as delivery):
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

    def test_report_only_preserves_package_as_previous_edition(self):
        report, delivery, _ = self.run_refresh('report')
        self.assertEqual((report, delivery), (1, 0))
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


if __name__ == '__main__':
    unittest.main()
