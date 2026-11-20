'use strict';
function renderFloodplain(parent){
 const box=details(parent,'Inspect floodplain and boundary response by section','按断面查看漫滩和边界影响');
 box.id='qa-tool-floodplain';
 const out=el('div');box.append(out);let started=false;
 const id=current.id,hash=current.summary.sha256;let requested=null;
 box.addEventListener('steadyreach-inspect-floodplain',event=>{
  requested={rs:String(event.detail.rs),geometry:event.detail.geometry};
  const station=out.querySelector('#ctx-station'),version=out.querySelector('#ctx-version');
  if(station&&Array.from(station.options).some(o=>o.value===requested.rs)){
   if(version&&Array.from(version.options).some(o=>o.value===requested.geometry))version.value=requested.geometry;
   station.value=requested.rs;station.onchange();requested=null;
  }
 });
 async function load(fetchLayers=false){
  out.setAttribute('aria-busy','true');
  const status=el('p',fetchLayers?tr('Loading public road and levee lines…','正在获取公开道路和堤线…'):tr('Reading verified section results and imagery…','正在读取已核验的断面和航片…'),'status');
  out.prepend(status);
  try{
   const data=await api('qa-floodplain',{id,summary_hash:hash,load_layers:fetchLayers});
   if(!out.isConnected||current?.id!==id||current.summary?.sha256!==hash)return;
   const prior={rs:out.querySelector('[data-context-station]')?.value,geometry:out.querySelector('#ctx-version')?.value,profile:out.querySelector('#ctx-profile')?.value,zoom:out.querySelector('#ctx-extent')?.value};
   out.replaceChildren();renderFloodplainView(out,data,{...prior,...requested});requested=null;
   if(!fetchLayers&&data.layers.some(s=>s.status==='NOT_LOADED')){await load(true);return;}
   if(data.layers.some(s=>s.status==='NOT_LOADED'||s.status==='UNAVAILABLE')){
    out.append(button('Load or retry public road and levee layers','获取或重试公开道路及堤线',()=>load(true)));
   }
  }catch(e){if(out.isConnected){out.replaceChildren(el('p',e.message,'warning'),button('Retry section context','重试断面联动图',()=>load(fetchLayers)));}}
  finally{out.removeAttribute('aria-busy');}
 }
 box.parentElement.addEventListener('toggle',()=>{if(box.parentElement.open&&!started){started=true;void load();}});
}

function renderFloodplainView(parent,data,prior){
 const names=Object.keys(data.frames),base=data.frames.baseline;
 const format=(n,d=2)=>Number.isFinite(n)?n.toFixed(d):'—';
 const options=list=>list.map(v=>[v,v,v]);
 const controls=el('div',undefined,'grid');parent.append(controls);
 const profiles=[...new Set(base.map(r=>r.profile))];
 const profile=field(controls,'ctx-profile','Profile','工况',profiles[0],'select',options(profiles));
 const revision=field(controls,'ctx-version','Geometry','几何版本','baseline','select',names.map(n=>[n,riverVariantName(n),riverVariantName(n)]));
 const select=field(controls,'ctx-station','River station','断面 RS','','select',[]);select.dataset.contextStation='yes';
 const zoom=field(controls,'ctx-extent','Map extent','地图范围','local','select',[['local','Selected section and neighbors','当前和相邻断面'],['all','Whole reach','全河段']]);
 const stage=el('div');parent.append(stage);
 const labels=el('p',undefined,'muted');
 const layerStatus=s=>({AVAILABLE:tr('loaded','已载入'),NO_FEATURES_RETURNED:tr('no records returned in this area','查询范围内无返回记录'),NOT_LOADED:tr('not loaded','尚未载入'),UNAVAILABLE:tr('unavailable','不可用'),EXTENT_UNSUPPORTED:tr('extent unsupported','范围超出支持')})[s]||s;
 labels.textContent=data.layers.map(l=>(l.kind==='levees'?'USACE NLD':l.kind.replace('roads_','Census TIGER '))+' · '+layerStatus(l.status)+(l.lines.length?' ('+l.lines.length+')':'')).join(' | ');
 parent.append(labels,el('p',tr('Road and levee lines show mapped locations. Inspect crest levels, openings and continuity before inferring a barrier. Blank coverage leaves these questions open.','道路及堤线标示已收录的位置。判定是否挡水需核实堤顶高程、开口及连通性，图层空白时仍需核查。'),'muted'));
 for(const e of data.errors)parent.append(el('p',e,'warning'));
 function variants(n){return data.frames[n].filter(r=>r.profile===profile.value);}
 function reset(){
  const rows=variants('baseline');const old=prior?.rs||select.value;prior=null;
  select.replaceChildren();
  for(const r of rows){const o=el('option','RS '+r.rs);o.value=r.rs;select.append(o);}
  const newly=variants('rotated' in data.frames?'rotated':'baseline').find(r=>{const a=rows.find(b=>b.rs===r.rs);return a&&((r.left_excess_ft>0&&a.left_excess_ft===0)||(r.right_excess_ft>0&&a.right_excess_ft===0));});
  const tested=data.boundaries.filter(c=>c.profile===profile.value).flatMap(c=>Object.entries(c.by_rs)).filter(v=>Number.isFinite(v[1])).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1]));
  select.value=rows.some(r=>r.rs===old)?old:(newly?.rs||tested[0]?.[0]||rows[0].rs);paint();
 }
 function paint(){
  const rows=variants(revision.value),r=rows.find(row=>row.rs===select.value);stage.replaceChildren();if(!r)return;
  const pair=el('div',undefined,'section-context-grid');stage.append(pair);
  const map=el('div'),profilePanel=el('div');pair.append(map,profilePanel);
  map.append(el('h3',tr('Imagery and section alignment','航片与断面位置')+' · RS '+r.rs));
  plotMap(map,r,rows);
  profilePanel.append(el('h3',tr('Native ground and water level','原生地面与计算水位')+' · RS '+r.rs));atlasSectionPlot(profilePanel,r);
  stage.append(el('h3',tr('How the floodplain carries flow','漫滩如何分担流量')+' · RS '+r.rs));
  table(stage,[tr('Geometry','几何'),tr('Water level (ft)','水位（ft）'),tr('Left / right share (%)','左／右漫滩占比（%）'),tr('Left / right end exceedance (ft)','左／右端过水深（ft）')],names.map(n=>{
   const a=variants(n).find(v=>v.rs===r.rs);return a?[riverVariantName(n),format(a.wse_ft,3),a.ob_percent.map(v=>format(v)).join(' / '),[a.left_excess_ft,a.right_excess_ft].map(v=>format(v,3)).join(' / ')]:[riverVariantName(n),'—','—','—'];
  }));
  const boundary=data.boundaries.filter(c=>c.profile===profile.value);
  stage.append(el('h3',tr('Boundary influence along the original reach','原模型的沿程边界影响')));
  if(!boundary.length){stage.append(el('p',tr('No verified boundary sensitivity cases are attached to this baseline.','此基准尚无已核验的边界敏感性工况。')));return;}
  const lineLabel=c=>(c.change.path.includes('upstream')?tr('Upstream','上游'):tr('Downstream','下游'))+' '+c.change.before+' → '+c.change.after;
  const baseRows=variants('baseline');
  const dist=[0];for(let i=1;i<baseRows.length;i++)dist.push(dist[i-1]+(baseRows[i-1].channel_length_ft||0));
  const values=boundary.flatMap(c=>Object.values(c.by_rs)).filter(Number.isFinite),max=Math.max(.10,...values.map(Math.abs));
  const svg=makeSvg(stage,'0 0 680 160',tr('Boundary response from upstream to downstream','上游至下游的边界水位响应'));
  const px=i=>55+dist[i]/Math.max(1,dist.at(-1))*600,py=v=>72-v/max*51;
  svgEl(svg,'line',{x1:55,y1:72,x2:655,y2:72,stroke:'#777'});
  const selected=baseRows.findIndex(v=>v.rs===r.rs);svgEl(svg,'line',{x1:px(selected),x2:px(selected),y1:12,y2:132,stroke:'#444','stroke-dasharray':'3 3'});
  const colors=['#087c97','#cd6718','#8843a5','#40773b'];
  const legend=el('p',undefined,'context-legend');stage.append(legend);
  boundary.forEach((c,j)=>{
   const label=el('span',lineLabel(c));label.style.borderLeft='4px solid '+colors[j%4];legend.append(label);
   let points=[];
   function flush(){if(points.length)svgEl(svg,'polyline',{points:points.join(' '),fill:'none',stroke:colors[j%4],'stroke-width':2});points=[];}
   baseRows.forEach((row,i)=>{const v=c.by_rs[row.rs];if(Number.isFinite(v))points.push(px(i)+','+py(v));else flush();});flush();
   if(Number.isFinite(c.by_rs[r.rs]))svgEl(svg,'circle',{cx:px(selected),cy:py(c.by_rs[r.rs]),r:3,fill:colors[j%4]});
  });
  svgEl(svg,'text',{x:55,y:13,'font-size':12}).textContent=tr('Water level change (ft)','水位变化（ft）');
  for(const y of [max,0,-max])svgEl(svg,'text',{x:2,y:py(y)+4,'font-size':12}).textContent=format(y,2);
  svgEl(svg,'text',{x:55,y:150,'font-size':12}).textContent=tr('Upstream','上游')+' RS '+baseRows[0].rs;
  svgEl(svg,'text',{x:655,y:150,'text-anchor':'end','font-size':12}).textContent=tr('Downstream','下游')+' RS '+baseRows.at(-1).rs;
  table(stage,[tr('Baseline boundary change','基准模型边界变化'),tr('Δ at selected RS (ft)','所选 RS 水位差（ft）'),tr('Sections with |Δ| > 0.10 ft','绝对差超过 0.10 ft 的断面')],boundary.map(c=>{
   const vals=Object.values(c.by_rs).filter(Number.isFinite);return [lineLabel(c),format(c.by_rs[r.rs],3),vals.filter(v=>Math.abs(v)>.1).length+' / '+vals.length];
  }));
 }
 function makeSvg(parent,view,label){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox',view);svg.setAttribute('aria-label',label);svg.classList.add('repair-profile');parent.append(svg);return svg;}
 function plotMap(panel,active,rows){
  if(!active.map){panel.append(el('p',tr('No mapped cutline for this section.','此断面无可对应的空间线位。')));return;}
  const svg=makeSvg(panel,'0 0 620 330',tr('Select a cross section on the map','在地图上点选断面'));
  const i=rows.indexOf(active),local=rows.slice(Math.max(0,i-1),i+2).filter(r=>r.map);
  const coords=local.flatMap(r=>r.map.cutline_xy),xs=coords.map(p=>p[0]),ys=coords.map(p=>p[1]);
  const [l,b,h,t]=zoom.value==='all'?data.bounds:[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)];
  const k=Math.min(570/Math.max(1,h-l),285/Math.max(1,t-b)),px=x=>310+(x-(l+h)/2)*k,py=y=>165-(y-(b+t)/2)*k;
  svgEl(svg,'rect',{x:0,y:0,width:620,height:330,fill:'#eceee7'});
  const a=data.imagery;
  if(a.status==='READY'){const [x0,y0,x1,y1]=a.bounds;svgEl(svg,'image',{href:a.uri,x:px(x0),y:py(y1),width:(x1-x0)*k,height:(y1-y0)*k,preserveAspectRatio:'none'});}
  function line(xy,color,width,dash){return svgEl(svg,'polyline',{points:xy.map(([x,y])=>px(x)+','+py(y)).join(' '),fill:'none',stroke:color,'stroke-width':width,'stroke-dasharray':dash||''});}
  for(const layer of data.layers)for(const f of layer.lines){const p=line(f.xy,layer.kind==='levees'?'#ff9a32':'#fbf6d6',layer.kind==='levees'?3:1.5,layer.kind==='levees'?'5 3':'');if(f.name)svgEl(p,'title',{}).textContent=f.name;}
  for(const v of [...rows.filter(v=>v!==active),active]){
   if(!v.map)continue;const xy=v.map.cutline_xy;
   line(xy,v===active?'#ff3c96':'#8bd5ec',v===active?4:1.4);
   const hit=line(xy,'transparent',12);hit.style.cursor='pointer';svgEl(hit,'title',{}).textContent='RS '+v.rs;
   hit.addEventListener('click',()=>{select.value=v.rs;paint();});
  }
  for(const p of active.map.banks_xy||[])svgEl(svg,'circle',{cx:px(p[0]),cy:py(p[1]),r:3.5,fill:'#ffe357',stroke:'#222'});
  svgEl(svg,'text',{x:606,y:20,'text-anchor':'end',fill:'white',stroke:'#28333a','paint-order':'stroke','stroke-width':3}).textContent='N ↑';
  panel.append(el('small',tr('Pink selected · cyan adjacent · yellow banks · cream roads · dashed orange levee alignments.','粉色为当前断面，青色为其他断面，黄点为岸站，米色为道路，橙色虚线为堤线。')));
  if(a.status!=='READY')panel.append(el('p',tr('Offline imagery unavailable','离线航片不可用')+' · '+a.status,'warning'));
 }
 if(profiles.includes(prior?.profile))profile.value=prior.profile;
 if(names.includes(prior?.geometry))revision.value=prior.geometry;
 if(prior?.zoom==='all')zoom.value='all';
 profile.onchange=reset;revision.onchange=paint;select.onchange=paint;zoom.onchange=paint;reset();
}
