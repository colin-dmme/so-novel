"""Local So Novel integration utilities. No web interface is started by default."""
from __future__ import annotations
import configparser, hashlib, json, os, re, shutil, socket, subprocess, tempfile, time, uuid, zipfile
from pathlib import Path
from urllib.parse import urlparse, urlencode
from urllib.request import urlopen

BASE = Path(__file__).resolve().parent
HOME = Path(os.getenv("SONOVEL_HOME", str(BASE.parent / "runtime" / "SoNovel"))).resolve()
WORK = Path(os.getenv("SONOVEL_MCP_WORKSPACE", str(BASE / "workspace"))).resolve()
RULE_DIR = HOME / "rules"
WEB = "http://127.0.0.1:" + str(int(os.getenv("SONOVEL_WEB_PORT", "17765")))
FORMATS = {"epub", "txt", "html", "pdf"}
LANGS = {"", "zh-CN", "zh-TW", "zh-Hant"}
RULEFILES = {"main.json", "no-search.json", "proxy-required.json", "rate-limit.json",
             "cloudflare.json", "non-search.json"}
ANSI = re.compile(r"\x1b\[[0-9;]*m")
PROGRESS = re.compile(r"Downloading\.{3}[^\r\n]*?(\d+)\s*/\s*(\d+)",re.I)

def init():
    for sub in ("jobs","downloads","exports","trash","configs"):
        (WORK/sub).mkdir(parents=True, exist_ok=True)

def java_exe():
    embedded=HOME/"runtime/bin/java.exe"
    if embedded.is_file(): return embedded
    java=shutil.which("java")
    if java: return Path(java)
    raise RuntimeError("Java executable not found. Install official So Novel Windows release.")

def check_install():
    if not (HOME/"app.jar").is_file(): raise FileNotFoundError(f"So Novel app.jar not found at {HOME}")
    if not (HOME/"config.ini").is_file(): raise FileNotFoundError(f"So Novel config.ini missing in {HOME}")
    if not RULE_DIR.is_dir(): raise FileNotFoundError(f"So Novel rules directory missing: {RULE_DIR}")

def allowed_rule_filename(name):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+\.json",name or ""):
        raise ValueError("Invalid rules file name")
    if not (RULE_DIR/name).is_file(): raise FileNotFoundError("Rule JSON not found: "+name)
    return name

def parse_rules(name="main.json"):
    allowed_rule_filename(name)
    rows=json.loads((RULE_DIR/name).read_text(encoding="utf-8-sig"))
    if not isinstance(rows,list): raise ValueError("Expected a JSON list of source rules")
    return rows

def source_names(name="main.json"):
    return [{"name":r.get("name"),"url":r.get("url"),
             "search_supported":bool(r.get("search")),
             "id":i+1,"comments":str(r.get("comment") or "")[:300]}
            for i,r in enumerate(parse_rules(name))]

def validate_book_url(url, rules_name="main.json"):
    u=urlparse(url)
    if u.scheme not in ("http","https") or not u.hostname or u.username or u.password or u.fragment:
        raise ValueError("Provide a normal http(s) URL of a listed source.")
    if u.port and u.port not in (80,443): raise ValueError("Non-standard ports are forbidden")
    if re.search(r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)",u.hostname,re.I):
        raise ValueError("Local/private network addresses not allowed")
    for r in parse_rules(rules_name):
        base=urlparse(str(r.get("url") or ""))
        if base.hostname and u.hostname.lower()==base.hostname.lower() and u.path.startswith(base.path or "/"):
            return {"provider":r.get("name"),"host":u.hostname,"url":url}
    raise ValueError("Book URL must belong to an enabled source in "+rules_name)

def make_config(filename, *, dest, rules, fmt, language="", concurrency=2,
                min_interval_ms=850, max_interval_ms=1550, retries=3):
    check_install()
    if fmt not in FORMATS: raise ValueError("Unsupported format")
    if language not in LANGS: raise ValueError("Unsupported output language")
    allowed_rule_filename(rules)
    if not (1<=concurrency<=8): raise ValueError("concurrency must be 1..8")
    if not (500<=min_interval_ms<=60000 and min_interval_ms<=max_interval_ms<=120000):
        raise ValueError("Inter-request interval must be 500..120000 ms")
    if not (0<=retries<=5): raise ValueError("retries must be 0..5")
    cfg=configparser.ConfigParser(interpolation=None)
    cfg.read(HOME/"config.ini",encoding="utf-8-sig")
    for section in ("global","download","source","crawl","web","cookie","proxy"):
        if not cfg.has_section(section): cfg.add_section(section)
    cfg.set("global","auto-update","0")
    cfg.set("download","download-path",str(dest))
    cfg.set("download","extname",fmt)
    cfg.set("download","preserve-chapter-cache","1")
    cfg.set("download","enable-progressbar","1")
    cfg.set("source","active-rules",rules)
    cfg.set("source","language",language)
    cfg.set("crawl","concurrency",str(concurrency))
    cfg.set("crawl","min-interval",str(min_interval_ms))
    cfg.set("crawl","max-interval",str(max_interval_ms))
    cfg.set("crawl","enable-retry","1")
    cfg.set("crawl","max-retries",str(retries))
    cfg.set("crawl","retry-min-interval","3000")
    cfg.set("crawl","retry-max-interval","8000")
    cfg.set("web","enabled","0")
    cfg.set("proxy","enabled","0")
    cfg.set("cookie","qidian","")
    with open(filename,"w",encoding="utf-8") as f: cfg.write(f)
    return filename

def json_read(path,default=None):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError):return default

def json_write(path,data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,delete=False) as tmp:
        json.dump(data,tmp,ensure_ascii=False,indent=2)
        tmp.write("\n")
        t=tmp.name
    os.replace(t,path)

def job_folder(job_id):
    if not re.fullmatch(r"[0-9a-f]{16}",job_id): raise ValueError("Invalid job_id")
    path=WORK/"jobs"/job_id
    if not path.is_dir(): raise FileNotFoundError("Unknown job ID: "+job_id)
    return path

def progress_from_log(path):
    if not path.is_file(): return None
    with path.open("rb") as f:
        f.seek(max(0,f.seek(0,2)-75000))
        s=f.read().decode("utf-8","replace")
    matches=PROGRESS.findall(ANSI.sub("",s))
    if not matches:return None
    done,total=map(int,matches[-1])
    return {"done":done,"total":total,"percentage":round(100*done/total,1) if total else 0}

def safe_file_in_downloads(file_path, *, workspace_only=False):
    path=Path(file_path).resolve(strict=True)
    roots=[WORK/"downloads",WORK/"exports"]
    if not workspace_only:
        roots += [HOME/"downloads-419",HOME/"downloads",HOME/"downloads-sample",HOME/"downloads-spread"]
    if path.is_file() and any(path.is_relative_to(r.resolve()) for r in roots if r.exists()):
        return path
    raise ValueError("File not in an approved So Novel downloads folder")

def local_books():
    out=[]
    dirs=[WORK/"exports",HOME/"downloads-419",HOME/"downloads",HOME/"downloads-sample",
          HOME/"downloads-spread"]
    dirs += sorted(p for p in (WORK/"downloads").iterdir() if p.is_dir()) if (WORK/"downloads").exists() else []
    for d in dirs:
        if not d.is_dir():continue
        for p in d.glob("*"):
            if p.is_file() and p.suffix.lower() in {".epub",".txt",".pdf",".zip",".html"}:
                out.append({"path":str(p),"name":p.name,"size_bytes":p.stat().st_size,
                            "modified":p.stat().st_mtime,"folder":str(d)})
    return sorted(out,key=lambda x:x["modified"],reverse=True)

def verify_book(path):
    p=safe_file_in_downloads(path)
    report={"path":str(p),"size_bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
            "format":p.suffix.lower().lstrip(".")}
    if p.suffix.lower()==".epub":
        with zipfile.ZipFile(p) as z:
            bad=z.testzip()
            names=z.namelist()
            entries=sorted({int(x.group(1)) for n in names if (x:=re.search(r"(?i)(?:^|/)(\d+)\.x?html$",n))})
            report.update({"zip_crc_ok":bad is None,"corrupted_entry":bad,
                 "entries":len(names),"numbered_chapters":len(entries),
                 "chapter_indexes_min":entries[0] if entries else None,
                 "chapter_indexes_max":entries[-1] if entries else None,
                 "chapter_indexes_missing":sorted(set(range(min(entries),max(entries)+1))-set(entries))[:100] if entries else [],
                 "mimetype":z.read("mimetype").decode("utf-8","replace") if "mimetype" in names else None})
    return report

def web_api(endpoint,query=None,timeout=20):
    if endpoint not in {"/sources","/sources/check","/config","/local-books",
                        "/suggestion","/search/aggregated"}: raise ValueError("Endpoint not permitted")
    query = query or {}
    full=WEB+endpoint+("?" + urlencode(query) if query else "")
    try:
        with urlopen(full,timeout=timeout) as response:
            if response.status!=200: raise RuntimeError(f"HTTP {response.status}")
            data=json.loads(response.read(2_000_000).decode("utf-8"))
    except (ConnectionError,OSError) as e:
        raise RuntimeError(f"So Novel WebUI unavailable at {WEB}. Start it manually in a trusted local environment. {e}")
    if not isinstance(data,dict) or "code" not in data: raise RuntimeError("Unexpected So Novel WebUI response")
    if data.get("code")!=200:raise RuntimeError(f"So Novel WebUI error: {data.get('message')}")
    return data.get("data")

def chapter_excerpt(path,index=1,max_chars=550):
    p=safe_file_in_downloads(path)
    if p.suffix.lower()!=".epub":raise ValueError("EPUB only")
    if not 1<=index<=100000:raise ValueError("Invalid chapter")
    with zipfile.ZipFile(p) as z:
        names=z.namelist()
        chapter=next((n for n in names if (m:=re.search(r"(?:^|/)(\d+)\.x?html$",n,re.I)) and int(m.group(1))==index),None)
        if chapter is None:raise FileNotFoundError(f"Chapter {index} not found")
        s=z.read(chapter).decode("utf-8","replace")
    import html
    s=re.sub(r"(?is)<style.*?</style>|<script.*?</script>","",s)
    s=re.sub(r"(?s)<[^>]+>"," ",s)
    s=re.sub(r"\s+"," ",html.unescape(s)).strip()
    limit=max(50,min(900,max_chars))
    return {"chapter":index,"total_chars":len(s),"excerpt":s[:limit],"truncated":len(s)>limit}
