"""
ASD v12.0 — Legal Document Generators.

Генерация юридических документов на основе результатов LegalService:
  1. Протокол разногласий (DOCX) — 3-колоночный формат
  2. Досудебная претензия — требование об устранении нарушений
  3. Исковое заявление — в арбитражный суд

Каждый документ опирается на конкретные статьи закона (ГК РФ, ГрК РФ, ФЗ-44/223),
анализ БЛС и судебную практику.

Usage:
    from src.core.services.legal_documents import LegalDocumentGenerator

    gen = LegalDocumentGenerator(llm_engine=llm_engine)
    
    # Протокол разногласий
    docx_path = await gen.generate_protocol(result, output_dir="/tmp")
    
    # Претензия
    claim = await gen.generate_claim(analysis_result, contract_info)
    
    # Иск
    lawsuit = await gen.generate_lawsuit(analysis_result, case_info)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.schemas.legal import (
    LegalAnalysisResult,
    LegalFinding,
    LegalSeverity,
    LegalVerdict,
    ProtocolDisagreements,
    ProtocolItem,
    ProtocolPartyInfo,
)

logger = logging.getLogger(__name__)


# =============================================================================
# LLM Prompts
# =============================================================================

PROTOCOL_INTRO_PROMPT = """Ты — юрист строительной субподрядной организации. 
Составь пояснительную записку к протоколу разногласий.

Договор: {contract_number} от {contract_date}
Стороны: Подрядчик ({contractor_name}) и Заказчик ({customer_name})

Найдено проблем: {total_issues} (критических: {critical}, высоких: {high})

Ключевые риски:
{key_risks}

Напиши краткую пояснительную записку (3-5 предложений) в деловом стиле.
Укажи, что протокол составлен в соответствии с ГК РФ и позицией ВС РФ.
Ответ: только текст записки, без заголовков.
"""

CLAIM_GENERATION_PROMPT = """Ты — юрист строительной субподрядной организации.
Составь досудебную претензию на основе результатов юридического анализа.

ДАННЫЕ ДЛЯ ПРЕТЕНЗИИ:
- Адресат (Заказчик): {customer_name}, ИНН {customer_inn}
- Адрес: {customer_address}
- Отправитель (Подрядчик): {contractor_name}, ИНН {contractor_inn}
- Адрес: {contractor_address}
- Договор: № {contract_number} от {contract_date}
- Предмет договора: {contract_subject}
- Сумма требований: {claim_amount} руб.

НАРУШЕНИЯ:
{violations}

СУММА ТРЕБОВАНИЙ:
{amount_breakdown}

ПРАВОВОЕ ОБОСНОВАНИЕ:
{legal_basis}

Составь текст досудебной претензии. Строгий деловой стиль.
Структура:
1. Шапка (кому, от кого)
2. Описание обязательств (договор)
3. Описание нарушений (факты)
4. Правовое обоснование (статьи)
5. Требования (конкретно)
6. Расчёт суммы требований
7. Предупреждение об обращении в суд
8. Приложения

Формат — чистый текст для вставки в документ.
"""

LAWSUIT_GENERATION_PROMPT = """Ты — юрист, специализирующийся на арбитражных спорах 
в строительстве. Составь исковое заявление в арбитражный суд.

ДАННЫЕ ДЕЛА:
- Истец: {contractor_name}, ИНН {contractor_inn}, ОГРН {contractor_ogrn}
- Адрес истца: {contractor_address}
- Ответчик: {customer_name}, ИНН {customer_inn}, ОГРН {customer_ogrn}
- Адрес ответчика: {customer_address}
- Договор: № {contract_number} от {contract_date}
- Цена иска: {claim_amount} руб.
- Госпошлина: {state_duty} руб.
- Арбитражный суд: {court_name}
- Подсудность: {jurisdiction_basis}

ОБСТОЯТЕЛЬСТВА ДЕЛА:
{case_facts}

ПРАВОВОЕ ОБОСНОВАНИЕ:
{legal_basis}

ДОСУДЕБНОЕ УРЕГУЛИРОВАНИЕ:
{pre_trial_info}

Составь текст искового заявления. Структура (АПК РФ ст. 125):
1. Шапка (суд, истец, ответчик, цена иска, госпошлина)
2. Описательная часть (обстоятельства дела)
3. Мотивировочная часть (правовое обоснование)
4. Просительная часть (конкретные требования)
5. Приложения
6. Подпись, дата

Ссылайся на конкретные статьи: ГК РФ (гл. 37), АПК РФ, Постановления Пленума ВС РФ.
Формат — чистый текст.
"""


# =============================================================================
# Legal Document Generator
# =============================================================================

class LegalDocumentGenerator:
    """
    Генератор юридических документов ASD v12.0.

    Принимает результат LegalService.analyze() и генерирует:
      - Протокол разногласий (DOCX, 3 колонки)
      - Досудебную претензию
      - Исковое заявление
    """

    def __init__(self, llm_engine=None):
        from src.core.llm_engine import llm_engine as default_llm
        self._llm = llm_engine or default_llm

    # =========================================================================
    # Protocol of Disagreements (DOCX)
    # =========================================================================

    async def generate_protocol(
        self,
        analysis_result: LegalAnalysisResult,
        contract_number: str = "",
        contract_date: str = "",
        customer_info: Optional[ProtocolPartyInfo] = None,
        contractor_info: Optional[ProtocolPartyInfo] = None,
        output_dir: str = "/tmp",
    ) -> str:
        """
        Сгенерировать протокол разногласий в формате DOCX.

        Args:
            analysis_result: результат юридической экспертизы
            contract_number: номер договора
            contract_date: дата договора
            customer_info: реквизиты Заказчика
            contractor_info: реквизиты Подрядчика
            output_dir: директория для сохранения

        Returns:
            Путь к сгенерированному DOCX-файлу
        """
        # Формируем ProtocolDisagreements из findings
        protocol = self._build_protocol_from_findings(
            analysis_result, contract_number, contract_date,
            customer_info, contractor_info,
        )

        # Генерируем пояснительную записку через LLM
        summary = await self._generate_protocol_summary(
            protocol, analysis_result,
        )
        protocol.summary = summary

        # Экспорт в DOCX
        docx_path = self._export_protocol_docx(protocol, output_dir)

        logger.info(
            "Protocol generated: %d items → %s",
            protocol.total_items, docx_path,
        )
        return docx_path

    def _build_protocol_from_findings(
        self,
        result: LegalAnalysisResult,
        contract_number: str,
        contract_date: str,
        customer_info: Optional[ProtocolPartyInfo],
        contractor_info: Optional[ProtocolPartyInfo],
    ) -> ProtocolDisagreements:
        """Собрать ProtocolDisagreements из findings анализа."""

        # Фильтруем: только HIGH и CRITICAL
        actionable = [
            f for f in result.findings
            if f.severity in (LegalSeverity.CRITICAL, LegalSeverity.HIGH)
        ]

        # Если уже есть protocol_items в результате — используем их
        if result.protocol_items:
            items = result.protocol_items
        else:
            # Строим из findings
            items = []
            for i, f in enumerate(actionable, 1):
                contractor_edit = f.contractor_edit or self._default_edit(f)
                items.append(ProtocolItem(
                    row_number=i,
                    clause_ref=f.clause_ref,
                    customer_text=f.issue,  # Проблемная формулировка
                    contractor_text=contractor_edit,
                    legal_basis=f.legal_basis,
                    severity=f.severity,
                    blc_match=f.blc_match,
                ))

        return ProtocolDisagreements(
            protocol_title=f"Протокол разногласий к Договору № {contract_number}",
            contract_number=contract_number,
            contract_date=contract_date,
            customer_info=customer_info or ProtocolPartyInfo(name="Заказчик"),
            contractor_info=contractor_info or ProtocolPartyInfo(name="Подрядчик"),
            items=items,
            total_items=len(items),
        )

    async def _generate_protocol_summary(
        self,
        protocol: ProtocolDisagreements,
        result: LegalAnalysisResult,
    ) -> str:
        """Генерация пояснительной записки через LLM."""
        key_risks = "\n".join(
            f"- [{f.severity.value}] п. {f.clause_ref}: {f.issue[:120]}"
            for f in result.findings
            if f.severity in (LegalSeverity.CRITICAL, LegalSeverity.HIGH)
        )[:1500]

        prompt = PROTOCOL_INTRO_PROMPT.format(
            contract_number=protocol.contract_number or "___",
            contract_date=protocol.contract_date or "___",
            contractor_name=protocol.contractor_info.name,
            customer_name=protocol.customer_info.name,
            total_issues=protocol.total_items,
            critical=result.critical_count,
            high=result.high_count,
            key_risks=key_risks or "Не указаны",
        )

        try:
            response = await self._llm.chat(
                "legal",
                [{"role": "user", "content": prompt}],
            )
            return response.strip()
        except Exception as e:
            logger.warning("Protocol summary LLM failed: %s", e)
            return (
                "Настоящий протокол разногласий составлен в соответствии с "
                "действующим законодательством РФ. Просим рассмотреть "
                "предложенные редакции пунктов договора."
            )

    def _export_protocol_docx(
        self, protocol: ProtocolDisagreements, output_dir: str
    ) -> str:
        """Экспорт протокола разногласий в DOCX (3 колонки)."""
        try:
            import docx as docx_lib
        except ImportError:
            logger.warning("python-docx not available — generating text file instead")
            return self._export_protocol_text(protocol, output_dir)

        doc = docx_lib.Document()

        # Title
        title = doc.add_heading(protocol.protocol_title, level=1)
        doc.add_paragraph(
            f"к Договору № {protocol.contract_number or '___'} "
            f"от {protocol.contract_date or '___'}"
        )
        doc.add_paragraph("")

        # Parties
        doc.add_paragraph(
            f"Заказчик: {protocol.customer_info.name}"
            + (f", ИНН {protocol.customer_info.inn}" if protocol.customer_info.inn else "")
        )
        doc.add_paragraph(
            f"Подрядчик: {protocol.contractor_info.name}"
            + (f", ИНН {protocol.contractor_info.inn}" if protocol.contractor_info.inn else "")
        )
        doc.add_paragraph("")

        # Summary
        if protocol.summary:
            doc.add_paragraph(protocol.summary, style="Intense Quote")
            doc.add_paragraph("")

        # Table: 3 columns
        if protocol.items:
            table = doc.add_table(rows=1, cols=3, style="Table Grid")
            # Header
            hdr = table.rows[0].cells
            hdr[0].text = "Пункт, статья договора"
            hdr[1].text = "Редакция Заказчика"
            hdr[2].text = "Редакция Подрядчика"
            for cell in hdr:
                for p in cell.paragraphs:
                    p.style = doc.styles["Normal"]
                    for run in p.runs:
                        run.bold = True

            # Data rows
            for item in protocol.items:
                row = table.add_row().cells
                row[0].text = (
                    f"{item.row_number}. {item.clause_ref}\n"
                    f"[{item.severity.value if item.severity else 'high'}]\n"
                    f"Основание: {item.legal_basis}"
                )
                row[1].text = item.customer_text
                row[2].text = item.contractor_text

            # Column widths
            from docx.shared import Inches
            for row in table.rows:
                row.cells[0].width = Inches(2.0)
                row.cells[1].width = Inches(2.5)
                row.cells[2].width = Inches(2.5)

        doc.add_paragraph("")
        doc.add_paragraph(
            f"Всего пунктов разногласий: {protocol.total_items}"
        )

        # Signatures
        doc.add_paragraph("")
        doc.add_paragraph("Подрядчик: ________________ /_____________/")
        doc.add_paragraph("Заказчик:  ________________ /_____________/")
        doc.add_paragraph(f"Дата: {datetime.now().strftime('%d.%m.%Y')}")

        # Save
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"protocol_disagreements_{ts}.docx"
        filepath = str(Path(output_dir) / filename)
        doc.save(filepath)

        return filepath

    def _export_protocol_text(
        self, protocol: ProtocolDisagreements, output_dir: str
    ) -> str:
        """Fallback: текстовый протокол если python-docx недоступен."""
        lines = [protocol.protocol_title, "=" * 60, ""]
        lines.append(f"Заказчик: {protocol.customer_info.name}")
        lines.append(f"Подрядчик: {protocol.contractor_info.name}")
        if protocol.summary:
            lines.extend(["", protocol.summary])
        lines.extend(["", "-" * 60])

        for item in protocol.items:
            lines.append(
                f"\n{item.row_number}. {item.clause_ref} "
                f"[{item.severity.value if item.severity else 'high'}]"
            )
            lines.append(f"   Основание: {item.legal_basis}")
            lines.append(f"   Заказчик:  {item.customer_text[:200]}")
            lines.append(f"   Подрядчик: {item.contractor_text[:200]}")

        lines.extend(["", f"Всего: {protocol.total_items} пунктов"])

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = str(Path(output_dir) / f"protocol_disagreements_{ts}.txt")
        Path(filepath).write_text("\n".join(lines), encoding="utf-8")
        return filepath

    # =========================================================================
    # Pre-trial Claim (Досудебная претензия)
    # =========================================================================

    async def generate_claim(
        self,
        analysis_result: LegalAnalysisResult,
        contract_number: str = "",
        contract_date: str = "",
        contract_subject: str = "",
        customer_name: str = "",
        customer_inn: str = "",
        customer_address: str = "",
        contractor_name: str = "",
        contractor_inn: str = "",
        contractor_address: str = "",
        claim_amount: float = 0.0,
        output_dir: str = "/tmp",
    ) -> str:
        """
        Сгенерировать досудебную претензию.

        Args:
            analysis_result: результат юридического анализа
            contract_number: номер договора
            contract_date: дата договора
            contract_subject: предмет договора
            customer_name: Заказчик
            customer_inn: ИНН Заказчика
            customer_address: адрес Заказчика
            contractor_name: Подрядчик
            contractor_inn: ИНН Подрядчика
            contractor_address: адрес Подрядчика
            claim_amount: сумма требований
            output_dir: директория для сохранения

        Returns:
            Путь к текстовому файлу претензии
        """
        # Собираем нарушения
        violations = self._format_violations(analysis_result)
        legal_basis = self._format_legal_basis(analysis_result)

        # Расчёт суммы
        amount_breakdown = (
            f"Основной долг: {claim_amount:,.2f} руб.\n"
            f"Проценты по ст. 395 ГК РФ: расчёт прилагается\n"
            f"Судебные расходы: будут предъявлены дополнительно"
        )

        prompt = CLAIM_GENERATION_PROMPT.format(
            customer_name=customer_name or "Заказчик",
            customer_inn=customer_inn or "___",
            customer_address=customer_address or "___",
            contractor_name=contractor_name or "Подрядчик",
            contractor_inn=contractor_inn or "___",
            contractor_address=contractor_address or "___",
            contract_number=contract_number or "___",
            contract_date=contract_date or "___",
            contract_subject=contract_subject or "выполнение строительных работ",
            claim_amount=f"{claim_amount:,.2f}",
            violations=violations,
            amount_breakdown=amount_breakdown,
            legal_basis=legal_basis,
        )

        try:
            claim_text = await self._llm.chat(
                "legal",
                [{"role": "user", "content": prompt}],
            )
        except Exception as e:
            logger.error("Claim generation LLM failed: %s", e)
            claim_text = self._fallback_claim(
                contractor_name, customer_name, contract_number, claim_amount, violations, legal_basis
            )

        # Save
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = str(Path(output_dir) / f"pre_trial_claim_{ts}.txt")
        Path(filepath).write_text(claim_text, encoding="utf-8")

        logger.info("Claim generated: %s", filepath)
        return filepath

    def _fallback_claim(
        self, contractor: str, customer: str, contract_num: str,
        amount: float, violations: str, legal_basis: str,
    ) -> str:
        """Fallback-текст претензии если LLM недоступна."""
        today = datetime.now().strftime('%d.%m.%Y')
        return f"""ДОСУДЕБНАЯ ПРЕТЕНЗИЯ

От: {contractor}
Кому: {customer}

По договору № {contract_num}

Уважаемый Заказчик!

На основании договора № {contract_num} Подрядчиком были выполнены работы.
Однако Заказчиком допущены следующие нарушения:

{violations}

ПРАВОВОЕ ОБОСНОВАНИЕ:
{legal_basis}

ТРЕБОВАНИЕ:
Оплатить задолженность в размере {amount:,.2f} руб. в течение 10 календарных дней с момента получения претензии.

В случае неисполнения требований Подрядчик будет вынужден обратиться в Арбитражный суд.

Подрядчик: ______________ /_____________/
Дата: {today}
"""

    # =========================================================================
    # Lawsuit (Исковое заявление)
    # =========================================================================

    async def generate_lawsuit(
        self,
        analysis_result: LegalAnalysisResult,
        case_facts: str = "",
        contract_number: str = "",
        contract_date: str = "",
        contractor_name: str = "",
        contractor_inn: str = "",
        contractor_ogrn: str = "",
        contractor_address: str = "",
        customer_name: str = "",
        customer_inn: str = "",
        customer_ogrn: str = "",
        customer_address: str = "",
        claim_amount: float = 0.0,
        court_name: str = "Арбитражный суд города Москвы",
        jurisdiction_basis: str = "ст. 35 АПК РФ — по месту нахождения ответчика",
        pre_trial_info: str = "",
        output_dir: str = "/tmp",
    ) -> str:
        """
        Сгенерировать исковое заявление в арбитражный суд.

        Returns:
            Путь к текстовому файлу искового заявления
        """
        # Расчёт госпошлины (ст. 333.21 НК РФ)
        state_duty = self._calc_state_duty(claim_amount)

        legal_basis = self._format_legal_basis(analysis_result)

        prompt = LAWSUIT_GENERATION_PROMPT.format(
            contractor_name=contractor_name or "Истец",
            contractor_inn=contractor_inn or "___",
            contractor_ogrn=contractor_ogrn or "___",
            contractor_address=contractor_address or "___",
            customer_name=customer_name or "Ответчик",
            customer_inn=customer_inn or "___",
            customer_ogrn=customer_ogrn or "___",
            customer_address=customer_address or "___",
            contract_number=contract_number or "___",
            contract_date=contract_date or "___",
            claim_amount=f"{claim_amount:,.2f}",
            state_duty=f"{state_duty:,.2f}",
            court_name=court_name,
            jurisdiction_basis=jurisdiction_basis,
            case_facts=case_facts or self._format_case_facts(analysis_result),
            legal_basis=legal_basis,
            pre_trial_info=pre_trial_info or "Досудебная претензия направлена, ответ не получен.",
        )

        try:
            lawsuit_text = await self._llm.chat(
                "legal",
                [{"role": "user", "content": prompt}],
            )
        except Exception as e:
            logger.error("Lawsuit generation LLM failed: %s", e)
            lawsuit_text = self._fallback_lawsuit(
                contractor_name, customer_name, contract_number,
                claim_amount, state_duty, court_name, legal_basis, case_facts
            )

        # Save
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = str(Path(output_dir) / f"lawsuit_{ts}.txt")
        Path(filepath).write_text(lawsuit_text, encoding="utf-8")

        logger.info("Lawsuit generated: %s", filepath)
        return filepath

    def _fallback_lawsuit(
        self, contractor: str, customer: str, contract_num: str,
        amount: float, duty: float, court: str,
        legal_basis: str, facts: str,
    ) -> str:
        """Fallback-текст иска если LLM недоступна."""
        return f"""В {court}

ИСТЕЦ: {contractor}
ОТВЕТЧИК: {customer}

ЦЕНА ИСКА: {amount:,.2f} руб.
ГОСПОШЛИНА: {duty:,.2f} руб.

ИСКОВОЕ ЗАЯВЛЕНИЕ
о взыскании задолженности по договору подряда

ОБСТОЯТЕЛЬСТВА ДЕЛА:
{facts}

ПРАВОВОЕ ОБОСНОВАНИЕ:
{legal_basis}

ПРОШУ СУД:
1. Взыскать с Ответчика задолженность в размере {amount:,.2f} руб.
2. Взыскать с Ответчика проценты по ст. 395 ГК РФ.
3. Взыскать с Ответчика расходы по уплате госпошлины.

ПРИЛОЖЕНИЯ:
1. Копия договора № {contract_num}
2. Акты КС-2, КС-3
3. Досудебная претензия
4. Расчёт задолженности
5. Квитанция об уплате госпошлины
6. Выписки из ЕГРЮЛ

Истец: ______________ /_____________/
Дата: {datetime.now().strftime('%d.%m.%Y')}
"""

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _format_violations(result: LegalAnalysisResult) -> str:
        """Форматировать список нарушений для претензии."""
        violations = []
        for i, f in enumerate(result.findings, 1):
            if f.severity in (LegalSeverity.CRITICAL, LegalSeverity.HIGH):
                violations.append(
                    f"{i}. {f.issue}\n"
                    f"   Пункт договора: {f.clause_ref}\n"
                    f"   Основание: {f.legal_basis}"
                )
        return "\n\n".join(violations) if violations else "Нарушения не детализированы."

    @staticmethod
    def _format_legal_basis(result: LegalAnalysisResult) -> str:
        """Форматировать правовое обоснование."""
        refs = result.normative_refs or []
        # Добавляем ссылки из findings
        for f in result.findings:
            if f.legal_basis and f.legal_basis not in refs:
                refs.append(f.legal_basis)

        if not refs:
            refs = [
                "ст. 309 ГК РФ (обязательства должны исполняться надлежащим образом)",
                "ст. 310 ГК РФ (недопустимость одностороннего отказа от исполнения)",
                "ст. 711 ГК РФ (порядок оплаты работы)",
                "ст. 395 ГК РФ (проценты за пользование чужими денежными средствами)",
            ]

        return "\n".join(f"- {ref}" for ref in refs[:10])

    @staticmethod
    def _format_case_facts(result: LegalAnalysisResult) -> str:
        """Форматировать обстоятельства дела."""
        critical_findings = [
            f for f in result.findings
            if f.severity == LegalSeverity.CRITICAL
        ]
        if critical_findings:
            return "\n".join(
                f"- {f.issue} (п. {f.clause_ref})" for f in critical_findings[:5]
            )
        return result.summary or "Обстоятельства изложены в прилагаемых документах."

    @staticmethod
    def _calc_state_duty(claim_amount: float) -> float:
        """Расчёт госпошлины по ст. 333.21 НК РФ (арбитраж)."""
        if claim_amount <= 100_000:
            return max(2000, claim_amount * 0.04)
        elif claim_amount <= 200_000:
            return 4000 + (claim_amount - 100_000) * 0.03
        elif claim_amount <= 1_000_000:
            return 7000 + (claim_amount - 200_000) * 0.02
        elif claim_amount <= 2_000_000:
            return 23_000 + (claim_amount - 1_000_000) * 0.01
        else:
            return min(200_000, 33_000 + (claim_amount - 2_000_000) * 0.005)

    @staticmethod
    def _default_edit(finding: LegalFinding) -> str:
        """Дефолтная редакция Подрядчика если не указана явно."""
        if finding.auto_fixable:
            return (
                f"Предлагается исключить/изменить данный пункт в соответствии с "
                f"{finding.legal_basis}. {finding.recommendation}"
            )
        return f"Требуется переформулировать с учётом {finding.legal_basis}. {finding.recommendation}"


# Синглтон
legal_doc_gen = LegalDocumentGenerator()
