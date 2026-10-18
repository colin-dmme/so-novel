"""So Novel Desktop Coworker MCP — local stdio bridge to official So Novel CLI & WebUI."""
from __future__ import annotations
import os, json, re, shutil, subprocess, sys, time, uuid, zipfile
from pathlib import Path
from datetime import datetime
from mcp.server.fastmcp import FastMCP

import sonovel_core as c
c.init()
mcp=FastMCP("So Novel MCP",instructions=(
    "Use sonovel_health first. sonovel_start_download is a durable detached CLI job; "
    "use sonovel_job_status to check success, then sonovel_verify_book to verify EPUB. "
    "WebUI is NOT started automatically; it may listen on all interfaces without authentication. "
    "Web endpoints work only when the user explicitly starts a trusted So Novel WebUI. "
    "Use source catalogs before downloading; never assume every listed source is online. "
    "Only access content you are authorized to download. "
    "Never silently mix Chinese originals and machine-translated English."))

def _jobs():
    result=[]
    for p in sorted((c.WORK/"jobs").glob("*"),key=lambda p:p.stat().st_mtime,reverse=True):
        if p.is_dir():
            s=c.json_read(p/"status.json",{})
            if s:result.append(s)
    return result

def _state(job_id):
    folder=c.job_folder(job_id)
    s=c.json_read(folder/"status.json",{})
    if not s: raise RuntimeError("Job has not started yet; retry soon")
    # Worker survives this MCP process. Do not claim success based on progress only.
    if s.get("state")=="running":
        import psutil
        pid=s.get("worker_pid")
        if pid and not psutil.pid_exists(pid):
            s={**s,"state":"interrupted","error":"Worker process is no longer running."}
    prog=c.progress_from_log(folder/"download.log")
    if prog:s["progress"]=prog
    s["log_path"]=str(folder/"download.log")
    return s

def _json_mask(value):
    if isinstance(value,dict):
        return {k:("***" if any(key in k.lower() for key in ("password","cookie","secret","token","api_key","proxy")) else _json_mask(v))
                for k,v in value.items()}
    if isinstance(value,list): return [_json_mask(x) for x in value]
    return value

@mcp.tool()
def sonovel_guide() -> dict:
    """Show safe end-to-end MCP workflow and operational limits."""
    return {"quickstart":["sonovel_health","sonovel_list_sources",
        "sonovel_start_download(url,format='epub',rules_file='main.json')",
        "sonovel_job_status(job_id)","sonovel_local_books","sonovel_verify_book"],
        "search":["Start So Novel WebUI manually or explicitly acknowledge the unprotected server using sonovel_web_start.",
                  "sonovel_search/sonovel_suggest/sonovel_web_sources then work with approved source URLs"],
        "operations":["Independent CLI jobs; multiple formats; durable progress; cancel; audit; preview; export; local file trash"],
        "cautions":["So Novel WebUI has no auth and may bind to network interfaces; leave disabled by default.",
                    "No DRM, login, paywall or CAPTCHA bypass.",
                    "Rule files define website support, not guaranteed download success.",
                    "Job success still needs file/chapter/content validation."]}

@mcp.tool()
def sonovel_health() -> dict:
    """Check installed So Novel release, Java, local workspace and optional WebUI."""
    try:
        c.check_install();jar="present";java=str(c.java_exe())
    except Exception as e:jar="missing: "+str(e);java=None
    web=False
    try:
        info=c.web_api("/sources",timeout=2)
        web=isinstance(info,list)
    except Exception:pass
    return {"home":str(c.HOME),"workspace":str(c.WORK),"app_jar":jar,
            "java":java,"rules_main":len(c.source_names("main.json")) if jar=="present" else 0,
            "web_ui_url":c.WEB,"web_api_available":web,
            "active_jobs":len([s for s in _jobs() if s.get("state")=="running"])}

@mcp.tool()
def sonovel_list_rule_files() -> dict:
    """Discover available website rule packs, including custom rule packs."""
    c.check_install()
    files=[]
    for p in sorted(c.RULE_DIR.glob("*.json")):
        try:
            rules=c.parse_rules(p.name)
            files.append({"filename":p.name,"count":len(rules)})
        except Exception as e:
            files.append({"filename":p.name,"error":str(e)})
    return {"rule_files":files}

@mcp.tool()
def sonovel_list_sources(rules_file: str="main.json", query: str="") -> dict:
    """List provider names, domains, search support and notes from a rule pack."""
    rows=c.source_names(rules_file)
    if query:rows=[r for r in rows if query.casefold() in (str(r["name"])+str(r["url"])).casefold()]
    return {"rule_file":rules_file,"total":len(rows),"sources":rows}

@mcp.tool()
def sonovel_source_rule(rules_file: str="main.json", source_name: str="") -> dict:
    """Inspect structured search, table-of-contents and chapter selectors for one provider."""
    if not source_name:raise ValueError("source_name is required")
    entries=[x for x in c.parse_rules(rules_file) if x.get("name")==source_name]
    if not entries:raise ValueError("Source name not found in rules file")
    r=entries[0]
    return {"name":r.get("name"),"url":r.get("url"),"search":r.get("search"),
            "book":r.get("book"),"toc":r.get("toc"),"chapter":r.get("chapter")}

@mcp.tool()
def sonovel_validate_url(url: str,rules_file:str="main.json") -> dict:
    """Verify a book URL belongs to a supported provider before starting a job."""
    return c.validate_book_url(url,rules_file)

@mcp.tool()
def sonovel_start_download(url: str, format: str="epub", rules_file: str="main.json",
                           language: str="", concurrency: int=2,
                           min_interval_ms: int=850,max_interval_ms: int=1550,
                           retries: int=3) -> dict:
    """Start full-book So Novel CLI download as a durable background job.

    Respects source access controls; no attempt to bypass protected chapters.
    Formats: epub/txt/html/pdf. Never modifies existing jobs or files.
    """
    import psutil
    for s in _jobs():
        if s.get("state")=="running" and psutil.pid_exists(s.get("worker_pid") or -1):
            if s.get("book_url")==url: raise RuntimeError("This URL already has an active download job: "+s["job_id"])
    provider=c.validate_book_url(url,rules_file)
    jid=uuid.uuid4().hex[:16]
    folder=c.WORK/"jobs"/jid
    folder.mkdir(parents=True,exist_ok=False)
    dest=c.WORK/"downloads"/jid
    dest.mkdir(parents=True,exist_ok=True)
    c.make_config(folder/"config.ini",dest=dest,rules=rules_file,fmt=format,
                  language=language,concurrency=concurrency,
                  min_interval_ms=min_interval_ms,max_interval_ms=max_interval_ms,
                  retries=retries)
    req={"url":url,"format":format,"rules":rules_file,"language":language,
         "source":provider["provider"],"concurrency":concurrency,
         "min_interval_ms":min_interval_ms,"max_interval_ms":max_interval_ms,
         "retries":retries,"created_at":time.time()}
    c.json_write(folder/"request.json",req)
    flags=(getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)
           |getattr(subprocess,"DETACHED_PROCESS",0)|getattr(subprocess,"CREATE_NO_WINDOW",0))
    with open(folder/"worker.log","ab") as log:
        proc=subprocess.Popen([sys.executable,str(c.BASE/"worker.py"),jid],
          cwd=c.BASE,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
          close_fds=True,creationflags=flags)
    return {"job_id":jid,"worker_pid":proc.pid,"state":"starting",
            "source":provider["provider"],"book_url":url,"download_format":format,
            "download_folder":str(dest),"status_tool":"sonovel_job_status"}

@mcp.tool()
def sonovel_job_status(job_id:str, log_tail_chars:int=0) -> dict:
    """Read actual CLI job state, progress, outputs and optional short diagnostic log."""
    s=_state(job_id)
    if log_tail_chars:
        log=c.job_folder(job_id)/"download.log"
        if log.is_file():
            with log.open("rb") as f:
                f.seek(max(0,f.seek(0,2)-min(35000,max(500,log_tail_chars))))
                s["log_tail"]=c.ANSI.sub("",f.read().decode("utf-8","replace"))[-min(4000,log_tail_chars):]
    return s

@mcp.tool()
def sonovel_jobs(limit:int=20) -> dict:
    """List recent persistent jobs without starting, resuming or retrying them."""
    rows=[]
    for s in _jobs()[:max(1,min(limit,60))]:
        jid=s.get("job_id")
        try: rows.append(_state(jid))
        except Exception:rows.append(s)
    return {"jobs":rows,"count":len(rows)}

@mcp.tool()
def sonovel_cancel_job(job_id: str) -> dict:
    """Cancel only this MCP's verified Java/worker process tree; preserve cached files."""
    import psutil
    state=_state(job_id)
    if state["state"] not in {"running","starting"}:
        return {"cancelled":False,"reason":"Job is not active","state":state["state"]}
    pid=state.get("worker_pid")
    if not pid:raise RuntimeError("Worker PID unavailable")
    try:
        proc=psutil.Process(pid)
        command=" ".join(proc.cmdline()).lower()
        if "worker.py" not in command or job_id not in command:
            raise RuntimeError("PID does not match the expected So Novel worker; refusing cancellation")
    except psutil.NoSuchProcess:
        raise RuntimeError("Worker already exited")
    children=proc.children(recursive=True)
    for p in children:
        try:p.terminate()
        except psutil.NoSuchProcess:pass
    _,alive=psutil.wait_procs(children,timeout=5)
    for p in alive:
        try:p.kill()
        except psutil.NoSuchProcess:pass
    try:proc.terminate()
    except psutil.NoSuchProcess:pass
    ended={**state,"state":"cancelled","finished_at":time.time(),
           "reason":"Explicit MCP cancellation; cached chapters remain on disk"}
    ended.pop("log_tail",None)
    c.json_write(c.job_folder(job_id)/"status.json",ended)
    return {"cancelled":True,"job_id":job_id,"cached_folder":str(c.WORK/"downloads"/job_id)}

@mcp.tool()
def sonovel_local_books() -> dict:
    """List generated books (including existing 419-chapter EPUB), paths and file sizes."""
    books=c.local_books()
    return {"total":len(books),"books":books}

@mcp.tool()
def sonovel_verify_book(path:str) -> dict:
    """Verify EPUB ZIP CRC and indexed chapters; report hash/format/length."""
    return c.verify_book(path)

@mcp.tool()
def sonovel_chapter_excerpt(path:str,chapter_index:int=1,max_chars:int=550) -> dict:
    """Show limited sample from an owned local EPUB for encoding validation."""
    return c.chapter_excerpt(path,chapter_index,max_chars)

@mcp.tool()
def sonovel_export_copy(path:str, filename:str="") -> dict:
    """Copy an existing generated ebook to isolated exports; never overwrite another file."""
    src=c.safe_file_in_downloads(path)
    if filename:
        if Path(filename).name!=filename or not re.fullmatch(r"[^<>:\"/\\|?*\x00-\x1f]{1,180}",filename):
            raise ValueError("Invalid output filename")
        if Path(filename).suffix.lower()!=src.suffix.lower(): raise ValueError("Keep original extension")
    else:filename=src.name
    dest=c.WORK/"exports"/filename
    if dest.exists():
        if dest.samefile(src):return {"path":str(dest),"copied":False,"reason":"already in exports"}
        dest=c.WORK/"exports"/(dest.stem+"-"+uuid.uuid4().hex[:8]+dest.suffix)
    shutil.copy2(src,dest)
    return {"path":str(dest),"bytes":dest.stat().st_size,"copied":True}

@mcp.tool()
def sonovel_move_to_trash(path:str, confirm_filename:str) -> dict:
    """Safely move only MCP-generated books into a reversible trash folder. No permanent delete."""
    p=c.safe_file_in_downloads(path,workspace_only=True)
    if p.name!=confirm_filename: raise ValueError("Type the exact filename to confirm move to trash")
    dest=c.WORK/"trash"/(uuid.uuid4().hex[:8]+"_"+p.name)
    shutil.move(str(p),str(dest))
    return {"moved":True,"trash_path":str(dest),"original":str(p)}

@mcp.tool()
def sonovel_web_status() -> dict:
    """Check So Novel WebUI availability (not automatically started)."""
    try:
        data=c.web_api("/sources",timeout=2)
        return {"available":True,"url":c.WEB,"sources":len(data) if isinstance(data,list) else None,
                "security_warning":"So Novel WebUI lacks authentication; never expose it to untrusted networks."}
    except Exception as e:
        return {"available":False,"url":c.WEB,"message":str(e)}

@mcp.tool()
def sonovel_search(keyword:str,limit:int=25) -> dict:
    """Aggregate search across active WebUI providers; requires So Novel WebUI already running."""
    if not keyword.strip() or len(keyword)>150:raise ValueError("Keyword must be 1..150 characters")
    data=c.web_api("/search/aggregated",{"kw":keyword,"searchLimit":max(1,min(60,limit))},timeout=120)
    return {"query":keyword,"results":data,"count":len(data) if isinstance(data,list) else None}

@mcp.tool()
def sonovel_suggest(keyword:str) -> dict:
    """Request remote book-title suggestions using So Novel's own WebUI endpoint."""
    if not keyword.strip() or len(keyword)>120:raise ValueError("Invalid keyword")
    return {"keyword":keyword,"suggestions":c.web_api("/suggestion",{"kw":keyword},timeout=20)}

@mcp.tool()
def sonovel_web_sources(check_availability:bool=False) -> dict:
    """Read active WebUI sources; optional availability check can take longer."""
    data=c.web_api("/sources/check" if check_availability else "/sources",
                   timeout=100 if check_availability else 15)
    return {"sources":data,"count":len(data) if isinstance(data,list) else None}

@mcp.tool()
def sonovel_web_config() -> dict:
    """Get non-secret WebUI configuration; cookie/password/token fields always redacted."""
    return {"config":_json_mask(c.web_api("/config",timeout=15))}

@mcp.tool()
def sonovel_web_local_books() -> dict:
    """List book files indexed by the running So Novel WebUI."""
    data=c.web_api("/local-books",timeout=15)
    return {"books":data}

@mcp.tool()
def sonovel_web_start(confirm_unauthenticated_network_service:bool=False,
                      rules_file:str="main.json") -> dict:
    """Explicitly start the original HTTP WebUI. Caution: Java Jetty may listen on all interfaces; no auth."""
    import psutil
    if not confirm_unauthenticated_network_service:
        raise ValueError("Refusing to start authless So Novel WebUI by default. "
                         "It may bind all network interfaces. Set confirm_unauthenticated_network_service=true "
                         "only on a trusted computer with appropriate firewall rules.")
    existing=sonovel_web_status()
    if existing["available"]:return {"started":False,**existing}
    c.check_install()
    path=c.WORK/"configs"/"web.ini"
    # No user credentials, proxy or cookies inherited.
    c.make_config(path,dest=c.WORK/"downloads"/"web",rules=rules_file,fmt="epub")
    import configparser
    cp=configparser.ConfigParser(interpolation=None)
    cp.read(path,encoding="utf-8")
    cp.set("web","enabled","1")
    cp.set("web","port",c.WEB.rsplit(":",1)[-1])
    with open(path,"w",encoding="utf-8") as f:cp.write(f)
    logpath=c.WORK/"configs"/"web-console.log"
    flags=(getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)
           |getattr(subprocess,"DETACHED_PROCESS",0)|getattr(subprocess,"CREATE_NO_WINDOW",0))
    with open(logpath,"ab") as log:
        proc=subprocess.Popen([str(c.java_exe()),"-Dmode=web",
                "-Dconfig.file="+str(path),"-jar",str(c.HOME/"app.jar")],
                cwd=c.HOME,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                creationflags=flags,close_fds=True)
    c.json_write(c.WORK/"configs"/"web-process.json",{"pid":proc.pid,
         "created_at":time.time(),"rules":rules_file,"config":str(path)})
    for _ in range(22):
        time.sleep(0.5)
        if sonovel_web_status()["available"]:
            return {"started":True,"pid":proc.pid,"url":c.WEB,
                    "security_warning":"WebUI may be reachable beyond localhost; check Windows firewall."}
    return {"started":False,"pid":proc.pid,"message":"WebUI starting; inspect sonovel_web_status and web-console.log"}

@mcp.tool()
def sonovel_web_stop() -> dict:
    """Stop only a WebUI Java process launched by this MCP; never stop someone else's server."""
    import psutil
    info=c.json_read(c.WORK/"configs"/"web-process.json",{})
    pid=info.get("pid")
    if not pid:return {"stopped":False,"reason":"No WebUI tracked by this MCP"}
    try:
        proc=psutil.Process(pid)
        command=" ".join(proc.cmdline()).lower()
        if "app.jar" not in command or "web.ini" not in command:
            raise RuntimeError("Running process does not match MCP-owned WebUI; refusing to stop")
        proc.terminate()
        try:proc.wait(timeout=8)
        except psutil.TimeoutExpired:proc.kill()
    except psutil.NoSuchProcess:pass
    (c.WORK/"configs"/"web-process.json").unlink(missing_ok=True)
    return {"stopped":True,"pid":pid}

@mcp.resource("sonovel://guide")
def guide_resource() -> str:
    return json.dumps(sonovel_guide(),ensure_ascii=False,indent=2)

if __name__=="__main__":
    mcp.run(transport="stdio")
