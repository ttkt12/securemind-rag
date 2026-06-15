# Smart RAG — Evidence-Based Metadata Answers

SecureMind RAG answers document-specific metadata questions from **actual document
evidence**, not from auto-extracted catalog fields.

## Source-of-truth rule

`document_catalog.json` is the source of truth **only** for:

1. document **count**,
2. document **list**,
3. **locating** a candidate document (code / title / filename).

`document_catalog.json` is **NOT** the source of truth for:

- version / latest version / version count
- author / reviewer / approver
- effective date
- scope / purpose / responsibility

For those aspects the answer must come from retrieved document evidence. The
catalog's auto-extracted fields are frequently wrong — for example a
table-of-contents number (`4.4.2`) was stored as `latest_version`, and a
change-log row (`3.4 Update Scope 2 June 2026 ...`) was stored as `scope_summary`.

## Flow

1. `intent_router` handles `catalog_count` / `catalog_list` (deterministic, no
   retrieval, no LLM, `sources=[]`).
2. `catalog_metadata.build_metadata_answer` detects the metadata **aspect** and
   resolves the **document code** (`document_code_utils`):
   - ambiguous shorthand (both code orderings exist) → ask for the full code
     (`metadata_source="catalog"`, no retrieval);
   - resolved code → hand off to evidence retrieval.
3. `document_evidence_metadata.answer_document_metadata_from_evidence`:
   - gathers the matched document's chunks (`vector_store.docstore`),
   - prefers keyword / section / version-table evidence over generic vector search,
   - extracts the answer with rule-based parsing (no LLM),
   - returns clear "insufficient evidence" text instead of guessing.
4. Anything else → normal RAG / hybrid retrieval (unchanged).

## Response metadata

Evidence-based metadata answers carry:

- `answer_type = "metadata"`
- `metadata_source = "document_evidence"`
- `normalized_document_code`, `query_aspect`
- `retrieval_used = true`
- `llm_used = false` (rule-based extraction; no synthesis today)
- `evidence_verified = true|false`
- `catalog_metadata_used = false`

## Aspect behavior

- **version_count** — count unique versions from the document's version-control
  table (rows with a year-bearing date or an author; TOC/procedure numbers like
  `4.4.2` / `5.1` are excluded). If only one version is found, say so; if none,
  say version info was not found. Never answers author.
- **latest_version** — newest version from the same table; never the catalog field.
- **scope / purpose** — the real section text; rejects table-of-contents (dotted
  leaders) and change-log rows (`Update Scope`, `N.N <verb> <year>`).
- **effective_date** — parsed from the document header label.
- **author / reviewer / approver** — from the version-control table (clean names)
  or an explicit `Label: Name` field; role/column-header phrases are rejected;
  "not found" when absent.

## Insufficient-evidence messages

- generic: `Mình chưa tìm thấy thông tin này trong tài liệu đã index.`
- version: `Mình chưa tìm thấy thông tin version trong tài liệu đã index.`
- scope: `Mình chưa tìm thấy nội dung phạm vi áp dụng rõ ràng trong tài liệu đã index.`

## Regression protection

- `scripts/golden_regression_test.py` — golden answer-quality checks (needs the
  vector store): catalog count/list, the `4.4.2` version guard, the scope
  change-log guard, shorthand resolution, author no-hallucination, normal RAG.
- `scripts/ci_smoke_test.py` — catalog-only mode validates count/list/code
  normalization without an index; full mode adds the evidence-metadata and RAG
  checks. `test_questions.json` is the labeled dataset (entries needing evidence
  are marked `requires_vector_store` and skipped in catalog-only CI).

## Limitations / future work

- Extraction is rule-based; very unusual document layouts may fall back to
  "insufficient evidence" rather than a wrong answer.
- Full **Ask Mode** (multi-query planning, per-query evidence, LLM synthesis with
  citations) remains future work. When added, `llm_used=true` answers must still
  cite evidence and respect the source-of-truth rule above.
