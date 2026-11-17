"""FIS column semantics, discovery failures and explicit applicability selection."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from ras_workflow import source_fema, source_tables, app_autoprepare


def layout_line(cells):
    text = [' '] * 125
    for start, value in cells:
        text[start:start+len(value)] = value
    return ''.join(text).rstrip()


def discharge_table():
    return '\n'.join([
        'Table 9: Summary of Discharges',
        layout_line([(67, 'Peak Discharge (cfs)')]),
        layout_line([(52, '10% Annual'), (72, '1% Annual'), (92, '1% Annual'), (112, '0.2% Annual')]),
        layout_line([(74, 'Chance'), (94, 'Plus')]),
        layout_line([(0, 'Flooding Source'), (28, 'Location')]),
        layout_line([(0, 'North Fork'), (24, 'At Town'), (56, '100'), (76, '250'), (96, '999'), (116, '800')]),
        layout_line([(0, 'Example River'), (24, 'Boundary')]),
        '',
        layout_line([(0, 'Other River'), (24, 'At Lake'), (56, '200'), (77, '*'), (96, '400'), (116, '500')]),
        layout_line([(24, 'Outlet')]),
    ])


def catalog_page(records):
    # The real page also has a commented historical script. It must be ignored.
    return '//var data = {"FIS_REPORT": []};\nvar data = '+json.dumps({'FIS_REPORT': records})+';'


def record(**values):
    result = dict(product_NAME='12345CV000A', product_SUPERSEDED='F', product_EFFECTIVE_FLAG='0',
                  product_TYPE_ID='FINAL_PRODUCT', product_SUBTYPE_ID='FIS_REPORT',
                  product_EFFECTIVE_DATE_STRING='01/01/2020', ref_COMMUN_NAME='Example County')
    result.update(values)
    return result


class TableTests(unittest.TestCase):
    def test_ordinary_q100_and_wrapped_labels(self):
        table = source_tables.parse(discharge_table(), 30)[0]
        self.assertEqual(table['warnings'], [])
        self.assertEqual(len(table['rows']), 1)
        row = table['rows'][0]
        self.assertEqual((row['stream'], row['location']), ('North Fork Example River', 'At Town Boundary'))
        self.assertEqual(row['flow_cfs'], 250)
        candidate = source_tables.candidates([table], 2, 1)[0]
        self.assertEqual(candidate['field'], 'c.scenarios.2.profiles.1.flow_cfs')
        self.assertEqual(candidate['source_locus']['pdf_page'], 30)
        self.assertTrue(candidate['requires_applicability_review'])

    def test_missing_q100_profile_and_metric_units(self):
        tables = source_tables.parse(discharge_table(), 1)
        self.assertEqual(source_tables.candidates(tables, profile_index=None), [])
        table = source_tables.parse(discharge_table().replace('(cfs)', '(m3/s)'), 1)[0]
        self.assertEqual(table['rows'], [])
        self.assertTrue(table['warnings'])

    def test_adjacent_missing_columns_and_footnote(self):
        layout = discharge_table()+'\n'+layout_line([
            (0, 'Third River'), (24, 'At Road'), (57, '*'), (76, '350'), (97, '*'), (117, '*')])
        layout += '\n*Data not Available'
        rows = source_tables.parse(layout, 31)[0]['rows']
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['stream'], 'Third River')
        self.assertEqual(rows[1]['location'], 'At Road')
        self.assertEqual(rows[1]['flow_cfs'], 350)

    def test_ambiguous_ordinary_column_is_reported(self):
        table = source_tables.parse(discharge_table().replace('Plus', 'Base'), 1)[0]
        self.assertEqual(table['rows'], [])
        self.assertTrue(table['warnings'])

    def test_roughness_midpoints_are_assumptions(self):
        table = source_tables.parse('Table 13: Roughness Coefficients\nStream  Channel  Overbank\nExample River  0.040 - 0.050  0.10\n', 38)[0]
        choices = source_tables.candidates([table])
        self.assertEqual([c['value'] for c in choices], [.045, .1])
        self.assertEqual([c['evidence_class'] for c in choices], ['assumed', 'reported'])
        self.assertEqual(choices[0]['range'], [.04, .05])

    def test_automatic_preparation_retains_location_choice(self):
        choice = source_tables.candidates(source_tables.parse(discharge_table(), 30))[0]
        choice['source'] = {'path': 'source.pdf'}
        field = dict(key=choice['field'], parameter_candidates=[choice])
        self.assertIsNone(app_autoprepare.select_candidate(field, {}, True))


class CatalogTests(unittest.TestCase):
    def test_current_report_filter(self):
        reports = source_fema.effective_reports(catalog_page([
            record(), record(product_NAME='old', product_SUPERSEDED='T'),
            record(product_NAME='future', product_EFFECTIVE_DATE_STRING='12/31/2999'),
            record(product_NAME='historic', product_EFFECTIVE_FLAG='2')]))
        self.assertEqual([r['product_id'] for r in reports], ['12345CV000A'])
        self.assertIn('productID=12345CV000A', reports[0]['url'])

    def test_ambiguous_or_executable_script_rejected(self):
        for html in ['var data = fetch("somewhere");', catalog_page([])+'\nvar data = {};']:
            with self.subTest(html=html), self.assertRaises(ValueError):
                source_fema.effective_reports(html)

    def discovery(self, pdf):
        service = json.dumps({'layers': [{'name': 'Political Jurisdictions', 'id': 99}]}).encode()
        schema = json.dumps({'fields': [{'name': 'CID'}, {'name': 'POL_NAME1'}]}).encode()
        features = json.dumps({'features': [{'attributes': {'CID': '123456', 'POL_NAME1': 'Example'}}]}).encode()
        responses = iter([service, schema, features, catalog_page([record()]).encode(), pdf])
        urls = []
        class Download:
            def get(self, url, limit):
                urls.append(url)
                return next(responses)
        with tempfile.TemporaryDirectory() as temp:
            with patch('ras_workflow.app_acquisition.progress'), patch('ras_workflow.app_acquisition.add_file', return_value={}) as add:
                with patch.object(source_fema, 'item', side_effect=lambda p: {'path': str(p)}):
                    attempts, links = source_fema.discover({}, {'longitude': -100, 'latitude': 40}, Path(temp), Download())
        self.assertIn('/99/query?', urls[2])
        return attempts, links, add

    def test_pdf_download_and_page_count(self):
        buffer = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(buffer)
        attempts, links, add = self.discovery(buffer.getvalue())
        self.assertEqual(attempts[-1]['status'], 'DOWNLOADED')
        self.assertEqual(attempts[-1]['pages'], 1)
        self.assertEqual(len(links), 2)
        self.assertEqual(add.call_count, 1)

    def test_bad_pdf_becomes_a_retained_failure(self):
        for pdf in [b'<html>Unavailable</html>', b'%PDF-1.7\nbroken']:
            with self.subTest(pdf=pdf):
                attempts, _, add = self.discovery(pdf)
                self.assertEqual(attempts[-1]['status'], 'DOWNLOAD_FAILED')
                self.assertTrue(attempts[-1]['error'])
                self.assertEqual(add.call_count, 0)


if __name__ == '__main__':
    unittest.main()
