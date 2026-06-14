# SharePoint Auto-Update Pipeline

SecureMind RAG treats SharePoint as the single source of truth for official documents. GitHub stores source code, workflow files, and non-secret deployment metadata only. PDFs and other raw SharePoint documents must not be committed to GitHub.

## Architecture

```text
GitHub Actions schedule / manual dispatch / code push
↓
Microsoft Graph app-only auth
↓
Sync configured SharePoint folder into sharepoint_downloads/
↓
Compute knowledge_manifest.json from SharePoint metadata + file hashes
↓
Compare with last_deployed_manifest.json
↓
If changed or knowledge code changed:
  rebuild vector_db
  rebuild document_catalog.json
  run smoke tests
  build Docker image
  push image to AgentBase Container Registry
  update existing AgentBase runtime
  verify production endpoints
↓
If unchanged:
  print "Knowledge base is up to date."
```

## Source Of Truth

- SharePoint stores official ISMS, security, compliance, policy, procedure, and governance documents.
- GitHub stores application code and CI/CD workflow only.
- `sharepoint_downloads/` is a temporary sync folder.
- `document_catalog.json` and `vector_db/` are generated knowledge artifacts.
- Raw downloaded documents are excluded from Docker and Git by default.

## Required Microsoft Graph Permissions

Use an app registration or service principal with application permissions suitable for the target SharePoint site:

- `Sites.Read.All` or a narrower site-scoped equivalent approved by IT.
- `Files.Read.All` if required by the tenant policy.
- Admin consent granted for application permissions.

For least privilege, ask IT for site-scoped Graph access to the ISMS Portal document library if possible.

## Required GitHub Secrets

Microsoft / SharePoint:

- `MS_TENANT_ID`
- `MS_CLIENT_ID`
- `MS_CLIENT_SECRET`
- `SHAREPOINT_SITE_ID`
- `SHAREPOINT_DRIVE_ID`
- `SHAREPOINT_FOLDER_PATH`
- Optional fallback: `SHAREPOINT_HOSTNAME`, `SHAREPOINT_SITE_PATH`

GreenNode / AgentBase:

- `GREENNODE_CLIENT_ID`
- `GREENNODE_CLIENT_SECRET`
- `AGENTBASE_RUNTIME_ID`
- `AGENTBASE_ENDPOINT_URL`
- Optional: `AGENTBASE_RUNTIME_FLAVOR`

AI Platform runtime:

- `AI_PLATFORM_API_KEY`
- `AI_PLATFORM_BASE_URL`
- `AI_PLATFORM_MODEL`

Teams runtime, if the Teams endpoint is enabled:

- `TEAMS_BOT_APP_ID`
- `TEAMS_BOT_APP_PASSWORD`

Do not store `.env` in GitHub. Do not print or echo secret values in workflow logs.

## Change Detection

The workflow creates `knowledge_manifest.json` from:

- SharePoint drive item id
- filename
- relative path
- size
- last modified time
- `eTag` / `cTag`
- SHA-256 hash of downloaded file

It compares this with `last_deployed_manifest.json`.

- SharePoint manifest changed: rebuild knowledge base and deploy.
- Knowledge pipeline code changed: rebuild knowledge base and deploy.
- UI/Docker-only code changed: build and deploy without necessarily rebuilding vector DB.
- No changes: skip deploy and print `Knowledge base is up to date.`

`last_deployed_manifest.json` contains non-secret metadata only. The workflow commits it after a successful rebuild/deploy so the next run can compare deterministically.

## Manual Trigger

In GitHub:

1. Open the repository.
2. Go to `Actions`.
3. Select `SharePoint knowledge update`.
4. Click `Run workflow`.
5. Set `force_rebuild=true` if you want to rebuild even when the manifest appears unchanged.

## Force Rebuild

Use the manual workflow input:

```text
force_rebuild=true
```

This forces:

- SharePoint sync
- vector DB rebuild
- document catalog rebuild
- smoke tests
- Docker build
- AgentBase runtime update
- production verification

## Generated Files

Generated locally or in CI:

- `sharepoint_downloads/`
- `sharepoint_downloads/sharepoint_manifest.json`
- `knowledge_manifest.json`
- `last_deployed_manifest.json`
- `document_catalog.json`
- `vector_db/index.faiss`
- `vector_db/index.pkl`

Do not commit:

- `.env`
- raw files under `sharepoint_downloads/`
- token caches
- API keys, passwords, or credentials

## Local Development Fallback

Local development can still use a local folder:

```env
PAPERS_DIR=papers
```

Production CI should use:

```env
PAPERS_DIR=sharepoint_downloads
SHAREPOINT_DOWNLOAD_DIR=sharepoint_downloads
MS_AUTH_FLOW=client_credentials
```

If SharePoint credentials are missing locally, developers can continue using the existing local document folder for testing. Production remains SharePoint-driven.

## Runtime Artifact Policy

The Docker image includes:

- app source code
- static UI files
- `document_catalog.json`
- `vector_db/index.faiss`
- `vector_db/index.pkl`

The Docker image excludes:

- `.env`
- `.venv/`
- `sharepoint_downloads/`
- raw PDFs
- token caches
- temporary manifests

## Troubleshooting

SharePoint sync fails:

- Confirm `MS_AUTH_FLOW=client_credentials`.
- Confirm `MS_TENANT_ID`, `MS_CLIENT_ID`, and `MS_CLIENT_SECRET`.
- Confirm Graph application permissions and admin consent.
- Confirm `SHAREPOINT_SITE_ID`, `SHAREPOINT_DRIVE_ID`, and `SHAREPOINT_FOLDER_PATH`.

Manifest always changes:

- Check whether SharePoint `eTag` or `cTag` changes on every read.
- Compare SHA-256 fields in `knowledge_manifest.json`.
- Confirm files are not being rewritten locally by another step.

Ingestion fails:

- Confirm `sharepoint_downloads/` contains PDFs.
- Confirm `PAPERS_DIR=sharepoint_downloads`.
- Confirm `vector_db/` can be written by the runner.

AgentBase deploy fails:

- Confirm `GREENNODE_CLIENT_ID` and `GREENNODE_CLIENT_SECRET`.
- Confirm `AGENTBASE_RUNTIME_ID` points to the existing runtime.
- Confirm AgentBase managed Container Registry access.
- Confirm `AGENTBASE_ENDPOINT_URL` is the public runtime URL.

Production verification fails:

- Check `GET /health`.
- Check runtime logs in AgentBase.
- Confirm the runtime listens on `PORT=8080`.
- Confirm `document_catalog.json` and `vector_db/` are present in the Docker image.

## What To Ask IT / Microsoft Admin

Ask IT for:

- Microsoft Entra app registration for CI.
- Client secret or certificate credential.
- Application permission approval for SharePoint read access.
- The exact SharePoint site ID.
- The exact SharePoint drive ID for the Documents library.
- The folder path, for example `ISMS-Docs/ISMS Portal`.
- Confirmation that GitHub Actions runner outbound traffic can reach Microsoft Graph.
