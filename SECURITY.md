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
- GitHub Actions does not access SharePoint and does not rebuild `vector_db/`.
- Refresh knowledge locally with `MS_AUTH_FLOW=device_code`, then deploy an artifact that includes the refreshed `vector_db/` when needed.

## Local Development

Use:

```powershell
python scripts/local_refresh_knowledge.py
python chatbot.py
```

Local SharePoint sync uses `MS_AUTH_FLOW=device_code`. GitHub Actions must not run SharePoint sync or Microsoft Graph SharePoint calls.

## Web API Access Token

- The web API endpoints `POST /chat`, `GET /documents` and `GET /documents/count`
  can be protected with a shared access token.
- Set `REQUIRE_APP_ACCESS_TOKEN=true` and a non-empty `APP_ACCESS_TOKEN` to require
  the header `X-App-Access-Token: <APP_ACCESS_TOKEN>` on those endpoints.
- Missing token returns HTTP 401; an invalid token returns HTTP 403. Responses are
  clean JSON (`{"error": ...}`) and never include the token, other secrets, or env
  values. Token comparison uses a constant-time check.
- `GET /`, `GET /health`, static assets, and the Teams `POST /api/messages` endpoint
  are not gated by this token (Teams keeps its Bot Framework JWT validation).
- The web UI sends the token from `sessionStorage` and prompts the user to set it when
  it receives 401/403. The token is never logged or hard-coded in the frontend.
- When `REQUIRE_APP_ACCESS_TOKEN=false` (default) local development works without a
  token. Keep `APP_ACCESS_TOKEN` out of Git; set it via `.env` locally and Secrets in
  deployment.

## Security Audit

Run before committing:

```powershell
python scripts/security_audit.py
```

The audit checks for tracked `.env` files, tracked generated knowledge artifacts, token caches, private keys, and high-confidence secret patterns. It never prints secret values.
