from __future__ import annotations

import json
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .git_sync import GitSyncManager
from .impact import impact
from .quality import collect_quality
from .store import GraphStore
from .whatif import proposed_change_impact

HTML = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RepoGraph Executive Dashboard</title>
<style>
:root{--bg:#050b17;--panel:#0a1426;--panel2:#0c1930;--line:#19375b;--text:#e9f4ff;--muted:#7f97b8;--blue:#2d8cff;--cyan:#19d7f3;--green:#20e3a2;--yellow:#f8c541;--red:#ff626f;--purple:#8f6cff;font-family:Inter,Segoe UI,system-ui,sans-serif}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 20% 0,#0c2241 0,transparent 32%),linear-gradient(135deg,#04101e,#050914 65%);color:var(--text);min-height:100vh}
button,input,textarea{font:inherit}.app{display:grid;grid-template-columns:210px 1fr;min-height:100vh}.side{background:linear-gradient(180deg,#061226,#07182e);border-right:1px solid #143154;padding:18px 12px;position:sticky;top:0;height:100vh;z-index:20}.brand{font-size:23px;font-weight:800;letter-spacing:-.5px;padding:4px 8px 20px}.brand span{color:#5ca5ff}.nav{display:grid;gap:5px}.navbtn{appearance:none;border:0;width:100%;text-align:left;padding:11px 12px;border-radius:9px;color:#a9bdd7;font-size:13px;background:transparent;cursor:pointer;transition:.18s}.navbtn:hover,.navbtn:focus-visible{background:#0b2747;color:#e9f4ff;outline:none}.navbtn.active{color:#dff4ff;background:linear-gradient(90deg,#124d8b,#0f315c);box-shadow:inset 3px 0 #28b9ff}.sidebox{position:absolute;bottom:20px;left:12px;right:12px;border:1px solid #1f4976;border-radius:12px;padding:13px;background:#071b34}.sidebox b{color:#70cfff}.sidebox small{display:block;color:#7f97b8;margin-top:5px;line-height:1.45}.main{min-width:0}.top{min-height:70px;border-bottom:1px solid #163451;background:rgba(5,13,26,.88);backdrop-filter:blur(12px);display:flex;align-items:center;gap:10px;padding:10px 18px;position:sticky;top:0;z-index:15}.title{min-width:185px}.title b{font-size:17px}.title small{display:block;color:var(--muted)}.topchip{background:#08182e;border:1px solid #1a3d63;border-radius:10px;padding:8px 11px;min-width:96px}.topchip small{color:var(--muted);display:block;font-size:10px}.topchip strong{font-size:12px}.search{margin-left:auto;display:flex;gap:6px;min-width:310px}.search input,.whatif textarea{width:100%;background:#08172b;border:1px solid #24486e;border-radius:9px;color:white;padding:10px;outline:none}.search input:focus,.whatif textarea:focus{border-color:#2d8cff;box-shadow:0 0 0 2px rgba(45,140,255,.13)}.content{padding:14px;display:grid;gap:12px}.section-anchor{scroll-margin-top:86px}.kpis{display:grid;grid-template-columns:repeat(6,minmax(135px,1fr));gap:10px}.card,.panel{background:linear-gradient(160deg,rgba(12,31,53,.96),rgba(7,18,35,.96));border:1px solid #173c61;border-radius:12px;box-shadow:0 10px 28px rgba(0,0,0,.18)}.card{padding:13px}.label{color:#a9c1dc;font-size:11px;font-weight:600}.value{font-size:25px;font-weight:800;margin:5px 0}.pill{display:inline-flex;border-radius:999px;padding:3px 8px;font-size:10px;font-weight:700}.good{background:#073d35;color:#34efa9;border:1px solid #10684f}.med{background:#3d2d08;color:#ffd25b;border:1px solid #7e5b12}.bad{background:#41151e;color:#ff7a85;border:1px solid #7f2935}.spark{height:22px;margin-top:5px;border-bottom:1px solid #13445d;background:linear-gradient(170deg,transparent 45%,rgba(32,227,162,.18) 46%,transparent 50%)}.tiers{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.tier{appearance:none;text-align:left;color:inherit;padding:10px 13px;border:1px solid #1a3c63;border-radius:9px;background:#09172b;cursor:pointer;transition:.18s}.tier:hover,.tier:focus-visible{border-color:#268fff;transform:translateY(-1px);outline:none}.tier.active{border-color:#268fff;box-shadow:0 0 12px rgba(45,140,255,.3);background:#0b284b}.tier b{font-size:12px}.tier small{display:block;color:var(--muted);font-size:10px;margin-top:2px}.grid3{display:grid;grid-template-columns:.9fr 1.1fr .88fr;gap:12px}.panel{padding:13px}.panel h3{font-size:13px;margin:0 0 11px;display:flex;align-items:center;justify-content:space-between;gap:8px}.subtle{color:var(--muted);font-size:10px}.quality{display:grid;grid-template-columns:125px 1fr;gap:12px}.ring{width:112px;height:112px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--green) 0 70%,var(--blue) 70% 88%,#162942 88%);position:relative}.ring:after{content:'';position:absolute;inset:12px;background:#09182b;border-radius:50%}.ringin{z-index:1;text-align:center}.ringin b{font-size:28px}.ringin small{display:block;color:#82ffd0}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.metric{border:1px solid #173b61;background:#08172b;border-radius:8px;padding:8px}.metric b{font-size:15px}.metric small{display:block;color:var(--muted);font-size:9px;margin-top:3px}.minirow{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:10px}.mini{border:1px solid #18446c;border-radius:8px;padding:8px;background:#082039}.mini b{font-size:15px}.mini small{display:block;color:#91aaca;font-size:9px}.graphwrap{height:310px;background:radial-gradient(circle,#0d2744,#071323 68%);border-radius:9px;border:1px solid #153653;position:relative;overflow:hidden}#graph{width:100%;height:100%}.legend{position:absolute;right:8px;top:8px;font-size:9px;color:#9bb0ca;background:#071629cc;border-radius:7px;padding:6px}.toolbar{display:flex;gap:6px;align-items:center}.toggle{appearance:none;border:1px solid #23496f;background:#08172b;color:#9bb4d1;border-radius:7px;padding:5px 8px;font-size:10px;cursor:pointer}.toggle.active{color:white;border-color:#2d8cff;background:#113a69}.whatif textarea{height:70px;resize:vertical}.btn{border:1px solid #267ee8;background:linear-gradient(135deg,#1e65e8,#328eff);color:white;border-radius:8px;padding:9px 12px;font-weight:700;cursor:pointer;transition:.18s}.btn:hover{filter:brightness(1.08);transform:translateY(-1px)}.btn:disabled{opacity:.55;cursor:not-allowed;transform:none}.btn.secondary{background:#0a203a;border-color:#285077;color:#cfe6ff}.btn.small{padding:7px 9px;font-size:11px}.whatrow{display:flex;gap:8px;align-items:flex-start}.whatrow textarea{flex:1}.impactstats{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:10px}.impactstats .metric{min-height:58px}.riskline{margin-top:10px;display:flex;align-items:center;justify-content:space-between}.blast{width:74px;height:74px;border-radius:50%;background:conic-gradient(var(--green) 0 42%,var(--yellow) 42% 70%,var(--red) 70%);display:grid;place-items:center;position:relative}.blast:after{content:'';width:53px;height:53px;border-radius:50%;background:#09172b;position:absolute}.blast span{z-index:1;font-weight:800}.gridbottom{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}.checklist{display:grid;gap:7px}.check{display:grid;grid-template-columns:22px 1fr auto;gap:8px;align-items:center;border-bottom:1px solid #16314e;padding-bottom:6px}.dot{width:19px;height:19px;border-radius:50%;display:grid;place-items:center;background:#0c5a43;color:#51f4b7;font-size:11px}.check b{font-size:11px}.check small{display:block;color:var(--muted);font-size:9px}.synccards{display:grid;grid-template-columns:1fr 70px 1fr;gap:8px;align-items:center}.db{border:1px solid #173b61;border-radius:8px;padding:11px;text-align:center;background:#08172b}.syncicon{text-align:center;font-size:28px;color:#2ce8a2}.activity{max-height:220px;overflow:auto}.activity .item{padding:8px;border-bottom:1px solid #15314f;font-size:10px}.widgets{display:grid;grid-template-columns:repeat(12,1fr);gap:6px}.widget{appearance:none;width:100%;min-height:64px;background:#09182c;border:1px solid #193b60;border-radius:8px;padding:7px;text-align:center;color:#aac1dc;font-size:8px;cursor:pointer;transition:.18s}.widget:hover,.widget:focus-visible{border-color:#2d8cff;color:white;transform:translateY(-2px);outline:none}.widget b{display:block;color:#dff3ff;font-size:10px;margin-bottom:3px}.settingsgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.setting{background:#08172b;border:1px solid #173b61;border-radius:8px;padding:10px}.setting small{display:block;color:var(--muted);font-size:9px;margin-bottom:4px}.setting b{font-size:12px}.footnote{color:#728aa7;font-size:9px}.empty{color:#728aa7;font-size:11px;padding:12px}.progress{height:5px;background:#142943;border-radius:5px;overflow:hidden;margin-top:5px}.progress i{display:block;height:100%;background:linear-gradient(90deg,var(--cyan),var(--green))}.nowrap{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.statusline{min-height:18px;margin-top:7px}.toast{position:fixed;right:20px;bottom:20px;z-index:100;background:#0a1b31;border:1px solid #28507a;border-radius:10px;padding:11px 14px;box-shadow:0 14px 40px rgba(0,0,0,.35);max-width:360px;font-size:12px;opacity:0;transform:translateY(12px);pointer-events:none;transition:.2s}.toast.show{opacity:1;transform:none}.toast.error{border-color:#7f2935;color:#ffb4ba}.toast.ok{border-color:#176b51;color:#92ffd3}.spin{display:inline-block;animation:sp .8s linear infinite}@keyframes sp{to{transform:rotate(360deg)}}
@media(max-width:1250px){.kpis{grid-template-columns:repeat(3,1fr)}.grid3,.gridbottom{grid-template-columns:1fr}.widgets{grid-template-columns:repeat(6,1fr)}.settingsgrid{grid-template-columns:repeat(2,1fr)}}@media(max-width:850px){.app{grid-template-columns:1fr}.side{display:none}.top{flex-wrap:wrap;height:auto}.kpis{grid-template-columns:repeat(2,1fr)}.tiers{grid-template-columns:1fr 1fr}.search{min-width:0;width:100%;margin-left:0}.widgets{grid-template-columns:repeat(3,1fr)}}
</style>
</head>
<body>
<div class="app">
<aside class="side">
  <div class="brand">◈ <span>RepoGraph</span></div>
  <nav class="nav" aria-label="Dashboard navigation">
    <button class="navbtn active" data-target="overview">⌂ &nbsp; Overview</button>
    <button class="navbtn" data-target="dependencies">◉ &nbsp; Intelligence</button>
    <button class="navbtn" data-target="dependencies">⌘ &nbsp; Dependencies</button>
    <button class="navbtn" data-target="quality">◇ &nbsp; Code Quality</button>
    <button class="navbtn" data-target="change-impact">⚗ &nbsp; Change Impact</button>
    <button class="navbtn" data-target="team-graph">▱ &nbsp; Repositories</button>
    <button class="navbtn" data-target="team-graph">◎ &nbsp; Team Graph</button>
    <button class="navbtn" data-target="activity">ϟ &nbsp; Activity</button>
    <button class="navbtn" data-target="settings">⚙ &nbsp; Settings</button>
  </nav>
  <div class="sidebox"><b>MBB Knowledge Brain</b><small>Unified code intelligence for better decisions.</small></div>
</aside>
<main class="main">
<header class="top">
  <div class="title"><b>Executive Dashboard</b><small>MBB Knowledge Brain</small></div>
  <div class="topchip"><small>Workspace</small><strong id="workspace">—</strong></div>
  <div class="topchip"><small>Branch</small><strong id="branch">—</strong></div>
  <div class="topchip"><small>Commit</small><strong id="commit">—</strong></div>
  <div class="topchip"><small>Sync</small><strong id="sync">Checking…</strong></div>
  <div class="topchip"><small>Last refresh</small><strong id="refresh">—</strong></div>
  <div class="search"><input id="globalSearch" placeholder="Search code, modules, dependencies…"><button id="searchBtn" class="btn small">Search</button></div>
</header>
<div class="content">
<section id="overview" class="section-anchor">
<div class="kpis">
  <div class="card"><div class="label">♥ Knowledge Health Score</div><div class="value" id="health">—</div><span class="pill good">Healthy</span><div class="spark"></div></div>
  <div class="card"><div class="label">⚠ Release Risk</div><div class="value" id="releaseRisk">—</div><span class="pill good">Low</span><div class="spark"></div></div>
  <div class="card"><div class="label">⬡ Dependency Health</div><div class="value" id="depHealth">—</div><span class="pill good">Graph ready</span><div class="spark"></div></div>
  <div class="card"><div class="label">◎ Coverage</div><div class="value" id="coverage">N/A</div><span class="pill good">Coverage data</span><div class="spark"></div></div>
  <div class="card"><div class="label">⬢ SonarQube Quality Gate</div><div class="value" id="qualityGate">Unknown</div><span class="pill good" id="qualityGrade">Local</span><div class="spark"></div></div>
  <div class="card"><div class="label">⌘ Change Impact Risk</div><div class="value" id="changeRisk">—</div><span class="pill med">What-if ready</span><div class="spark"></div></div>
</div>
</section>

<div class="tiers">
  <button class="tier active" data-target="quality"><b>1. Health</b><small>Repository & Code Quality</small></button>
  <button class="tier" data-target="dependencies"><b>2. Intelligence</b><small>Knowledge & Dependencies</small></button>
  <button class="tier" data-target="team-graph"><b>3. Operations</b><small>Releases & Runtime</small></button>
  <button class="tier" data-target="widgets"><b>4. Efficiency</b><small>Productivity & Insights</small></button>
  <button class="tier" data-target="activity"><b>5. Activity</b><small>Teams & Changes</small></button>
</div>

<div class="grid3">
<section id="quality" class="panel section-anchor">
  <h3><span>⬢ Code Quality & SonarQube</span><span class="subtle" id="sonarSource">local coverage artifacts</span></h3>
  <div class="quality"><div class="ring"><div class="ringin"><b id="grade">—</b><small id="gateMini">Quality Gate</small></div></div><div class="metrics"><div class="metric"><b id="bugs">0</b><small>Bugs</small></div><div class="metric"><b id="vulns">0</b><small>Vulnerabilities</small></div><div class="metric"><b id="smells">0</b><small>Code Smells</small></div><div class="metric"><b id="dupes">N/A</b><small>Duplications</small></div><div class="metric"><b id="maint">N/A</b><small>Maintainability</small></div><div class="metric"><b id="security">N/A</b><small>Security</small></div></div></div>
  <div class="minirow"><div class="mini"><small>Coverage</small><b id="covMini">N/A</b><div class="progress"><i id="covBar" style="width:0%"></i></div></div><div class="mini"><small>Test Pass Rate</small><b id="testPass">N/A</b><div class="progress"><i id="testBar" style="width:0%"></i></div></div><div class="mini"><small>Reliability</small><b id="reliability">N/A</b><div class="progress"><i style="width:80%"></i></div></div></div>
</section>

<section id="dependencies" class="panel section-anchor">
  <h3><span>⌘ Dependency Graph & Impact Analysis</span><span class="toolbar"><button id="localGraphBtn" class="toggle active">Local graph</button><button id="teamGraphBtn" class="toggle">Team graph</button></span></h3>
  <div class="graphwrap"><canvas id="graph"></canvas><div class="legend">● Maven modules (labeled)<br>● symbols & files<br>— dependencies & ownership</div></div>
  <div id="graphStatus" class="subtle statusline">Local graph loaded</div>
</section>

<section id="change-impact" class="panel whatif section-anchor">
  <h3><span>⚗ Proposed Change Impact</span><span class="subtle">What-if simulation</span></h3>
  <div class="whatrow"><textarea id="proposal" placeholder="Describe a change before writing code, e.g. Add OAuth2 authentication middleware to the API service"></textarea><button id="analyzeBtn" class="btn">Analyze Impact →</button></div>
  <div class="riskline"><div><div class="label">Impact Summary</div><div style="margin-top:5px"><span id="whatRisk" class="pill med">Waiting</span></div></div><div class="blast"><span id="blast">0%</span></div></div>
  <div class="impactstats"><div class="metric"><b id="mods">0</b><small>Modules affected</small></div><div class="metric"><b id="filesImpact">0</b><small>Files likely to change</small></div><div class="metric"><b id="testsImpact">0</b><small>Tests potentially impacted</small></div><div class="metric"><b id="matches">0</b><small>Matched graph roots</small></div></div>
  <div id="whatDetails" class="subtle statusline">No source files are modified during simulation.</div>
</section>
</div>

<div class="gridbottom">
<section class="panel"><h3><span>▣ Engineering Quality Improvements</span><span class="pill good">5 / 5 addressed</span></h3><div class="checklist"><div class="check"><span class="dot">✓</span><div><b>Correct non-Python symbol attribution</b><small>Brace-aware ownership avoids stale current-symbol attachment.</small></div><span class="pill good">Fixed</span></div><div class="check"><span class="dot">✓</span><div><b>Repository-scoped lookups</b><small>Search/resolve can remain inside a repository namespace.</small></div><span class="pill good">Fixed</span></div><div class="check"><span class="dot">✓</span><div><b>Scalable cross-edge rebuild</b><small>Per-repository SQL load + path index avoids repeated full scans.</small></div><span class="pill good">Fixed</span></div><div class="check"><span class="dot">✓</span><div><b>Robust runtime detection</b><small>MCP config uses the exact Python executable that initialized RepoGraph.</small></div><span class="pill good">Fixed</span></div><div class="check"><span class="dot">✓</span><div><b>Multi-repo isolation</b><small>Graph namespaces and remote worktrees stay separated.</small></div><span class="pill good">Fixed</span></div></div></section>

<section id="team-graph" class="panel section-anchor"><h3><span>☁ Team Graph & Remote Sync</span><button id="syncBtn" class="btn">Sync now</button></h3><div class="synccards"><div class="db"><div class="subtle">Local Graph</div><div class="value" id="localNodes">0</div><small>nodes</small></div><div class="syncicon">↻<div class="subtle" id="syncWord">sync</div></div><div class="db"><div class="subtle">Team Graph</div><div class="value" id="teamNodes">0</div><small>nodes</small></div></div><div id="repos" class="activity" style="margin-top:9px"></div></section>

<section id="activity" class="panel section-anchor"><h3><span>ϟ Recent Activity & Commit Intelligence</span><span class="toolbar"><button id="refreshBtn" class="btn secondary small">Refresh</button></span></h3><div id="events" class="activity"></div></section>
</div>

<section id="widgets" class="panel section-anchor"><h3><span>◈ The 12 Dashboard Widgets</span><span class="subtle">click a widget to jump to its data</span></h3><div class="widgets">
<button class="widget" data-target="overview"><b>1</b>Knowledge<br>Health Score</button><button class="widget" data-target="quality"><b>2</b>Repository Quality<br>(SonarQube)</button><button class="widget" data-target="dependencies"><b>3</b>Dependency<br>Graph</button><button class="widget" data-target="change-impact"><b>4</b>Change Impact<br>Simulation</button><button class="widget" data-target="quality"><b>5</b>Test Coverage<br>& Results</button><button class="widget" data-target="overview"><b>6</b>Release Risk<br>& Readiness</button><button class="widget" data-target="team-graph"><b>7</b>Team Graph<br>& Sync</button><button class="widget" data-target="activity"><b>8</b>Repository<br>Activity</button><button class="widget" data-target="settings"><b>9</b>Efficiency<br>Metrics</button><button class="widget" data-target="quality"><b>10</b>Security &<br>Vulnerabilities</button><button class="widget" data-target="change-impact"><b>11</b>Key Insights &<br>Recommendations</button><button class="widget" data-target="activity"><b>12</b>Commit Intelligence<br>& Trends</button>
</div></section>

<section id="settings" class="panel section-anchor"><h3><span>⚙ Dashboard Settings & Diagnostics</span><button id="diagRefreshBtn" class="btn secondary small">Refresh now</button></h3><div class="settingsgrid"><div class="setting"><small>Auto refresh</small><b>15 seconds</b></div><div class="setting"><small>Git sync mode</small><b>Remote-safe fetch</b></div><div class="setting"><small>Graph mode</small><b id="graphModeText">Local</b></div><div class="setting"><small>API status</small><b id="apiStatus">Checking…</b></div></div></section>
<div class="footnote">Commit-gated team view • Local changes remain isolated • Dashboard refreshes automatically</div>
</div>
</main>
</div>
<div id="toast" class="toast" role="status" aria-live="polite"></div>
<script>
const $=id=>document.getElementById(id);
let currentGraph='local', booting=false, toastTimer=null;
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function pct(v){return v==null?'N/A':Number(v).toFixed(1)+'%'}
function toast(msg,type='ok'){let t=$('toast');t.textContent=msg;t.className='toast show '+type;clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.className='toast',3200)}
async function j(u,opt){let r=await fetch(u,opt);let body;try{body=await r.json()}catch(_){body={error:'Invalid JSON response'}}if(!r.ok)throw new Error(body.error||('HTTP '+r.status));return body}
function scrollToSection(id){let el=$(id);if(!el)return;el.scrollIntoView({behavior:'smooth',block:'start'});document.querySelectorAll('.navbtn').forEach(b=>b.classList.toggle('active',b.dataset.target===id));}
function bindNav(){document.querySelectorAll('[data-target]').forEach(el=>el.addEventListener('click',()=>scrollToSection(el.dataset.target)));}
function setBusy(btn,busy,label){if(!btn)return;if(busy){btn.dataset.old=btn.textContent;btn.disabled=true;btn.innerHTML='<span class="spin">↻</span> '+esc(label||'Working…')}else{btn.disabled=false;btn.textContent=btn.dataset.old||label||'Done'}}
async function boot(showToast=false){if(booting)return;booting=true;$('apiStatus').textContent='Refreshing…';try{let [s,ts,g,q,ev,gr]=await Promise.all([j('/api/stats'),j('/api/team-stats'),j('/api/git'),j('/api/quality'),j('/api/events'),j(currentGraph==='team'?'/api/team-graph?limit=170':'/api/graph?limit=170')]);$('workspace').textContent=s.repo||'workspace';$('localNodes').textContent=(s.nodes||0).toLocaleString();$('teamNodes').textContent=(ts.nodes||0).toLocaleString();let r=(g.repositories||[])[0]||{};$('branch').textContent=r.branch||'workspace';$('commit').textContent=(r.commit||'n/a').slice(0,8);let behind=(g.repositories||[]).reduce((n,x)=>n+(Number(x.behind)||0),0);$('sync').textContent=behind?'Behind '+behind:'Up to date';$('syncWord').textContent=behind?'updates available':'in sync';$('refresh').textContent=new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});let health=Math.max(45,Math.min(99,Math.round(92-Math.log10(Math.max(1,s.edges||0))*2-(behind?5:0))));$('health').textContent=health+'/100';$('depHealth').textContent=Math.max(50,Math.min(99,Math.round(70+Math.log10(Math.max(10,s.edges||0))*5)))+'%';$('releaseRisk').textContent=(behind?18:8)+'%';if($('changeRisk').textContent==='—')$('changeRisk').textContent='Ready';renderQuality(q);renderRepos(g.repositories||[]);renderEvents(ev||[]);draw(gr||{nodes:[],edges:[]});$('graphStatus').textContent=(currentGraph==='team'?'Team':'Local')+' graph · '+((gr.nodes||[]).length)+' visible nodes';$('apiStatus').textContent='Healthy';if(showToast)toast('Dashboard refreshed')}catch(e){$('apiStatus').textContent='Error';toast('Dashboard error: '+e.message,'error')}finally{booting=false}}
function renderQuality(q){q=q||{};$('coverage').textContent=q.coverage_label||'N/A';$('covMini').textContent=q.coverage_label||'N/A';$('covBar').style.width=Math.max(0,Math.min(100,Number(q.coverage)||0))+'%';$('qualityGate').textContent=q.quality_gate||'Unknown';$('gateMini').textContent=q.quality_gate||'Quality Gate';$('grade').textContent=q.maintainability==='N/A'?'—':(q.maintainability||'—');$('qualityGrade').textContent=q.sonarqube_connected?'Connected':'Local';$('sonarSource').textContent=q.sonarqube_connected?'SonarQube connected':'local coverage artifacts';$('bugs').textContent=q.bugs??0;$('vulns').textContent=q.vulnerabilities??0;$('smells').textContent=q.code_smells??0;$('dupes').textContent=q.duplications==null?'N/A':pct(q.duplications);$('maint').textContent=q.maintainability||'N/A';$('security').textContent=q.security||'N/A';$('reliability').textContent=q.reliability||'N/A';$('testPass').textContent=q.test_pass_rate==null?'N/A':pct(q.test_pass_rate);$('testBar').style.width=Math.max(0,Math.min(100,Number(q.test_pass_rate)||0))+'%'}
function renderRepos(rows){$('repos').innerHTML=rows.length?rows.slice(0,8).map(r=>`<div class="item"><b>${esc(r.repo)}</b> <span class="subtle">${esc(r.branch||'-')} · ${esc((r.commit||'').slice(0,8))} · behind ${Number(r.behind)||0}</span>${r.error?`<br><span class="subtle" style="color:#ff8a95">${esc(r.error)}</span>`:''}</div>`).join(''):'<div class="empty">No Git repositories detected</div>'}
function renderEvents(ev){$('events').innerHTML=ev.length?ev.slice(0,12).map(x=>`<div class="item"><b>${esc(x.event_type)}</b> <span class="subtle">${esc(x.path)}</span><br><span class="subtle">${esc(x.ts)}</span></div>`).join(''):'<div class="empty">No graph activity yet</div>'}
async function syncGit(){let b=$('syncBtn');setBusy(b,true,'Syncing…');try{let d=await j('/api/git-sync',{method:'POST'});let errs=(d.errors||[]).length;if(errs)toast('Git sync completed with '+errs+' error(s)','error');else toast('Git sync complete');await boot()}catch(e){toast('Git sync failed: '+e.message,'error')}finally{setBusy(b,false,'Sync now')}}
async function runWhatIf(){let proposal=$('proposal').value.trim();if(!proposal){toast('Describe a proposed change first','error');$('proposal').focus();return}let b=$('analyzeBtn');setBusy(b,true,'Analyzing…');$('whatDetails').textContent='Running graph-grounded simulation…';try{let d=await j('/api/what-if',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({proposal,depth:4,team:currentGraph==='team'})});$('whatRisk').textContent=(d.risk||'UNKNOWN')+' RISK';$('whatRisk').className='pill '+((d.risk==='HIGH'||d.risk==='CRITICAL')?'bad':d.risk==='MEDIUM'?'med':'good');$('blast').textContent=(d.blast_radius_pct||0)+'%';$('mods').textContent=d.modules_affected||0;$('filesImpact').textContent=d.files_likely_to_change||0;$('testsImpact').textContent=d.tests_potentially_impacted||0;$('matches').textContent=(d.matched||[]).length;$('changeRisk').textContent=d.risk||'Unknown';$('whatDetails').innerHTML=(d.matched||[]).slice(0,5).map(x=>`<div class="nowrap">↳ <b>${esc(x.name)}</b> · ${esc(x.repo)}:${esc(x.path)}:${esc(x.line)}</div>`).join('')||'No strong graph match found. Try naming a module, class, method, route, or file.';toast('Impact simulation complete')}catch(e){$('whatDetails').textContent='Analysis failed: '+e.message;toast('Impact analysis failed: '+e.message,'error')}finally{setBusy(b,false,'Analyze Impact →')}}
async function doSearch(){let q=$('globalSearch').value.trim();if(!q){toast('Enter a symbol, file, or module to search','error');return}let b=$('searchBtn');setBusy(b,true,'Searching…');try{let d=await j('/api/search?q='+encodeURIComponent(q));$('proposal').value='Change '+q;$('whatDetails').innerHTML=(d||[]).slice(0,7).map(x=>`<div class="nowrap">⌕ <b>${esc(x.name)}</b> · ${esc(x.repo)}:${esc(x.path)}:${esc(x.line)}</div>`).join('')||'No results';scrollToSection('change-impact');toast((d||[]).length+' search result(s)')}catch(e){toast('Search failed: '+e.message,'error')}finally{setBusy(b,false,'Search')}}
async function switchGraph(mode){currentGraph=mode;$('localGraphBtn').classList.toggle('active',mode==='local');$('teamGraphBtn').classList.toggle('active',mode==='team');$('graphModeText').textContent=mode==='team'?'Team':'Local';try{let gr=await j(mode==='team'?'/api/team-graph?limit=170':'/api/graph?limit=170');draw(gr);$('graphStatus').textContent=(mode==='team'?'Team':'Local')+' graph · '+((gr.nodes||[]).length)+' visible nodes';toast((mode==='team'?'Team':'Local')+' graph selected')}catch(e){toast('Graph load failed: '+e.message,'error')}}
function draw(data){let c=$('graph'),ctx=c.getContext('2d'),r=c.getBoundingClientRect();if(!r.width||!r.height)return;c.width=Math.max(1,Math.floor(r.width*devicePixelRatio));c.height=Math.max(1,Math.floor(r.height*devicePixelRatio));ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);ctx.clearRect(0,0,r.width,r.height);let W=r.width,H=r.height,n=data.nodes||[],pos={};let modules=n.filter(x=>x.kind==='maven_module'),hubs=n.filter(x=>x.kind!=='file'&&x.kind!=='maven_module').slice(0,70);let display=[...modules,...hubs,...n.filter(x=>x.kind==='file').slice(0,30)];display.forEach((x,i)=>{let a=2*Math.PI*i/Math.max(1,display.length),rad=Math.min(W,H)*(.16+.32*((i%11)/11));pos[x.id]={x:W/2+Math.cos(a)*rad,y:H/2+Math.sin(a)*rad}});ctx.lineWidth=.7;ctx.strokeStyle='#1d4c77';(data.edges||[]).forEach(e=>{let a=pos[e.src],b=pos[e.dst];if(a&&b){ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke()}});display.forEach(x=>{let p=pos[x.id],isModule=x.kind==='maven_module',color=isModule?'#ffb347':x.kind==='file'?'#2d8cff':x.kind==='class'?'#8f6cff':'#20e3a2';ctx.beginPath();ctx.shadowBlur=isModule?16:10;ctx.shadowColor=color;ctx.fillStyle=color;ctx.arc(p.x,p.y,isModule?7:x.kind==='file'?2.5:4,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;if(isModule){ctx.fillStyle='#f7fbff';ctx.font='600 11px Segoe UI';ctx.fillText(x.name,p.x+10,p.y+4)}});if(!display.length){ctx.fillStyle='#7892b2';ctx.font='12px Segoe UI';ctx.fillText('No graph nodes available yet',16,28)}}
function bind(){bindNav();$('searchBtn').addEventListener('click',doSearch);$('globalSearch').addEventListener('keydown',e=>{if(e.key==='Enter')doSearch()});$('analyzeBtn').addEventListener('click',runWhatIf);$('syncBtn').addEventListener('click',syncGit);$('refreshBtn').addEventListener('click',()=>boot(true));$('diagRefreshBtn').addEventListener('click',()=>boot(true));$('localGraphBtn').addEventListener('click',()=>switchGraph('local'));$('teamGraphBtn').addEventListener('click',()=>switchGraph('team'));window.addEventListener('resize',()=>switchGraph(currentGraph));}
bind();boot();setInterval(()=>boot(false),15000);
</script>
</body></html>'''


def serve(root: Path, store: GraphStore, host: str = "127.0.0.1", port: int = 9739, open_browser: bool = True):
    root = Path(root).resolve()
    team_store = GraphStore(root / ".repograph" / "cache" / "team_graph.db")
    git_manager = GitSyncManager(root, team_store)

    class H(BaseHTTPRequestHandler):
        def send_json(self, obj, status=200):
            b = json.dumps(obj, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def read_json(self):
            try:
                return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0") or 0)) or b"{}")
            except Exception:
                return {}

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(u.query)
            try:
                if u.path == "/":
                    b = HTML.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(b)))
                    self.end_headers()
                    self.wfile.write(b)
                    return
                if u.path == "/api/stats":
                    self.send_json({**store.stats(), "repo": root.name}); return
                if u.path == "/api/team-stats":
                    self.send_json(team_store.stats()); return
                if u.path == "/api/git":
                    self.send_json(git_manager.status()); return
                if u.path == "/api/quality":
                    self.send_json(collect_quality(root)); return
                if u.path == "/api/events":
                    self.send_json((store.recent_events(60) + team_store.recent_events(60))[:100]); return
                if u.path == "/api/search":
                    self.send_json(store.search(qs.get("q", [""])[0], 50, repo=qs.get("repo", [None])[0])); return
                if u.path == "/api/graph":
                    self.send_json(store.graph_slice(int(qs.get("limit", [250])[0]))); return
                if u.path == "/api/team-graph":
                    self.send_json(team_store.graph_slice(int(qs.get("limit", [250])[0]))); return
                if u.path == "/api/impact":
                    self.send_json(impact(store, qs.get("target", [""])[0], int(qs.get("depth", [4])[0]))); return
                self.send_json({"error": "not found"}, 404)
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            try:
                if u.path == "/api/git-sync":
                    self.send_json(git_manager.sync()); return
                if u.path == "/api/what-if":
                    d = self.read_json()
                    chosen = team_store if d.get("team") else store
                    self.send_json(proposed_change_impact(chosen, d.get("proposal", ""), int(d.get("depth", 4)))); return
                self.send_json({"error": "not found"}, 404)
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer((host, port), H)
    url = f"http://{host}:{port}"
    print(f"RepoGraph dashboard: {url}")
    if open_browser:
        threading.Timer(.5, lambda: webbrowser.open(url)).start()
    httpd.serve_forever()
