"""Reported 1% AEP flows matched by official USGS streamgage ID, never by row order."""
import io
import re
import zipfile
from .usgs_water import pages, query
from xml.etree import ElementTree as ET

from pyproj import Geod

from .common import item
from .terrain import bbox_for

TABLE='https://pubs.usgs.gov/sir/2012/5113/data/sir20125113_Table4.xlsx'
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def table_value(data, station):
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError('USGS frequency download did not return an Excel workbook')
    with zipfile.ZipFile(io.BytesIO(data)) as workbook:
        def xml(name):
            info=workbook.getinfo('xl/'+name)
            if info.file_size>10_000_000:
                raise ValueError('Unexpected USGS workbook size')
            return ET.fromstring(workbook.read(info))
        strings=[''.join(el.itertext()).strip() for el in xml('sharedStrings.xml')]
        sheet=xml('worksheets/sheet1.xml')
    rows={}
    for row in sheet.findall('.//s:row',NS):
        cells={}
        for c in row.findall('s:c',NS):
            value=c.findtext('s:v',None,NS)
            if value is not None:
                cells[c.get('r').rstrip('0123456789')]=strings[int(value)] if c.get('t')=='s' else value
        rows[int(row.get('r'))]=cells
    if (rows[4].get('B')!='USGS station number' or 'cubic feet per second' not in rows[4].get('C','')
            or rows[5].get('R')!='1-percent' or [rows[6].get(k) for k in 'RST']!=['G','R','W']):
        raise ValueError('USGS table headers changed; review units and probability')
    hits=[(row,r) for row,r in rows.items() if r.get('B','').zfill(8)==station]
    if len(hits)!=1:
        return None
    row,values=hits[0]
    for key,method in [('T','weighted'),('R','at-station Bulletin 17B')]:
        cell=values.get(key,'')
        if re.fullmatch(r'\d+(?:\.\d+)?',cell) and float(cell)>0:
            return dict(value=float(cell),cell=key+str(row),method=method)
    return None


def normalized(name):
    replace={'c':'creek','cr':'creek','r':'river','fk':'fork','nr':'near'}
    return ' '.join(replace.get(w,w) for w in re.findall(r'[a-z]+',name.lower()))


def station_on_river(station_name, river_name):
    river = normalized(river_name)
    name = normalized(station_name)
    if not river or not name.startswith(river):
        return False
    suffix = name[len(river):]
    if not suffix:
        return True
    return suffix.startswith(' ') and suffix.split()[0] in {'at','a','near','above','below','ab','abv','bl','blw','upstream','downstream'}


def lookup(location, reach, out, download):
    lat,lon=location['latitude'],location['longitude']
    url=query('monitoring-locations',limit=100,bbox=','.join(map(str,bbox_for(lat,lon,1500))))
    sources=[]; features=[]
    for index,(address,raw,page) in enumerate(pages(url,download.get)):
        path=out/('streamgages.json' if index==0 else f'streamgages_{index + 1}.json')
        path.write_bytes(raw)
        sources.append(dict(**item(path,'USGS_streamgages'),url=address))
        features.extend(page['features'])
    river=normalized(reach.get('river') or '')
    stations=[]
    for feature in features:
        props=feature['properties']
        if props.get('agency_code')!='USGS' or props.get('state_code')!='06' or props.get('site_type_code')!='ST':
            continue
        xy=feature['geometry']['coordinates']
        distance=Geod(ellps='WGS84').inv(lon,lat,*xy[:2])[2]
        matches=station_on_river(props['monitoring_location_name'], river)
        if (distance<=25 and (not river or matches)) or (matches and distance<=1500):
            stations.append((distance,props))
    if not stations:
        return dict(route='CA_USGS_gage_frequency',status='NO_MATCHING_STREAMGAGE',sources=sources)
    table=out/'USGS_CA_peak_frequency_table4.xlsx'
    data=download.get(TABLE,2_000_000);table.write_bytes(data)
    sources.append(dict(**item(table,'USGS_published_frequency_table'),url=TABLE))
    found=[]
    for distance,props in sorted(stations,key=lambda s:s[0]):
        station=props['monitoring_location_number']
        value=table_value(data,station)
        if value:
            basis=(f"USGS SIR 2012-5113, Table 4, cell {value['cell']}; {value['method']} 1% annual exceedance flow "
                   f"through water year 2006 at station {station} ({props['monitoring_location_name']}); "
                   f"{distance:.0f} m from the project coordinate. Check reach transfer, tributaries and subsequent flood records.")
            found.append(dict(**value,station=station,distance_m=round(distance,1),basis=basis,
                              location=props['monitoring_location_name'],drainage_area_sqmi=props.get('drainage_area'),
                              evidence_class='reported' if distance<=25 else 'assumed'))
    return dict(route='CA_USGS_gage_frequency',status='MATCH_CANDIDATE' if found else 'NO_PUBLISHED_ESTIMATE',
                sources=sources,matches=found)
