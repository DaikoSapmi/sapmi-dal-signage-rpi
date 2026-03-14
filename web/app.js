const ROTATE_MS = 10000;
const REFRESH_MS = 120000;
const WEATHER_REFRESH_MS = 10 * 60 * 1000;
let items = [];
let idx = 0;
let CONFIG_SOURCES = [];
let DISPLAY_COUNT = 5;
let SETTINGS_OPEN = false;

const CLOCK_FMT = new Intl.DateTimeFormat('no-NO', {
  timeZone: 'Europe/Oslo',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit'
});

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

function toMs(iso){
  if(!iso) return 0;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? t : 0;
}

function pickDisplayItems(raw, displayCount=5){
  const count = Number.isFinite(displayCount) && displayCount > 0 ? displayCount : 5;

  // Krav: nyeste nyheter totalt (uansett kilde), rotert kronologisk.
  const valid = (raw || []).filter(i => i && i.title && i.url);

  // Finn de N nyeste først.
  const newest = valid
    .sort((a, b) => toMs(b.published_at) - toMs(a.published_at))
    .slice(0, count);

  // Roter i kronologisk rekkefølge (eldst -> nyest blant de N nyeste).
  return newest.sort((a, b) => toMs(a.published_at) - toMs(b.published_at));
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
    DISPLAY_COUNT = Number.isFinite(Number(d.display_count)) && Number(d.display_count) > 0 ? Number(d.display_count) : 5;
    items=pickDisplayItems(d.items, DISPLAY_COUNT);
    if(idx>=items.length) idx=0;
  }catch(e){ }
}

function next(){
  if(SETTINGS_OPEN) return;
  if(!items.length) return;
  render(items[idx]);
  idx=(idx+1)%items.length;
}

function updateClock(){
  const el = document.getElementById('clock');
  if(!el) return;
  el.textContent = CLOCK_FMT.format(new Date());
}

function weatherEmoji(symbolCode=''){
  const s = (symbolCode || '').toLowerCase();
  if(s.includes('snow') || s.includes('sleet')) return '❄️';
  if(s.includes('rain') || s.includes('drizzle')) return '🌧️';
  if(s.includes('partlycloudy')) return '⛅';
  if(s.includes('cloudy') || s.includes('fog')) return '☁️';
  if(s.includes('clearsky') || s.includes('fair')) return '☀️';
  return '🌤️';
}

async function loadWeather(){
  const el = document.getElementById('weather');
  if(!el) return;
  try{
    const r = await fetch('/api/weather?ts=' + Date.now());
    if(!r.ok) throw new Error('weather unavailable');
    const w = await r.json();
    const t = Number(w.temperature_c);
    const temp = Number.isFinite(t) ? `${Math.round(t)}°C` : '–';
    const emoji = weatherEmoji(w.symbol_code);
    el.textContent = `${w.location || 'Kárášjohka'} dál ${temp} ${emoji}`;
  }catch{
    el.textContent = 'Kárášjohka dál –';
  }
}

(async function init(){
  wireSettings();
  await fetchConfigSources();
  await loadData();
  await loadWeather();
  updateClock();
  next();
  setInterval(updateClock, 1000);
  setInterval(next, ROTATE_MS);
  setInterval(loadData, REFRESH_MS);
  setInterval(loadWeather, WEATHER_REFRESH_MS);
})();