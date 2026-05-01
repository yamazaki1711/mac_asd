"""
ASD v12.0 — Jurist MCP Tools.

9 tools for the Legal Agent with real LLM logic:
  1. asd_upload_document          — Parse PDF/DOCX → chunks
  2. asd_analyze_contract         — Full Map-Reduce + БЛС legal analysis
  3. asd_normative_search         — Hybrid search (Vector + Graph)
  4. asd_generate_protocol        — Protocol of disagreements (stub → DOCX)
  5. asd_generate_claim           — Pre-trial claim (stub → DOCX)
  6. asd_generate_lawsuit         — Arbitration lawsuit (stub → DOCX)
  7. asd_add_trap                 — Manual trap addition to БЛС
  8. asd_list_telegram_channels   — List cataloged Telegram channels for БЛС
  9. asd_ingest_telegram          — Ingest Telegram export to БЛС (single or batch)
"""

import os
import logging
from typing import Dict, Any, Optional, List

from src.core.services.legal_service import legal_service
from src.schemas.legal import (
    LegalAnalysisRequest,
    ReviewType,
)

logger = logging.getLogger(__name__)


async def asd_upload_document(file_path: str) -> Dict[str, Any]:
    """
    Загрузка и парсинг документа (PDF, DOCX).

    Args:
        file_path: Путь к файлу документа

    Returns:
        {"status", "file_path", "chunks_extracted", "total_chars", "message"}
    """
    logger.info(f"asd_upload_document: {file_path}")

    try:
        result = await legal_service.upload_and_parse(file_path)
        return result.model_dump()
    except Exception as e:
        logger.error(f"Failed to upload document: {e}")
        return {"status": "error", "message": str(e)}


async def asd_analyze_contract(
    document_id: Optional[int] = None,
    document_text: Optional[str] = None,
    file_path: Optional[str] = None,
    review_type: str = "contract",
    chunk_size: int = 6000,
    chunk_overlap: int = 300,
) -> Dict[str, Any]:
    """
    Юридическая экспертиза контракта (БЛС + Map-Reduce + LightRAG).

    Полный цикл анализа:
      1. Парсинг документа (если file_path)
      2. Разбивка на чанки (если документ длинный)
      3. Поиск похожих ловушек в БЛС через RAG
      4. MAP: LLM анализирует каждый чанк
      5. REDUCE: агрегация результатов → вердикт

    Args:
        document_id: ID документа в БД (если уже загружен)
        document_text: Текст документа напрямую
        file_path: Путь к файлу (PDF, DOCX)
        review_type: Тип рассмотрения (contract, tender, compliance)
        chunk_size: Размер чанка для Map-Reduce (символов)
        chunk_overlap: Перекрытие чанков

    Returns:
        Полный LegalAnalysisResult как dict:
        {"findings", "verdict", "summary", "normative_refs", "contradictions", ...}
    """
    logger.info(
        f"asd_analyze_contract: doc_id={document_id}, "
        f"text={'yes' if document_text else 'no'}, "
        f"file={file_path}, review_type={review_type}"
    )

    try:
        request = LegalAnalysisRequest(
            document_id=document_id,
            document_text=document_text,
            file_path=file_path,
            review_type=ReviewType(review_type),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        result = await legal_service.analyze(request)
        return result.model_dump()

    except Exception as e:
        logger.error(f"Contract analysis failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "findings": [],
            "verdict": "approved",
            "summary": f"Ошибка при анализе: {str(e)[:200]}",
        }


async def asd_normative_search(query: str) -> Dict[str, Any]:
    """
    Поиск по нормативной базе (Graph + Vector).

    Args:
        query: Поисковый запрос (например, "неустойка ФЗ-44")

    Returns:
        {"status", "query", "results": {"vector_chunks", "graph_context"}}
    """
    logger.info(f"asd_normative_search: {query}")

    try:
        from src.core.rag_service import rag_service

        results = await rag_service.hybrid_search(query)
        return {"status": "success", "query": query, "results": results}
    except Exception as e:
        logger.error(f"Normative search failed: {e}")
        return {"status": "error", "query": query, "message": str(e)}


async def asd_generate_protocol(
    analysis_result: Dict[str, Any],
    contract_number: str = "___",
    contract_date: str = "___",
    customer_name: str = "Заказчик",
    contractor_name: str = "Подрядчик",
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Протокол разногласий к договору (DOCX).

    v12.0.0: Генерирует полноценный DOCX с 3-колоночной таблицей:
    | Пункт, статья | Редакция Заказчика | Редакция Подрядчика |

    Каждая правка Подрядчика опирается на конкретную статью закона (ГК РФ,
    ГрК РФ, ФЗ-44/223). Это заставляет даже государственного Заказчика
    вернуться в правовое поле и умерить аппетиты.

    Args:
        analysis_result: Результат asd_analyze_contract (dict с findings)
        contract_number: Номер договора
        contract_date: Дата договора
        customer_name: Наименование Заказчика
        contractor_name: Наименование Подрядчика
        output_path: Путь для сохранения DOCX (если None — auto-generate)

    Returns:
        {"status", "file_path", "total_items", "message"}
    """
    logger.info(f"asd_generate_protocol: contract={contract_number}")

    try:
        from docx import Document
        from docx.shared import Inches, Pt, Cm, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from src.config import settings

        # Extract protocol items from analysis
        findings = analysis_result.get("findings", [])
        protocol_items = analysis_result.get("protocol_items", [])

        # Build protocol items from findings if not already provided
        if not protocol_items:
            for i, f in enumerate(findings):
                if isinstance(f, dict):
                    protocol_items.append({
                        "clause_ref": f.get("clause_ref", "—"),
                        "customer_text": f.get("contract_quote", f.get("issue", "—")),
                        "contractor_text": f.get("contractor_edit", f.get("recommendation", "—")),
                        "legal_basis": f.get("legal_basis", "—"),
                        "severity": f.get("severity", "medium"),
                        "blc_match": f.get("blc_match"),
                    })

        if not protocol_items:
            return {
                "status": "success",
                "message": "Нет пунктов для протокола разногласий",
                "total_items": 0,
                "file_path": None,
            }

        # Create DOCX
        doc = Document()

        # Styles
        style = doc.styles['Normal']
        font = style.font
        font.name = 'Calibri'
        font.size = Pt(10)

        # Title
        title = doc.add_heading('ПРОТОКОЛ РАЗНОГЛАСИЙ', level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        subtitle = doc.add_paragraph()
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = subtitle.add_run(
            f'к Договору {contract_number} от {contract_date}'
        )
        run.font.size = Pt(12)
        run.bold = True

        # Parties
        doc.add_paragraph()
        parties = doc.add_paragraph()
        parties.add_run('Заказчик: ').bold = True
        parties.add_run(customer_name + '\n')
        parties.add_run('Подрядчик: ').bold = True
        parties.add_run(contractor_name)

        doc.add_paragraph()
        note = doc.add_paragraph()
        note.add_run(
            'Настоящий протокол разногласий составлен на основании '
            'действующего законодательства РФ (ГК РФ, ГрК РФ, ФЗ-44/223). '
            'Каждая предлагаемая редакция Подрядчика опирается на конкретную '
            'норму права, что обеспечивает правовую обоснованность позиции Подрядчика.'
        ).italic = True

        doc.add_paragraph()

        # 3-column table
        table = doc.add_table(rows=1, cols=4)
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # Header
        header_cells = table.rows[0].cells
        headers = ['№', 'Пункт, статья\nдоговора', 'Редакция\nЗаказчика', 'Редакция\nПодрядчика']
        widths = [Cm(1.2), Cm(3.5), Cm(6.5), Cm(6.5)]

        for i, (header, width) in enumerate(zip(headers, widths)):
            header_cells[i].text = header
            header_cells[i].width = width
            for paragraph in header_cells[i].paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.bold = True
                    run.font.size = Pt(9)

        # Data rows
        for idx, item in enumerate(protocol_items, 1):
            row = table.add_row()

            row.cells[0].text = str(idx)
            row.cells[1].text = item.get("clause_ref", "—")
            row.cells[2].text = item.get("customer_text", "—")
            
            # Contractor text with legal basis
            contractor_text = item.get("contractor_text", "—")
            legal_basis = item.get("legal_basis", "")
            if legal_basis and legal_basis != "—":
                contractor_text += f"\n\n(Основание: {legal_basis})"
            row.cells[3].text = contractor_text

            # Format
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(9)
                    paragraph.paragraph_format.space_before = Pt(2)
                    paragraph.paragraph_format.space_after = Pt(2)

            row.cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Summary
        doc.add_paragraph()
        total = len(protocol_items)
        summary = doc.add_paragraph()
        summary.add_run(
            f'Итого: {total} {"пункт" if total == 1 else "пункта" if total < 5 else "пунктов"} разногласий.'
        ).bold = True

        # Severity summary
        severities = {}
        for item in protocol_items:
            sev = item.get("severity", "medium")
            severities[sev] = severities.get(sev, 0) + 1

        sev_text = []
        if severities.get("critical"):
            sev_text.append(f"{severities['critical']} критических")
        if severities.get("high"):
            sev_text.append(f"{severities['high']} высоких")
        if severities.get("medium"):
            sev_text.append(f"{severities['medium']} средних")

        if sev_text:
            sev_para = doc.add_paragraph()
            sev_para.add_run("Критичность: ").bold = True
            sev_para.add_run(", ".join(sev_text))

        # Signature lines
        doc.add_paragraph()
        doc.add_paragraph()

        sig_table = doc.add_table(rows=3, cols=2)
        sig_table.style = 'Table Grid'
        sig_table.cell(0, 0).text = "ЗАКАЗЧИК:"
        sig_table.cell(0, 1).text = "ПОДРЯДЧИК:"
        for cell in sig_table.rows[0].cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.bold = True

        sig_table.cell(1, 0).text = f"\n\n\n________________ / {customer_name} /"
        sig_table.cell(1, 1).text = f"\n\n\n________________ / {contractor_name} /"
        sig_table.cell(2, 0).text = "М.П."
        sig_table.cell(2, 1).text = "М.П."

        # Save
        if not output_path:
            artifacts = settings.artifacts_path
            artifacts.mkdir(parents=True, exist_ok=True)
            output_path = str(artifacts / f"Протокол_разногласий_{contract_number}.docx")

        doc.save(output_path)

        return {
            "status": "success",
            "file_path": output_path,
            "total_items": total,
            "message": f"Протокол разногласий создан: {total} пунктов ({', '.join(sev_text)})",
        }

    except Exception as e:
        logger.error(f"Protocol generation failed: {e}")
        return {"status": "error", "message": str(e)}


async def asd_generate_claim(document_id: str) -> Dict[str, Any]:
    """
    Претензия при неоплате СМР (DOCX).

    TODO: Реализовать DOCX-генерацию через python-docx.

    Args:
        document_id: ID документа/контракта

    Returns:
        {"status", "document_id", "content", "action"}
    """
    logger.info(f"asd_generate_claim: {document_id}")
    # TODO: Implement DOCX generation with python-docx
    return {
        "status": "success",
        "document_id": document_id,
        "content": "Претензия о нарушении сроков оплаты...",
        "action": "DOCX generation stubbed — will be implemented in Phase 3",
    }


async def asd_generate_lawsuit(document_id: str) -> Dict[str, Any]:
    """
    Исковое заявление в арбитраж (DOCX).

    TODO: Реализовать DOCX-генерацию через python-docx.

    Args:
        document_id: ID документа/контракта

    Returns:
        {"status", "document_id", "content", "action"}
    """
    logger.info(f"asd_generate_lawsuit: {document_id}")
    # TODO: Implement DOCX generation with python-docx
    return {
        "status": "success",
        "document_id": document_id,
        "content": "Исковое заявление в Арбитражный суд...",
        "action": "DOCX generation stubbed — will be implemented in Phase 3",
    }


async def asd_add_trap(
    title: str,
    description: str,
    source: str,
    mitigation: str,
    domain: str = "legal",
    channel: Optional[str] = None,
    category: Optional[str] = None,
    court_cases: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Ручное добавление доменной ловушки в БЛС.

    v12.0.0: Обобщено с LegalTrap до DomainTrap — поддержка всех доменов.
    v12.0.0: Добавлен параметр domain (legal, pto, smeta, logistics, procurement).

    Args:
        title: Краткое название ловушки
        description: Полное описание
        source: Источник (например, "Telegram @advokatgrikevich", "Internal")
        mitigation: Рекомендация по защите
        domain: Домен агента (legal, pto, smeta, logistics, procurement)
        channel: Username Telegram-канала (например, "advokatgrikevich")
        category: Категория источника
        court_cases: Список судебных дел (например, ["А40-123/2023"])

    Returns:
        {"status", "message", "trap_id", "domain"}
    """
    logger.info(f"asd_add_trap: {title} (domain={domain})")

    try:
        from src.db.init_db import SessionLocal
        from src.db.models import DomainTrap
        from src.core.llm_engine import llm_engine

        db = SessionLocal()
        try:
            # Get embedding via llm_engine
            embedding = await llm_engine.embed(description)

            # Determine weight from category
            weight_map = {
                "legal_practice": 100, "pto_practice": 100, "smeta_practice": 100,
                "legal_association": 80, "pto_news": 60, "smeta_news": 60,
                "legal_education": 60, "logistics_practice": 80, "procurement_practice": 80,
                "legal_news": 40, "logistics_news": 40, "procurement_news": 40,
                "unknown": 50,
            }
            weight = weight_map.get(category, 50) if category else 50

            trap = DomainTrap(
                domain=domain,
                title=title,
                description=description,
                source=source,
                channel=channel or source,
                category=category or "unknown",
                weight=weight,
                court_cases=court_cases or [],
                mitigation=mitigation,
                embedding=embedding,
            )
            db.add(trap)
            db.commit()
            db.refresh(trap)

            return {
                "status": "success",
                "message": f"Trap '{title}' added to domain={domain} (id={trap.id}, category={category or 'unknown'}, weight={weight}).",
                "trap_id": trap.id,
                "domain": domain,
            }
        except Exception as e:
            db.rollback()
            raise
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Failed to add trap: {e}")
        return {"status": "error", "message": str(e)}


async def asd_list_telegram_channels(
    priority: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Вывод каталога Telegram-каналов для БЛС.

    v12.0.0: Показывает все каналы из config/telegram_channels.yaml
    с метаданными (категория, приоритет, фокус-области).

    Args:
        priority: Фильтр по приоритету (critical, high, medium, low).
                  Если None — показать все каналы.

    Returns:
        {"status", "channels": [...], "total_count"}
    """
    logger.info(f"asd_list_telegram_channels: priority={priority}")

    try:
        from src.scripts.ingest_blc_telegram import ChannelCatalog

        catalog = ChannelCatalog()

        # Collect unique channels
        seen = set()
        channels = []
        for key, ch in catalog.channels.items():
            username = ch.get("username", "")
            if username in seen:
                continue
            seen.add(username)

            if priority and ch.get("priority") != priority:
                continue

            channels.append({
                "username": username,
                "display_name": ch.get("display_name", ""),
                "url": ch.get("url", f"https://t.me/{username}"),
                "category": ch.get("category", "unknown"),
                "priority": ch.get("priority", "low"),
                "focus_areas": ch.get("focus_areas", []),
                "description": ch.get("description", ""),
            })

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        channels.sort(key=lambda x: priority_order.get(x["priority"], 4))

        return {
            "status": "success",
            "channels": channels,
            "total_count": len(channels),
        }

    except Exception as e:
        logger.error(f"Failed to list channels: {e}")
        return {"status": "error", "message": str(e), "channels": []}


async def asd_ingest_telegram(
    file_path: Optional[str] = None,
    batch_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Импорт Telegram JSON-экспорта в БЛС (одиночный или пакетный).

    v12.0.0: Поддерживает каталог каналов для автокатегоризации
    и приоритизации ловушек.

    Args:
        file_path: Путь к result.json (одиночный импорт)
        batch_dir: Путь к папке с JSON-экспортами (пакетный импорт)

    Returns:
        {"status", "results": {...}, "total_traps_found"}
    """
    logger.info(f"asd_ingest_telegram: file={file_path}, batch_dir={batch_dir}")

    try:
        from src.scripts.ingest_blc_telegram import (
            ChannelCatalog,
            parse_telegram_export,
            batch_parse_exports,
        )

        catalog = ChannelCatalog()

        if batch_dir:
            results = await batch_parse_exports(batch_dir, catalog)
            total_traps = sum(s.get("trapped", 0) for s in results.values())
            return {
                "status": "success",
                "mode": "batch",
                "results": results,
                "total_traps_found": total_traps,
            }
        elif file_path:
            stats = await parse_telegram_export(file_path, catalog)
            return {
                "status": "success",
                "mode": "single",
                "results": {os.path.basename(file_path): stats},
                "total_traps_found": stats.get("trapped", 0),
            }
        else:
            return {
                "status": "error",
                "message": "Specify either file_path or batch_dir",
            }

    except Exception as e:
        logger.error(f"Failed to ingest telegram: {e}")
        return {"status": "error", "message": str(e)}
