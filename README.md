# SecureMind RAG

Enterprise-ready RAG knowledge assistant for security, compliance, ISMS, policy, procedure, and governance documents.

![Python](https://img.shields.io/badge/Python-3.10+-1f2937?logo=python)
![RAG](https://img.shields.io/badge/RAG-FAISS%20%2B%20Hybrid%20Retrieval-0f766e)
![Teams](https://img.shields.io/badge/Microsoft%20Teams-Bot%20Framework-6264a7)
![AgentBase](https://img.shields.io/badge/GreenNode-AgentBase-16a34a)
![Security](https://img.shields.io/badge/Security-Secrets%20Safe-b91c1c)

## At A Glance

SecureMind RAG turns approved ISMS and GRC documents into a source-grounded assistant that works locally, in a browser, in Microsoft Teams, and on GreenNode AgentBase.

| Area | Status |
| --- | --- |
| Knowledge source | SharePoint ISMS Portal folder or local PDFs |
| Retrieval | FAISS, document catalog routing, keyword + semantic hybrid search |
| Answering | Vietnamese/English, source-grounded, no model-generated source sections |
| Interfaces | CLI, web chat, Microsoft Teams Bot Framework |
| Runtime | Docker + AgentBase custom runtime |
| Safety | No secrets in repo, scoped SharePoint sync, predeploy/security checks |

Quick links:

* [Local run](#how-to-run-locally-on-windows)
* [SharePoint refresh](#one-command-local-knowledge-refresh)
* [Teams setup](README_TEAMS.md)
* [Deployment notes](DEPLOYMENT.md)
* [API contract](API_CONTRACT.md)
* [Chunking strategy](CHUNKING_STRATEGY.md)

## Overview

SecureMind RAG is an internal AI knowledge assistant for querying controlled security and governance documents. It combines SharePoint document sync, PDF ingestion, document intelligence, FAISS retrieval, and Qwen-compatible answer generation into one local-first workflow that can be exposed through CLI, web chat, Microsoft Teams, and AgentBase.

The project is designed for an internal competition demo, but the structure follows an enterprise pattern: documents stay in approved sources, the vector index is built before runtime, answers cite retrieved sources, and hosted services do not run SharePoint sync or ingestion on startup.

## Current Capabilities

* SharePoint sync from a scoped ISMS Portal folder.
* Local PDF ingestion from `papers/` or `sharepoint_downloads/`.
* Text cleaning, chunking, multilingual embeddings, and FAISS vector storage.
* Document intelligence catalog for document codes, process areas, section types, titles, and metadata hints.
* Context budget builder for safe prompt assembly, duplicate trimming, and token estimation.
* Hybrid retrieval using semantic search, document code detection, section keyword matching, query expansion, and catalog-aware ranking.
* Vietnamese and English answer support with concise source-grounded responses.
* Qwen no-thinking prompt controls and retry handling for empty final content.
* CLI chatbot for local use.
* Temporary ChatGPT-like web UI at `/` with chat API at `/chat`.
* Microsoft Teams Bot Framework endpoint at `/api/messages`.
* Optional GreenNode AgentBase Memory recall and safe fact storage for CLI chat.
* AgentBase deployment support with Docker packaging.
* Predeploy validation for vector DB, runtime files, configuration, and bot readiness.

## Architecture

```text
SharePoint ISMS Portal / Local Documents
|
v
SharePoint Sync / Local Ingestion
|
v
Text Cleaning & Chunking
|
v
Document Catalog & Metadata Intelligence
|
v
Embedding Generation
|
v
FAISS Vector Store
|
v
RAG Core
|
v
Interfaces:
* CLI Chatbot
* Web Chat UI
* Microsoft Teams Bot Endpoint
  |
  v
  Hosting:
* AgentBase Runtime
```

## Main Components

| File or folder | Purpose |
| --- | --- |
| `config.py` | Central runtime configuration loaded from environment variables. |
| `text_utils.py` | Text normalization and cleanup helpers used during ingestion. |
| `sharepoint_sync.py` | Microsoft Graph sync for downloading allowed SharePoint documents from the configured folder. |
| `ingest.py` | Loads documents, chunks text, generates embeddings, and builds `vector_db/`. |
| `build_document_catalog.py` | Builds `document_catalog.json` from the indexed document chunks. |
| `document_intelligence.py` | Document code, process area, section type, synonym, and catalog-ranking logic. |
| `memory.py` | Optional AgentBase Memory abstraction for recall and safe fact storage. |
| `context_budget.py` | Prompt context budgeting, safe chunk deduplication, and token estimation inspired by Open Notebook's context-builder pattern. |
| `rag_core.py` | Reusable retrieval and answer generation logic shared by every interface. |
| `chatbot.py` | Thin local CLI entrypoint. |
| `teams_bot.py` | aiohttp service for health checks, web chat, and Teams Bot Framework messages. |
| `predeploy_check.py` | Deployment-readiness validation script. |
| `eval_agent.py` | Lightweight evaluation runner for representative questions. |
| `teams_app/` | Microsoft Teams custom app manifest and icons for the current package. |
| `teams/` | Microsoft Teams manifest template and packaging notes. |
| `Dockerfile` | Container runtime for AgentBase or another approved host. |
| `.agents/skills/` | Project-scoped AgentBase operating skills. |

## Chunking Strategy

`ingest.py` uses document-aware chunking for ISMS, policy, standard, and procedure PDFs. It first preserves structure from headings, numbered sections, Vietnamese/English procedure headings, and bullet lists, then falls back to `RecursiveCharacterTextSplitter` for oversized sections.

Optional semantic chunking is available behind `SEMANTIC_CHUNKING_ENABLED=false` by default. See `CHUNKING_STRATEGY.md` for the full settings, tradeoffs, and rebuild workflow.

## SharePoint Sync Flow

`sharepoint_sync.py` reads configuration from `.env`, authenticates through Microsoft Graph, resolves the configured SharePoint site and folder, then downloads supported files into `SHAREPOINT_DOWNLOAD_DIR`.

Production treats SharePoint as the document source of truth. GitHub stores code and CI/CD workflow only; official PDFs should not be committed to the repository. The GitHub Actions workflow in `.github/workflows/sharepoint-knowledge-update.yml` can sync SharePoint, compare `knowledge_manifest.json` with `last_deployed_manifest.json`, rebuild `vector_db/` and `document_catalog.json` when needed, and update the existing AgentBase runtime.

See [SHAREPOINT_AUTO_UPDATE_PIPELINE.md](SHAREPOINT_AUTO_UPDATE_PIPELINE.md) for the full pipeline design, required GitHub Secrets, and troubleshooting notes.

The intended scoped sync is:

```text
SHAREPOINT_HOSTNAME -> SHAREPOINT_SITE_PATH -> SHAREPOINT_FOLDER_PATH -> SHAREPOINT_DOWNLOAD_DIR
```

When `SHAREPOINT_FOLDER_PATH` is set, the sync must start from that folder. If the folder cannot be resolved, the script stops instead of scanning the whole drive. This prevents noisy indexing and accidental ingestion of unrelated documents.

## One-Command Local Knowledge Refresh

Use the refresh script when SharePoint documents change and you want to sync, rebuild, and verify local knowledge in one command.

macOS/Linux:

```bash
source .venv/bin/activate
python scripts/local_refresh_knowledge.py --clean
```

Windows CMD:

```bat
.venv\Scripts\activate.bat
python scripts\local_refresh_knowledge.py --clean
```

Shortcuts:

```bash
python scripts/local_refresh_knowledge.py --skip-sync
python scripts/local_refresh_knowledge.py --clean --yes
```

Default behavior runs SharePoint sync, vector DB rebuild, document catalog rebuild, security audit, catalog smoke test, and full smoke test.

## Document Intelligence Layer

The document intelligence layer turns the vector database into a structured document catalog. `build_document_catalog.py` scans indexed chunks and writes `document_catalog.json` with best-effort metadata such as:

* Document code and title.
* Document type and likely process area.
* Section types such as scope, purpose, responsibility, procedure, control, or definition.
* Source files and pages.
* Likely user questions and search hints.

`rag_core.py` uses this catalog before and during retrieval so questions like "which document should I check for access request?" or "tell me the scope of ZION-QT-08" can prefer the right document and section before calling the LLM.

## Document Code Normalization

`document_code_utils.py` resolves the document code typed in a question against the
codes that actually exist in `document_catalog.json`:

* Full codes resolve to themselves. Both orderings can be distinct documents
  (for example `ZION-QT-04` and `QT-ZION-04`), so the exact order is respected.
* A reordered code resolves to the single existing ordering
  (`TC-ZION-13` → `ZION-TC-13`).
* Shorthand resolves when unique (`CS-01` → `ZION-CS-01`, `TC-13` → `ZION-TC-13`).
* When shorthand is ambiguous (for example `QT-04` matches both `QT-ZION-04` and
  `ZION-QT-04`), it does not guess — the bot asks for the full code.

The shared resolver also feeds query-side retrieval in `rag_core.py`, so shorthand
and reordered codes now scope retrieval to the right document.

## Catalog-Backed Metadata Answers

When a question contains both a resolvable document code and a metadata aspect,
`catalog_metadata.py` answers directly from `document_catalog.json` — before generic
RAG, with no retrieval and no LLM call. Aspects (Vietnamese + English): `author`,
`version_count`, `latest_version`, `reviewer`, `approver`, `effective_date`, `scope`,
`purpose`, `responsibility`. The response uses `answer_type="metadata"` and a source
card pointing at the matched document.

Examples:

```text
QT-04 có mấy version?          -> ambiguous code -> asks for the full code
ZION-QT-04 có mấy version?     -> answers the version-count aspect (not author/latest only);
                                  if no full version-history table exists in metadata it says so
author của ZION-QT-04 là ai?   -> uses the catalog author; if empty, falls back to
                                  document-scoped RAG (never invents an author)
scope của ZION-QT-08 là gì?    -> answers scope from catalog metadata
```

This respects the requested aspect (it no longer answers "latest version + author"
when you only asked for the version count). Normal questions without a document code
and aspect (for example "quy định về mật khẩu là gì?") still use the regular
RAG/hybrid retrieval path.

> This is not full Ask Mode yet. Multi-query planning, per-query evidence answers,
> and final synthesis remain a later phase on the roadmap.

## Context Budgeting

SecureMind RAG includes a lightweight context-budget layer inspired by the best parts of Open Notebook's context builder:

* Deduplicates selected chunks before they enter the final prompt.
* Enforces `MAX_CONTEXT_CHARS` without sending the entire corpus to the model.
* Estimates prompt tokens with `tiktoken` when available and a safe offline fallback when not.
* Adds safe debug metadata such as included chunk count, used characters, estimated tokens, and source labels.

The debug metadata is available through `POST /chat` with `"debug": true`. It never returns raw document chunks, raw prompts, environment values, API keys, or secrets.

## Local CLI Chatbot

The CLI chatbot keeps the original local workflow:

```powershell
python chatbot.py
```

It loads the existing `vector_db/`, creates the LLM client, accepts terminal questions, prints the answer, and shows source file, page, and retrieval score details.

When AgentBase Memory is enabled, the CLI also recalls relevant prior semantic memories before calling the LLM and stores only explicit non-sensitive facts or preferences after answering. If memory is disabled, misconfigured, unavailable, or the SDK call fails, the chatbot prints a short warning and continues with normal RAG-only behavior.

Exit commands:

```text
exit
quit
q
```

## Web Chat UI

`teams_bot.py` also exposes a small browser chat interface for demos:

```text
GET  /
POST /chat
```

The web chat calls the same `answer_chat()` answer path as the CLI and Teams bot. It does not change retrieval behavior.

### Web API Access Token

The web API can require a shared access token:

```text
REQUIRE_APP_ACCESS_TOKEN=false   # set true to enforce
APP_ACCESS_TOKEN=                # the shared token value
```

When `REQUIRE_APP_ACCESS_TOKEN=true`, these endpoints require the header
`X-App-Access-Token: <APP_ACCESS_TOKEN>`:

```text
POST /chat
GET  /documents
GET  /documents/count
```

`GET /`, `GET /health`, static assets, and Teams `POST /api/messages` stay public
(Teams keeps its Bot Framework JWT validation). A missing token returns `401`, an
invalid token returns `403`, both as clean JSON with no secret or env values. When
the flag is `false` (default) local development works without a token. The web UI
stores the token in `sessionStorage`, sends it on protected calls, and prompts for
it on `401`/`403`.

## Microsoft Teams Endpoint

The Bot Framework endpoint is:

```text
POST /api/messages
```

Microsoft Teams sends POST activities to this route. A browser GET request to `/api/messages` may return `405 Method Not Allowed`, which is expected.

The custom Teams app package is built from:

```text
teams_app/manifest.json
teams_app/color.png
teams_app/outline.png
```

For setup details, see `README_TEAMS.md`. A placeholder Teams app template is also available in `teams/`.

## AgentBase Deployment

SecureMind RAG can run as an AgentBase custom runtime. The deployment uses the prebuilt vector database and starts the bot service directly.

Start command:

```bash
python teams_bot.py
```

Runtime endpoints:

```text
GET  /health
GET  /
POST /chat
POST /api/messages
```

Important runtime artifacts:

* `vector_db/index.faiss`
* `vector_db/index.pkl`
* `document_catalog.json`

Do not run SharePoint sync or ingestion during app startup.

## AgentBase Memory

AgentBase Memory is optional and enhances the CLI chatbot without replacing local PDF retrieval or FAISS search.

Behavior:

* Recall: before answering, `chatbot.py` searches AgentBase Memory for records relevant to the current question and passes them to `rag_core.answer_question()` as a separate memory context.
* Remember: after answering, the chatbot stores only explicit non-sensitive facts, user preferences, or project context statements such as "remember that...", "I prefer...", or "project context: ...".
* Safety: the memory layer rejects likely secrets and does not store PDF chunks, retrieved document context, API keys, passwords, tokens, or raw confidential source text.
* Fallback: if any memory setting is missing, `greennode-agentbase` is not installed, or the memory service call fails, the chatbot continues with normal RAG-only behavior.

Required dependency:

```powershell
pip install -r requirements.txt
```

Environment placeholders:

```text
ENABLE_AGENTBASE_MEMORY=true
MEMORY_ID=your_agentbase_memory_id_here
MEMORY_STRATEGY_ID=your_agentbase_memory_strategy_id_here
MEMORY_ACTOR_ID=local-user
MEMORY_SEARCH_LIMIT=5
MEMORY_MAX_CONTEXT_CHARS=1200
```

`MEMORY_ID` is the AgentBase Memory container ID. `MEMORY_STRATEGY_ID` is the long-term memory strategy ID used to build the namespace `/strategies/{MEMORY_STRATEGY_ID}/actors/{MEMORY_ACTOR_ID}`. Keep GreenNode credentials in local `.env` or the AgentBase runtime environment; do not hardcode them.

Manual GreenNode setup still required:

* Create or identify a Memory store in GreenNode AgentBase.
* Create or identify a long-term memory strategy.
* Add the Memory ID and strategy ID to `.env`.
* Keep the repository private and do not commit real secrets.

## Docker Usage

Build:

```powershell
docker build --platform linux/amd64 -t securemind-rag:test .
```

Run locally:

```powershell
docker run --rm -p 8080:8080 --env-file .env --name securemind-rag-test securemind-rag:test
```

Health check:

```powershell
curl http://localhost:8080/health
```

## Configuration Overview

Use `.env.example` as the safe template. Real values belong in `.env` or the hosting platform's secret manager, not in documentation.

| Area | Variables |
| --- | --- |
| AI platform | `AI_PLATFORM_API_KEY`, `AI_PLATFORM_BASE_URL`, `AI_PLATFORM_MODEL` |
| RAG | `PAPERS_DIR`, `VECTOR_DB_DIR`, `EMBEDDING_MODEL`, `RETRIEVAL_K`, `RETRIEVAL_FETCH_K`, `MAX_CONTEXT_CHARS`, `ANSWER_LANGUAGE` |
| Generation | `MAX_TOKENS`, `SHOW_USAGE`, `DEBUG_RETRIEVAL` |
| SharePoint | `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `MS_AUTH_FLOW`, `SHAREPOINT_HOSTNAME`, `SHAREPOINT_SITE_PATH`, `SHAREPOINT_FOLDER_PATH`, `SHAREPOINT_DOWNLOAD_DIR`, `SHAREPOINT_FILE_EXTENSIONS` |
| Teams | `TEAMS_BOT_APP_ID`, `TEAMS_BOT_APP_PASSWORD`, `TEAMS_BOT_HOST`, `TEAMS_BOT_PORT`, `PORT` |
| AgentBase | `GREENNODE_CLIENT_ID`, `GREENNODE_CLIENT_SECRET` |
| AgentBase Memory | `ENABLE_AGENTBASE_MEMORY`, `MEMORY_ID`, `MEMORY_STRATEGY_ID`, `MEMORY_ACTOR_ID`, `MEMORY_SEARCH_LIMIT`, `MEMORY_MAX_CONTEXT_CHARS` |

## Security Notes

* Keep the repository private.
* Do not print or expose `.env` values in logs, screenshots, commits, or documentation.
* Treat `vector_db/` and `document_catalog.json` as sensitive because they are derived from internal documents.
* Do not commit `sharepoint_downloads/` raw documents.
* Do not run SharePoint sync or ingestion inside the hosted app startup path.
* Rotate any credential that was accidentally exposed during local testing or demos.

## Run Locally On Windows

Set up the environment:

```powershell
git clone https://github.com/ttkt12/securemind-rag.git
cd securemind-rag
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` from `.env.example`, then choose one document source.

For local PDFs:

```powershell
mkdir papers
copy C:\path\to\docs\*.pdf papers\
python ingest.py
python build_document_catalog.py
python chatbot.py
```

For SharePoint:

```powershell
python sharepoint_sync.py
python ingest.py
python build_document_catalog.py
python chatbot.py
```

Start the HTTP bot service:

```powershell
python teams_bot.py
```

Open:

```text
http://localhost:3978/
```

## Rebuild After SharePoint Documents Change

When SharePoint content changes, refresh the local artifacts in this order:

```powershell
python sharepoint_sync.py
python ingest.py
python build_document_catalog.py
python chatbot.py
```

For a hosted runtime, rebuild locally first, then provide the updated `vector_db/` and `document_catalog.json` through the approved deployment process.

## Roadmap

* Add stronger evaluation reports for retrieval quality and answer grounding.
* Improve metadata extraction for document owners, review dates, versions, and control mappings.
* Add permission-aware retrieval once enterprise identity integration is approved.
* Add admin monitoring, usage analytics, and audit reporting.
* Replace the temporary web UI with an approved production interface if required.
* Automate safe artifact packaging for AgentBase without including raw documents.
* Expand Teams app capabilities for team and group chat scopes after validation.
