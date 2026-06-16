# Microsoft Teams Integration

SecureMind RAG exposes a Microsoft Bot Framework-compatible endpoint through the existing `aiohttp` runtime.

Runtime endpoints:

```text
GET  /health
POST /chat
POST /api/messages
```

Keep `/chat` for JSON API testing and `/api/messages` for Microsoft Teams / Bot Framework activities.

## Environment Variables

Use placeholders from `.env.example` and put real values only in local `.env` or the deployment secret environment.

```text
MICROSOFT_APP_ID=
MICROSOFT_APP_PASSWORD=
MICROSOFT_APP_TYPE=MultiTenant
MICROSOFT_APP_TENANT_ID=
```

Backward-compatible aliases are still supported:

```text
TEAMS_BOT_APP_ID=
TEAMS_BOT_APP_PASSWORD=
MS_TENANT_ID=
```

Do not commit real Microsoft credentials.

## Azure / Microsoft Setup

1. Create or reuse a Microsoft Entra app registration for the bot.
2. Create a client secret and save it securely.
3. Create an Azure Bot or Bot Channels Registration using the same App ID.
4. Enable the Microsoft Teams channel.
5. Set the bot messaging endpoint to:

```text
https://<my-agentbase-runtime-domain>/api/messages
```

For the current AgentBase runtime:

```text
https://endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn/api/messages
```

## Teams App Package

`teams_bot.py` is always active because it also hosts the web UI/API
(`GET /`, `POST /chat`, `GET /documents`), independent of whether the Teams
integration is enabled.

There are **two** Teams package folders with distinct roles:

| Folder | Role | Output zip |
| --- | --- | --- |
| `teams_app/` | **Canonical**: pre-filled with this deployment's real bot ID and runtime domain. `package_teams_app.py` defaults to it. | `securemind-rag-teams-app.zip` |
| `teams/` | Parametric template (placeholders). Build it with `--bot-id` and `--domain` to inject real values without editing files. | `securemind-rag-teams-app.zip` (override with `--output`) |

The bare command now produces an uploadable package from `teams_app/`:

```powershell
python scripts/package_teams_app.py
```

The packager validates the manifest before zipping and fails with a clear
message if `id`/`botId`/`validDomains` still contain placeholders — so a template
built without real values will not silently produce a zip that Teams rejects.

The Teams zip must contain these files at the root:

```text
manifest.json
color.png
outline.png
```

In `manifest.json`, set:

* `id` to the Microsoft Bot App ID.
* `bots[0].botId` to the same Microsoft Bot App ID.
* `validDomains` to the AgentBase runtime hostname without `https://`.

Upload the zip through Microsoft Teams custom app upload. If custom app upload is blocked, send the zip to IT/admin and ask them to upload it to the Teams app catalog.

## Optional Azure CLI Automation

This machine must have Azure CLI installed and logged in before Microsoft-side automation is possible:

```powershell
az --version
az login
az account show
```

If `az` is missing, install Azure CLI first. If your tenant blocks app registration, bot creation, Teams channel enablement, or custom app upload, ask your Microsoft 365/Azure admin to perform those steps.

Do not create paid Azure resources until the subscription, resource group, region, and permission model are confirmed.

## Build The Package

Run the packager (defaults to the canonical `teams_app/` source):

```powershell
python scripts/package_teams_app.py
```

The output zip is:

```text
securemind-rag-teams-app.zip
```

To build from the `teams/` template with real values injected at build time
(without editing the template files):

```powershell
python scripts/package_teams_app.py --source teams `
  --bot-id "<MICROSOFT_APP_ID>" `
  --domain "endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn"
```

## Local Validation

Compile:

```powershell
python -m py_compile teams_bot.py config.py rag_core.py chatbot.py
```

Run locally:

```powershell
python teams_bot.py
```

Test health:

```powershell
curl.exe http://localhost:3978/health
```

`GET /api/messages` returns `405 Method Not Allowed`; this is expected because Teams sends POST activities.
