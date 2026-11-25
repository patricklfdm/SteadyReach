// Browser acceptance of the normal entry and recipient controls. Only the release machine needs Chromium.
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const {url, project, decision, run_id, mode} = input;
  const executables = [process.env.STEADYREACH_RELEASE_BROWSER];
  for (const root of [process.env.PROGRAMFILES, process.env['PROGRAMFILES(X86)']].filter(Boolean)) {
    executables.push(path.join(root, 'Microsoft/Edge/Application/msedge.exe'),
                     path.join(root, 'Google/Chrome/Application/chrome.exe'));
  }
  const executable = executables.find(p => p && fs.existsSync(p));
  if (!executable) throw Error('Set STEADYREACH_RELEASE_BROWSER to Chrome or Edge for page acceptance');
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'steadyreach-release-'));
  const child = spawn(executable, ['--headless=new','--no-first-run','--no-default-browser-check',
    '--disable-background-networking','--remote-debugging-pipe','--user-data-dir='+profile],
    {stdio:['ignore','ignore','ignore','pipe','pipe'],windowsHide:true});
  let n = 0, session, buffer = '';
  const requests = new Map();
  const closed = new Promise(resolve => child.once('close', resolve));
  child.stdio[4].setEncoding('utf8');
  child.stdio[4].on('data', chunk => {
    buffer += chunk;
    let end;
    while ((end=buffer.indexOf('\0'))>=0) {
      const message=JSON.parse(buffer.slice(0,end));
      buffer=buffer.slice(end+1);
      const pending=requests.get(message.id);
      if (!pending) continue;
      requests.delete(message.id);
      message.error ? pending.reject(Error(message.error.message)) : pending.resolve(message.result);
    }
  });
  function send(method,params={}) {
    const id=++n;
    return new Promise((resolve,reject)=>{
      requests.set(id,{resolve,reject});
      child.stdio[3].write(JSON.stringify({id,method,params,sessionId:session})+'\0');
    });
  }
  async function evaluate(expression) {
    const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);
    return result.result.value;
  }
  async function until(expression, attempts=240) {
    for(let step=0;step<attempts;step++){
      if(await evaluate(expression))return;
      await delay(250);
    }
    throw Error('Page did not reach '+expression+'; '+await evaluate('document.body.innerText.slice(-1200)'));
  }
  async function click(selector) {
    await until('!!document.querySelector('+JSON.stringify(selector)+')');
    await evaluate('document.querySelector('+JSON.stringify(selector)+').click()');
  }
  try {
    const tab=await send('Target.createTarget',{url:'about:blank'});
    session=(await send('Target.attachToTarget',{targetId:tab.targetId,flatten:true})).sessionId;
    await send('Page.enable');
    await send('Page.navigate',{url});
    if(mode==='recipient-copy'){
      await until('document.readyState==="complete" && document.querySelector("main")?.textContent.includes('+JSON.stringify(run_id)+')');
      const links=await evaluate('Array.from(document.querySelectorAll("a")).map(a=>a.getAttribute("href"))');
      if(!links.some(v=>v.endsWith('Report_EN.pdf'))||!links.some(v=>v.startsWith('Minimal/HEC_RAS/')&&v.endsWith('.prj')))throw Error('Missing recipient shortcuts');
      await click('nav a');
      await until('location.pathname.endsWith("Start_zh-CN.html") && document.querySelector("main")?.textContent.includes('+JSON.stringify(run_id)+')');
      await until('!!document.querySelector(\'a[href="Complete/Reports/Report_CN.pdf"]\')');
      await click('nav a');
      await until('location.pathname.endsWith("Start_EN.html") && !!document.querySelector("main")');
      console.log('Offline recipient opened both local entry pages for '+run_id);return;
    }
    await until("!!document.querySelector('#accept-agreement')");
    await evaluate("document.querySelector('#accept-site').value='yes';document.querySelector('#accept-site').dispatchEvent(new Event('input',{bubbles:true}))");
    await until("document.querySelector('#accept-agreement').value==='yes'");
    const selector='[data-project-id="'+project+'"]';
    await until('!!document.querySelector('+JSON.stringify(selector)+')');
    await evaluate('document.querySelector('+JSON.stringify(selector)+').closest("details").open=true');
    await click(selector+' button');
    async function buttonByName(label, root='document') {
      const b='Array.from('+root+'.querySelectorAll("button")).find(b=>b.textContent.trim()==='+JSON.stringify(label)+' && !b.disabled)';
      await until('!busy && !!('+b+')');
      await evaluate('(()=>{const b='+b+';for(let p=b;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;b.click()})()');
      await until('!busy');
    }
    async function fieldValue(id,value){
      await until('!busy && !!document.getElementById('+JSON.stringify(id)+')');
      await evaluate('(()=>{const f=document.getElementById('+JSON.stringify(id)+');for(let p=f;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true; f.value='+JSON.stringify(String(value))+';f.dispatchEvent(new Event(f.tagName==="SELECT"?"change":"input",{bubbles:true}));})()');
      await until('!busy');
    }
    async function upload(files) {
      await until('!busy && !!document.querySelector("#attachments")');
      await evaluate('for(let p=document.querySelector("#attachments");p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true');
      const {root}=await send('DOM.getDocument');
      const {nodeId}=await send('DOM.querySelector',{nodeId:root.nodeId,selector:'#attachments'});
      await send('DOM.setFileInputFiles',{nodeId,files});
      await buttonByName('Save and extract selected files');
      await until('!busy && current?.acquisition?.documents?.some(d=>d.source.original_name==='+JSON.stringify(path.basename(files.at(-1)))+') && !!document.getElementById("attachments")',1400);
    }
    if(mode==='condition-review'||mode==='wet-revision'){
      await until('!!document.querySelector("[id^=qa-wet-]")');
      await buttonByName('Inspect computed section');
      await until('!!document.querySelector("#qa-tool-atlas details[open] svg image")');
      await until('Array.from(document.querySelectorAll("#qa-tool-atlas details[open] svg")).some(s=>s.textContent.includes("ft")||s.getAttribute("aria-label")?.includes("profile"))');
      if(mode==='wet-revision'){
        const station=await evaluate('document.querySelector("[id^=qa-wet-]").value');
        await buttonByName('Revise this wet section');
        await until('document.querySelector("#repair-section option:checked")?.textContent.includes("RS "+Number('+JSON.stringify(station)+'))');
        const width=Number(await evaluate('document.querySelector("#repair-width_ft").value'));
        await fieldValue('repair-width_ft',Math.ceil(width+10));
        await buttonByName('Preview DEM resampling');
        await buttonByName('Use this DEM preview');
        const bank=await evaluate('current.intake.fields.find(f=>f.missing && f.key.endsWith(".bank_stations_ft") && f.parameter_candidates.length===1)?.key');
        if(!bank)throw Error('Expected one reviewed bank candidate for the widened section');
        await buttonByName('Use this candidate','document.getElementById('+JSON.stringify('input-'+bank)+').closest("section.parameter")');
        console.log(await evaluate('current.id'));return;
      }
      await click('#result-tab-overview');
      await buttonByName('Inspect native roadway discharge');
      await until('document.querySelector("#qa-tool-native").innerText.includes("Unknown") && document.querySelector("#qa-tool-native").innerText.includes('+JSON.stringify(run_id)+')');
      await click('#result-tab-overview');
      await buttonByName('Request inlet and outlet elevations');
      await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:input.download});
      await buttonByName('Download invert survey worksheet');
      const file=path.join(input.download,'invert_'+run_id+'.csv');
      for(let i=0;i<80&&!fs.existsSync(file);i++)await delay(100);
      if(!fs.existsSync(file))throw Error('Worksheet was not downloaded');
      await buttonByName('Pause until survey returns');
      await until('current?.iteration_choice?.choice==="wait"');
      console.log(file);return;
    }
    if(mode==='survey-return'){
      await until('current?.iteration_choice?.choice==="wait"');
      await buttonByName('Request inlet and outlet elevations');
      await buttonByName('Import returned survey in a new revision');
      await upload(input.files);
      await until('!!document.querySelector("#returned-inverts")');
      await buttonByName('Adopt displayed survey returns');
      console.log(await evaluate('current.id'));return;
    }
    if(mode==='edition-transfer'){
      await until('current?.comparison?.status==="COMPARISON_NOT_ACCEPTANCE"');
      await until('document.querySelector(".result-assessment")?.textContent.includes("Midway_Channel_Bridge_Hydraulic_Analysis.docx")');
      await buttonByName('Keep previous calculation');
      await buttonByName('Open selected baseline');
      await until('current?.id==='+JSON.stringify(input.parent));
      await buttonByName('← Projects');
      await until('!!document.querySelector('+JSON.stringify(selector)+')');
      await click(selector+' button');
      await buttonByName('Resume review of this edition');
      await buttonByName('Use this revision');
      await buttonByName('Prepare handoff for the selected use');
      await until('document.querySelector("#transfer-status code")?.textContent.includes("Handoff_")');
      console.log(await evaluate('document.querySelector("#transfer-status code").textContent'));return;
    }
    if(mode==='prepare-crossing'){
      await upload(input.files);
      await until('document.querySelectorAll("#first-crossing a[href]").length>=6');
      const originals=await evaluate('Promise.all(Array.from(document.querySelectorAll("#first-crossing details:first-of-type a")).map(async a=>{const r=await fetch(a.href);return {name:a.textContent,ok:r.ok,bytes:(await r.arrayBuffer()).byteLength};}))');
      if(!input.files.every(f=>originals.some(r=>r.name===path.basename(f)&&r.ok&&r.bytes===fs.statSync(f).size)))throw Error('One or more original file links failed');
      for(const [key,value] of Object.entries(input.dimensions)){
        await fieldValue('input-'+key,value);
        await fieldValue('origin-'+key,key.endsWith('width_ft')?'assumed':'reported');
      }
      await buttonByName('Save all changes');
      await buttonByName('Locate inlet and outlet on the DEM');
      await until('!!document.querySelector("#crossing-map svg.interactive-map")');
      await fieldValue('wall-gap',input.gap);
      for(const [side,coords] of Object.entries(input.openings)){
        await buttonByName('Pick '+side+' center');
        await evaluate('(()=>{const svg=document.querySelector("#crossing-map svg.interactive-map");svg.scrollIntoView({block:"center",behavior:"instant"});const r=svg.getBoundingClientRect(),[x,y]='+JSON.stringify(coords)+',[x0,y0,x1,y1]=mapData.bounds;svg.dispatchEvent(new MouseEvent("click",{bubbles:true,clientX:r.left+(x-x0)/(x1-x0)*r.width,clientY:r.top+(y1-y)/(y1-y0)*r.height}));})()');
        await until('current.map_picks?.'+side+'?.length===1 && !mapDirty');
      }
      await buttonByName('Save opening picks and preview automatic layout');
      await fieldValue('auto-reach-length',input.length);
      await fieldValue('auto-width-limit',input.maximum);
      await buttonByName('Propose anchors and sections');
      const approval='Array.from(document.querySelectorAll("#dem-layout label.check")).find(l=>l.textContent.includes("I checked direction"))?.querySelector("input")';
      await until('!!('+approval+')');
      await evaluate('('+approval+').click()');
      await buttonByName('Adopt and review calculation inputs');
      await until('current.intake.section_count>=4 && document.querySelector("#confirm-run")');
      console.log('Uploaded originals, identified opening centers on the map, previewed DEM reach anchors and adopted the layout through the page.');return;
    }
    if(mode==='supplement'){
      await until('!!document.querySelector("#result-tab-overview")');
      await click('#result-tab-review');
      await buttonByName('Create editable revision');
      await until('current?.id!=='+JSON.stringify(project)+' && !!document.querySelector("#road-supplement")');
      await upload(input.files);
      const option='Array.from(document.querySelector("#supplement-source")?.options||[]).find(o=>o.textContent.includes('+JSON.stringify(path.basename(input.files[0]))+'))';
      await until('!!('+option+')');
      await fieldValue('supplement-source',await evaluate('('+option+').value'));
      await buttonByName('Compare width and road profiles');
      await until('document.querySelectorAll("#road-supplement svg.chart").length===2 && !!document.querySelector("#adopt-road-supplement")');
      await until('Array.from(document.querySelectorAll("#road-supplement summary")).some(s=>s.textContent==="Inspect individual profile samples" && !s.parentElement.open)');
      await click('#adopt-road-supplement');
      await until('!busy && !document.querySelector("#adopt-road-supplement") && document.getElementById("input-g.structure.road.width_ft")?.value==="26"');
      console.log(await evaluate('current.id'));return;
    }
    if(mode==='solve'){
      const review="Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Review calculation inputs →' && !b.disabled)";
      await until('!!('+review+')');
      await evaluate('('+review+').click()');
      await until("!!document.querySelector('#confirm-parameters') && document.querySelector('#confirm-run').disabled");
      await until("document.body.textContent.includes('Delivery conditions for this run') && document.body.textContent.includes('Source required')");
      await click('#confirm-parameters');
      await until("document.querySelector('#confirm-run')?.disabled===false");
      await click('#confirm-run');
      await until("!!document.querySelector('#result-tab-overview')",2400);
      console.log('Confirmed frozen inputs and opened native results through the calculation page.');
      return;
    }
    await until('document.querySelector(".result-assessment")?.innerText.includes('+JSON.stringify(decision.en)+')');
    await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='简体中文').click()");
    await until('document.querySelector(".result-assessment")?.innerText.includes('+JSON.stringify(decision.zh)+')');
    await click('#result-tab-delivery');
    await until("Array.from(document.querySelectorAll('button')).some(b=>b.textContent.includes('校验双包并生成收件人说明'))");
    await evaluate("const b=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('校验双包并生成收件人说明'));for(let n=b.parentElement;n;n=n.parentElement)if(n.tagName==='DETAILS')n.open=true;b.click()");
    await until("document.body.innerText.includes('已保存中英文打开说明') && document.body.innerText.includes("+JSON.stringify(run_id)+")");
    console.log('Chromium page passed: purpose controls, selected edition, both verdicts and recipient export.');
  } finally {
    if(child.exitCode===null && !child.killed){
      session=undefined;
      void send('Browser.close').catch(()=>{});
      const kill=setTimeout(()=>child.kill(),3000);
      await closed;
      clearTimeout(kill);
    }
    if(path.dirname(profile)===path.resolve(os.tmpdir()) && path.basename(profile).startsWith('steadyreach-release-'))
      fs.rmSync(profile,{recursive:true,force:true,maxRetries:6,retryDelay:200});
  }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
