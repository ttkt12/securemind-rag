from __future__ import annotations

from openai import OpenAI

from catalog_metadata import build_metadata_answer
from catalog_service import answer_catalog_count, answer_catalog_list
from intent_router import detect_intent
from rag_core import answer_question, load_vector_store, make_client


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

    # Catalog-backed deterministic metadata answers (document code + aspect).
    # Answered from document_catalog.json without retrieval/LLM when possible;
    # otherwise we fall back to document-scoped RAG below.
    question_for_rag = question
    fallback_aspect = None
    fallback_code = None
    metadata_result = build_metadata_answer(question)
    if metadata_result is not None:
        if metadata_result["kind"] == "answer":
            meta = metadata_result["metadata"]
            payload = {
                "answer": metadata_result["answer"],
                "sources": metadata_result["sources"],
                "usage": None,
                "session_id": session_id or None,
                "answer_type": "metadata",
                "metadata": _debug_metadata(
                    meta, "metadata", meta.get("retrieval_used", False), meta.get("llm_used", False)
                ),
            }
            if debug:
                payload["debug"] = {
                    "intent": "metadata",
                    "answer_type": "metadata",
                    "metadata_source": meta.get("metadata_source"),
                    "normalized_document_code": meta.get("normalized_document_code"),
                    "query_aspect": meta.get("query_aspect"),
                    "retrieval_used": meta.get("retrieval_used", False),
                    "llm_used": meta.get("llm_used", False),
                }
            return payload
        if metadata_result["kind"] == "fallback":
            fallback_code = metadata_result.get("code")
            fallback_aspect = metadata_result.get("aspect")
            # Ensure the resolved code is present so RAG scopes to that document.
            if fallback_code and fallback_code.upper() not in question.upper():
                question_for_rag = f"{question} [{fallback_code}]"

    if vector_store is None:
        vector_store = load_vector_store()
    if client is None:
        client = make_client()

    retrieval_debug = {}
    response_metadata = {}
    answer, sources, usage = answer_question(
        question_for_rag,
        vector_store,
        client,
        conversation_state=conversation_state,
        memory_context=memory_context,
        conversation_history=history,
        debug_info_out=retrieval_debug if debug else None,
        metadata_out=response_metadata,
    )
    response_metadata.setdefault("answer_type", "rag")
    if fallback_aspect:
        # Document-scoped fallback after a metadata lookup missed the field.
        response_metadata["query_aspect"] = fallback_aspect
        response_metadata["metadata_source"] = "document"
        if fallback_code:
            response_metadata["normalized_document_code"] = fallback_code
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
