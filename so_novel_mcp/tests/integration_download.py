"""End-to-end MCP integration with isolated three-chapter So Novel test rule."""
from __future__ import annotations
import asyncio, json, time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]

def normalize(result):
    if result.isError: raise RuntimeError(str(result.content))
    value=result.structuredContent or (result.content[0].text if result.content else {})
    return json.loads(value) if isinstance(value,str) else value

async def main():
    params=StdioServerParameters(command=str(ROOT/".venv/Scripts/python.exe"),
                                args=[str(ROOT/"server.py")],cwd=str(ROOT))
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as s:
            await s.initialize()
            r=normalize(await s.call_tool("sonovel_start_download",{
                "url":"https://www.biquge365.net/book/374722/",
                "format":"epub","rules_file":"sample-only.json",
                "concurrency":1,"min_interval_ms":800,"max_interval_ms":1600
            }))
            jobid=r["job_id"]
            print("STARTED_JOB",jobid,flush=True)
            status=None
            for i in range(65):
                await asyncio.sleep(2)
                status=normalize(await s.call_tool("sonovel_job_status",{"job_id":jobid,"log_tail_chars":150}))
                if i%4==0: print("STATUS",status["state"],status.get("progress"),flush=True)
                if status["state"] in {"succeeded","failed","incomplete","cancelled","interrupted"}:break
            print("FINAL_STATUS",status,flush=True)
            assert status["state"]=="succeeded",f"job failed: {status}"
            assert status["epub_validations"][0]["numbered_chapters"]==3
            path=status["output_files"][0]
            checked=normalize(await s.call_tool("sonovel_verify_book",{"path":path}))
            assert checked["zip_crc_ok"] and checked["numbered_chapters"]==3
            preview=normalize(await s.call_tool("sonovel_chapter_excerpt",{"path":path,"chapter_index":2,"max_chars":90}))
            assert preview["total_chars"]>100 and len(preview["excerpt"])<=90
            copied=normalize(await s.call_tool("sonovel_export_copy",{"path":path}))
            assert Path(copied["path"]).exists()
            print("INTEGRATION_PASS",copied["path"],flush=True)
if __name__=="__main__":asyncio.run(main())
