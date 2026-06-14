# Security Policy

## Secret Handling

- Do not commit `.env`, local token caches, Microsoft client secrets, GreenNode credentials, Teams bot passwords, or API keys.
- Store runtime values in local `.env` for development and GitHub Secrets for CI/CD.
- Use `.env.example` for placeholder names only.
- If a secret is accidentally committed, rotate it immediately and remove it from the repository history where required.

## Document And Knowledge Artifacts

- SharePoint is the source of truth for official ISMS, security, compliance, policy, procedure, and governance documents.
- Do not commit raw SharePoint downloads from `sharepoint_downloads/`.
- Treat `vector_db/` as a generated and potentially sensitive artifact because embeddings can reveal information about source documents.
- CI should rebuild `vector_db/` and `document_catalog.json` from SharePoint after app-only SharePoint access is approved.

## Local Development

Use:

```powershell
python sharepoint_sync.py
python ingest.py
python build_document_catalog.py
python chatbot.py
```

Local SharePoint sync may use `MS_AUTH_FLOW=device_code`. GitHub Actions must use `MS_AUTH_FLOW=client_credentials`.

## Security Audit

Run before committing:

```powershell
python scripts/security_audit.py
```

The audit checks for tracked `.env` files, tracked generated knowledge artifacts, token caches, private keys, and high-confidence secret patterns. It never prints secret values.
