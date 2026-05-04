"""
Tests for MAC_ASD v13.0 Web UI.

Covers: Items 1-4 (web interface, HITL UI, dashboard, drag-drop upload).
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create TestClient for the FastAPI app."""
    from src.web.app import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_app_state():
    """Reset app_state before each test."""
    from src.web.app import app_state
    app_state["projects"].clear()
    app_state["documents"].clear()
    app_state["hitl_sessions"].clear()
    app_state["alerts"].clear()
    yield


# ═══════════════════════════════════════════════════════════════════════════════
# Item 1: Веб-интерфейс — pages render
# ═══════════════════════════════════════════════════════════════════════════════

class TestWebPages:
    """All HTML pages should return 200."""

    def test_index_redirects(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (200, 307)

    def test_dashboard_page(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "Дашборд" in resp.text

    def test_projects_page(self, client):
        resp = client.get("/projects")
        assert resp.status_code == 200
        assert "Проекты" in resp.text

    def test_documents_page(self, client):
        resp = client.get("/documents")
        assert resp.status_code == 200
        assert "Документы" in resp.text

    def test_hitl_page(self, client):
        resp = client.get("/hitl")
        assert resp.status_code == 200
        assert "HITL" in resp.text

    def test_evidence_page(self, client):
        resp = client.get("/evidence/test-project")
        assert resp.status_code == 200
        assert "Граф" in resp.text

    def test_reports_page(self, client):
        resp = client.get("/reports")
        assert resp.status_code == 200
        assert "Отчёты" in resp.text


# ═══════════════════════════════════════════════════════════════════════════════
# Item 1: API Status
# ═══════════════════════════════════════════════════════════════════════════════

class TestAPIStatus:
    def test_status_endpoint(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "profile" in data
        assert "projects_count" in data
        assert "documents_count" in data

    def test_alerts_endpoint(self, client):
        from src.web.app import app_state
        app_state["alerts"].append({"project_id": "test", "message": "Test alert", "severity": "high"})
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["alerts"]) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Item 1: Project CRUD
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectCRUD:
    def test_create_project(self, client):
        resp = client.post("/api/projects", data={
            "name": "Тестовый проект",
            "slug": "test-prj",
            "customer": "ООО Тест",
            "contract_number": "T-001",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["project"]["name"] == "Тестовый проект"

    def test_list_projects(self, client):
        client.post("/api/projects", data={
            "name": "Проект 1", "slug": "prj1", "customer": "Заказчик"
        })
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["projects"]) == 1

    def test_project_dashboard_page(self, client):
        client.post("/api/projects", data={
            "name": "Проект", "slug": "prj", "customer": "Клиент"
        })
        resp = client.get("/dashboard/prj")
        assert resp.status_code == 200
        assert "Проект" in resp.text

    def test_project_dashboard_404(self, client):
        resp = client.get("/dashboard/nonexistent")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Item 3: Dashboard API
# ═══════════════════════════════════════════════════════════════════════════════

class TestDashboardAPI:
    def test_dashboard_json(self, client):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "projects" in data
        assert "metrics" in data
        assert "alerts" in data

    def test_project_dashboard_json(self, client):
        client.post("/api/projects", data={
            "name": "Dash Project", "slug": "dash", "customer": "C"
        })
        resp = client.get("/api/dashboard/dash")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "dash"
        assert "completeness_pct" in data
        assert "documents_count" in data
        assert "hitl_progress_pct" in data


# ═══════════════════════════════════════════════════════════════════════════════
# Item 4: Drag & Drop Upload
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpload:
    def test_upload_single_file(self, client):
        file_content = b"Test document content"
        resp = client.post(
            "/api/upload",
            files={"file": ("test.pdf", io.BytesIO(file_content), "application/pdf")},
            data={"project_id": "test-project"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["document"]["file_name"] == "test.pdf"
        assert data["document"]["file_size"] == len(file_content)

    def test_upload_batch(self, client):
        files = [
            ("files", ("doc1.pdf", io.BytesIO(b"content1"), "application/pdf")),
            ("files", ("doc2.pdf", io.BytesIO(b"content2"), "application/pdf")),
            ("files", ("doc3.docx", io.BytesIO(b"word content"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ]
        resp = client.post("/api/upload/batch", files=files, data={"project_id": "batch-prj"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["uploaded"] == 3

    def test_list_documents(self, client):
        client.post(
            "/api/upload",
            files={"file": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
            data={"project_id": "p1"},
        )
        resp = client.get("/api/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["documents"]) >= 1

    def test_list_documents_filtered(self, client):
        client.post("/api/upload", files={"file": ("a.pdf", io.BytesIO(b"a"), "application/pdf")}, data={"project_id": "pA"})
        client.post("/api/upload", files={"file": ("b.pdf", io.BytesIO(b"b"), "application/pdf")}, data={"project_id": "pB"})
        resp = client.get("/api/documents?project_id=pA")
        assert resp.status_code == 200
        data = resp.json()
        assert all(d["project_id"] == "pA" for d in data["documents"])


# ═══════════════════════════════════════════════════════════════════════════════
# Item 2: HITL UI API
# ═══════════════════════════════════════════════════════════════════════════════

class TestHITL:
    def test_hitl_questions_fallback(self, client):
        """Without a graph, HITL returns sample questions."""
        resp = client.get("/api/hitl/questions/test-prj")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["questions"]) > 0
        # Check structure
        q = data["questions"][0]
        assert "id" in q
        assert "priority" in q
        assert "text" in q
        assert "suggested_answers" in q

    def test_hitl_answer(self, client):
        """Submit answer to a HITL question."""
        client.get("/api/hitl/questions/test-prj")  # Init questions
        resp = client.post("/api/hitl/answer", data={
            "project_id": "test-prj",
            "question_id": "hq_001",
            "answer": "АОСР подписан, приложу скан",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_hitl_project_page(self, client):
        resp = client.get("/hitl/test-prj")
        assert resp.status_code == 200
        assert "HITL" in resp.text


# ═══════════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_upload_no_file(self, client):
        """Upload without file should fail gracefully."""
        resp = client.post("/api/upload", data={"project_id": "test"})
        assert resp.status_code in (422, 400)

    def test_hitl_nonexistent_project(self, client):
        """HITL for nonexistent project should return sample questions."""
        resp = client.get("/api/hitl/questions/does-not-exist")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["questions"]) > 0

    def test_dashboard_empty_projects(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "Нет активных проектов" in resp.text

    def test_create_project_minimal(self, client):
        resp = client.post("/api/projects", data={"name": "Minimal", "slug": "min"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["project"]["status"] == "active"

    def test_create_project_duplicate_slug(self, client):
        """Duplicate slug creates a second project (no uniqueness enforced in memory)."""
        client.post("/api/projects", data={"name": "A", "slug": "dup"})
        resp = client.post("/api/projects", data={"name": "B", "slug": "dup"})
        assert resp.status_code == 200
        # Both exist
        lst = client.get("/api/projects").json()
        dup_count = sum(1 for p in lst["projects"] if p["slug"] == "dup")
        assert dup_count == 2

    def test_hitl_multiple_answers(self, client):
        """Multiple answers to different questions."""
        client.get("/api/hitl/questions/multi")
        for qid in ["hq_001", "hq_002"]:
            resp = client.post("/api/hitl/answer", data={
                "project_id": "multi",
                "question_id": qid,
                "answer": f"Answer for {qid}",
            })
            assert resp.status_code == 200
