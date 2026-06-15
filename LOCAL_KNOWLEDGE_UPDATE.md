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

## 2. One-Command Refresh

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

The script runs:

1. `python sharepoint_sync.py`
2. `python ingest.py`
3. `python build_document_catalog.py`
4. `python scripts/security_audit.py`
5. `python scripts/ci_smoke_test.py --catalog-only`
6. `python scripts/ci_smoke_test.py`

Useful shortcuts:

```powershell
python scripts/local_refresh_knowledge.py --skip-sync
python scripts/local_refresh_knowledge.py --clean --yes
```

Use `--skip-tests` to only sync and rebuild knowledge artifacts. Use `--catalog-only` to run only the catalog build and catalog smoke test after ingest.

`scripts/local_refresh_knowledge.py` is the single supported local refresh command. SharePoint sync is local-only (device_code); GitHub Actions never syncs SharePoint.

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
