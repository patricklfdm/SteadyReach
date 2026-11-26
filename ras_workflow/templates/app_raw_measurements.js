'use strict';
function rawPointMap(parent,preview){
 const points=preview.rows.filter(r=>r.xy),cuts=preview.cuts;
 if(!points.length||!cuts.length)return;
 const coords=[...points.map(r=>r.xy),...cuts.flatMap(c=>c.xy)];
 const xs=coords.map(p=>p[0]),ys=coords.map(p=>p[1]);
 const xmin=Math.min(...xs),ymin=Math.min(...ys);
 const scale=Math.min(566/(Math.max(...xs)-xmin||1),266/(Math.max(...ys)-ymin||1));
 const xy=p=>[16+(p[0]-xmin)*scale,284-(p[1]-ymin)*scale];
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 600 300');svg.setAttribute('width','100%');
 svg.setAttribute('role','img');svg.setAttribute('aria-label',tr('Model sections and source rows','模型断面与测量原始行'));parent.append(svg);
 for(const c of cuts)svgEl(svg,'polyline',{points:c.xy.map(p=>xy(p).join(',')).join(' '),fill:'none',stroke:'#667986','stroke-width':1.3});
 for(const p of points){const [cx,cy]=xy(p.xy),node=svgEl(svg,'circle',{cx,cy,r:4,fill:p.issues.length?'#a84422':p.role==='outlet'?'#925610':'#006e81'});
 svgEl(node,'title',{}).textContent='RS '+p.rs+' · '+tr('source row ','原始行 ')+p.line;}
 parent.append(el('small',tr('Section lines · teal = interior · ochre = outlet · red = check source','断面线 · 青色为内点 · 棕色为出口 · 红色需核对原件')));
}
function renderRawMeasurements(parent,edition){
 const box=details(parent,'Import an original measurement table','导入原始测量表');box.id='raw-measurements';
 const host=el('div');host.setAttribute('aria-live','polite');box.append(host);
 const call=(action,extra={})=>api('raw-'+action,{id:edition.id,revision:current.revision,...extra});
 box.append(button('Start from my field table','从我的测量表开始',async()=>{
  await save();const state=await call('inspect');host.replaceChildren();
  const invert=edition.model_type!=='river';
  host.append(el('p',tr('Model reference for comparison: ','模型参考基准供核对：')+[state.crs,state.datum].filter(Boolean).join(' · ')));
  if(state.stations.length){
   table(host,[tr('Registered gage','已登记测站'),'RS',tr('Distance to outlet','至出口距离'),tr('Use','用途')],
    state.stations.map(s=>[s.station,s.matched_rs??'—',s.distance_to_boundary_center_m==null?'—':s.distance_to_boundary_center_m+' m',
     [s.datum||'—',s.datum_check==='CONVERSION_REQUIRED'?tr('Document the datum conversion','需基准转换依据'):'',
      s.transfer_required?tr('Context until event transfer is documented','须有同事件传递依据，当前仅供背景'):tr('Check event and gage zero','核对事件与水尺零点')].filter(Boolean).join(' · ')]));
  }
  if(invert)for(const f of state.invert_fields)host.append(el('p',tr(f.label.en,f.label.zh)+' · '+(f.value??'—')+' ft · '+(f.classification||tr('Missing','缺失'))));
  host.append(el('p',invert?tr('Supply group and separate inlet/outlet elevations, or group, end and elevation. Leave unmeasured ends blank.','填写涵孔组及进、出口两列涵底，或使用组号、端别、高程三列。未测端留空。'):tr('Compare points with the located sections. Before computing, use only the directly surveyed outlet. After computing, return the unused interior observations in a revision.','和已定位断面对照。计算前可采用出口原位测点，计算后再将未用于调参的内点回传至修订版。')));
  const file=field(host,'raw-file',invert?'Original UTF-8 CSV / TSV':'Original CSV / TSV or USGS field-visit GeoJSON',invert?'原始 UTF-8 CSV／制表符表':'原始 CSV／制表符表或 USGS 测验 GeoJSON','','file');file.accept=invert?'.csv,.tsv,.txt':'.csv,.tsv,.txt,.json,.geojson';
  const mode=invert?null:field(host,'raw-mode','What the elevation column measures','高程列的测量含义','stage','select',[['stage','Absolute water elevation','绝对水面高程'],['gage','Relative gage reading','相对水尺读数']]);
  const editor=el('div');file.onchange=()=>editor.replaceChildren();if(mode)mode.onchange=()=>editor.replaceChildren();
  host.append(button('Read columns and suggest matches','读取表头并建议匹配',async()=>{
   const f=file.files[0];if(!f||f.size>2000000)throw Error(tr('Select a table under 2 MB','请选择 2 MB 以内的测量表'));
   const [doc]=await encodeFiles([f]),input={...doc,mode:mode?.value||'invert'};
   const found=await call('columns',input);editor.replaceChildren();
   editor.append(el('p',found.count+tr(' source rows. Confirm units, reference systems and event against the field original. Model defaults are suggestions.',' 个原始数据行。请按测量原件确认单位、基准及事件，模型预填项仅供参考。')));
   for(const r of found.references)editor.append(el('p',r.file+' · '+Object.values(r.values).join(' · ')));
   const mapping=details(editor,'Review column assignments','核对列名匹配'),cols={},options=[['','Unassigned','未指定'],...found.headers.map(h=>[h,h,h])];
   const labels={x:['Easting / X','横坐标'],y:['Northing / Y','纵坐标'],level:['Measured elevation or reading','水位／读数／高程'],group:['Group number (1-based)','涵孔组号（从 1 起）'],end:['Inlet / outlet','进出口端别'],level_in:['Inlet invert','进口涵底'],level_out:['Outlet invert','出口涵底'],profile:['Profile','工况'],event:['Event','事件'],date:['Date','日期'],flow:['Discharge','流量'],flow_unit:['Flow unit','流量单位'],unit:['Elevation unit','高程单位'],crs:['Horizontal CRS','平面坐标系'],datum:['Vertical datum','高程基准'],uncertainty:['Vertical uncertainty','垂直不确定度'],station:['Gage ID','水尺站号']};
   const keys=invert?['group','end','level','level_in','level_out','unit','datum']:['x','y','level','profile','event','date','flow','flow_unit','unit','crs','datum','uncertainty','station'];
   const out=el('div'),invalidate=()=>out.replaceChildren();
   for(const k of keys)cols[k]=field(mapping,'raw-column-'+k,...labels[k],found.mapping[k]||'','select',options,invalidate);
   if(found.gage_json){mapping.hidden=true;editor.append(el('p',tr('USGS mean gage heights. Record numbers are 1-based GeoJSON feature positions; flow is paired by station and visit.','USGS 实测相对水尺读数。编号为从 1 起的 GeoJSON 要素序号，流量按站号及测次配对。')));}
   const settings={},grid=el('div',undefined,'grid');editor.append(grid);
   for(const k of (invert?['unit','datum']:['profile','event','date','flow','flow_unit','unit','crs','datum','uncertainty'])){
    const opts={profile:state.profiles.map(p=>[p.id,p.id,p.id]),unit:[['ft','International ft','国际英尺'],['m','Metres','米'],['us_survey_ft','US survey ft','美国测量英尺']],flow_unit:[['cfs','cfs','cfs'],['m3/s','m³/s','m³/s']]}[k];
    settings[k]=field(grid,'raw-meta-'+k,...labels[k],found.suggestions[k]??'',opts?'select':'text',opts?[['','Choose','请选择'],...opts]:null,invalidate);
   }
   if(!invert)editor.append(el('small',tr('Source columns take precedence over these defaults. The flow must match the selected model profile.','原表非空列优先于此处填写的信息。事件流量须与模型工况相符。')));
   editor.append(button('Locate and preview source rows','定位并预览原始行',async()=>{
    const pick=obj=>Object.fromEntries(Object.entries(obj).map(([k,v])=>[k,v.value]));
    const body={...input,settings:pick(settings),columns:pick(cols)},p=await call('preview',body);
    out.replaceChildren();out.append(el('p',p.raw_count+tr(' rows · eligible source rows: ',' 行 · 本次可选行：')+new Set(p.selectable).size+' · '+tr('outside section centers: ','断面中心范围外：')+p.outside_count));
    if(p.missing.length)out.append(el('p',tr('Still need survey evidence: ','仍需测量依据：')+p.missing.join(', '),'warning'));
    if(!invert)rawPointMap(out,p);
    const choices=new Map(),reasons={DATUM_MISMATCH:'Datum mismatch / 高程基准不一致',UNIT_REQUIRED:'Supply source units / 缺测量单位',EVENT_REQUIRED:'Supply event and date / 缺事件日期',DISCHARGE_MISMATCH:'Check event flow / 核对事件流量',GAGE_REQUIRES_REGISTER:'Check gage zero, datum and site transfer in the register / 核对水尺零点、基准和异地传递',DUPLICATE_POINT:'Repeated coordinates / 坐标重复',DUPLICATE_TARGET:'Repeated invert / 同端重复',CHECK_REPEATED_ROWS:'Check duplicates / 核对重复行',AMBIGUOUS_NEAREST:'Tied nearest points / 多行同距',GROUP_OR_END_REQUIRED:'Identify group and end / 需组号及端别'};
   const tableRows=p.rows.map(r=>[r.line,r.target||('RS '+(r.rs??'—')),r.value??'—',r.unit||'—',r.meta?.date||'—',r.meta?.flow?String(r.meta.flow)+' '+r.meta.flow_unit:'—',r.issues.map(i=>reasons[i]||i).join(' · ')||({interior:tr('Interior','内点'),outlet:tr('Outlet; excluded from scoring','出口，不计入评分'),invert:tr('Invert','涵底')}[r.role]||'—'),(r.nearby_lines||[]).join(', ')]);
    table(out,[tr('Record','原始行／要素'),tr('Location','位置'),tr('Value','读数'),tr('Unit','单位'),tr('Date','日期'),tr('Event flow','事件流量'),tr('Use or issue','用途或问题'),tr('Other nearby lines','其他邻近行')],tableRows);
    if(!p.selectable.length){out.append(el('p',tr('Review the source, column assignments or evidence register. No input changed.','请核对原件、列名或资料清单。本次预览未改动模型。')));return;}
    for(const n of new Set(p.selectable)){const cb=field(out,'raw-pick-'+n,'Use source row '+n,'采用原始行 '+n,'','checkbox');cb.checked=true;choices.set(n,cb);}
    const ack=field(out,'raw-ack',p.role==='interior'?'I confirm these interior points were held out from calibration and boundary inputs':'I verified the selected rows and their metadata',p.role==='interior'?'确认这些内点未用于设边界或调参':'已核对所选行、单位和基准','','checkbox');
    const uncertain=p.role==='outlet'&&p.rows.some(r=>p.selectable.includes(r.line)&&!r.meta.uncertainty);
    const conditional=uncertain?field(out,'raw-conditional','Use the outlet with unknown vertical accuracy for conditional screening','明确同意以未知垂直精度的出口作条件性初筛','','checkbox'):null;
    out.append(button(state.computed?'Create editable revision':'Save selected measurements',state.computed?'建立可编辑修订版':'保存所选实测输入',async()=>{
     if(!ack.checked)throw Error(tr('Confirm the source rows and intended use first','请先核对并确认所选原始行和用途'));
     const result=await call('apply',{...body,token:p.token,lines:[...choices].filter(([,cb])=>cb.checked).map(([n])=>n),confirmed:true,independent:p.role==='interior',conditional:!!conditional?.checked});
     await open(result.id);notify(tr('Measurements saved. Review affected inputs before running.','实测资料已保存，请核对受影响的输入后再计算。'));
    },'primary'));
   }),out);
  }),editor);
 }));
}
