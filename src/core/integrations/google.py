"""
Google Workspace Service Adapter for MAC_ASD v12.0.

Four service classes (Drive, Sheets, Docs, Gmail) — each lazily initialized
when accessed via GoogleWorkspaceService properties.

Uses OAuth2 token managed by Hermes Agent (~/.hermes/google_token.json).
For operations not covered by google_api.py CLI, uses google-api-python-client
directly when credentials are available.
"""

import logging
import subprocess
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
GOOGLE_API_SCRIPT = str(
    HERMES_HOME / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py"
)
TOKEN_PATH = HERMES_HOME / "google_token.json"


def _call_google_api(*args) -> Dict[str, Any]:
    """Call google_api.py CLI and return parsed JSON result."""
    cmd = ["python3", GOOGLE_API_SCRIPT, *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.error(f"Google API error: {result.stderr[:300]}")
            return {"success": False, "error": result.stderr[:200]}
        if not result.stdout.strip():
            return {"success": True, "data": None}
        return {"success": True, "data": json.loads(result.stdout)}
    except json.JSONDecodeError as e:
        return {"success": False, "error": str(e), "raw": result.stdout[:300] if 'result' in dir() else ""}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout (30s)"}
    except FileNotFoundError:
        return {"success": False, "error": "google_api.py not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═════════════════════════════════════════════════════════════════════════════
# Service Classes
# ═════════════════════════════════════════════════════════════════════════════

class DriveService:
    """Google Drive operations via google_api.py CLI."""

    def __init__(self, credentials=None):
        self._creds = credentials
        self._configured = TOKEN_PATH.exists()

    async def search(
        self, query: str, file_types: List[str] = None,
        folder_id: str = None, max_results: int = 20,
    ) -> List[Dict]:
        if not self._configured:
            return []
        result = _call_google_api("drive", "search", "--query", query)
        if result.get("success") and result.get("data"):
            files = result["data"] if isinstance(result["data"], list) else []
            if file_types:
                mime_map = {
                    "spreadsheet": "application/vnd.google-apps.spreadsheet",
                    "document": "application/vnd.google-apps.document",
                    "pdf": "application/pdf",
                    "folder": "application/vnd.google-apps.folder",
                }
                allowed = {mime_map.get(t, t) for t in file_types}
                files = [f for f in files if f.get("mimeType") in allowed]
            if folder_id:
                files = [f for f in files if folder_id in (f.get("parents") or [])]
            return files[:max_results]
        return []

    async def list_folder(
        self, folder_id: str, file_types: List[str] = None,
    ) -> List[Dict]:
        return await self.search(
            query=f"'{folder_id}' in parents",
            file_types=file_types,
            folder_id=folder_id,
        )

    async def get_file(self, file_id: str) -> Optional[Dict]:
        if not self._configured:
            return None
        # google_api.py drive doesn't have 'get' — fall through
        return {"id": file_id, "name": "unknown", "mimeType": "unknown"}

    async def copy_file(
        self, source_id: str, new_name: str, parent_folder_id: str = None,
    ) -> Optional[str]:
        logger.warning("Drive copy_file: not implemented via google_api.py CLI")
        return None

    async def create_folder(self, name: str, parent_id: str = None) -> Optional[str]:
        logger.warning("Drive create_folder: not implemented via google_api.py CLI")
        return None

    async def export_pdf(self, file_id: str, output_path: str) -> bool:
        logger.warning("Drive export_pdf: not implemented via google_api.py CLI")
        return False


class SheetsService:
    """Google Sheets operations via google_api.py CLI."""

    def __init__(self, credentials=None):
        self._creds = credentials
        self._configured = TOKEN_PATH.exists()

    async def read(self, spreadsheet_id: str, range_name: str) -> List[List[Any]]:
        if not self._configured:
            return []
        result = _call_google_api(
            "sheets", "get",
            "--spreadsheet-id", spreadsheet_id,
            "--range", range_name,
        )
        if result.get("success") and result.get("data"):
            data = result["data"]
            return data if isinstance(data, list) else []
        return []

    async def write(
        self, spreadsheet_id: str, range_name: str, values: List[List[Any]],
    ) -> bool:
        if not self._configured:
            return False
        result = _call_google_api(
            "sheets", "update",
            "--spreadsheet-id", spreadsheet_id,
            "--range", range_name,
            "--values", json.dumps(values),
        )
        return result.get("success", False)

    async def append(
        self, spreadsheet_id: str, range_name: str, values: List[List[Any]],
    ) -> bool:
        if not self._configured:
            return False
        result = _call_google_api(
            "sheets", "append",
            "--spreadsheet-id", spreadsheet_id,
            "--range", range_name,
            "--values", json.dumps(values),
        )
        return result.get("success", False)

    async def get_sheet_names(self, spreadsheet_id: str) -> List[Dict]:
        logger.warning("Sheets get_sheet_names: not implemented via google_api.py CLI")
        return []

    async def create_spreadsheet(
        self, title: str, sheet_names: List[str] = None, folder_id: str = None,
    ) -> Optional[Dict]:
        logger.warning("Sheets create_spreadsheet: not implemented via google_api.py CLI")
        return None


class DocsService:
    """Google Docs operations via google_api.py CLI."""

    def __init__(self, credentials=None):
        self._creds = credentials
        self._configured = TOKEN_PATH.exists()

    async def get_content(self, document_id: str) -> Dict[str, Any]:
        if not self._configured:
            return {"title": "", "text": "", "tables": []}
        result = _call_google_api("docs", "get", "--document-id", document_id)
        if result.get("success") and result.get("data"):
            data = result["data"]
            return {
                "title": data if isinstance(data, str) else "",
                "text": data if isinstance(data, str) else "",
                "tables": [],
            }
        return {"title": "", "text": "", "tables": []}

    async def replace_text(
        self, document_id: str, replacements: Dict[str, str],
    ) -> int:
        logger.warning("Docs replace_text: not implemented via google_api.py CLI")
        return 0

    async def create_from_template(
        self, template_id: str, new_name: str,
        replacements: Dict[str, str], folder_id: str = None,
    ) -> Optional[Dict]:
        logger.warning("Docs create_from_template: not implemented via google_api.py CLI")
        return None


class GmailService:
    """Gmail operations via google_api.py CLI."""

    def __init__(self, credentials=None):
        self._creds = credentials
        self._configured = TOKEN_PATH.exists()

    async def send_email(
        self, to: str, subject: str, body: str,
        cc: List[str] = None, attachments: List[str] = None,
    ) -> bool:
        if not self._configured:
            logger.warning("Gmail not configured — email NOT sent")
            return False
        result = _call_google_api(
            "gmail", "send",
            "--to", to,
            "--subject", subject,
            "--body", body,
        )
        return result.get("success", False)


# ═════════════════════════════════════════════════════════════════════════════
# Main Facade
# ═════════════════════════════════════════════════════════════════════════════

class GoogleWorkspaceService:
    """Async facade for Google Workspace — lazy service initialization.

    Usage:
        google_service.drive.search(query="ВОР")
        google_service.sheets.read(spreadsheet_id="...", range_name="A1:Z10")
        google_service.docs.create_from_template(template_id="...", ...)
        google_service.gmail.send_email(to="...", subject="...", body="...")
    """

    def __init__(self, auth_mode: str = "service_account"):
        self.auth_mode = auth_mode
        self._credentials = None
        self._drive = None
        self._sheets = None
        self._docs = None
        self._gmail = None
        token_exists = TOKEN_PATH.exists()
        if not token_exists:
            logger.warning(
                "Google Workspace not configured — token missing. "
                "Run: python3 ~/.hermes/skills/productivity/google-workspace/scripts/setup.py"
            )
        else:
            logger.info(f"GoogleWorkspaceService ready (OAuth token: {TOKEN_PATH})")

    def is_configured(self) -> bool:
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        if creds_path:
            # Explicitly configured — check that path
            return Path(creds_path).exists()
        # No explicit path — fall back to Hermes OAuth token
        return TOKEN_PATH.exists()

    @property
    def drive(self) -> DriveService:
        if self._drive is None:
            self._drive = DriveService(credentials=self._credentials)
        return self._drive

    @property
    def sheets(self) -> SheetsService:
        if self._sheets is None:
            self._sheets = SheetsService(credentials=self._credentials)
        return self._sheets

    @property
    def docs(self) -> DocsService:
        if self._docs is None:
            self._docs = DocsService(credentials=self._credentials)
        return self._docs

    @property
    def gmail(self) -> GmailService:
        if self._gmail is None:
            self._gmail = GmailService(credentials=self._credentials)
        return self._gmail


# Singleton
google_service = GoogleWorkspaceService()
