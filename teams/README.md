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

You can build the template package with:

```powershell
python scripts/package_teams_app.py
```

To generate a package with real values without editing the template:

```powershell
python scripts/package_teams_app.py `
  --bot-id "<MICROSOFT_APP_ID>" `
  --domain "endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn"
```

## Upload

Upload the zip through Microsoft Teams custom app upload. If custom app upload is blocked, ask IT/admin to upload the package to the Teams app catalog and ensure the Teams channel is enabled for the bot registration.
