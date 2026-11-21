import json
from unittest import TestCase
from ras_workflow.usgs_water import pages, query


class WaterPagesTests(TestCase):
    url = query('monitoring-locations', limit=2)

    def test_follows_relative_link_and_keeps_raw_pages(self):
        second = self.url.split('?')[0] + '?offset=2'
        data = {self.url: b'{"features":[],"links":[{"rel":"next","href":"?offset=2"}]}',
                second: b'{"features":[]}'}
        self.assertEqual([(u, raw) for u, raw, _ in pages(self.url, data.__getitem__)], list(data.items()))

    def test_invalid_or_cyclic_next_is_rejected_before_second_request(self):
        for target in [self.url, 'https://example.org/x', '/ogcapi/v1/collections/peaks/items']:
            calls = []
            def fetch(url):
                calls.append(url)
                return json.dumps({'features': [], 'links': [{'rel': 'next', 'href': target}]}).encode()
            with self.subTest(target=target), self.assertRaises(ValueError):
                list(pages(self.url, fetch))
            self.assertEqual(calls, [self.url])

    def test_bad_response_is_not_an_empty_result(self):
        with self.assertRaises(ValueError):
            list(pages(self.url, lambda _: b'{"error":"service unavailable"}'))
