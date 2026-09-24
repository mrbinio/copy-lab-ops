// Run with node tests/test_export.cjs. No browser or dependencies required.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../../lab/app.js'),'utf8');
const fn=source.slice(source.indexOf('async function exportDaily(){'));
async function run({preview=false,fail=false}={}){
 let fetched=0,downloads=0,status='',filename='';
 const elements={export:{disabled:false},'report-date':{value:'2026-09-23'}};
 const ctx={preview,location:{hostname:'btc.damianbiniarz.com'},$:id=>elements[id],t:a=>a,
  fetch:async()=>{fetched++;if(fail)throw Error('network unavailable');return {ok:true,json:async()=>({schema:'btc-daily-report-v2',period:{date:'2026-09-23'},worker_fresh_at_export:false})};},
  AbortSignal:{timeout:()=>null},URL:{createObjectURL:()=>'',revokeObjectURL:()=>{}},Blob:class{},
  node:()=>({set download(v){filename=v;},click:()=>downloads++}),setTimeout:()=>{},text:(_,v)=>status=v};
 vm.createContext(ctx);vm.runInContext(fn,ctx);await ctx.exportDaily();
 assert.equal(elements.export.disabled,false);
 return {fetched,downloads,status,filename};
}
(async()=>{
 let r=await run({fail:true});assert.equal(r.downloads,0);assert.equal(r.fetched,1);
 r=await run({preview:true});assert.equal(r.downloads,0);assert.equal(r.fetched,0);
 r=await run();assert.equal(r.downloads,1);assert.equal(r.filename,'btc-lab-2026-09-23-Stockholm.json');assert.match(r.status,/stale/);
 console.log('3 export cases passed: offline, preview, fresh fetch with stale-worker warning');
})().catch(e=>{console.error(e);process.exit(1);});
