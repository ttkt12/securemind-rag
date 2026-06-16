from __future__ import annotations

import re
import unicodedata

# A question naming a specific document code (ZION-QT-16) or asking about a
# document's versions is about ONE document, not the whole knowledge base — it
# must not be answered with a catalog-wide list/count.
_DOCUMENT_CODE_RE = re.compile(r"\b(?:ZION|ISO|PCI)[-_ ]?[A-Z]{2,8}[-_ ]?\d{1,3}\b", re.IGNORECASE)
_VERSION_TERMS = ("version", "phien ban")


MOJIBAKE_REPLACEMENTS = {
    "ká»ƒ": "ke",
    "tĂªn": "ten",
    "liá»‡t": "liet",
    "kĂª": "ke",
    "sĂ¡ch": "sach",
    "táº¥t": "tat",
    "cáº£": "ca",
    "tĂ i": "tai",
    "liá»‡u": "lieu",
    "toĂ n": "toan",
    "bá»™": "bo",
    "Ä‘Ă³": "do",
    "cĂ¡c": "cac",
    "nhá»¯ng": "nhung",
    "bao nhiĂªu": "bao nhieu",
    "cĂ³": "co",
    "tá»•ng": "tong",
    "sá»‘": "so",
}


CATALOG_LIST_TRIGGERS = [
    "ke ten",
    "liet ke",
    "danh sach",
    "tat ca tai lieu",
    "toan bo tai lieu",
    "tai lieu do",
    "cac tai lieu do",
    "nhung tai lieu do",
    "ke ten tat ca tai lieu do ra",
    "ke tat ca cac tai lieu do",
    "list documents",
    "list all documents",
    "show all documents",
    "those documents",
    "all of them",
]

CATALOG_COUNT_TRIGGERS = [
    "bao nhieu document",
    "bao nhieu tai lieu",
    "co tat ca bao nhieu",
    "tong so tai lieu",
    "how many documents",
    "total documents",
    "document count",
]

FOLLOW_UP_LIST_TERMS = [
    "do",
    "tat ca",
    "ke ten",
    "liet ke",
]


def repair_mojibake(text: str) -> str:
    current = text
    for _ in range(2):
        changed = False
        for encoding in ("cp1252", "latin1"):
            try:
                repaired = current.encode(encoding).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if repaired != current:
                current = repaired
                changed = True
                break
        if not changed:
            break
    return current


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def replace_known_mojibake(text: str) -> str:
    value = text
    for broken, replacement in MOJIBAKE_REPLACEMENTS.items():
        value = value.replace(broken, replacement)
        value = value.replace(broken.lower(), replacement)
    return value


def normalized_variants(text: str) -> set[str]:
    raw_source = (text or "").strip()
    repaired_source = repair_mojibake(raw_source)
    known_repaired_source = replace_known_mojibake(raw_source)
    raw = " ".join(raw_source.lower().split())
    repaired = " ".join(repaired_source.lower().split())
    known_repaired = " ".join(known_repaired_source.lower().split())
    variants = {raw, repaired, known_repaired}
    variants.update(replace_known_mojibake(item) for item in list(variants))
    variants.update(strip_accents(item) for item in list(variants))
    return {item for item in variants if item}


def contains_any(variants: set[str], triggers: list[str]) -> bool:
    trigger_variants = []
    for trigger in triggers:
        trigger_variants.extend(normalized_variants(trigger))
    return any(trigger in variant for variant in variants for trigger in trigger_variants)


def history_has_catalog_answer(history: list | None) -> bool:
    if not isinstance(history, list):
        return False
    recent = history[-6:]
    for item in recent:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").lower()
        content_variants = normalized_variants(str(item.get("content") or ""))
        if role == "assistant" and (
            contains_any(content_variants, ["document catalog"])
            or contains_any(content_variants, ["tai lieu duy nhat"])
        ):
            return True
    return False


def looks_like_mojibake_catalog_list(question: str) -> bool:
    raw = (question or "").lower()
    mojibake_markers = ("k\u00e1\u00bb", "li\u00e1\u00bb", "t\u0102", "\u00c4\u2018")
    list_markers = ("document", "li", "t\u00c3", "t\u00e0i", "tai")
    if any(marker in raw for marker in mojibake_markers) and any(marker in raw for marker in list_markers):
        return True
    if "?" in raw:
        question_mark_patterns = (
            "k???",
            "t??n",
            "li???t",
            "danh s??",
            "t???t c???",
            "t??i li",
            "li???u",
            "c??c t??i",
            "nh???ng t??i",
        )
        return any(pattern in raw for pattern in question_mark_patterns)
    return False


def looks_like_mojibake_catalog_count(question: str) -> bool:
    raw = (question or "").lower()
    if "document" in raw and ("bao nhi\u0102" in raw or "bao nhi\u00c3" in raw):
        return True
    if "?" in raw and ("bao nhi" in raw or "t???ng s" in raw or "c?? t???t c" in raw):
        return True
    return False


def references_specific_document(question: str, variants: set[str]) -> bool:
    """True when the question targets one specific document (by code) or asks
    about a document's versions, so catalog-wide list/count must not fire."""
    if _DOCUMENT_CODE_RE.search(question or ""):
        return True
    return any(term in variant for variant in variants for term in _VERSION_TERMS)


def detect_intent(question: str, history: list | None = None) -> str:
    variants = normalized_variants(question)

    # "List the versions of ZION-QT-16" / "how many versions does X have" are
    # per-document questions; route them to metadata, not the catalog list/count.
    if references_specific_document(question, variants):
        return "rag_question"

    if contains_any(variants, CATALOG_LIST_TRIGGERS):
        return "catalog_list"

    if history_has_catalog_answer(history) and contains_any(variants, FOLLOW_UP_LIST_TERMS):
        return "catalog_list"

    if contains_any(variants, CATALOG_COUNT_TRIGGERS):
        return "catalog_count"

    if looks_like_mojibake_catalog_count(question):
        return "catalog_count"

    if looks_like_mojibake_catalog_list(question):
        return "catalog_list"

    return "rag_question"
