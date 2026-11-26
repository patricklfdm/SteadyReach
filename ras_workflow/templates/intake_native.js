'use strict';
// The alternative handoff remains in the same saved intake session.
function nativeInputCard(screen){
 const box=el('details');box.id='native-input-handoff';box.open=Boolean(data.native_import);
 box.append(el('summary',tr('Have a complete HEC-RAS model? Continue here','已有完整 HEC-RAS 模型？在这里接续')));screen.append(box);
 box.append(el('p',tr('Supply the four selected steady input files. Review the extracted geometry, roughness, boundaries and flows below. Coordinates, acquired DEM and prior flow evidence stay with this project. Previous result files are never imported.','提供所选恒定流计划的四个输入文件，在下方审核提取的几何、糙率、边界和流量。保留本项目坐标、已下载 DEM 及已填流量证据，不导入旧结果文件。')));
 const source=el('input');source.id='native-source-upload';source.value=data.draft.native_review?.source||'';
 const sl=el('label',tr('Model source, version and applicable site','模型来源、版本及适用地点'));sl.htmlFor=source.id;
 const files=el('input');files.id='native-files';files.type='file';files.multiple=true;
 const fl=el('label',tr('Select .prj + selected .pNN + .gNN + .fNN together','同时选择 .prj、所选 .pNN、.gNN、.fNN'));fl.htmlFor=files.id;
 box.append(sl,source,fl,files,button(tr('Inspect native inputs','检查原生输入'),()=>geometryTask(tr('Inspecting source files…','正在检查来源文件…'),async()=>{
  if(files.files.length!==4)throw Error(tr('Select exactly four native input files.','请选择四个原生输入文件。'));
  const rows=[];for(const file of files.files){if(file.size>15000000)throw Error('Maximum 15 MB');const content=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(Error('File read failed'));r.readAsDataURL(file);});rows.push({name:file.name,content});}
  applyResponse(await request('native-upload',{revision:data.draft.revision,files:rows,source:source.value}));
 })));
 const local=el('details');local.append(el('summary',tr('Use a model already inside this workspace','使用已放在本项目工作区内的模型')));
 local.append(el('p',tr('Copy the source model folder into this workspace first, then paste its .prj path below (absolute or relative to the workspace root). The selected plan and its geometry/steady-flow files are inspected together. Only these four input files are read; result files are excluded.','先将来源模型文件夹放入本项目工作区，再粘贴其中 .prj 的绝对路径或相对工作区根目录的路径。程序一起检查所选计划及其几何、恒定流文件，只读取这四个输入文件，不导入结果。')));
 const localPath=el('input');localPath.id='native-workspace-path';const localLabel=el('label',tr('HEC-RAS .prj path inside this workspace','工作区内 HEC-RAS .prj 路径'));localLabel.htmlFor=localPath.id;
 const localPlan=el('input');localPlan.id='native-workspace-plan';localPlan.placeholder='p01';const planLabel=el('label',tr('Steady plan (optional; empty uses the saved Current Plan)','恒定流计划（可选，如 p01；留空使用原工程当前计划）'));planLabel.htmlFor=localPlan.id;
 local.append(localLabel,localPath,planLabel,localPlan,button(tr('Inspect workspace model','检查工作区模型'),()=>geometryTask(tr('Inspecting source files…','正在检查来源文件…'),async()=>{
  applyResponse(await request('native-workspace',{revision:data.draft.revision,project:localPath.value,selected_plan:localPlan.value.trim(),source:source.value}));
 })));box.append(local);
 const preview=data.native_import;if(!preview)return;
 const p=preview.packet,r=data.draft.native_review;r.mapping??={};const m=r.mapping;
 box.append(el('h3',tr('Review imported inputs','审核导入输入')),el('p',p.river_reach+' · '+p.regime),el('p',p.profiles.map(v=>v.id+': '+v.flow_cfs+' cfs').join('; ')));
 box.append(el('p',tr('Selected steady plan: ','本次选择的恒定流计划：')+p.selected_plan+(p.plan_title?' · '+p.plan_title:'')));
 if(p.previous_current_plan&&p.previous_current_plan!==p.selected_plan)box.append(el('p',tr('The source project saved Current Plan ','原工程保存的当前计划为 ')+p.previous_current_plan+tr('; this review uses the selected plan above. Original files are preserved; approval is still required.','；本次审核采用上方所选计划。原件保持不变，仍需审核批准。')));
 for(const v of p.expected_native.groups)box.append(el('p',v.name+': '+v.count+' × '+v.shape+'; '+v.span_ft+' × '+v.rise_ft+' ft; '+tr('length ','涵长 ')+v.length_ft+' ft; '+tr('inverts ','涵底 ')+v.us_invert_ft+' / '+v.ds_invert_ft+' ft; n='+v.culvert_n));
 const details=el('details');details.append(el('summary',tr('Section banks, Manning n, road and boundaries','断面岸站、糙率、路顶及边界')));
 const table=(headers,rows)=>{const t=el('table'),h=el('tr');for(const v of headers)h.append(el('th',v));t.append(h);for(const row of rows){const r=el('tr');for(const v of row)r.append(el('td',String(v)));t.append(r);}return t;};
 details.append(table([tr('River station','河站'),tr('Left / right bank (ft)','左 / 右岸站 (ft)'),tr('Manning n by start station','各起始站点的 Manning n'),tr('Ineffective areas','无效流区')],p.sections.map(s=>[s.rs,s.banks.join(' / '),s.manning.map(n=>n[0]+': '+n[1]).join('; '),s.ineffective_areas?tr('Present','有'):tr('None','无')])));
 const boundary=b=>b.type===0?tr('Unused for this regime','本流态不使用'):b.type===3?tr('Normal depth; slope = ','正常水深；坡度 = ')+b.slope:b.type===1?tr('Known stage ','已知水位 ')+b.stage_ft+' ft':tr('Type ','类型 ')+b.type;
 details.append(el('h3',tr('Profile boundaries','各工况边界')),table([tr('Profile','工况'),tr('Upstream','上游'),tr('Downstream','下游')],p.boundaries.map(b=>[p.profiles[b.profile_number-1]?.id||b.profile_number,boundary(b.upstream),boundary(b.downstream)])));
 for(const [side,rows] of Object.entries(p.expected_native.road_profiles)){const z=rows.map(v=>v[1]);details.append(el('p',(side==='upstream'?tr('Upstream road','上游侧路顶'):tr('Downstream road','下游侧路顶'))+': '+rows.length+tr(' points; elevation ',' 个点；高程 ')+Math.min(...z)+'–'+Math.max(...z)+' ft'));}
 details.append(el('p',tr('Road width: ','道路宽度：')+p.expected_native.road_width_ft+' ft'));
 const raw=el('details');raw.append(el('summary',tr('Exact extracted input record','精确提取记录')),el('pre',JSON.stringify({sections:p.sections,boundaries:p.boundaries,road:p.expected_native.road_profiles},null,2)));details.append(raw);box.append(details);
 for(const match of preview.prior_profile_matches)box.append(el('p',tr('Retained supplied flow: ','保留已填流量：')+match.original.id+' '+match.original.flow_cfs+' cfs → '+match.native_profile,'card'));
 if(preview.reconciliation_error)box.append(el('p',preview.reconciliation_error,'field-error'));
 box.append(el('p',tr('The native survey sections drive hydraulics. DEM and imagery provide mapped context; this is not DEM-only model reconstruction. All source profiles are retained.','原生测量断面用于水力计算，DEM 与航片提供地图背景；本路线不是仅凭 DEM 重建水力模型。保留来源的全部流量工况。')));
 const edit=(mapping,key,value)=>{const current=data.draft.native_review;(mapping?current.mapping:current)[key]=value;current.mapping.confirmed=false;const c=$('#native-mapping-confirmed');if(c)c.checked=false;const a=$('#native-approve-consent');if(a)a.checked=false;changed();};
 function field(target,key,en,cn,choices){const mapping=target===m,lab=el('label',tr(en,cn)),input=el(choices?'select':['source','basis'].includes(key)?'textarea':'input');input.id='native-'+key;lab.htmlFor=input.id;if(input.tagName==='TEXTAREA')input.rows=4;if(choices)for(const v of ['',...choices])input.append(new Option(v||tr('Select','请选择'),v));input.value=target[key]??'';input.oninput=()=>edit(mapping,key,input.value);box.append(lab,input);}
 for(const [key,en,cn] of [['title','Project title','项目标题'],['source','Hydraulic source and site applicability','水力资料来源及本站适用性'],['reviewer','Reviewer','审核人'],['vertical_datum','Native model elevation datum','原生模型高程基准']])field(r,key,en,cn);
 field(r,'native_length_unit','Native model foot convention','原生模型英尺定义',['international ft','US survey foot']);
 field(m,'horizontal_crs','Native geometry CRS (for example EPSG code from source)','原生模型平面坐标系（按来源填写 EPSG）');
 field(m,'dem_vertical_unit','DEM elevation unit','DEM 高程单位',['m','US survey foot','international foot']);field(m,'dem_vertical_datum','DEM elevation datum','DEM 高程基准');field(m,'basis','Coordinate system / metadata / site evidence','坐标系、元数据及本站对应依据');
 const t=data.terrain_setup,candidate=t?.metadata_candidate;
 box.append(el('p',tr('Acquired DEM: ','已获取 DEM：')+(t?.raster?.path||tr('Not available; run acquisition first.','未获取，请先下载地形。'))));
 if(candidate){const md=el('details');md.append(el('summary',tr('USGS metadata candidates and source locators','USGS 元数据候选及来源定位')),el('pre',JSON.stringify(candidate,null,2)));box.append(md);if(candidate.status==='CANDIDATE_REQUIRES_REVIEW')box.append(button(tr('Copy DEM metadata candidates for review','填入待审 DEM 元数据候选'),()=>{const current=data.draft.native_review.mapping;current.dem_vertical_unit=candidate.unit;current.dem_vertical_datum=candidate.datum;current.confirmed=false;changed();render();}));}
 const mapcheck=el('input');mapcheck.type='checkbox';mapcheck.id='native-mapping-confirmed';mapcheck.checked=m.confirmed===true;mapcheck.onchange=()=>{data.draft.native_review.mapping.confirmed=mapcheck.checked;changed();};const ml=el('label',undefined,'check');ml.append(mapcheck,el('span',tr('I checked the coordinate system, terrain/model datums and site correspondence.','我已核实坐标系、地形与模型高程基准及本站对应关系。')));box.append(ml);
 const approve=el('input');approve.type='checkbox';approve.id='native-approve-consent';const al=el('label',undefined,'check');al.append(approve,el('span',tr('Use these native hydraulic inputs instead of the manual geometry draft, retain prior evidence, and authorize conditional computation. This is not engineering acceptance.','使用上述原生水力输入替代手工几何草稿，保留此前证据，并授权条件性计算；这不是工程验收。')));box.append(al);
 box.append(button(tr('Save native review draft','保存原生审核草稿'),save),button(tr('Confirm native inputs and continue','确认原生输入并继续'),()=>geometryTask(tr('Checking and recording your approval…','正在检查并记录审核…'),async()=>{
  if(!approve.checked)throw Error(tr('Confirm conditional use of the native inputs.','请确认按条件使用原生输入。'));
  const result=await request('native-approve',{revision:data.draft.revision,confirmed:true});if(result.status==='APPLIED')done(result.status,result.project);
 }),'primary'));
}
