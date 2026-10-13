from __future__ import annotations

import base64
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import time
from pathlib import Path

_CACHE = {}
CACHE_SECONDS = 30

def _num(v, default=0.0):
    try:return float(v)
    except (TypeError,ValueError):return default


def _coverage_xml(path: Path):
    try:
        root=ET.parse(path).getroot()
        rate=root.attrib.get("line-rate") or root.attrib.get("lineRate")
        if rate is not None:return round(_num(rate)*100,1)
        counter=next((x for x in root.iter() if x.tag.endswith("counter") and x.attrib.get("type")=="LINE"),None)
        if counter is not None:
            c=_num(counter.attrib.get("covered")); m=_num(counter.attrib.get("missed")); return round(100*c/max(1,c+m),1)
    except Exception:pass
    return None


def _lcov(path: Path):
    try:
        found=hit=0
        for line in path.read_text(encoding="utf-8",errors="ignore").splitlines():
            if line.startswith("LF:"):found+=int(line[3:] or 0)
            elif line.startswith("LH:"):hit+=int(line[3:] or 0)
        if found:return round(hit*100/found,1)
    except Exception:pass
    return None


def _sonar_props(root: Path):
    props={}
    p=root/"sonar-project.properties"
    if p.exists():
        for line in p.read_text(encoding="utf-8",errors="ignore").splitlines():
            line=line.strip()
            if line and not line.startswith("#") and "=" in line:
                k,v=line.split("=",1); props[k.strip()]=v.strip()
    return props


def _sonar_remote(root: Path):
    props=_sonar_props(root)
    url=os.getenv("SONAR_HOST_URL") or props.get("sonar.host.url")
    key=os.getenv("SONAR_PROJECT_KEY") or props.get("sonar.projectKey")
    token=os.getenv("SONAR_TOKEN")
    if not (url and key):return None
    metrics="coverage,bugs,vulnerabilities,code_smells,duplicated_lines_density,reliability_rating,security_rating,sqale_rating,security_hotspots"
    endpoint=url.rstrip("/")+"/api/measures/component?"+urllib.parse.urlencode({"component":key,"metricKeys":metrics})
    req=urllib.request.Request(endpoint)
    if token:req.add_header("Authorization","Basic "+base64.b64encode((token+":").encode()).decode())
    try:
        with urllib.request.urlopen(req,timeout=3) as r:data=json.load(r)
        m={x["metric"]:x.get("value") for x in data.get("component",{}).get("measures",[])}
        return m
    except Exception:return None


def collect_quality(root: Path, force: bool = False) -> dict:
    root=Path(root).resolve()
    key=str(root)
    now=time.monotonic()
    cached=_CACHE.get(key)
    if cached and not force and now-cached[0] < CACHE_SECONDS:
        return dict(cached[1])
    sources=[]; coverage=None
    # explicit local quality override/CI artifact
    for q in (root/".repograph/quality.json",root/"quality.json"):
        if q.exists():
            try:
                d=json.loads(q.read_text(encoding="utf-8")); d.setdefault("sources",[]); d["sources"].append(str(q.relative_to(root))); out=_normalize(d); _CACHE[key]=(now,out); return dict(out)
            except Exception:pass
    for pattern in ("coverage.xml","**/coverage.xml","jacoco.xml","**/jacoco.xml"):
        for f in root.glob(pattern):
            if ".repograph" in f.parts:continue
            c=_coverage_xml(f)
            if c is not None: coverage=max(coverage or 0,c); sources.append(str(f.relative_to(root)))
    for pattern in ("lcov.info","**/lcov.info"):
        for f in root.glob(pattern):
            if ".repograph" in f.parts:continue
            c=_lcov(f)
            if c is not None: coverage=max(coverage or 0,c); sources.append(str(f.relative_to(root)))
    sonar=_sonar_remote(root)
    out={"coverage":coverage,"test_pass_rate":None,"bugs":0,"vulnerabilities":0,"code_smells":0,"duplications":None,
         "maintainability":"N/A","reliability":"N/A","security":"N/A","security_hotspots":0,"quality_gate":"Unknown","sources":sources,"sonarqube_connected":False}
    if sonar:
        out.update({"coverage":_num(sonar.get("coverage"),coverage or 0),"bugs":int(_num(sonar.get("bugs"))),"vulnerabilities":int(_num(sonar.get("vulnerabilities"))),
                    "code_smells":int(_num(sonar.get("code_smells"))),"duplications":_num(sonar.get("duplicated_lines_density")),"security_hotspots":int(_num(sonar.get("security_hotspots"))),
                    "maintainability":_rating(sonar.get("sqale_rating")),"reliability":_rating(sonar.get("reliability_rating")),"security":_rating(sonar.get("security_rating")),
                    "quality_gate":"Passed" if int(_num(sonar.get("bugs")))==0 and int(_num(sonar.get("vulnerabilities")))==0 else "Review","sonarqube_connected":True})
        out["sources"].append("SonarQube API")
    out=_normalize(out)
    _CACHE[key]=(now,out)
    return dict(out)


def _rating(v):
    n=int(_num(v,0)); return {1:"A",2:"B",3:"C",4:"D",5:"E"}.get(n,"N/A")


def _normalize(d):
    d=dict(d)
    d.setdefault("coverage",None); d.setdefault("test_pass_rate",None); d.setdefault("bugs",0); d.setdefault("vulnerabilities",0); d.setdefault("code_smells",0)
    d.setdefault("duplications",None); d.setdefault("maintainability","N/A"); d.setdefault("reliability","N/A"); d.setdefault("security","N/A"); d.setdefault("security_hotspots",0)
    d.setdefault("quality_gate","Unknown"); d.setdefault("sources",[]); d.setdefault("sonarqube_connected",False)
    cov=d.get("coverage"); d["coverage_label"]="N/A" if cov is None else f"{float(cov):.1f}%"
    return d
