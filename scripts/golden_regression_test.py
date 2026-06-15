"""Golden regression tests for SecureMind RAG answer quality.

These guard the high-value behaviors that previously regressed:
  * catalog count/list stay deterministic (no retrieval / no LLM, sources=[]),
  * document-metadata answers are grounded in document evidence and never echo
    auto-extracted catalog noise (a TOC number "4.4.2" as a version, or a
    change-log row as a scope),
  * shorthand codes resolve (or ask for clarification when ambiguous),
  * normal RAG still works with sources.

Assertions are robust (answer_type, retrieval/LLM flags, evidence flags,
contains/not-contains) rather than exact LLM text. Requires the vector store and
an LLM client (the last case is a normal RAG question).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from answer_engine import answer_chat
from catalog_service import load_document_catalog
from document_code_utils import load_catalog_codes
from rag_core import load_vector_store, make_client


class GoldenError(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise GoldenError(message)


def run() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    catalog = load_document_catalog()
    total = len(catalog)
    codes = set(load_catalog_codes())
    check(total > 0, "catalog is empty")
    print(f"Catalog document count: {total}")

    vector_store = load_vector_store()
    client = make_client()

    def ask(question, history=None):
        return answer_chat(question, vector_store, client, history=history, debug=True)

    passed = 0

    # 1. Catalog count -------------------------------------------------------
    r = ask("có tất cả bao nhiêu document trong AI Agent này?")
    m = r["metadata"]
    check(m.get("answer_type") == "catalog", "1 count: answer_type")
    check(m.get("retrieval_used") is False, "1 count: retrieval_used")
    check(m.get("llm_used") is False, "1 count: llm_used")
    check(r.get("sources") == [], "1 count: sources not empty")
    check(str(total) in r.get("answer", ""), f"1 count: answer missing total {total}")
    passed += 1

    # 2. Catalog list --------------------------------------------------------
    r = ask("kể tên tất cả tài liệu đó ra")
    m = r["metadata"]
    check(m.get("answer_type") == "catalog", "2 list: answer_type")
    check(r.get("sources") == [], "2 list: sources not empty")
    check(m.get("total_documents") == total, "2 list: total mismatch")
    passed += 1

    # 3. Version count must be evidence-based (no TOC 4.4.2, no author) -------
    if "ZION-QT-04" in codes:
        r = ask("ZION-QT-04 có mấy version?")
        m = r["metadata"]
        ans = r.get("answer", "")
        check(m.get("answer_type") == "metadata", "3 version: answer_type")
        check(m.get("metadata_source") == "document_evidence", "3 version: metadata_source")
        check(m.get("llm_used") is False, "3 version: llm_used")
        check(m.get("catalog_metadata_used") is False, "3 version: catalog_metadata_used")
        check("4.4.2" not in ans, "3 version: leaked TOC number 4.4.2")
        check("Tác giả" not in ans, "3 version: answered author instead of version")
        passed += 1

    # 4. Shorthand resolves uniquely in this corpus --------------------------
    if "ZION-QT-04" in codes and "QT-ZION-04" not in codes:
        r = ask("QT-04 có mấy version?")
        m = r["metadata"]
        check(m.get("answer_type") == "metadata", "4 shorthand: answer_type")
        check(m.get("normalized_document_code") == "ZION-QT-04", "4 shorthand: code resolution")
        check("4.4.2" not in r.get("answer", ""), "4 shorthand: leaked 4.4.2")
        passed += 1

    # 5. Scope must reject change-log text -----------------------------------
    if "ZION-QT-08" in codes:
        r = ask("scope của ZION-QT-08 là gì?")
        m = r["metadata"]
        check(m.get("answer_type") == "metadata", "5 scope: answer_type")
        check(m.get("metadata_source") == "document_evidence", "5 scope: metadata_source")
        check(
            "3.4 Update Scope 2 June 2026 Ta Thi Kieu Thi" not in r.get("answer", ""),
            "5 scope: returned change-log text",
        )
        passed += 1

    # 6. Author evidence-based or not found (no hallucination) ----------------
    if "ZION-QT-04" in codes:
        r = ask("author của ZION-QT-04 là ai?")
        m = r["metadata"]
        check(m.get("answer_type") == "metadata", "6 author: answer_type")
        check(m.get("query_aspect") == "author", "6 author: aspect")
        check("Xem xét và phê duyệt" not in r.get("answer", ""), "6 author: returned a role phrase")
        passed += 1

    # 7. Effective date evidence-based or not found --------------------------
    if "ZION-CS-01" in codes:
        r = ask("ngày hiệu lực của ZION-CS-01 là ngày nào?")
        m = r["metadata"]
        check(m.get("answer_type") == "metadata", "7 effective_date: answer_type")
        check(m.get("query_aspect") == "effective_date", "7 effective_date: aspect")
        passed += 1

    # 8. Normal RAG unchanged ------------------------------------------------
    r = ask("quy định về mật khẩu là gì?")
    m = r["metadata"]
    check(m.get("answer_type") == "rag", "8 rag: answer_type")
    check(m.get("retrieval_used") is True, "8 rag: retrieval_used")
    check(m.get("llm_used") is True, "8 rag: llm_used")
    check(bool(r.get("sources")), "8 rag: sources missing")
    passed += 1

    print(f"Golden regression tests: OK ({passed} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
