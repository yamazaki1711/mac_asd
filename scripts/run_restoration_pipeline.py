"""
ASD v12.0 — Pipeline восстановления исполнительной документации на ОКС.

Полный сценарий антикризисного восстановления ИД:
  Инвентаризация → ProjectLoader → Inference → Chain Builder → HITL → Journal Reconstructor

Этапы:
  1. Ingestion Pipeline — сканирование папки, OCR, классификация, VLM-фолбэк
  2. Evidence Graph — заполнение единого графа доказательств
  3. ProjectLoader — нулевой слой: плановые WorkUnit из ПД/РД
  4. Inference Engine — 6 symbolic-правил вывода дат/фактов
  5. Chain Builder — построение документальных цепочек, выявление разрывов
  6. HITL System — генерация вопросов оператору
  7. Journal Reconstructor v2 — восстановление ОЖР с цветовой разметкой

Usage:
  PYTHONPATH=. python scripts/run_restoration_pipeline.py \
    --project-dir data/test_projects/LOS --project-id LOS --vlm

  PYTHONPATH=. python scripts/run_restoration_pipeline.py \
    --project-id SK-2025  # использует существующий граф
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("restoration_pipeline")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

DOC_TYPE_MAP = {
    "aosr": "aosr",
    "certificate": "certificate",
    "passport": "passport",
    "ttn": "ttn",
    "ks2": "ks2",
    "ks3": "ks3",
    "ks6a": "ks6a",
    "vor": "vor",
    "contract": "contract",
    "letter": "letter",
    "photo": "photo",
    "journal": "journal",
    "executive_scheme": "executive_scheme",
    "drawing": "drawing",
    "protocol": "protocol",
    "invoice": "invoice",
    "upd": "upd",
    "unknown": "unknown",
}

CONFIDENCE_COLORS = {
    (0.8, 1.0): "green",
    (0.6, 0.8): "yellow",
    (0.4, 0.6): "red",
    (0.0, 0.4): "gray",
}

def _confidence_color(conf: float) -> str:
    for (lo, hi), color in CONFIDENCE_COLORS.items():
        if lo <= conf < hi or (hi == 1.0 and conf == 1.0):
            return color
    return "gray"


def _first_str(value, default=""):
    """Извлечь первое строковое значение из списка или скаляра."""
    if isinstance(value, list):
        return str(value[0]) if value else default
    return str(value) if value else default


def _first_float(value, default=0.0):
    """Извлечь первое float-значение."""
    if isinstance(value, list):
        if value:
            try:
                return float(value[0])
            except (ValueError, TypeError):
                return default
        return default
    try:
        return float(value) if value else default
    except (ValueError, TypeError):
        return default


# ═══════════════════════════════════════════════════════════════════════════
# Этап 1: Инвентаризация папки проекта
# ═══════════════════════════════════════════════════════════════════════════

def run_ingestion(project_dir: str, project_id: str, enable_vlm: bool = False):
    """Сканировать папку, классифицировать, извлечь сущности."""
    from src.core.ingestion import IngestionPipeline

    print("\n" + "=" * 70)
    print("ЭТАП 1: ИНВЕНТАРИЗАЦИЯ ДОКУМЕНТОВ")
    print("=" * 70)

    pipeline = IngestionPipeline(enable_vlm=enable_vlm)

    print(f"  Папка: {project_dir}")
    project_path = Path(project_dir)
    if not project_path.exists():
        raise FileNotFoundError(f"Папка не найдена: {project_dir}")

    docs = pipeline.scan_folder(project_path, recursive=True)
    report = pipeline.get_inventory_report()

    print(f"  Обработано: {report['total_processed']} файлов")
    print(f"  Типы документов:")
    for dt, count in sorted(report.get("doc_types_found", {}).items(), key=lambda x: -x[1]):
        print(f"    {dt}: {count}")

    if report.get("vlm_stats"):
        vs = report["vlm_stats"]
        print(f"  VLM: {vs.get('vlm_classified', 0)} переклассификаций, "
              f"{vs.get('embedded_refs_found', 0)} встроенных ссылок")

    # Классификация по файлам
    print(f"\n  Классификация:")
    for doc in docs:
        marker = " [VLM]" if getattr(doc, "vlm_classified", False) else ""
        print(f"    {doc.file_path.name:40s} → {doc.doc_type.value:20s} "
              f"conf={doc.classification_confidence:.2f}{marker}")

    return pipeline, docs, report


# ═══════════════════════════════════════════════════════════════════════════
# Этап 2: Заполнение Evidence Graph
# ═══════════════════════════════════════════════════════════════════════════

def populate_evidence_graph(
    docs: list,
    project_id: str,
    eg,
) -> int:
    """Заполнить Evidence Graph v2 извлечёнными документами."""
    from src.core.evidence_graph import DocType as EGDocType, EvidenceDocStatus, EdgeType
    from src.core.ingestion import DocumentType

    print("\n" + "=" * 70)
    print("ЭТАП 2: ЗАПОЛНЕНИЕ EVIDENCE GRAPH v2")
    print("=" * 70)

    # Карта типов: DocumentType (ingestion) → DocType (evidence_graph)
    type_map = {
        DocumentType.AOSR: EGDocType.AOSR,
        DocumentType.AOOK: EGDocType.AOSR,  # АООК → AOSR (ближайший аналог)
        DocumentType.CERTIFICATE: EGDocType.CERTIFICATE,
        DocumentType.TTN: EGDocType.TTN,
        DocumentType.KS2: EGDocType.KS2,
        DocumentType.KS3: EGDocType.KS3,
        DocumentType.VOR: EGDocType.VOR,
        DocumentType.CONTRACT: EGDocType.CONTRACT,
        DocumentType.LETTER: EGDocType.LETTER,
        DocumentType.EMAIL: EGDocType.LETTER,
        DocumentType.JOURNAL: EGDocType.JOURNAL,
        DocumentType.EXECUTIVE_SCHEME: EGDocType.EXECUTIVE_SCHEME,
        DocumentType.DRAWING: EGDocType.DRAWING,
        DocumentType.UPD: EGDocType.UPD,
        DocumentType.CLAIM: EGDocType.LETTER,
        DocumentType.PHOTO: EGDocType.PHOTO,
        DocumentType.UNKNOWN: EGDocType.UNKNOWN,
    }

    nodes_added = 0
    for idx, doc in enumerate(docs):
        entities = doc.entities or {}
        etype = type_map.get(doc.doc_type, EGDocType.UNKNOWN)

        # Извлечение полей
        doc_number = _first_str(entities.get("document_number", "") or
                                entities.get("doc_number", ""))
        doc_date_str = _first_str(entities.get("date", "") or
                                  entities.get("doc_date", ""))
        mat_name = _first_str(entities.get("material_name", ""))
        batch_num = _first_str(entities.get("batch_number", ""))
        batch_qty = _first_float(entities.get("batch_size", 0.0) or
                                 entities.get("quantity", 0.0))
        unit = _first_str(entities.get("unit", ""))
        supplier = _first_str(entities.get("supplier_name", ""))
        gost = _first_str(entities.get("gost", ""))
        work_type = _first_str(entities.get("work_type", ""))

        # Конвертация даты
        doc_date = None
        if doc_date_str:
            for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    doc_date = datetime.strptime(doc_date_str, fmt).date()
                    break
                except ValueError:
                    continue

        try:
            # Создать Document узел
            doc_id = eg.add_document(
                doc_type=etype,
                doc_number=doc_number or f"extracted_{idx}",
                doc_date=doc_date,
                file_path=str(doc.file_path),
                content_summary=(doc.raw_text or "")[:500],
                signatures_present=False,
                stamps_present=False,
                confidence=doc.classification_confidence,
                status=EvidenceDocStatus.SCAN,
            )
            nodes_added += 1

            # Если есть материал — создать MaterialBatch
            if mat_name:
                mat_id = eg.add_material_batch(
                    material_name=mat_name,
                    batch_number=batch_num,
                    quantity=batch_qty,
                    unit=unit,
                    gost=gost,
                    supplier=supplier,
                    delivery_date=doc_date,
                    confidence=doc.classification_confidence,
                )
                eg.link(mat_id, doc_id, EdgeType.REFERENCES)
                nodes_added += 1

            # Если АОСР с work_type — создать WorkUnit
            if etype == EGDocType.AOSR and work_type:
                from src.core.evidence_graph import WorkUnitStatus, FactSource, EdgeType as EGEdgeType
                wu_id = eg.add_work_unit(
                    work_type=work_type,
                    description=f"По АОСР: {doc_number}",
                    status=WorkUnitStatus.COMPLETED,
                    confidence=doc.classification_confidence,
                    source=FactSource.AGENT,
                    start_date=doc_date,
                )
                eg.link(wu_id, doc_id, EGEdgeType.CONFIRMED_BY)
                if mat_name:
                    for nid, ndata in eg.graph.nodes(data=True):
                        if ndata.get("node_type") == "MaterialBatch" and ndata.get("material_name") == mat_name:
                            eg.link(wu_id, nid, EGEdgeType.USED_IN)
                            break
                nodes_added += 1

        except Exception as e:
            import traceback
            logger.error("Evidence Graph: не удалось добавить %s: %s\n%s",
                        doc.file_path.name, e, traceback.format_exc())

    eg.save()
    print(f"  Узлов в графе: {eg.graph.number_of_nodes()}")
    print(f"  Рёбер в графе: {eg.graph.number_of_edges()}")
    print(f"  Добавлено: {nodes_added}")
    return nodes_added


# ═══════════════════════════════════════════════════════════════════════════
# Этап 3: ProjectLoader — плановые WorkUnit
# ═══════════════════════════════════════════════════════════════════════════

def run_project_loader(project_dir: str, project_id: str, eg):
    """Загрузить ПД/РД → плановое дерево WorkUnit."""
    from src.core.project_loader import project_loader

    print("\n" + "=" * 70)
    print("ЭТАП 3: PROJECT LOADER — ПЛАНОВЫЕ WORKUNIT")
    print("=" * 70)

    project_path = Path(project_dir)
    try:
        summary = project_loader.load_from_folder(eg, str(project_path))
        print(f"  WorkUnit'ов создано: {summary.get('work_units', 0)}")
        print(f"  MaterialBatch создано: {summary.get('material_batches', 0)}")
        print(f"  Документов REFERENCED: {summary.get('documents', 0)}")
    except Exception as e:
        logger.warning("ProjectLoader: %s (пропускаем)", e)
        print(f"  ⚠️ ProjectLoader не отработал: {e} (нужны файлы ПД/РД)")


# ═══════════════════════════════════════════════════════════════════════════
# Этап 4: Inference Engine
# ═══════════════════════════════════════════════════════════════════════════

def run_inference(eg):
    """Запустить symbolic inference на Evidence Graph."""
    from src.core.inference_engine import inference_engine

    print("\n" + "=" * 70)
    print("ЭТАП 4: INFERENCE ENGINE — ВЫВОД ФАКТОВ")
    print("=" * 70)

    inferred = inference_engine.run_all(eg)
    print(f"  Выведено фактов: {len(inferred)}")
    for fact in inferred[:10]:  # Ограничить вывод
        desc = getattr(fact, 'description', str(fact))
        rule = getattr(fact, 'rule_name', '?')
        print(f"    [{rule}] {desc[:120]}")
    if len(inferred) > 10:
        print(f"    ...и ещё {len(inferred) - 10}")
    return inferred


# ═══════════════════════════════════════════════════════════════════════════
# Этап 5: Chain Builder
# ═══════════════════════════════════════════════════════════════════════════

def run_chain_builder(eg):
    """Построить документальные цепочки, выявить разрывы."""
    from src.core.chain_builder import chain_builder, ChainStatus

    print("\n" + "=" * 70)
    print("ЭТАП 5: CHAIN BUILDER — ДОКУМЕНТАЛЬНЫЕ ЦЕПОЧКИ")
    print("=" * 70)

    chains = chain_builder.build_chains(eg)

    complete = [c for c in chains if c.status == ChainStatus.COMPLETE]
    partial = [c for c in chains if c.status == ChainStatus.PARTIAL]
    broken = [c for c in chains if c.status == ChainStatus.BROKEN]
    empty = [c for c in chains if c.status == ChainStatus.EMPTY]

    print(f"  Цепочек всего:   {len(chains)}")
    print(f"    COMPLETE:  {len(complete)}")
    print(f"    PARTIAL:   {len(partial)}")
    print(f"    BROKEN:    {len(broken)}")
    print(f"    EMPTY:     {len(empty)}")

    all_gaps = []
    for chain in partial + broken:
        print(f"\n  [{chain.status.value.upper()}] {chain.work_type[:50]}")
        print(f"    confidence={chain.confidence:.2f}")
        for gap in chain.gaps:
            print(f"    {gap.severity.value.upper():8s}: {gap.description}")
            all_gaps.append(gap)

    return chains, all_gaps


# ═══════════════════════════════════════════════════════════════════════════
# Этап 6: HITL System
# ═══════════════════════════════════════════════════════════════════════════

def run_hitl(eg, all_chains: list, output_dir: Path):
    """Сгенерировать вопросы оператору."""
    from src.core.hitl_system import hitl_system, HITLPriority
    from src.core.chain_builder import ChainReport

    print("\n" + "=" * 70)
    print("ЭТАП 6: HITL SYSTEM — ВОПРОСЫ ОПЕРАТОРУ")
    print("=" * 70)

    # Создать ChainReport из списка цепочек
    chain_report = ChainReport(chains=all_chains)
    questions = hitl_system.generate_questions(eg, chain_report=chain_report)

    crit = [q for q in questions if q.priority == HITLPriority.CRITICAL]
    high = [q for q in questions if q.priority == HITLPriority.HIGH]
    med = [q for q in questions if q.priority == HITLPriority.MEDIUM]
    low = [q for q in questions if q.priority == HITLPriority.LOW]

    print(f"  Всего вопросов: {len(questions)}")
    print(f"    CRITICAL: {len(crit)}")
    print(f"    HIGH:     {len(high)}")
    print(f"    MEDIUM:   {len(med)}")
    print(f"    LOW:      {len(low)}")

    for q in crit + high[:5]:
        print(f"\n  [{q.priority.value.upper()}] {q.text[:120]}")
        print(f"    Тип: {q.qtype.value} | Узлы: {q.graph_nodes}")

    # Сохранить вопросы в JSON для Telegram
    q_json = output_dir / f"hitl_questions_{datetime.now():%Y%m%d_%H%M%S}.json"
    q_json.parent.mkdir(parents=True, exist_ok=True)
    q_data = [
        {
            "id": q.id,
            "priority": q.priority.value,
            "qtype": q.qtype.value,
            "text": q.text,
            "context": q.context,
            "graph_nodes": q.graph_nodes,
            "suggested_answers": q.suggested_answers,
        }
        for q in questions
    ]
    q_json.write_text(json.dumps(q_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  📋 Вопросы сохранены: {q_json}")

    return questions


# ═══════════════════════════════════════════════════════════════════════════
# Этап 7: Journal Reconstructor v2
# ═══════════════════════════════════════════════════════════════════════════

def run_journal_reconstructor(eg, output_dir: Path):
    """Восстановить Общий Журнал Работ."""
    from src.core.journal_reconstructor import journal_reconstructor

    print("\n" + "=" * 70)
    print("ЭТАП 7: JOURNAL RECONSTRUCTOR v2 — ВОССТАНОВЛЕНИЕ ОЖР")
    print("=" * 70)

    journal = journal_reconstructor.reconstruct(eg)

    print(f"  Записей:      {journal.total_entries}")
    print(f"  Период:       {journal.start_date} – {journal.end_date}")
    print(f"  Покрытие:     {journal.coverage:.1%}")
    print(f"  Подтверждено: {journal.confirmed_entries}")
    print(f"  Высокая ув.:  {journal.high_entries}")
    print(f"  Низкая ув.:   {journal.low_entries}")
    print(f"  Выведено:     {journal.inferred_entries}")

    # Таблица
    table = journal_reconstructor.format_journal_table(journal, max_entries=25)
    print("\n" + table)

    # JSON
    j_json = output_dir / f"reconstructed_journal_{datetime.now():%Y%m%d_%H%M%S}.json"
    j_data = journal_reconstructor.to_json(journal)
    j_json.write_text(json.dumps(j_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Журнал сохранён: {j_json}")

    return journal


# ═══════════════════════════════════════════════════════════════════════════
# Главный конвейер
# ═══════════════════════════════════════════════════════════════════════════

def run_restoration_pipeline(
    project_id: str,
    project_dir: Optional[str] = None,
    enable_vlm: bool = False,
    skip_ingestion: bool = False,
    skip_inference: bool = False,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Полный конвейер восстановления ИД на ОКС.

    Args:
        project_id: идентификатор проекта (напр. "LOS", "SK-2025")
        project_dir: путь к папке с документами (если нужна инвентаризация)
        enable_vlm: включить VLM-фолбэк для сканированных PDF
        skip_ingestion: пропустить инвентаризацию (использовать существующий граф)
        output_dir: директория для output-файлов (по умолчанию data/restoration/{project_id})
    """
    from src.core.evidence_graph import evidence_graph

    start_time = datetime.now()

    # Output directory
    if output_dir:
        out_path = Path(output_dir)
    else:
        out_path = Path(f"data/restoration/{project_id}")
    out_path.mkdir(parents=True, exist_ok=True)

    # Очистка графа при новой инвентаризации
    if not skip_ingestion and project_dir:
        evidence_graph.clear()
        logger.info("Evidence Graph очищен")

    # ═══ Этап 1: Инвентаризация ═══
    if not skip_ingestion and project_dir:
        pipeline, docs, inventory_report = run_ingestion(project_dir, project_id, enable_vlm)

        # ═══ Этап 2: Evidence Graph ═══
        populate_evidence_graph(docs, project_id, evidence_graph)

        # сохранить inventory report
        inv_json = out_path / f"inventory_{datetime.now():%Y%m%d_%H%M%S}.json"
        inv_json.write_text(json.dumps(inventory_report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Инвентаризация сохранена: {inv_json}")
    else:
        print("\n" + "=" * 70)
        print("ЭТАП 1-2: ПРОПУЩЕНЫ (используется существующий граф)")
        print("=" * 70)
        print(f"  Узлов: {evidence_graph.graph.number_of_nodes()}")
        print(f"  Рёбер: {evidence_graph.graph.number_of_edges()}")
        inventory_report = None

    # ═══ Этап 3: ProjectLoader ═══
    if project_dir:
        run_project_loader(project_dir, project_id, evidence_graph)
    else:
        print("\n" + "=" * 70)
        print("ЭТАП 3: PROJECT LOADER — ПРОПУЩЕН (нет project_dir)")
        print("=" * 70)

    # ═══ Этап 4: Inference Engine ═══
    if not skip_inference:
        inferred = run_inference(evidence_graph)
    else:
        print("\n" + "=" * 70)
        print("ЭТАП 4: INFERENCE ENGINE — ПРОПУЩЕН (--no-inference)")
        print("=" * 70)
        inferred = []

    # ═══ Этап 5: Chain Builder ═══
    chains, gaps = run_chain_builder(evidence_graph)

    # ═══ Этап 6: HITL System ═══
    questions = run_hitl(evidence_graph, chains, out_path)

    # ═══ Этап 7: Journal Reconstructor ═══
    journal = run_journal_reconstructor(evidence_graph, out_path)

    # ═══ Сводный отчёт ═══
    from src.core.chain_builder import ChainStatus

    elapsed = (datetime.now() - start_time).total_seconds()

    summary = {
        "project_id": project_id,
        "timestamp": start_time.isoformat(),
        "elapsed_seconds": elapsed,
        "nodes": evidence_graph.graph.number_of_nodes(),
        "edges": evidence_graph.graph.number_of_edges(),
        "chains": {
            "total": len(chains),
            "complete": len([c for c in chains if c.status == ChainStatus.COMPLETE]),
            "partial": len([c for c in chains if c.status == ChainStatus.PARTIAL]),
            "broken": len([c for c in chains if c.status == ChainStatus.BROKEN]),
            "empty": len([c for c in chains if c.status == ChainStatus.EMPTY]),
        },
        "journal": {
            "entries": journal.total_entries,
            "coverage": journal.coverage,
            "confirmed": journal.confirmed_entries,
            "high": journal.high_entries,
            "low": journal.low_entries,
            "inferred": journal.inferred_entries,
            "period": f"{journal.start_date} – {journal.end_date}",
        },
        "hitl_questions": len(questions),
        "inferred_facts": len(inferred),
        "gaps": {
            "critical": len([g for g in gaps if g.severity.value == "critical"]),
            "high": len([g for g in gaps if g.severity.value == "high"]),
            "medium": len([g for g in gaps if g.severity.value == "medium"]),
            "low": len([g for g in gaps if g.severity.value == "low"]),
        },
        "status": "OK" if (
            len(chains) > 0 and
            len([c for c in chains if c.status == ChainStatus.BROKEN]) == 0
        ) else "NEEDS_ATTENTION",
    }

    # Сохранить сводку
    summary_json = out_path / f"restoration_summary_{datetime.now():%Y%m%d_%H%M%S}.json"
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📊 Сводка сохранена: {summary_json}")

    print("\n" + "=" * 70)
    print("КОНВЕЙЕР ЗАВЕРШЁН")
    print("=" * 70)
    print(f"""
  Проект:              {project_id}
  Время:               {elapsed:.1f} сек
  Узлов графа:         {summary['nodes']}
  Цепочек:             {summary['chains']['total']} (OK:{summary['chains']['complete']} "
          f"PART:{summary['chains']['partial']} BRK:{summary['chains']['broken']})
  Записей ОЖР:         {summary['journal']['entries']} (покрытие: {summary['journal']['coverage']:.1%})
  Вопросов HITL:       {summary['hitl_questions']}
  Критических разрывов:{summary['gaps']['critical']}
  Статус:              {summary['status']}
""")

    return summary


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="ASD v12.0 — Pipeline восстановления ИД на ОКС",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s --project-dir data/test_projects/LOS --project-id LOS --vlm
  %(prog)s --project-id SK-2025  # только существующий граф
  %(prog)s --project-dir /path/to/project --project-id 61.17 --no-inference
        """,
    )
    parser.add_argument("--project-id", required=True, help="Идентификатор проекта")
    parser.add_argument("--project-dir", help="Папка с документами (если нужна инвентаризация)")
    parser.add_argument("--vlm", action="store_true", help="Включить VLM-фолбэк для сканов")
    parser.add_argument("--skip-ingestion", action="store_true",
                        help="Пропустить инвентаризацию (использовать граф с диска)")
    parser.add_argument("--no-inference", action="store_true",
                        help="Пропустить Inference Engine")
    parser.add_argument("--output-dir", help="Директория для результатов")
    parser.add_argument("--verbose", "-v", action="store_true", help="Подробный вывод")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.skip_ingestion and not args.project_dir:
        parser.error("Укажите --project-dir или --skip-ingestion")

    run_restoration_pipeline(
        project_id=args.project_id,
        project_dir=args.project_dir,
        enable_vlm=args.vlm,
        skip_ingestion=args.skip_ingestion,
        skip_inference=args.no_inference,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
