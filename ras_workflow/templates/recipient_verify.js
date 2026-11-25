// Offline copy check. The browser grants read access only to the selected directory.
(()=>{
 const input=document.getElementById('verify-directory'),status=document.getElementById('verify-status');
 const tr=(en,zh)=>document.documentElement.lang==='zh-CN'?zh:en;
 const expected={Complete:input.dataset.complete,Minimal:input.dataset.minimal};
 async function hash(file){
  const bytes=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());
  return Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
 }
 input.addEventListener('change',async()=>{
  const files=new Map();input.disabled=true;status.dataset.state='checking';let current='';
  try{
   if(!globalThis.crypto?.subtle)throw Error(tr('Open the local start page in Edge or Chrome.','请用 Edge 或 Chrome 打开本地入口。'));
   for(const file of input.files){
    const parts=file.webkitRelativePath.split('/');
    if(parts.length<2)throw Error(tr('Select the whole handoff folder.','请选择整个交接目录。'));
    const path=parts.slice(1).join('/');
    if(files.has(path))throw Error(tr('Duplicate path','重复路径')+' · '+path);
    files.set(path,file);
   }
   const seen=new Set();
   function required(path){
    current=path;
    const file=files.get(path);
    if(!file)throw Error(tr('Missing file','缺少文件')+' · '+path);
    seen.add(path);return file;
   }
   async function check(path,sha,size){
    const file=required(path);
    if((size!=null&&file.size!==size)||await hash(file)!==sha)
     throw Error(tr('File changed or belongs to a different edition','文件已变化或版本不符')+' · '+path);
   }
   const receiptText=await required('HANDOFF.json').text();
   const receipt=JSON.parse(receiptText);
   if(receipt.run_id!==input.dataset.run)throw Error(tr('Different calculation','计算版本不符')+' · HANDOFF.json');
   const guides={};
   for(const name of ['Start_EN.html','Start_zh-CN.html']){
    guides[name]=receipt.pages[name];
    await check(name,guides[name]);
   }
   if(JSON.stringify({pages:guides,run_id:input.dataset.run},null,2)!==receiptText)
    throw Error(tr('Changed handoff receipt','交接清单已变化')+' · HANDOFF.json');
   let nextUpdate=0;
   for(const [name,manifestHash] of Object.entries(expected)){
    const path=name+'/PACKAGE_MANIFEST.json';
    await check(path,manifestHash);
    const manifest=JSON.parse(await files.get(path).text());
    for(const row of manifest.files){
     const member=name+'/'+row.path;
     if(performance.now()>=nextUpdate){
      status.textContent=tr('Checking','正在校验')+' '+(seen.size+1)+' / '+files.size+' · '+member;
      nextUpdate=performance.now()+300;
     }
     await check(member,row.sha256,row.size_bytes);
    }
   }
   for(const path of files.keys())if(!seen.has(path))throw Error(tr('Unlisted file','清单外文件')+' · '+path);
   status.dataset.state='verified';
   status.textContent=tr('Verified files','已校验文件')+' · '+seen.size+' · '+receipt.run_id;
  }catch(error){
   status.dataset.state='failed';
   status.textContent=tr('Check incomplete','校验未通过')+' · '+(error.message.includes(current)?error.message:current+' · '+error.message);
  }finally{input.value='';input.disabled=false;}
 });
})();
