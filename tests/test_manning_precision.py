"""Regression checks for fixed-width Manning data through native model creation."""
import tempfile
import unittest
from pathlib import Path

from ras_workflow import native
from ras_workflow.river_report import roughness_text
from ras_workflow.section_hydraulics import manning_cards
from test_river_contract import river


class ManningPrecision(unittest.TestCase):
    def test_native_build_preserves_default_and_segmented_coefficients(self):
        geometry = river()
        geometry['cross_sections'][1]['manning_segments'] = [
            [0, .1101234], [10, .0425], [20, .035125], [50, .065]]
        scenario = dict(id='precision', channel_n=.0425, overbank_n=.110,
                        profiles=[dict(id='CHECK', flow_cfs=100)])
        config = dict(project_id='precision_software_test', case_kind='software_validation')
        with tempfile.TemporaryDirectory() as temporary:
            project, expected = native.build(Path(temporary)/'model', config, scenario, geometry)
            lines = project.with_suffix('.g01').read_text(encoding='ascii').splitlines()
            roughness = []
            for index, line in enumerate(lines):
                if not line.startswith('#Mann='):
                    continue
                count = int(line.split('=')[1].split(',')[0])
                values = []
                for data in lines[index+1:index+1+(count+2)//3]:
                    values.extend(float(data[i:i+8]) for i in range(0,len(data),8))
                self.assertEqual(len(values), count*3)
                roughness.append([[values[i],values[i+1]] for i in range(0,len(values),3)])
            self.assertEqual(roughness, expected['manning_by_section'])
            self.assertEqual(roughness[0][1][1], .0425)
            self.assertEqual(roughness[1][0][1], .1101234)

    def test_station_width_is_independent_of_coefficient_precision(self):
        text = manning_cards([[1234.1234,.0425]], native.fixed)
        self.assertEqual(text[:8], '1234.123')
        self.assertEqual(float(text[8:16]), .0425)
        self.assertEqual(len(text.rstrip('\n')), 24)

    def test_wide_station_only_discards_insignificant_zeroes(self):
        fields = native.fixed([25364.25, 12345678, 9999.125]).rstrip('\n')
        self.assertEqual([fields[i:i+8] for i in range(0,24,8)],
                         ['25364.25', '12345678', '9999.125'])
        for value in (25364.251, 123456789):
            with self.assertRaisesRegex(ValueError, 'overflow'):
                native.fixed([value])

    def test_invalid_or_unrepresentable_coefficient_is_rejected(self):
        for value in [0, 1, float('nan'), 1e-9, .999999999]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                manning_cards([[0,value]], native.fixed)

    def test_report_keeps_confirmed_coefficient(self):
        self.assertEqual(roughness_text(.0425), '0.0425')
        self.assertEqual(roughness_text(.1101234), '0.1101234')
        self.assertEqual(roughness_text(None), '—')


if __name__ == '__main__':
    unittest.main()
