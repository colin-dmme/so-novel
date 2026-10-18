"""Idempotently register local So Novel stdio MCP with Desktop Coworker.

Never publishes the upstream config, tokens or user identifiers to Git.
"""
from __future__ import annotations
import json, os, shutil, sys
from pathlib import Path

BASE=Path(__file__).resolve().parent
user_root=Path(os.environ.get("LOCALAPPDATA",str(Path.home()/"AppData/Local")))/"DesktopCoworkerForChatGPT/users"
files=list(user_root.glob("*/mcp-upstream.json"))
if len(files)!=1:
    raise SystemExit(f"Expected one Desktop Coworker profile; found {len(files)}. Please set up manually.")
path=files[0]
payload=json.loads(path.read_text(encoding="utf-8-sig"))
servers=payload.get("servers")
if not isinstance(servers,list):raise SystemExit("Unexpected config shape; no changes made.")
python=BASE/".venv/Scripts/python.exe"
server=BASE/"server.py"
if not python.is_file() or not server.is_file():
    raise SystemExit("Install Python dependencies first; .venv/Scripts/python.exe missing")
home=Path(os.environ.get("SONOVEL_HOME",str(BASE.parent / "runtime" / "SoNovel")))
if not (home/"app.jar").is_file():
    raise SystemExit(f"So Novel app.jar missing at {home}. Set SONOVEL_HOME before registering.")
entry={
  "id":"so-novel",
  "name":"So Novel MCP",
  "enabled":True,
  "transport":"stdio",
  "command":str(python),
  "args":[str(server)],
  "cwd":str(BASE),
  "env":{"SONOVEL_HOME":str(home),"SONOVEL_MCP_WORKSPACE":str(BASE/"workspace"),
         "SONOVEL_WEB_PORT":"17765"},
  "expose":"all",
}
existing=next((x for x in servers if x.get("id")=="so-novel"),None)
if existing:
    # Keep identity stable and avoid duplicates.
    servers[servers.index(existing)]=entry
else:servers.append(entry)
backup=path.with_name("mcp-upstream.before-so-novel.json")
if not backup.exists():shutil.copy2(path,backup)
temp=path.with_suffix(".so-novel.tmp")
temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
os.replace(temp,path)
print(f"Registered so-novel (stdio, {len(servers)} total) in {path}.")
print(f"Backup: {backup}")
print("Restart Desktop Coworker and reconnect COLINPC to load the new upstream.")
