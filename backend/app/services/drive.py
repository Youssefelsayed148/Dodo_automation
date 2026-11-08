"""Google Drive export (PLAN.md section 14). OAuth installed-app flow with
scope drive.file; token in data/ with 0600 permissions.

The Drive API is wrapped in `DriveClient` (protocol) so upload planning and
naming are testable with a fake."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..config import get_settings

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveError(RuntimeError):
    pass


class DriveNotConnected(DriveError):
    pass


# --------------------------------------------------------------- naming


def sanitize_folder_name(title: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", title or "")
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:100] or "Untitled book"


def unique_folder_name(base: str, existing: set[str]) -> str:
    base = sanitize_folder_name(base)
    if base not in existing:
        return base
    n = 2
    while f"{base} ({n})" in existing:
        n += 1
    return f"{base} ({n})"


@dataclass
class UploadItem:
    local: Path
    remote_name: str
    parent: str  # "" = book folder, else subfolder name ("pages")
    size: int


def plan_uploads(export_dir: Path, existing: dict[str, dict[str, int]] | None = None) -> tuple[list[UploadItem], list[UploadItem]]:
    """Return (to_upload, skipped). `existing` maps parent -> {name: size}
    of files already in Drive (resume after partial upload)."""
    existing = existing or {}
    items: list[UploadItem] = []
    for name in ("interior.pdf", "cover.pdf", "book-settings.json"):
        p = export_dir / name
        if p.is_file():
            items.append(UploadItem(p, name, "", p.stat().st_size))
    pages = export_dir / "pages"
    if pages.is_dir():
        for p in sorted(pages.glob("*.png")):
            items.append(UploadItem(p, p.name, "pages", p.stat().st_size))
    todo, skipped = [], []
    for it in items:
        if existing.get(it.parent, {}).get(it.remote_name) == it.size:
            skipped.append(it)
        else:
            todo.append(it)
    return todo, skipped


# ----------------------------------------------------------- client API


class DriveClient(Protocol):
    def list_folder_names(self, parent: str | None) -> set[str]: ...
    def find_folder(self, name: str, parent: str | None) -> str | None: ...
    def create_folder(self, name: str, parent: str | None) -> str: ...
    def list_files(self, folder_id: str) -> dict[str, int]: ...
    def upload(self, local: Path, name: str, folder_id: str) -> str: ...
    def folder_link(self, folder_id: str) -> str: ...


def token_path() -> Path:
    return get_settings().google_token_path


def is_configured() -> bool:
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret)


def is_connected() -> bool:
    return token_path().is_file()


def _client_config(redirect_uri: str) -> dict[str, Any]:
    s = get_settings()
    return {"installed": {"client_id": s.google_client_id, "client_secret": s.google_client_secret,
                          "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                          "token_uri": "https://oauth2.googleapis.com/token",
                          "redirect_uris": [redirect_uri]}}


def auth_url(redirect_uri: str) -> tuple[str, str]:
    if not is_configured():
        raise DriveError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not set in .env")
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(_client_config(redirect_uri), scopes=SCOPES, redirect_uri=redirect_uri)
    url, state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    return url, state


def finish_auth(redirect_uri: str, code: str) -> None:
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(_client_config(redirect_uri), scopes=SCOPES, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    save_token(flow.credentials.to_json())


def save_token(token_json: str) -> None:
    p = token_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token_json)
    os.chmod(p, 0o600)


def disconnect() -> None:
    token_path().unlink(missing_ok=True)


class GoogleDriveClient:
    def __init__(self) -> None:
        if not is_connected():
            raise DriveNotConnected("Google Drive is not connected")
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_info(json.loads(token_path().read_text()), SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:  # noqa: BLE001
                    raise DriveNotConnected(f"Google token expired and could not be refreshed: {e}") from e
                save_token(creds.to_json())
            else:
                raise DriveNotConnected("Google token is invalid; reconnect Drive in Settings")
        self.svc = build("drive", "v3", credentials=creds, cache_discovery=False)

    @staticmethod
    def _q(s: str) -> str:
        return s.replace("\\", "\\\\").replace("'", "\\'")

    def _list(self, q: str) -> list[dict[str, Any]]:
        out, token = [], None
        while True:
            resp = self.svc.files().list(q=q, fields="nextPageToken, files(id,name,size,mimeType)",
                                         pageToken=token, pageSize=200).execute()
            out += resp.get("files", [])
            token = resp.get("nextPageToken")
            if not token:
                return out

    def list_folder_names(self, parent: str | None) -> set[str]:
        q = f"mimeType='{FOLDER_MIME}' and trashed=false and '{parent or 'root'}' in parents"
        return {f["name"] for f in self._list(q)}

    def find_folder(self, name: str, parent: str | None) -> str | None:
        q = f"mimeType='{FOLDER_MIME}' and trashed=false and name='{self._q(name)}' and '{parent or 'root'}' in parents"
        files = self._list(q)
        return files[0]["id"] if files else None

    def create_folder(self, name: str, parent: str | None) -> str:
        meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent or "root"]}
        return self.svc.files().create(body=meta, fields="id").execute()["id"]

    def list_files(self, folder_id: str) -> dict[str, int]:
        q = f"trashed=false and '{folder_id}' in parents and mimeType!='{FOLDER_MIME}'"
        return {f["name"]: int(f.get("size", 0)) for f in self._list(q)}

    def upload(self, local: Path, name: str, folder_id: str) -> str:
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload

        mime = "application/pdf" if local.suffix == ".pdf" else "application/json" if local.suffix == ".json" else "image/png"
        media = MediaFileUpload(str(local), mimetype=mime, resumable=True)
        try:
            return self.svc.files().create(body={"name": name, "parents": [folder_id]}, media_body=media, fields="id").execute()["id"]
        except HttpError as e:
            if e.resp.status in (403, 429) and b"quota" in (e.content or b"").lower():
                raise DriveError("Google Drive quota exceeded; try again later") from e
            raise DriveError(f"Drive upload failed: {e}") from e

    def folder_link(self, folder_id: str) -> str:
        return f"https://drive.google.com/drive/folders/{folder_id}"


def upload_export(client: DriveClient, folder_name: str, export_dir: Path, *, resume_folder_id: str | None = None,
                  progress=lambda p, m=None: None) -> dict[str, Any]:
    """Create the book folder (unique name) or resume into an existing one,
    then upload files, skipping those already uploaded with the same size."""
    if resume_folder_id:
        folder_id = resume_folder_id
        name = folder_name
    else:
        name = unique_folder_name(folder_name, client.list_folder_names(None))
        folder_id = client.create_folder(name, None)
    pages_id = client.find_folder("pages", folder_id) or client.create_folder("pages", folder_id)
    existing = {"": client.list_files(folder_id), "pages": client.list_files(pages_id)}
    todo, skipped = plan_uploads(export_dir, existing)
    for i, it in enumerate(todo):
        client.upload(it.local, it.remote_name, folder_id if it.parent == "" else pages_id)
        progress((i + 1) / max(len(todo), 1), f"uploaded {it.remote_name}")
    return {"folder_id": folder_id, "folder_name": name, "link": client.folder_link(folder_id),
            "uploaded": len(todo), "skipped": len(skipped)}
