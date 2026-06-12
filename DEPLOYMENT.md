# Agent Base Deployment Readiness

This guide describes a generic deployment path for hosting SecureMind RAG as a Bot Framework-compatible HTTP chatbot endpoint.

AgentBase deployment is prepared but has not been executed yet.

SecureMind RAG should be deployed as a Python service with this start command:

```bash
python3 teams_bot.py
```

The Docker image uses the same start command and exposes port `8080`.

The service exposes:

```text
GET /health
POST /api/messages
```

The public messaging endpoint for Microsoft Teams or an Agent Base routing layer should be:

```text
https://<public-url>/api/messages
```

## Required Environment Variables

LLM / AI platform:

```bash
AI_PLATFORM_API_KEY=...
AI_PLATFORM_BASE_URL=...
AI_PLATFORM_MODEL=...
```

RAG runtime:

```bash
VECTOR_DB_DIR=vector_db
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RETRIEVAL_K=4
RETRIEVAL_FETCH_K=20
MAX_TOKENS=8192
MAX_CONTEXT_CHARS=5000
SHOW_USAGE=false
DEBUG_RETRIEVAL=false
ANSWER_LANGUAGE=vi
```

Teams / Bot Framework:

```bash
TEAMS_BOT_APP_ID=...
TEAMS_BOT_APP_PASSWORD=...
TEAMS_BOT_HOST=0.0.0.0
PORT=8080
```

On hosted platforms, prefer `PORT` when the platform injects a dynamic port. The Dockerfile defaults `PORT=8080`. The bot falls back to `TEAMS_BOT_PORT`, then `3978`.

## Pre-Deployment Steps

1. Prepare documents locally using one of the supported flows:

```bash
python3 sharepoint_sync.py
```

or place PDFs directly in `papers/`.

2. Build the vector database:

```bash
python3 ingest.py
```

3. Run the readiness checker:

```bash
python3 predeploy_check.py
```

4. Start the bot locally:

```bash
python3 teams_bot.py
```

5. Verify health:

```bash
curl http://localhost:3978/health
```

## AgentBase Skills

AgentBase skills are installed project-scoped under `.agents/skills/`.

Start with `/agentbase-wizard` and validate before deploying. Use:

```text
/agentbase-wizard test validate
```

Use `/agentbase-deploy` only after local tests and validation pass.

Required AgentBase credentials must be set locally in `.env`:

```bash
GREENNODE_CLIENT_ID=...
GREENNODE_CLIENT_SECRET=...
```

Never commit `.env`.

## Vector DB Deployment Options

`vector_db/` is required at runtime. If it is not present, `teams_bot.py` stops with a clear error and instructs the operator to run ingestion or provide the vector database as a deployment artifact.

Option A - Prebuilt vector DB:

Run `python3 sharepoint_sync.py`, then `python3 ingest.py`, then upload or mount `vector_db/` as a private deployment artifact if Agent Base supports private artifacts or mounted storage.

This is preferred for demo stability because the bot can start quickly and does not need interactive SharePoint login during startup.

The default `.dockerignore` excludes `vector_db/` so it is not accidentally baked into an image or committed as build context. If Agent Base requires bundling the index inside the image for a private demo, make that as an explicit deployment-time decision and keep the repository rule of never committing `vector_db/`.

Option B - Build index during deployment:

Provide SharePoint environment variables, run sync and ingest as a pre-start job, then start `teams_bot.py`.

This is not recommended when startup time is limited or when SharePoint authentication requires interactive device login.

## What Not To Include In Git

Do not commit:

* `.env`
* API keys or client secrets
* `vector_db/`
* `sharepoint_downloads/`
* internal documents
* `token_cache.bin`
* virtual environments

These must be supplied by environment variables, private artifacts, mounted storage, or approved deployment secret management.

## SharePoint Sync Notes

`sharepoint_sync.py` is a separate local sync tool. The hosted bot does not run SharePoint sync automatically and does not require interactive SharePoint login at bot startup.

For demo deployment, build `vector_db/` before deployment and provide it to the runtime.

## Teams / Bot Framework Notes

IT/Admin must provide or configure:

* Teams Bot App ID
* Teams Bot App Password / Client Secret
* Azure Bot or Bot Channels Registration
* Microsoft Teams channel enabled
* Messaging endpoint: `https://<public-url>/api/messages`
* Permission to upload a custom Teams app for testing
* Production hosting target later, such as Agent Base, Azure App Service, or approved internal hosting
