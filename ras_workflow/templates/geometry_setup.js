'use strict';
// Plain form inputs; generated files and evidence binding stay on the server.
function geometryFormInput(parent,key,en,zh,value,kind='text',onchange){
 const label=el('label',tr(en,zh)),input=el(kind==='textarea'?'textarea':'input');input.id='geometry-'+key;label.htmlFor=input.id;
 if(kind!=='textarea'){input.type=kind;if(kind==='number')input.step='any';}else input.rows=3;
 input.value=value??'';input.oninput=()=>onchange(kind==='number'?(input.value===''?null:Number(input.value)):input.value);parent.append(label,input);return input;
}
async function geometryTask(message,action){
 await operation(async()=>{notice(message);const screen=$('#screen');screen.inert=true;try{await action();notice('');}finally{screen.inert=false;}});
}
function geometrySetup(screen){
 const t=data.terrain_setup,box=el('details');box.id='geometry-setup';box.append(el('summary',tr('Generate / resample sections from DEM','从 DEM 生成 / 重采样断面')));const body=el('div',undefined,'body');box.append(body);screen.append(box);
 if(t?.status!=='READY'){body.append(el('p',tr('Run the workflow to acquire terrain first. ','先运行工作流获取地形。')+(t?.reason||'')));return;}
 body.append(el('p',tr('DEM coordinate system: ','DEM 坐标系：')+t.crs+' · '+t.horizontal_unit),el('p',tr('Confirm metadata and ordered exterior anchors. Screening parameters below are editable proposals, not measured site dimensions. New sections replace only this draft and require bank/length/structure-face review.','确认元数据及按流向排列的外部锚点。下面的筛查参数仅是可修改的建议，不是实测尺寸。生成只替换当前草稿，仍须审核岸站、流程长度及结构外侧断面。')));
 data.draft.geometry_setup_draft??={};const form=data.draft.geometry_setup_draft;form.setup??={mode:t.can_resample?'resample':'alignment',unit:t.vertical_unit||'',datum:t.vertical_datum||'',...t.defaults};const f=form.setup;
 const update=(k,v)=>{f[k]=v;data.draft.geometry_setup_draft.setup=f;changed();};const mode=el('select');mode.id='geometry-mode';mode.append(new Option(tr('Generate along exterior reaches','沿外部河段生成'),'alignment'));if(t.can_resample)mode.append(new Option(tr('Resample existing cutlines','重采样现有断面线'),'resample'));mode.value=f.mode;body.append(el('label',tr('Generation mode','生成方式')),mode);
 const unit=el('select');unit.id='geometry-unit';for(const v of ['','m','US survey foot','international foot'])unit.append(new Option(v||tr('Confirm vertical unit','确认高程单位'),v));unit.value=f.unit;unit.onchange=()=>update('unit',unit.value);body.append(el('label',tr('DEM vertical unit','DEM 高程单位')),unit);
 const datumInput=geometryFormInput(body,'datum','Vertical datum','高程基准',f.datum,'text',v=>update('datum',v));
 geometryFormInput(body,'metadata-basis','Metadata interpretation / source page','元数据解释 / 来源页码',f.metadata_basis,'textarea',v=>update('metadata_basis',v));
 const pathsInput=geometryFormInput(body,'metadata-paths','Metadata / anchor evidence paths (workspace-relative, one per line)','元数据 / 锚点证据路径（相对项目根目录，每行一个）',f.paths,'textarea',v=>update('paths',v));
 const candidate=t.metadata_candidate;
 if(candidate){
  const details=el('details');details.id='terrain-metadata-candidate';details.append(el('summary',tr('Downloaded USGS metadata — review before using','已下载 USGS 元数据——使用前复核')));
  for(const p of candidate.products||[]){details.append(el('p',p.title||p.product_id),el('p',tr('Elevation unit / datum: ','高程单位 / 基准：')+(p.unit||'?')+' / '+(p.datum||'?')));for(const k of ['vertical_unit','vertical_datum'])for(const e of [...(p.evidence[k].evidence||[]),...(p.evidence[k].narrative_evidence||[])])details.append(el('p',e.locator+': '+(e.quote||e.value)));}
  for(const issue of candidate.review_items||[])details.append(el('p',issue));
  if(candidate.status==='CANDIDATE_REQUIRES_REVIEW'){
   const use=el('button',tr('Copy candidate units, datum and source paths','填入候选单位、基准及来源路径'));use.type='button';use.id='use-terrain-metadata';
   use.onclick=()=>{unit.value=candidate.unit;datumInput.value=candidate.datum;pathsInput.value=candidate.source_paths.join('\n');update('unit',candidate.unit);update('datum',candidate.datum);update('paths',pathsInput.value);notice(tr('Candidate copied. Review the evidence and enter your interpretation and reviewer name before generating.','候选值已填入。请复核证据，填写解释和复核人后再生成。'));};details.append(use);
  }
  body.append(details);
 }
 geometryFormInput(body,'reviewer','Reviewer','复核人',f.reviewer||data.draft.reviewer,'text',v=>update('reviewer',v));
 geometryFormInput(body,'basis','Generation purpose and geometry evidence','生成目的及几何依据',f.basis,'textarea',v=>update('basis',v));
 const alignment=el('div');body.append(alignment);
 alignment.append(el('p',tr('Enter X, Y per line in the displayed projected CRS, ordered upstream to downstream. Supply separate reaches before and after the crossing; do not route through buried culverts.','按显示的投影坐标系，每行输入 X, Y，按上游到下游排序。涵洞前后应分成独立外部河段，不穿过埋藏涵洞寻路。')));
 geometryFormInput(alignment,'upstream','Upstream exterior reach anchors','上游外部河段锚点',f.upstream,'textarea',v=>update('upstream',v));
 geometryFormInput(alignment,'downstream','Downstream exterior reach anchors','下游外部河段锚点',f.downstream,'textarea',v=>update('downstream',v));
 geometryAnchorMap(alignment,f,update);
 geometryFormInput(alignment,'direction','Flow direction evidence','流向依据',f.direction,'textarea',v=>update('direction',v));
 const orientation=el('select');orientation.id='geometry-section-direction';orientation.append(new Option(tr('Local terrain-route tangent','局部地形路径切线'),'local_tangent'),new Option(tr('Parallel sections across this exterior reach','本段外部河段的平行断面'),'external_reach_chord'));orientation.value=f.section_direction||'local_tangent';orientation.onchange=()=>update('section_direction',orientation.value);alignment.append(el('label',tr('Section orientation proposal','断面方向候选方法')),orientation,el('p',tr('Parallel sections can reduce crossings caused by grid zigzags. Use only for a locally straight exterior reach; review floodplain coverage and each section. This does not approve banks or eliminate hydraulic QA.','平行断面可减少网格折线造成的相交，仅适合局部顺直外部河段。仍须逐断面复核漫滩覆盖及岸站，不能据此关闭水力 QA。')));
 for(const [k,en,zh]of [['section_width_ft','Section width (ft)','断面宽度（ft）'],['section_spacing_ft','Section spacing (ft)','断面间距（ft）'],['sampling_ft','Sampling interval (ft)','采样间隔（ft）'],['grid_ft','Route grid (ft)','寻路网格（ft）'],['corridor_half_width_ft','Corridor half-width (ft)','走廊半宽（ft）'],['height_scale_ft','Relative elevation scale (ft)','相对高程尺度（ft）'],['elevation_weight','Low-terrain preference weight','低地偏好权重'],['uphill_weight','Uphill penalty weight','爬坡惩罚权重']])geometryFormInput(alignment,k,en,zh,f[k],'number',v=>update(k,v));
 alignment.hidden=mode.value!=='alignment';mode.onchange=()=>{update('mode',mode.value);alignment.hidden=mode.value!=='alignment';};
 const replace=el('input');replace.type='checkbox';replace.id='geometry-replace';const consent=el('label',undefined,'check');consent.append(replace,el('span',tr('Replace draft sections and invalidate their previous reviews; retain history.','替换草稿断面并使原复核失效，历史记录保留。')));if(t.can_resample)body.append(consent);
 body.append(button(tr('Generate candidate sections','生成候选断面'),()=>geometryTask(tr('Sampling terrain and checking sections…','正在采样地形并检查断面…'),async()=>{
  const parameters=Object.fromEntries(Object.keys(t.defaults).map(k=>[k,f[k]??t.defaults[k]]));
  const external_reaches=['upstream','downstream'].filter(k=>String(f[k]||'').trim()).map(id=>({id,anchors_xy:parse({kind:'matrix'},f[id])}));
  applyResponse(await request('geometry-generate',{revision:data.draft.revision,configuration:{mode:mode.value,reviewer:f.reviewer||data.draft.reviewer,basis:f.basis,replace_existing:replace.checked,vertical_review:{unit:f.unit,datum:f.datum,basis:f.metadata_basis,source_paths:String(f.paths||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean)},parameters,external_reaches,direction_basis:f.direction}}));
 }),'primary'));
}
function geometryAnchorMap(parent,form,update){
 const box=el('details');box.append(el('summary',tr('Pick anchors on the DEM map','在 DEM 地图上选择锚点')));parent.append(box);let map=null,mode=null;const controls=el('div'),canvas=el('div'),hint=el('p');box.append(el('p',tr('Choose a mode, then click upstream to downstream. The crossing marker is a review aid only; it does not set buried inverts or culvert length. Save the draft and provide the flow-direction evidence above.','先选择模式，再按上游至下游顺序点选。涵洞标记仅辅助复核，不确定埋藏涵底或涵长。保存草稿并补充上面的流向依据。')),controls,hint,canvas);
 const picks={};for(const [key,en,zh]of [['upstream','Upstream anchors','上游锚点'],['downstream','Downstream anchors','下游锚点'],['crossing','Crossing marker','涵洞标记']]){const b=button(tr(en,zh),()=>{mode=mode===key?null:key;draw();});b.id='anchor-mode-'+key;b.setAttribute('aria-pressed','false');controls.append(b);picks[key]=b;}
 const parsePoints=v=>String(v||'').split(/\r?\n/).map(s=>s.trim().split(/[\s,]+/).map(Number)).filter(p=>p.length===2&&p.every(Number.isFinite));
 async function load(bounds){await geometryTask(tr('Loading DEM view…','正在加载 DEM 视图…'),async()=>{map=await request('geometry-map',bounds?{bounds}:{});draw();});}
 controls.append(button(tr('Load / reset map','加载 / 重置地图'),()=>load()),button(tr('Zoom in','放大'),()=>zoom(.5)),button(tr('Zoom out','缩小'),()=>zoom(2)),button(tr('Undo selected anchor','撤销所选模式的上一点'),()=>{if(!mode)return;const p=parsePoints(form[mode]);p.pop();update(mode,p.map(p=>p.join(', ')).join('\n'));sync();draw();}));
 function zoom(factor){if(!map)return;const b=map.bounds,c=[(b[0]+b[2])/2,(b[1]+b[3])/2],r=(b[2]-b[0])*factor/2;return load([c[0]-r,c[1]-r,c[0]+r,c[1]+r]);}
 function sync(){for(const k of ['upstream','downstream']){const input=document.getElementById('geometry-'+k);if(input)input.value=form[k]||'';}}
 function draw(){for(const [k,b]of Object.entries(picks)){b.setAttribute('aria-pressed',String(k===mode));b.classList.toggle('primary',k===mode);}hint.textContent=mode?tr('Selecting: ','当前选择：')+picks[mode].textContent:tr('Selection off','未开启选择');canvas.replaceChildren();if(!map)return;
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 650 650');svg.setAttribute('aria-label',tr('DEM anchor selection map','DEM 锚点选择地图'));svg.style.width='100%';svg.style.touchAction='none';canvas.append(svg);
  const add=(tag,attrs)=>{const n=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);svg.append(n);return n;};const [x0,y0,x1,y1]=map.bounds,toPixel=p=>[(p[0]-x0)/(x1-x0)*650,(y1-p[1])/(y1-y0)*650];
  add('image',{href:'data:image/png;base64,'+map.background,width:650,height:650});for(const cut of map.sections)add('polyline',{points:cut.map(toPixel).map(p=>p.join(',')).join(' '),fill:'none',stroke:'#9956c7','stroke-width':1});
  for(const [key,color]of [['upstream','#006fce'],['downstream','#d44b00'],['crossing','#d40062']]){const points=parsePoints(form[key]);add('polyline',{points:points.map(toPixel).map(p=>p.join(',')).join(' '),fill:'none',stroke:color,'stroke-width':3});points.forEach((p,i)=>{const [x,y]=toPixel(p);add('circle',{cx:x,cy:y,r:5,fill:color,stroke:'white'});add('text',{x:x+7,y:y-7,fill:color}).textContent=(key==='crossing'?'C':key==='upstream'?'U':'D')+(i+1);});}
  add('text',{x:580,y:25,fill:'#111'}).textContent='Grid N ↑';add('line',{x1:20,x2:150,y1:625,y2:625,stroke:'#111','stroke-width':3});add('text',{x:20,y:613,fill:'#111'}).textContent=((x1-x0)*map.unit_to_m/5).toFixed(1)+' m';
  svg.addEventListener('click',event=>{if(!mode)return;const pt=svg.createSVGPoint();pt.x=event.clientX;pt.y=event.clientY;const p=pt.matrixTransform(svg.getScreenCTM().inverse());if(p.x<0||p.x>650||p.y<0||p.y>650)return;const xy=[x0+p.x/650*(x1-x0),y1-p.y/650*(y1-y0)].map(v=>Number(v.toFixed(3)));const rows=mode==='crossing'?[]:parsePoints(form[mode]);rows.push(xy);update(mode,rows.map(p=>p.join(', ')).join('\n'));sync();draw();});
  canvas.append(el('p',map.crs+' · '+tr('Blue U: upstream; orange D: downstream; pink C: review marker. Coordinates are draft selections.','蓝色 U：上游；橙色 D：下游；粉色 C：待核对标记。坐标仅为草稿点选。')));
 }
 draw();
}
function geometryEditPanel(parent,index,fingerprint,row,reviewer,basis){
 const box=el('details');box.id='geometry-edit';box.append(el('summary',tr('Adjust cutline and preview DEM samples','调整断面线并预览 DEM 重采样')));const body=el('div',undefined,'body');box.append(body);parent.append(box);
 body.append(el('p',tr('Preview rotation, translation or width. Apply clears bank reviews and affected reach lengths; moving a crossing-face section also clears barrel centres and road stations. Narrowing may remove floodplain conveyance.','可预览旋转、平移及宽度变化。应用后须重新复核岸站和受影响流程长度；移动涵口断面还会清空涵孔横向中心和路顶站距。缩窄可能遗漏漫滩过流。')));
 data.draft.geometry_setup_draft??={};const drafts=data.draft.geometry_setup_draft;drafts.edits??={};drafts.edits[fingerprint]??={rotation_deg:0,shift_east_ft:0,shift_north_ft:0,width_ft:null,sampling_ft:1};const params=drafts.edits[fingerprint];let preview=null;const inputs={};
 for(const [k,en,zh]of [['rotation_deg','Rotation counterclockwise (degrees)','逆时针旋转（度）'],['shift_east_ft','Shift east (ft)','向东平移（ft）'],['shift_north_ft','Shift north (ft)','向北平移（ft）'],['width_ft','Width (ft; blank keeps current cut length)','宽度（ft；留空保持原断面线长度）'],['sampling_ft','Sampling interval (ft)','采样间隔（ft）']])inputs[k]=geometryFormInput(body,'section-'+k,en,zh,params[k],'number',v=>{params[k]=v;data.draft.geometry_setup_draft.edits[fingerprint]=params;preview=null;changed();});
 const alternatives=el('div'),result=el('div');body.append(button(tr('Find fewer-crossing alternatives','寻找减少相交的候选'),()=>geometryTask(tr('Checking layout alternatives…','正在检查布局候选…'),async()=>{
  const r=await request('geometry-alternatives',{index});alternatives.replaceChildren(el('p',tr('Geometric alternatives only; preview and review their hydraulic coverage.','仅为几何候选，仍需预览并复核过流覆盖。')));if(!r.alternatives.length)alternatives.append(el('p',tr('No improvement found in the limited rotation/width search. Adjust manually.','有限旋转/宽度搜索未找到改善方案，请手动调整。')));
  for(const a of r.alternatives)alternatives.append(button(tr('Load candidate: ','载入候选：')+a.parameters.rotation_deg+'° / '+a.parameters.width_ft.toFixed(1)+' ft · '+tr('remaining issues ','剩余问题 ')+a.remaining_spatial_issues,()=>{Object.assign(params,a.parameters);for(const k of Object.keys(inputs))inputs[k].value=params[k]??'';preview=null;data.draft.geometry_setup_draft.edits[fingerprint]=params;changed();}));
 })),alternatives,button(tr('Preview resampling','预览重采样'),()=>geometryTask(tr('Sampling the current cutline from DEM…','正在从 DEM 采样当前断面线…'),async()=>{
  const parameters=Object.fromEntries(Object.entries(params).filter(([,v])=>v!==null));const r=await request('geometry-preview',{revision:data.draft.revision,index,fingerprint,parameters});preview=r.preview;
  result.replaceChildren(el('p',tr('Preview only. Samples: ','仅预览。采样点：')+preview.after.station_ft.length+' · NoData '+preview.nodata_samples+' · '+tr('spatial issues ','空间问题 ')+preview.spatial_issues.length));
  geometryPreviewPlot(result,preview);
  result.append(button(tr('Apply preview to draft','将预览应用到草稿'),()=>geometryTask(tr('Saving the reviewed geometry change…','正在保存审核后的几何修改…'),async()=>{if(!preview)throw Error(tr('Parameters changed; preview again.','参数已改变，请重新预览。'));applyResponse(await request('geometry-apply',{revision:data.draft.revision,preview_id:preview.id,reviewer:reviewer.value,basis:basis.value}));}),'primary'));
 })),result);
}
function geometryPreviewPlot(parent,v){
 for(const kind of ['layout','profile']){
  const points=r=>kind==='layout'?r.cutline_xy:r.station_ft.map((x,i)=>[x,r.elevation_ft[i]]);const all=[...points(v.before),...points(v.after)].filter(p=>p.every(Number.isFinite));if(!all.length)continue;
  const low=[0,1].map(i=>Math.min(...all.map(p=>p[i]))),span=[0,1].map(i=>Math.max(Math.max(...all.map(p=>p[i]))-low[i],1));
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 700 230');svg.setAttribute('role','img');svg.setAttribute('aria-label',tr('Before and after '+kind,'修改前后'+(kind==='layout'?'布局':'剖面')));svg.style.width='100%';
  const project=p=>[25+(p[0]-low[0])/span[0]*650,195-(p[1]-low[1])/span[1]*170].join(',');
  for(const [row,color]of [[v.before,'#888'],[v.after,'#147b6f']]){let segment=[];const flush=()=>{if(segment.length){const n=document.createElementNS(svg.namespaceURI,'polyline');n.setAttribute('points',segment.join(' '));n.setAttribute('fill','none');n.setAttribute('stroke',color);n.setAttribute('stroke-width','2');svg.append(n);}segment=[];};for(const p of points(row)){if(p.every(Number.isFinite))segment.push(project(p));else flush();}flush();}
  parent.append(el('p',tr((kind==='layout'?'Layout (independent axis scales)':'Profile (international ft)')+' · gray: before; green: candidate',(kind==='layout'?'布局（两轴独立缩放）':'剖面（国际英尺）')+' · 灰色：原断面；绿色：候选')),svg);
 }
}
