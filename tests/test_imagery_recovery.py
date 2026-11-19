import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from pyproj import CRS

from ras_workflow.common import save, sha
from ras_workflow.imagery import SERVICE
from ras_workflow.imagery_recovery import _live_selection, contains, lookup


class NAIPRecoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.crs = CRS.from_epsg(26913)
        self.bounds = [10., 20., 12., 22.]
        self.rule = {'lockRasterIds': [2, 1], 'mosaicMethod':'esriMosaicLockRaster'}
        self.records = [{'id': 1, 'Year': 2017}, {'id': 2, 'Year': 2019}]
        request = urlencode({'bbox': ','.join(map(str, self.bounds)),
                             'mosaicRule': json.dumps(self.rule),
                             'renderingRule': json.dumps({'rasterFunction':'NaturalColor'})})
        receipts = []
        for name, route, data in (
            ('catalog.json', '/query', {'objectIdFieldName':'id', 'features':[{'attributes':r} for r in self.records]}),
            ('export.json', '/exportImage?'+request, {'test_fixture': True}),
        ):
            file = self.folder/name
            save(file, data)
            receipt = dict(url=SERVICE+route, sha256=sha(file), tls_verification=True)
            save(self.folder/(name+'.request.json'), receipt)
            receipts.append(receipt)
        self.state = dict(status='FAILED',pixel_transfer_failed=True,service=SERVICE,
                          requested_bounds=self.bounds,requested_crs=self.crs.to_wkt(),requests=receipts)
        save(self.folder/'acquisition.json',self.state)

    def test_matching_catalog_uses_exact_lock_order_and_requires_full_containment(self):
        self.assertEqual(_live_selection(self.folder,self.crs,self.bounds),(self.rule,list(reversed(self.records))))
        self.assertTrue(contains([9,20,12,23],self.bounds))
        self.assertFalse(contains([10,20,11.999,22],self.bounds))
        self.assertIsNone(_live_selection(self.folder,self.crs,[9,20,12,22]))

    def test_invalid_transfer_or_changed_catalog_cannot_authorize_cached_image(self):
        save(self.folder/'acquisition.json',dict(self.state,pixel_transfer_failed=False))
        self.assertIsNone(lookup(self.folder,self.crs,self.bounds))
        save(self.folder/'acquisition.json',self.state)
        save(self.folder/'catalog.json',dict(features=[]))
        self.assertIsNone(lookup(self.folder,self.crs,self.bounds))
        (self.folder/'catalog.json.request.json').write_text('{',encoding='utf8')
        self.assertIsNone(lookup(self.folder,self.crs,self.bounds))
