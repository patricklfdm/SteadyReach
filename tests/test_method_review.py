import json
import unittest
from ras_workflow.method_review import series, timing


class Timing(unittest.TestCase):
    def rows(self, hours):
        return [dict(properties=dict(time=f'2020-01-02T{h:02d}:00:00Z',value=100,
                    monitoring_location_id='USGS-01020304',time_series_id='series',unit_of_measure='ft^3/s',
                    approval_status='Approved',parameter_code='00060')) for h in hours]

    def test_continuity_and_event_association(self):
        rows=self.rows([0,1,2,20,21,22,23])
        info=series(json.dumps(dict(features=rows)).encode(),'2020-01-02','Flood',100)
        self.assertEqual(info['gap_hours'],18)
        self.assertEqual(info['near_peak_continuous_minutes'],180)
        self.assertIn('different profile',timing(info,[dict(id='Flood',flow_cfs=150)])[0])

    def test_mixed_records_and_incomplete_download(self):
        rows=self.rows([1,2,3])
        rows[-1]['properties']['monitoring_location_id']='USGS-4321'
        with self.assertRaisesRegex(ValueError,'one approved'):
            series(json.dumps(dict(features=rows)).encode(),'2020-01-02','Flood',100)
        with self.assertRaisesRegex(ValueError,'complete'):
            series(json.dumps(dict(features=rows,links=[dict(rel='next')])).encode(),'2020-01-02','Flood',100)
