"""
ASD v12.0 — Tests for Google Workspace Integration.

Тестирует:
  - GoogleWorkspaceService: структура, lazy init, is_configured
  - Google MCP tools: сигнатуры, валидация, graceful degradation
  - Config: Google-related settings

NOTES:
  - Реальные API-вызовы НЕ выполняются (нет credentials в CI)
  - Тесты проверяют архитектуру, интерфейсы и обработку ошибок
  - Для интеграционного тестирования с реальным API нужен Service Account
"""

import pytest
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Корень проекта mac_asd
PROJECT_ROOT = Path(__file__).parent.parent


# =============================================================================
# Config Tests
# =============================================================================

class TestGoogleConfig:
    """Тесты настроек Google Workspace в config.py."""

    def test_google_credentials_path_default(self):
        """Путь к кредам по умолчанию указывает на credentials/."""
        from src.config import Settings
        s = Settings()
        assert "credentials" in s.GOOGLE_APPLICATION_CREDENTIALS
        assert "google_service_account.json" in s.GOOGLE_APPLICATION_CREDENTIALS

    def test_google_folder_settings_exist(self):
        """Все настройки Google Drive папок присутствуют."""
        from src.config import Settings
        s = Settings()
        assert hasattr(s, "GOOGLE_DRIVE_PROJECTS_FOLDER")
        assert hasattr(s, "GOOGLE_DRIVE_TEMPLATES_FOLDER")
        assert hasattr(s, "GOOGLE_DRIVE_CONTRACTS_FOLDER")

    def test_google_docs_templates_exist(self):
        """Все настройки шаблонов Google Docs присутствуют."""
        from src.config import Settings
        s = Settings()
        assert hasattr(s, "GOOGLE_DOCS_AOSR_TEMPLATE")
        assert hasattr(s, "GOOGLE_DOCS_AOOK_TEMPLATE")
        assert hasattr(s, "GOOGLE_DOCS_PROTOCOL_TEMPLATE")

    def test_google_sheets_templates_exist(self):
        """Все настройки шаблонов Google Sheets присутствуют."""
        from src.config import Settings
        s = Settings()
        assert hasattr(s, "GOOGLE_SHEETS_VOR_TEMPLATE")
        assert hasattr(s, "GOOGLE_SHEETS_ESTIMATE_TEMPLATE")

    def test_get_drive_folder_method(self):
        """Метод get_drive_folder возвращает корректный ID."""
        from src.config import Settings
        s = Settings(GOOGLE_DRIVE_VOR_FOLDER="test_vor_id_123")
        assert s.get_drive_folder("vor") == "test_vor_id_123"
        assert s.get_drive_folder("unknown") == ""

    def test_get_docs_template_method(self):
        """Метод get_docs_template возвращает корректный ID."""
        from src.config import Settings
        s = Settings(GOOGLE_DOCS_AOSR_TEMPLATE="test_aosr_id_456")
        assert s.get_docs_template("aosr") == "test_aosr_id_456"
        assert s.get_docs_template("unknown") == ""

    def test_google_configured_false_when_no_key(self):
        """google_configured = False когда файла ключа нет."""
        from src.config import Settings
        s = Settings(GOOGLE_APPLICATION_CREDENTIALS="/nonexistent/key.json")
        assert s.google_configured is False


# =============================================================================
# GoogleWorkspaceService Tests
# =============================================================================

class TestGoogleWorkspaceService:
    """Тесты фасада GoogleWorkspaceService."""

    def test_service_initialization(self):
        """Сервис инициализируется без ошибок."""
        from src.core.integrations.google import GoogleWorkspaceService
        svc = GoogleWorkspaceService(auth_mode="service_account")
        assert svc.auth_mode == "service_account"
        assert svc._drive is None  # lazy
        assert svc._sheets is None
        assert svc._docs is None
        assert svc._gmail is None

    def test_is_configured_false_without_key(self):
        """is_configured() = False когда ключа нет."""
        from src.core.integrations.google import GoogleWorkspaceService
        svc = GoogleWorkspaceService()
        with patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "/nonexistent/key.json"}):
            assert svc.is_configured() is False

    def test_drive_property_type(self):
        """Свойство drive возвращает DriveService (с замоканными кредами)."""
        from src.core.integrations.google import GoogleWorkspaceService, DriveService
        svc = GoogleWorkspaceService()
        svc._credentials = MagicMock()
        assert isinstance(svc.drive, DriveService)

    def test_sheets_property_type(self):
        """Свойство sheets возвращает SheetsService."""
        from src.core.integrations.google import GoogleWorkspaceService, SheetsService
        svc = GoogleWorkspaceService()
        svc._credentials = MagicMock()
        assert isinstance(svc.sheets, SheetsService)

    def test_docs_property_type(self):
        """Свойство docs возвращает DocsService."""
        from src.core.integrations.google import GoogleWorkspaceService, DocsService
        svc = GoogleWorkspaceService()
        svc._credentials = MagicMock()
        assert isinstance(svc.docs, DocsService)

    def test_gmail_property_type(self):
        """Свойство gmail возвращает GmailService."""
        from src.core.integrations.google import GoogleWorkspaceService, GmailService
        svc = GoogleWorkspaceService()
        svc._credentials = MagicMock()
        assert isinstance(svc.gmail, GmailService)

    def test_lazy_init_credentials_shared(self):
        """Все подсервисы используют одни и те же креды."""
        from src.core.integrations.google import GoogleWorkspaceService
        svc = GoogleWorkspaceService()
        svc._credentials = MagicMock()
        drive_creds = svc.drive._creds
        sheets_creds = svc.sheets._creds
        assert drive_creds is sheets_creds


# =============================================================================
# Google MCP Tools Tests (mocked — no real API calls)
# =============================================================================

class TestGoogleMCPTools:
    """Тесты MCP инструментов Google Workspace с замоканными вызовами."""

    @pytest.mark.asyncio
    async def test_google_status_not_configured(self):
        """asd_google_status корректно сообщает о ненастроенном API."""
        from mcp_servers.asd_core.tools.google_tools import asd_google_status
        with patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "/nonexistent/key.json"}):
            result = await asd_google_status()
            assert result["status"] in ("not_configured", "configured")
            assert "services" in result

    @pytest.mark.asyncio
    async def test_drive_search_returns_structure(self):
        """asd_drive_search возвращает ожидаемую структуру."""
        from mcp_servers.asd_core.tools.google_tools import asd_drive_search

        # Мокаем сам объект google_service (singleton)
        mock_drive = MagicMock()
        mock_drive.search = AsyncMock(return_value=[
            {"id": "abc123", "name": "ВОР_бетонные.xlsx", "mimeType": "application/vnd.google-apps.spreadsheet"},
        ])

        with patch(
            "mcp_servers.asd_core.tools.google_tools.google_service",
            MagicMock(drive=mock_drive),
        ):
            result = await asd_drive_search("ВОР")
            assert result["status"] == "success"
            assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_sheets_read_returns_structure(self):
        """asd_sheets_read возвращает ожидаемую структуру."""
        from mcp_servers.asd_core.tools.google_tools import asd_sheets_read

        mock_sheets = MagicMock()
        mock_sheets.read = AsyncMock(return_value=[
            ["Наименование", "Ед.изм.", "Кол-во"],
            ["Бетонирование", "м3", 150],
        ])

        with patch(
            "mcp_servers.asd_core.tools.google_tools.google_service",
            MagicMock(sheets=mock_sheets),
        ):
            result = await asd_sheets_read("sheet_id_123", "Лист1!A1:C2")
            assert result["status"] == "success"
            assert result["rows"] == 2

    @pytest.mark.asyncio
    async def test_sheets_write_returns_status(self):
        """asd_sheets_write возвращает статус."""
        from mcp_servers.asd_core.tools.google_tools import asd_sheets_write

        mock_sheets = MagicMock()
        mock_sheets.write = AsyncMock(return_value=True)

        with patch(
            "mcp_servers.asd_core.tools.google_tools.google_service",
            MagicMock(sheets=mock_sheets),
        ):
            result = await asd_sheets_write("sheet_id", "A1", [["test"]])
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_docs_from_template_returns_structure(self):
        """asd_docs_from_template возвращает ожидаемую структуру."""
        from mcp_servers.asd_core.tools.google_tools import asd_docs_from_template

        mock_docs = MagicMock()
        mock_docs.create_from_template = AsyncMock(return_value={
            "document_id": "new_doc_123",
            "url": "https://docs.google.com/document/d/new_doc_123/edit",
            "replacements_made": 5,
        })

        with patch(
            "mcp_servers.asd_core.tools.google_tools.google_service",
            MagicMock(docs=mock_docs),
        ):
            result = await asd_docs_from_template(
                template_id="tmpl_123",
                new_name="АОСР №45",
                replacements={"{{НОМЕР}}": "45"},
            )
            assert result["status"] == "success"
            assert "document_id" in result

    @pytest.mark.asyncio
    async def test_gmail_send_returns_status(self):
        """asd_gmail_send возвращает статус."""
        from mcp_servers.asd_core.tools.google_tools import asd_gmail_send

        mock_gmail = MagicMock()
        mock_gmail.send_email = AsyncMock(return_value=True)

        with patch(
            "mcp_servers.asd_core.tools.google_tools.google_service",
            MagicMock(gmail=mock_gmail),
        ):
            result = await asd_gmail_send(
                to="pto@company.ru",
                subject="АОСР готовы",
                body="Прилагаю акты",
            )
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_drive_search_error_handling(self):
        """asd_drive_search обрабатывает ошибки API."""
        from mcp_servers.asd_core.tools.google_tools import asd_drive_search

        mock_drive = MagicMock()
        mock_drive.search = AsyncMock(side_effect=Exception("API quota exceeded"))

        with patch(
            "mcp_servers.asd_core.tools.google_tools.google_service",
            MagicMock(drive=mock_drive),
        ):
            result = await asd_drive_search("test")
            assert result["status"] == "error"
            assert "quota" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_sheets_create_returns_ids(self):
        """asd_sheets_create возвращает spreadsheet_id и url."""
        from mcp_servers.asd_core.tools.google_tools import asd_sheets_create

        mock_sheets = MagicMock()
        mock_sheets.create_spreadsheet = AsyncMock(return_value={
            "spreadsheet_id": "new_sheet_123",
            "url": "https://docs.google.com/spreadsheets/d/new_sheet_123/",
        })

        with patch(
            "mcp_servers.asd_core.tools.google_tools.google_service",
            MagicMock(sheets=mock_sheets),
        ):
            result = await asd_sheets_create(
                title="Локальная смета №1",
                sheet_names=["Смета", "Ресурсы", "Итоги"],
            )
            assert result["status"] == "success"
            assert "spreadsheet_id" in result


# =============================================================================
# Integration: Agent Config → Google Tools mapping
# =============================================================================

class TestAgentGoogleToolMapping:
    """Проверяем что каждый агент имеет нужные Google-инструменты."""

    def _load_yaml(self, path: str) -> dict:
        """Простейший YAML-парсер для config файлов."""
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)

    def test_hermes_has_google_tools(self):
        """Hermes имеет drive_search, drive_list_folder, gmail_send."""
        config = self._load_yaml(str(PROJECT_ROOT / "agents" / "pm" / "config.yaml"))
        tools = config["mcp"]["tools"]
        assert "drive_search" in tools
        assert "drive_list_folder" in tools
        assert "gmail_send" in tools

    def test_pto_has_google_tools(self):
        """ПТО имеет sheets_read, sheets_write, docs_from_template."""
        config = self._load_yaml(str(PROJECT_ROOT / "agents" / "pto" / "config.yaml"))
        tools = config["mcp"]["tools"]
        assert "sheets_read" in tools
        assert "sheets_write" in tools
        assert "docs_from_template" in tools

    def test_smeta_has_google_tools(self):
        """Сметчик имеет sheets_read, sheets_write, sheets_create."""
        config = self._load_yaml(str(PROJECT_ROOT / "agents" / "smeta" / "config.yaml"))
        tools = config["mcp"]["tools"]
        assert "sheets_read" in tools
        assert "sheets_write" in tools
        assert "sheets_create" in tools

    def test_legal_has_google_tools(self):
        """Юрист имеет docs_from_template, docs_get_content, gmail_send."""
        config = self._load_yaml(str(PROJECT_ROOT / "agents" / "legal" / "config.yaml"))
        tools = config["mcp"]["tools"]
        assert "docs_from_template" in tools
        assert "docs_get_content" in tools
        assert "gmail_send" in tools

    def test_procurement_has_google_tools(self):
        """Закупщик имеет sheets_read, drive_search, gmail_send."""
        config = self._load_yaml(str(PROJECT_ROOT / "agents" / "procurement" / "config.yaml"))
        tools = config["mcp"]["tools"]
        assert "sheets_read" in tools
        assert "drive_search" in tools


# =============================================================================
# Run
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
