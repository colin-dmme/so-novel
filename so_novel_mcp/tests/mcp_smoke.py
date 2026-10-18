"""Smoke test using actual MCP stdio transport."""
import asyncio, json, sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
BASE=Path(__file__).resolve().parents[1]

async def main():
    async with stdio_client(StdioServerParameters(command=str(BASE/".venv/Scripts/python.exe"),
        args=[str(BASE/"server.py")],cwd=str(BASE))) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            info=await session.initialize()
            alltools=await session.list_tools()
            print("MCP_STARTED",info.serverInfo.name,"TOOLS",len(alltools.tools))
            for name,arguments in [
                ("sonovel_health",{}),
                ("sonovel_list_sources",{"query":"biquge365"}),
                ("sonovel_local_books",{}),
            ]:
                result=await session.call_tool(name,arguments)
                print("CALL",name,"ERROR",result.isError)
                assert not result.isError
                txt=result.structuredContent or (result.content[0].text if result.content else "")
                print(str(txt)[:650])
            assert len(alltools.tools)>=20
            print("MCP_SMOKE_PASS")
if __name__=="__main__":
    asyncio.run(main())
