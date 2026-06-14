from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import quote

import msal
import requests
from dotenv import load_dotenv

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
DELEGATED_SCOPES = ["User.Read", "Files.Read.All", "Sites.Read.All"]
APP_ONLY_SCOPES = ["https://graph.microsoft.com/.default"]
TOKEN_CACHE_FILE = Path("token_cache.bin")
MANIFEST_FILE_NAME = "sharepoint_manifest.json"
_auth_token = None


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("your_"):
        raise RuntimeError(f"Missing required .env value: {name}")
    return value


def env_is_configured(name: str) -> bool:
    value = os.getenv(name, "").strip()
    return bool(value and not value.startswith("your_"))


def get_auth_flow() -> str:
    auth_flow = os.getenv("MS_AUTH_FLOW", "device_code").strip().lower()
    aliases = {
        "app": "client_credentials",
        "app_only": "client_credentials",
        "application": "client_credentials",
    }
    auth_flow = aliases.get(auth_flow, auth_flow)
    if auth_flow not in {"device_code", "client_credentials"}:
        raise RuntimeError("MS_AUTH_FLOW must be device_code or client_credentials.")

    return auth_flow


def validate_config(auth_flow: str) -> None:
    required_names = ["MS_TENANT_ID", "MS_CLIENT_ID"]
    if auth_flow == "client_credentials":
        required_names.append("MS_CLIENT_SECRET")
    if not env_is_configured("SHAREPOINT_SITE_ID"):
        required_names.extend(["SHAREPOINT_HOSTNAME", "SHAREPOINT_SITE_PATH"])
    print("Config validation:")
    print(f"- MS_AUTH_FLOW: {auth_flow}")
    missing = []
    for name in required_names:
        configured = env_is_configured(name)
        print(f"- {name}: {'OK' if configured else 'MISSING'}")
        if not configured:
            missing.append(name)

    folder_path = get_sharepoint_folder_path()
    print(f"- SHAREPOINT_FOLDER_PATH: {'OK' if folder_path else 'EMPTY'}")
    print(f"- SHAREPOINT_SITE_ID: {'OK' if env_is_configured('SHAREPOINT_SITE_ID') else 'EMPTY'}")
    print(f"- SHAREPOINT_DRIVE_ID: {'OK' if env_is_configured('SHAREPOINT_DRIVE_ID') else 'EMPTY'}")

    if missing:
        raise RuntimeError("Missing required .env values. Update .env and try again.")


def get_sharepoint_folder_path() -> str:
    folder_path = os.getenv("SHAREPOINT_FOLDER_PATH", "").strip().strip('"').strip("'").strip()
    return folder_path.strip("/")


def load_allowed_extensions() -> set[str]:
    raw_extensions = os.getenv("SHAREPOINT_FILE_EXTENSIONS", ".pdf,.docx,.pptx,.xlsx")
    extensions = set()
    for extension in raw_extensions.split(","):
        extension = extension.strip().lower()
        if not extension:
            continue
        extensions.add(extension if extension.startswith(".") else f".{extension}")

    return extensions


def load_token_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_FILE.exists():
        try:
            cache.deserialize(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
        except ValueError:
            print("Ignoring invalid Microsoft token cache. A new login is required.")

    return cache


def save_token_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        TOKEN_CACHE_FILE.write_text(cache.serialize(), encoding="utf-8")
        TOKEN_CACHE_FILE.chmod(0o600)


def get_access_token() -> str:
    global _auth_token
    if _auth_token:
        return _auth_token

    auth_flow = get_auth_flow()
    print(f"Authentication mode: {auth_flow}")
    tenant_id = required_env("MS_TENANT_ID")
    client_id = required_env("MS_CLIENT_ID")
    authority = f"https://login.microsoftonline.com/{tenant_id}"

    if auth_flow == "client_credentials":
        client_secret = required_env("MS_CLIENT_SECRET")
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=authority,
        )
        result = app.acquire_token_for_client(scopes=APP_ONLY_SCOPES)
        if "access_token" not in result:
            error = result.get("error", "authentication_failed")
            description = result.get("error_description", "No error description returned.")
            raise RuntimeError(f"Microsoft app-only authentication failed: {error}. {description}")
        _auth_token = result["access_token"]
        return _auth_token

    cache = load_token_cache()
    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=authority,
        token_cache=cache,
    )

    accounts = app.get_accounts()
    if accounts:
        for account in accounts:
            result = app.acquire_token_silent(DELEGATED_SCOPES, account=account)
            if result and "access_token" in result:
                print("Using cached Microsoft Graph token.")
                _auth_token = result["access_token"]
                return _auth_token

    flow = app.initiate_device_flow(scopes=DELEGATED_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError("Could not start Microsoft device code flow.")

    verification_uri = flow.get("verification_uri") or "https://microsoft.com/devicelogin"
    print("Open this URL in your browser:")
    print(verification_uri)
    print("Enter this code:")
    print(flow["user_code"])
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        error = result.get("error", "authentication_failed")
        description = result.get("error_description", "No error description returned.")
        if "AADSTS7000218" in description:
            raise RuntimeError(
                "Device code flow is blocked for this app registration. Ask IT to "
                "enable 'Allow public client flows' in Microsoft Entra App "
                "Registration > Authentication > Advanced settings."
            )
        raise RuntimeError(f"Microsoft authentication failed: {error}. {description}")

    save_token_cache(cache)
    _auth_token = result["access_token"]
    return _auth_token


def graph_get(url: str, access_token: str, stream: bool = False) -> requests.Response:
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
        stream=stream,
    )
    if response.status_code in {401, 403}:
        raise RuntimeError(
            "Microsoft Graph request was not authorized. For CI app-only sync, ask IT to grant "
            "admin consent for application permissions such as Sites.Read.All or a site-scoped "
            "equivalent, and confirm the app can access the configured SharePoint site/drive."
        )
    response.raise_for_status()
    return response


def graph_json(url: str, access_token: str) -> dict:
    return graph_get(url, access_token).json()


def get_site(access_token: str, hostname: str, site_path: str) -> dict:
    clean_site_path = "/" + site_path.strip("/")
    site_url = f"{GRAPH_BASE_URL}/sites/{hostname}:{quote(clean_site_path)}"
    site = graph_json(site_url, access_token)
    print(f"Site found: {site.get('displayName') or site.get('name') or site.get('id')}")
    return site


def get_default_drive(access_token: str, site_id: str) -> dict:
    drive = graph_json(f"{GRAPH_BASE_URL}/sites/{site_id}/drive", access_token)
    print(f"Drive found: {drive.get('name') or drive.get('id')}")
    return drive


def get_site_from_env(access_token: str) -> dict:
    site_id = os.getenv("SHAREPOINT_SITE_ID", "").strip()
    if site_id:
        site = graph_json(f"{GRAPH_BASE_URL}/sites/{quote(site_id, safe=':,')}", access_token)
        print(f"Site found: {site.get('displayName') or site.get('name') or site.get('id')}")
        return site

    hostname = required_env("SHAREPOINT_HOSTNAME")
    site_path = required_env("SHAREPOINT_SITE_PATH")
    return get_site(access_token, hostname, site_path)


def get_drive_from_env(access_token: str, site_id: str) -> dict:
    drive_id = os.getenv("SHAREPOINT_DRIVE_ID", "").strip()
    if drive_id:
        drive = graph_json(f"{GRAPH_BASE_URL}/drives/{quote(drive_id, safe='')}", access_token)
        print(f"Drive found: {drive.get('name') or drive.get('id')}")
        return drive

    return get_default_drive(access_token, site_id)


def get_target_folder(access_token: str, site_id: str, folder_path: str) -> dict:
    print(f"Target folder path: {folder_path}")
    encoded_folder_path = quote(folder_path, safe="/")
    folder_url = f"{GRAPH_BASE_URL}/sites/{site_id}/drive/root:/{encoded_folder_path}"

    try:
        folder = graph_json(folder_url, access_token)
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else "unknown"
        if status_code == 404:
            raise RuntimeError(f"Cannot find SharePoint folder: {folder_path}") from error
        raise RuntimeError(
            f"Cannot resolve SharePoint folder: {folder_path} (HTTP {status_code})"
        ) from error

    if "folder" not in folder:
        raise RuntimeError(f"Cannot find SharePoint folder: {folder_path}")

    print(f"Target folder found: {folder.get('name') or folder.get('id')}")
    return folder


def get_target_folder_by_drive(access_token: str, drive_id: str, folder_path: str) -> dict:
    print(f"Target folder path: {folder_path}")
    encoded_folder_path = quote(folder_path, safe="/")
    folder_url = f"{GRAPH_BASE_URL}/drives/{quote(drive_id, safe='')}/root:/{encoded_folder_path}"

    try:
        folder = graph_json(folder_url, access_token)
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else "unknown"
        if status_code == 404:
            raise RuntimeError(f"Cannot find SharePoint folder: {folder_path}") from error
        raise RuntimeError(
            f"Cannot resolve SharePoint folder: {folder_path} (HTTP {status_code})"
        ) from error

    if "folder" not in folder:
        raise RuntimeError(f"Cannot find SharePoint folder: {folder_path}")

    print(f"Target folder found: {folder.get('name') or folder.get('id')}")
    return folder


def iter_drive_children(access_token: str, drive_id: str, item_id: str | None = None):
    if item_id:
        url = f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/children"
    else:
        url = f"{GRAPH_BASE_URL}/drives/{drive_id}/root/children"

    while url:
        payload = graph_json(url, access_token)
        for item in payload.get("value", []):
            yield item
        url = payload.get("@odata.nextLink")


def sanitize_path_part(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", value)
    value = value.strip(" .")
    return value or "_"


def safe_relative_path(parent_path: Path, name: str) -> Path:
    parts = [sanitize_path_part(part) for part in parent_path.parts if part not in {"", "."}]
    parts.append(sanitize_path_part(name))
    return Path(*parts)


def manifest_key(drive_id: str, item_id: str) -> str:
    return f"{drive_id}:{item_id}"


def load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        return {"files": []}

    return json.loads(manifest_path.read_text(encoding="utf-8"))


def save_manifest(manifest_path: Path, manifest: dict) -> None:
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_manifest_index(manifest: dict) -> dict:
    indexed = {}
    for item in manifest.get("files", []):
        key = manifest_key(item.get("drive_id", ""), item.get("sharepoint_item_id", ""))
        indexed[key] = item

    return indexed


def item_change_token(item: dict) -> str:
    return item.get("eTag") or item.get("cTag") or item.get("lastModifiedDateTime") or ""


def manifest_change_token(entry: dict) -> str:
    return entry.get("eTag") or entry.get("cTag") or entry.get("last_modified_datetime") or ""


def should_download(item: dict, local_path: Path, manifest_entry: dict | None) -> bool:
    if not local_path.exists() or not manifest_entry:
        return True

    return item_change_token(item) != manifest_change_token(manifest_entry)


def download_file(item: dict, local_path: Path, access_token: str) -> None:
    download_url = item.get("@microsoft.graph.downloadUrl")
    if download_url:
        response = requests.get(download_url, timeout=120, stream=True)
    else:
        content_url = f"{GRAPH_BASE_URL}/drives/{item['parentReference']['driveId']}/items/{item['id']}/content"
        response = graph_get(content_url, access_token, stream=True)

    response.raise_for_status()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("wb") as file_handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                file_handle.write(chunk)


def manifest_entry_for_item(item: dict, drive_id: str, local_path: Path) -> dict:
    relative_path = str(local_path).replace("\\", "/")
    return {
        "name": item.get("name"),
        "local_path": str(local_path),
        "relative_path": relative_path,
        "drive_item_id": item.get("id"),
        "sharepoint_item_id": item.get("id"),
        "drive_id": drive_id,
        "web_url": item.get("webUrl"),
        "last_modified_datetime": item.get("lastModifiedDateTime"),
        "size": item.get("size"),
        "eTag": item.get("eTag"),
        "cTag": item.get("cTag"),
    }


def sync_drive(
    access_token: str,
    drive_id: str,
    download_dir: Path,
    allowed_extensions: set[str],
    start_item_id: str | None = None,
) -> None:
    manifest_path = download_dir / MANIFEST_FILE_NAME
    download_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(manifest_path)
    manifest_index = build_manifest_index(manifest)

    files_scanned = 0
    files_downloaded = 0
    files_skipped = 0
    updated_entries = dict(manifest_index)

    stack = [(start_item_id, Path())]
    while stack:
        item_id, parent_path = stack.pop()
        for item in iter_drive_children(access_token, drive_id, item_id=item_id):
            item_name = item.get("name", "")
            if "folder" in item:
                stack.append((item["id"], safe_relative_path(parent_path, item_name)))
                continue

            if "file" not in item:
                continue

            files_scanned += 1
            extension = Path(item_name).suffix.lower()
            if extension not in allowed_extensions:
                files_skipped += 1
                continue

            relative_path = safe_relative_path(parent_path, item_name)
            local_path = download_dir / relative_path
            key = manifest_key(drive_id, item["id"])
            manifest_entry = manifest_index.get(key)

            if should_download(item, local_path, manifest_entry):
                download_file(item, local_path, access_token)
                files_downloaded += 1
            else:
                files_skipped += 1

            updated_entries[key] = manifest_entry_for_item(item, drive_id, local_path)

    manifest["files"] = sorted(
        updated_entries.values(),
        key=lambda entry: str(entry.get("local_path", "")),
    )
    save_manifest(manifest_path, manifest)

    print(f"Files scanned: {files_scanned}")
    print(f"Files downloaded: {files_downloaded}")
    print(f"Files skipped: {files_skipped}")
    print(f"Manifest saved: {manifest_path}")


def main() -> None:
    load_dotenv()
    auth_flow = get_auth_flow()
    validate_config(auth_flow)
    folder_path = get_sharepoint_folder_path()
    download_dir = Path(os.getenv("SHAREPOINT_DOWNLOAD_DIR", "sharepoint_downloads"))
    allowed_extensions = load_allowed_extensions()

    access_token = get_access_token()
    site = get_site_from_env(access_token)
    drive = get_drive_from_env(access_token, site["id"])
    target_folder = get_target_folder_by_drive(access_token, drive["id"], folder_path) if folder_path else None
    start_item_id = target_folder["id"] if target_folder else None
    sync_drive(access_token, drive["id"], download_dir, allowed_extensions, start_item_id=start_item_id)


if __name__ == "__main__":
    main()
