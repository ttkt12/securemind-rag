# 🎬 Kịch bản Demo — GRC Assistant

Trợ lý tri thức ISMS cho ZaloPay (Compliance / GRC). Demo gồm **2 kênh**: Web UI và Microsoft Teams.

---

## 🎯 Mục tiêu (nói mở đầu ~30s)

> "GRC Assistant biến **52 tài liệu ISMS** đã duyệt của ZaloPay thành trợ lý hỏi đáp. Mọi câu trả lời **chỉ lấy từ tài liệu**, kèm **trích dẫn nguồn** — không bịa, phù hợp môi trường tuân thủ. Dùng được trên **web** và ngay trong **Microsoft Teams**."

---

## ⚙️ Chuẩn bị (chọn 1)

**Cách A — Endpoint đã deploy (khuyến nghị, không cần setup):**
- Web: `https://endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn/`
- Teams: bot **GRC Assistant** (đã cài, chat trực tiếp).

**Cách B — Chạy local (backup, không phụ thuộc mạng/AgentBase):**
```bash
# macOS / Linux
bash scripts/demo.sh
```
```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
```
Script sẽ khởi động server, chờ sẵn sàng, tự mở trình duyệt `http://localhost:3978` và in sẵn câu hỏi demo.
> Yêu cầu: đã có `.env` (API key) và `vector_db/` (chạy `python ingest.py` nếu chưa có).

---

## 🖥️ Phần 1 — Web UI (~3 phút)

| # | Thao tác | Câu hỏi | Điểm nhấn khi nói |
|---|---|---|---|
| 1 | Mở trang | — | **Trang intro**: tổng quan 52 tài liệu (25 tiêu chuẩn · 13 quy trình · 8 hồ sơ · 4 chính sách · 2 chứng nhận). Bấm **"Vào trợ lý hỏi đáp"**. |
| 2 | Gõ | `tham khảo tài liệu gì về cấp quyền truy cập` | **Định tuyến thông minh** → gợi ý đúng tài liệu (QT-04, TC-13, QT-15) **tức thì**, không cần gọi LLM. |
| 3 | Gõ | `quy trình xử lý sự cố bảo mật gồm những bước nào` | Trả lời grounded + **trích dẫn `[n]` kiểu NotebookLM**. **Hover** vào `[n]` để xem nguồn, **click** để cuộn tới & highlight thẻ nguồn. |
| 4 | Gõ | `QT-01 có bao nhiêu version` | **Lịch sử phiên bản** — liệt kê đúng từ bảng trong tài liệu, dẫn đúng nguồn. |
| 5 | Gõ | `ai là tác giả của ZION-TC-13` | **Metadata theo bằng chứng** — không lấy từ field auto-extract dễ sai. |
| 6 | Gõ | `có bao nhiêu tài liệu` | **Catalog** — trả lời chính xác 52. |
| 7 | Gõ | `bạn làm được gì` | **Câu xã giao/meta** — trả lời thân thiện về năng lực (không lôi nội dung lạ). |
| 8 | Bấm 🌙/☀️ (góc trên phải) | — | **Dark/Light mode**, branding ZaloPay. |

**Điểm nhấn chốt:** "Mỗi câu trả lời đều dẫn đúng tài liệu + trang. Bot tự phân loại câu hỏi (gợi ý tài liệu / version / metadata / nội dung) để trả lời đúng cách."

---

## 💬 Phần 2 — Microsoft Teams (~1 phút)

| # | Thao tác | Câu hỏi |
|---|---|---|
| 1 | Mở chat bot **GRC Assistant** trong Teams | `hi` → bot chào + giới thiệu năng lực |
| 2 | Gõ | `QT-01 có bao nhiêu version` → liệt kê phiên bản + nguồn |
| 3 | Gõ | `tham khảo tài liệu gì về cấp quyền truy cập` → gợi ý tài liệu |

**Điểm nhấn:** "Cùng một bộ não, truy cập ngay trong công cụ làm việc hằng ngày. Bot hiện 'đang gõ…' rồi trả lời (xử lý bất đồng bộ nên không bị rớt khi model chậm)."

---

## 🗂️ Bộ câu hỏi nhanh (copy-paste)

```
tham khảo tài liệu gì về cấp quyền truy cập
quy trình xử lý sự cố bảo mật gồm những bước nào
QT-01 có bao nhiêu version
ZION-TC-13 có những phiên bản nào
ai là tác giả của ZION-TC-13
phạm vi áp dụng của ZION-QT-04
có bao nhiêu tài liệu
liệt kê tất cả tài liệu
bạn làm được gì
```

---

## 💡 Tips

- **Câu RAG (hỏi nội dung)** mất ~15–30s do model lớn — gõ trước câu này rồi nói trong lúc chờ; còn **gợi ý tài liệu / version / catalog** trả lời **tức thì**.
- Nếu một câu không có trong tài liệu → bot **gợi ý tài liệu liên quan** thay vì trả lời bừa (điểm cộng về độ tin cậy).
- Trên web, nhớ **hover/click `[n]`** để khoe tính năng trích dẫn.
- Câu trả lời luôn kèm phần **Nguồn** đánh số ở cuối.
