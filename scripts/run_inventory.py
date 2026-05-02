#!/usr/bin/env python3
"""
ASD v12.0 — Inventory Mode Runner.
Сканирует папку с документами → OCR → classify → extract → graph → forensic → отчёт.

Usage:
    PYTHONPATH=. python scripts/run_inventory.py /path/to/folder --project-id 61.17
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("inventory")


def run_inventory(folder: Path, project_id: str = ""):
    """Основной цикл инвентаризации."""
    from src.core.ingestion import IngestionPipeline, DocumentType
    from src.core.graph_service import graph_service

    logger.info("=" * 60)
    logger.info("ИНВЕНТАРИЗАЦИЯ: %s", folder)
    logger.info("Проект: %s", project_id or "не указан")
    logger.info("=" * 60)

    # ── Шаг 1: Сканирование + OCR + Классификация ──────────────────────────
    t0 = time.time()
    pipeline = IngestionPipeline(enable_vlm=args.vlm if hasattr(args, 'vlm') else True)

    # Очищаем граф перед запуском (предотвращает накопление между тестами)
    graph_service.graph.clear()

    docs = pipeline.scan_folder(folder, recursive=True)
    scan_time = time.time() - t0
    logger.info("Шаг 1 (OCR + classify): %d файлов за %.1f сек (%.2f сек/файл)",
                len(docs), scan_time, scan_time / max(len(docs), 1))

    # ── Шаг 2: Заполнение графа ────────────────────────────────────────────
    t0 = time.time()
    nodes_added = pipeline.ingest_to_graph(project_id=project_id)
    graph_time = time.time() - t0
    logger.info("Шаг 2 (Graph): %d узлов за %.1f сек", nodes_added, graph_time)

    # ── Шаг 3: Forensic-проверки ───────────────────────────────────────────
    t0 = time.time()
    forensic_findings = []
    try:
        from src.core.graph_service import graph_service
        forensic_raw = graph_service.run_all_forensic_checks()
        forensic_findings = forensic_raw if isinstance(forensic_raw, list) else forensic_raw.get("findings", [])
        logger.info("Шаг 3 (Forensic): %d находок", len(forensic_findings))
    except Exception as e:
        logger.warning("Forensic checks skipped: %s", e)
    forensic_time = time.time() - t0

    # ── Шаг 3.5: Classification Quality Audit (новые проверки 9-11) ───────
    t0 = time.time()
    class_findings = []
    try:
        from src.core.auditor import AuditorAgent
        auditor = AuditorAgent(llm_engine=None)
        class_findings = auditor._check_classification_quality(state=None)
        # Если документы не загрузились из singleton — передаём явно
        if not class_findings and pipeline.documents:
            from src.core.ingestion import ingestion_pipeline
            ingestion_pipeline.documents = pipeline.documents
            class_findings = auditor._check_classification_quality(state=None)
        logger.info("Шаг 3.5 (Classif. audit): %d находок", len(class_findings))
    except Exception as e:
        logger.warning("Classification audit skipped: %s", e)
    class_audit_time = time.time() - t0

    # ── Шаг 4: Отчёт ───────────────────────────────────────────────────────
    report = pipeline.get_inventory_report()
    report["project_id"] = project_id or folder.name
    report["folder"] = str(folder)
    report["timing"] = {
        "scan_seconds": round(scan_time, 1),
        "graph_seconds": round(graph_time, 1),
        "forensic_seconds": round(forensic_time, 1),
        "class_audit_seconds": round(class_audit_time, 1),
        "total_seconds": round(scan_time + graph_time + forensic_time + class_audit_time, 1),
    }
    report["graph"] = {
        "total_nodes": graph_service.graph.number_of_nodes(),
        "total_edges": graph_service.graph.number_of_edges(),
    }
    report["forensic_findings"] = {
        "total": len(forensic_findings),
        "critical": sum(1 for f in forensic_findings if getattr(f, "severity", "") == "critical"),
        "high": sum(1 for f in forensic_findings if getattr(f, "severity", "") == "high"),
        "medium": sum(1 for f in forensic_findings if getattr(f, "severity", "") == "medium"),
    }

    # Classification quality audit findings
    class_sev = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in class_findings:
        sev = getattr(f, "severity", None)
        k = sev.value.upper() if hasattr(sev, "value") else str(sev).upper()
        class_sev[k] = class_sev.get(k, 0) + 1
    report["classification_audit"] = {
        "total": len(class_findings),
        "critical": class_sev.get("CRITICAL", 0),
        "high": class_sev.get("HIGH", 0),
        "medium": class_sev.get("MEDIUM", 0),
        "low": class_sev.get("LOW", 0),
        "details": [
            {
                "target": f.target_agent,
                "category": f.category,
                "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                "description": f.description,
                "recommendation": f.recommendation,
            }
            for f in class_findings
        ],
    }

    # ── Детализация по типам ───────────────────────────────────────────────
    type_details = {}
    for doc in docs:
        dt = doc.doc_type.value
        if dt not in type_details:
            type_details[dt] = {"count": 0, "high_conf": 0, "low_conf": 0, "avg_pages": 0}
        td = type_details[dt]
        td["count"] += 1
        if doc.classification_confidence >= 0.7:
            td["high_conf"] += 1
        elif doc.classification_confidence < 0.3:
            td["low_conf"] += 1
    report["type_details"] = type_details

    # ── Вывод ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТЫ ИНВЕНТАРИЗАЦИИ")
    print("=" * 60)
    print(f"  Папка:     {folder}")
    print(f"  Проект:    {project_id or 'не указан'}")
    print(f"  Файлов:    {len(docs)}")
    print(f"  Время:     {report['timing']['total_seconds']} сек")
    print(f"  Узлов:     {report['graph']['total_nodes']}")
    print(f"  Связей:    {report['graph']['total_edges']}")

    # VLM stats
    vlm_stats = report.get("vlm_stats", {})
    if vlm_stats:
        print(f"\n  VLM-анализ:")
        print(f"    Сканов обнаружено:  {vlm_stats.get('scanned_detected', 0)}")
        print(f"    VLM-классифицировано: {vlm_stats.get('vlm_classified', 0)}")
        er_count = vlm_stats.get('embedded_reference_count', 0)
        if er_count:
            print(f"    Встроенных ссылок: {er_count} (документы, упомянутые внутри PDF)")
            for ref in vlm_stats.get('embedded_references', []):
                print(f"      ↳ [{ref.get('type', '?')}] {ref.get('identifier', '?')[:80]}")
                print(f"         в: {ref.get('found_in', '?')}")

    print(f"  Находок:   {report['forensic_findings']['total']} "
          f"(крит: {report['forensic_findings']['critical']}, "
          f"выс: {report['forensic_findings']['high']}, "
          f"сред: {report['forensic_findings']['medium']})")

    # Classification audit findings
    ca = report.get("classification_audit", {})
    if ca and ca.get("total", 0) > 0:
        print(f"\n  Аудит классификации:")
        print(f"    Всего находок: {ca['total']} "
              f"(крит: {ca.get('critical',0)}, "
              f"выс: {ca.get('high',0)}, "
              f"сред: {ca.get('medium',0)}, "
              f"низ: {ca.get('low',0)})")
        for d in ca.get("details", [])[:8]:
            sev = d.get("severity", "?").upper()
            desc = d.get("description", "")[:120]
            print(f"    [{sev}] {desc}")
    print()
    print("  Типы документов:")
    for dt, info in sorted(type_details.items(), key=lambda x: -x[1]["count"]):
        bar = "█" * min(info["count"], 40)
        marker = ""
        if info["low_conf"] > info["count"] * 0.5:
            marker = " [низкая уверенность]"
        print(f"    {dt:<25s} {info['count']:>4d}  {bar}{marker}")

    unknown = report.get("unknown_docs", [])
    if unknown:
        print(f"\n  ⚠ Нераспознано: {len(unknown)} файлов")
        for u in unknown[:10]:
            print(f"    - {u}")
        if len(unknown) > 10:
            print(f"    ... и ещё {len(unknown) - 10}")

    # ── Сохранение ─────────────────────────────────────────────────────────
    output_path = Path(f"data/inventory_{project_id or folder.name}_{int(time.time())}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Упрощаем Path-объекты для JSON
    report["unknown_docs"] = [str(Path(p)) for p in unknown]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  Полный отчёт: {output_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ASD Inventory Runner")
    parser.add_argument("folder", help="Путь к папке с документами")
    parser.add_argument("--project-id", default="", help="ID проекта")
    parser.add_argument("--vlm", action="store_true", default=True,
                       help="Использовать VLM для сканированных PDF (по умолчанию: да)")
    parser.add_argument("--no-vlm", action="store_true",
                       help="Отключить VLM-классификацию")
    args = parser.parse_args()

    if args.no_vlm:
        args.vlm = False

    folder = Path(args.folder)
    if not folder.exists():
        print(f"ERROR: папка не найдена: {folder}")
        sys.exit(1)

    report = run_inventory(folder, args.project_id)
