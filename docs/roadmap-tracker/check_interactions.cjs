// Isolated JavaScript string/handler checks: no browser, DOM renderer or network.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const template=fs.readFileSync(__dirname+'/template.html','utf8');
const source=template.slice(template.indexOf("$('#refresh-snapshot').addEventListener"),template.indexOf('if(V.errors.length'));
function run(data){
 const nodes=new Map(),buttons=['outcomes','packets'].map(x=>({dataset:{distribution:x},attrs:{},handlers:{},setAttribute(k,v){this.attrs[k]=v;},addEventListener(k,v){this.handlers[k]=v;}}));
 const node=selector=>{if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',handlers:{},addEventListener(k,v){this.handlers[k]=v;}});return nodes.get(selector);};
 let reloads=0;
 const context={SNAPSHOT:{status_metrics:data},$:node,$$:()=>buttons,statusLabel:x=>x,esc:x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;'),window:{location:{reload(){reloads++;}}}};
 vm.createContext(context);vm.runInContext(source,context);
 assert.match(node('#distribution-content').innerHTML,/denominator/);
 assert.equal(buttons[0].attrs['aria-pressed'],'true');
 buttons[1].handlers.click();
 assert.equal(buttons[1].attrs['aria-pressed'],'true');
 assert.match(node('#distribution-content').innerHTML,/future delivery scope/);
 assert.match(node('#distribution-content').innerHTML,new RegExp(data.delivery.tested+' test-qualified packets'));
 assert.doesNotMatch(node('#distribution-content').innerHTML,/NaN|undefined|Infinity/);
 node('#refresh-snapshot').handlers.click();assert.equal(reloads,1);
 return node('#distribution-content').innerHTML;
}
const metrics=JSON.parse(fs.readFileSync(process.argv[2],'utf8')).status_metrics;
run(metrics);
const empty=JSON.parse(JSON.stringify(metrics));for(const key of ['outcomes','packets']){empty[key].total=0;for(const s in empty[key].counts){empty[key].counts[s]=0;empty[key].percentages[s]=0;}}empty.delivery={tested:0,d07_tested:0,tested_added:0,d07_added:0,previous_packet:null,recent:[]};
assert.match(run(empty),/No delivery packets/);
console.log(JSON.stringify({checks:9,passed:true,validation:'isolated_JS_logic_only',browser:false,network:false}));
