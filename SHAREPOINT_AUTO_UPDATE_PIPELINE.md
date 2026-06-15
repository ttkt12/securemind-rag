# SharePoint Local Knowledge Update

SecureMind RAG now uses a local-only SharePoint sync design.

SharePoint remains the source of truth for official ISMS, security, compliance, policy, procedure, and governance documents. GitHub Actions no longer connects to SharePoint and no longer uses Microsoft Graph `client_credentials` / app-only sync.

## Current Architecture

```text
Developer machine
  |
  | MS_AUTH_FLOW=device_code
  v
Microsoft user login
  |
  v
SharePoint ISMS Portal
  |
  v
sharepoint_downloads/
  |
  v
python ingest.py
  |
  v
vector_db/
  |
  v
python build_document_catalog.py
  |
  v
document_catalog.json
  |
  v
manual AgentBase runtime update when needed
```

GitHub Actions is now used for repository checks only:

- security audit
- Python compile checks
- catalog-only smoke tests
- optional verification of the existing AgentBase runtime

GitHub Actions does not:

- call Microsoft Graph SharePoint endpoints
- run `sharepoint_sync.py`
- run `scripts/graph_auth_diagnostic.py`
- require `MS_CLIENT_SECRET` for SharePoint
- rebuild `vector_db/` from SharePoint
- create a duplicate AgentBase runtime

## Local SharePoint Sync

Use local interactive auth:

```env
MS_AUTH_FLOW=device_code
```

Then run the preferred one-command refresh:

Windows:

```bat
python scripts\local_refresh_knowledge.py --clean --yes
```

macOS/Linux:

```bash
python scripts/local_refresh_knowledge.py --clean --yes
```

The helper runs:

1. `python sharepoint_sync.py`
2. `python ingest.py`
3. `python build_document_catalog.py`
4. `python scripts/security_audit.py`
5. `python scripts/ci_smoke_test.py --catalog-only`
6. `python scripts/ci_smoke_test.py`

It prints only a safe summary:

- document count
- downloaded file count
- vector DB path

It does not print tokens, secrets, API keys, or raw document content.

## Required Local Configuration

The local `.env` should contain SharePoint settings for your user login:

- `MS_AUTH_FLOW=device_code`
- `MS_TENANT_ID`
- `MS_CLIENT_ID`
- `SHAREPOINT_HOSTNAME`
- `SHAREPOINT_SITE_PATH`
- `SHAREPOINT_FOLDER_PATH`
- `SHAREPOINT_DOWNLOAD_DIR`
- `PAPERS_DIR=sharepoint_downloads`

`MS_CLIENT_SECRET` is not required for local `device_code` sync.

## GitHub Actions Configuration

CI no longer needs SharePoint client credentials. Do not add these as required CI secrets for SharePoint sync:

- `MS_TENANT_ID`
- `MS_CLIENT_ID`
- `MS_CLIENT_SECRET`
- `SHAREPOINT_SITE_ID`
- `SHAREPOINT_DRIVE_ID`
- `SHAREPOINT_HOSTNAME`
- `SHAREPOINT_SITE_PATH`
- `SHAREPOINT_FOLDER_PATH`

CI may still use non-SharePoint secrets for optional production verification or future deployment tasks, such as:

- `AGENTBASE_ENDPOINT_URL`
- `AI_PLATFORM_API_KEY`
- `AI_PLATFORM_BASE_URL`
- `AI_PLATFORM_MODEL`
- Teams bot runtime secrets if a deployment workflow explicitly needs them

## Deployment Artifact Policy

`vector_db/` is not tracked in Git because it is generated and can contain sensitive knowledge-derived embeddings.

Because CI no longer syncs SharePoint and no longer has `vector_db/`, the safe default is:

- CI checks code only.
- CI does not build or deploy a new AgentBase image that would omit the knowledge base.
- The existing AgentBase runtime remains unchanged until you perform a manual knowledge/runtime update.

To update production knowledge, run the local knowledge update flow first, then deploy the existing AgentBase runtime with an artifact/image that includes the refreshed `vector_db/` and `document_catalog.json`.

## Tradeoff

This design is more conservative and avoids storing Microsoft SharePoint app-only credentials in CI.

The tradeoff is manual knowledge updates instead of automatic SharePoint-driven CI updates.

## Troubleshooting

Local SharePoint sync fails:

- Confirm `MS_AUTH_FLOW=device_code`.
- Confirm the Microsoft account used in the device-code login has access to the SharePoint folder.
- Confirm `SHAREPOINT_FOLDER_PATH` points to the intended folder inside the Documents drive.
- Confirm `PAPERS_DIR=sharepoint_downloads` before rebuilding the vector DB.

CI unexpectedly tries SharePoint sync:

- Remove any workflow step calling `sharepoint_sync.py` or `scripts/graph_auth_diagnostic.py`.
- Do not set `MS_AUTH_FLOW=device_code` in GitHub Actions. It is interactive and unsupported in CI.
