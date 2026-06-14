from __future__ import annotations

from openai import OpenAI

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
        allow_catalog=False,
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
