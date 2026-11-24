// Browser acceptance of the normal entry and recipient controls. Only the release machine needs Chromium.
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  const {url, project, decision, run_id, mode} = JSON.parse(fs.readFileSync(0, 'utf8'));
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
    await until("!!document.querySelector('#accept-agreement')");
    await evaluate("document.querySelector('#accept-site').value='yes';document.querySelector('#accept-site').dispatchEvent(new Event('input',{bubbles:true}))");
    await until("document.querySelector('#accept-agreement').value==='yes'");
    const selector='[data-project-id="'+project+'"]';
    await until('!!document.querySelector('+JSON.stringify(selector)+')');
    await evaluate('document.querySelector('+JSON.stringify(selector)+').closest("details").open=true');
    await click(selector+' button');
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
