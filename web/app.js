const ROTATE_MS = 10000;
const REFRESH_MS = 120000;
let items = [];
let idx = 0;
let CONFIG_SOURCES = [];
let SETTINGS_OPEN = false;

function fmt(iso){
  if(!iso) return '';
  const d=new Date(iso);
  const monthsGen = [
    'ođđajagemánu', 'guovvamánu', 'njukčamánu', 'cuoŋománu',
    'miessemánu', 'geassemánu', 'suoidnemánu', 'borgemánu',
    'čakčamánu', 'golggotmánu', 'skábmamánu', 'juovlamánu'
  ];
  const day = d.getDate();
  const monthRaw = monthsGen[d.getMonth()] || '';
  const month = monthRaw.charAt(0).toUpperCase() + monthRaw.slice(1);
  const year = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${month} ${day}. b. ${year}, ${hh}:${mm}`;
}

function safeItems(raw){
  return (raw||[]).filter(i=>i && i.title && i.url).slice(0,120);
}

function interleaveBySource(arr){
  const buckets = new Map();
  for(const it of arr){
    const k = it.source || 'Eará';
    if(!buckets.has(k)) buckets.set(k, []);
    buckets.get(k).push(it);
  }
  const keys=[...buckets.keys()];
  const out=[];
  let added=true;
  while(added){
    added=false;
    for(const k of keys){
      const b=buckets.get(k);
      if(b && b.length){ out.push(b.shift()); added=true; }
    }
  }
  return out;
}

async function fetchConfigSources(){
  try{
    const r=await fetch('/api/config?ts='+Date.now());
    const c=await r.json();
    CONFIG_SOURCES=(c.sources||[]).filter(s=>s&&s.name&&s.url);
  }catch{ CONFIG_SOURCES=[]; }
}

async function saveConfigSources(){
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sources:CONFIG_SOURCES})});
}

function renderSettings(){
  const wrap=document.getElementById('settingsSources');
  wrap.innerHTML=(CONFIG_SOURCES||[]).map(s=>`<label class="settings-row"><span>${s.name}</span><input type="number" min="1" step="1" data-name="${s.name}" value="${s.maxItems||''}" placeholder="buot"/></label>`).join('');
}

function wireSettings(){
  const btn=document.getElementById('settingsBtn');
  const panel=document.getElementById('settingsPanel');
  const close=document.getElementById('settingsClose');
  const save=document.getElementById('settingsSave');
  const add=document.getElementById('addSourceBtn');
  btn.onclick=async()=>{
    await fetchConfigSources();
    renderSettings();
    panel.classList.toggle('hidden');
    SETTINGS_OPEN = !panel.classList.contains('hidden');
  };
  close.onclick=()=>{
    panel.classList.add('hidden');
    SETTINGS_OPEN = false;
  };
  add.onclick=async()=>{
    const n=document.getElementById('newSourceName').value.trim();
    const u=document.getElementById('newSourceUrl').value.trim();
    const l=document.getElementById('newSourceLimit').value.trim();
    if(!n||!u) return;
    const maxItems=l?Number(l):undefined;
    CONFIG_SOURCES.push({name:n,url:u,...(maxItems?{maxItems}:{})});
    await saveConfigSources();
    renderSettings();
  };
  save.onclick=async()=>{
    const byName=Object.fromEntries((CONFIG_SOURCES||[]).map(s=>[s.name,s]));
    panel.querySelectorAll('[data-name]').forEach(el=>{
      const n=el.dataset.name; const v=(el.value||'').trim();
      if(!byName[n]) return;
      if(v) byName[n].maxItems=Number(v); else delete byName[n].maxItems;
    });
    CONFIG_SOURCES=Object.values(byName);
    await saveConfigSources();
    panel.classList.add('hidden');
    SETTINGS_OPEN = false;
    await loadData();
    next();
  };
}

function render(item){
  const stage=document.getElementById('stage');
  stage.classList.add('fade');
  setTimeout(()=>{
    const bg=document.getElementById('bg');
    const source=document.getElementById('source');
    const title=document.getElementById('title');
    const meta=document.getElementById('meta');
    bg.src = item.image_url || 'https://picsum.photos/1920/1080?blur=1';
    source.textContent = item.source || 'Sápmi dál';
    title.textContent = item.title;
    meta.textContent = fmt(item.published_at);
    stage.classList.remove('fade');
  },620);
}

async function loadData(){
  try{
    const r=await fetch('data/news.json?ts='+Date.now());
    const d=await r.json();
    items=interleaveBySource(safeItems(d.items));
    if(idx>=items.length) idx=0;
  }catch(e){ }
}

function next(){
  if(SETTINGS_OPEN) return;
  if(!items.length) return;
  render(items[idx]);
  idx=(idx+1)%items.length;
}

(async function init(){
  wireSettings();
  await fetchConfigSources();
  await loadData();
  next();
  setInterval(next, ROTATE_MS);
  setInterval(loadData, REFRESH_MS);
})();