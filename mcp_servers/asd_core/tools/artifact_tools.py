"""
ASD v12.0 — Artifact MCP Tools.

File-based artifact store with versioning.
Artifacts live under data/artifacts/{project_id}/{doc_type}/{filename}.v{version}.json
Registry at data/artifacts/registry.json
"""

import json
import os
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_ARTIFACT_BASE = Path("data/artifacts")
_REGISTRY_PATH = _ARTIFACT_BASE / "registry.json"


def _load_registry() -> dict:
    """Load artifact registry."""
    if _REGISTRY_PATH.exists():
        try:
            return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load registry: %s", e)
    return {"artifacts": {}, "metadata": {"initialized": datetime.now(timezone.utc).isoformat()}}


def _save_registry(registry: dict) -> None:
    """Persist artifact registry."""
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


async def artifact_list(
    project_id: Optional[str] = None,
    doc_type: Optional[str] = None,
) -> dict:
    """
    Список зарегистрированных артефактов.

    Args:
        project_id: Фильтр по проекту.
        doc_type: Фильтр по типу (aosr|ks2|ks3|certificate|drawing|legal...).

    Returns:
        dict со списком артефактов и их метаданными.
    """
    registry = _load_registry()
    items = []

    for artifact_id, info in registry.get("artifacts", {}).items():
        if project_id and info.get("project_id") != project_id:
            continue
        if doc_type and info.get("doc_type") != doc_type:
            continue
        items.append({
            "artifact_id": artifact_id,
            "project_id": info.get("project_id"),
            "doc_type": info.get("doc_type"),
            "filename": info.get("filename"),
            "current_version": info.get("current_version", 1),
            "updated_at": info.get("updated_at"),
        })

    return {
        "status": "ok",
        "count": len(items),
        "items": sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True),
    }


async def artifact_write(
    project_id: str,
    doc_type: str,
    filename: str,
    content: str,
    version: Optional[int] = None,
) -> dict:
    """
    Записать артефакт с версионированием.

    Args:
        project_id: ID проекта.
        doc_type: Тип документа (aosr, ks2, ks3, certificate, invoice, etc.).
        filename: Имя файла.
        content: Содержимое.
        version: Номер версии (авто-инкремент если None).

    Returns:
        dict с информацией о записанном артефакте.
    """
    registry = _load_registry()
    artifact_id = f"{project_id}/{doc_type}/{filename}"

    # Determine version
    if version is None:
        existing = registry["artifacts"].get(artifact_id, {})
        current = existing.get("current_version", 0)
        version = current + 1

    # Write artifact file
    artifact_dir = _ARTIFACT_BASE / project_id / doc_type
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{filename}.v{version}.json"
    artifact_path.write_text(content, encoding="utf-8")

    # Update registry
    now = datetime.now(timezone.utc).isoformat()
    registry["artifacts"][artifact_id] = {
        "project_id": project_id,
        "doc_type": doc_type,
        "filename": filename,
        "current_version": version,
        "versions": list(range(1, version + 1)),
        "created_at": registry["artifacts"].get(artifact_id, {}).get("created_at", now),
        "updated_at": now,
    }
    _save_registry(registry)

    logger.info("Artifact written: %s v%d (%s)", artifact_id, version, artifact_path)

    return {
        "status": "ok",
        "artifact_id": artifact_id,
        "project_id": project_id,
        "doc_type": doc_type,
        "filename": filename,
        "version": version,
        "path": str(artifact_path),
        "updated_at": now,
    }


async def artifact_read(
    project_id: str,
    doc_type: str,
    filename: str,
    version: Optional[int] = None,
) -> dict:
    """
    Получить содержимое конкретной версии артефакта.

    Args:
        project_id: ID проекта.
        doc_type: Тип документа.
        filename: Имя файла.
        version: Номер версии (None = последняя).

    Returns:
        dict с содержимым и метаданными версии.
    """
    registry = _load_registry()
    artifact_id = f"{project_id}/{doc_type}/{filename}"
    info = registry["artifacts"].get(artifact_id)

    if info is None:
        return {"status": "not_found", "artifact_id": artifact_id}

    if version is None:
        version = info["current_version"]

    artifact_path = _ARTIFACT_BASE / project_id / doc_type / f"{filename}.v{version}.json"
    if not artifact_path.exists():
        return {"status": "not_found", "artifact_id": artifact_id, "version": version}

    content = artifact_path.read_text(encoding="utf-8")

    return {
        "status": "ok",
        "artifact_id": artifact_id,
        "project_id": project_id,
        "doc_type": doc_type,
        "filename": filename,
        "version": version,
        "content": content,
        "versions_available": info.get("versions", [version]),
        "current_version": info.get("current_version", version),
        "updated_at": info.get("updated_at"),
    }


# Alias for backward compatibility
artifact_version = artifact_read
