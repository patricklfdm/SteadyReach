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
function downloadParameterTemplate(){
 const fields=current.intake?.fields||[];const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';
 const csv=['field,value,unit,datum,evidence_class,source',...fields.map(f=>[f.key,'',f.unit||'','','reported',''].map(quote).join(','))].join('\r\n');
 const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));const a=el('a');a.href=url;a.download='parameter_import.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notify(tr('Template downloaded. Empty rows are ignored; existing project values will not be overwritten.','模板已下载。空行会忽略，导入后不会自动覆盖已有参数。'));
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
  await saveAll();
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

function renderSources(parent){
 const a=current.acquisition,card=el('section',undefined,'card source-hub');parent.append(card);
 card.append(el('h2',tr('Find, import and inspect source material','查找、导入与核查资料')),el('p',tr('Local search and extraction retain the original files and identify parameter candidates. Automatic draft preparation fills supported values and labels estimates for the final review. Conflicting sources remain available for your choice.','在本机查询和提取资料，保留原件并识别参数候选。自动准备草稿会填入有依据的数值，并标注估计项供最终核对；来源冲突集中保留供选择。')));
 const actions=el('div',undefined,'actions');card.append(actions);
 if(!current.native)actions.append(button(a?'Retry public search + analyze':'Find available data automatically',a?'重试公开查询并解析':'自动查找可用资料',async()=>{await save();await api('acquire',{id:current.id});await open(current.id);},'primary'),button('Reanalyze saved material','重新解析已存资料',async()=>{await save();await api('analyze',{id:current.id});await open(current.id);}));
 const imports=details(card,'Add PDFs, photos, survey CSV or a local site folder','添加 PDF、照片、测量 CSV 或本站资料文件夹',!a);
 const fi=field(imports,'attachments','Choose source files (multiple allowed)','选择资料（可多选）','','file');fi.multiple=true;fi.accept='.pdf,.jpg,.jpeg,.png,.tif,.tiff,.csv,.txt,.xml,.docx,.kml,.kmz';
 imports.append(button('Save and extract selected files','保存并解析所选资料',async()=>{await save();if(!fi.files.length)throw Error(tr('Select files first.','请先选择文件。'));const chosen=[...fi.files];let batch=[],bytes=0;for(const f of chosen){if(f.size>15000000)throw Error(tr('Each file must be at most 15 MB. Use the single-site folder import for many files.','单文件不能超过 15 MB，多份资料可使用本站文件夹导入。'));batch.push(f);bytes+=f.size;}if(bytes>48000000)throw Error(tr('Selection exceeds 48 MB; use the local site folder below.','所选资料超过 48 MB，请使用下方本机资料文件夹导入。'));await api('attach',{id:current.id,files:await encodeFiles(batch)});await open(current.id);}));
 if(!current.native){const path=field(imports,'material-folder','Or paste the existing single-site folder path','或粘贴已下载的本站资料文件夹路径');imports.append(button('Import this folder and analyze','导入此文件夹并解析',async()=>{await save();await api('sources/folder',{id:current.id,revision:current.revision,path:path.value});await open(current.id);}));imports.append(el('small',tr('Supported source files only, up to 100 files / 100 MB. Original files are unchanged; native HEC-RAS models are not imported here.','只导入支持的资料格式，最多 100 份／100 MB。原件不变，此处不会导入 HEC-RAS 模型。')),button('Download optional parameter CSV template','下载可选参数 CSV 模板',downloadParameterTemplate));}
 if(!current.native){const record=details(card,'Import another public USGS catalog record','导入其他公开 USGS 资料记录');const url=field(record,'catalog-url','ScienceBase catalog item URL','ScienceBase 公开目录页面网址');record.append(el('p',tr('Use an item page from the search results or a known source. Downloads are bounded to supported document files; check site/event/group applicability. Archives or browser verification remain explicit handoffs.','可使用查询结果或已知资料的目录页面。下载受大小和格式限制，仍须核对地点、工况及涵孔组；压缩包及浏览器验证会明确提示手动接续。')),button('Download available documents and analyze','下载可用文档并解析',async()=>{await saveAll();await api('catalog-import',{id:current.id,revision:current.revision,url:url.value});await open(current.id);}));if(current.catalog_result)table(record,[tr('File','文件'),tr('Status','状态'),tr('Detail','详情')],current.catalog_result.files.map(r=>[r.name,sourceStatus(r.status),r.error||r.reason||'']));}
 if(a){
  card.append(el('p',`${a.documents.length} `+tr('documents attempted','份资料已尝试解析')+` · ${a.documents.filter(d=>d.status==='EXTRACTION_FAILED').length} `+tr('failed (originals retained)','份提取失败（原件保留）')+` · ${a.candidates.length} `+tr('source candidates','项来源候选')+` · ${a.surveys.reduce((n,s)=>n+s.points.length,0)} `+tr('survey points','个测点'),'status'));
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
  for(const doc of a.documents){const f=doc.source,box=details(docs,f.original_name||f.path.split('/').at(-1),f.original_name||f.path.split('/').at(-1));const link=el('a',tr('Open original ↗','查看原件 ↗'));link.href='file/'+f.path;link.target='_blank';box.append(link,el('p',(doc.method||'')+' · '+sourceStatus(doc.status)));if(doc.coverage)box.append(el('p',doc.coverage.inspected_pages+' / '+doc.coverage.total_pages+tr(' pages inspected; OCR attempts ',' 页已尝试解析；OCR 尝试 ')+doc.coverage.ocr_pages));if(doc.error)box.append(el('p',doc.error,'warning'));for(const w of doc.warnings||[])box.append(el('p',typeof w==='string'?w:JSON.stringify(w),'warning'));if(doc.text)box.append(el('pre',doc.text));}
  for(const survey of a.surveys)renderSurvey(card,survey);
 }else if(current.attachments.length){const docs=details(card,'Saved source files','已保存的资料');for(const f of current.attachments){const p=el('p'),link=el('a',f.original_name);link.href='file/'+f.path;link.target='_blank';p.append(link);docs.append(p);}}
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
