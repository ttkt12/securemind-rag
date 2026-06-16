"""Routing for document-specific metadata questions.

This module decides *whether* a question is a document-metadata question and, if
so, which aspect (version count, latest version, author, reviewer, approver,
effective date, scope, purpose, responsibility) and which document code it refers
to. It does NOT answer from catalog fields — the catalog is trusted only to
*locate* the document (resolve/disambiguate the code). The actual answer is
produced from retrieved document evidence by
``document_evidence_metadata.answer_document_metadata_from_evidence``.

Earlier this module answered directly from auto-extracted catalog fields
(``latest_version``, ``scope_summary`` …), which produced wrong answers such as a
table-of-contents number ("4.4.2") for a version or a change-log row for a scope.
That behavior has been removed.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from document_code_utils import find_code_candidates, resolve_code
from intent_router import repair_mojibake, replace_known_mojibake, strip_accents

CATALOG_PATH = Path("document_catalog.json")

# Aspects in detection-priority order. version_count must precede latest_version
# so "mấy version" is not swallowed by the bare "version" of latest_version.
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
            # "list the versions" phrasings (the version_count answer lists them)
            "cac phien ban",
            "nhung phien ban",
            "phien ban nao",
            "cac version",
            "nhung version",
            "version nao",
            "liet ke phien ban",
            "liet ke cac phien ban",
            "liet ke version",
            "liet ke cac version",
            "danh sach phien ban",
            "danh sach version",
            "list version",
            "list all version",
            "list the version",
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
    """Locate the catalog record for a code (title/filename only; not trusted for
    metadata field values)."""
    return _catalog_by_code().get(code)


def _clarify_payload(candidates: list, aspect: str) -> dict:
    listed = ", ".join(candidates)
    answer = (
        f"Mã tài liệu bạn cung cấp khớp với nhiều tài liệu khác nhau: {listed}. "
        f"Vui lòng nêu rõ mã đầy đủ (ví dụ: {candidates[0]}) để mình trả lời chính xác."
    )
    return {
        "kind": "clarify",
        "answer": answer,
        "sources": [],
        "metadata": {
            "answer_type": "metadata",
            "metadata_source": "catalog",
            "normalized_document_code": None,
            "query_aspect": aspect,
            "retrieval_used": False,
            "llm_used": False,
            "evidence_verified": False,
            "catalog_metadata_used": False,
        },
    }


def resolve_metadata_request(question: str):
    """Return ``{"aspect", "code", "candidates"}`` or ``None``.

    ``code`` is the resolved canonical code, or ``None`` when the shorthand is
    ambiguous (``candidates`` then lists the competing codes) or no code is found.
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
    return {"aspect": aspect, "code": resolved, "candidates": ambiguous}


def build_metadata_answer(question: str, fallback_code: str | None = None):
    """Route a metadata question.

    ``fallback_code`` is used when the question has a metadata aspect but no
    explicit code — e.g. a follow-up like "tài liệu này có mấy version" where the
    document was named earlier in the conversation.

    Returns one of:
      * ``None`` — not a metadata question (no aspect, or no usable code).
      * ``{"kind": "clarify", ...}`` — ambiguous shorthand; ask for the full code
        (deterministic, no retrieval/LLM).
      * ``{"kind": "evidence", "code", "aspect"}`` — resolved; the caller must
        answer from document evidence (never from catalog fields).
    """
    request = resolve_metadata_request(question)
    if not request:
        return None
    aspect = request["aspect"]
    if request["code"]:
        return {"kind": "evidence", "code": request["code"], "aspect": aspect}
    if request["candidates"]:
        return _clarify_payload(request["candidates"], aspect)
    if fallback_code:
        return {"kind": "evidence", "code": fallback_code, "aspect": aspect}
    return None
