# SecureMind RAG

Enterprise-ready RAG knowledge assistant for security, compliance, ISMS, policy, procedure, and governance documents.

## Overview

SecureMind RAG is an internal AI knowledge assistant for querying controlled security and governance documents. It combines SharePoint document sync, PDF ingestion, document intelligence, FAISS retrieval, and Qwen-compatible answer generation into one local-first workflow that can be exposed through CLI, web chat, Microsoft Teams, and AgentBase.

The project is designed for an internal competition demo, but the structure follows an enterprise pattern: documents stay in approved sources, the vector index is built before runtime, answers cite retrieved sources, and hosted services do not run SharePoint sync or ingestion on startup.

## Current Capabilities

* SharePoint sync from a scoped ISMS Portal folder.
* Local PDF ingestion from `papers/` or `sharepoint_downloads/`.
* Text cleaning, chunking, multilingual embeddings, and FAISS vector storage.
* Document intelligence catalog for document codes, process areas, section types, titles, and metadata hints.
* Hybrid retrieval using semantic search, document code detection, section keyword matching, query expansion, and catalog-aware ranking.
* Vietnamese and English answer support with concise source-grounded responses.
* Qwen no-thinking prompt controls and retry handling for empty final content.
* CLI chatbot for local use.
* Temporary ChatGPT-like web UI at `/` with chat API at `/chat`.
* Microsoft Teams Bot Framework endpoint at `/api/messages`.
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
| `rag_core.py` | Reusable retrieval and answer generation logic shared by every interface. |
| `chatbot.py` | Thin local CLI entrypoint. |
| `teams_bot.py` | aiohttp service for health checks, web chat, and Teams Bot Framework messages. |
| `predeploy_check.py` | Deployment-readiness validation script. |
| `eval_agent.py` | Lightweight evaluation runner for representative questions. |
| `teams_app/` | Microsoft Teams custom app manifest and icons. |
| `Dockerfile` | Container runtime for AgentBase or another approved host. |
| `.agents/skills/` | Project-scoped AgentBase operating skills. |

## SharePoint Sync Flow

`sharepoint_sync.py` reads configuration from `.env`, authenticates through Microsoft Graph, resolves the configured SharePoint site and folder, then downloads supported files into `SHAREPOINT_DOWNLOAD_DIR`.

The intended scoped sync is:

```text
SHAREPOINT_HOSTNAME -> SHAREPOINT_SITE_PATH -> SHAREPOINT_FOLDER_PATH -> SHAREPOINT_DOWNLOAD_DIR
```

When `SHAREPOINT_FOLDER_PATH` is set, the sync must start from that folder. If the folder cannot be resolved, the script stops instead of scanning the whole drive. This prevents noisy indexing and accidental ingestion of unrelated documents.

## Document Intelligence Layer

The document intelligence layer turns the vector database into a structured document catalog. `build_document_catalog.py` scans indexed chunks and writes `document_catalog.json` with best-effort metadata such as:

* Document code and title.
* Document type and likely process area.
* Section types such as scope, purpose, responsibility, procedure, control, or definition.
* Source files and pages.
* Likely user questions and search hints.

`rag_core.py` uses this catalog before and during retrieval so questions like "which document should I check for access request?" or "tell me the scope of ZION-QT-08" can prefer the right document and section before calling the LLM.

## Local CLI Chatbot

The CLI chatbot keeps the original local workflow:

```powershell
python chatbot.py
```

It loads the existing `vector_db/`, creates the LLM client, accepts terminal questions, prints the answer, and shows source file, page, and retrieval score details.

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

The web chat calls the same `rag_core.answer_question()` function as the CLI and Teams bot. It does not change retrieval behavior.

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
