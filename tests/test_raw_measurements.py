import json
import unittest
from ras_workflow.raw_measurements import parse, suggestions, stage_rows, invert_rows, gage_table

PROFILES=[dict(id='Jan',flow_cfs=100)]
GEOM=dict(horizontal_crs='EPSG:32615',vertical_datum='NAVD88',structure={'groups':[{}]},
          cross_sections=[dict(rs=rs,center_xy=[500000,y],cutline_xy=[[499970,y],[500030,y]],station_ft=[0,197])
                          for rs,y in [(200,4200100),(100,4200000)]])
META=dict(crs='EPSG:32615',datum='NAVD88',unit='ft',profile='Jan',event='Jan',date='2024-01-01',flow=100,flow_unit='cfs')

def preview(text,mode='stage',settings=META):
    headers,cols,rows=parse(text.encode(),'source.csv',{})
    return stage_rows(rows,settings,GEOM,PROFILES,cols,mode)[0]

class FieldBook(unittest.TestCase):
    def test_unreported_reference_stays_unknown(self):
        _,cols,raw=parse(b'X,Y,measwse\r\n500000,4200000,20\r\n','river_20240101.csv',{})
        defaults=suggestions(raw,cols,'river_20240101.csv',PROFILES)
        self.assertEqual((defaults['date'],defaults['flow'],defaults['profile']),('2024-01-01',100,'Jan'))
        self.assertTrue({'crs','datum','unit'}.isdisjoint(defaults))

    def test_column_mapping_and_record_number(self):
        _,cols,rows=parse(b'xx\tY\tZ\n500000\t4200000\t0\n','custom.tsv',{'x':'xx'})
        self.assertEqual((cols['x'],rows[0][0],rows[0][1]['level']),('xx',2,'0'))
        with self.assertRaises(ValueError):parse(b'x,y,z\n1,2,3\n','a.csv',{'x':'z'})
        with self.assertRaises(ValueError):parse(b'x,x,z\n1,2,3\n','a.csv',{})

    def test_roles_and_repeated_points(self):
        hdr='x,y,measwse\n'
        rows=preview(hdr+'500000,4200000,1\n500000,4200100,2\n500000,4200000,1\n')
        self.assertEqual([r['role'] for r in rows],['outlet','interior'])
        self.assertIn('DUPLICATE_POINT',rows[0]['issues'])
        self.assertEqual(rows[0]['nearby_lines'],[4])
        self.assertEqual(rows[1]['issues'],[])

    def test_row_datum_and_flow_override_model(self):
        rows=preview('x,y,wse,datum,flow\n500000,4200000,2,NGVD29,1\n')
        self.assertTrue({'DATUM_MISMATCH','DISCHARGE_MISMATCH'}.issubset(rows[0]['issues']))

    def test_relative_reading_is_never_an_absolute_outlet(self):
        r=preview('x,y,gage height (ft)\n500000,4200000,6\n')[0]
        self.assertIn('GAGE_REQUIRES_REGISTER',r['issues'])

    def test_partial_invert_leaves_other_end_unknown(self):
        _,_,rows=parse(b'group,inletinvertft,outletinvertft,datum\n1,0,,NAVD88\n','a.csv',{})
        values,missing=invert_rows(rows,dict(unit='ft'),GEOM,PROFILES)
        self.assertEqual([r['value_ft'] for r in values],[0.])
        self.assertEqual(missing,['g.structure.groups.0.ds_invert_ft'])
        values,_=invert_rows(rows*2,dict(unit='ft'),GEOM,PROFILES)
        self.assertTrue(all('DUPLICATE_TARGET' in r['issues'] for r in values))

    def test_gage_flow_requires_same_site_and_visit(self):
        def feature(station,visit,kind,value,unit):
            return dict(properties=dict(monitoring_location_id=station,field_visit_id=visit,reading_type=kind,
                        value=value,unit_of_measure=unit,time='2024-03-15T08:00:00Z'),geometry=dict(coordinates=[-121,37]))
        data=dict(type='FeatureCollection',features=[
            feature('USGS-1','one','MeanGageHeight','3','ft'),feature('USGS-2','one','Discharge','4','ft^3/s'),
            feature('USGS-1','two','Discharge','100','ft^3/s')])
        source=lambda:json.dumps(data).encode()
        index,r=gage_table(source())[0]
        self.assertEqual((index,r['flow']),(1,''))
        data['features'].append(feature('USGS-1','one','Discharge','23','ft^3/s'))
        r=gage_table(source())[0][1]
        self.assertEqual((r['date'],r['flow'],r['flow_unit']),('2024-03-15','23','cfs'))
