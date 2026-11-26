"""A reported converter crash may leave a partial file next to its input."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ras_workflow import render_worker
from ras_workflow.common import read


class ConverterRetry(unittest.TestCase):
    def test_new_attempt_only_can_supply_the_result(self):
        attempts = [('broken', [], dict(returncode=3221226505,valid_pdf=False)),
                    ('second.pdf', ['second'], dict(returncode=0,valid_pdf=True))]
        with tempfile.TemporaryDirectory() as folder, patch.object(render_worker,'convert_once',side_effect=attempts):
            out = Path(folder)
            self.assertEqual(render_worker.convert_document('exe','doc','sha',out),('second.pdf',['second']))
            self.assertEqual(len(read(out/'conversion.json')['attempts']),2)

    def test_no_manufactured_success_after_two_failures(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(render_worker,'convert_once',return_value=(
                'failed', [], dict(returncode=1,valid_pdf=False))) as convert:
            with self.assertRaisesRegex(RuntimeError,'two isolated attempts'):
                render_worker.convert_document('exe','doc','sha',Path(folder))
            self.assertEqual(convert.call_count,2)
