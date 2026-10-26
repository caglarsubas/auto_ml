// Isolated string/handler checks only: no browser, renderer or network.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const template=fs.readFileSync(__dirname+'/template.html','utf8');
const source=template.slice(template.indexOf('function renderProgress(){'),template.indexOf('function renderDistribution(){'));
function render(progress){
 const node={innerHTML:''};
 const context={SNAPSHOT:{status_metrics:{progress}},$:()=>node,esc:x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;')};
 vm.createContext(context);vm.runInContext(source+';renderProgress();',context);
 return node.innerHTML;
}
const metrics=JSON.parse(fs.readFileSync(process.argv[2],'utf8')).status_metrics;
const current=render(metrics.progress);
assert.match(current,/Outcome gates/);assert.match(current,/Delivery packets/);
assert.match(current,/Done \/ open \/ blocked/);
assert.match(current,/all records, independent of filters/);
assert.doesNotMatch(current,/NaN|undefined|Infinity/);
const sample={comparison:{packet:'P153<script>'},outcomes:{total:3,counts:{done:1,open:1,blocked:1},percentages:{done:33.3,open:33.3,blocked:33.3},delta:{counts:{done:1,open:0,blocked:-1},percentage_points:{done:33.3,open:0,blocked:-33.3}}}};
sample.packets=JSON.parse(JSON.stringify(sample.outcomes));
const changed=render(sample);
assert.match(changed,/changes since P153&lt;script>/);assert.doesNotMatch(changed,/<script>/);
for(const text of ['Δ +1 items · +33.3 pp','Δ 0 items · 0 pp','Δ -1 items · -33.3 pp'])assert.ok(changed.includes(text));
assert.equal((changed.match(/data-progress="blocked" data-count="1"/g)||[]).length,2);
assert.match(changed,/33.3%/);
for(const key of ['outcomes','packets'])sample[key]={total:0,counts:{done:0,open:0,blocked:0},percentages:{done:0,open:0,blocked:0},delta:null};
sample.comparison=null;
const empty=render(sample);assert.match(empty,/no previous comparison snapshot/);assert.match(empty,/No prior comparison/);assert.match(empty,/0.0%/);assert.doesNotMatch(empty,/NaN|undefined|Infinity/);
assert.match(render(undefined),/No progress comparison snapshot recorded/);
console.log(JSON.stringify({checks:16,passed:true,validation:'isolated_JS_logic_only',browser:false,network:false}));
