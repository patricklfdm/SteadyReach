"""Read native geometry for delivery maps; never write hydraulic HDF datasets.

Dataset names and Mapper XML nodes were inspected in HEC-RAS 7.0.1's
GUI-saved reference project. Only one georeferenced reach/culvert is supported.
"""
from pathlib import Path
import math
import xml.etree.ElementTree as ET
import zipfile
import h5py
import numpy as np
from pyproj import CRS
from .common import item, save


def interpolate_line(points, fraction):
    lengths=[math.dist(a,b) for a,b in zip(points,points[1:])]
    if not lengths or sum(lengths)<=0 or not 0<=fraction<=1:
        raise ValueError('Invalid bank location along native cutline')
    position=fraction*sum(lengths)
    for a,b,length in zip(points,points[1:],lengths):
        if position<=length and length:
            return [a[j]+(b[j]-a[j])*position/length for j in (0,1)]
        position-=length
    return list(points[-1])


def extract(hdf, crs_value):
    crs=CRS.from_user_input(crs_value)
    if not crs.is_projected:raise ValueError('Delivery geometry requires a reviewed projected CRS')
    def feature(kind,coordinates,**properties):
        return dict(type='Feature',geometry=dict(type=kind,coordinates=coordinates),properties=properties)
    layers={'river':[], 'cross_sections':[], 'banks':[], 'structures':[]}
    with h5py.File(hdf,'r') as h:
        for group,info_name,point_name,target in [
            ('River Centerlines','Polyline Info','Polyline Points','river'),
            ('Cross Sections','Polyline Info','Polyline Points','cross_sections'),
            ('Structures','Centerline Info','Centerline Points','structures')]:
            g=h['Geometry/'+group];infos=g[info_name][:];points=g[point_name][:];attrs=g['Attributes'][:]
            if len(attrs)!=len(infos):raise ValueError('Native spatial attribute/line count mismatch')
            if target!='cross_sections' and len(infos)!=1:raise ValueError('Delivery supports one reach and one crossing')
            for i,(a,info) in enumerate(zip(attrs,infos)):
                start,count,part_start,parts=map(int,info)
                if parts!=1 or count<2 or start<0 or start+count>len(points):raise ValueError('Unsupported multipart or missing native cutline')
                xy=points[start:start+count].astype(float).tolist()
                if not np.isfinite(xy).all():raise ValueError('Nonfinite native map coordinate')
                rs=a['RS'].decode().strip() if 'RS' in a.dtype.names else ''
                name=('RS '+rs) if rs else a['River Name'].decode().strip()
                layers[target].append(feature('LineString',xy,rs=rs,name=name,
                    basis='Native solver geometry; structure line is not buried barrel footprint'))
                if target=='cross_sections':
                    si,sc=map(int,g['Station Elevation Info'][i]);se=g['Station Elevation Values'][si:si+sc]
                    first,last=float(se[0,0]),float(se[-1,0])
                    if last<=first:raise ValueError('Invalid section station range')
                    for side,key in [('Left','Left Bank'),('Right','Right Bank')]:
                        station=float(a[key]);fraction=(station-first)/(last-first)
                        layers['banks'].append(feature('Point',interpolate_line(xy,fraction),rs=rs,name=side+' bank '+rs,
                            side=side,station=station,basis='Native bank station mapped proportionally along native cutline; reviewed model input'))
    allxy=[xy for key in ['cross_sections','structures'] for f in layers[key] for xy in f['geometry']['coordinates']]
    a=np.asarray(allxy);bounds=[float(a[:,0].min()),float(a[:,1].min()),float(a[:,0].max()),float(a[:,1].max())]
    if bounds[0]==bounds[2] or bounds[1]==bounds[3]:raise ValueError('Degenerate geographic extent')
    return dict(crs=crs.to_wkt(),bounds=bounds,layers=layers,source=item(hdf),
        bank_mapping='Proportional station range to native cutline length; not surveyed bank coordinates')


def write_layers(spatial,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    for name,features in spatial['layers'].items():
        # Projected GeoJSON is an intermediate consumed with explicit CRS by QGIS.
        save(folder/(name+'.json'),dict(type='FeatureCollection',features=features))
    save(folder/'spatial.json',spatial)


def mapper(project, terrain, projection, bounds, interval, imagery=None, contours=None):
    """Emit the small observed XML subset; GUI round-trip is a separate check."""
    import os
    project=Path(project)
    def relative(p):return os.path.relpath(p,project.parent).replace('/','\\')
    root=ET.Element('RASMapper');ET.SubElement(root,'Version').text='2.0.0'
    ET.SubElement(root,'RASProjectionFilename',Filename=relative(projection))
    ET.SubElement(root,'Features')
    gs=ET.SubElement(root,'Geometries',Checked='True',Expanded='True')
    g=ET.SubElement(gs,'Layer',Name='Reviewed native geometry',Type='RASGeometry',Checked='True',Expanded='True',Filename=relative(project.with_suffix('.g01.hdf')))
    ET.SubElement(g,'Layer',Type='RASRiver',Checked='True')
    xs=ET.SubElement(g,'Layer',Type='RASXS',Checked='True')
    ET.SubElement(xs,'PlotOption',Name='Bank Stations')
    ET.SubElement(g,'Layer',Type='BridgesCulvertsLayer',Checked='True')
    ET.SubElement(root,'Plans');ET.SubElement(root,'EventConditions')
    results=ET.SubElement(root,'Results')
    ET.SubElement(results,'Layer',Name='Steady results',Type='RASResults',Filename=relative(project.with_suffix('.p01.hdf')))
    maps=ET.SubElement(root,'MapLayers',Checked='True',Expanded='True')
    if contours:ET.SubElement(maps,'Layer',Name='Ground contours',Type='PolylineFeatureLayer',Filename=relative(contours))
    if imagery:
        layer=ET.SubElement(maps,'Layer',Name='Offline imagery',Type='ImageLayer',Filename=relative(imagery))
        ET.SubElement(layer,'ResampleMethod').text='near'
    ts=ET.SubElement(root,'Terrains',Checked='True',Expanded='True')
    t=ET.SubElement(ts,'Layer',Name='Terrain',Type='TerrainLayer',Checked='True',Filename=relative(terrain))
    sym=ET.SubElement(t,'Symbology');ET.SubElement(sym,'HillShade',On='True',Azimuth='315',Zenith='45',ZFactor='1')
    ET.SubElement(sym,'Contour',On='True',Interval=str(interval),Color='-16777216')
    ET.SubElement(t,'ResampleMethod').text='near';ET.SubElement(t,'Surface',On='True')
    view=ET.SubElement(root,'CurrentView')
    for key,val in zip(['MinX','MinY','MaxX','MaxY'],bounds):ET.SubElement(view,key).text=str(val)
    ET.SubElement(root,'Units').text='US Customary'
    ET.SubElement(root,'RenderMode').text='sloping'
    ET.indent(root)
    ET.ElementTree(root).write(project.with_suffix('.rasmap'),encoding='utf-8',xml_declaration=False)


def check_references(folder):
    """Check each package's own paths, including native HDF terrain associations."""
    folder=Path(folder).resolve();checks=[]
    def check(base,value):
        p=(base/value.replace('\\','/')).resolve()
        if not p.is_relative_to(folder) or not p.is_file():raise ValueError('Missing/external delivery dependency: '+value)
        checks.append(p.relative_to(folder).as_posix())
    for p in folder.rglob('*.rasmap'):
        for e in ET.parse(p).iter():
            for key in ['Filename','GeometryHDF']:
                if e.get(key):check(p.parent,e.get(key))
    for p in folder.rglob('*.vrt'):
        for e in ET.parse(p).iter('SourceFilename'):
            if e.get('relativeToVRT')!='1':raise ValueError('Terrain VRT contains an absolute dependency')
            check(p.parent,e.text)
    for p in folder.rglob('*.g01.hdf'):
        with h5py.File(p,'r') as h:
            value=h['Geometry'].attrs.get('Terrain Filename')
            if isinstance(value,bytes):value=value.decode()
            if value:check(p.parent,value)
    for p in folder.rglob('*.shp'):
        for ext in ['.shx','.dbf','.prj']:check(p.parent,p.with_suffix(ext).name)
    for p in (folder/'HEC_RAS').glob('*.prj'):
        cards=p.read_text(encoding='ascii').splitlines()
        for line in cards:
            if line.split('=',1)[0] in ['Current Plan','Plan File','Geom File','Flow File']:
                ext=line.split('=',1)[1].strip()
                if not __import__('re').fullmatch('[pgf][0-9]{2}',ext):raise ValueError('Unsupported native reference: '+line)
                check(p.parent,p.with_suffix('.'+ext).name)
        for plan in p.parent.glob(p.stem+'.p[0-9][0-9]'):
            for line in plan.read_text(encoding='ascii').splitlines():
                if line.startswith(('Geom File=','Flow File=')):
                    ext=line.split('=',1)[1].strip()
                    if not __import__('re').fullmatch('[gf][0-9]{2}',ext):raise ValueError('Unsupported native plan reference')
                    check(plan.parent,p.with_suffix('.'+ext).name)
    for p in folder.glob('*.qgz'):
        with zipfile.ZipFile(p) as z:
            names=[n for n in z.namelist() if n.endswith('.qgs')]
            if len(names)!=1:raise ValueError('Ambiguous QGIS project')
            for layer in ET.fromstring(z.read(names[0])).findall('./projectlayers/maplayer'):
                value=layer.findtext('datasource')
                if not value:raise ValueError('Missing QGIS datasource')
                check(p.parent,value.split('|',1)[0])
    return sorted(set(checks))
