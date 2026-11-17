"""Transient imagery failures retry without masking validation or access errors."""
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from ras_workflow.imagery import fetch_imagery


class ImageryRetry(unittest.TestCase):
    def run_case(self, outcomes):
        failures = []
        with patch('ras_workflow.imagery.fetch', side_effect=outcomes) as fetch, \
             patch('ras_workflow.imagery.time.sleep') as sleep:
            try:
                result = fetch_imagery('https://example.test/imagery', Path('image.png'), 1234, failures)
            except (HTTPError, ValueError) as error:
                result = error
        return result, failures, fetch, sleep

    def error(self, code):
        return HTTPError('https://example.test/imagery', code, 'test', {}, None)

    def test_gateway_then_success_retains_attempt_and_budget(self):
        result, failures, fetch, sleep = self.run_case([self.error(502), {'size_bytes': 100}])
        self.assertEqual(result, {'size_bytes': 100})
        self.assertEqual([entry['status_code'] for entry in failures], [502])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args.args[-1], 1234)
        sleep.assert_called_once_with(1)

    def test_repeated_failure_is_bounded_and_reported(self):
        result, failures, fetch, sleep = self.run_case([self.error(503) for _ in range(3)])
        self.assertIsInstance(result, HTTPError)
        self.assertEqual(len(failures), 3)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_access_and_validation_errors_are_immediate(self):
        for error in (self.error(403), ValueError('budget exceeded')):
            result, failures, fetch, sleep = self.run_case([error])
            self.assertIs(result, error)
            self.assertEqual(fetch.call_count, 1)
            sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
