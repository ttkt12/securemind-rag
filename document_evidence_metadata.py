"""Evidence-grounded answers for document-specific metadata questions.

The document catalog is allowed to *locate* a document (count / list / map a code
to a title/filename), but it is NOT trusted for version, author, reviewer,
approver, effective date, scope, purpose, or responsibility. Those auto-extracted
fields are frequently wrong — e.g. a table-of-contents section number ("4.4.2")
gets stored as ``latest_version`` and a change-log row ("3.4 Update Scope ...")
gets stored as ``scope_summary``.

This module answers those aspects from the *actual retrieved document chunks*:
it gathers the chunks of the matched document, applies aspect-specific, rule-based
extraction (no LLM), rejects change-log / table-of-contents noise, and clearly
reports when evidence is insufficient instead of guessing.
"""

from __future__ import annotations

import re

from rag_core import (
    document_source_name,
    extract_version_history_entries,
    fold_accents,
    normalize_for_match,
    version_key,
)

INSUFFICIENT_GENERIC = "Mình chưa tìm thấy thông tin này trong tài liệu đã index."
INSUFFICIENT_VERSION = "Mình chưa tìm thấy thông tin version trong tài liệu đã index."
INSUFFICIENT_SCOPE = "Mình chưa tìm thấy nội dung phạm vi áp dụng rõ ràng trong tài liệu đã index."
INSUFFICIENT_PURPOSE = "Mình chưa tìm thấy nội dung mục đích rõ ràng trong tài liệu đã index."

_DOTTED_LEADER = re.compile(r"\.{4,}")          # table-of-contents leaders
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_VERSION_ROW_PREFIX = re.compile(r"^\s*\d+\.\d+(?:\.\d+)?\s+\S")
_CHANGELOG_VERBS = (
    "update",
    "edit",
    "add ",
    "replace",
    "new issuance",
    "cap nhat",
    "chinh sua",
    "them ",
    "thay the",
)
_VERSION_CONTROL_MARKERS = (
    "version control",
    "version history",
    "revision history",
    "document history",
    "lich su thay doi",
    "lich su phien ban",
    "new issuance",
    "change process",
    "change history",
)

_MAX_SECTION_CHARS = 600


# --------------------------------------------------------------------------- #
# Chunk gathering
# --------------------------------------------------------------------------- #
def gather_document_chunks(vector_store, code: str) -> list:
    """Return every chunk belonging to ``code``, ordered by page then section."""
    if vector_store is None or not code:
        return []
    needle = code.upper()
    try:
        documents = list(vector_store.docstore._dict.values())
    except AttributeError:
        return []
    chunks = [doc for doc in documents if needle in document_source_name(doc).upper()]
    chunks.sort(key=lambda doc: (doc.metadata.get("page") or 0, doc.metadata.get("section_index") or 0))
    return chunks


def _source_record(code: str, chunks: list, catalog_record: dict | None, page=None) -> list[dict]:
    filename = document_source_name(chunks[0]) if chunks else ""
    if not filename and catalog_record:
        filename = str(catalog_record.get("filename") or catalog_record.get("file_name") or "")
    title = ""
    if catalog_record:
        title = str(catalog_record.get("document_title") or catalog_record.get("title") or "")
    label_bits = [bit for bit in (code, title or filename) if bit]
    label = " — ".join(label_bits) if label_bits else (filename or code)
    record = {
        "filename": filename or f"{code}.pdf",
        "page": (page + 1) if isinstance(page, int) else None,
        "label": label,
        "code": code,
        "source_type": "document_evidence",
    }
    return [record]


def _payload(answer: str, sources: list, code: str, aspect: str, verified: bool, llm_used: bool = False) -> dict:
    return {
        "answer": answer,
        "sources": sources,
        "metadata": {
            "answer_type": "metadata",
            "metadata_source": "document_evidence",
            "normalized_document_code": code,
            "query_aspect": aspect,
            "retrieval_used": True,
            "llm_used": llm_used,
            "evidence_verified": verified,
            "catalog_metadata_used": False,
        },
    }


# --------------------------------------------------------------------------- #
# Version extraction
# --------------------------------------------------------------------------- #
def _version_region_text(chunks: list) -> str:
    parts = []
    for doc in chunks:
        text = doc.page_content or ""
        if _DOTTED_LEADER.search(text):  # skip table-of-contents rows
            continue
        section = doc.metadata.get("section_title") or ""
        folded = fold_accents(normalize_for_match(text))
        folded_section = fold_accents(normalize_for_match(section))
        if (
            _VERSION_ROW_PREFIX.match(section)
            or any(marker in folded or marker in folded_section for marker in _VERSION_CONTROL_MARKERS)
        ):
            parts.append(text)
    return "\n".join(parts)


def _genuine_version_entries(chunks: list) -> list[dict]:
    """Return version-control rows that carry provenance (a year-bearing date or
    an author). This excludes procedure/TOC numbers like '5.1' or '4.4.2'."""
    entries = extract_version_history_entries(_version_region_text(chunks))
    genuine: list[dict] = []
    seen: set[str] = set()
    for entry in entries:
        date = entry.get("date") or ""
        author = entry.get("author") or ""
        if not (_YEAR.search(date) or author):
            continue
        version = entry.get("version") or ""
        if not version or version in seen:
            continue
        seen.add(version)
        genuine.append(entry)
    genuine.sort(key=lambda item: version_key(item["version"]))
    return genuine


def _answer_version_count(code, chunks, sources) -> dict:
    entries = _genuine_version_entries(chunks)
    if len(entries) >= 2:
        versions = [entry["version"] for entry in entries]
        latest = entries[-1]
        date_note = f" ({latest['date']})" if latest.get("date") else ""
        answer = (
            f"Theo bảng lịch sử phiên bản trong tài liệu {code}, có {len(versions)} phiên bản: "
            + ", ".join(versions)
            + f". Phiên bản mới nhất là {latest['version']}{date_note}."
        )
        return _payload(answer, sources, code, "version_count", verified=True)
    if len(entries) == 1:
        version = entries[0]["version"]
        answer = (
            f"Mình chỉ tìm thấy phiên bản đang ghi nhận là {version} trong tài liệu. "
            "Mình chưa tìm thấy bảng lịch sử phiên bản đầy đủ để xác định tổng số version."
        )
        return _payload(answer, sources, code, "version_count", verified=True)
    return _payload(INSUFFICIENT_VERSION, sources, code, "version_count", verified=False)


def _answer_latest_version(code, chunks, sources) -> dict:
    entries = _genuine_version_entries(chunks)
    if entries:
        latest = entries[-1]
        date_note = f" (ngày {latest['date']})" if latest.get("date") else ""
        answer = (
            f"Theo bảng lịch sử phiên bản trong tài liệu {code}, phiên bản mới nhất là "
            f"{latest['version']}{date_note}."
        )
        return _payload(answer, sources, code, "latest_version", verified=True)
    return _payload(INSUFFICIENT_VERSION, sources, code, "latest_version", verified=False)


# --------------------------------------------------------------------------- #
# Scope / purpose section extraction
# --------------------------------------------------------------------------- #
def _looks_like_changelog(text: str) -> bool:
    stripped = text.strip()
    folded = fold_accents(normalize_for_match(stripped))
    if "update scope" in folded:
        return True
    if re.match(r"^\s*\d+\.\d+(?:\.\d+)?\s+(?:" + "|".join(_CHANGELOG_VERBS) + r")", folded):
        return True
    # A bare version-control row: starts with N.N and carries a year.
    if re.match(r"^\s*\d+\.\d+\b", stripped) and _YEAR.search(folded):
        return True
    return False


def _strip_section_heading(text: str, headings: tuple[str, ...]) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    # Drop a leading section number like "1.2." or "2."
    cleaned = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", cleaned)
    folded = fold_accents(cleaned.lower())
    cut = 0
    for heading in headings:
        idx = folded.find(heading)
        if idx != -1:
            end = idx + len(heading)
            if end > cut:
                cut = end
    body = cleaned[cut:]
    # Tidy separators left by bilingual "Phạm vi áp dụng/ Scope" headings.
    body = re.sub(r"^[\s/:\-–—]+", "", body).strip()
    return body


def _extract_section(chunks: list, headings: tuple[str, ...]) -> tuple[str | None, object]:
    best_body, best_len, best_page = None, 0, None
    for doc in chunks:
        text = (doc.page_content or "").strip()
        if not text or _DOTTED_LEADER.search(text) or _looks_like_changelog(text):
            continue
        folded = fold_accents(normalize_for_match(text))
        if not any(heading in folded for heading in headings):
            continue
        body = _strip_section_heading(text, headings)
        letters = re.sub(r"[^A-Za-zÀ-ỹ]", "", body)
        if len(letters) < 40:  # heading with no real prose behind it
            continue
        if len(body) > best_len:
            best_body, best_len, best_page = body, len(body), doc.metadata.get("page")
    if best_body and len(best_body) > _MAX_SECTION_CHARS:
        best_body = best_body[:_MAX_SECTION_CHARS].rstrip() + "…"
    return best_body, best_page


# scope/purpose heading keywords are accent-folded
_SCOPE_HEADINGS = ("pham vi ap dung", "pham vi", "scope")
_PURPOSE_HEADINGS = ("muc dich", "purpose")


def _answer_scope(code, chunks, catalog_record) -> dict:
    body, page = _extract_section(chunks, _SCOPE_HEADINGS)
    sources = _source_record(code, chunks, catalog_record, page=page)
    if body:
        answer = f"Theo tài liệu {code}, phạm vi áp dụng (scope): {body}"
        return _payload(answer, sources, code, "scope", verified=True)
    return _payload(INSUFFICIENT_SCOPE, sources, code, "scope", verified=False)


def _answer_purpose(code, chunks, catalog_record) -> dict:
    body, page = _extract_section(chunks, _PURPOSE_HEADINGS)
    sources = _source_record(code, chunks, catalog_record, page=page)
    if body:
        answer = f"Theo tài liệu {code}, mục đích (purpose): {body}"
        return _payload(answer, sources, code, "purpose", verified=True)
    return _payload(INSUFFICIENT_PURPOSE, sources, code, "purpose", verified=False)


# --------------------------------------------------------------------------- #
# Label-based aspects: effective date / author / reviewer / approver
# --------------------------------------------------------------------------- #
_DATE_VALUE = (
    r"(\d{1,2}\s+[A-Za-zÀ-ỹ.]+\s+\d{4}"  # 19 May 2026
    r"|\d{1,2}/\d{1,2}/\d{4}"            # 30/04/2021
    r"|\d{4}-\d{2}-\d{2})"               # 2026-05-19
)
_EFFECTIVE_DATE_LABELS = r"(?:effective date|ngày hiệu lực|ngay hieu luc|ngày ban hành|ngay ban hanh)"

_PERSON_VALUE = r"([A-ZÀ-Ỹ][\wÀ-ỹ.'\-]*(?:\s+[A-ZÀ-Ỹ][\wÀ-ỹ.'\-]*){0,4})"
_PERSON_LABELS = {
    "author": r"(?:author|tác giả|tac gia|prepared by|người soạn|nguoi soan|owner)",
    "reviewer": r"(?:reviewer|reviewed by|người review|nguoi review|người rà soát|nguoi ra soat)",
    "approver": r"(?:approver|approved by|người phê duyệt|nguoi phe duyet|người duyệt|nguoi duyet)",
}


def _find_effective_date(chunks: list) -> tuple[str | None, object]:
    for doc in chunks[:8]:  # the header/cover carries the effective date
        match = re.search(_EFFECTIVE_DATE_LABELS + r"\s*[:\-]?\s*" + _DATE_VALUE, doc.page_content or "", re.IGNORECASE)
        if match:
            return match.group(1).strip(), doc.metadata.get("page")
    return None, None


# Tokens that signal a column header / role phrase rather than a person name.
_NON_NAME_TOKENS = {
    "va", "xem", "xet", "phe", "duyet", "soan", "lap", "kiem", "tra",
    "review", "reviewed", "approve", "approved", "approval", "prepared",
    "author", "owner", "reviewer", "approver", "date", "ngay", "name", "ten",
}


def _looks_like_person_name(value: str) -> bool:
    folded = fold_accents(value.lower())
    tokens = [tok for tok in re.split(r"\s+", folded) if tok]
    if not tokens or len(tokens) > 5:
        return False
    if any(tok in _NON_NAME_TOKENS for tok in tokens):
        return False
    return len(re.sub(r"[^A-Za-zÀ-ỹ]", "", value)) >= 2


def _find_labeled_person(chunks: list, label_pattern: str) -> tuple[str | None, object]:
    for doc in chunks:
        match = re.search(label_pattern + r"\s*[:\-]\s*" + _PERSON_VALUE, doc.page_content or "", re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if _looks_like_person_name(value):
                return value, doc.metadata.get("page")
    return None, None


def _answer_effective_date(code, chunks, catalog_record) -> dict:
    value, page = _find_effective_date(chunks)
    sources = _source_record(code, chunks, catalog_record, page=page)
    if value:
        answer = f"Theo tài liệu {code}, ngày hiệu lực (effective date) là {value}."
        return _payload(answer, sources, code, "effective_date", verified=True)
    return _payload(INSUFFICIENT_GENERIC, sources, code, "effective_date", verified=False)


def _answer_person(code, chunks, catalog_record, aspect: str) -> dict:
    # Prefer the version-control table: it carries clean per-version
    # author/reviewer/approver names. Fall back to an explicit "Label: Name"
    # field only when the table has nothing for this aspect.
    page = None
    value = None
    entries = _genuine_version_entries(chunks)
    if entries:
        candidate = entries[-1].get(aspect)
        if candidate and _looks_like_person_name(candidate):
            value = candidate
    if not value:
        value, page = _find_labeled_person(chunks, _PERSON_LABELS[aspect])
    sources = _source_record(code, chunks, catalog_record, page=page)
    label_vi = {"author": "Tác giả (author)", "reviewer": "Người review", "approver": "Người phê duyệt (approver)"}[aspect]
    if value:
        answer = f"Theo tài liệu {code}, {label_vi}: {value}."
        return _payload(answer, sources, code, aspect, verified=True)
    return _payload(INSUFFICIENT_GENERIC, sources, code, aspect, verified=False)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def answer_document_metadata_from_evidence(
    question: str,
    normalized_code: str,
    catalog_record: dict | None,
    vector_store,
    aspect: str,
    debug: bool = False,
) -> dict:
    """Answer a document-metadata ``aspect`` for ``normalized_code`` from evidence.

    Returns ``{"answer", "sources", "metadata"}``. ``metadata.metadata_source`` is
    always ``"document_evidence"`` and ``catalog_metadata_used`` is always False —
    the catalog is used only to locate the document.
    """
    chunks = gather_document_chunks(vector_store, normalized_code)
    base_sources = _source_record(normalized_code, chunks, catalog_record)
    if not chunks:
        return _payload(INSUFFICIENT_GENERIC, base_sources, normalized_code, aspect, verified=False)

    if aspect == "version_count":
        return _answer_version_count(normalized_code, chunks, base_sources)
    if aspect == "latest_version":
        return _answer_latest_version(normalized_code, chunks, base_sources)
    if aspect == "scope":
        return _answer_scope(normalized_code, chunks, catalog_record)
    if aspect == "purpose":
        return _answer_purpose(normalized_code, chunks, catalog_record)
    if aspect == "effective_date":
        return _answer_effective_date(normalized_code, chunks, catalog_record)
    if aspect in _PERSON_LABELS:  # author / reviewer / approver
        return _answer_person(normalized_code, chunks, catalog_record, aspect)

    # responsibility or any other aspect: try a section, else insufficient.
    body, page = _extract_section(chunks, ("trach nhiem", "responsibilit", "responsible"))
    sources = _source_record(normalized_code, chunks, catalog_record, page=page)
    if body:
        return _payload(f"Theo tài liệu {normalized_code}: {body}", sources, normalized_code, aspect, verified=True)
    return _payload(INSUFFICIENT_GENERIC, sources, normalized_code, aspect, verified=False)
