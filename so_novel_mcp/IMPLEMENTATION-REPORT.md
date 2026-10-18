# So Novel MCP — Báo cáo triển khai trên COLINPC, 2026-10-18

## Kết quả

- Source: C:\Coder\so-novel\so_novel_mcp.
- Upstream MCP ID: so-novel, transport stdio, 23 tools và 1 resource.
- So Novel v1.11.0 tại C:\Coder\so-novel\runtime\SoNovel. Không sửa mã nguồn Java gốc.
- Lõi: sonovel_core.py; MCP: server.py; worker độc lập: worker.py; đăng ký Desktop Coworker: register_upstream.py.
- Chế độ WebUI: mặc định tắt do ứng dụng không có xác thực và có thể lắng nghe trên tất cả mạng. API WebUI có 7 công cụ nhưng chỉ dùng sau khi được bật trên mạng tin cậy.
- Quản lý tác vụ: jobs/downloads/exports/trash nằm trong workspace/ (gitignored).

## Kiểm thử

- Unit tests: 8/8 PASS; URL source allowlist, cấu hình riêng, quyền truy cập file, source catalog, đọc 419 chương hiện có, cấu trúc EPUB, che thông tin bí mật, tiến độ thực tế.
- MCP stdio: MCP_STARTED So Novel MCP TOOLS 23. Health, source listing, local books PASS.
- Download end-to-end qua MCP, URL thật trên Biquge365 với rule 3 chương:
  - Lượt 1: mạng timeout tại bước đọc BookParser; CLI trả code 0 nhưng không có đầu ra; MCP đánh dấu **failed** chính xác.
  - Lượt 2: EPUB thực tế có 3 chương, nhưng bộ nhận diện tiến độ nhầm "Attempt 1/2", dẫn tới **incomplete** giả; đã sửa và thêm regression test.
  - **Lượt 3 (đạt):** job 9496d23dd0f4480a; 3/3, succeeded; ZIP CRC PASS; EPUB 70,641 bytes; 3 chương; SHA256 182c3f0083ed97ebeb9d6eb3e73cd68680e917fd0437f5aec7859f080d6f2b59; export copy PASS.
- Bộ EPUB tiếng Trung 419 mục tại downloads-419 đã được kiểm tra lại bằng MCP ở chế độ read-only.
- Không tải lại bộ truyện 419 chương, không đụng China Novel DL / QuickNovel.

## Bảo mật và giới hạn

- WebUI không có auth: sẽ không tự khởi chạy; tool sonovel_web_start yêu cầu xác nhận rõ rằng đây là dịch vụ HTTP thiếu auth. Chưa kiểm thử bật WebUI qua MCP vì tránh mở dịch vụ không xác thực; các endpoint /sources, /search đã kiểm tra với So Novel gốc ở phiên trước.
- CLI bản upstream có thể return code 0 khi xảy ra Java parser timeout. MCP chỉ đánh dấu succeeded nếu có file thật, EPUB CRC hợp lệ và số chương phù hợp bộ đếm.
- Việc trình bày chapter đủ không xác nhận bản nguồn trùng 100% Qidian hay nội dung có quyền phân phối. Không vượt paywall, CAPTCHA, DRM.
- Chi tiết cách cài, cấu hình MCP, vận hành và chạy test trong README.md.

## Kích hoạt

- Chạy .\.venv\Scripts\python.exe register_upstream.py (nếu chưa đăng ký) với SONOVEL_HOME.
- Khởi động lại Desktop Coworker và kết nối lại COLINPC để nạp upstream mới.
- Kiểm tra mcp_servers, mcp_tools(server_id="so-novel"), gọi sonovel_health.
