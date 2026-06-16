from __future__ import annotations

from openai import OpenAI

from catalog_metadata import build_metadata_answer, get_catalog_record
from catalog_service import answer_catalog_count, answer_catalog_list
from conversational import detect_meta_intent, meta_answer
from document_code_utils import find_code_candidates, resolve_code
from document_evidence_metadata import answer_document_metadata_from_evidence
from document_recommendation import build_document_recommendation, related_documents_hint
from intent_router import detect_intent
from rag_core import NO_RELEVANT_CONTEXT_ANSWER, answer_question, load_vector_store, make_client


def _last_document_code(history: list | None) -> str | None:
    """Most recent resolvable document code mentioned in the conversation, used to
    resolve follow-ups like "tài liệu này có mấy version" that omit the code."""
    if not isinstance(history, list):
        return None
    for item in reversed(history[-8:]):
        if not isinstance(item, dict):
            continue
        for raw in find_code_candidates(str(item.get("content") or "")):
            code, _ = resolve_code(raw)
            if code:
                return code
    return None


def _debug_metadata(metadata: dict, intent: str, retrieval_used: bool, llm_used: bool) -> dict:
    metadata["intent"] = intent
    metadata["retrieval_used"] = retrieval_used
    metadata["llm_used"] = llm_used
    return metadata


def answer_chat(
    question: str,
    vector_store=None,
    client: OpenAI | None = None,
    history: list | None = None,
    session_id: str | None = None,
    debug: bool = False,
    conversation_state: dict | None = None,
    memory_context: str = "",
) -> dict:
    intent = detect_intent(question, history)

    # Greetings / "who are you" / "what can you do": answer about the assistant
    # itself (grounded — never invents policy) instead of running retrieval.
    meta_intent = detect_meta_intent(question)
    if meta_intent:
        meta = _debug_metadata({"answer_type": "meta"}, meta_intent, False, False)
        payload = {
            "answer": meta_answer(meta_intent),
            "sources": [],
            "usage": None,
            "session_id": session_id or None,
            "answer_type": "meta",
            "metadata": meta,
        }
        if debug:
            payload["debug"] = {"intent": meta_intent, "answer_type": "meta"}
        return payload

    if intent == "catalog_count":
        payload = answer_catalog_count()
        payload["session_id"] = session_id or None
        payload["answer_type"] = "catalog"
        payload["metadata"] = _debug_metadata(payload["metadata"], intent, False, False)
        if debug:
            payload["debug"] = {
                "intent": intent,
                "answer_type": "catalog",
                "catalog_count": payload["metadata"]["total_documents"],
                "retrieval_used": False,
                "llm_used": False,
            }
        return payload

    if intent == "catalog_list":
        payload = answer_catalog_list()
        payload["session_id"] = session_id or None
        payload["answer_type"] = "catalog"
        payload["metadata"] = _debug_metadata(payload["metadata"], intent, False, False)
        if debug:
            payload["debug"] = {
                "intent": intent,
                "answer_type": "catalog",
                "catalog_count": payload["metadata"]["total_documents"],
                "retrieval_used": False,
                "llm_used": False,
            }
        return payload

    # "Which document should I look at for X?" questions are answered directly
    # from catalog metadata, which routes by topic far more reliably than chunk
    # embeddings for this phrasing (and needs no LLM call).
    recommendation = build_document_recommendation(question)
    if recommendation is not None:
        recommendation["session_id"] = session_id or None
        recommendation["metadata"] = _debug_metadata(
            recommendation["metadata"], "document_discovery", False, False
        )
        if debug:
            recommendation["debug"] = {"intent": "document_discovery", **recommendation["metadata"]}
        return recommendation

    # Document-specific metadata questions (document code + aspect). The catalog
    # is used ONLY to locate/disambiguate the document; the answer comes from
    # retrieved document evidence, never from auto-extracted catalog fields.
    metadata_result = build_metadata_answer(question, fallback_code=_last_document_code(history))
    if metadata_result is not None:
        if metadata_result["kind"] == "clarify":
            meta = _debug_metadata(metadata_result["metadata"], "metadata", False, False)
            payload = {
                "answer": metadata_result["answer"],
                "sources": metadata_result["sources"],
                "usage": None,
                "session_id": session_id or None,
                "answer_type": "metadata",
                "metadata": meta,
            }
            if debug:
                payload["debug"] = {"intent": "metadata", **meta}
            return payload
        if metadata_result["kind"] == "evidence":
            code = metadata_result["code"]
            aspect = metadata_result["aspect"]
            if vector_store is None:
                vector_store = load_vector_store()
            evidence = answer_document_metadata_from_evidence(
                question, code, get_catalog_record(code), vector_store, aspect, debug=debug
            )
            meta = evidence["metadata"]
            _debug_metadata(meta, "metadata", meta.get("retrieval_used", True), meta.get("llm_used", False))
            payload = {
                "answer": evidence["answer"],
                "sources": evidence["sources"],
                "usage": None,
                "session_id": session_id or None,
                "answer_type": "metadata",
                "metadata": meta,
            }
            if debug:
                payload["debug"] = {"intent": "metadata", **meta}
            return payload

    if vector_store is None:
        vector_store = load_vector_store()
    if client is None:
        client = make_client()

    retrieval_debug = {}
    response_metadata = {}
    answer, sources, usage = answer_question(
        question,
        vector_store,
        client,
        conversation_state=conversation_state,
        memory_context=memory_context,
        conversation_history=history,
        debug_info_out=retrieval_debug if debug else None,
        metadata_out=response_metadata,
    )
    # Grounded fallback: when nothing in the indexed text answers the question,
    # point to the most relevant documents instead of a bare "not found", and
    # drop the (rejected) retrieved sources so we don't cite irrelevant docs.
    if answer == NO_RELEVANT_CONTEXT_ANSWER:
        hint = related_documents_hint(question)
        if hint:
            answer = f"{answer}\n{hint}"
            sources = []
    response_metadata.setdefault("answer_type", "rag")
    _debug_metadata(response_metadata, intent, True, True)

    payload = {
        "answer": answer,
        "sources": sources,
        "usage": usage,
        "session_id": session_id or None,
        "answer_type": "rag",
        "metadata": response_metadata,
    }
    if debug:
        retrieval_debug.update(
            {
                "intent": intent,
                "answer_type": "rag",
                "retrieval_used": True,
                "llm_used": True,
            }
        )
        payload["debug"] = retrieval_debug
    return payload
