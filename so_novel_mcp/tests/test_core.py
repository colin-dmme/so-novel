import hashlib, json, zipfile, pytest
from pathlib import Path
import sonovel_core as c
import server

def test_providers_and_url():
    s=c.source_names()
    assert len(s)>=8
    assert any("biquge365" in x["url"] for x in s)
    assert c.validate_book_url("https://www.biquge365.net/book/374722/")["host"]=="www.biquge365.net"
    for bad in ("http://localhost:3000/","https://127.0.0.1/a",
                "file:///C:/Secrets","https://www.biquge365.net:8080/a",
                "https://other.example/books/1"):
        with pytest.raises(ValueError):
            c.validate_book_url(bad)

def test_rule_path_safety():
    for bad in ("../config.json","C:\\evil.json","evil / thing","malicious.json/thing"):
        with pytest.raises((ValueError,FileNotFoundError)):
            c.allowed_rule_filename(bad)

def test_make_config(tmp_path):
    path=tmp_path/"config.ini"
    c.make_config(path,dest=tmp_path/"downloads",rules="main.json",fmt="epub",
                  concurrency=2,min_interval_ms=800,max_interval_ms=1800)
    s=path.read_text("utf-8")
    assert "preserve-chapter-cache = 1" in s
    assert "active-rules = main.json" in s
    assert "enabled = 0" in s
    with pytest.raises(ValueError):c.make_config(path,dest=tmp_path,rules="main.json",fmt="rar")
    with pytest.raises(ValueError):c.make_config(path,dest=tmp_path,rules="main.json",fmt="txt",concurrency=100)

def test_generated_epub_integrity():
    """Portable test fixture: no copyrighted book downloads required."""
    path=c.WORK/"exports"/"unit_generated.epub"
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with zipfile.ZipFile(path,"w") as z:
            z.writestr("mimetype","application/epub+zip")
            z.writestr("OEBPS/1.html","<html><body>"+"中文测试章节"*100+"</body></html>")
            z.writestr("OEBPS/2.html","<html><body>"+"测试内容"*170+"</body></html>")
        v=c.verify_book(str(path))
        assert v["zip_crc_ok"]
        assert v["numbered_chapters"]==2
        assert v["chapter_indexes_missing"]==[]
        sample=c.chapter_excerpt(str(path),index=2,max_chars=170)
        assert sample["truncated"]
        assert len(sample["excerpt"]) <= 170
    finally:
        path.unlink(missing_ok=True)

def test_path_denied():
    with pytest.raises((ValueError,FileNotFoundError)):
        c.safe_file_in_downloads(r"C:\Windows\win.ini")

def test_web_secret_redaction():
    o=server._json_mask({"cookie":"secret","myToken":"abc","proxy":{"host":"1.2.3.4"},"port":7765})
    assert o["cookie"]=="***"
    assert o["myToken"]=="***"
    assert o["proxy"]=="***"
    assert o["port"]==7765

def test_progress_parser_ignores_attempt_numbers(tmp_path):
    log=tmp_path/'download.log'
    log.write_text('Downloading... 100% |###| 3/3 (elapsed 10s)\n==== Attempt 1/2 ====\n',encoding='utf-8')
    assert c.progress_from_log(log)['total']==3
    assert c.progress_from_log(log)['done']==3

def test_mcp_tool_count():
    ts=server.mcp._tool_manager._tools
    assert len(ts)>=20
    assert "sonovel_start_download" in ts
    assert "sonovel_web_stop" in ts
    assert "sonovel_verify_book" in ts
