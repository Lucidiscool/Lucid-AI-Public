'use strict';
const $ = id => document.getElementById(id);
let apiBase='', publicSession='', connected=false;
let cloudClient=null, cloudMode=false;
const hosted=!!window.LUCID_STATIC_PREVIEW;
let state = null, mode = 'chat', lastMessages = '', lastChats = '', lastMemories = '', lastEvents = '', lastNotice = '', polling = false;
const commands = [
 ['/help','See every command'],['/think','Toggle readable process summaries'],['/forget','Toggle the blank canvas experiment'],
 ['/facts','See experimental facts'],['/teach ','Teach an experimental fact'],['/reset','Clear experimental facts'],
 ['/search ','Search the web for a topic'],['/research ','Explore multiple sources'],['/auto-memory off','Disable automatic memory'],
 ['/auto-memory on','Enable automatic memory'],['/auto-web off','Disable automatic search'],['/auto-web on','Enable automatic search'],
 ['/remember ','Save something for later'],['/memories','See saved memories'],['/forget all','Remove all normal saved memories'],
 ['/good ','Mark the latest answer helpful'],['/bad ','Explain what could be better'],['/correct ','Provide a preferred answer'],
 ['/feedback','Review feedback'],['/unrate','Remove the latest rating'],['/new','Start a new conversation'],
 ['/chats','List conversations'],['/load latest','Continue the latest chat'],['/history','Show conversation history'],['/save','Save the current conversation'],
 ['/temperature ','Set creativity from 0 to 2'],['/tokens ','Set maximum response tokens'],['/system ','Inspect or edit the system prompt'],
 ['/system reset','Restore the default prompt'],['/settings','Show all settings'],['/model','Inspect the local model configuration'],['/stats','Show session statistics']
];

function el(tag, cls, text) { const node = document.createElement(tag); if(cls) node.className = cls; if(text !== undefined) node.textContent = text; return node; }
function inline(text, parent) {
  const pattern = /(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<>]+|`[^`\n]+`|\*\*[^*\n]+\*\*)/g;
  let previous=0;
  for(const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(previous,match.index)));
    const token=match[0]; let node;
    if(token.startsWith('`')) node=el('code','',token.slice(1,-1));
    else if(token.startsWith('**')) node=el('strong','',token.slice(2,-2));
    else {
      const markdown=token.match(/^\[([^\]]+)\]\((.+)\)$/);
      const href=markdown?markdown[2]:token;
      node=el('a','',markdown?markdown[1]:token);
      try { const url=new URL(href); if(!['http:','https:'].includes(url.protocol)) throw Error(); node.href=url.href; node.target='_blank'; node.rel='noopener noreferrer'; }
      catch { node=el('span','',token); }
    }
    parent.append(node);previous=match.index+token.length;
  }
  parent.append(document.createTextNode(text.slice(previous)));
}
function markdown(text) {
  const container=el('div','message-content'), lines=text.split('\n'); let code=null, buffer=[], paragraph=[], list=null;
  function flush(){if(paragraph.length){const p=el('p');inline(paragraph.join('\n'),p);container.append(p);paragraph=[];}list=null;}
  for(const line of lines){
    if(line.trim().startsWith('```')){
      if(code!==null){const pre=el('pre'), body=el('code','',buffer.join('\n')), button=el('button','code-copy','Copy code');button.onclick=()=>copy(body.textContent);pre.append(button,body);container.append(pre);code=null;buffer=[];}
      else{flush();code=line.trim().slice(3);}
      continue;
    }
    if(code!==null){buffer.push(line);continue;}
    if(!line.trim()){flush();continue;}
    const heading=line.match(/^#{1,3}\s+(.+)/), item=line.match(/^\s*(?:[-*]|\d+\.)\s+(.+)/);
    if(heading){flush();const h=el('h3');inline(heading[1],h);container.append(h);}
    else if(item){if(paragraph.length)flush();if(!list){list=el(/^\s*\d/.test(line)?'ol':'ul');container.append(list);}const li=el('li');inline(item[1],li);list.append(li);}
    else{list=null;paragraph.push(line);}
  }
  flush();if(code!==null){const pre=el('pre');pre.append(el('code','',buffer.join('\n')));container.append(pre);}return container;
}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,5500);}
async function copy(text){try{await navigator.clipboard.writeText(text);toast('Copied to clipboard.');}catch{toast('Clipboard access is unavailable. Select the text to copy it.');}}
function openDialog(id){$(id).showModal();if(id==='commands-dialog')$('command-search').focus();$('sidebar').classList.remove('open');}

function renderMessages(messages){
  const signature=JSON.stringify(messages);if(signature===lastMessages)return;lastMessages=signature;
  const scroller=$('scroll-area'),nearBottom=scroller.scrollHeight-scroller.scrollTop-scroller.clientHeight<120;
  const fragment=document.createDocumentFragment();
  messages.forEach((message,index)=>{
    const article=el('article','message '+message.role+(message.pending?' pending':''));
    article.append(el('div','message-avatar',message.role==='user'?'You':state.experiment?'◈':'✦'));
    const body=el('div','message-body'), label=el('div','message-label',message.role==='user'?'You':state.experiment?'Experiment':'Lucid');
    if(message.role==='assistant')label.append(el('small','',state.experiment?'Temporary facts':'V5'));
    body.append(label,markdown(message.content));
    if(message.interrupted)body.append(el('p','interrupted','Stopped · this partial answer was not saved'));
    if(message.role==='assistant'&&!message.pending){
      const tools=el('div','message-tools'),copyButton=el('button','','Copy');copyButton.onclick=()=>copy(message.content);tools.append(copyButton);
      if(index===messages.length-1&&!state.experiment&&!message.interrupted){for(const [text,cmd] of [['Helpful','/good'],['Needs work','/bad']]){const b=el('button','',text);b.disabled=state.busy;b.onclick=()=>sendCommand(cmd);tools.append(b);}}
      body.append(tools);
    }
    article.append(body);fragment.append(article);
  });
  $('messages').replaceChildren(fragment);
  if(nearBottom||messages.at(-1)?.role==='user')requestAnimationFrame(()=>scroller.scrollTop=scroller.scrollHeight);
}
function render(){
  if(!state)return;
  $('welcome').hidden=state.messages.length>0||state.experiment;
  $('experiment-banner').hidden=!state.experiment;
  $('working').hidden=!state.busy;
  $('send-button').hidden=state.busy;$('stop-button').hidden=!state.busy;
  $('stop-button').disabled=false;$('send-button').disabled=!$('prompt').value.trim();
  $('error-box').hidden=!state.error;$('error-box').textContent=state.error;
  $('chat-title').textContent=state.experiment?'Blank canvas experiment':state.chats.find(c=>c.id===state.chat_id)?.title||'New conversation';
  $('memory-count').textContent=state.memories.length;
  renderMessages(state.messages);
  const cs=JSON.stringify([state.chats,state.chat_id]);
  if(cs!==lastChats){lastChats=cs;const fragment=document.createDocumentFragment();if(!state.chats.length)fragment.append(el('p','empty-history','Your next good idea starts here.'));
    state.chats.forEach(chat=>{const button=el('button',chat.id===state.chat_id?'current':'',chat.title);button.title=chat.title;button.onclick=()=>{sendCommand('/load '+chat.id);$('sidebar').classList.remove('open');};fragment.append(button);});$('history-list').replaceChildren(fragment);}
  const ms=JSON.stringify(state.memories);
  if(ms!==lastMemories){lastMemories=ms;const fragment=document.createDocumentFragment();if(!state.memories.length)fragment.append(el('p','dialog-intro','Nothing saved yet. Useful details will appear here as you chat.'));
    state.memories.forEach(memory=>{const row=el('div','memory-row'),button=el('button','','Forget');button.onclick=()=>sendCommand('/forget '+memory.id);row.append(el('span','',memory.text),button);fragment.append(row);});$('memory-list').replaceChildren(fragment);}
  for(const [id,value] of [['think-toggle',state.think],['memory-toggle',state.settings.auto_memory],['web-toggle',state.settings.auto_web],['experiment-toggle',state.experiment]])$(id).checked=value;
  if(document.activeElement!==$('temperature'))$('temperature').value=state.temperature;
  if(document.activeElement!==$('tokens'))$('tokens').value=state.max_tokens;
  document.querySelectorAll('[data-command],#history-list button,.switch,#apply-settings,#memory-form button,#memory-list button').forEach(b=>b.disabled=state.busy);
  const es=JSON.stringify(state.events);
  $('activity').hidden=!state.events.length;
  if(es!==lastEvents){lastEvents=es;$('activity-list').replaceChildren(...state.events.map(event=>{const li=el('li');li.append(el('time','',event.time),document.createTextNode(event.text));return li;}));}
  $('activity-title').textContent=state.busy?'Working on it…':state.error?'Request stopped':'Activity · complete';
  const last=state.events.at(-1)?.text||'Preparing your reply';$('working-text').textContent=last.length>90?last.slice(0,87)+'…':last;
  if(state.notice&&state.notice!==lastNotice){lastNotice=state.notice;toast(state.notice);}if(!state.notice)lastNotice='';
  publicControls();
}
function sessionHeaders(){return hosted?{'X-Lucid-Session':publicSession}:{};}
async function poll(){
  if(cloudMode)return;
  if(polling || (hosted&&!publicSession))return;
  polling=true;
  try{
    const response=await fetch(apiBase+'/api/state',{headers:sessionHeaders(),signal:AbortSignal.timeout(12000)});
    if(!response.ok)throw Error(response.status===401?'Session expired. Reload the page to reconnect.':'Lucid is temporarily unavailable.');
    state=await response.json();connected=true;render();
    if(hosted)$('connection-status').textContent='Connected to Lucid AI V5';
  }catch(error){
    connected=false;
    $('error-box').hidden=false;
    $('error-box').textContent=hosted?(error.message==='Failed to fetch'?'Lucid is offline. The host computer must be on.':error.message):'Cannot reach Lucid. Keep the local server terminal open.';
    if(hosted){$('connection-status').textContent='Lucid is offline — reconnecting';$('send-button').disabled=true;}
  }finally{polling=false;}
}
async function request(path,data){
  if(!state || (hosted&&!connected)){toast('Lucid is offline. Please wait for the host to reconnect.');return false;}
  try{
    const response=await fetch(apiBase+path,{method:'POST',headers:{'Content-Type':'application/json','X-Lucid-Token':state.token,...sessionHeaders()},body:JSON.stringify(data),signal:AbortSignal.timeout(15000)});
    const body=await response.json();if(!response.ok)throw Error(body.error||'Request failed');return true;
  }catch(error){toast(error.message);return false;}
}
async function sendCommand(message){if(state?.busy){toast('Let the current reply finish, or stop it first.');return false;}if(cloudMode)return sendCloud(message);if(await request('/api/message',{message})){state.busy=true;state.error='';render();await poll();return true;}return false;}
async function waitIdle(){for(let i=0;i<240;i++){await new Promise(r=>setTimeout(r,250));await poll();if(!state.busy)return;}throw Error('The command is taking longer than expected.');}
async function sendMessage(event){event?.preventDefault();const text=$('prompt').value.trim();if(!text||state?.busy)return;
  if(text==='/help'){openDialog('commands-dialog');$('prompt').value='';return;}
  const message=text.startsWith('/')||mode==='chat'?text:'/'+mode+' '+text;
  if(await sendCommand(message)){$('prompt').value='';$('prompt').style.height='auto';$('prompt').focus();render();}}
function showCommands(){const filter=$('command-search').value.toLowerCase();$('command-list').replaceChildren(...commands.filter(([cmd,desc])=>(cmd+desc).toLowerCase().includes(filter)).map(([cmd,desc])=>{const button=el('button');button.append(el('code','',cmd.trim()),el('span','',desc));button.onclick=()=>{$('prompt').value=cmd;$('commands-dialog').close();$('prompt').focus();render();};return button;}));}

$('composer').addEventListener('submit',sendMessage);
$('prompt').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage();}});
$('prompt').addEventListener('input',()=>{$('prompt').style.height='auto';$('prompt').style.height=Math.min(160,$('prompt').scrollHeight)+'px';if($('prompt').value==='/'){openDialog('commands-dialog');}if(state)render();});
document.querySelectorAll('[data-prompt]').forEach(button=>button.onclick=()=>{$('prompt').value=button.dataset.prompt;$('prompt').focus();render();});
document.querySelectorAll('[data-command]').forEach(button=>button.onclick=()=>sendCommand(button.dataset.command));
document.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>{mode=button.dataset.mode;document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('selected',b===button));$('prompt').placeholder=mode==='chat'?'What’s on your mind?':mode==='search'?'What would you like to find?':'What would you like to explore in depth?';$('prompt').focus();});
document.querySelectorAll('.close-dialog').forEach(button=>button.onclick=()=>button.closest('dialog').close());
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}}));
for(const id of ['commands-nav','inline-help','footer-help'])$(id).onclick=()=>openDialog('commands-dialog');
for(const id of ['settings-button','profile-settings'])$(id).onclick=()=>openDialog('settings-dialog');
$('memory-nav').onclick=()=>openDialog('memory-dialog');$('chat-nav').onclick=()=>$('sidebar').classList.remove('open');
$('menu-button').onclick=()=>$('sidebar').classList.toggle('open');
$('command-search').oninput=showCommands;
for(const [id,command] of [['think-toggle','/think'],['memory-toggle','/auto-memory'],['web-toggle','/auto-web'],['experiment-toggle','/forget']])$(id).onchange=()=>sendCommand(command+($(id).checked?' on':' off'));
$('apply-settings').onclick=async()=>{const temperature=$('temperature').value,tokens=$('tokens').value;try{if(await sendCommand('/temperature '+temperature)){await waitIdle();if(!state.error)await sendCommand('/tokens '+tokens);}}catch(error){toast(error.message);}};
$('memory-form').onsubmit=async event=>{event.preventDefault();const text=$('memory-input').value.trim();if(text&&await sendCommand('/remember '+text))$('memory-input').value='';};
$('stop-button').onclick=async()=>{if(await request('/api/stop',{})){$('stop-button').disabled=true;$('working-text').textContent='Stopping safely…';}};
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();sendCommand('/new');}if(event.key==='Escape')$('sidebar').classList.remove('open');});
document.querySelector('.new-chat kbd').textContent=navigator.platform.includes('Mac')?'⌘ K':'Ctrl K';
function publicControls(){
  if(!hosted)return;
  document.querySelectorAll('[data-mode="search"],[data-mode="research"],#web-toggle').forEach(node=>{node.disabled=true;node.title='Available in the local app';});
  $('tokens').max=cloudMode?512:1024;
  if(cloudMode){$('stop-button').disabled=true;$('stop-button').title='The cloud request is running. Wait for the reply.';}
  $('prompt').maxLength=4000;
  $('send-button').disabled=!connected||!$('prompt').value.trim();
}
async function connectPublic(){
  const banner=el('div','hosting-banner');
  const status=el('strong','','Connecting to Lucid AI V5…');status.id='connection-status';
  banner.append(status,el('span','','Runs on the owner’s computer. Chats pass through Cloudflare and are stored temporarily on the host, separately from other visitors. Sessions expire after 1 hour idle.'));
  document.querySelector('.topbar').after(banner);
  document.querySelector('.model-tag').textContent='Lucid V5 · Qwen 3 · 4B';
  document.querySelector('.local-card p').textContent='Powered by the owner’s Lucid V5.';
  document.querySelector('.welcome > p').textContent='Ask a question. Explore an idea. Chat with Lucid AI V5.';
  document.querySelector('.composer-footer > span').textContent='Lucid V5 · Hosted on the owner’s PC';
  document.querySelector('#memory-dialog .dialog-intro').textContent='Memories belong only to this temporary visitor session.';
  document.querySelector('[data-prompt^="/research"]').dataset.prompt='Explain the differences between local and cloud AI assistants.';
  const unavailable=new Set(['/search','/research','/auto-web','/model','/system']);
  for(let i=commands.length-1;i>=0;i--)if(unavailable.has(commands[i][0].trim().split(' ')[0]))commands.splice(i,1);
  showCommands();publicControls();
  try{
    let config=await fetch('./backend.json',{cache:'no-store',signal:AbortSignal.timeout(10000)}).then(r=>{if(!r.ok)throw Error('Backend not configured.');return r.json();});
    if(config.provider==='huggingface'){
      if(config.space!=='lucidpy/lucid-ai-v5')throw Error('Unknown Lucid hosting configuration.');
      const {Client}=await import('https://cdn.jsdelivr.net/npm/@gradio/client@2.7.0/+esm');
      cloudClient=await Client.connect(config.space,{events:['data','status']});
      const info=await cloudClient.view_api();
      if(info.named_endpoints?.['/hosting_config']){
        const result=await cloudClient.predict('/hosting_config',[]);
        config=result.data[0];
      }
    }
    if(config.provider==='huggingface')return await connectCloud(config,status,banner);
    const url=new URL(config.url);
    if(url.protocol!=='https:'||!url.hostname.endsWith('.trycloudflare.com')||url.username||url.password)throw Error('Invalid backend address.');
    apiBase=url.origin;
    banner.querySelector('span').textContent='Runs on the owner’s PC through Cloudflare. The owner can review messages, replies, and feature usage for up to 24 hours (at most 2,000 requests). Do not share sensitive information.';
    try{publicSession=sessionStorage.getItem('lucid-session:'+apiBase)||'';}catch{}
    if(publicSession){const check=await fetch(apiBase+'/api/state',{headers:sessionHeaders(),signal:AbortSignal.timeout(12000)});if(!check.ok)publicSession='';}
    if(!publicSession){
      const response=await fetch(apiBase+'/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(15000)});
      const body=await response.json();if(!response.ok)throw Error(body.error||'Could not connect.');
      publicSession=body.session;try{sessionStorage.setItem('lucid-session:'+apiBase,publicSession);}catch{}
    }
    await poll();
    setInterval(poll,1500);
  }catch(error){
    status.textContent='Lucid is offline';
    $('error-box').hidden=false;$('error-box').textContent='The host computer or connection is unavailable. Reload to try again. '+error.message;
  }
}
showCommands();
if(hosted){connectPublic();}else{poll();setInterval(poll,600);}

async function connectCloud(config,status,banner){
  cloudMode=true;
  if(config.space!=='lucidpy/lucid-ai-v5')throw Error('Unknown Lucid hosting configuration.');
  status.textContent='Connecting to hosted Lucid V5…';
  banner.querySelector('span').textContent='Hosted on Hugging Face. The owner can review messages, replies, and feature usage for up to 24 hours (at most 2,000 requests). Do not share sensitive information. Free GPU queues and limits apply.';
  const link=el('a','','Open hosted app ↗');link.href='https://huggingface.co/spaces/lucidpy/lucid-ai-v5';link.target='_blank';link.rel='noopener noreferrer';banner.append(link);
  document.querySelector('.local-card p').textContent='Lucid V5 · Free cloud hosting';
  document.querySelector('.composer-footer > span').textContent='Lucid V5 · Hugging Face ZeroGPU';
  document.querySelector('[data-prompt^="Explain the differences"] > span:last-child').textContent='Explore an idea together ↗';
  const {Client}=await import('https://cdn.jsdelivr.net/npm/@gradio/client@2.7.0/+esm');
  cloudClient=cloudClient||await Client.connect(config.space,{events:['data','status']});
  state={messages:[],chats:[],memories:[],events:[],settings:{auto_memory:false,auto_web:false},busy:false,error:'',notice:'',experiment:false,think:false,temperature:0.6,max_tokens:384};
  connected=true;status.textContent='Connected to hosted Lucid AI V5';render();
}

async function sendCloud(message){
  if(!cloudClient||!connected){toast('Lucid is connecting. Please wait.');return false;}
  const previous=JSON.parse(JSON.stringify(state));
  state.busy=true;state.error='';state.notice='';
  if(!message.startsWith('/')||message.startsWith('/teach '))state.messages.push({role:'user',content:message});
  state.events=[{time:'',text:'Waiting for a free GPU…'}];render();
  let received=false;
  try{
    const job=cloudClient.submit('/chat',[message]);
    for await(const event of job){
      if(event.type==='status'){
        if(event.stage==='error'||event.success===false)throw Error(event.message||'The cloud request failed.');
        if(event.stage==='complete')continue;
        const label=event.stage==='pending'?'Waiting in the free GPU queue…':'Lucid is preparing your reply…';
        state.events=[{time:'',text:label}];render();
      }
      if(event.type==='data'){
        const snapshot=event.data.find(value=>value&&Array.isArray(value.messages)&&value.settings);
        if(!snapshot)throw Error('Unexpected response from Lucid.');
        state=snapshot;received=true;render();
      }
    }
    if(!received)throw Error('No reply received. Please try again.');
    return true;
  }catch(error){
    state=previous;state.error=String(error.message||error)+ ' Free GPU usage may be exhausted; open the hosted app for account and quota details.';
    return false;
  }finally{state.busy=false;render();}
}
