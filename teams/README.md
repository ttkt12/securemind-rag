# SecureMind RAG Microsoft Teams Package

This folder is a template for creating a Microsoft Teams custom app package.

## Replace Before Packaging

Update `manifest.json`:

* `id`: use the Microsoft Bot App ID.
* `bots[0].botId`: use the same Microsoft Bot App ID.
* `developer.websiteUrl`, `developer.privacyUrl`, and `developer.termsOfUseUrl`: use approved URLs for your tenant.
* `validDomains[0]`: use only the AgentBase runtime hostname, without `https://`.

Example domain:

```text
endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn
```

The messaging endpoint configured in Azure Bot / Bot Channels Registration must be:

```text
https://<my-agentbase-runtime-domain>/api/messages
```

## Required Files In The Zip

The final zip must contain these files at the root of the archive:

```text
manifest.json
color.png
outline.png
```

Zip the contents of this folder, not the folder itself.

> This folder is the **parametric template**. The packager defaults to the
> canonical `teams_app/` folder (which holds this deployment's real values), so
> a bare `python scripts/package_teams_app.py` does **not** build from here.

To build a package from this template with real values injected at build time
(without editing the template files):

```powershell
python scripts/package_teams_app.py --source teams `
  --bot-id "<MICROSOFT_APP_ID>" `
  --domain "endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn"
```

Building from this template without `--bot-id`/`--domain` fails with a clear
error, because the placeholder `id`/`botId`/`validDomains` would be rejected by
the Teams upload validator.

## Upload

Upload the zip through Microsoft Teams custom app upload. If custom app upload is blocked, ask IT/admin to upload the package to the Teams app catalog and ensure the Teams channel is enabled for the bot registration.
