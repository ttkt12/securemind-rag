# Local Knowledge Update

Use this when SharePoint documents change and you want to refresh SecureMind RAG locally.

## 1. Configure Local Auth

In local `.env`, use:

```env
MS_AUTH_FLOW=device_code
PAPERS_DIR=sharepoint_downloads
SHAREPOINT_DOWNLOAD_DIR=sharepoint_downloads
```

Do not commit `.env`.

## 2. Run The Local Update

```powershell
python scripts/local_sync_knowledge.py
```

The script runs SharePoint sync, rebuilds `vector_db/`, rebuilds `document_catalog.json`, and runs a catalog smoke test.

## 3. Verify Locally

```powershell
python scripts/ci_smoke_test.py
python chatbot.py
```

## 4. Deploy Manually

GitHub Actions does not sync SharePoint or rebuild `vector_db/`.

After local verification, deploy/update the existing AgentBase runtime using a package or image that includes:

- `vector_db/index.faiss`
- `vector_db/index.pkl`
- `document_catalog.json`

Do not deploy a fresh image that omits `vector_db/`.
