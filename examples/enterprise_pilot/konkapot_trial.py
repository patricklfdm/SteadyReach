"""Prepare a conditional diagram-based alternative A through the normal editable intake."""
import argparse
import base64
import json
import os
from pathlib import Path
import sys

import numpy as np
import rasterio

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'ras_workflow').is_dir())
sys.path.insert(0,str(ROOT))
from ras_workflow import inputs, intake
from ras_workflow.common import read, save, sha

REPORT = 'https://www.mass.gov/doc/conceptual-design-report/download'
VERTICAL = 'https://www.usgs.gov/faqs/what-projection-horizontal-datum-vertical-datum-and-resolution-a-usgs-digital-elevation-model'
FT_PER_M = 1 / .3048
# Printed river station, source minimum channel elevation, published PDF page.
SECTIONS = [(2732,1243.59,130), (2700,1245.09,132), (2666,1244.80,134), (2604,1244.50,136), (2569,1244.72,138)]
BASIS = ('Alternative A local screening reconstruction. Coordinates interpreted from NAIP and sheets G-2 and C-5. '
         'Five local cuts, bank locations, submerged shape, local normal-depth transfer, barrel/road lengths, loss '
         'coefficients and roughness are conditional. The original 3255 ft reach includes a dam and footbridge. '
         'The reference stages in the study are modeled. Field measurement uncertainty and independent flood stages are unavailable.')
def geometry(dem):
    # Distances are referenced to the center of the road; map anchors are interpretations from the NAIP.
    anchors=np.array([[647541,4671287],[647537.5,4671273],[647539.5,4671256],
                      [647541,4671245],[647542,4671235],[647546,4671225],[647554,4671216]])
    chain=np.r_[0,np.cumsum(np.linalg.norm(np.diff(anchors,axis=0),axis=1))]
    river_stations=2635+(chain[3]-chain)*FT_PER_M
    def center(rs):
        return np.array([np.interp(rs,river_stations[::-1],anchors[::-1,axis]) for axis in (0,1)])
    # The five closely spaced sections have a shared east-to-west normal looking downstream.
    offset=np.arange(-48.,48.01,.5)
    station=(offset-offset[0])*FT_PER_M
    lateral=np.c_[-offset,np.zeros(len(offset))]
    rows=[]
    with rasterio.open(dem) as data:
        if data.crs.to_epsg()!=26918:raise ValueError('Unexpected DEM coordinate system')
        def samples(xy):
            z=np.array([float(v[0]) for v in data.sample(xy,masked=True)])*FT_PER_M
            if not np.isfinite(z).all():raise ValueError('Unexpected missing terrain')
            return z
        for i,(rs,bed,page) in enumerate(SECTIONS):
            xy=center(rs)+lateral
            surface=samples(xy)
            # A water-surface DEM cannot supply submerged geometry. Use an explicitly assumed
            # flat 3 m bed transitioning back to the original bank terrain 5 m from center.
            weight=np.clip((5.-np.abs(offset))/3.5,0,1)
            z=(1-weight)*surface+weight*bed
            if min(z)<bed-.25:
                raise ValueError('Review unexpectedly lower terrain outside the assumed bed at RS '+str(rs))
            bank_width=2.5 if rs in (2666,2604) else 3.
            idx=[int(np.where(offset==v)[0][0]) for v in (-bank_width,bank_width)]
            # Use published in-channel distances, with equal left/right lengths as a screening assumption.
            length=rs-SECTIONS[i+1][0] if i+1<len(SECTIONS) else 0.
            rows.append(dict(rs=rs,reach_id='river',local_chainage_ft=SECTIONS[0][0]-rs,
                cutline_xy=xy[[0,-1]].tolist(),center_xy=center(rs).tolist(),station_ft=station.round(6).tolist(),
                elevation_ft=z.round(6).tolist(),bank_stations_ft=station[idx].round(6).tolist(),
                reach_lengths_ft=[length]*3,expansion_contraction=[.5,.3] if rs in (2700,2666,2604) else [.3,.1],
                reach_length_basis='Channel path approximated from the published station differences; overbank lengths assumed equal.',
                channel_floor_basis=f'Published model minimum {bed} ft at RS {rs}, PDF page {page}. Interpreted submerged shape.'))
        crest=samples(center(2635)+lateral)
        road_center=float(crest[len(crest)//2])
        road=np.maximum(1256.5,crest-road_center+1256.5)
    center_station=round(float(station[len(station)//2]),6)
    opening=dict(name='AltA',count=1,shape='box',span_ft=15.,rise_ft=12.,length_ft=40.,distance_us_ft=11.,
        us_invert_ft=1242.8,ds_invert_ft=1242.5,depth_blocked_ft=2.,bottom_n_depth_ft=2.1,mann_top=.013,mann_bottom=.035,
        blockage_basis='Published 2 ft design embedment, assumed continuously filled along the barrel. Composite bottom n and its depth are conditional.',
        bottom_type='Concept alternative A: precast concrete box with 2 ft natural substrate above the structural floor.',
        inlet_description='Existing wingwalls retained in the conceptual layout; square-edge inlet and wingwall angle assumed for screening.',
        entrance_loss=.5,exit_loss=1.,chart_scale=[8,1],centers_ft=[[center_station,center_station]],evidence_class='inferred')
    return dict(schema_version='1.0',model_type='culvert',hydraulic_unit='international_ft',horizontal_crs='EPSG:26918',
         vertical_datum='NAVD88',river='Konkapot',reach='Main Road',flow_regime='subcritical',
         boundary_slopes=dict(downstream=.001149),cross_sections=rows,flowlines=[dict(id='river',xy=anchors.tolist())],
         functional_section_basis=BASIS,provenance=[REPORT,VERTICAL,BASIS],
         structure=dict(rs=2635,us_xs_rs=2666,ds_xs_rs=2604,groups=[opening],road=dict(profile_mode='shared',
            distance_us_ft=11.,width_ft=40.,weir_coefficient=2.6,station_ft=station.round(6).tolist(),
            elevation_ft=road.round(6).tolist())))
def prepare(source,out):
    hashes=read(Path(__file__).with_name('source_hashes.json'))
    pdf=source/'Konkapot_conceptual_report.pdf';dem=source/'Konkapot_USGS_terrain.tif'
    for file in (pdf,dem):
        if sha(file)!=hashes[file.name]:raise ValueError('Unexpected original file: '+file.name)
    out.mkdir(parents=True,exist_ok=False)
    relative=lambda file:os.path.relpath(file,out)
    proposed=geometry(dem)
    problems=inputs.geometry_errors(proposed)
    if problems:raise ValueError(problems)
    scenario=dict(id='q100',profiles=[dict(id='Q100',flow_cfs=1620.,source=REPORT+' PDF p. 91 Table 1, p. 94 Table 2.')],
        channel_n=.035,overbank_n=.065,culvert_n=.013,parameter_source='Trial assumptions for a gravel channel, vegetated overbanks and concrete box; obtain surveyed subdivisions and calibration before engineering use.')
    project=inputs.template('konkapot_alt_a',42.17948,-73.21343)
    project.update(title='Konkapot River at Main Road • Conceptual alternative A screening',scenarios=[scenario],
        terrain=dict(mode='local',raster=relative(dem),vertical_datum='NAVD88',vertical_unit='m',create_native=True,
                     provenance=relative(source/'Konkapot_terrain_source.json')),
        delivery=dict(enabled=True,horizontal_crs='EPSG:26918',contour_interval=2,mapping_enabled=True,
                      imagery=dict(mode='local',raster=relative(source/'konkapot_imagery/Aerial.tif'),
                        source='USGS/USDA NAIP MA 2023, tile m_4207355_sw_18_030_20230902'),
                      additional_sources=[relative(pdf),relative(source/'Konkapot_terrain_source.json'),relative(source/'konkapot_imagery/acquisition.json'),'trial_basis.json']))
    project['location'].update(source='Project StreamStats pin, not a surveyed opening center.',crossing_confirmed=True)
    save(out/'trial_basis.json',dict(evidence_class='conditional_developer_trial',construction_status='conceptual alternative A',source=REPORT,
         section_basis=SECTIONS,alternative='15 x 12 ft box with 2 ft embedment, replacement design at PDF pp. 92, 176',
         estimated_inverts='Assumed natural substrate meets adjacent published channel minima of 1244.80/1244.50 ft. Structural floors are 2 ft lower.',
         downstream='Published alternative A Q100 energy slope at the terminal local RS 2569, PDF p.138. Using it for normal depth is a conditional transfer. Dam effects require a longer reach.',
         road='DEM cut shifted to 1256.5 ft at the center with crest clipped at published minimum; exterior extent/width are assumed. No deck survey imported.',
         validation='Published Q100 headwater is a modeled, contextual comparison. No measured Q100 water level.',
         limitations=BASIS))
    config=out/'project.json';save(config,project)
    session=intake.prepare(config,'q100');sp=ROOT/session['session']
    missing=intake.validate(sp,require_consent=False)
    if missing['ready']:raise ValueError('Partial data incorrectly allowed a solve')
    payload=json.dumps(proposed,ensure_ascii=False).encode('utf-8')
    page=intake.upload(sp,0,'conditional_geometry.json',base64.b64encode(payload).decode(),'geometry',BASIS,'inferred')
    answers={}
    for f in page['fields']:
        if f['value'] is None or f['value']==[] or f['value']=='':continue
        basis=BASIS
        evidence='assumed'
        if 'flow_cfs' in f['key'] or f['key'].endswith(('.rise_ft','.span_ft')):
            evidence='reported';basis=REPORT+' PDF pp. 91, 92. Published conceptual design and discharge.'
        answers[f['key']]=dict(value=f['value'],evidence_class=evidence,basis=basis,confirmed=True)
    page=intake.save_draft(sp,dict(revision=page['draft']['revision'],answers=answers,basis=BASIS))
    decision=intake.apply(sp,page['draft']['revision'],direct_start=True,mapping_enabled=True)
    if decision.get('status')!='APPLIED':raise ValueError(decision)
    save(out/'intake_result.json',dict(status='COMPLETE_INPUTS_FOR_CONDITIONAL_TRIAL',missing_initial=len(missing['errors']),
        project=decision['project'],assumptions='trial_basis.json',geometry_hash=sha((ROOT/decision['project']).parent/'geometry.json'),
        engineering_acceptance='NOT_ASSESSED'))
    return ROOT/decision['project']
if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('source',type=Path);cli.add_argument('output',type=Path)
    args=cli.parse_args();print(prepare(args.source.resolve(),args.output.resolve()))
