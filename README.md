# SecureMind RAG

Enterprise-ready RAG knowledge assistant for security, compliance, ISMS, policy, procedure, and governance documents.

## Overview

SecureMind RAG is an internal AI knowledge assistant that helps users query security, compliance, ISMS, policy, procedure, standard, and governance documents using Retrieval-Augmented Generation.

The system supports local development, SharePoint document sync, a Microsoft Teams chatbot interface, and AgentBase deployment readiness.

## Current Capabilities

* Local document ingestion
* SharePoint document sync via Microsoft Graph delegated access
* Text cleaning and chunking
* Multilingual embeddings
* FAISS vector database
* Hybrid retrieval using semantic search, document code detection, section keyword matching, and structured metadata parsing
* Vietnamese and English Q&A support
* Source traceability with file name, page number, and retrieval score
* CLI chatbot for local testing
* Microsoft Teams chatbot endpoint through Bot Framework
* Docker packaging for deployment
* AgentBase deployment readiness
* Pre-deployment validation script
* Project-scoped AgentBase skills

## Architecture

```text
SharePoint / Local Documents
↓
Document Sync / Local Ingestion
↓
Text Cleaning & Chunking
↓
Embedding Generation
↓
FAISS Vector Store
↓
RAG Core
↓
Interfaces:

* CLI Chatbot
* Microsoft Teams Bot Endpoint
  ↓
  Future Hosting:
* AgentBase
* Approved enterprise hosting platform
```

## Main Components

* `config.py` - environment and runtime configuration
* `text_utils.py` - PDF text cleaning utilities
* `ingest.py` - document ingestion and vector database creation
* `rag_core.py` - reusable RAG retrieval and answering logic
* `chatbot.py` - local CLI chatbot
* `sharepoint_sync.py` - Microsoft Graph SharePoint document sync
* `teams_bot.py` - Microsoft Teams Bot Framework HTTP endpoint
* `predeploy_check.py` - deployment readiness validation
* `Dockerfile` - container packaging
* `.dockerignore` - Docker build exclusions
* `DEPLOYMENT.md` - deployment notes
* `.env.example` - safe configuration template
* `.agents/skills/` - project-scoped AgentBase skills

## Local Development Workflow

1. Configure `.env`.
2. Sync documents from SharePoint or add local PDFs.
3. Run document ingestion.
4. Test with CLI chatbot.
5. Start Teams bot endpoint locally.
6. Validate before AgentBase deployment.
7. Push back to GitHub to continue on another machine.

Common commands:

```bash
python3 sharepoint_sync.py
python3 ingest.py
python3 chatbot.py
python3 teams_bot.py
python3 predeploy_check.py
```

## SharePoint Integration

SharePoint sync uses Microsoft Graph delegated permissions. It reads documents that the signed-in user is allowed to access and downloads them into `sharepoint_downloads/`.

Downloaded documents are local working files and should not normally be committed. After sync, set `PAPERS_DIR=sharepoint_downloads` in `.env` to ingest the synced documents.

Do not place real SharePoint URLs, tenant IDs, app IDs, secrets, or internal document contents in documentation.

## Microsoft Teams Chatbot Interface

`teams_bot.py` exposes:

```text
GET /health
POST /api/messages
```

The Teams bot reuses `rag_core.answer_question()` and is intended to work as a conversational chatbot in Microsoft Teams.

Microsoft Teams requires a public HTTPS messaging endpoint. For local testing, a tunnel may be used. For stable deployment, use AgentBase or another approved enterprise hosting platform.

## AgentBase Deployment Readiness

The project includes Docker packaging and deployment readiness checks. AgentBase can host the bot and provide a stable messaging endpoint.

Preferred demo strategy:

* Build or provide `vector_db/` before runtime.
* Start with `python3 teams_bot.py`.

`vector_db/` is required at runtime unless the platform builds the index before startup.

Start command:

```bash
python3 teams_bot.py
```

Health endpoint:

```text
/health
```

Messaging endpoint:

```text
/api/messages
```

## Docker

Build:

```bash
docker build --platform linux/amd64 -t securemind-rag:test .
```

Local test with `vector_db` mounted:

```bash
docker run --rm \
  -p 8080:8080 \
  --env-file .env \
  -v "$PWD/vector_db:/app/vector_db:ro" \
  --name securemind-rag-test \
  securemind-rag:test
```

Health check:

```bash
curl http://localhost:8080/health
```

## Configuration

| Group | Environment variables |
| --- | --- |
| AI Platform | `AI_PLATFORM_API_KEY`, `AI_PLATFORM_BASE_URL`, `AI_PLATFORM_MODEL` |
| RAG | `PAPERS_DIR`, `VECTOR_DB_DIR`, `EMBEDDING_MODEL`, `RETRIEVAL_K`, `RETRIEVAL_FETCH_K`, `MAX_CONTEXT_CHARS`, `ANSWER_LANGUAGE` |
| SharePoint | `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `MS_AUTH_FLOW`, `SHAREPOINT_HOSTNAME`, `SHAREPOINT_SITE_PATH`, `SHAREPOINT_FOLDER_PATH`, `SHAREPOINT_DOWNLOAD_DIR` |
| Teams | `TEAMS_BOT_APP_ID`, `TEAMS_BOT_APP_PASSWORD`, `TEAMS_BOT_HOST`, `TEAMS_BOT_PORT`, `PORT` |
| AgentBase | `GREENNODE_CLIENT_ID`, `GREENNODE_CLIENT_SECRET` |

Use `.env.example` as the safe template. Do not place real values in documentation.

## Security Notes

* This repository is intended to remain private.
* `.env` contains sensitive credentials.
* Committing `.env` is only acceptable here because this is an internal competition workflow.
* In production, `.env` must not be committed.
* Internal documents and SharePoint downloads should not normally be committed.
* `vector_db/` may contain embedded information from documents and should be handled as sensitive.
* Rotate secrets after demos or internal testing if they were exposed.

## Repository Structure

```text
.
├── .agents/
├── papers/
├── config.py
├── text_utils.py
├── ingest.py
├── rag_core.py
├── chatbot.py
├── sharepoint_sync.py
├── teams_bot.py
├── predeploy_check.py
├── Dockerfile
├── .dockerignore
├── requirements.txt
├── .env.example
├── DEPLOYMENT.md
└── README.md
```

## Windows Continuation

Clone and set up:

```powershell
git clone <repo-url>
cd securemind-rag
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python chatbot.py
```

If `vector_db/` is not available:

```powershell
python sharepoint_sync.py
python ingest.py
python chatbot.py
```

## Roadmap

* Improve evaluation suite
* Improve structured metadata extraction
* Improve document permission awareness
* Optimize vector DB artifact handling for AgentBase
* Add admin monitoring and usage logging
* Add stable production hosting
* Improve Teams app packaging

## License

License to be defined.
