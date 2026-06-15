from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any


def estimate_tokens(text: str) -> int:
    """Estimate tokens without making tiktoken a hard runtime dependency."""
    value = str(text or "")
    if not value:
        return 0

    try:
        import tiktoken  # type: ignore

        encoding = tiktoken.get_encoding("o200k_base")
        return len(encoding.encode(value))
    except Exception:
        # Useful enough for budgeting mixed Vietnamese/English text offline.
        word_estimate = int(len(value.split()) * 1.35)
        char_estimate = int(len(value) / 4)
        return max(1, max(word_estimate, char_estimate))


@dataclass
class ContextBudgetItem:
    index: int
    source: str
    page: int | None
    document_code: str
    content: str
    char_count: int
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def page_number(self) -> int | None:
        if isinstance(self.page, int):
            return self.page + 1
        return None


@dataclass
class ContextBudgetResult:
    context: str
    items: list[ContextBudgetItem]
    skipped_duplicates: int
    skipped_empty: int
    max_chars: int
    used_chars: int
    estimated_tokens: int

    def metadata(self) -> dict[str, Any]:
        return {
            "max_chars": self.max_chars,
            "used_chars": self.used_chars,
            "estimated_tokens": self.estimated_tokens,
            "included_chunks": len(self.items),
            "skipped_duplicates": self.skipped_duplicates,
            "skipped_empty": self.skipped_empty,
            "sources": [
                {
                    "label": item_label(item),
                    "filename": item.source,
                    "page": item.page_number,
                    "document_code": item.document_code or None,
                    "char_count": item.char_count,
                    "estimated_tokens": item.token_count,
                }
                for item in self.items
            ],
        }


def item_label(item: ContextBudgetItem) -> str:
    page_label = f" page {item.page_number}" if item.page_number is not None else ""
    return f"{item.source}{page_label}"


def _content_key(source: str, page: int | None, content: str) -> str:
    digest = hashlib.sha1(content[:2000].encode("utf-8", errors="ignore")).hexdigest()
    return f"{source}|{page if page is not None else ''}|{digest}"


def build_context_budget(
    documents,
    *,
    max_chars: int,
    source_name_fn,
    document_code_fn,
) -> ContextBudgetResult:
    context_parts: list[str] = []
    items: list[ContextBudgetItem] = []
    remaining_chars = max(0, int(max_chars or 0))
    used_chars = 0
    skipped_duplicates = 0
    skipped_empty = 0
    seen_keys: set[str] = set()

    for document in documents:
        if remaining_chars <= 0:
            break

        raw_content = str(getattr(document, "page_content", "") or "").strip()
        if not raw_content:
            skipped_empty += 1
            continue

        source = source_name_fn(document)
        page = getattr(document, "metadata", {}).get("page")
        document_code = getattr(document, "metadata", {}).get("document_code") or document_code_fn(source)
        dedupe_key = _content_key(source, page if isinstance(page, int) else None, raw_content)
        if dedupe_key in seen_keys:
            skipped_duplicates += 1
            continue
        seen_keys.add(dedupe_key)

        content = raw_content[:remaining_chars]
        if not content:
            skipped_empty += 1
            continue

        item = ContextBudgetItem(
            index=len(items) + 1,
            source=source,
            page=page if isinstance(page, int) else None,
            document_code=str(document_code or ""),
            content=content,
            char_count=len(content),
            token_count=estimate_tokens(content),
            metadata=dict(getattr(document, "metadata", {}) or {}),
        )
        page_label = f", page {item.page_number}" if item.page_number is not None else ""
        code_label = f"\nDocument code: {item.document_code}" if item.document_code else ""
        context_parts.append(f"[{item.index}] Source: {item.source}{page_label}{code_label}\n{item.content}")
        items.append(item)
        used_chars += len(content)
        remaining_chars -= len(content)

    context = "\n\n".join(context_parts)
    return ContextBudgetResult(
        context=context,
        items=items,
        skipped_duplicates=skipped_duplicates,
        skipped_empty=skipped_empty,
        max_chars=max_chars,
        used_chars=used_chars,
        estimated_tokens=estimate_tokens(context),
    )
