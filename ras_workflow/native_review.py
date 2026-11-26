"""Inspect and copy supported steady inputs; never import old solver outputs.

Card layouts are those observed in the shipped USACE examples and USGS
Phelps model. Unsupported layouts stop at inspection, before user approval.
"""
import math
import re
import shutil
from pathlib import Path
from .common import ROOT, identifier, item, intact, read, rel, safe_path, save, utc


def text(path):
    return Path(path).read_bytes().decode('ascii').replace('\r\r\n','\n').replace('\r\n','\n')


def card(lines, key):
    values=[v.split('=',1)[1].strip() for v in lines if v.startswith(key+'=')]
    if len(values)!=1:raise ValueError('Expected one native card: '+key)
    return values[0]


def fixed(lines, start, count, width=8, blank=False):
    values=[];i=start
    while len(values)<count:
        line=lines[i];i+=1
        for j in range(0,len(line),width):
            v=line[j:j+width].strip()
            values.append(None if not v and blank else float(v))
    if len(values)!=count:raise ValueError('Unexpected fixed-width native record length')
    return values,i


def inspect(project, *, selected_plan=None):
    try:return _inspect(project,selected_plan=selected_plan)
    except (IndexError,KeyError,StopIteration) as e:
        raise ValueError('Native layout is outside the inspected importer scope. Keep the original files and use a reviewed adapter; no inputs were approximated.') from e


def _inspect(project, *, selected_plan=None):
    """Read only a selected steady plan and its inputs, without opening HEC-RAS."""
    project=Path(project).resolve()
    if project.suffix.lower()!='.prj':raise ValueError('Select the HEC-RAS .prj file')
    prj=text(project);previous=card(prj.splitlines(),'Current Plan')
    current=previous if selected_plan is None else selected_plan
    if not isinstance(current,str):raise ValueError('Select a saved steady plan such as p01')
    if not re.fullmatch(r'p\d{2}',current):raise ValueError('Select a saved steady plan in HEC-RAS first')
    planpath=project.with_suffix('.'+current);plan=text(planpath);pl=plan.splitlines()
    geom=card(pl,'Geom File');flow=card(pl,'Flow File')
    if not re.fullmatch(r'g\d{2}',geom) or not re.fullmatch(r'f\d{2}',flow):
        raise ValueError('Only 1D steady flow (.fNN) is supported; unsteady models need a separate workflow')
    for declaration in ['Plan File='+current,'Geom File='+geom,'Flow File='+flow]:
        if prj.splitlines().count(declaration)!=1:raise ValueError('Selected input is not uniquely listed in project: '+declaration)
    if 'English Units' not in prj.splitlines() or 'SI Units' in prj.splitlines():
        raise ValueError('This importer requires explicit English Units; SI conversion is not performed')
    regimes=[v.strip() for v in pl if v.strip() in ['Subcritical Flow','Supercritical Flow','Mixed Flow']]
    if len(regimes)!=1:raise ValueError('A single explicit steady flow regime is required')
    gp=project.with_suffix('.'+geom);fp=project.with_suffix('.'+flow)
    geometry=text(gp);fl=text(fp).splitlines();gl=geometry.splitlines()
    river=card(gl,'River Reach')
    # Result extraction is one reach with one culvert. Do not quietly truncate.
    blocks=re.split(r'^Type RM Length L Ch R =',geometry,flags=re.M)[1:]
    types=[int(v.split(',',1)[0].strip()) for v in blocks]
    if types.count(2)!=1 or any(v not in [1,2] for v in types) or types.count(1)<4:
        raise ValueError('Supported scope: one reach, one culvert crossing and at least four exterior sections')
    if any(re.search(p,geometry,re.M) for p in [r'^Junct Name=',r'^Storage Area=',r'^2D Flow Area=',r'^Lateral Structure=',r'^#Pier=\s*[1-9]']):
        raise ValueError('Junctions, storage/2D areas, lateral structures or bridge piers require a different adapter')
    station=[v.splitlines()[0].split(',')[1].strip() for v in blocks]
    ci=types.index(2)
    if ci<2 or ci>len(types)-3:raise ValueError('Need approach/face and face/recovery sections around the crossing')
    sections=[];ground_minima=[]
    for b,t,rs in zip(blocks,types,station):
        if t!=1:continue
        lines=b.splitlines();mi=next(i for i,v in enumerate(lines) if v.startswith('#Mann='))
        zi=next(i for i,v in enumerate(lines) if v.startswith('#Sta/Elev='))
        z,_=fixed(lines,zi+1,int(card(lines,'#Sta/Elev'))*2)
        ground_minima.append(min(z[1::2]))
        ncount=int(card(lines,'#Mann').split(',')[0]);rough,_=fixed(lines,mi+1,ncount*3)
        sections.append(dict(rs=rs,manning=[rough[i:i+3] for i in range(0,len(rough),3)],
            banks=[float(v) for v in card(lines,'Bank Sta').split(',')],
            ineffective_areas=any(v.startswith('#XS Ineff=') for v in lines)))
    bl=blocks[ci].splitlines();di=bl.index('Deck Dist Width WeirC Skew NumUp NumDn MinLoCord MaxHiCord MaxSubmerge Is_Ogee')
    deck=[v.strip() for v in bl[di+1].split(',')];pos=di+2;roads={}
    for side,count in [('upstream',int(deck[4])),('downstream',int(deck[5]))]:
        stations,pos=fixed(bl,pos,count);elev,pos=fixed(bl,pos,count);low,pos=fixed(bl,pos,count,blank=True)
        # The inspected reference culvert uses a buried deck closure. Accept only a
        # fully specified closure below every exterior ground point. A real
        # bridge opening or partial/ambiguous low chord remains unsupported.
        if any(v is not None for v in low):
            if any(v is None for v in low) or max(low)>=min(ground_minima):
                raise ValueError('Exposed or partial bridge low chords are outside the culvert-only import scope')
        roads[side]=list(map(list,zip(stations,elev)))
    groups=[]
    for i,line in enumerate(bl):
        if not line.startswith(('Culvert=','Multiple Barrel Culv=')):continue
        v=[v.strip() for v in line.split('=',1)[1].split(',')];shape={1:'circular',2:'box'}.get(int(v[0]))
        if not shape:raise ValueError('Only inspected circular and box culvert layouts are supported')
        multiple=line.startswith('Multiple');count=int(v[11]) if multiple else 1
        if multiple:
            xy,_=fixed(bl,i+1,2*count);centers=[xy[j:j+2] for j in range(0,len(xy),2)]
        else:centers=[[float(v[10]),float(v[12])]]
        end=next((j for j in range(i+1,len(bl)) if bl[j].startswith(('Culvert=','Multiple Barrel Culv='))),len(bl))
        extras=bl[i+1:end]
        b=dict(name=v[12] if multiple else v[13],count=count,shape=shape,rise_ft=float(v[1]),
            span_ft=float(v[1] if shape=='circular' else v[2]),length_ft=float(v[3]),culvert_n=float(v[4]),
            entrance_loss=float(v[5]),exit_loss=float(v[6]),chart=int(v[7]),scale=int(v[8]),us_invert_ft=float(v[9]),
            ds_invert_ft=float(v[10] if multiple else v[11]),distance_us_ft=float(v[14] if multiple else v[15]),centers_ft=centers)
        for native,key in [('Culvert Bottom n','bottom_n'),('Culvert Bottom Depth','bottom_n_depth_ft'),('Culvert Depth Blocked','depth_blocked_ft')]:
            if any(x.startswith(native+'=') for x in extras):b[key]=float(card(extras,native))
        groups.append(b)
    if not groups:raise ValueError('No supported culvert records; bridge-only models are unsupported')
    names=card(fl,'Profile Names').split(',');count=int(card(fl,'Number of Profiles'))
    if len(names)!=count:raise ValueError('Profile name count mismatch')
    locations=[i for i,v in enumerate(fl) if v.startswith('River Rch & RM=')]
    if len(locations)!=1:raise ValueError('Only constant discharge along one reach is supported')
    flows,_=fixed(fl,locations[0]+1,count)
    boundaries=[]
    for i,line in enumerate(fl):
        if not line.startswith('Boundary for River Rch & Prof#='):continue
        end=next((j for j in range(i+1,len(fl)) if fl[j].startswith('Boundary for River Rch & Prof#=')),len(fl))
        chunk=fl[i+1:end];bc=dict(profile_number=int(line.rsplit(',',1)[1]))
        for side,prefix in [('upstream','Up'),('downstream','Dn')]:
            typ=int(card(chunk,prefix+' Type'));bc[side]=dict(type=typ)
            if typ==3:bc[side]['slope']=float(card(chunk,prefix+' Slope'))
            elif typ == 1 and side == 'downstream' and regimes == ['Subcritical Flow']:
                stage = float(card(chunk, prefix + ' Known WS'))
                if not math.isfinite(stage):
                    raise ValueError('Known downstream stage must be finite')
                bc[side]['stage_ft'] = stage
            elif typ != 0:
                raise ValueError('Unsupported steady boundary. A known stage is supported at the downstream end of a subcritical plan.')
        boundaries.append(bc)
    if [v['profile_number'] for v in boundaries]!=list(range(1,count+1)):raise ValueError('Boundary profile identities differ')
    expected=dict(groups=groups,xs_count=len(sections),xs_stations=[v['rs'] for v in sections],road_width_ft=float(deck[1]),
        road_min_ft=min(v[1] for rows in roads.values() for v in rows),us_xs_rs=station[ci-1],ds_xs_rs=station[ci+1],structure_rs=station[ci],
        road_profiles=roads,weir_minimum_override_ft=float(deck[6]) if deck[6] else None)
    known = {str(row['profile_number']): row['downstream']['stage_ft'] for row in boundaries if row['downstream']['type'] == 1}
    if known:
        expected['imported_downstream_stages_ft'] = known
    return dict(selected_plan=current,previous_current_plan=previous,plan_title=card(pl,'Plan Title'),
        regime=regimes[0],river_reach=river,sections=sections,boundaries=boundaries,expected_native=expected,
        profiles=[dict(id=n.strip(),flow_cfs=q) for n,q in zip(names,flows)],
        files={'project':str(project),'plan':str(planpath),'geometry':str(gp),'flow':str(fp)},
        preserved_features=dict(ineffective_area_sections=[v['rs'] for v in sections if v['ineffective_areas']],
            distinct_road_profiles=roads['upstream']!=roads['downstream']))


def prepare(project, output, *, selected_plan=None):
    result=inspect(project,selected_plan=selected_plan);folder=safe_path(ROOT,output)
    if folder.exists():raise ValueError('Use a new import folder; existing projects are never overwritten')
    folder.mkdir(parents=True);original=folder/'original';original.mkdir()
    for key,value in result['files'].items():
        src=Path(value);target=original/src.name;shutil.copyfile(src,target);result['files'][key]=item(target)
    result.update(schema_version='native_import_review_1.0',status='WAITING_FOR_REVIEW',created_utc=utc(),
        review=dict(project_id=None,title=None,source=None,reviewer=None,native_length_unit=None,vertical_datum=None,approve=False))
    save(folder/'review.json',result);return folder/'review.json'


def approve(review_path, review, context=None, *, direct_start=False):
    path=safe_path(ROOT,review_path);packet=read(path);folder=path.parent
    if not intact(list(packet['files'].values())):raise ValueError('Native source files changed; inspect a new import')
    for key in (['project_id','title','source','vertical_datum'] if direct_start else ['project_id','title','source','reviewer','vertical_datum']):
        if not isinstance(review.get(key),str) or not review[key].strip():raise ValueError('Required review field: '+key)
    identifier(review['project_id'])
    if review.get('native_length_unit') not in ['international ft','US survey foot'] or review.get('approve') is not True:
        raise ValueError('Explicit foot convention and conditional import approval are required')
    # Reinspect bound original files, not editable expected values in the packet.
    verified=inspect(ROOT/packet['files']['project']['path'],selected_plan=packet['selected_plan'])
    if any(item(value)!=packet['files'][role] for role,value in verified['files'].items()):
        raise ValueError('Selected native input files changed; inspect a new import')
    for key in ['selected_plan','expected_native','profiles','regime','sections','boundaries','preserved_features']:
        if verified[key]!=packet[key]:raise ValueError('Import preview changed: '+key)
    for key in ['previous_current_plan','plan_title']:
        if key in packet and verified[key]!=packet[key]:raise ValueError('Import preview changed: '+key)
    additions={};context_receipt={}
    if context is not None:
        from .native_context import configuration
        additions,context_receipt=configuration(packet,review,context,folder,direct_start=direct_start)
    target=folder/'inputs';target.mkdir(exist_ok=False)
    for role,extension in [('project','.prj'),('plan','.p01'),('geometry','.g01'),('flow','.f01')]:
        src=ROOT/packet['files'][role]['path'];dest=target/('Model'+extension)
        if role in ['geometry','flow']:shutil.copyfile(src,dest)
        else:
            value=text(src)
            if role=='plan':
                value=re.sub(r'^Geom File=.*$', 'Geom File=g01', value,flags=re.M)
                value=re.sub(r'^Flow File=.*$', 'Flow File=f01', value,flags=re.M)
            else:
                value=re.sub(r'^Current Plan=.*$', 'Current Plan=p01', value,flags=re.M)
                # Preserve native card order; some versions stop reading lists
                # once later project settings have started.
                selected={'Plan File':verified['selected_plan'],'Geom File':Path(verified['files']['geometry']).suffix[1:],
                          'Flow File':Path(verified['files']['flow']).suffix[1:]}
                normalized={'Plan File':'p01','Geom File':'g01','Flow File':'f01'};lines=[]
                for line in value.splitlines():
                    key=line.split('=',1)[0]
                    if key in selected:
                        if line.split('=',1)[1].strip()!=selected[key]:continue
                        line=key+'='+normalized[key]
                    lines.append(line)
                value='\n'.join(lines)+'\n'
            dest.write_text(value,encoding='ascii')
    expected=packet['expected_native'];expected['vertical_datum']=review['vertical_datum']
    config=dict(schema_version='1.0',project_id=review['project_id'],title=review['title'],case_kind='site_conditional',location=None,
        terrain=dict(mode='not_applicable'),native_project='inputs/Model.prj',native_length_unit=review['native_length_unit'],
        expected_native=expected,native_import_review='import_receipt.json',geometry=None,authorization=None,
        scenarios=[dict(id='baseline',profiles=[dict(**p,source=review['source']) for p in packet['profiles']])],engineering_acceptance='NOT_ASSESSED')
    config.update(additions)
    if review.get('production_scope'):
        from .feasibility import scope
        config['production_scope'] = scope(review['production_scope'])
    cp=folder/'project.json';save(cp,config)
    save(folder/'import_receipt.json',dict(schema_version='native_import_1.0',status='CONDITIONAL_RUN_REQUESTED' if direct_start else 'CONDITIONALLY_AUTHORIZED_NOT_ENGINEERING_ACCEPTED',
        policy='local_computation_v1' if direct_start else 'named_review',review=review,
        inspection=item(path),sources=list(packet['files'].values())+context_receipt.get('source_context',[]),
        selected_plan=verified['selected_plan'],previous_current_plan=verified['previous_current_plan'],plan_title=verified['plan_title'],
        context=context_receipt,files=[item(cp)]+[item(p) for p in sorted(target.iterdir())],
        scope='Single reach, constant steady discharge, one circular/box culvert crossing. Raw geometry and flow preserved byte-for-byte; selected plan references normalized to 01.',created_utc=utc()))
    return cp
