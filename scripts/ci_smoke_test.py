from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from answer_engine import answer_chat
from catalog_service import load_document_catalog
from intent_router import detect_intent
from rag_core import load_vector_store, make_client


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def u(value: str) -> str:
    return value.encode("ascii").decode("unicode_escape")


def test_catalog_core() -> None:
    count_question = "có tất cả bao nhiêu document trong AI Agent này?"
    list_question = "kể tên tất cả tài liệu đó ra"
    history = [
        {"role": "user", "content": count_question},
        {
            "role": "assistant",
            "content": "Hiện tại AI Agent này có 52 tài liệu duy nhất trong document catalog.",
        },
    ]
    catalog = load_document_catalog()
    assert_true(len(catalog) == 52, f"expected 52 catalog documents, got {len(catalog)}")
    assert_true(detect_intent(count_question) == "catalog_count", "count intent not detected")
    assert_true(detect_intent(list_question, history) == "catalog_list", "list intent not detected")

    vietnamese_list_phrases = [
        r"k\u1ec3 t\u00ean",
        r"li\u1ec7t k\u00ea",
        r"danh s\u00e1ch",
        r"t\u1ea5t c\u1ea3 t\u00e0i li\u1ec7u",
        r"to\u00e0n b\u1ed9 t\u00e0i li\u1ec7u",
        r"t\u00e0i li\u1ec7u \u0111\u00f3",
        r"c\u00e1c t\u00e0i li\u1ec7u \u0111\u00f3",
        r"nh\u1eefng t\u00e0i li\u1ec7u \u0111\u00f3",
        r"k\u1ec3 t\u00ean t\u1ea5t c\u1ea3 t\u00e0i li\u1ec7u \u0111\u00f3 ra",
        r"k\u1ec3 t\u1ea5t c\u1ea3 c\u00e1c t\u00e0i li\u1ec7u \u0111\u00f3",
    ]
    for phrase in vietnamese_list_phrases:
        assert_true(detect_intent(u(phrase), history) == "catalog_list", f"list phrase missed: {phrase}")

    list_phrases = [
        "ká»ƒ tĂªn",
        "ke ten",
        "liá»‡t kĂª",
        "liet ke",
        "danh sĂ¡ch",
        "danh sach",
        "táº¥t cáº£ tĂ i liá»‡u",
        "tat ca tai lieu",
        "toĂ n bá»™ tĂ i liá»‡u",
        "toan bo tai lieu",
        "tĂ i liá»‡u Ä‘Ă³",
        "tai lieu do",
        "cĂ¡c tĂ i liá»‡u Ä‘Ă³",
        "cac tai lieu do",
        "nhá»¯ng tĂ i liá»‡u Ä‘Ă³",
        "nhung tai lieu do",
        "ká»ƒ tĂªn táº¥t cáº£ tĂ i liá»‡u Ä‘Ă³ ra",
        "ká»ƒ táº¥t cáº£ cĂ¡c tĂ i liá»‡u Ä‘Ă³",
        "list documents",
        "list all documents",
        "show all documents",
        "those documents",
        "all of them",
    ]
    for phrase in list_phrases:
        assert_true(detect_intent(phrase, history) == "catalog_list", f"list phrase missed: {phrase}")

    vietnamese_count_phrases = [
        r"bao nhi\u00eau document",
        r"bao nhi\u00eau t\u00e0i li\u1ec7u",
        r"c\u00f3 t\u1ea5t c\u1ea3 bao nhi\u00eau",
        r"t\u1ed5ng s\u1ed1 t\u00e0i li\u1ec7u",
    ]
    for phrase in vietnamese_count_phrases:
        assert_true(detect_intent(u(phrase)) == "catalog_count", f"count phrase missed: {phrase}")

    count_phrases = [
        "bao nhiĂªu document",
        "bao nhieu document",
        "bao nhiĂªu tĂ i liá»‡u",
        "bao nhieu tai lieu",
        "cĂ³ táº¥t cáº£ bao nhiĂªu",
        "co tat ca bao nhieu",
        "tá»•ng sá»‘ tĂ i liá»‡u",
        "tong so tai lieu",
        "how many documents",
        "total documents",
        "document count",
    ]
    for phrase in count_phrases:
        assert_true(detect_intent(phrase) == "catalog_count", f"count phrase missed: {phrase}")

    print(f"Catalog loader count: {len(catalog)}")


def test_catalog_answers(vector_store, client) -> None:
    count_response = answer_chat(
        "có tất cả bao nhiêu document trong AI Agent này?",
        vector_store,
        client,
        debug=True,
    )
    count_meta = count_response.get("metadata", {})
    assert_true(count_meta.get("answer_type") == "catalog", "catalog count answer_type mismatch")
    assert_true(count_meta.get("catalog_intent") == "count", "catalog count intent mismatch")
    assert_true(count_meta.get("retrieval_used") is False, "catalog count used retrieval")
    assert_true(count_meta.get("llm_used") is False, "catalog count used LLM")
    assert_true(count_response.get("sources") == [], "catalog count returned sources")

    list_response = answer_chat(
        "kể tên tất cả tài liệu đó ra",
        vector_store,
        client,
        history=[
            {"role": "user", "content": "có tất cả bao nhiêu document trong AI Agent này?"},
            {
                "role": "assistant",
                "content": count_response.get("answer", ""),
            },
        ],
        debug=True,
    )
    list_meta = list_response.get("metadata", {})
    total = list_meta.get("total_documents", 0)
    assert_true(list_meta.get("catalog_intent") == "list", "catalog list intent mismatch")
    assert_true(list_meta.get("retrieval_used") is False, "catalog list used retrieval")
    assert_true(list_meta.get("llm_used") is False, "catalog list used LLM")
    assert_true(list_response.get("sources") == [], "catalog list returned sources")
    assert_true(str(total) in list_response.get("answer", ""), "catalog list did not include total")
    catalog = load_document_catalog()
    assert_true(total == len(catalog) == 52, f"catalog list total mismatch: {total}")
    answer_text = list_response.get("answer", "")
    for document in catalog:
        expected = document.get("code") or document.get("title") or document.get("filename")
        assert_true(expected in answer_text, f"catalog list missing document: {expected}")
    print("Catalog answer tests: OK")


def test_rag_answers(vector_store, client) -> None:
    rag_questions = [
        "can you tell me scope of ZION-QT-08",
        "password policy requirements là gì?",
    ]
    for question in rag_questions:
        response = answer_chat(question, vector_store, client, debug=True)
        meta = response.get("metadata", {})
        assert_true(meta.get("answer_type") == "rag", f"RAG answer_type mismatch for {question}")
        assert_true(meta.get("retrieval_used") is True, f"retrieval flag missing for {question}")
        assert_true(meta.get("llm_used") is True, f"llm flag missing for {question}")
        assert_true(bool(response.get("sources")), f"sources missing for {question}")
    print("RAG answer tests: OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="SecureMind RAG CI smoke tests.")
    parser.add_argument("--catalog-only", action="store_true", help="Skip LLM-backed RAG questions.")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    test_catalog_core()
    if args.catalog_only:
        test_catalog_answers(None, None)
        return

    vector_store = load_vector_store()
    client = make_client()
    test_catalog_answers(vector_store, client)
    if not args.catalog_only:
        test_rag_answers(vector_store, client)


if __name__ == "__main__":
    main()
