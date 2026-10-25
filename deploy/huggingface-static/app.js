const el=id=>document.getElementById(id);
let records;
function show(index){
 const record=records[index];if(!record)return;
 for(const b of document.querySelectorAll('[data-index]'))b.setAttribute('aria-pressed',String(Number(b.dataset.index)===index));
 el('title').textContent=record.response.title;el('input').textContent=JSON.stringify(record.request,null,2);
 el('status').textContent=record.response.result.status;el('summary').textContent=record.response.summary;
 el('result').textContent=JSON.stringify(record.response.result,null,2);
}
fetch('results.json').then(r=>{if(!r.ok)throw new Error('Unavailable');return r.json();}).then(data=>{records=data.runs;show(0);}).catch(()=>{el('title').textContent='Recorded examples could not load.';el('summary').textContent='Open the source repository to inspect the captured results.';});
for(const b of document.querySelectorAll('[data-index]'))b.addEventListener('click',()=>{if(records)show(Number(b.dataset.index));});
