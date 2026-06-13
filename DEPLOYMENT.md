# SecureMind RAG Deployment

This guide covers deployment readiness for SecureMind RAG as an internal RAG chatbot service with CLI, web chat, and Microsoft Teams Bot Framework interfaces.

AgentBase deployment is available for this project and has been used for the internal demo runtime.

## Runtime Shape

Start command:

```bash
python teams_bot.py
```

The service binds to `0.0.0.0` and uses `PORT` when provided by the hosting platform. If `PORT` is not set, it falls back to `TEAMS_BOT_PORT`, then `3978`.

Runtime endpoints:

```text
GET  /health
GET  /
POST /chat
POST /api/messages
```

Endpoint purposes:

| Endpoint | Purpose |
| --- | --- |
| `/health` | Health check endpoint for AgentBase or another hosting platform. |
| `/` | Temporary web chat UI for browser demos. |
| `/chat` | Web chat JSON API that calls the same RAG core as the CLI and Teams bot. |
| `/api/messages` | Microsoft Teams / Bot Framework messaging endpoint. |

Calling `/api/messages` with GET may return `405 Method Not Allowed`. This is expected because Microsoft Teams sends Bot Framework activities as POST requests.

## Current AgentBase Demo Endpoint

Health URL:

```text
https://endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn/health
```

Web UI:

```text
https://endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn/
```

Web chat API:

```text
https://endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn/chat
```

Teams / Bot Framework messaging endpoint:

```text
https://endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn/api/messages
```

Teams app package:

```text
securemind-rag-teams-app.zip
```

If Teams custom app upload is blocked, send the package to IT/admin and ask them to upload it to the Teams app catalog. If the Azure Bot or Teams bot registration still needs endpoint configuration, set the messaging endpoint to the `/api/messages` URL above.

## Required Runtime Artifacts

The hosted app starts from prebuilt artifacts. Do not run SharePoint sync or ingestion during app startup.

Required:

```text
vector_db/index.faiss
vector_db/index.pkl
document_catalog.json
```

`vector_db/` is required at runtime. `document_catalog.json` should be rebuilt whenever documents change so catalog-aware retrieval stays aligned with the FAISS index.

## Rebuild Workflow

When SharePoint or local documents change, rebuild locally in this order:

```bash
python sharepoint_sync.py
python ingest.py
python build_document_catalog.py
python chatbot.py
```

For local-only PDFs, place files in `papers/` and skip `sharepoint_sync.py`.

After rebuilding, provide the updated `vector_db/` and `document_catalog.json` through the approved internal deployment or artifact process.

## Predeploy Validation

Run:

```bash
python predeploy_check.py
```

The checker validates:

* Required runtime environment variables are configured.
* `vector_db/index.faiss` exists.
* `vector_db/index.pkl` exists.
* `rag_core` imports.
* The vector store loads.
* The LLM client can be created.
* `teams_bot.py` imports.

## Docker Usage

Build:

```bash
docker build --platform linux/amd64 -t securemind-rag:test .
```

Run locally:

```bash
docker run --rm -p 8080:8080 --env-file .env --name securemind-rag-test securemind-rag:test
```

Health check:

```bash
curl http://localhost:8080/health
```

The Docker image uses the same `python teams_bot.py` startup path and expects the runtime artifacts to be available inside the image or deployment artifact.

## Environment Variables

Do not place real values in documentation. Use `.env.example` as the template and provide real values through `.env` locally or hosting secrets in production-like environments.

AI platform:

```text
AI_PLATFORM_API_KEY
AI_PLATFORM_BASE_URL
AI_PLATFORM_MODEL
```

RAG:

```text
PAPERS_DIR
VECTOR_DB_DIR
EMBEDDING_MODEL
RETRIEVAL_K
RETRIEVAL_FETCH_K
MIN_RELEVANCE_SCORE
MAX_TOKENS
MAX_CONTEXT_CHARS
SHOW_USAGE
DEBUG_RETRIEVAL
ANSWER_LANGUAGE
```

Microsoft Graph / SharePoint:

```text
MS_TENANT_ID
MS_CLIENT_ID
MS_CLIENT_SECRET
MS_AUTH_FLOW
MS_REDIRECT_URI
SHAREPOINT_HOSTNAME
SHAREPOINT_SITE_PATH
SHAREPOINT_FOLDER_PATH
SHAREPOINT_DOWNLOAD_DIR
SHAREPOINT_FILE_EXTENSIONS
```

Teams / Bot Framework:

```text
TEAMS_BOT_APP_ID
TEAMS_BOT_APP_PASSWORD
TEAMS_BOT_HOST
TEAMS_BOT_PORT
PORT
```

AgentBase:

```text
GREENNODE_CLIENT_ID
GREENNODE_CLIENT_SECRET
```

## AgentBase Notes

Use `/agentbase-deploy` only when a deployment or redeployment is intentionally required. Do not run it as part of normal documentation updates or Git pushes.

Deployment settings:

```text
Start command: python teams_bot.py
Health endpoint: /health
Web UI: /
Web chat API: /chat
Teams/Bot Framework endpoint: /api/messages
Runtime artifact: vector_db/ and document_catalog.json
```

## Microsoft Teams Notes

Teams app package files:

```text
teams_app/manifest.json
teams_app/color.png
teams_app/outline.png
```

The zip package must contain these files at the root of the archive, not inside a parent folder.

IT/Admin may need to:

* Allow custom app upload for the user or tenant.
* Upload the app to the Teams app catalog.
* Configure the Azure Bot messaging endpoint.
* Enable the Microsoft Teams channel for the bot.

Message to IT/Admin:

```text
Please configure the Teams/Azure Bot messaging endpoint to:
https://endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn/api/messages

The Teams app package is:
securemind-rag-teams-app.zip
```

## Security And Artifact Handling

* Keep the repository private.
* Do not print or expose `.env` values.
* Do not include API keys, Microsoft secrets, Teams bot passwords, or GreenNode secrets in docs or logs.
* Do not commit `sharepoint_downloads/` raw documents.
* Treat `vector_db/` and `document_catalog.json` as sensitive derived artifacts.
* Do not run SharePoint sync during hosted app startup.
* Do not run ingestion during hosted app startup.
* Rotate secrets if they are accidentally exposed.
