from __future__ import annotations

import json
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .impact import impact
from .store import GraphStore
from .util import git_info

HTML=r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RepoGraph Dashboard</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui;background:#0b1020;color:#e8ecf3}*{box-sizing:border-box}
body{margin:0}.top{padding:18px 24px;border-bottom:1px solid #26304d;background:#0f1630;position:sticky;top:0;z-index:3}
.top h1{margin:0;font-size:20px}.muted{color:#9aa7c2}.wrap{padding:20px;display:grid;gap:16px}.cards{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:12px}.card,.panel{background:#111a35;border:1px solid #26304d;border-radius:12px;padding:16px}.big{font-size:26px;font-weight:700;margin-top:5px}.grid{display:grid;grid-template-columns:1.25fr .75fr;gap:16px}input,button{background:#0b1020;color:#e8ecf3;border:1px solid #344064;border-radius:8px;padding:9px 11px}button{cursor:pointer;background:#24345f}.row{display:flex;gap:8px}.row input{flex:1}#graph{width:100%;height:520px;background:#080d1b;border-radius:10px}.list{max-height:400px;overflow:auto}.item{padding:8px 0;border-bottom:1px solid #24304b}.risk{font-weight:800}.LOW{color:#67e8a6}.MEDIUM{color:#ffd166}.HIGH{color:#ff8c42}.CRITICAL{color:#ff5d73}code{color:#b8c4ff}@media(max-width:900px){.cards{grid-template-columns:1fr 1fr}.grid{grid-template-columns:1fr}}
</style></head><body>
<div class="top"><h1>RepoGraph <span class="muted" id="repo"></span></h1><div class="muted" id="git"></div></div>
<div class="wrap"><div class="cards"><div class="card">Files<div class="big" id="files">-</div></div><div class="card">Nodes<div class="big" id="nodes">-</div></div><div class="card">Edges<div class="big" id="edges">-</div></div><div class="card">Working changes<div class="big" id="changes">-</div></div></div>
<div class="grid"><div class="panel"><h3>Global graph</h3><canvas id="graph"></canvas></div><div class="panel"><h3>Impact analysis</h3><div class="row"><input id="target" placeholder="Symbol or path, e.g. processPayment"><button onclick="runImpact()">Analyze</button></div><div id="impact" class="list" style="margin-top:12px"></div><h3>Search</h3><div class="row"><input id="query" placeholder="Search symbol/path"><button onclick="search()">Search</button></div><div id="results" class="list"></div></div></div>
<div class="panel"><h3>Recent graph updates</h3><div id="events" class="list"></div></div></div>
<script>
async function j(u){return (await fetch(u)).json()}
async function boot(){let s=await j('/api/stats');files.textContent=s.files;nodes.textContent=s.nodes;edges.textContent=s.edges;repo.textContent='— '+s.repo;let g=await j('/api/git');changes.textContent=g.changed.length;git.textContent=(g.branch||'no-git')+' '+(g.commit||'').slice(0,10);let ev=await j('/api/events');events.innerHTML=ev.map(x=>`<div class=item><code>${x.event_type}</code> ${x.path} <span class=muted>${x.ts}</span></div>`).join('');draw(await j('/api/graph?limit=220'))}
function draw(data){let c=document.querySelector('#graph'),ctx=c.getContext('2d');let r=c.getBoundingClientRect();c.width=r.width*devicePixelRatio;c.height=r.height*devicePixelRatio;ctx.scale(devicePixelRatio,devicePixelRatio);let W=r.width,H=r.height,n=data.nodes;let pos={};n.forEach((x,i)=>{let a=2*Math.PI*i/Math.max(1,n.length),rad=Math.min(W,H)*(.18+.30*((i%17)/17));pos[x.id]={x:W/2+Math.cos(a)*rad,y:H/2+Math.sin(a)*rad}});ctx.strokeStyle='#263b6d';data.edges.forEach(e=>{let a=pos[e.src],b=pos[e.dst];if(a&&b){ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke()}});n.forEach(x=>{let p=pos[x.id];ctx.beginPath();ctx.fillStyle=x.kind==='file'?'#5aa9ff':x.kind==='class'?'#a78bfa':'#5ee6a8';ctx.arc(p.x,p.y,x.kind==='file'?3:4,0,7);ctx.fill()})}
async function runImpact(){let q=target.value.trim();if(!q)return;let d=await j('/api/impact?target='+encodeURIComponent(q));impact.innerHTML=`<div class='risk ${d.risk}'>${d.risk} — score ${d.score}</div><div class=muted>${d.affected.length} affected nodes</div>`+d.affected.slice(0,100).map(x=>`<div class=item><b>${x.name}</b> <span class=muted>${x.kind}</span><br><code>${x.path}:${x.line}</code> via ${x.via}</div>`).join('')}
async function search(){let q=query.value.trim();if(!q)return;let d=await j('/api/search?q='+encodeURIComponent(q));results.innerHTML=d.map(x=>`<div class=item><b>${x.name}</b> <span class=muted>${x.kind}</span><br><code>${x.path}:${x.line}</code></div>`).join('')}
boot();setInterval(boot,10000)
</script></body></html>'''


def serve(root: Path, store: GraphStore, host: str="127.0.0.1", port: int=9739, open_browser: bool=True):
    root=Path(root).resolve()
    class H(BaseHTTPRequestHandler):
        def send_json(self,obj,status=200):
            b=json.dumps(obj,default=str).encode();self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
        def do_GET(self):
            u=urllib.parse.urlparse(self.path); qs=urllib.parse.parse_qs(u.query)
            if u.path=="/":
                b=HTML.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b);return
            if u.path=="/api/stats": self.send_json({**store.stats(),"repo":root.name});return
            if u.path=="/api/git": self.send_json(git_info(root));return
            if u.path=="/api/events": self.send_json(store.recent_events(100));return
            if u.path=="/api/search": self.send_json(store.search(qs.get("q",[""])[0],50));return
            if u.path=="/api/graph": self.send_json(store.graph_slice(int(qs.get("limit",[250])[0])));return
            if u.path=="/api/impact": self.send_json(impact(store,qs.get("target",[""])[0],int(qs.get("depth",[4])[0])));return
            self.send_json({"error":"not found"},404)
        def log_message(self,*args): pass
    httpd=ThreadingHTTPServer((host,port),H)
    url=f"http://{host}:{port}"
    print(f"RepoGraph dashboard: {url}")
    if open_browser: threading.Timer(.5,lambda:webbrowser.open(url)).start()
    httpd.serve_forever()
