"""Catalog-backed deterministic answers for document-specific metadata.

When a question contains *both* a resolvable document code and a metadata
aspect (author, version count, latest version, reviewer, approver, effective
date, scope, purpose, responsibility), we answer directly from
``document_catalog.json`` instead of running generic RAG. This fixes
wrong-aspect answers (e.g. answering "latest version + author" when the user
asked only for the version count).

This is intentionally *not* full Ask Mode / multi-query synthesis — that remains
a later phase. When the catalog lacks the requested field, callers fall back to
document-scoped RAG.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from document_code_utils import find_code_candidates, resolve_code
from intent_router import repair_mojibake, replace_known_mojibake, strip_accents

CATALOG_PATH = Path("document_catalog.json")

# Aspects in detection-priority order. Each entry: (aspect, accent-folded
# trigger phrases). version_count must precede latest_version so "mấy version"
# is not swallowed by the bare "version" of latest_version triggers.
ASPECT_TRIGGERS: list[tuple[str, list[str]]] = [
    (
        "version_count",
        [
            "co may version",
            "may version",
            "bao nhieu version",
            "may phien ban",
            "bao nhieu phien ban",
            "so version",
            "tong so version",
            "version history",
            "revision history",
            "lich su thay doi",
            "lich su phien ban",
        ],
    ),
    (
        "latest_version",
        [
            "version moi nhat",
            "phien ban moi nhat",
            "latest version",
            "ban moi nhat",
        ],
    ),
    (
        "author",
        [
            "author",
            "tac gia",
            "nguoi soan",
            "nguoi tao",
            "prepared by",
            "owner",
            "pic",
        ],
    ),
    (
        "reviewer",
        [
            "reviewer",
            "reviewed by",
            "nguoi review",
            "review boi ai",
            "nguoi ra soat",
        ],
    ),
    (
        "approver",
        [
            "approver",
            "approved by",
            "nguoi phe duyet",
            "phe duyet boi ai",
            "phe duyet boi",
            "nguoi duyet",
        ],
    ),
    (
        "effective_date",
        [
            "effective date",
            "ngay hieu luc",
            "hieu luc ngay nao",
            "co hieu luc",
            "ngay ban hanh",
        ],
    ),
    (
        "scope",
        [
            "scope",
            "pham vi",
            "ap dung cho ai",
            "ap dung cho",
            "applies to",
            "applicable to",
        ],
    ),
    (
        "purpose",
        [
            "purpose",
            "muc dich",
        ],
    ),
    (
        "responsibility",
        [
            "responsibility",
            "responsible",
            "trach nhiem",
        ],
    ),
]

INSUFFICIENT_DOCUMENT_ANSWER = (
    "Mình chưa tìm thấy thông tin này trong tài liệu đã index."
)


def _normalize(text: str) -> str:
    value = replace_known_mojibake(repair_mojibake(text or ""))
    value = strip_accents(value).lower()
    return re.sub(r"\s+", " ", value).strip()


def detect_metadata_aspect(question: str):
    normalized = _normalize(question)
    if not normalized:
        return None
    for aspect, triggers in ASPECT_TRIGGERS:
        for phrase in triggers:
            if re.search(r"\b" + re.escape(phrase) + r"\b", normalized):
                return aspect
    return None


def _load_raw_items() -> list[dict]:
    try:
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict):
        items = payload.get("documents") or payload.get("items") or payload.get("catalog") or []
    else:
        items = payload
    return [item for item in items if isinstance(item, dict)]


@lru_cache(maxsize=1)
def _catalog_by_code() -> dict:
    index: dict[str, dict] = {}
    for item in _load_raw_items():
        code = str(item.get("document_code") or item.get("code") or "").strip()
        if code:
            index.setdefault(code, item)
    return index


def get_catalog_record(code: str):
    return _catalog_by_code().get(code)


def _clean(value) -> str:
    return str(value or "").strip()


def _letters(value: str) -> str:
    return re.sub(r"[^0-9A-Za-zÀ-ỹ]", "", value)


def _is_sufficient(value: str, min_letters: int = 2, min_len: int = 2) -> bool:
    text = _clean(value)
    if not text:
        return False
    return len(re.sub(r"[.\s]+", "", text)) >= min_len and len(_letters(text)) >= min_letters


def _metadata_source(record: dict) -> dict:
    code = _clean(record.get("document_code") or record.get("code"))
    filename = _clean(record.get("filename") or record.get("file_name") or record.get("source"))
    title = _clean(record.get("document_title") or record.get("title"))
    label_bits = [bit for bit in (code, title or filename) if bit]
    label = " — ".join(label_bits) if label_bits else (filename or code or "catalog document")
    return {
        "filename": filename or (f"{code}.pdf" if code else "catalog"),
        "page": None,
        "label": label,
        "code": code,
        "source_type": "catalog",
    }


def _answer_payload(answer: str, sources: list, code, aspect: str, partial: bool = False) -> dict:
    return {
        "kind": "answer",
        "answer": answer,
        "sources": sources,
        "metadata": {
            "answer_type": "metadata",
            "metadata_source": "catalog",
            "normalized_document_code": code,
            "query_aspect": aspect,
            "retrieval_used": False,
            "llm_used": False,
            "partial_from_catalog": partial,
        },
    }


def _fallback(code, aspect: str) -> dict:
    return {"kind": "fallback", "code": code, "aspect": aspect}


def _ambiguous_payload(candidates: list, aspect: str) -> dict:
    listed = ", ".join(candidates)
    answer = (
        f"Mã tài liệu bạn cung cấp khớp với nhiều tài liệu khác nhau: {listed}. "
        f"Vui lòng nêu rõ mã đầy đủ (ví dụ: {candidates[0]}) để mình trả lời chính xác."
    )
    return _answer_payload(answer, [], None, aspect)


def _version_count_answer(code: str, record: dict, sources: list) -> dict:
    history = record.get("version_history") or record.get("all_versions")
    if isinstance(history, list) and history:
        unique = list(dict.fromkeys(_clean(v) for v in history if _clean(v)))
        if unique:
            answer = (
                f"Tài liệu {code} hiện ghi nhận {len(unique)} phiên bản trong metadata: "
                + ", ".join(unique)
                + "."
            )
            return _answer_payload(answer, sources, code, "version_count")
    latest = _clean(record.get("latest_version") or record.get("version"))
    if latest:
        answer = (
            f"Tài liệu {code} đang ghi nhận phiên bản mới nhất là {latest}. "
            "Mình chưa tìm thấy bảng lịch sử phiên bản đầy đủ trong metadata "
            "để xác định tổng số version."
        )
        return _answer_payload(answer, sources, code, "version_count")
    return _fallback(code, "version_count")


# aspect -> (catalog field candidates, Vietnamese answer template, sufficiency)
_SIMPLE_ASPECTS = {
    "latest_version": (
        ("latest_version", "version"),
        "Phiên bản mới nhất của tài liệu {code} là {value}.",
        dict(min_letters=1, min_len=1),
    ),
    "author": (
        ("author",),
        "Tác giả (author) của tài liệu {code} là {value}.",
        dict(min_letters=2, min_len=2),
    ),
    "reviewer": (
        ("reviewer",),
        "Người review tài liệu {code} là {value}.",
        dict(min_letters=2, min_len=2),
    ),
    "approver": (
        ("approver",),
        "Người phê duyệt (approver) tài liệu {code} là {value}.",
        dict(min_letters=2, min_len=2),
    ),
    "effective_date": (
        ("effective_date",),
        "Ngày hiệu lực (effective date) của tài liệu {code} là {value}.",
        dict(min_letters=1, min_len=1),
    ),
    "scope": (
        ("scope_summary", "scope"),
        "Theo metadata catalog, phạm vi áp dụng (scope) của tài liệu {code} được tóm tắt: {value}",
        dict(min_letters=6, min_len=12),
    ),
    "purpose": (
        ("purpose_summary", "purpose"),
        "Theo metadata catalog, mục đích (purpose) của tài liệu {code} được tóm tắt: {value}",
        dict(min_letters=6, min_len=12),
    ),
}


def _answer_for_aspect(aspect: str, code: str, record: dict) -> dict:
    sources = [_metadata_source(record)]
    if aspect == "version_count":
        return _version_count_answer(code, record, sources)
    if aspect == "responsibility":
        # No dedicated catalog field; always defer to document-scoped retrieval.
        return _fallback(code, aspect)
    spec = _SIMPLE_ASPECTS.get(aspect)
    if not spec:
        return _fallback(code, aspect)
    fields, template, checks = spec
    value = ""
    for field in fields:
        candidate = _clean(record.get(field))
        if candidate:
            value = candidate
            break
    if value and _is_sufficient(value, **checks):
        partial = aspect in {"scope", "purpose"}
        return _answer_payload(template.format(code=code, value=value), sources, code, aspect, partial=partial)
    return _fallback(code, aspect)


def build_metadata_answer(question: str):
    """Return a metadata answer descriptor for ``question`` or ``None``.

    Result shapes:
      * ``{"kind": "answer", "answer", "sources", "metadata"}`` — answered from
        the catalog (or an ambiguity clarification); no retrieval/LLM used.
      * ``{"kind": "fallback", "code", "aspect"}`` — code resolved but the field
        is missing; caller should run document-scoped RAG.
      * ``None`` — not a metadata question (no aspect, or no usable code).
    """
    aspect = detect_metadata_aspect(question)
    if not aspect:
        return None

    resolved = None
    ambiguous: list = []
    for raw in find_code_candidates(question):
        code, candidates = resolve_code(raw)
        if code:
            resolved = code
            break
        if len(candidates) > 1 and not ambiguous:
            ambiguous = candidates

    if not resolved:
        if ambiguous:
            return _ambiguous_payload(ambiguous, aspect)
        return None

    record = get_catalog_record(resolved)
    if not record:
        return None
    return _answer_for_aspect(aspect, resolved, record)
