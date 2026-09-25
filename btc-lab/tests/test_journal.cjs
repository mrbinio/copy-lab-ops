const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../../lab/app.js'),'utf8');
const ctx={};vm.createContext(ctx);vm.runInContext(src.slice(src.indexOf('function filterJournal('),src.indexOf('function reason(')),ctx);
const rows=[{strategy:'mid-window-v1',status:'CLOSED'},{strategy:'early-v1',status:'REDEEMED'},{strategy:'mid-window-v1',status:'OPEN'}];
assert.equal(ctx.filterJournal(rows,'all').length,3);
assert.equal(ctx.filterJournal(rows,'mid-window-v1').length,2);
assert.equal(ctx.filterJournal(rows,'value-v1').length,0);
assert.equal(rows.length,3);
console.log('Journal filters preserve input and include sold/open experimental positions');
