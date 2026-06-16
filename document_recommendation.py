from __future__ import annotations

import unicodedata

from document_intelligence import find_catalog_candidates, load_document_catalog

# Phrasings where the user is explicitly asking WHICH document / procedure /
# policy / standard to consult (e.g. "tham khảo tài liệu gì", "tài liệu nào",
# "which document"). Kept deliberately narrow so substantive content questions
# still flow to full RAG instead of being answered with a document list.
_DISCOVERY_PHRASES = (
    "tai lieu nao",
    "tai lieu gi",
    "quy trinh nao",
    "chinh sach nao",
    "tieu chuan nao",
    "van ban nao",
    "tai lieu tham khao",
    "tham khao tai lieu",
    "xem tai lieu nao",
    "doc tai lieu nao",
    "trong tai lieu nao",
    "o tai lieu nao",
    "tim tai lieu",
    "which document",
    "what document",
    "which policy",
    "which procedure",
    "which standard",
    "where can i find",
    "where is it documented",
)

# Only offer a recommendation when the top catalog candidate is at least this
# relevant; weaker/ambiguous matches fall through to normal retrieval.
_MIN_TOP_SCORE = 8


def _fold(text: str) -> str:
    folded = unicodedata.normalize("NFC", str(text or "")).lower().replace("đ", "d")
    folded = " ".join(folded.split())
    decomposed = unicodedata.normalize("NFD", folded)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def is_document_discovery_question(question: str) -> bool:
    folded = _fold(question)
    if any(phrase in folded for phrase in _DISCOVERY_PHRASES):
        return True
    return "tham khao" in folded and "tai lieu" in folded


def _recommendation_line(candidate: dict) -> str:
    code = str(candidate.get("document_code") or "").strip()
    title = str(candidate.get("document_title") or candidate.get("file_name") or "").strip()
    if code and title:
        return f"* {code} — {title}"
    return f"* {code or title or 'Tài liệu'}"


def related_documents_hint(question: str, limit: int = 3) -> str | None:
    """A short 'related documents' suggestion appended to a grounded
    not-found answer. Returns None when nothing in the catalog is relevant
    enough — so we never point users at unrelated documents.
    """
    catalog = load_document_catalog()
    if not catalog:
        return None
    candidates = find_catalog_candidates(question, catalog, limit=limit)
    if not candidates:
        return None
    top_score = int(candidates[0].get("catalog_score", 0))
    if top_score < _MIN_TOP_SCORE:
        return None
    cutoff = max(_MIN_TOP_SCORE, top_score * 0.5)
    selected = [c for c in candidates if int(c.get("catalog_score", 0)) >= cutoff][:limit]
    if not selected:
        return None
    lines = ["", "Một số tài liệu có thể liên quan:"]
    lines.extend(_recommendation_line(candidate) for candidate in selected)
    return "\n".join(lines)


def build_document_recommendation(question: str, limit: int = 4) -> dict | None:
    """Recommend the most relevant documents for a "which document" question.

    Returns a deterministic, catalog-driven answer payload (no LLM call) when the
    question is clearly asking which document to consult and the catalog has a
    strong match; otherwise returns None so the caller falls back to RAG.
    """
    if not is_document_discovery_question(question):
        return None

    catalog = load_document_catalog()
    if not catalog:
        return None

    candidates = find_catalog_candidates(question, catalog, limit=limit)
    if not candidates:
        return None

    top_score = int(candidates[0].get("catalog_score", 0))
    if top_score < _MIN_TOP_SCORE:
        return None

    # Keep only candidates that stay close to the best match so the list does not
    # trail off into weakly-related documents.
    cutoff = max(_MIN_TOP_SCORE, top_score * 0.5)
    selected = [c for c in candidates if int(c.get("catalog_score", 0)) >= cutoff][:limit]
    if not selected:
        return None

    lines = [
        "Dựa trên câu hỏi của bạn, các tài liệu liên quan nhất trong knowledge base là:",
        "",
    ]
    lines.extend(_recommendation_line(candidate) for candidate in selected)
    lines.append("")
    lines.append(
        "Bạn có thể hỏi chi tiết về một tài liệu cụ thể, ví dụ: "
        f'"{selected[0].get("document_code")} quy định gì".'
    )
    answer = "\n".join(lines)

    sources = []
    for candidate in selected:
        code = str(candidate.get("document_code") or "").strip()
        title = str(candidate.get("document_title") or "").strip()
        filename = str(candidate.get("file_name") or candidate.get("filename") or "").strip()
        label = f"{code} — {title}" if code and title else (title or code or filename)
        sources.append({"filename": filename or label, "label": label})

    return {
        "answer": answer,
        "sources": sources,
        "usage": None,
        "answer_type": "metadata",
        "metadata": {
            "answer_type": "metadata",
            "metadata_source": "catalog_recommendation",
            "recommended_codes": [candidate.get("document_code") for candidate in selected],
            "retrieval_used": False,
            "llm_used": False,
        },
    }
