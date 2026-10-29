// Isolated string/handler tests only. No browser, layout engine or network.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const template=fs.readFileSync(__dirname+'/template.html','utf8'),snapshot=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const source=template.slice(template.indexOf('// BEGIN BACKLOG LOGIC'),template.indexOf('// END BACKLOG LOGIC'));
function run(data){
 const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{value:['#backlog-priority','#backlog-outcome'].includes(id)?'all':'',innerHTML:'',textContent:'',handlers:{},addEventListener(k,v){this.handlers[k]=v;},insertAdjacentHTML(_,v){this.innerHTML+=v;}});return nodes.get(id);};
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const context={SNAPSHOT:data,L:data.ledger,$:node,esc,pill:(x)=>esc(x),list:xs=>xs.map(esc).join(' / ')};
 vm.createContext(context);vm.runInContext(source,context);return {node,context};
}
let {node,context}=run(snapshot);const total=snapshot.status_metrics.backlog.total,summary=node('#backlog-overview').innerHTML;
assert.match(summary,new RegExp(snapshot.status_metrics.backlog.remaining+' remaining tasks'));
for(const state of ['Ready','Waiting','Blocked','Done','In progress'])assert.ok(summary.includes(state));
assert.match(summary,/Δ/);assert.match(summary,/not effort/);assert.match(summary,/#backlog/);
assert.match(node('#backlog-count').textContent,new RegExp(total+' of '+total));
const task=snapshot.status_metrics.backlog.tasks.find(t=>t.status==='waiting');
assert.ok(node('#backlog-tasks').innerHTML.includes('#backlog/'+task.dependencies[0]));
node('#backlog-search').value=task.title;node('#backlog-search').handlers.input();
assert.match(node('#backlog-count').textContent,/1 of/);
assert.equal(node('#backlog-overview').innerHTML,summary);
node('#reset-backlog').handlers.click();
node('#backlog-status-filters').handlers.click({target:{closest:()=>({dataset:{taskStatus:'blocked'}})}});
assert.match(node('#backlog-count').textContent,new RegExp(snapshot.status_metrics.backlog.counts.blocked+' of '+total));
assert.match(node('#backlog-tasks').innerHTML,/What unblocks this task/);
node('#backlog-search').value='no-such-task-173527';node('#backlog-search').handlers.input();assert.match(node('#backlog-tasks').innerHTML,/No matching tasks/);
vm.runInContext('resetBacklog();',context);node('#backlog-priority').value='P3';node('#backlog-priority').handlers.change();assert.doesNotMatch(node('#backlog-tasks').innerHTML,/>P0/);
const hostile=structuredClone(snapshot);hostile.status_metrics.backlog.tasks[0].title='<script>never run</script>';hostile.status_metrics.backlog.unmapped_outcomes=['D99<script>'];
const unsafe=run(hostile).node;assert.match(unsafe('#backlog-tasks').innerHTML,/&lt;script&gt;/);assert.doesNotMatch(unsafe('#backlog-tasks').innerHTML,/<script>/);assert.match(unsafe('#backlog-overview').innerHTML,/Planning coverage gap/);
const absent=structuredClone(snapshot);delete absent.status_metrics.backlog;assert.match(run(absent).node('#backlog-overview').innerHTML,/not been inventoried/);
// Route logic uses actual generated IDs, resets filters and focuses the requested task.
const routeSource=template.slice(template.indexOf('function route(){'),template.indexOf('function go(hash)'));
let focused=false,scrolled=false,reset=0;const row={open:false,scrollIntoView(){scrolled=true;},querySelector(){return {focus(){focused=true;}};}};
const routeContext={location:{hash:'#backlog/'+task.id},backlog:snapshot.status_metrics.backlog,$:id=>{assert.equal(id,'#task-'+task.id);return row;},$$:()=>[],resetBacklog(){reset++;},requestAnimationFrame:f=>f(),window:{scrollTo(){throw Error('wrong route');}},byID:new Map(),L:snapshot.ledger};
vm.createContext(routeContext);vm.runInContext(routeSource+';route();',routeContext);assert.ok(row.open&&focused&&scrolled&&reset===1);
// The third distribution uses task states and its own denominator.
const distributionSource=template.slice(template.indexOf("$('#refresh-snapshot').addEventListener"),template.indexOf('if(V.errors.length'));
const buttons=['outcomes','packets','backlog'].map(x=>({dataset:{distribution:x},attrs:{},handlers:{},setAttribute(k,v){this.attrs[k]=v;},addEventListener(k,v){this.handlers[k]=v;}}));
const distributionNodes=new Map();const dn=id=>{if(!distributionNodes.has(id))distributionNodes.set(id,{innerHTML:'',addEventListener(){}});return distributionNodes.get(id);};
const dc={SNAPSHOT:snapshot,$:dn,$$:()=>buttons,statusLabel:x=>x,esc:x=>String(x).replaceAll('<','&lt;'),window:{location:{reload(){}}}};
vm.createContext(dc);vm.runInContext(distributionSource,dc);buttons[2].handlers.click();
assert.equal(buttons[2].attrs['aria-pressed'],'true');assert.equal(buttons[0].attrs['aria-pressed'],'false');
assert.match(dn('#distribution-content').innerHTML,new RegExp(total+' remaining-scope tasks'));
assert.match(dn('#distribution-content').innerHTML,/Waiting on dependencies/);assert.match(dn('#distribution-content').innerHTML,/data-state="blocked"/);
assert.doesNotMatch(dn('#distribution-content').innerHTML,/NaN|undefined|Infinity/);
// Parse the complete script, including optional backlog distribution, without executing browser APIs.
new vm.Script(template.slice(template.lastIndexOf('<script>')+8,template.lastIndexOf('</script>')));
console.log(JSON.stringify({checks:23,passed:true,validation:'isolated_JS_logic_only',browser:false,network:false}));
