const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../../lab/app.js'),'utf8');
function render(state,opts={}){
 const rows=[];const box={replaceChildren:()=>rows.splice(0),append:e=>rows.push(e.text)};
 const ctx={Date,Number,String,preview:false,connected:true,lang:'en',isEth:()=>false,
  $:()=>box,node:(tag,text)=>({text,style:{}}),t:(en)=>en,money:n=>String(n),reason:x=>x,...opts};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function renderWalletPanel(s){')),ctx);
 ctx.renderWalletPanel(state);return rows.join('\n');
}
const now=Date.now()/1000;
let s=render({wallet_observer:[{wallet:'0xabc',status:'POLL_OK',checked_at:now,unique_fingerprints:0}]});
assert.match(s,/0xabc/);assert.match(s,/Recorded events: 0/);assert.match(s,/separate PAPER copy results/);
assert.match(s,/NOT STARTED/);
s=render({wallet_observer:[{wallet:'0xabc',status:'POLL_OK',checked_at:now-120}]});assert.match(s,/STALE/);
s=render({wallet_observer:[{wallet:'0xabc',status:'ERROR',checked_at:now,error:'HTTP 403'}]});assert.match(s,/HTTP 403/);assert.match(s,/Recorded events: unknown/);
assert.match(render({}, {preview:true}),/synthetic preview/);
assert.match(render({}, {isEth:()=>true}),/Select BTC/);
s=render({wallet_discovery:{status:'SCAN_OK',last_success_at:now,candidates:[{wallet:'candidate',week_reported_pnl:12,month_reported_pnl:15}]}});assert.match(s,/candidate/);assert.match(s,/SHORTLIST_30D/);
s=render({wallet_discovery:{status:'ERROR',last_success_at:now-5000,error:'failed',candidates:[]}});assert.match(s,/no fresh successful scan/);assert.match(s,/failed/);
s=render({wallet_copy_execution:{status:'RUNNING',updated_at:now,accounts:[{wallet:'sourcewallet',settled:1,pnl:-4.7,trades:1,fees:.1,max_drawdown_usd:4.7,last_reason:'COPIED_BUY'}]}});assert.match(s,/sourcewallet/);assert.match(s,/-4.7/);assert.match(s,/COPIED_BUY/);
s=render({wallet_copy_execution:{status:'RUNNING',updated_at:now,accounts:[{wallet:'0xabc',name:'Copy Atomforge · PAPER',settled:0,pnl:0,trades:0,fees:0,max_drawdown_usd:0,last_reason:'NO_NEW_SOURCE_TRADE'}]}});assert.match(s,/Atomforge/);
s=render({wallet_observer:[{wallet:'0xce50',label:'honey-spot',status:'POLL_OK',checked_at:now,unique_fingerprints:0}]});assert.match(s,/honey-spot · 0xce50/);
console.log('10 wallet panel scenarios passed');
