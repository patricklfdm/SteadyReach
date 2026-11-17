"""Portable evidence must retain nested inputs and reject changed source bytes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ras_workflow import common, delivery_evidence


class DeliveryEvidence(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        for module in (common,delivery_evidence):
            p=patch.object(module,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        self.source=self.root/'source';self.source.mkdir()
        self.full=self.root/'Complete';self.full.mkdir()

    def test_nested_sources_are_portable_and_content_deduplicated(self):
        raw=self.source/'Model.f01';raw.write_bytes(b'reviewed native flow cards')
        same=self.source/'copy.f01';same.write_bytes(raw.read_bytes())
        summary=self.source/'summary.json'
        common.save(summary,dict(input=common.item(raw),duplicate=common.item(same)))
        result=delivery_evidence.archive_report_sources(self.full,[common.item(summary)],100000)
        self.assertEqual(len(result['entries']),3)
        destinations=[v['package_path'] for v in result['entries']]
        self.assertEqual(len(set(destinations)),2)
        raw.unlink();same.unlink();summary.unlink()
        for row in result['entries']:
            self.assertEqual(common.sha(self.full/row['package_path']),row['source']['sha256'])

    def test_changed_or_outside_source_is_rejected(self):
        file=self.source/'flow.txt';file.write_text('first');entry=common.item(file)
        file.write_text('changed')
        with self.assertRaisesRegex(ValueError,'dependency changed'):
            delivery_evidence.archive_report_sources(self.full,[entry],10000)
        entry['path']='../outside.txt'
        with self.assertRaisesRegex(ValueError,'leaves workspace'):
            delivery_evidence.archive_report_sources(self.full,[entry],10000)

    def test_budget_stops_additional_copy(self):
        file=self.source/'data.txt';file.write_bytes(b'12345')
        with self.assertRaisesRegex(ValueError,'budget exceeded'):
            delivery_evidence.archive_report_sources(self.full,[common.item(file)],4)
        self.assertFalse((self.full/'Evidence/ReportSources').exists())

    def test_imagery_reuse_preserves_sealed_acquisition_files(self):
        prior=self.root/'Previous';folder=prior/'Evidence/Imagery';folder.mkdir(parents=True)
        file=folder/'catalog.json';common.save(file,dict(source='test fixture'))
        receipt=prior/'Evidence/imagery.json';common.save(receipt,dict(status='READY_FOR_MAP_REVIEW'))
        manifest=prior/'PACKAGE_MANIFEST.json'
        common.save(manifest,dict(files=[dict(path='Evidence/Imagery/catalog.json',
            sha256=common.sha(file),size_bytes=file.stat().st_size)]))
        acquisition=dict(previous_manifest=common.item(manifest),previous_receipt=common.item(receipt))
        self.assertEqual(delivery_evidence.preserve_imagery_records(acquisition,self.full),1)
        self.assertEqual(common.sha(self.full/'Evidence/Imagery/catalog.json'),common.sha(file))
        file.write_text('changed')
        with self.assertRaisesRegex(ValueError,'record changed'):
            delivery_evidence.preserve_imagery_records(acquisition,self.full)


if __name__=='__main__':unittest.main()
