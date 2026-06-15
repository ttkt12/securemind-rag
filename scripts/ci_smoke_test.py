from __future__ import annotations

import argparse
import json
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
    catalog = load_document_catalog()
    catalog_count = len(catalog)
    history = [
        {"role": "user", "content": count_question},
        {
            "role": "assistant",
            "content": f"Hiện tại AI Agent này có {catalog_count} tài liệu duy nhất trong document catalog.",
        },
    ]
    assert_true(catalog_count > 0, "catalog is empty")
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
    assert_true(total == len(catalog), f"catalog list total mismatch: {total}")
    answer_text = list_response.get("answer", "")
    for document in catalog:
        expected = document.get("code") or document.get("title") or document.get("filename")
        assert_true(expected in answer_text, f"catalog list missing document: {expected}")
    print("Catalog answer tests: OK")


def test_rag_answers(vector_store, client) -> None:
    rag_questions = [
        "password policy requirements là gì?",
        "quy định về mật khẩu là gì?",
    ]
    for question in rag_questions:
        response = answer_chat(question, vector_store, client, debug=True)
        meta = response.get("metadata", {})
        assert_true(meta.get("answer_type") == "rag", f"RAG answer_type mismatch for {question}")
        assert_true(meta.get("retrieval_used") is True, f"retrieval flag missing for {question}")
        assert_true(meta.get("llm_used") is True, f"llm flag missing for {question}")
        assert_true(bool(response.get("sources")), f"sources missing for {question}")
    print("RAG answer tests: OK")


def test_document_code_normalization() -> None:
    from document_code_utils import load_catalog_codes, normalize_document_code, resolve_code

    codes = set(load_catalog_codes())
    assert_true(bool(codes), "catalog has no document codes")

    # Full codes resolve to themselves; both orderings are distinct documents.
    for code in ("ZION-QT-04", "QT-ZION-04", "ZION-CS-01", "ZION-QT-08"):
        if code in codes:
            assert_true(normalize_document_code(code) == code, f"full code did not resolve: {code}")

    # Reordered full code resolves to the single existing ordering.
    if "ZION-TC-13" in codes and "TC-ZION-13" not in codes:
        assert_true(
            normalize_document_code("TC-ZION-13") == "ZION-TC-13",
            "reordered TC code did not resolve",
        )

    # Unique shorthand resolves; ambiguous shorthand returns None + candidates.
    if "ZION-CS-01" in codes and "CS-ZION-01" not in codes:
        assert_true(normalize_document_code("CS-01") == "ZION-CS-01", "shorthand CS-01 did not resolve")
    if {"QT-ZION-04", "ZION-QT-04"} <= codes:
        resolved, candidates = resolve_code("QT-04")
        assert_true(resolved is None, "ambiguous QT-04 should not resolve to one code")
        assert_true(len(candidates) >= 2, "ambiguous QT-04 should list candidates")

    # Unknown code returns None.
    assert_true(normalize_document_code("ZZ-QQ-99") is None, "unknown code should be None")
    print("Document code normalization tests: OK")


def test_metadata_answers(vector_store, client, catalog_only: bool = False) -> None:
    from document_code_utils import load_catalog_codes

    codes = set(load_catalog_codes())

    def meta(question: str) -> dict:
        return answer_chat(question, vector_store, client, debug=True)

    if "ZION-QT-04" in codes:
        # Version count: only latest_version is known -> careful message, no LLM,
        # must not leak author or invent a count.
        response = meta("ZION-QT-04 có mấy version?")
        m = response.get("metadata", {})
        answer = response.get("answer", "")
        assert_true(m.get("answer_type") == "metadata", "version_count not routed to metadata")
        assert_true(m.get("query_aspect") == "version_count", "version_count aspect mismatch")
        assert_true(m.get("retrieval_used") is False, "version_count used retrieval")
        assert_true(m.get("llm_used") is False, "version_count used LLM")
        assert_true("Tác giả" not in answer, "version_count leaked author")
        assert_true("phiên bản" in answer.lower(), "version_count message missing")

        # Latest version is answerable from the catalog with a source card.
        response = meta("ZION-QT-04 version mới nhất là gì?")
        m = response.get("metadata", {})
        assert_true(m.get("answer_type") == "metadata", "latest_version not metadata")
        assert_true(m.get("query_aspect") == "latest_version", "latest_version aspect mismatch")
        assert_true(m.get("normalized_document_code") == "ZION-QT-04", "latest_version code mismatch")
        assert_true(bool(response.get("sources")), "metadata answer missing source card")

    if {"QT-ZION-04", "ZION-QT-04"} <= codes:
        # Ambiguous shorthand -> deterministic clarification (still metadata).
        response = meta("QT-04 có mấy version?")
        m = response.get("metadata", {})
        answer = response.get("answer", "")
        assert_true(m.get("answer_type") == "metadata", "ambiguous code not metadata")
        assert_true(m.get("retrieval_used") is False, "ambiguous code used retrieval")
        assert_true("QT-ZION-04" in answer and "ZION-QT-04" in answer, "ambiguous answer missing candidates")

    if "ZION-QT-08" in codes:
        response = meta("scope của ZION-QT-08 là gì?")
        m = response.get("metadata", {})
        assert_true(m.get("answer_type") == "metadata", "scope not metadata")
        assert_true(m.get("query_aspect") == "scope", "scope aspect mismatch")

    if "ZION-CS-01" in codes:
        response = meta("ngày hiệu lực của ZION-CS-01 là ngày nào")
        m = response.get("metadata", {})
        assert_true(m.get("answer_type") == "metadata", "effective_date not metadata")
        assert_true(m.get("query_aspect") == "effective_date", "effective_date aspect mismatch")

    if catalog_only:
        print("Metadata answer tests (catalog-only): OK")
        return

    if "ZION-QT-04" in codes:
        # author is empty in the catalog -> fall back to document-scoped RAG.
        response = meta("author của ZION-QT-04 là ai?")
        m = response.get("metadata", {})
        assert_true(m.get("answer_type") == "rag", "author fallback should use RAG")
        assert_true(m.get("query_aspect") == "author", "author fallback lost aspect")
        assert_true(m.get("retrieval_used") is True, "author fallback should retrieve")
    print("Metadata answer tests: OK")


def test_labeled_dataset(vector_store, client) -> None:
    """Assert the deterministic (no-LLM) entries in test_questions.json.

    Only checks cheap, stable signals (answer_type, retrieval_used, llm_used,
    normalized_document_code, must_contain/must_not_contain) — never exact LLM
    text. RAG entries (expect_llm_used=true) are exercised by test_rag_answers and
    eval_agent instead, so they are skipped here.
    """
    from document_code_utils import load_catalog_codes

    path = PROJECT_ROOT / "test_questions.json"
    if not path.exists():
        print("Labeled dataset: test_questions.json missing; skipped")
        return
    entries = json.loads(path.read_text(encoding="utf-8"))
    codes = set(load_catalog_codes())

    checked = 0
    for item in entries:
        if item.get("expect_llm_used") is not False:
            continue  # deterministic-only here
        expected_code = item.get("expected_code")
        if expected_code and expected_code not in codes:
            continue  # catalog no longer has this code; skip rather than fail
        label = item.get("category", item["question"])
        response = answer_chat(item["question"], vector_store, client, debug=True)
        meta = response.get("metadata", {})
        answer = response.get("answer", "")
        assert_true(
            meta.get("answer_type") == item["expected_answer_type"],
            f"[{label}] answer_type {meta.get('answer_type')!r} != {item['expected_answer_type']!r}",
        )
        assert_true(meta.get("retrieval_used") == item["expect_retrieval_used"], f"[{label}] retrieval_used")
        assert_true(meta.get("llm_used") == item["expect_llm_used"], f"[{label}] llm_used")
        if expected_code:
            assert_true(
                meta.get("normalized_document_code") == expected_code,
                f"[{label}] normalized_document_code {meta.get('normalized_document_code')!r} != {expected_code!r}",
            )
        for needle in item.get("must_contain", []):
            assert_true(needle in answer, f"[{label}] answer missing {needle!r}")
        for needle in item.get("must_not_contain", []):
            assert_true(needle not in answer, f"[{label}] answer should not contain {needle!r}")
        checked += 1

    print(f"Labeled dataset deterministic checks: OK ({checked} cases)")


def main() -> None:
    parser = argparse.ArgumentParser(description="SecureMind RAG CI smoke tests.")
    parser.add_argument("--catalog-only", action="store_true", help="Skip LLM-backed RAG questions.")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    test_catalog_core()
    test_document_code_normalization()
    if args.catalog_only:
        test_catalog_answers(None, None)
        test_metadata_answers(None, None, catalog_only=True)
        test_labeled_dataset(None, None)
        return

    vector_store = load_vector_store()
    client = make_client()
    test_catalog_answers(vector_store, client)
    test_metadata_answers(vector_store, client, catalog_only=False)
    test_labeled_dataset(vector_store, client)
    test_rag_answers(vector_store, client)


if __name__ == "__main__":
    main()
