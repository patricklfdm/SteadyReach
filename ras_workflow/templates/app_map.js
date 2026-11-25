'use strict';
let terrainMapController=null,sectionRepairController=null;
const terrainViews=new Map();
function terrainMap(canvas,options){
 const project=current.id,viewKey=options.viewKey||project,viewport=el('div',undefined,'terrain-viewport'),message=el('p','', 'muted');
 viewport.tabIndex=0;viewport.setAttribute('role','region');viewport.setAttribute('aria-label',tr('DEM map: drag to pan, scroll to zoom; arrows and + / − also work','DEM 地图：拖动平移，滚轮缩放，也可用方向键及加减键'));
 canvas.replaceChildren(viewport,message);let data=null,requested=null,serial=0,timer=null,drag=null,suppressUntil=0,selected=null,preview=[],highlighted=new Set();
 function clamp(bounds){
  if(!data)return bounds;const e=data.terrain_bounds,min=data.min_span,max=data.max_span;
  const span=Math.max(min,Math.min(max,Math.max(bounds[2]-bounds[0],bounds[3]-bounds[1])));
  const x=Math.max(e[0],Math.min(e[2],(bounds[0]+bounds[2])/2)),y=Math.max(e[1],Math.min(e[3],(bounds[1]+bounds[3])/2));
  return [x-span/2,y-span/2,x+span/2,y+span/2];
 }
 async function load(bounds){
  clearTimeout(timer);const number=++serial;requested=bounds?clamp(bounds):null;viewport.setAttribute('aria-busy','true');message.removeAttribute('role');message.textContent=tr('Loading DEM…','正在载入 DEM…');
  try{const r=await api('geometry/map',{id:project,bounds:requested});if(number!==serial||!canvas.isConnected)return;
   data=r;if(!options.detached)mapData=r;requested=r.bounds;terrainViews.set(viewKey,r.bounds);draw();
  }catch(e){if(number===serial&&canvas.isConnected){message.textContent=tr('Map load failed: ','地图载入失败：')+e.message;message.setAttribute('role','alert');}}
  finally{if(number===serial)viewport.removeAttribute('aria-busy');}
 }
 function schedule(bounds){requested=clamp(bounds);++serial;clearTimeout(timer);timer=setTimeout(()=>load(requested),140);}
 function zoom(factor,at=[.5,.5]){if(!data)return load();const b=requested||data.bounds,s=b[2]-b[0],next=Math.max(data.min_span,Math.min(data.max_span,s*factor)),x=b[0]+s*at[0],y=b[3]-s*at[1];schedule([x-next*at[0],y-next*(1-at[1]),x+next*(1-at[0]),y+next*at[1]]);}
 async function fit(kind){if(!data){await load();if(!data)return;}let points=[];if(kind==='preview')points=preview.flatMap(r=>r.cutline_xy);if(kind==='conflict')points=preview.filter(r=>highlighted.has(r)).flatMap(r=>r.cutline_xy);if(kind==='sections')points=(data.section_items||[]).flatMap(r=>r.cutline_xy);if(!points.length){const b=data.terrain_bounds;points=[[b[0],b[1]],[b[2],b[3]]];}const x=points.map(p=>p[0]),y=points.map(p=>p[1]);const cx=(Math.min(...x)+Math.max(...x))/2,cy=(Math.min(...y)+Math.max(...y))/2,span=Math.max(Math.max(...x)-Math.min(...x),Math.max(...y)-Math.min(...y))*1.12;return load(clamp([cx-span/2,cy-span/2,cx+span/2,cy+span/2]));}
 function focus(index){selected=index;draw();}
 function setPreview(rows,focusRows=[]){preview=rows||[];highlighted=new Set(focusRows);draw();}
 function draw(){
  if(!data)return;viewport.replaceChildren();const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 650 650');svg.classList.add('map','interactive-map');viewport.append(svg);
  const group=svgEl(svg,'g',{});svgEl(group,'image',{href:'data:image/png;base64,'+data.background,width:650,height:650});
  const [x0,y0,x1,y1]=data.bounds,span=x1-x0,xy=p=>[(p[0]-x0)/span*650,(y1-p[1])/span*650];
  const tb=data.terrain_bounds,a=xy([tb[0],tb[3]]),b=xy([tb[2],tb[1]]);svgEl(group,'rect',{x:a[0],y:a[1],width:b[0]-a[0],height:b[1]-a[1],fill:'none',stroke:'#657577','stroke-dasharray':'5 4','pointer-events':'none'});
  const bad=new Set((data.spatial_issues||[]).flatMap(q=>q.sections));
  for(const row of data.section_items||[]){const pts=row.cutline_xy.map(xy),color=row.index===selected?'#005bbb':bad.has(row.index)?'#c52e2e':'#7750aa';const path=svgEl(group,'polyline',{points:pts.map(p=>p.join(',')).join(' '),fill:'none',stroke:color,'stroke-width':row.index===selected?4:2,tabindex:0,role:'button','aria-label':`XS ${row.rs}`});path.style.cursor='pointer';const pick=e=>{if(options.getMode()||busy)return;e.stopPropagation();selected=row.index;sectionRepairController?.select(row.index);draw();};path.onclick=pick;path.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();pick(e);}};svgEl(group,'text',{x:pts[0][0]+4,y:pts[0][1]-5,fill:color,'font-size':12,'pointer-events':'none'}).textContent=`RS ${row.rs}`;}
  function drawPreview(row,active){
   const pts=row.cutline_xy.map(xy);
   svgEl(group,'polyline',{points:pts.map(p=>p.join(',')).join(' '),fill:'none',stroke:active?'#a52518':'#007641','stroke-width':active?5:3,'stroke-dasharray':active?'':'8 5','pointer-events':'none'});
   if(active)svgEl(group,'text',{x:pts[0][0]+4,y:pts[0][1]-4,fill:'#78190f',stroke:'white','stroke-width':3,'paint-order':'stroke','pointer-events':'none'}).textContent='RS '+row.rs;
  }
  for(const row of preview)if(!highlighted.has(row))drawPreview(row,false);
  for(const row of highlighted)drawPreview(row,true);
  const lines=options.riverLines ?? data.river_lines ?? [];
  for(const line of lines)svgEl(group,'polyline',{points:line.map(xy).map(p=>p.join(',')).join(' '),fill:'none',stroke:'#005aab','stroke-width':3,'pointer-events':'none'});
  if(options.openingAxis){
   const [a,b]=options.openingAxis.map(xy),angle=Math.atan2(b[1]-a[1],b[0]-a[0]),color='#75257c';
   svgEl(group,'line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1],stroke:color,'stroke-width':3});
   svgEl(group,'circle',{cx:a[0],cy:a[1],r:4,fill:'white',stroke:color,'stroke-width':2});
   const tip=[b,...[-.52,.52].map(t=>[b[0]-9*Math.cos(angle+t),b[1]-9*Math.sin(angle+t)])];
   svgEl(group,'polygon',{points:tip.map(p=>p.join(',')).join(' '),fill:color});
  }
  const anchors=options.getAnchors();
  for(const[key,color]of [['river','#007b65'],['upstream','#0055cb'],['downstream','#c64a00'],['inlet','#9800a4'],['outlet','#114f00'],['road','#990000']]){if(key!=='river'||!lines.length)svgEl(group,'polyline',{points:(anchors[key]||[]).map(xy).map(p=>p.join(',')).join(' '),fill:'none',stroke:color,'stroke-width':3});(anchors[key]||[]).forEach((p,i)=>{const[x,y]=xy(p);svgEl(group,'circle',{cx:x,cy:y,r:5,fill:color});svgEl(group,'text',{x:x+7,y:y-7,fill:color}).textContent=key[0].toUpperCase()+(i+1);});}
  for(const opening of data.opening_items||[]){const points=opening.xy.map(xy);svgEl(group,'polyline',{points:points.map(p=>p.join(',')).join(' '),fill:'none',stroke:'#007e86','stroke-width':3,'stroke-dasharray':'4 3','pointer-events':'none'});svgEl(group,'text',{x:points[0][0]+5,y:points[0][1]+15,fill:'#005e66','font-size':12,'pointer-events':'none'}).textContent='G'+(opening.group+1)+' / '+(opening.barrel+1);}
  drawSurveyOverlay(group,data,xy,p=>{if(!options.getMode())return false;options.onPoint(p.xy);return true;});
  svgEl(svg,'text',{x:540,y:25,fill:'#18344d','pointer-events':'none'}).textContent='Grid N ↑';
  const meters=span*data.unit_to_m,scale=Math.pow(10,Math.floor(Math.log10(meters/5))),px=scale/meters*650;svgEl(svg,'path',{d:`M20 610 v8 h${px} v-8`,fill:'none',stroke:'#17324d','stroke-width':3,'pointer-events':'none'});svgEl(svg,'text',{x:20,y:602,fill:'#17324d','pointer-events':'none'}).textContent=scale+' m';
  message.textContent=(lines.length?tr('Blue: modeled river path. ','蓝线：模型河道路径。'):'')+tr('Drag to pan · scroll to zoom · red: intersections · green dashed: preview. ','拖动平移 · 滚轮缩放 · 红色：相交 · 绿色虚线：预览。')+tr('View width ','视野宽度 ')+meters.toFixed(1)+' m · DEM '+(data.resolution[0]*data.unit_to_m).toFixed(2)+' m · '+data.crs+tr(' · Outside the dashed DEM boundary is unavailable, not additional terrain.',' · DEM 虚线边界外无地形数据。');
  svg.onclick=e=>{if(busy||!options.getMode())return;const r=svg.getBoundingClientRect(),nx=(e.clientX-r.left)/r.width,ny=(e.clientY-r.top)/r.height;if(nx<0||nx>1||ny<0||ny>1)return;const p=[x0+nx*span,y1-ny*span];if(p[0]<tb[0]||p[0]>tb[2]||p[1]<tb[1]||p[1]>tb[3]){notify(tr('This point is outside the downloaded DEM.','该点在已下载 DEM 范围外。'),true);return;}options.onPoint(p);};
 }
 viewport.addEventListener('click',e=>{if(performance.now()<suppressUntil){e.preventDefault();e.stopImmediatePropagation();}},true);
 viewport.addEventListener('pointerdown',e=>{if(e.button!==0||!data||busy)return;viewport.focus({preventScroll:true});drag={id:e.pointerId,x:e.clientX,y:e.clientY,bounds:[...data.bounds],moved:false};});
 viewport.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.hypot(dx,dy)>5&&!drag.moved){drag.moved=true;viewport.setPointerCapture(e.pointerId);viewport.classList.add('dragging');}if(drag.moved){e.preventDefault();const g=viewport.querySelector('svg > g'),r=viewport.querySelector('svg').getBoundingClientRect();if(g)g.setAttribute('transform',`translate(${dx/r.width*650},${dy/r.width*650})`);}});
 const end=e=>{if(!drag||e.pointerId!==drag.id)return;const d=drag;drag=null;viewport.classList.remove('dragging');if(viewport.hasPointerCapture(e.pointerId))viewport.releasePointerCapture(e.pointerId);if(d.moved){suppressUntil=performance.now()+500;const r=viewport.querySelector('svg').getBoundingClientRect(),s=(d.bounds[2]-d.bounds[0])/r.width,dx=(e.clientX-d.x)*s,dy=(e.clientY-d.y)*s;schedule([d.bounds[0]-dx,d.bounds[1]+dy,d.bounds[2]-dx,d.bounds[3]+dy]);}};
 viewport.addEventListener('pointerup',end);viewport.addEventListener('pointercancel',e=>{drag=null;suppressUntil=performance.now()+500;viewport.classList.remove('dragging');draw();});
 viewport.addEventListener('wheel',e=>{if(!data||busy)return;e.preventDefault();const r=viewport.querySelector('svg').getBoundingClientRect();zoom(Math.exp(Math.max(-200,Math.min(200,e.deltaY))*.0015),[(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height]);},{passive:false});
 viewport.addEventListener('keydown',e=>{if(busy||e.target!==viewport)return;if(['+','=','-'].includes(e.key)){e.preventDefault();zoom(e.key==='-'?1.2:1/1.2);}else if(e.key==='Home'){e.preventDefault();fit('terrain');}else if(data&&['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();const b=requested||data.bounds,s=(b[2]-b[0])*.15,dx=e.key==='ArrowLeft'?-s:e.key==='ArrowRight'?s:0,dy=e.key==='ArrowDown'?-s:e.key==='ArrowUp'?s:0;schedule([b[0]+dx,b[1]+dy,b[2]+dx,b[3]+dy]);}});
 const controller={load,zoom,fit,draw,focus,setPreview};if(!options.detached)terrainMapController=controller;load(terrainViews.get(viewKey));return controller;
}
