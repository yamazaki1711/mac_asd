"""
MAC_ASD v13.0 — Web Interface (P0, May 2026).

Локальный веб-интерфейс для антикризисной команды из 4 человек.
FastAPI + Jinja2 + vanilla JS (Chart.js для дашборда).

Sections:
  - Dashboard (состояние проектов, Delta ИД, алерты)
  - Projects (список, статус, lifecycle)
  - Documents (загрузка, просмотр, drag & drop)
  - HITL (вопросы, ответы, подтверждения)
  - Evidence Graph (визуализация, поиск)
  - Reports (сводки, экспорт)

Start: python -m src.web.app  (or: uvicorn src.web.app:app --host 127.0.0.1 --port 8080)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import settings

logger = logging.getLogger(__name__)

# ── Paths & State ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = Path(settings.BASE_DIR) / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app_state: Dict[str, Any] = {
    "projects": [],
    "documents": [],
    "hitl_sessions": {},
    "alerts": [],
    "started_at": datetime.now().isoformat(),
}

# ── Lifespan ───────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Загрузка существующих проектов и документов при старте."""
    logger.info("MAC_ASD Web UI starting on profile: %s", settings.ASD_PROFILE)

    try:
        from src.db.init_db import Session
        from src.db.models import Project

        with Session() as session:
            db_projects = session.query(Project).all()
            for p in db_projects:
                app_state["projects"].append({
                    "id": p.slug, "slug": p.slug, "name": p.name,
                    "customer": p.customer, "contract_number": p.contract_number,
                    "status": p.status,
                    "created_at": p.created_at.isoformat() if p.created_at else "",
                })
        logger.info("Loaded %d projects from DB", len(db_projects))
    except Exception as e:
        logger.warning("Could not load projects from DB: %s", e)

    graphs_dir = settings.graphs_path
    if graphs_dir.exists():
        for gf in graphs_dir.glob("*.gpickle"):
            pid = gf.stem
            if not _find_project(pid):
                app_state["projects"].append({
                    "id": pid, "slug": pid, "name": pid,
                    "customer": "", "contract_number": "",
                    "status": "active", "created_at": datetime.now().isoformat(),
                })

    logger.info("Startup complete. Projects: %d", len(app_state["projects"]))
    yield
    logger.info("MAC_ASD Web UI shutting down")


# ── App Setup ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="MAC_ASD v13.0",
    version="13.0",
    description="Антикризисное восстановление исполнительной документации",
    lifespan=lifespan,
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGES — HTML
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Главный дашборд — обзор по проектам."""
    return templates.TemplateResponse(request, "dashboard.html", {
        "projects": app_state["projects"],
        "alerts": app_state["alerts"],
    })


@app.get("/dashboard/{project_id}", response_class=HTMLResponse)
async def project_dashboard(request: Request, project_id: str):
    """Дашборд конкретного проекта."""
    project = _find_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    metrics = _compute_project_metrics(project_id)
    return templates.TemplateResponse(request, "project_dashboard.html", {
        "project": project,
        "metrics": metrics,
    })


@app.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request):
    """Список проектов."""
    return templates.TemplateResponse(request, "projects.html", {
        "projects": app_state["projects"],
    })


@app.get("/documents", response_class=HTMLResponse)
async def documents_page(request: Request):
    """Список документов с drag-and-drop загрузкой."""
    return templates.TemplateResponse(request, "documents.html", {
        "documents": app_state["documents"],
    })


@app.get("/hitl", response_class=HTMLResponse)
async def hitl_page(request: Request):
    """HITL-интерфейс — вопросы и ответы."""
    sessions = app_state["hitl_sessions"]
    return templates.TemplateResponse(request, "hitl.html", {
        "sessions": sessions,
    })


@app.get("/hitl/{project_id}", response_class=HTMLResponse)
async def hitl_project(request: Request, project_id: str):
    """HITL для конкретного проекта."""
    session = app_state["hitl_sessions"].get(project_id, {"questions": [], "answered": 0, "total": 0})
    return templates.TemplateResponse(request, "hitl_project.html", {
        "project_id": project_id,
        "session": session,
    })


@app.get("/evidence/{project_id}", response_class=HTMLResponse)
async def evidence_page(request: Request, project_id: str):
    """Evidence Graph визуализация."""
    return templates.TemplateResponse(request, "evidence.html", {
        "project_id": project_id,
    })


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    """Сводные отчёты."""
    return templates.TemplateResponse(request, "reports.html", {})


# ═══════════════════════════════════════════════════════════════════════════════
# REST API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/status")
async def api_status():
    """Общий статус системы."""
    return {
        "version": settings.VERSION,
        "profile": settings.ASD_PROFILE,
        "started_at": app_state["started_at"],
        "projects_count": len(app_state["projects"]),
        "documents_count": len(app_state["documents"]),
        "alerts_count": len(app_state["alerts"]),
    }


@app.get("/api/dashboard")
async def api_dashboard():
    """JSON для дашборда."""
    project_metrics = {}
    for p in app_state["projects"]:
        pid = p.get("id", p.get("slug", str(id(p))))
        project_metrics[pid] = _compute_project_metrics(pid)

    return {
        "projects": app_state["projects"],
        "metrics": project_metrics,
        "alerts": app_state["alerts"],
    }


@app.get("/api/dashboard/{project_id}")
async def api_project_dashboard(project_id: str):
    """JSON для дашборда проекта."""
    return _compute_project_metrics(project_id)


@app.get("/api/hitl/questions/{project_id}")
async def api_hitl_questions(project_id: str):
    """Получить HITL-вопросы для проекта."""
    try:
        from src.core.hitl_system import hitl_system

        session = app_state["hitl_sessions"].get(project_id, {})
        questions = session.get("questions", [])

        if not questions:
            # Попробовать сгенерировать из графа
            from src.core.evidence_graph import EvidenceGraph
            graph = EvidenceGraph()
            graph_path = settings.graphs_path / f"{project_id}.gpickle"
            if graph_path.exists():
                graph.load(graph_path)
                generated = hitl_system.generate_questions(graph)
                questions = [{
                    "id": q.id, "priority": q.priority.value, "qtype": q.qtype.value,
                    "text": q.text, "context": q.context,
                    "suggested_answers": q.suggested_answers,
                    "answered": q.answered, "answer": q.answer,
                } for q in generated]
                app_state["hitl_sessions"][project_id] = {
                    "questions": questions,
                    "answered": sum(1 for q in generated if q.answered),
                    "total": len(generated),
                }
            else:
                questions = _sample_hitl_questions()

        return {"status": "ok", "project_id": project_id, "questions": questions}
    except Exception as e:
        logger.error("HITL questions error: %s", e)
        return {"status": "error", "message": str(e)}


@app.post("/api/hitl/answer")
async def api_hitl_answer(
    project_id: str = Form(...),
    question_id: str = Form(...),
    answer: str = Form(...),
):
    """Применить ответ оператора на HITL-вопрос."""
    try:
        session = app_state["hitl_sessions"].get(project_id, {})
        questions = session.get("questions", [])

        for q in questions:
            if q["id"] == question_id:
                q["answered"] = True
                q["answer"] = answer
                break

        session["answered"] = sum(1 for q in questions if q.get("answered"))
        app_state["hitl_sessions"][project_id] = session

        # Попытаться применить к графу
        try:
            from src.core.hitl_system import hitl_system, HITLQuestion, HITLPriority, QuestionType
            from src.core.evidence_graph import EvidenceGraph
            graph = EvidenceGraph()
            graph_path = settings.graphs_path / f"{project_id}.gpickle"
            if graph_path.exists():
                graph.load(graph_path)
                hq = HITLQuestion(
                    id=question_id,
                    priority=HITLPriority.HIGH,
                    qtype=QuestionType.MISSING_DOCUMENT,
                    text=q["text"],
                    context=q.get("context", ""),
                    suggested_answers=q.get("suggested_answers", []),
                )
                hitl_system.apply_answer(graph, question_id, answer, [hq])
                graph.save(graph_path)
        except Exception as e:
            logger.warning("Graph update skipped: %s", e)

        return {"status": "ok", "message": "Answer applied"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...), project_id: str = Form("default")):
    """Загрузка документа (drag-and-drop)."""
    try:
        file_id = str(uuid.uuid4())[:8]
        safe_name = f"{file_id}_{file.filename}"
        dest = UPLOAD_DIR / safe_name

        content = await file.read()
        dest.write_bytes(content)

        doc_record = {
            "id": file_id,
            "file_name": file.filename,
            "file_size": len(content),
            "project_id": project_id,
            "uploaded_at": datetime.now().isoformat(),
            "status": "uploaded",
            "path": str(dest),
        }
        app_state["documents"].append(doc_record)

        # Запустить ingestion асинхронно (fire-and-forget)
        logger.info("Document uploaded: %s (%d bytes) → %s", file.filename, len(content), dest)

        return {"status": "ok", "document": doc_record}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/upload/batch")
async def api_upload_batch(
    files: List[UploadFile] = File(...),
    project_id: str = Form("default"),
):
    """Массовая загрузка документов."""
    results = []
    for file in files:
        result = await api_upload(file, project_id)
        results.append(result)
    return {"status": "ok", "uploaded": len(results), "results": results}


@app.post("/api/projects")
async def api_create_project(
    name: str = Form(...),
    slug: str = Form(...),
    customer: str = Form(""),
    contract_number: str = Form(""),
):
    """Создать проект."""
    project = {
        "id": slug,
        "slug": slug,
        "name": name,
        "customer": customer,
        "contract_number": contract_number,
        "status": "active",
        "created_at": datetime.now().isoformat(),
    }
    app_state["projects"].append(project)
    app_state["hitl_sessions"][slug] = {"questions": [], "answered": 0, "total": 0}
    return {"status": "ok", "project": project}


@app.get("/api/evidence/summary/{project_id}")
async def api_evidence_summary(project_id: str):
    """Статистика Evidence Graph."""
    try:
        from src.core.evidence_graph import EvidenceGraph
        graph = EvidenceGraph()
        graph_path = settings.graphs_path / f"{project_id}.gpickle"
        if graph_path.exists():
            graph.load(graph_path)
            stats = graph.summary()
            return {"status": "ok", "summary": stats}
        return {"status": "ok", "summary": {"nodes": 0, "edges": 0}, "note": "Graph not found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/projects")
async def api_projects():
    """Список проектов."""
    return {"status": "ok", "projects": app_state["projects"]}


@app.get("/api/documents")
async def api_documents(project_id: Optional[str] = None):
    """Список документов (с фильтром)."""
    docs = app_state["documents"]
    if project_id:
        docs = [d for d in docs if d.get("project_id") == project_id]
    return {"status": "ok", "documents": docs}


@app.get("/api/alerts")
async def api_alerts():
    """Активные алерты."""
    return {"status": "ok", "alerts": app_state["alerts"]}


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _find_project(project_id: str) -> Optional[Dict]:
    for p in app_state["projects"]:
        if p.get("id") == project_id or p.get("slug") == project_id:
            return p
    return None


def _compute_project_metrics(project_id: str) -> Dict[str, Any]:
    """Вычислить метрики проекта."""
    project = _find_project(project_id)
    docs = [d for d in app_state["documents"] if d.get("project_id") == project_id]
    hitl = app_state["hitl_sessions"].get(project_id, {})

    # Try to get chain report
    completeness_pct = 0.0
    chain_stats = {"total": 0, "complete": 0, "partial": 0, "missing": 0}
    try:
        from src.core.chain_builder import chain_builder
        from src.core.evidence_graph import EvidenceGraph
        graph = EvidenceGraph()
        graph_path = settings.graphs_path / f"{project_id}.gpickle"
        if graph_path.exists():
            graph.load(graph_path)
            chains = chain_builder.build_chains(graph)
            report = chain_builder.generate_report(chains)
            completeness_pct = report.completeness_percent
            chain_stats = {
                "total": report.chains_total,
                "complete": report.chains_complete,
                "partial": report.chains_partial,
                "missing": report.chains_missing,
            }
    except Exception as e:
        logger.debug("Chain metrics unavailable for %s: %s", project_id, e)

    return {
        "project_id": project_id,
        "documents_count": len(docs),
        "uploaded_size_mb": round(sum(d.get("file_size", 0) for d in docs) / (1024 * 1024), 2),
        "completeness_pct": completeness_pct,
        "chain_stats": chain_stats,
        "hitl_questions_total": hitl.get("total", 0),
        "hitl_questions_answered": hitl.get("answered", 0),
        "hitl_progress_pct": round(
            hitl.get("answered", 0) / max(hitl.get("total", 1), 1) * 100, 1
        ),
        "status": project.get("status", "unknown") if project else "unknown",
        "alerts": [a for a in app_state["alerts"] if a.get("project_id") == project_id],
    }


def _sample_hitl_questions() -> List[Dict]:
    """Сгенерировать демо-вопросы HITL (fallback)."""
    return [
        {
            "id": "hq_001",
            "priority": "critical",
            "qtype": "missing_document",
            "text": "АОСР на бетонирование ростверка №3 — где находится?",
            "context": "КС-2 подтверждает 45 м³ бетона. АОСР в папке не найден.",
            "suggested_answers": [
                "АОСР подписан, приложу скан",
                "АОСР не оформлялся",
                "Работы не выполнялись",
            ],
            "answered": False,
            "answer": None,
        },
        {
            "id": "hq_002",
            "priority": "high",
            "qtype": "missing_document",
            "text": "Сертификат на арматуру А500С (партия B-045) — где?",
            "context": "Материал использован в армировании. Сертификат в папке не найден.",
            "suggested_answers": [
                "Сертификат есть, приложу скан",
                "Сертификат утерян",
                "Сертификата не было",
            ],
            "answered": False,
            "answer": None,
        },
        {
            "id": "hq_003",
            "priority": "medium",
            "qtype": "missing_date",
            "text": "Когда выполнялись работы «Монтаж колонн К-1..К-6»?",
            "context": "Есть поставка металла 15.03.2026 и КС-2, но даты работ не зафиксированы.",
            "suggested_answers": [
                "Точные даты: 20-25.03.2026",
                "Примерно в марте",
                "Не знаю",
            ],
            "answered": False,
            "answer": None,
        },
        {
            "id": "hq_004",
            "priority": "high",
            "qtype": "missing_document",
            "text": "Исполнительная схема на погружение шпунта — есть?",
            "context": "ГОСТ Р 51872-2024 требует ИС. В папке не найдена.",
            "suggested_answers": [
                "ИС есть, приложу",
                "ИС не делали — нужна съёмка",
            ],
            "answered": False,
            "answer": None,
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="info")
