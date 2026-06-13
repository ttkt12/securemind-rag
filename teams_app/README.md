# SecureMind RAG Teams App Package

This folder contains a minimal Microsoft Teams app package for the SecureMind RAG chatbot.

Before packaging:

1. Confirm `manifest.json` uses the real Teams Bot App ID.
2. Replace the placeholder `developer` URLs with approved organization URLs if required by your tenant policy.
3. Keep `color.png` and `outline.png` as valid PNG icons, or replace them with approved production icons.

To package:

```bash
cd teams_app
zip securemind-rag-teams-app.zip manifest.json color.png outline.png
```

Zip the contents of `teams_app/`, not the folder itself.

Upload the zip to Microsoft Teams for testing if custom app upload is allowed in your tenant.
