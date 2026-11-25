'use strict';
const sourceStatus=s=>({FIS_ROW_SELECTED:tr('Selected FIS row','已采用 FIS 表行'),FIS_STREAM_MISMATCH:tr('Check roughness for the selected flow river','核对糙率与已选流量的河流'),FIS_SELECTION_CHANGED:tr('Check the previous FIS selection against current evidence','按当前资料重新核对已选 FIS 表行'),NOT_ATTEMPTED:tr('Not attempted yet','尚未尝试'),NO_EXTRACTED_VALUE:tr('Attempted · no unambiguous value','已尝试 · 无明确可用值'),CANDIDATE:tr('Candidate available','已有候选'),CONFLICT:tr('Values differ','数值冲突'),SOURCE_CHANGED:tr('Source changed · import again','来源已改变 · 请重新导入'),INSPECTED:tr('Inspected','已解析'),EXTRACTION_FAILED:tr('Extraction unavailable','暂无法提取'),NETWORK_FAILED:tr('Network request failed','网络请求失败'),SOURCE_LOOKUP_FAILED:tr('Source lookup needs review','资料查询需核查'),DOWNLOAD_LIMIT_REACHED:tr('Automatic download limit reached','已达到自动下载上限'),PUBLIC_DOWNLOAD_ACTION_REQUIRED:tr('Public download needs a browser step (no manager account)','公开下载需浏览器操作（无需管理账号）'),DOWNLOAD_FAILED:tr('Download failed · saved material retained','下载失败 · 已存资料保留'),FOUND_RECORDS:tr('Catalog records found','已找到目录记录'),NO_CATALOG_MATCH:tr('No catalog match','目录未匹配'),MATCH_CANDIDATE:tr('Nearby site candidate','邻近站点候选'),NO_MATCH_WITHIN_150_M:tr('No supported site within 150 m','150 米内未匹配支持站点'),OUTSIDE_PROVIDER_COVERAGE:tr('Outside this provider coverage','不在此资料源覆盖范围'),DOWNLOADED:tr('Downloaded','已下载'),CRS_AND_UNITS_REQUIRED:tr('Confirm survey CRS / units','需确认测量坐标系／单位'),COLUMN_MAPPING_REQUIRED:tr('Map column names','需匹配列名'),PARSED:tr('Survey points read','已读取测点')}[s]||s);
function focusParameter(key){const input=document.getElementById('input-'+key);if(!input){notify(tr('Open the editable parameter list for this field.','请打开此字段的可编辑参数清单。'),true);return;}let p=input.parentElement;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement;}input.scrollIntoView({block:'center',behavior:'smooth'});input.focus({preventScroll:true});}
function renderParameterNavigator(parent,fields){
 const box=el('section',undefined,'card parameter-nav');parent.append(box);
 const missing=fields.filter(f=>f.missing&&f.required),conflicts=fields.filter(f=>f.source_conflict),choices=fields.filter(f=>f.parameter_candidates?.length);
 box.append(el('strong',`${fields.length} `+tr('parameters','项参数')+` · ${missing.length} `+tr('required missing','项必要缺失')+` · ${conflicts.length} `+tr('source conflicts','项来源冲突')+` · ${choices.length} `+tr('with candidates','项有候选')));
 const browse=details(box,'Find a parameter / missing item','查找参数／缺失项',false),grid=el('div',undefined,'grid');browse.append(grid);
 const search=field(grid,'parameter-search','Search name or field','搜索名称或字段');
 const filter=field(grid,'parameter-filter','Show','显示','missing','select',[['missing','Required missing','必要缺失'],['conflict','Source conflicts','来源冲突'],['candidate','Has candidates','有候选值'],['all','All parameters','全部参数']]);
 const list=el('div');browse.append(list);
 function draw(){list.replaceChildren();const q=search.value.toLowerCase();const selected=fields.filter(f=>(!q||(f.key+' '+f.label.en+' '+f.label.zh).toLowerCase().includes(q))&&(filter.value==='all'||filter.value==='missing'&&f.missing&&f.required||filter.value==='conflict'&&f.source_conflict||filter.value==='candidate'&&f.parameter_candidates?.length));if(!selected.length)list.append(el('p',tr('No matching items.','没有符合条件的项目。')));for(const f of selected){const row=el('div',undefined,'parameter-link');row.append(button(tr(f.label.en,f.label.zh),tr(f.label.en,f.label.zh),async()=>focusParameter(f.key)),el('small',(f.missing?'—':format(f.value,f.kind).slice(0,100))+' · '+sourceStatus(f.acquisition?.status||'')));list.append(row);}}
 search.oninput=draw;filter.onchange=draw;draw();
}
const siteRequests={
 crossing:['Crossing and road survey','涵洞与道路联合测量','Ask the owner or survey crew for the as-built plan and longitudinal survey. Request both end inverts on the same datum, barrel dimensions, blockage and road crest. These control headwater and overtopping.','向业主或测量队索取竣工图和纵断测量。两端涵底要使用同一高程基准，同时核对孔径、淤堵与路顶。这些资料影响涵前水位和漫顶判断。'],
 flow:['Event discharge record','事件流量资料','Request the hydrology study or gage record for this event and reach. Check the return period, units and drainage area.','向水文资料提供方索取本事件、本河段的研究或测站记录。核对重现期、单位和汇水面积。'],
 control:['Boundary or datum control','边界与高程控制资料','Ask for the applicable vertical reference and any event-matched water levels at the model boundary. Record station, event and units.','索取适用的高程基准和模型边界同事件水位，注明位置、事件和单位。']
};
function siteRequestKind(key){
 if(/^g\.structure\.groups\.\d+\.(shape|count|span_ft|rise_ft|length_ft|us_invert_ft|ds_invert_ft|depth_blocked_ft|bottom_type|inlet_description)$/.test(key)
    ||/^g\.structure\.road\.(width_ft|elevation_ft|station_ft|downstream_station_ft|downstream_elevation_ft)$/.test(key))return 'crossing';
 if(/^c\.scenarios\.\d+\.profiles\.\d+\.flow_cfs$/.test(key))return 'flow';
 if(key==='g.vertical_datum'||/^g\.boundaries\.(upstream|downstream)\.stages_ft$/.test(key))return 'control';
 return null;
}
function requestBundles(fields){
 const crossing=fields.some(f=>siteRequestKind(f.key)==='crossing');
 return Object.entries(siteRequests).map(([kind,labels])=>({kind,labels,
  fields:fields.filter(f=>(crossing&&f.key==='g.vertical_datum'?'crossing':siteRequestKind(f.key))===kind)})).filter(group=>group.fields.length);
}
function siteEvidenceRequests(fields){
 const provisional=new Set(['assumed','inferred','terrain_derived','source_input_unverified','user_entered']);
 return fields.filter(f=>siteRequestKind(f.key)&&(f.required||!f.missing)&&(f.source_conflict||(
  f.missing?f.required&&!f.parameter_candidates?.some(c=>['reported','measured','surveyed'].includes(c.evidence_class))
           :provisional.has(f.evidence_class))));
}
function renderRequestBundles(host,fields){
 for(const group of requestBundles(fields)){
  const [en,zh,whyEn,whyZh]=group.labels;
  const row=details(host,en+' ('+group.fields.length+')',zh+'（'+group.fields.length+'）');
  const status=f=>f.source_conflict?tr('Conflicting sources','来源冲突'):f.missing?tr('Missing','待补'):tr('Verify adopted value','核对已采用值');
  row.append(el('p',tr(whyEn,whyZh)),el('p',group.fields.map(f=>tr(f.label.en,f.label.zh)+' ('+status(f)+')').join(' · ')),
   button('Export this request','导出这份索取表',()=>downloadParameterTemplate(group.fields,'site_'+group.kind+'.csv',group.labels)));
 }
}
function preparationActions(model){
 const intake=model.intake;
 if(!intake||model.native||model.results||model.feasibility?.state==='outside')return [];
 const fields=intake.fields||[], actions=[];
 function group(kind,rows){if(rows.length)actions.push({kind,fields:rows});}
 const remaining=fields.filter(f=>f.required&&f.missing&&!f.source_conflict);
 const physical=siteRequestKind;
 const geometry=intake.geometry_review?.issues||[];
 const blocking=(model.automation?.checks?.issues||[]).filter(issue=>issue.blocking&&!geometry.some(
  spatial=>spatial.code===issue.code&&JSON.stringify(spatial.sections)===JSON.stringify(issue.sections)));
 if(!intake.section_count)actions.push({kind:'layout',fields:[]});
 else if(geometry.length)actions.push({kind:'repair',fields:[],geometry});
 if(blocking.length)actions.push({kind:'dependencies',fields:[],issues:blocking});
 group('conflict',fields.filter(f=>f.source_conflict&&(f.required||!f.missing)));
 if(remaining.length&&intake.section_count&&model.route==='coordinates'&&model.automation&&!model.preparation_result){
  actions.push({kind:'derive',fields:[]});
 }
 group('source',remaining.filter(f=>physical(f.key)&&!f.parameter_candidates?.length));
 group('banks',remaining.filter(f=>f.key.endsWith('.bank_stations_ft')));
 group('candidates',remaining.filter(f=>!f.key.endsWith('.bank_stations_ft')&&f.parameter_candidates?.length));
 group('judgment',remaining.filter(f=>!physical(f.key)&&!f.key.endsWith('.bank_stations_ft')&&!f.parameter_candidates?.length));
 if(!actions.length&&model.missing?.length)actions.push({kind:'checks',fields:[]});
 return actions;
}

function scopedParameterCsv(fields,request=null){
 const quote=value=>'"'+String(value??'').replaceAll('"','""')+'"';
 const instructions=request?request.slice(2):[];
 return ['field,value,unit,datum,evidence_class,source,parameter_en,parameter_zh'+(request?',request_en,request_zh,request_status,current_value,current_class':''),
  ...fields.map(f=>[f.key,'',f.unit||'','','reported','',f.label?.en,f.label?.zh,...instructions,...(request?[
   f.source_conflict?'conflict':f.missing?'missing':'verify_adopted',f.missing?'':JSON.stringify(f.value),f.evidence_class||'']:[])].map(quote).join(','))].join('\r\n');
}
function downloadParameterTemplate(fields=current.intake?.fields||[],name='parameter_import.csv',request=null){
 const url=URL.createObjectURL(new Blob(['\ufeff'+scopedParameterCsv(fields,request)],{type:'text/csv;charset=utf-8'}));
 const link=el('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 notify(fields.length+tr(' rows exported. Enter values, units, elevation datum where applicable, and the source; mark estimates as assumed. Import the CSV in Site materials to review the candidates.',' 行已导出。请填写数值、单位、适用的高程基准和来源，估计值标为 assumed；将 CSV 导回现场资料后核对候选。'));
}

function renderPreparationActions(parent,actions){
 if(!actions.length)return;
 const labels={
  layout:['Lay out the river and cross sections','布置河线和断面'],
  repair:['Resolve section geometry','修正断面几何'],
  dependencies:['Resolve blocking model checks','处理阻塞计算的模型检查'],
  derive:['Try automatic preparation with the available sources','用已有资料自动补齐草稿'],
  conflict:['Resolve conflicting sources','核对有冲突的来源'],
  source:['Find missing site or design data','补充缺少的现场或设计资料'],
  banks:['Locate missing banks','核对缺少的岸站'],
  candidates:['Review available parameter candidates','核对已有候选值'],
  judgment:['Complete remaining hydraulic settings','补齐其余水力设置'],
  checks:['Inspect remaining input checks','定位其余输入检查']
 };
 const box=el('section',undefined,'card');parent.append(box);
 box.append(el('h2',tr('What should I do next?','现在先做什么？')));
 const show=async key=>{
  if(!document.getElementById('input-'+key))await showFinalReview();
  revealParameter(key);
 };
 function render(host,action){
  const rows=action.fields,kind=action.kind;
  host.append(el('strong',tr(...labels[kind])+(rows.length?' · '+rows.length:'')));
  if(kind==='layout'){
   host.append(el('p',tr('Preview the channel and section positions on the DEM, then check their direction and coverage. A drawing or survey can be added at any time.','在 DEM 上预览河线与断面，核对方向和覆盖范围。已有图纸或测量资料时可随时补充。')),
    button('Open DEM layout','打开 DEM 布置',()=>openModelTool('dem-layout')));
  }else if(kind==='repair'){
   host.append(el('p',action.geometry.length+tr(' spatial checks. Open the section tools and inspect the affected cuts before changing hydraulic inputs.',' 项断面空间检查。请先定位受影响的断面并预览修正。')),
    button('Open section repair','打开断面修正',()=>openModelTool('section-repair')));
  }else if(kind==='dependencies'){
   for(const issue of action.issues)host.append(el('p',tr(issue.message,issue.zh)));
   host.append(button('Open model checks','打开模型检查',()=>openModelTool('model-automation')));
  }else if(kind==='derive'){
   host.append(el('p',tr('Use the saved materials and terrain to propose inputs first. Review assumptions together before starting HEC-RAS.','先用已保存的资料和地形推导候选参数。开算前再集中核对假设。')),
    button('Prepare an automatic draft','自动准备草稿（含标注的估计值）',async()=>{const id=current.id;await save();await api('automatic-prepare',{id,revision:current.revision});await open(id);},'primary'));
  }else if(kind==='checks'){
   host.append(button('Locate the failed checks','定位检查项',showFinalReview));
  }else{
   if(kind==='source'){
    host.append(el('p',tr('These required fields lack a usable candidate. Check hydrology records, drawings or survey first. You can send a worksheet with just these fields and import the reply here.','这些必填字段还没有可用候选。先查水文原件、竣工图或测量记录；可只导出这些缺项，将填好的表导回此项目。')),
     button('Add a source or returned worksheet','导入资料或填好的缺项表',()=>openModelTool('site-file-import')),
     button('Export missing site data (CSV)','导出待索取资料（CSV）',()=>downloadParameterTemplate(rows,'missing_site_data.csv')));
   }else if(kind==='banks'){
    host.append(button('Inspect bank profiles','查看岸站剖面',()=>openModelTool('bank-profiles')));
   }else{
    const first=rows[0];host.append(button('Review '+first.label.en,'核对'+first.label.zh,()=>show(first.key)));
   }
   const list=details(host,'Fields in this group','查看本组字段');for(const f of rows){
    list.append(button(f.label.en,f.label.zh,()=>show(f.key)));
   }
  }
 }
 render(box,actions[0]);
 if(actions.length>1){
  const rest=details(box,'Other preparation tasks ('+(actions.length-1)+')','其他准备事项（'+(actions.length-1)+' 组）');
  for(const action of actions.slice(1)){const section=el('section',undefined,'parameter');rest.append(section);render(section,action);}
 }
}
function renderFisSelection(parent) {
 const fields = current.intake?.fields || [];
 const candidates = fields.flatMap(field => (field.parameter_candidates || []).filter(row => row.source_locus && row.source?.sha256 && row.source.path));
 const flows = candidates.filter(row => row.hydrologic_context?.aep_percent === 1);
 if (!flows.length) return;
 const adopted = fields.map(field => field.answer?.candidate_record)
  .find(row => row && flows.some(candidate => candidate.candidate === row.candidate));
 const sourceFields = fields.filter(field => candidates.some(row => row.field === field.key));
 const settled = !!adopted && sourceFields.every(field => field.acquisition?.status === 'FIS_ROW_SELECTED');
 const suffix = settled ? ' · '+adopted.hydrologic_context.stream+' · '+adopted.hydrologic_context.location+' · '+adopted.value+' cfs' : '';
 const box = details(parent, 'FIS river and Q100 location'+suffix, 'FIS 河流与 Q100 适用地点'+suffix, !settled);
 box.append(el('p', tr(
  'Choose the river and hydrologic location that applies to your reach. The report can contain several locations on the same river. Check relevant map revisions and the source pages.',
  '选择适用于本河段的河流及水文位置。同一条河可能有多行流量，需对照来源页及相关地图修订确认。')));
 const streams = [...new Set(flows.map(candidate => candidate.hydrologic_context.stream))].sort();
 const titleMatches = streams.filter(stream => current.title.toLowerCase().includes(stream.toLowerCase()));
 const initial = adopted?.hydrologic_context.stream || (titleMatches.length === 1 ? titleMatches[0] : '');
 const river = field(box, 'fis-river', 'River', '河流', initial, 'select',
  [['', 'Choose a river', '选择河流'], ...streams.map(stream => [stream, stream, stream])]);
 const location = field(box, 'fis-location', 'Hydrologic location and source', '水文位置与来源', '', 'select', []);
 const preview = el('div');
 box.append(preview);
 let selected = null;
 let roughnessSelections = [];
 const apply = button('Apply this flow and checked roughness', '采用此流量与勾选的糙率', async () => {
  if (!selected) throw Error(tr('Choose a hydrologic location first.', '请先选择适用水文位置。'));
  const chosen = [selected, ...roughnessSelections.filter(row => row.input.checked).map(row => row.candidate)];
  await save();
  const selections = chosen.map(candidate => {
   const fresh = current.intake.fields.find(field => field.key === candidate.field)
    ?.parameter_candidates.find(value => value.candidate === candidate.candidate);
   if (!fresh) throw Error(tr('Source candidates changed. Reopen this selection.', '来源候选已变化，请重新打开此选择。'));
   return {field: candidate.field, candidate: fresh.candidate};
  });
  await api('candidate', {id: current.id, revision: current.revision, selections});
  await open(current.id);
  notify(tr('Source choices saved with page references. Review the full model before calculating.', '已保存来源选择及页码。运算前请核对完整模型。'));
 }, 'primary');
 box.append(apply);
 function show() {
  preview.replaceChildren();
  roughnessSelections = [];
  selected = flows.find(candidate => candidate.candidate === location.value) || null;
  apply.disabled = !selected;
  if (!selected) return;
  preview.append(el('p', 'Q100 '+selected.value+' cfs · '+selected.basis));
  const original = el('a', tr('Open discharge source page ↗', '打开流量来源页 ↗'));
  original.href = 'file/'+selected.source.path+'#page='+selected.source_locus.pdf_page;
  original.target = '_blank';
  preview.append(original);
  const prefix = selected.field.split('.').slice(0, 3).join('.')+'.';
  for (const name of ['channel_n', 'overbank_n']) {
   const choices = candidates.filter(candidate => candidate.field === prefix+name
    && candidate.source.sha256 === selected.source.sha256
    && candidate.hydrologic_context?.stream === selected.hydrologic_context.stream);
   const meanings = new Set(choices.map(candidate => JSON.stringify([candidate.value,candidate.range,candidate.evidence_class])));
   if (meanings.size !== 1) continue;
   const candidate = choices[0], saved = fields.find(field => field.key === candidate.field);
   const label = el('label'), input = el('input');
   input.type = 'checkbox';
   input.checked = !!saved?.missing;
   label.append(input, document.createTextNode(' '+tr(name === 'channel_n' ? 'Channel n' : 'Overbank n', name === 'channel_n' ? '主槽 n' : '漫滩 n')
    +' = '+candidate.value+' · '+originName(candidate.evidence_class)));
   preview.append(label, el('p', candidate.basis), el('small', tr('Saved value: ', '已保存值：')+(saved?.value ?? '—')));
   roughnessSelections.push({input, candidate});
  }
 }
 function populate() {
  location.replaceChildren();
  for (const value of [{candidate:'', label:tr('Choose a location', '选择位置')},
   ...flows.filter(candidate => candidate.hydrologic_context.stream === river.value).map(candidate => ({
    candidate:candidate.candidate, label:candidate.hydrologic_context.location+' · '+candidate.value+' cfs · '
     +(candidate.source.original_name || candidate.source.path.split('/').at(-1))+' · p'+candidate.source_locus.pdf_page}))]) {
   const option = el('option', value.label);option.value = value.candidate;location.append(option);
  }
  if (adopted && flows.some(candidate => candidate.candidate === adopted.candidate && candidate.hydrologic_context.stream === river.value)) location.value = adopted.candidate;
  show();
 }
 river.onchange = () => {
  populate();
  notify(tr('River preview updated. Choose a location and apply to save.', '河流预览已更新，选择适用位置后点击采用即可保存。'));
 };
 location.onchange = () => {
  show();
  notify(tr('Candidate preview updated. Apply to save these source choices.', '候选预览已更新，点击采用后保存本次来源选择。'));
 };
 populate();
}

function showAcquisitionGaps(parent,acquisition){
 const gaps=(acquisition?.attempts||[]).filter(r=>r.status?.endsWith('_FAILED')||r.status==='PUBLIC_DOWNLOAD_ACTION_REQUIRED');
 if(!gaps.length)return false;
 const box=el('section',undefined,'warning');
 const heading=tr('Public sources needing attention on the last search','上次公开查询中需要留意的来源');
 box.append(el('strong',heading+' ('+gaps.length+')'),el('p',tr('Document extraction covers files already on disk. Check the listed sources before relying on fallback values. You can retry the public search or import a local copy.','提取统计只涵盖已取得的文件。采用备选参数前，请核对下列来源，可以重试公开查询或导入本地副本。')));
 const list=el('ul');
 for(const row of gaps){
  let product='';
  if(row.url){try{product=new URL(row.url).searchParams.get('productID')||'';}catch{/* Some providers only record a route. */}}
  const item=el('li',[row.route,product,sourceStatus(row.status),row.error||row.reason].filter(Boolean).join(' · '));
  if(product&&(acquisition.documents||[]).some(d=>d.source?.original_name?.toLowerCase()===product.toLowerCase()+'.pdf')){
   item.append(el('small',tr(' A local PDF with this product name is now available. Verify its contents.',' 已有同产品名的本地 PDF，可核对其内容。')));
  }
  list.append(item);
 }
 box.append(list);parent.append(box);return true;
}

function sourceFileHref(source){return 'file/'+source.path.split('/').map(encodeURIComponent).join('/');}
function renderCrossingIntake(parent,fields){
 const panel=el('section',undefined,'card');panel.id='first-crossing';parent.append(panel);
 panel.append(el('h3',tr('Start with the crossing','从涵洞位置开始')));
 const originals=current.attachments||[];
 const add=button(originals.length?'Review or add source files':'Add site files',originals.length?'复核或补充原始资料':'添加现场资料',()=>openModelTool('site-file-import'));
 panel.append(add);
 if(originals.length){
  const files=details(panel,'Open the originals ('+originals.length+')','查看原件（'+originals.length+'）');
  for(const f of originals){const a=el('a',f.original_name||f.path.split('/').at(-1));a.href=sourceFileHref(f);a.target='_blank';a.rel='noopener';files.append(a,el('br'));}
 }
 const essentials=fields.filter(f=>/\.(flow_cfs|overbank_n|channel_n|shape|span_ft|rise_ft|count|length_ft|us_invert_ft|ds_invert_ft)$/.test(f.key)||f.key==='g.structure.road.width_ft');
 const buckets=[
  [tr('Available inputs and source candidates','已有输入和资料候选'),f=>!f.missing&&!['assumed','inferred','terrain_derived'].includes(f.evidence_class)||f.missing&&f.parameter_candidates?.some(c=>c.source)],
  [tr('Conditional values to review','待核对的条件性数值'),f=>!f.missing&&['assumed','inferred','terrain_derived'].includes(f.evidence_class)],
  [tr('Still to establish','待补依据的参数'),f=>f.missing&&!f.parameter_candidates?.some(c=>c.source)]];
 for(const [title,test] of buckets){
  const list=essentials.filter(test),group=details(panel,title+' ('+list.length+')',title+'（'+list.length+'）');
  for(const f of list){const c=f.parameter_candidates?.find(v=>v.source);
   const row=el('p');row.append(button(f.label.en,f.label.zh,()=>revealParameter(f.key)),document.createTextNode(' '+(f.missing?(c?tr('Candidate ','候选 ')+format(c.value,f.kind):'—'):format(f.value,f.kind))+' '+(f.unit||'')+' · '+(f.missing&&c?originName(c.evidence_class):originName(f.evidence_class))));
   if(c?.source){const a=el('a',c.source.original_name||tr('Original','原件'));a.href=sourceFileHref(c.source);a.target='_blank';a.rel='noopener';row.append(' ',a);}
   if(f.missing&&/\.([ud]s_invert_ft|length_ft)$/.test(f.key))row.append(el('small',tr('Check survey or as-built dimensions. A map-based screening estimate can become available after geometry review.','优先核对测量或竣工资料。采用几何后可查看是否具备依据提出初筛估计。')));
   group.append(row);}
 }
 panel.append(el('p',tr('Use the pin and photos to identify the inlet and outlet of each opening group on the DEM. A site pin alone does not establish flow direction. Get buried elevations from a survey or carry them as explicit screening assumptions.','结合定位点和照片，在 DEM 上辨认各组进口与出口。单个定位点不能确定流向。埋藏涵底需查测量资料，用于初筛的估计须保留假设标记。')));
 if(!(current.map_picks?.inlet?.length&&current.map_picks?.outlet?.length)){
  const request=details(panel,'Cannot locate both portals? Request a field return','还无法辨认两个洞口？导出现场补资料单');
  const message=tr('For each opening group, return labeled inlet and outlet coordinates, horizontal CRS, flow direction, and a marked photo or plan. Give both invert elevations, units and vertical datum if surveyed. Resume this saved project, import the originals and locate the two centers on the map.','请逐组提供标明进出口的中心坐标、平面坐标系、流向和标注照片或平面图。如已测内底，请附两端高程、单位和高程基准。回到这个已保存项目，导入返回的原件，再在地图定位两端。');
  request.append(el('p',message),button('Download portal survey request','下载洞口补测单',()=>{
   const url=URL.createObjectURL(new Blob([current.title+'\n'+message+'\n'],{type:'text/plain;charset=utf-8'}));
   const a=el('a');a.download='portal-request.txt';a.href=url;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }));
 }
 panel.append(button('Locate inlet and outlet on the DEM','在 DEM 上定位进出口',()=>openModelTool('crossing-map')));
 panel.append(el('p',tr('Preview the proposed reach anchors and sections. Check the arrow, opening positions and bank profiles, then adopt the geometry to fill dependent inputs and review the assumptions together.','程序会提出上下游锚点和断面。预览箭头、洞口和岸站剖面，采用后会补齐关联参数，运算前可集中核对假设。')),
  button('Preview reach anchors and sections','预览河段锚点与断面',()=>openModelTool('dem-layout'),'primary'));
}

function renderReturnedInverts(parent,fields){
 const rows=fields.map(f=>{
  const candidates=f.parameter_candidates||[],choices=candidates.filter(c=>c.returned_invert);
  if(!choices.length)return null;
  const first=choices[0];
  const differs=candidates.some(c=>c.source && !c.returned_invert && c.value!==first.value);
  const savedConflict=!f.missing && ['reported','measured','surveyed'].includes(f.evidence_class) && f.value!==first.value;
  return {f,choices,review:choices.length!==1 || differs || savedConflict};
 }).filter(Boolean);
 if(!rows.length)return;
 const card=el('section',undefined,'card');card.id='returned-inverts';parent.append(card);
 card.append(el('h3',tr('Matched survey return','已匹配的补测回传')),el('p',tr('Check group, end, datum and source before adopting returned values.','采用前核对孔组、进出口、基准、数值及资料来源。')));
 for(const {f,choices,review} of rows){
  const grid=el('div');card.append(grid);grid.append(el('strong',tr(f.label.en,f.label.zh)+' · '+tr('Saved','原值')+' '+(f.value??'—')+' ft'));
  for(const c of choices){
   const source=el('a',c.source.original_name);source.href=sourceFileHref(c.source);source.target='_blank';source.rel='noopener';
   grid.append(el('p',c.value+' ft · '+c.datum+' · '+originName(c.evidence_class)+' · '+c.basis),source);
  }
  if(review)grid.append(el('p',tr('Compare the returned records and existing sources for this elevation.','此高程有多个回传记录或与已有资料不同，请逐项核对。'),'warning'),button('Review alternatives','逐项核对候选',()=>revealParameter(f.key)));
 }
 if(rows.every(r=>!r.review)){
  const choices=rows.map(({f,choices:[c]})=>({field:f.key,candidate:c.candidate}));
  card.append(button('Adopt displayed survey returns','采用已核对的回传值',async()=>{
   await save();await api('candidate',{id:current.id,revision:current.revision,selections:choices});await open(current.id);notify(tr('Survey values saved in this revision. Check dependent inputs before computing.','回传值已存入本修订版，请在重算前核对关联输入。'));
  }));
 }
}
function renderRoadSupplement(parent,fields){
 renderReturnedInverts(parent,fields);
 const road=fields.find(f=>f.key==='g.structure.road.width_ft');if(!road)return;
 const inherited=current.parent_revision.inherited_sources;
 const options=(road.parameter_candidates||[]).filter(c=>c.source&&inherited&&!inherited.includes(c.source.sha256)&&c.value!==road.value);
 const card=el('section',undefined,'card');card.id='road-supplement';parent.append(card);
 card.append(el('h3',tr('Update this revision from additional material','用补充资料更新本修订版')),
  button('Add a drawing or site memo','导入图纸或现场说明',()=>openModelTool('site-file-import')));
 if(!inherited){card.append(el('p',tr('The baseline source list is unavailable. Review the road width and source individually.','无法核实基准版的资料清单，请在路宽参数处逐项核对来源。')),
  button('Open width input','打开路宽参数',()=>revealParameter(road.key)));return;}
 if(!options.length){card.append(el('p',tr('A new document with a different road width will appear here for comparison. Other parameters can be updated from the input list.','补充资料中不同于现值的路宽会在此列出。其他参数可从参数清单核对修改。')));return;}
 const out=el('div');out.setAttribute('aria-live','polite');
 const select=field(card,'supplement-source','Road-width source','路宽依据','', 'select',[['','Choose the source','请选择依据'],...options.map(c=>{const t=c.value+' ft · '+(c.source.original_name||c.source.path);return [c.candidate,t,t];})],()=>out.replaceChildren());
 card.append(button('Compare width and road profiles','比较路宽和道路剖面',async()=>{
  if(!select.value)throw Error(tr('Choose a document first.','请先选择资料。'));
  await save();const candidate=select.value,body={id:current.id,revision:current.revision,candidate};
  const v=await api('material-revision-preview',body);out.replaceChildren();
  const source=el('a',v.selected.source.original_name||v.selected.source.path);source.href=sourceFileHref(v.selected.source);source.target='_blank';source.rel='noopener';
  out.append(source,el('blockquote',v.selected.basis),el('p',v.before+' ft ('+originName(v.previous_class)+') → '+v.selected.value+' ft ('+originName(v.selected.evidence_class)+')'),
   el('p',tr('Check whether the stated width is the effective overflow width. Review the road offset and both crest profiles below.','请判断资料宽度能否作为有效越流宽度，并核对道路位置和上下游两条堰顶剖面。')));
  const fmt=value=>{
   if(!Array.isArray(value))return String(value??'—');
   if(!value.length)return '—';
   return value.length+tr(' samples, range ',' 个采样点，范围 ')+Math.min(...value).toFixed(2)+' – '+Math.max(...value).toFixed(2);
  };
  const matrix=details(out,'Compare all affected inputs ('+v.changes.length+')','逐项对照关联输入（'+v.changes.length+'）',true);
  const reasons={independent:tr('Keep and review the independently entered value','保留独立填报值，需单独复核'),competing:tr('Compare competing candidates','需比较多个候选'),needs_evidence:tr('Check the supporting inputs','需补齐推导依据')};
  table(matrix,[tr('Input','输入'),tr('Saved','已保存'),tr('Proposed','建议')],v.changes.map(r=>[tr(r.label.en,r.label.zh)+(r.unit?' ('+r.unit+')':''),fmt(r.before),r.automatic?(JSON.stringify(r.after)===JSON.stringify(r.before)?tr('Same value, recalculated','重算后数值相同'):fmt(r.after)):reasons[r.reason]]));
  drawRoadChange(out,v.changes);
  const sampled=v.changes.filter(r=>Array.isArray(r.before)||Array.isArray(r.after));
  if(sampled.length){
   const raw=details(out,'Inspect individual profile samples','查看剖面逐点原值与建议值');
   raw.append(el('p',tr('Rows follow each profile’s sampling order. Compare the station arrays when the crest locations change.','按各版剖面的采样顺序列出。堰顶位置改变时，请对照两版的站距数组。')));
   for(const r of sampled){const before=r.before||[],after=r.after||[];
    const group=details(raw,r.label.en,r.label.zh);
    table(group,[tr('Sample','采样点'),tr('Saved','原值'),tr('Proposed','建议值')],Array.from({length:Math.max(before.length,after.length)},(_,i)=>[i+1,before[i]??'—',after[i]??'—']));
   }
  }
  if(!v.ready){out.append(el('p',tr('Some values have independent evidence or multiple interpretations. Open the width input, select the source and review the individual dependencies.','部分参数有独立依据或存在多种解释，请从路宽字段采用资料并逐项复核关联参数。'),'warning'),button('Open width input','打开路宽参数',()=>revealParameter(road.key)));return;}
  const apply=button('Adopt width and linked inputs in this revision','仅在本修订版采用路宽及关联参数',async()=>{
   await save();await api('material-revision-apply',{...body,token:v.token,confirmed:true});
   await open(body.id);notify(tr('Saved the road revision. Review calculation inputs before running.','道路修订已保存，请进入参数核对后再计算。'));
  },'primary');apply.id='adopt-road-supplement';out.append(apply);
 }));card.append(out);
}

function drawRoadChange(parent,rows){
 const values=Object.fromEntries(rows.map(r=>[r.key.split('.').at(-1),r]));
 for(const [prefix,en,zh] of [['','Upstream crest','上游堰顶'],['downstream_','Downstream crest','下游堰顶']]){
  const x=values[prefix+'station_ft'],z=values[prefix+'elevation_ft'];
  if(!x||!z)continue;
  const series=['before','after'].filter(k=>Array.isArray(x[k])&&x[k].length>1&&x[k].length===z[k]?.length);
  if(!series.length)continue;
  const xs=series.flatMap(k=>x[k]),zs=series.flatMap(k=>z[k]);
  const minX=Math.min(...xs),maxX=Math.max(...xs),minZ=Math.min(...zs),maxZ=Math.max(...zs);
  const chart=document.createElementNS('http://www.w3.org/2000/svg','svg');chart.setAttribute('viewBox','0 0 700 230');chart.classList.add('chart');chart.setAttribute('aria-label',tr(en,zh));
  parent.append(el('h4',tr(en,zh)),chart);profileGrid(chart,[minX,maxX],minZ,Math.max(minZ+1,maxZ),[40,670,30,190]);
  for(const k of series){const pts=x[k].map((v,i)=>[40+630*(v-minX)/Math.max(0.001,maxX-minX),190-160*(z[k][i]-minZ)/Math.max(1,maxZ-minZ)].join(',')).join(' ');
   svgEl(chart,'polyline',{points:pts,fill:'none',stroke:k==='before'?'#565e64':'#00767d','stroke-width':2,'stroke-dasharray':k==='before'?'6 4':'none'});}
  parent.append(el('small',tr('Dashed grey = saved. Teal = proposed. Horizontal distance and elevation in feet.','灰色虚线为原值，蓝绿色为建议值；横距和高程单位均为英尺。')));
 }
}

function renderSources(parent){
 const a=current.acquisition,card=el('section',undefined,'card source-hub');parent.append(card);
 card.append(el('h2',tr('Find, import and inspect source material','查找、导入与核查资料')),el('p',tr('Local search and extraction retain the original files and identify parameter candidates. Automatic draft preparation fills supported values and labels estimates for the final review. Conflicting sources remain available for your choice.','在本机查询和提取资料，保留原件并识别参数候选。自动准备草稿会填入有依据的数值，并标注估计项供最终核对；来源冲突集中保留供选择。')));
 const actions=el('div',undefined,'actions');card.append(actions);
 if(!current.native)actions.append(button(a?'Retry public search + analyze':'Find available data automatically',a?'重试公开查询并解析':'自动查找可用资料',async()=>{await save();await api('acquire',{id:current.id});await open(current.id);},'primary'),button('Reanalyze saved material','重新解析已存资料',async()=>{await save();await api('analyze',{id:current.id});await open(current.id);}));
 const imports=details(card,'Add PDFs, photos, survey CSV or a local site folder','添加 PDF、照片、测量 CSV 或本站资料文件夹',!a);
 imports.id='site-file-import';
 const fi=field(imports,'attachments','Choose source files (multiple allowed)','选择资料（可多选）','','file');fi.multiple=true;fi.accept='.pdf,.jpg,.jpeg,.png,.tif,.tiff,.csv,.txt,.xml,.docx,.kml,.kmz';
 const folderFiles=field(imports,'site-source-directory','Or inspect a folder of site originals','也可选取现场原件目录','','file');folderFiles.webkitdirectory=true;folderFiles.multiple=true;
 let selectedFolder=[];
 const inventory=el('p');inventory.setAttribute('aria-live','polite');imports.append(inventory);
 folderFiles.onchange=()=>{
  selectedFolder=[];fi.value='';
  const files=Array.from(folderFiles.files),supported=files.filter(f=>fi.accept.split(',').some(ext=>f.name.toLowerCase().endsWith(ext)));
  const same=new Set(),repeated=new Set();
  for(const f of supported){const name=f.name.toLowerCase();if(same.has(name))repeated.add(name);same.add(name);}
  if(repeated.size){inventory.textContent=tr('Choose the intended files individually. Duplicate names: ','有同名文件，请单独选择正确原件：')+Array.from(repeated).join(', ');return;}
  selectedFolder=supported;
  inventory.textContent=tr('Ready to import ','待导入 ')+supported.length+' · '+tr('Skipped unsupported files ','略过不支持的文件 ')+(files.length-supported.length)+' · '+supported.map(f=>f.name).join(', ');
 };
 fi.onchange=()=>{folderFiles.value='';selectedFolder=[];inventory.textContent=Array.from(fi.files).map(f=>f.name).join(', ');};
 imports.append(button('Save and extract selected files','保存并解析所选资料',async()=>{await save();const chosen=selectedFolder.length?selectedFolder:[...fi.files];if(!chosen.length)throw Error(tr('Select files first.','请先选择文件。'));let batch=[],bytes=0;for(const f of chosen){if(f.size>15000000)throw Error(tr('Each file must be at most 15 MB. Use the single-site folder import for many files.','单文件不能超过 15 MB，多份资料可使用本站文件夹导入。'));batch.push(f);bytes+=f.size;}if(bytes>48000000)throw Error(tr('Selection exceeds 48 MB; use the local site folder below.','所选资料超过 48 MB，请使用下方本机资料文件夹导入。'));await api('attach',{id:current.id,files:await encodeFiles(batch)});await open(current.id);}));
 if(!current.native){const path=field(imports,'material-folder','Or paste the existing single-site folder path','或粘贴已下载的本站资料文件夹路径');imports.append(button('Import this folder and analyze','导入此文件夹并解析',async()=>{await save();await api('sources/folder',{id:current.id,revision:current.revision,path:path.value});await open(current.id);}));imports.append(el('small',tr('Supported source files only, up to 100 files / 100 MB. Original files are unchanged; native HEC-RAS models are not imported here.','只导入支持的资料格式，最多 100 份／100 MB。原件不变，此处不会导入 HEC-RAS 模型。')),button('Download optional parameter CSV template','下载可选参数 CSV 模板',downloadParameterTemplate));}
 if(!current.native){const record=details(card,'Import another public USGS catalog record','导入其他公开 USGS 资料记录');const url=field(record,'catalog-url','ScienceBase catalog item URL','ScienceBase 公开目录页面网址');record.append(el('p',tr('Use an item page from the search results or a known source. Downloads are bounded to supported document files; check site/event/group applicability. Archives or browser verification remain explicit handoffs.','可使用查询结果或已知资料的目录页面。下载受大小和格式限制，仍须核对地点、工况及涵孔组；压缩包及浏览器验证会明确提示手动接续。')),button('Download available documents and analyze','下载可用文档并解析',async()=>{await save();await api('catalog-import',{id:current.id,revision:current.revision,url:url.value});await open(current.id);}));if(current.catalog_result)table(record,[tr('File','文件'),tr('Status','状态'),tr('Detail','详情')],current.catalog_result.files.map(r=>[r.name,sourceStatus(r.status),r.error||r.reason||'']));}
 if(a){
  card.append(el('p',`${a.documents.length} `+tr('documents attempted','份资料已尝试解析')+` · ${a.documents.filter(d=>d.status==='EXTRACTION_FAILED').length} `+tr('failed (originals retained)','份提取失败（原件保留）')+` · ${a.candidates.length} `+tr('source candidates','项来源候选')+` · ${a.surveys.reduce((n,s)=>n+s.points.length,0)} `+tr('survey points','个测点'),'status'));
  const visual=a.documents.filter(d=>d.visual_only);
  if(visual.length){const visualPanel=details(card,'Photos for visual inspection ('+visual.length+')','需目视核对的照片（'+visual.length+'）');
   visualPanel.append(el('p',tr('Text recognition found no legible labels. Open the originals to check visible features such as the number of openings. Use dimensions or elevations only where their scale and datum are documented.','文字识别未找到可读标注。打开原图可核对孔数等外观特征。采用尺寸或高程时需另核对比例和基准。')));
   for(const doc of visual){const a=el('a',doc.source.original_name,'link');a.href=sourceFileHref(doc.source);a.target='_blank';a.rel='noopener';visualPanel.append(a);}
  }
  if(a.auto_filled?.length)card.append(el('p',tr('Filled missing source-reported values: ','已填入空白资料值：')+a.auto_filled.join(', '),'status'));
  showAcquisitionGaps(card,a);
  renderFisSelection(card);
  const attempts=details(card,'Public search coverage and attempts','公开查询范围与尝试记录',false);
  attempts.append(el('p',tr('Searches the USGS catalog, the supported Massachusetts crossing inventory, and effective FEMA FIS reports for the coordinate-matched community. Review source coverage, river location and applicable map revisions.','查询 USGS 目录、已支持的 Massachusetts 过水设施资料表，以及坐标所在社区的有效 FEMA FIS 报告。请核查来源覆盖范围、河流位置和相关地图修订。')));
  for(const r of a.attempts){const row=el('p',r.route+' · '+sourceStatus(r.status));if(r.error)row.append(el('small',' · '+r.error));if(r.url){const link=el('a',tr(' Open source ↗',' 查看来源 ↗'));link.href=r.url;link.target='_blank';link.rel='noreferrer';row.append(link);}attempts.append(row);}
  for(const r of a.links){const link=el('a',r.title);link.href=r.url;link.target='_blank';link.rel='noreferrer';const row=el('p');row.append(link);attempts.append(row);}
  const candidates=details(card,'Review source candidates ('+a.candidates.length+')','核查资料候选（'+a.candidates.length+'）',false);
  for(const f of current.intake?.fields||[]){if(!a.candidates.some(c=>c.field===f.key))continue;const row=el('div',undefined,'source-candidate');row.append(el('strong',tr(f.label.en,f.label.zh)),el('p',tr('Current: ','当前值：')+(format(f.value,f.kind)||'—')));for(const choice of f.parameter_candidates.filter(c=>c.source)){const part=el('div');part.append(el('p',format(choice.value,f.kind)+' · '+choice.basis),button('Review / use this candidate','查看／采用此候选',async()=>focusParameter(f.key)));row.append(part);}candidates.append(row);}
  const partial=a.documents.filter(doc=>doc.coverage?.status==='PARTIAL'||(doc.warnings||[]).some(w=>typeof w==='string'&&/Only the first|OCR failed/.test(w)));
  if(partial.length)card.append(el('p',partial.length+tr(' documents need page review. Expand Original documents and extracted text for page coverage and OCR warnings.',' 份资料需要原文核查。展开“原件与提取文本”，查看已读页数及 OCR 提示。'),'warning'));
  const docs=details(card,'Original documents and extracted text','原件与提取文本',false);
  for(const doc of a.documents){const f=doc.source,box=details(docs,f.original_name||f.path.split('/').at(-1),f.original_name||f.path.split('/').at(-1));const link=el('a',tr('Open original ↗','查看原件 ↗'));link.href=sourceFileHref(f);link.target='_blank';box.append(link,el('p',(doc.method||'')+' · '+sourceStatus(doc.status)));if(doc.coverage)box.append(el('p',doc.coverage.inspected_pages+' / '+doc.coverage.total_pages+tr(' pages inspected; OCR attempts ',' 页已尝试解析；OCR 尝试 ')+doc.coverage.ocr_pages));if(doc.error)box.append(el('p',doc.error,'warning'));for(const w of doc.warnings||[])box.append(el('p',typeof w==='string'?w:JSON.stringify(w),'warning'));if(doc.text)box.append(el('pre',doc.text));}
  for(const survey of a.surveys)renderSurvey(card,survey);
 }else if(current.attachments.length){const docs=details(card,'Saved source files','已保存的资料');for(const f of current.attachments){const p=el('p'),link=el('a',f.original_name||f.path.split('/').at(-1));link.href=sourceFileHref(f);link.target='_blank';p.append(link);docs.append(p);}}
}
function renderSurvey(parent,s){
 const key=s.source.sha256,box=details(parent,'Survey: '+s.source.original_name+' · '+s.points.length+' points','测量：'+s.source.original_name+' · '+s.points.length+' 个点',false),context=s.context||{};
 box.append(el('p',sourceStatus(s.status)),el('p',context.basis||tr('Coordinate reference, units and datum remain unresolved.','坐标系、单位和基准尚未明确。')));
 const settings=details(box,'Coordinate / column interpretation','坐标／列名解释',!s.context),grid=el('div',undefined,'grid');settings.append(grid);
 const crs=field(grid,'survey-crs-'+key,'Projected CRS','投影坐标系',context.horizontal_crs||''),unit=field(grid,'survey-unit-'+key,'Survey elevation unit','测量高程单位',context.vertical_unit||'','select',[['','Choose','请选择'],['m','Metres','米'],['US survey foot','US survey foot','美制测量英尺'],['international foot','International foot','国际英尺']]),datum=field(grid,'survey-datum-'+key,'Survey elevation datum','测量高程基准',context.vertical_datum||'');
 const cols={};for(const[k,en,zh]of [['id','Point ID','点号'],['x','Easting / X','东坐标／X'],['y','Northing / Y','北坐标／Y'],['z','Elevation / Z','高程／Z'],['code','Code / description','代码／说明']])cols[k]=field(grid,'column-'+key+k,en,zh,s.columns[k]||'','select',[['','Unassigned','未指定'],...s.headers.map(h=>[h,h,h])]);
 settings.append(button('Use this coordinate / column interpretation','采用此坐标／列名解释',async()=>{await save();await api('sources/survey',{id:current.id,revision:current.revision,source:key,settings:{horizontal_crs:crs.value,vertical_unit:unit.value,vertical_datum:datum.value,columns:Object.fromEntries(Object.entries(cols).map(([k,v])=>[k,v.value]))}});await open(current.id);}));
 const points=details(box,'Point table / identify dimension or invert endpoints','测点表／指认尺寸端点或涵底点',false);
 const selection=field(points,'point-ids-'+key,'Selected point IDs (comma separated; map clicks append IDs)','已选点号（逗号分隔，点击地图测点可添加）');
 const fields=(current.intake?.fields||[]).filter(f=>/\.(us_invert_ft|ds_invert_ft|length_ft|span_ft|width_ft)$/.test(f.key));
 const target=field(points,'point-target-'+key,'Use these points to propose','用这些点提出候选','', 'select',[['','Choose a parameter','选择参数'],...fields.map(f=>[f.key,f.label.en,f.label.zh])]);
 points.append(el('p',tr('One actual interior invert point for elevation; two feature endpoints for plan distance. Crown points are NOT invert points. The resulting candidate is not adopted automatically.','高程需选择一个真实内部涵底点；平面距离需选择两个特征端点。管顶点不是涵底点。计算得到的候选不会自动采用。'),'warning'),button('Create candidate from identified points','由已指认测点生成候选',async()=>{await save();await api('sources/points',{id:current.id,revision:current.revision,source:key,points:selection.value.split(/[,，\s]+/).filter(Boolean),field:target.value});await open(current.id);focusParameter(target.value);}));
 table(points,[tr('Point','点号'),'X','Y','Z',tr('Code','代码')],s.points.map(p=>[p.id,p.x,p.y,p.z,p.code]));
 if(s.invalid_rows?.length)points.append(el('p',tr('Invalid source rows skipped: ','跳过无效原始行：')+s.invalid_rows.join(', '),'warning'));
}
function drawSurveyOverlay(svg,data,xy,useAnchor){
 for(const p of data.survey_points||[]){const[x,y]=xy(p.xy);if(x<0||x>650||y<0||y>650)continue;const node=svgEl(svg,'circle',{cx:x,cy:y,r:4,fill:'#06756d',stroke:'white','stroke-width':1,tabindex:0,role:'button','aria-label':p.id+' '+p.code+' Z='+p.z});const title=svgEl(node,'title',{});title.textContent=p.id+' '+p.code+' · Z '+p.z+' '+p.unit+' '+p.datum;const label=svgEl(svg,'text',{x:x+5,y:y-5,fill:'#044f49','font-size':10,'pointer-events':'none'});label.textContent=p.id;
  const pick=e=>{e.stopPropagation();if(busy)return;if(useAnchor?.(p))return;const input=document.getElementById('point-ids-'+p.source);if(input){const ids=input.value.split(/[,，\s]+/).filter(Boolean);if(!ids.includes(p.id))ids.push(p.id);input.value=ids.join(', ');}notify(tr('Survey point selected: ','已选择测点：')+p.id+' · '+p.code+' · Z '+p.z+' '+p.unit+' '+p.datum+tr('. Review in the source survey table.','. 请在资料测点表中核查。'));node.setAttribute('fill','#b05d00');};node.onclick=pick;node.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pick(e);}};
 }
}
