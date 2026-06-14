from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CATALOG_PATH = Path("document_catalog.json")
DOCUMENT_CODE_RE = re.compile(r"\b(?:ZION|ISO|PCI)[-_ ]?[A-Z]{2,8}[-_ ]?\d{1,3}(?:[-_ ]?\d+)?\b", re.IGNORECASE)


def derive_code(value: str) -> str:
    match = DOCUMENT_CODE_RE.search(value or "")
    if not match:
        return ""
    return match.group(0).replace("_", "-").replace(" ", "-").upper()


def clean_title_from_filename(filename: str) -> str:
    title = Path(filename or "").stem
    title = re.sub(r"^\s*[A-Z]+-[A-Z]+-\d+\s*[-–—]\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" -–—_")
    return title or filename or "Untitled document"


def _extract_items(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("documents", "items", "catalog"):
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def normalize_catalog_item(item: dict) -> dict:
    filename = (
        str(item.get("filename") or item.get("file_name") or item.get("source") or item.get("path") or "")
        .replace("\\", "/")
        .split("/")[-1]
        .strip()
    )
    title = str(item.get("title") or item.get("document_title") or item.get("name") or "").strip()
    code = str(item.get("code") or item.get("document_code") or "").strip()
    if not derive_code(code):
        code = derive_code(filename) or derive_code(title)
    else:
        code = derive_code(code)
    if not title:
        title = clean_title_from_filename(filename or code)
    page_count = item.get("page_count")
    try:
        page_count = int(page_count) if page_count not in (None, "") else None
    except (TypeError, ValueError):
        page_count = None
    return {
        "code": code,
        "title": title,
        "filename": filename or f"{title}.pdf",
        "page_count": page_count,
    }


def _dedupe_key(document: dict) -> str:
    filename = document.get("filename") or ""
    if filename:
        return f"filename:{filename.casefold()}"
    code = document.get("code") or ""
    if code:
        return f"code:{code.casefold()}"
    return f"title:{(document.get('title') or '').casefold()}"


def load_document_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    documents = []
    seen = set()
    for item in _extract_items(payload):
        normalized = normalize_catalog_item(item)
        key = _dedupe_key(normalized)
        if not key or key in seen:
            continue
        seen.add(key)
        documents.append(normalized)
    return documents


def catalog_count_payload() -> dict:
    documents = load_document_catalog()
    return {"total_documents": len(documents)}


def catalog_documents_payload() -> dict:
    documents = load_document_catalog()
    return {"total_documents": len(documents), "documents": documents}


def answer_catalog_count() -> dict:
    documents = load_document_catalog()
    total = len(documents)
    if total <= 0:
        answer = (
            "Không thể xác định số lượng tài liệu vì chưa tìm thấy document catalog. "
            "Vui lòng chạy lại bước build catalog/ingest."
        )
    else:
        answer = f"Hiện tại AI Agent này có {total} tài liệu duy nhất trong document catalog."
    return {
        "answer": answer,
        "sources": [],
        "metadata": {
            "answer_type": "catalog",
            "catalog_intent": "count",
            "total_documents": total,
            "retrieval_used": False,
            "llm_used": False,
        },
    }


def catalog_line(document: dict, index: int) -> str:
    code = document.get("code") or ""
    title = document.get("title") or document.get("filename") or "Untitled document"
    label = f"{code} — {title}" if code else title
    return f"{index}. {label}"


def answer_catalog_list() -> dict:
    documents = load_document_catalog()
    total = len(documents)
    if total <= 0:
        answer = (
            "Không thể xác định số lượng tài liệu vì chưa tìm thấy document catalog. "
            "Vui lòng chạy lại bước build catalog/ingest."
        )
    else:
        lines = [f"Danh sách {total} tài liệu trong AI Agent:", ""]
        lines.extend(catalog_line(document, index) for index, document in enumerate(documents, start=1))
        answer = "\n".join(lines)
    return {
        "answer": answer,
        "sources": [],
        "metadata": {
            "answer_type": "catalog",
            "catalog_intent": "list",
            "total_documents": total,
            "retrieval_used": False,
            "llm_used": False,
        },
    }
