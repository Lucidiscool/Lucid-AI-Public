/* A constrained, offline theme interpreter. Never executes generated CSS or HTML. */
(() => {
  'use strict';
  const key = 'lucid-appearance-v1';
  const presets = {
    studio: {name:'Studio', paper:'#f5f5f7', panel:'#ffffff', ink:'#1d1d1f', muted:'#6e6e73', line:'#dedee3', accent:'#0066cc', soft:'#e8f1fc', sidebar:'#ededf0', dark:false},
    midnight: {name:'Midnight', paper:'#101116', panel:'#1b1d25', ink:'#f5f5f7', muted:'#a6a9b8', line:'#343744', accent:'#93b5ff', soft:'#272f47', sidebar:'#15171e', dark:true},
    ocean: {name:'Ocean', paper:'#f0f7fa', panel:'#ffffff', ink:'#153340', muted:'#536f7a', line:'#cfdee5', accent:'#007c91', soft:'#dceff3', sidebar:'#e6f0f4', dark:false},
    forest: {name:'Forest', paper:'#f3f6f1', panel:'#ffffff', ink:'#223829', muted:'#607164', line:'#d4dfd4', accent:'#35704a', soft:'#e0eddf', sidebar:'#e8eee5', dark:false},
    rose: {name:'Rose', paper:'#faf3f5', panel:'#ffffff', ink:'#392630', muted:'#80616e', line:'#e7d6de', accent:'#b23d70', soft:'#f6e3ec', sidebar:'#f1e7ec', dark:false},
    dusk: {name:'Dusk', paper:'#181420', panel:'#241e30', ink:'#f6efff', muted:'#b5a6c8', line:'#41364f', accent:'#c7a2ff', soft:'#382b49', sidebar:'#201a29', dark:true}
  };
  let current = {preset:'studio', accent:presets.studio.accent, compact:false, rounded:true, glass:65};
  try { const saved=JSON.parse(localStorage.getItem(key)); if(saved && presets[saved.preset] && /^#[\da-f]{6}$/i.test(saved.accent)) current={preset:saved.preset,accent:saved.accent,compact:saved.compact===true,rounded:saved.rounded!==false}; } catch {}
  const root=document.documentElement;
  try {const saved=JSON.parse(localStorage.getItem(key));current.glass=Number.isFinite(saved?.glass)?Math.min(100,Math.max(0,saved.glass)):65;} catch {current.glass=65;}
  const button=document.createElement('button');button.className='appearance-button';button.id='appearance-button';button.textContent='✧ Appearance';button.setAttribute('aria-haspopup','dialog');
  document.querySelector('.top-actions').prepend(button);
  const dialog=document.createElement('dialog');dialog.className='appearance-dialog';dialog.id='appearance-dialog';dialog.setAttribute('aria-labelledby','appearance-title');
  dialog.innerHTML=`<div class="dialog-heading"><div><span class="eyebrow">YOUR SPACE. YOUR STYLE.</span><h2 id="appearance-title">Make yourself at home.</h2></div><button class="icon-button" id="close-appearance" aria-label="Close appearance">×</button></div>
    <p class="appearance-intro">A fresh perspective, whenever you feel like it.</p><div class="theme-presets" aria-label="Theme presets"></div>
    <form id="theme-form"><label class="theme-label" for="theme-description">Describe your theme</label><textarea class="theme-prompt" id="theme-description" maxlength="300" placeholder="A dark purple space, with soft corners…"></textarea>
    <div class="theme-examples"><button type="button">Minimal Apple white</button><button type="button">Dark purple and cozy</button><button type="button">Ocean blue, compact</button></div>
    <div class="theme-actions"><button class="primary-button" type="submit">Apply description ↗</button><button class="theme-reset" type="button" id="reset-appearance">Reset to Studio</button></div></form>
    <div class="appearance-options"><label>Accent <input id="theme-accent" type="color" aria-label="Accent color"></label><label><input id="theme-compact" type="checkbox"> Compact</label><label><input id="theme-rounded" type="checkbox"> Soft corners</label></div>
    <p class="theme-feedback" id="theme-feedback" role="status">Saved on this device. Descriptions match built-in colors and styles; no model connection needed.</p>`;
  document.body.append(dialog);
  const glassControl=document.createElement('section');glassControl.className='glass-control';
  glassControl.innerHTML='<div class="glass-heading"><label class="theme-label" for="theme-glass">Liquid glass</label><output id="glass-value" for="theme-glass">65%</output></div><p id="glass-help">Dial up the glow, frosted surfaces, and glossy reflections.</p><input id="theme-glass" type="range" min="0" max="100" step="1" value="65" aria-describedby="glass-help"><div class="glass-scale"><span>Off</span><span>Subtle</span><span>Full glass</span></div>';
  dialog.querySelector('.theme-presets').after(glassControl);
  const byId=id=>document.getElementById(id);
  Object.entries(presets).forEach(([id,preset])=>{
    const item=document.createElement('button');item.type='button';item.className='theme-preset';item.dataset.preset=id;
    const preview=document.createElement('span');preview.className='theme-preview';preview.textContent='✦';preview.style.setProperty('--swatch-bg',preset.paper);preview.style.setProperty('--swatch-accent',preset.accent);
    item.append(preview,document.createTextNode(preset.name));item.onclick=()=>{current.preset=id;current.accent=preset.accent;apply();feedback(preset.name+' applied.');};dialog.querySelector('.theme-presets').append(item);
  });
  function feedback(text){byId('theme-feedback').textContent=text;}
  function apply(){
    const p=presets[current.preset];
    const glass=current.glass/100;
    root.dataset.glass=current.glass>0?'on':'off';
    root.style.setProperty('--glass-opacity',String(glass));
    root.style.setProperty('--glass-surface',(100-glass*44)+'%');
    root.style.setProperty('--glass-sidebar',(100-glass*22)+'%');
    root.style.setProperty('--glass-blur',(glass*28)+'px');
    root.style.setProperty('--glass-highlight',String(glass*(p.dark?.19:.85)));
    root.style.setProperty('--glass-shadow',String(glass*(p.dark?.28:.10)));
    byId('theme-glass').value=current.glass;byId('glass-value').value=current.glass+'%';
    byId('theme-glass').setAttribute('aria-valuetext',current.glass===0?'Off':current.glass+' percent');
    for(const token of ['paper','panel','ink','muted','line','soft','sidebar'])root.style.setProperty('--'+token,p[token]);
    root.style.setProperty('--accent',current.accent);root.style.setProperty('--radius',current.rounded?'22px':'10px');root.style.colorScheme=p.dark?'dark':'light';root.dataset.density=current.compact?'compact':'comfortable';
    const rgb=current.accent.slice(1).match(/../g).map(c=>{const v=parseInt(c,16)/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});
    root.style.setProperty('--on-accent',rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722>.179?'#111111':'#ffffff');
    document.querySelector('.brand img').style.filter=p.dark?'invert(1)':'none';
    byId('theme-accent').value=current.accent;byId('theme-compact').checked=current.compact;byId('theme-rounded').checked=current.rounded;
    dialog.querySelectorAll('[data-preset]').forEach(item=>item.setAttribute('aria-pressed',String(item.dataset.preset===current.preset)));
    try{localStorage.setItem(key,JSON.stringify(current));}catch{feedback('Theme applied. Browser storage is unavailable, so it may reset when you reload.');}
  }
  function describe(text){
    const t=text.toLowerCase();
    const dark=/\b(dark|black|night|midnight|space|moody)\b/.test(t);
    let preset=/\b(purple|violet|lavender|dusk)\b/.test(t)?'dusk':/\b(ocean|sea|teal|aqua|blue)\b/.test(t)?'ocean':/\b(forest|green|nature|sage)\b/.test(t)?'forest':/\b(rose|pink|blush)\b/.test(t)?'rose':/\b(apple|white|light|minimal|clean|studio|silver)\b/.test(t)?'studio':dark?'midnight':null;
    const colors={red:'#b92d3d',orange:'#ae5000',yellow:'#8c6900',gold:'#8c6900',pink:'#b23d70',purple:'#8053bc',violet:'#8053bc',lavender:'#8053bc',blue:'#0066cc',teal:'#007c91',green:'#35704a'};
    const lightColors={red:'#ff9ca5',orange:'#ffba7c',yellow:'#efdb87',gold:'#efdb87',pink:'#ffa6d0',purple:'#c7a2ff',violet:'#c7a2ff',lavender:'#c7a2ff',blue:'#93b5ff',teal:'#80d3df',green:'#9cdbad'};
    const color=Object.keys(colors).find(c=>new RegExp('\\b'+c+'\\b').test(t));
    const hex=t.match(/#[a-f\d]{6}\b/);
    const density=/\b(compact|dense|spacious|airy|comfortable)\b/.test(t), corners=/\b(rounded|round|soft|sharp|square)\b/.test(t);
    const glassStyle=/\b(glass|glassy|frosted|liquid)\b/.test(t);
    if(!preset&&!color&&!hex&&!density&&!corners&&!glassStyle){feedback('Try a color or style such as “dark blue”, “forest”, “liquid glass”, “compact”, or “soft corners”. Your theme has not changed.');return;}
    if(glassStyle)current.glass=/\b(no|off|without)\b/.test(t)?0:/\b(subtle|gentle)\b/.test(t)?30:85;
    if(dark&&preset!=='dusk')preset='midnight';
    if(/\b(light|white)\b/.test(t)&&preset==='dusk')preset='studio';
    if(preset){current.preset=preset;current.accent=presets[preset].accent;}
    if(color)current.accent=(presets[current.preset].dark?lightColors:colors)[color];
    if(hex)current.accent=hex[0];
    if(density)current.compact=/\b(compact|dense)\b/.test(t);
    if(corners)current.rounded=!/\b(sharp|square)\b/.test(t);
    apply();feedback(presets[current.preset].name+' applied with '+(current.compact?'compact':'comfortable')+' spacing. Adjust any detail below.');
  }
  button.onclick=()=>dialog.showModal();byId('close-appearance').onclick=()=>dialog.close();
  document.addEventListener('lucid-theme',event=>{dialog.showModal();byId('theme-description').value=String(event.detail||'');if(event.detail)describe(String(event.detail));});
  dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
  byId('theme-form').onsubmit=event=>{event.preventDefault();describe(byId('theme-description').value);};
  dialog.querySelectorAll('.theme-examples button').forEach(item=>item.onclick=()=>{byId('theme-description').value=item.textContent;describe(item.textContent);});
  byId('theme-accent').oninput=event=>{current.accent=event.target.value;apply();};byId('theme-compact').onchange=event=>{current.compact=event.target.checked;apply();};byId('theme-rounded').onchange=event=>{current.rounded=event.target.checked;apply();};
  byId('theme-glass').oninput=event=>{current.glass=Number(event.target.value);apply();};
  byId('reset-appearance').onclick=()=>{current={preset:'studio',accent:presets.studio.accent,compact:false,rounded:true,glass:65};byId('theme-description').value='';apply();feedback('Restored the default Studio theme.');};
  const sidebar=byId('sidebar'),scrim=byId('sidebar-scrim'),menu=byId('menu-button');menu.setAttribute('aria-controls','sidebar');
  function syncNavigation(){const open=sidebar.classList.contains('open');scrim.hidden=!open;menu.setAttribute('aria-expanded',String(open));sidebar.inert=window.innerWidth<=800&&!open;}
  scrim.onclick=()=>{sidebar.classList.remove('open');menu.focus();};new MutationObserver(syncNavigation).observe(sidebar,{attributes:true,attributeFilter:['class']});window.addEventListener('resize',syncNavigation);syncNavigation();apply();
})();
