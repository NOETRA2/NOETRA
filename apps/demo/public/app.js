let selected='logic';
const byId=id=>document.getElementById(id);
const titles={logic:['Does the claim follow?','Supply one integer premise and a claim. Z3 checks entailment or finds a counterexample.'],planning:['What is blocking the release?','Build → review → release. Toggle the test prerequisite to see how the plan changes.'],evidence:['An observation is not a proof.','Store a fixed attributed observation and inspect its status, limitations and digest.']};
for(const button of document.querySelectorAll('[data-example]'))button.addEventListener('click',()=>{
  selected=button.dataset.example;
  for(const b of document.querySelectorAll('[data-example]'))b.setAttribute('aria-pressed',String(b===button));
  for(const name of Object.keys(titles))byId(name+'-controls').hidden=name!==selected;
  byId('example-title').textContent=titles[selected][0];byId('example-description').textContent=titles[selected][1];
  byId('result-status').textContent='NOT RUN';byId('summary').textContent='Run this example to see the actual result.';byId('json').textContent='No result yet.';byId('raw').open=false;
});
byId('run').addEventListener('click',async()=>{
  const controls=[...document.querySelectorAll('button,input')];controls.forEach(x=>x.disabled=true);byId('progress').textContent='Running the NOETRA core…';
  const payload=selected==='logic'?{example:selected,lowerBound:Number(byId('lower').value),claimBound:Number(byId('claim').value)}:selected==='planning'?{example:selected,testsPassed:byId('passed').checked}:{example:selected};
  try{
    const response=await fetch('/api/demo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(14000)});
    const data=await response.json();if(!response.ok)throw new Error(data.error??'The engine did not obtain a result; retry shortly.');
    byId('result-status').textContent=data.result.status;byId('summary').textContent=data.summary;byId('json').textContent=JSON.stringify(data.result,null,2);byId('privacy').textContent=data.privacy;byId('raw').open=true;byId('progress').textContent='Finished. Inspect the result and its limitations.';
  }catch(error){byId('progress').textContent=error.message;byId('result-status').textContent='NO RESULT';byId('summary').textContent='No successful conclusion obtained.';byId('json').textContent='No successful result.';}
  finally{controls.forEach(x=>x.disabled=false);}
});
