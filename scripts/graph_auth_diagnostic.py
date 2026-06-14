from __future__ import annotations

import os
import sys
from urllib.parse import quote

import msal
import requests
from dotenv import load_dotenv

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
APP_ONLY_SCOPES = ["https://graph.microsoft.com/.default"]


def env_value(name: str) -> str:
    return os.getenv(name, "").strip().strip('"').strip("'").strip()


def env_is_configured(name: str) -> bool:
    value = env_value(name)
    return bool(value and not value.startswith("your_"))


def print_env_status(names: list[str]) -> list[str]:
    missing: list[str] = []
    for name in names:
        configured = env_is_configured(name)
        print(f"- {name}: {'OK' if configured else 'MISSING'}")
        if not configured:
            missing.append(name)
    return missing


def print_safe_sharepoint_config() -> None:
    hostname = env_value("SHAREPOINT_HOSTNAME") or "EMPTY"
    site_path = env_value("SHAREPOINT_SITE_PATH") or "EMPTY"
    folder_path = env_value("SHAREPOINT_FOLDER_PATH") or "EMPTY"
    print(f"- SHAREPOINT_HOSTNAME: {hostname}")
    print(f"- SHAREPOINT_SITE_PATH: {site_path}")
    print(f"- SHAREPOINT_FOLDER_PATH: {folder_path}")
    print(f"- SHAREPOINT_SITE_ID: {'OK' if env_is_configured('SHAREPOINT_SITE_ID') else 'EMPTY'}")
    print(f"- SHAREPOINT_DRIVE_ID: {'OK' if env_is_configured('SHAREPOINT_DRIVE_ID') else 'EMPTY'}")


def acquire_app_token() -> str:
    tenant_id = env_value("MS_TENANT_ID")
    client_id = env_value("MS_CLIENT_ID")
    client_secret = env_value("MS_CLIENT_SECRET")
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )
    result = app.acquire_token_for_client(scopes=APP_ONLY_SCOPES)
    if "access_token" not in result:
        print(
            "Token acquisition failed. Check tenant/client/secret. "
            "Make sure MS_CLIENT_SECRET is the secret VALUE, not Secret ID."
        )
        error = result.get("error")
        if error:
            print(f"Token error code: {error}")
        raise SystemExit(1)

    print("Token acquisition: OK")
    return result["access_token"]


def graph_get_json(url: str, access_token: str) -> dict:
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
    )
    if response.status_code in {401, 403}:
        print(
            "Token acquired, but SharePoint access failed. App likely lacks "
            "Microsoft Graph application permission or admin consent."
        )
        print(f"Graph HTTP status: {response.status_code}")
        raise SystemExit(2)
    if response.status_code == 404:
        print("Token acquired, but SharePoint site/drive/folder configuration is likely incorrect.")
        print("Graph HTTP status: 404")
        raise SystemExit(3)
    if response.status_code >= 400:
        print(f"Microsoft Graph request failed with HTTP status: {response.status_code}")
        raise SystemExit(4)
    return response.json()


def get_site(access_token: str) -> dict:
    site_id = env_value("SHAREPOINT_SITE_ID")
    if site_id:
        site = graph_get_json(f"{GRAPH_BASE_URL}/sites/{quote(site_id, safe=':,')}", access_token)
        print("SharePoint site access: OK")
        return site

    hostname = env_value("SHAREPOINT_HOSTNAME")
    site_path = "/" + env_value("SHAREPOINT_SITE_PATH").strip("/")
    if not hostname or site_path == "/":
        print("Token acquired, but SharePoint site/drive/folder configuration is likely incorrect.")
        print("Missing SHAREPOINT_SITE_ID or SHAREPOINT_HOSTNAME/SHAREPOINT_SITE_PATH.")
        raise SystemExit(3)

    site = graph_get_json(f"{GRAPH_BASE_URL}/sites/{hostname}:{quote(site_path)}", access_token)
    print("SharePoint site access: OK")
    return site


def get_drive(access_token: str, site: dict) -> dict:
    drive_id = env_value("SHAREPOINT_DRIVE_ID")
    if drive_id:
        drive = graph_get_json(f"{GRAPH_BASE_URL}/drives/{quote(drive_id, safe='')}", access_token)
        print("SharePoint drive access: OK")
        return drive

    site_id = site.get("id")
    if not site_id:
        print("Token acquired, but SharePoint site/drive/folder configuration is likely incorrect.")
        print("Graph site response did not include a site id.")
        raise SystemExit(3)

    drive = graph_get_json(f"{GRAPH_BASE_URL}/sites/{quote(site_id, safe=':,')}/drive", access_token)
    print("SharePoint drive access: OK")
    return drive


def check_folder(access_token: str, drive: dict) -> None:
    folder_path = env_value("SHAREPOINT_FOLDER_PATH").strip("/")
    if not folder_path:
        print("SharePoint folder path: EMPTY, root drive access checked only.")
        return

    drive_id = drive.get("id")
    if not drive_id:
        print("Token acquired, but SharePoint site/drive/folder configuration is likely incorrect.")
        print("Graph drive response did not include a drive id.")
        raise SystemExit(3)

    encoded_folder_path = quote(folder_path, safe="/")
    graph_get_json(f"{GRAPH_BASE_URL}/drives/{quote(drive_id, safe='')}/root:/{encoded_folder_path}", access_token)
    print("SharePoint folder access: OK")


def main() -> None:
    load_dotenv()
    print("Microsoft Graph app-only diagnostic")
    print("- MS_AUTH_FLOW: client_credentials")
    required = ["MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET"]
    missing = print_env_status(required)
    print_safe_sharepoint_config()
    if missing:
        print(
            "Token acquisition failed. Check tenant/client/secret. "
            "Make sure MS_CLIENT_SECRET is the secret VALUE, not Secret ID."
        )
        raise SystemExit(1)

    access_token = acquire_app_token()
    site = get_site(access_token)
    drive = get_drive(access_token, site)
    check_folder(access_token, drive)
    print("Microsoft Graph app-only diagnostic: PASS")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as error:
        print(f"Microsoft Graph diagnostic request failed: {error.__class__.__name__}")
        sys.exit(4)
