# Chunking Strategy

SecureMind RAG uses document-aware chunking for ISMS, policy, standard, and procedure PDFs.

## Current Default

Semantic chunking is available but disabled by default:

```env
SEMANTIC_CHUNKING_ENABLED=false
```

The default ingestion pipeline is:

1. Load PDFs from `PAPERS_DIR`.
2. Clean PDF text while preserving paragraphs, bullets, and numbered sections.
3. Split each page into document sections using:
   - numbered headings such as `1.`, `1.1`, `2.3`
   - Vietnamese headings such as `Mục đích`, `Phạm vi`, `Định nghĩa`, `Trách nhiệm`, `Nội dung`, `Quy trình`
   - English headings such as `Scope`, `Purpose`, `Definition`, `Responsibility`, `Procedure`, `Policy`
4. Split oversized sections with `RecursiveCharacterTextSplitter`.
5. Store chunk metadata in FAISS.

## Default Settings

```env
CHUNK_SIZE=1500
CHUNK_OVERLAP=250
RETRIEVAL_K=6
RETRIEVAL_FETCH_K=40
MAX_CONTEXT_CHARS=7000
```

Runtime config may override these values in `.env`.

## Metadata

Ingested chunks include metadata such as:

- `source`
- `source_filename`
- `page`
- `page_number`
- `section_title`
- `document_code`
- `chunk_id`
- `chunking_strategy`

This helps retrieval prefer exact document codes, section-like matches, compact source cards, and catalog-aware answers.

## Optional Semantic Chunking

Semantic chunking can be enabled for experiments:

```env
SEMANTIC_CHUNKING_ENABLED=true
SEMANTIC_CHUNK_MIN_CHARS=700
SEMANTIC_CHUNK_MAX_CHARS=1500
SEMANTIC_CHUNK_SIMILARITY_THRESHOLD=0.55
```

When enabled, the pipeline:

1. Runs document-aware section splitting first.
2. Splits long sections into sentence/paragraph units.
3. Embeds adjacent units.
4. Cuts when cosine similarity drops below the threshold.
5. Merges small chunks to avoid tiny fragments.

Semantic chunking is slower because it performs extra embedding calls during ingestion. Keep it disabled for fast, stable competition demos unless retrieval quality requires experimentation.

## Rebuild Workflow

Run this whenever PDFs change or chunking settings change:

```bash
python ingest.py
python build_document_catalog.py
```

Then run:

```bash
python chatbot.py
```

AgentBase deployments must include the rebuilt `vector_db/` and `document_catalog.json`.
