from __future__ import annotations

from openai import OpenAI

from catalog_metadata import build_metadata_answer, get_catalog_record
from catalog_service import answer_catalog_count, answer_catalog_list
from document_evidence_metadata import answer_document_metadata_from_evidence
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

    # Document-specific metadata questions (document code + aspect). The catalog
    # is used ONLY to locate/disambiguate the document; the answer comes from
    # retrieved document evidence, never from auto-extracted catalog fields.
    metadata_result = build_metadata_answer(question)
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
