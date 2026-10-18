# So Novel MCP — ChatGPT + Desktop Coworker

MCP độc lập cho [So Novel](https://github.com/freeok/so-novel) trên Windows. Điều khiển ứng dụng gốc qua **Java CLI và HTTP WebUI**, không cần Android/giả lập. Repo này không chứa binary So Novel hay văn bản truyện.

## Có gì?

- **23 MCP tools + 1 resource:** khám phá nguồn và rule, tìm kiếm tổng hợp, gợi ý tên, kiểm tra source, tải EPUB/TXT/HTML/PDF, trạng thái job, hủy, liệt kê sách, EPUB CRC/index/hash, mẫu chương, xuất bản sao và chuyển file sang thùng rác (có xác nhận).
- **Tác vụ bền vững:** download chạy bằng worker độc lập với phiên ChatGPT, có job ID, trạng thái, log, tiến độ, retry và cấu hình/tệp đầu ra riêng.
- **An toàn:** URL chỉ được chấp nhận khi thuộc domain đã đăng ký trong rule; giới hạn concurrency; không xóa sách gốc; tránh proxy/bypass/cookie. WebUI không mở tự động.
- **Giới hạn:** CLI tự tải toàn sách theo URL; không phải mọi nút TUI có API riêng. WebUI search chỉ dùng khi WebUI đang mở. Không hỗ trợ vượt paywall, DRM, captcha.

## 1. Chuẩn bị Windows

Cần: Windows 10/11, Python 3.12+, So Novel Windows release v1.11.0 hoặc tương thích, [Desktop Coworker](https://beta.desktopcoworker.online/) nếu dùng từ ChatGPT.

Tải bản chính thức từ [So Novel Releases](https://github.com/freeok/so-novel/releases), giải nén sonovel-windows.tar.gz vào C:\Coder\so-novel\runtime\SoNovel. Trong thư mục phải có app.jar, config.ini, rules/, runtime/bin/java.exe.

Clone MCP và cài dependencies:

~~~powershell
git clone https://github.com/colin-dmme/so-novel.git C:\Coder\so-novel
cd C:\Coder\so-novel\so_novel_mcp
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Biến môi trường chỉ cho phiên PowerShell này
$env:SONOVEL_HOME = 'C:\Coder\so-novel\runtime\SoNovel'
.\.venv\Scripts\python.exe tests\mcp_smoke.py
~~~

Trên COLINPC, ứng dụng So Novel nằm tại C:\Coder\so-novel\runtime\SoNovel. Thư mục runtime/ không được commit; máy mới cần giải nén Java release riêng.

Biến môi trường:
- SONOVEL_HOME: thư mục chương trình Java So Novel.
- SONOVEL_MCP_WORKSPACE: thư mục lưu tải, job, cache, log và export, mặc định workspace/ bên cạnh server.py.
- SONOVEL_WEB_PORT: cổng WebUI, mặc định 17765.

## 2. Kết nối MCP với Desktop Coworker

~~~powershell
cd C:\Coder\so-novel\so_novel_mcp
$env:SONOVEL_HOME = 'C:\Coder\so-novel\runtime\SoNovel'
.\.venv\Scripts\python.exe register_upstream.py
~~~

Script tìm đúng một profile Desktop Coworker, backup mcp-upstream.json thành mcp-upstream.before-so-novel.json, đăng ký upstream **so-novel** qua stdio, expose=all. Nếu có nhiều profile hoặc không tìm thấy app.jar, script không ghi thay đổi.

Cấu hình thủ công (chỉnh lại mọi đường dẫn):

~~~json
{
  "id": "so-novel",
  "name": "So Novel MCP",
  "enabled": true,
  "transport": "stdio",
  "command": "C:\\Coder\\so-novel\\so_novel_mcp\\.venv\\Scripts\\python.exe",
  "args": ["C:\\Coder\\so-novel\\so_novel_mcp\\server.py"],
  "cwd": "C:\\Coder\\so-novel\\so_novel_mcp",
  "env": {
    "SONOVEL_HOME": "C:\\Coder\\so-novel\\runtime\\SoNovel",
    "SONOVEL_MCP_WORKSPACE": "C:\\Coder\\so-novel\\so_novel_mcp\\workspace",
    "SONOVEL_WEB_PORT": "17765"
  },
  "expose": "all"
}
~~~

**Phải thoát và khởi động lại Desktop Coworker** (kể cả system tray) rồi kết nối lại COLINPC với ChatGPT để nhận upstream mới. ChatGPT có thể gọi qua mcp_servers, mcp_tools và mcp_call(server_id="so-novel").

MCP client khác có thể trực tiếp chạy .\.venv\Scripts\python.exe server.py (transport stdio).

## 3. Hướng dẫn dùng từ ChatGPT

Ví dụ prompt:

> Dùng upstream so-novel trên COLINPC. Kiểm tra nhà cung cấp Biquge365, xác minh URL truyện, tải EPUB tiếng Trung bằng CLI (2 luồng, giãn cách khoảng 1 giây), ghi job ID, kiểm tra số chương thực tế và gửi đường dẫn file khi hoàn tất.

Quy trình tools:
1. sonovel_health → sonovel_list_rule_files → sonovel_list_sources.
2. sonovel_validate_url(url, rules_file="main.json").
3. sonovel_start_download(url, format="epub", concurrency=2) → nhận job_id.
4. sonovel_job_status(job_id) / sonovel_jobs() để xem trạng thái và log.
5. sonovel_local_books() → sonovel_verify_book(path).
6. sonovel_chapter_excerpt(path, chapter_index=2) giới hạn ký tự → sonovel_export_copy(path).

Tải TXT, HTML hoặc PDF bằng cách đổi format trong sonovel_start_download. Có thể chỉ định rules_file (main.json, no-search.json, proxy-required.json, ...), language (zh-CN/zh-TW/zh-Hant), concurrency, min_interval_ms, max_interval_ms, retries. So Novel phải thực sự tải được các chương mà bạn có quyền đọc; liệt kê đủ chương không đảm bảo toàn bộ nội dung đúng.

Các job nằm dưới workspace/jobs/<job_id> với request.json, config.ini, status.json, download.log; file tại workspace/downloads/<job_id>. Tác vụ vẫn có thể hoàn thành dù phiên ChatGPT đã đóng.

### Tìm kiếm thông qua WebUI

WebUI gốc của So Novel **KHÔNG CÓ ĐĂNG NHẬP**, có thể lắng nghe trên mọi interface. MCP mặc định **không mở** WebUI. Chỉ dùng trên máy/mạng tin cậy, chặn kết nối tới port từ mạng ngoài qua Windows Firewall, tuyệt đối không port-forward lên Internet.

- sonovel_web_status kiểm tra dịch vụ.
- sonovel_web_start(confirm_unauthenticated_network_service=true) bật WebUI sau khi đã chấp nhận rủi ro.
- sonovel_search("无限恐怖之散装玩家"), sonovel_suggest, sonovel_web_sources(check_availability=true), sonovel_web_config, sonovel_web_local_books.
- sonovel_web_stop dừng WebUI do chính MCP mở, không can thiệp dịch vụ do người khác mở.

## 4. Danh mục 23 tools

| Nhóm | Tên tools |
|---|---|
| Tổng quan | sonovel_guide, sonovel_health |
| Nguồn | sonovel_list_rule_files, sonovel_list_sources, sonovel_source_rule, sonovel_validate_url |
| Tải / công việc | sonovel_start_download, sonovel_job_status, sonovel_jobs, sonovel_cancel_job |
| File / ebook | sonovel_local_books, sonovel_verify_book, sonovel_chapter_excerpt, sonovel_export_copy, sonovel_move_to_trash |
| WebUI | sonovel_web_status, sonovel_search, sonovel_suggest, sonovel_web_sources, sonovel_web_config, sonovel_web_local_books, sonovel_web_start, sonovel_web_stop |

Resource: sonovel://guide.

## 5. Bảo toàn dữ liệu & giới hạn

- File download do MCP tạo nằm trong workspace/, được .gitignore loại trừ. Không commit sách, token, cookie, file config local, Python venv, log hoặc binary.
- sonovel_move_to_trash yêu cầu xác nhận **đúng filename** và chỉ làm việc với file trong workspace, không đụng bộ truyện gốc downloads-419.
- sonovel_cancel_job kiểm tra tiến trình Java worker thật và giữ lại cache chương.
- Job sai/thất bại (kể cả CLI trả mã 0 nhưng chưa xuất file) được báo failed; không ngụy tạo kết quả.
- Có thử lại tối đa 2 lượt đối với lần không tạo đầu ra, ngoài retry nội bộ So Novel.
- Việc đủ mục EPUB, không lỗi CRC vẫn chưa chứng minh từng chữ giống Qidian; nên kiểm tra nguồn và quyền sử dụng. Không vượt quy tắc trả phí.

## 6. Kiểm thử

~~~powershell
cd C:\Coder\so-novel\so_novel_mcp
.\.venv\Scripts\python.exe -m pytest -q tests\test_core.py
.\.venv\Scripts\python.exe tests\mcp_smoke.py

# Chỉ dành cho COLINPC đang có rule mẫu 3 chương:
.\.venv\Scripts\python.exe tests\integration_download.py
~~~

Thông tin kiểm thử thực tế và các hạn chế được lưu ở IMPLEMENTATION-REPORT.md.

**Mã nguồn So Novel thuộc [freeok/so-novel](https://github.com/freeok/so-novel)**. MCP là lớp kết nối độc lập, không bao gồm mã Java của So Novel hoặc truyện; cần tuân thủ giấy phép phần mềm và quyền tác giả của nguồn nội dung.
