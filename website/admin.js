const $=id=>document.getElementById(id);
let client,token='',pcToken='',pcUrl='',rows=[],timer;
const node=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
async function cloud(action,url=''){const r=await client.predict('/admin_action',[token,action,url]);return r.data[0];}
async function pc(path,body){const r=await fetch(pcUrl+'/api/admin/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(15000)});const data=await r.json();if(!r.ok)throw Error(data.error||'PC admin request failed.');return data;}
function renderRows(){const q=$('filter').value.toLowerCase();$('chats').replaceChildren();for(const row of rows.filter(r=>(r.visitor+' '+r.message+' '+r.answer).toLowerCase().includes(q))){const d=node('details','');d.append(node('summary',new Date(row.time*1000).toLocaleString()+' · Session '+row.visitor+' · '+row.feature+(row.failed?' · Failed':'')));for(const [label,text] of [['Visitor',row.message],['Lucid',row.answer]]){d.append(node('h3',label));const p=node('div',text||'(No reply recorded)');p.className='chat-text';d.append(p);}$('chats').append(d);}if(!$('chats').children.length)$('chats').append(node('p','No matching activity yet.'));}
async function refresh(){
 const control=await cloud('dashboard');
 const next=control.hosting.url||'';if(next!==pcUrl)pcToken='';pcUrl=next;
 $('host').textContent=control.hosting.provider==='local'?'AI is running on your PC':'AI is running in the cloud';
 let data=control;
 if($('source').value==='local'){
  if(!pcUrl)throw Error('Select a PC host first.');
  if(!pcToken)throw Error('Sign out and sign in again while the PC host is selected to unlock its activity. Set the same passcode on both hosts.');
  data=await pc('action',{token:pcToken,action:'dashboard'});
 }
 $('stats').replaceChildren(...[['Requests',data.requests],['Visitor sessions',data.visitors],['Failed requests',data.failures]].map(([label,value])=>{const d=node('div',label);d.className='metric';d.prepend(node('strong',String(value)));return d;}));
 $('features').replaceChildren(...Object.entries(data.features).map(([name,count])=>{const d=node('div',name);d.className='feature';d.append(node('strong',String(count)));return d;}));
 rows=data.activity;renderRows();$('status').textContent='Updated '+new Date().toLocaleTimeString()+'. Admin sign-in lasts 30 minutes.';
}
async function run(fn){try{await fn();}catch(e){$('status').textContent=String(e.message||e);}}
function clear(){token=pcToken='';rows=[];clearTimeout(timer);$('chats').replaceChildren();$('stats').replaceChildren();$('features').replaceChildren();$('dashboard').hidden=true;$('login').hidden=false;$('local-dialog').close();}
$('login').onsubmit=e=>{e.preventDefault();run(async()=>{const password=$('password').value;$('password').value='';const result=await client.predict('/admin_login',[password]);token=result.data[0].token;$('source').value='cloud';await refresh();let warning='';if(pcUrl){try{pcToken=(await pc('login',{password})).token;}catch{warning=' Cloud admin unlocked; PC activity unavailable. Check the PC passcode and sign in again.';}}$('dashboard').hidden=false;$('login').hidden=true;$('status').textContent+=warning;timer=setTimeout(()=>{clear();$('status').textContent='Admin session expired. Sign in again.';},1800000);});};
$('logout').onclick=()=>run(async()=>{try{await cloud('logout');if(pcToken)await pc('action',{token:pcToken,action:'logout'});}finally{clear();$('status').textContent='Signed out.';}});
$('refresh').onclick=() => run(refresh);
$('source').onchange=()=>{rows=[];renderRows();run(refresh);};
$('filter').oninput=renderRows;
$('local').onclick=()=>$('local-dialog').showModal();
$('close-local').onclick=()=>$('local-dialog').close();
$('copy').onclick=()=>run(async()=>{await navigator.clipboard.writeText($('command').textContent);$('local-status').textContent='Command copied. Run it in your repository folder.';});
$('switch-local').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;$('local-status').textContent='Checking the PC host…';try{await cloud('local',$('local-url').value.trim());$('local-dialog').close();await refresh();}catch(error){$('local-status').textContent=String(error.message||error);}finally{b.disabled=false;}};
$('cloud').onclick=()=>run(async()=>{await cloud('cloud');$('source').value='cloud';await refresh();});
try{const {Client}=await import('https://cdn.jsdelivr.net/npm/@gradio/client@2.7.0/+esm');client=await Client.connect('lucidpy/lucid-ai-v5');const api=await client.view_api();if(!api.named_endpoints?.['/admin_login'])throw Error('Deploy the updated Hugging Face backend first (see ADMIN.md).');$('sign-in').disabled=false;$('status').textContent='Sign in to manage Lucid.';}catch(e){$('status').textContent='Admin is unavailable. '+String(e.message||e)+' Check the Hugging Face Space and reload.';}
