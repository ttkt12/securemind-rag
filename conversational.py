"""Grounded handling for conversational / meta questions.

These answers describe the assistant and its corpus only — they never invent
policy content — so they are safe under the strict-grounded policy. Substantive
questions still flow to retrieval / metadata / RAG.
"""

from __future__ import annotations

import unicodedata

from catalog_service import load_document_catalog

_GREETING_WORDS = {"hi", "hello", "hey", "helo", "hallo", "chao", "alo", "yo"}
_GREETING_PHRASES = {"hi", "hello", "hey", "chao", "xin chao", "chao ban", "alo", "hallo"}
_IDENTITY = (
    "ban la ai", "ban la gi", "ban ten gi", "ban ten la gi", "ai vay",
    "gioi thieu ve ban", "gioi thieu ban", "who are you", "what are you",
)
_CAPABILITIES = (
    "ban lam duoc gi", "ban lam duoc nhung gi", "lam duoc nhung gi", "lam duoc gi",
    "ban giup duoc gi", "ban giup gi", "giup duoc gi", "ban co the lam gi",
    "huong dan su dung", "cach su dung", "what can you do", "ban biet gi", "ban ho tro gi",
)


def _fold(text: str) -> str:
    folded = unicodedata.normalize("NFC", str(text or "")).lower().replace("đ", "d")
    folded = " ".join(folded.split())
    decomposed = unicodedata.normalize("NFD", folded)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def detect_meta_intent(question: str) -> str | None:
    """Return "greeting" | "identity" | "capabilities", or None.

    Greetings only match very short messages so a real question that merely opens
    with "chào" still goes to retrieval.
    """
    folded = _fold(question)
    if not folded:
        return None
    words = folded.split()
    if folded in _GREETING_PHRASES or (len(words) <= 2 and words[0] in _GREETING_WORDS):
        return "greeting"
    if any(phrase in folded for phrase in _IDENTITY):
        return "identity"
    if any(phrase in folded for phrase in _CAPABILITIES):
        return "capabilities"
    return None


def meta_answer(intent: str) -> str:
    total = len(load_document_catalog())
    if intent == "greeting":
        return (
            "Chào bạn 👋 Mình là **GRC Assistant** — trợ lý tra cứu tài liệu ISMS, bảo mật "
            "và tuân thủ của ZaloPay. Bạn cần tra cứu chính sách, quy trình hay tiêu chuẩn "
            "nào? Ví dụ: \"quy trình cấp quyền truy cập\", \"ZION-QT-04 có mấy phiên bản\"."
        )
    if intent == "identity":
        return (
            f"Mình là **GRC Assistant**, trợ lý tri thức GRC của ZaloPay (team GRC thuộc "
            f"Compliance). Mình trả lời dựa trên {total} tài liệu ISMS đã được lập chỉ mục — "
            "chỉ dùng nội dung trong tài liệu, không suy đoán bên ngoài."
        )
    return (
        "Mình có thể giúp bạn:\n\n"
        "* Tra cứu nội dung **chính sách / quy trình / tiêu chuẩn** bảo mật & tuân thủ\n"
        "* Gợi ý **nên xem tài liệu nào** cho một chủ đề\n"
        "* **Liệt kê phiên bản / tác giả / phạm vi** của một tài liệu\n"
        "* Cho biết **tổng số và danh sách** tài liệu\n\n"
        f"Hiện có {total} tài liệu trong cơ sở tri thức. Ví dụ: \"tài liệu nào về quản lý "
        "tài khoản\", \"ZION-TC-13 có những phiên bản nào\", \"có bao nhiêu tài liệu\"."
    )
