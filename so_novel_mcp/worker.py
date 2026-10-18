"""Detached durable So Novel CLI worker. Preserves job logs and checks actual output files."""
from __future__ import annotations
import argparse, os, re, subprocess, time, traceback
from pathlib import Path
from sonovel_core import HOME, WORK, java_exe, json_read, json_write, progress_from_log, verify_book

def run(job_id):
    folder=WORK/"jobs"/job_id
    request=json_read(folder/"request.json")
    if not isinstance(request,dict):raise RuntimeError("Job request missing")
    output=WORK/"downloads"/job_id
    output.mkdir(parents=True,exist_ok=True)
    state={"job_id":job_id,"state":"running","worker_pid":os.getpid(),
           "started_at":time.time(),"file_format":request["format"],"book_url":request["url"],
           "source_rules":request["rules"]}
    json_write(folder/"status.json",state)
    args=[str(java_exe()), "-Dmode=cli", "-Dconfig.file="+str(folder/"config.ini"),
          "-jar",str(HOME/"app.jar"),"--url="+request["url"],"--ext="+request["format"]]
    log_file=folder/"download.log"
    try:
        max_attempts=2
        for attempt in range(1,max_attempts+1):
            state["attempt"]=attempt
            json_write(folder/"status.json",state)
            with open(log_file,"ab") as log:
                log.write(f"\n==== Attempt {attempt}/{max_attempts} ====\n".encode("utf-8"))
                proc=subprocess.Popen(args,cwd=HOME,stdout=log,stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL,
                                      creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                state["java_pid"]=proc.pid
                json_write(folder/"status.json",state)
                last=0.0
                while proc.poll() is None:
                    time.sleep(1.2)
                    now=time.time()
                    if now-last>4:
                        state["progress"]=progress_from_log(log_file)
                        json_write(folder/"status.json",state)
                        last=now
                code=proc.returncode
            output_files=[p for p in output.iterdir() if p.is_file() and p.suffix.lower()=="."+request["format"]]
            state["return_code"]=code
            state["output_files"]=[str(p) for p in output_files]
            state["progress"]=progress_from_log(log_file)
            if code==0 and output_files:break
            if attempt<max_attempts:
                state["last_error"]=f"Attempt {attempt}: CLI exited {code}; ebook outputs: {len(output_files)}"
                json_write(folder/"status.json",state)
                time.sleep(8)
        state["finished_at"]=time.time()
        if code!=0 or not output_files:
            state["state"]="failed"
            state["error"]=f"So Novel exited {code}; ebook files: {len(output_files)}, attempts: {max_attempts}. Read download.log"
        else:
            state["state"]="succeeded"
            if request["format"]=="epub":
                checks=[verify_book(str(p)) for p in output_files]
                state["epub_validations"]=checks
                if not all(x.get("zip_crc_ok") and x.get("numbered_chapters") for x in checks):
                    state["state"]="failed"
                    state["error"]="EPUB integrity check failed"
                elif state["progress"] and any(x["numbered_chapters"]!=state["progress"]["total"] for x in checks):
                    state["state"]="incomplete"
                    state["error"]="Actual chapter count differs from CLI progress"
    except BaseException:
        state["state"]="failed";state["finished_at"]=time.time()
        state["error"]=traceback.format_exc()[-2600:]
    finally:
        json_write(folder/"status.json",state)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("job_id",type=str)
    a=parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{16}",a.job_id):raise SystemExit("Bad job_id")
    run(a.job_id)
