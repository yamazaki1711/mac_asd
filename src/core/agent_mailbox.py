"""
ASD v12.0 — Agent Mailbox (Email Layer).

Даёт агентам возможность отправлять и получать email через Gmail API.
Интегрируется с существующей Google Workspace инфраструктурой.

Агенты:
  - info@ksk-1.ru     → Делопроизводитель (общая корреспонденция)
  - tender@ksk-1.ru   → Закупщик + Логист (RFQ, КП)
  - law@ksk-1.ru      → Юрист (претензии, иски)
  - pto@ksk-1.ru      → ПТО (пакеты ИД на согласование)
  - smeta@ksk-1.ru    → Сметчик (КС-2, КС-3)

Ключевые возможности:
  - send_email() — отправка письма
  - send_rfq() — отправка запроса КП поставщику
  - check_inbox() — мониторинг входящих
  - route_incoming() — классификация входящего письма → нужный агент
  - process_attachments() — извлечение вложений (.pdf, .xlsx) для Ingestion Pipeline
"""

from __future__ import annotations

import base64
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Путь к Google API скрипту
GWS_SCRIPT = os.path.expanduser("~/.hermes/skills/productivity/google-workspace/scripts/google_api.py")
GWS_TOKEN = os.path.expanduser("~/.hermes/google_token.json")


# =============================================================================
# Email Message
# =============================================================================

@dataclass
class EmailMessage:
    """Структура email-сообщения."""
    msg_id: str = ""
    from_addr: str = ""
    to_addr: str = ""
    subject: str = ""
    body: str = ""
    date: str = ""
    snippet: str = ""
    has_attachments: bool = False
    attachment_names: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    is_unread: bool = False
    thread_id: str = ""


@dataclass
class IncomingClassification:
    """Результат классификации входящего письма."""
    target_agent: str       # "procurement", "legal", "pto", "smeta", "archive"
    category: str           # "rfq_response", "claim_response", "id_rejection", "general"
    confidence: float
    key_entities: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""


# =============================================================================
# Agent Mailbox
# =============================================================================

class AgentMailbox:
    """
    Email-интерфейс агентов ASD.

    Использует Gmail API через существующий google_api.py.

    Отправка:
      mailbox.send("tender@ksk-1.ru", "metal@evraz.com",
                   "Запрос КП: шпунт Л5-УМ", body)

    Приём:
      messages = mailbox.check_inbox("tender", query="is:unread")
    """

    # Маппинг агент → email-адрес
    AGENT_EMAILS = {
        "archive": "info@ksk-1.ru",       # Делопроизводитель
        "procurement": "tender@ksk-1.ru",  # Закупщик
        "logistics": "tender@ksk-1.ru",    # Логист (тот же ящик)
        "legal": "law@ksk-1.ru",           # Юрист
        "pto": "pto@ksk-1.ru",             # ПТО
        "smeta": "smeta@ksk-1.ru",         # Сметчик
    }

    # Маппинг агент → подпись
    AGENT_SIGNATURES = {
        "archive": "ООО «КСК №1»\nОтдел исполнительной документации\ninfo@ksk-1.ru",
        "procurement": "ООО «КСК №1»\nТендерный отдел\ntender@ksk-1.ru\n+7 (XXX) XXX-XX-XX",
        "legal": "ООО «КСК №1»\nЮридический отдел\nlaw@ksk-1.ru",
        "pto": "ООО «КСК №1»\nИнженер ПТО\npto@ksk-1.ru",
        "smeta": "ООО «КСК №1»\nСметный отдел\nsmeta@ksk-1.ru",
    }

    def __init__(self):
        self._check_token()

    def _check_token(self):
        """Проверить наличие токена Gmail API."""
        if not os.path.exists(GWS_TOKEN):
            logger.warning("Gmail token not found at %s. Email features disabled.", GWS_TOKEN)
            self._enabled = False
        else:
            self._enabled = True

    def _gmail_api(self, action: str, **kwargs) -> Dict:
        """
        Вызвать Google API через Python (subprocess к google_api.py).

        Использует subprocess, т.к. google_api.py — CLI-скрипт.
        В production можно заменить на прямые вызовы API.
        """
        import json
        import subprocess

        cmd = ["python3", GWS_SCRIPT, "gmail", action]

        if action == "search":
            cmd.extend(["search", kwargs.get("query", "is:unread")])
            if kwargs.get("max_results"):
                cmd.extend(["--max", str(kwargs["max_results"])])
        elif action == "send":
            cmd.extend(["send",
                       "--to", kwargs.get("to", ""),
                       "--subject", kwargs.get("subject", "Без темы"),
                       "--body", kwargs.get("body", "")])
            if kwargs.get("attachment"):
                cmd.extend(["--attachment", kwargs["attachment"]])
        elif action == "get":
            cmd.extend(["get", kwargs.get("msg_id", "")])
        elif action == "reply":
            cmd.extend(["reply",
                       "--to", kwargs.get("msg_id", ""),
                       "--body", kwargs.get("body", "")])
        elif action == "labels":
            cmd.extend(["labels"])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error("Gmail API error: %s", result.stderr[:200])
                return {"error": result.stderr[:200]}
            return {"output": result.stdout}
        except Exception as e:
            logger.error("Gmail API call failed: %s", e)
            return {"error": str(e)}

    # =========================================================================
    # Отправка
    # =========================================================================

    def send_email(
        self,
        from_agent: str,
        to: str,
        subject: str,
        body: str,
        attachment: str = "",
        cc: str = "",
    ) -> bool:
        """
        Отправить email от имени агента.

        Args:
            from_agent: "procurement", "legal", "pto", etc.
            to: адрес получателя
            subject: тема письма
            body: тело письма (plain text)
            attachment: путь к файлу вложения
            cc: копия

        Returns:
            True если отправлено успешно
        """
        if not self._enabled:
            logger.warning("Email disabled — no Gmail token. Would send to %s: %s", to, subject)
            return False

        # Подпись агента
        signature = self.AGENT_SIGNATURES.get(from_agent, "ООО «КСК №1»")
        full_body = f"{body}\n\n--\n{signature}"

        kwargs = {
            "to": to,
            "subject": subject,
            "body": full_body,
        }
        if attachment and os.path.exists(attachment):
            kwargs["attachment"] = attachment

        result = self._gmail_api("send", **kwargs)
        success = "error" not in result

        if success:
            logger.info("Email sent: %s → %s: %s", from_agent, to, subject)
        return success

    def send_rfq(
        self,
        supplier_name: str,
        supplier_email: str,
        materials: List[Dict[str, Any]],
        delivery_address: str = "",
        deadline: str = "",
        project_name: str = "",
    ) -> bool:
        """
        Отправить запрос коммерческого предложения (RFQ) поставщику.

        Args:
            supplier_name: название компании-поставщика
            supplier_email: email поставщика
            materials: список [{name, quantity, unit, gost}]
            delivery_address: адрес доставки
            deadline: срок подачи КП
            project_name: название объекта

        Returns:
            True если отправлено
        """
        # Формируем таблицу материалов
        material_table = "№ | Наименование | Кол-во | Ед. | ГОСТ/ТУ\n"
        material_table += "---|-------------|--------|-----|--------\n"
        for i, mat in enumerate(materials, 1):
            material_table += (
                f"{i} | {mat.get('name', '')} | "
                f"{mat.get('quantity', '')} | {mat.get('unit', '')} | "
                f"{mat.get('gost', '—')}\n"
            )

        subject = f"Запрос КП: {materials[0].get('name', 'материалы')} — {project_name or 'объект'}"

        body = f"""Уважаемые коллеги!

ООО «КСК №1» просит предоставить коммерческое предложение на поставку
следующих материалов для объекта «{project_name or 'строительный объект'}»:

{material_table}

Условия поставки:
- Адрес доставки: {delivery_address or 'уточняется'}
- Срок поставки: {deadline or 'уточняется'}
- Условия оплаты: стандартные

Просим указать в КП:
1. Цену за единицу и общую стоимость
2. Срок поставки с момента заявки
3. Условия доставки (включена / отдельно)
4. Наличие сертификатов и паспортов качества

Срок предоставления КП: до {deadline or '3 рабочих дней'}.

С уважением,
"""

        return self.send_email(
            from_agent="procurement",
            to=supplier_email,
            subject=subject,
            body=body,
        )

    # =========================================================================
    # Приём и маршрутизация
    # =========================================================================

    def check_inbox(
        self, agent: str = "", query: str = "is:unread", max_results: int = 20
    ) -> List[EmailMessage]:
        """
        Проверить входящие для агента.

        Args:
            agent: имя агента (фильтрует по AGENT_EMAILS, "" = все)
            query: Gmail-запрос (по умолчанию: непрочитанные)
            max_results: макс. количество результатов
        """
        if not self._enabled:
            return []

        # Фильтр по адресу агента
        if agent and agent in self.AGENT_EMAILS:
            query = f"{query} to:{self.AGENT_EMAILS[agent]}"

        result = self._gmail_api("search", query=query, max_results=max_results)
        if "error" in result:
            return []

        return self._parse_search_results(result.get("output", ""))

    def _parse_search_results(self, output: str) -> List[EmailMessage]:
        """Распарсить вывод gmail search."""
        messages = []
        # Простой парсинг вывода (ID сообщений)
        msg_ids = re.findall(r'(?:ID|id|messageId)[:\s]+([a-f0-9]+)', output, re.IGNORECASE)
        for msg_id in msg_ids[:20]:
            msg = self._get_message(msg_id)
            if msg:
                messages.append(msg)
        return messages

    def _get_message(self, msg_id: str) -> Optional[EmailMessage]:
        """Получить содержимое сообщения по ID."""
        result = self._gmail_api("get", msg_id=msg_id)
        if "error" in result:
            return None

        output = result.get("output", "")

        # Парсинг (упрощённый — в production заменить на парсер MIME)
        return self._parse_message_output(output, msg_id)

    def _parse_message_output(self, output: str, msg_id: str) -> EmailMessage:
        """Распарсить вывод gmail get."""
        msg = EmailMessage(msg_id=msg_id)

        patterns = {
            "from_addr": r"(?:From|from)[:\s]+([^\n]+)",
            "to_addr": r"(?:To|to)[:\s]+([^\n]+)",
            "subject": r"(?:Subject|subject)[:\s]+([^\n]+)",
            "date": r"(?:Date|date)[:\s]+([^\n]+)",
            "snippet": r"(?:Snippet|snippet)[:\s]+([^\n]+)",
        }

        for field, pattern in patterns.items():
            match = re.search(pattern, output)
            if match:
                setattr(msg, field, match.group(1).strip())

        # Тело письма
        body_match = re.search(r'(?:Body|body)[:\s]+\n?(.*?)(?:\n(?:From|Labels|---)|$)',
                               output, re.DOTALL)
        if body_match:
            msg.body = body_match.group(1).strip()[:2000]

        # Вложения
        att_match = re.findall(r'(?:Attachment|att|filename)[:\s]+([^\n]+)', output, re.IGNORECASE)
        if att_match:
            msg.has_attachments = True
            msg.attachment_names = att_match

        # UNREAD label
        msg.is_unread = "UNREAD" in output

        return msg

    def route_incoming(self, message: EmailMessage) -> IncomingClassification:
        """
        Классифицировать входящее письмо и определить целевого агента.

        Использует keyword-matching (без LLM) для быстрой маршрутизации.
        """
        text = f"{message.subject} {message.body}"[:5000].lower()

        # ── RFQ / КП ──
        rfq_keywords = [
            "коммерческое предложение", "кп", "запрос кп", "rfq",
            "прайс", "цена", "стоимость", "расценка", "счёт на оплату",
            "спецификация", "поставка",
        ]
        if any(kw in text for kw in rfq_keywords):
            return IncomingClassification(
                target_agent="procurement",
                category="rfq_response",
                confidence=0.85,
                reason="Входящее КП или ответ на RFQ",
            )

        # ── Претензии / Юридическое ──
        legal_keywords = [
            "претензия", "иск", "арбитраж", "суд", "неустойка",
            "штраф", "расторжение", "уведомление о",
        ]
        if any(kw in text for kw in legal_keywords):
            return IncomingClassification(
                target_agent="legal",
                category="claim_response",
                confidence=0.85,
                reason="Юридический документ или претензия",
            )

        # ── ИД / Замечания ──
        id_keywords = [
            "исполнительная документация", "ид", "аоср", "кс-2", "кс-3",
            "замечания", "не принято", "доработать", "стройконтроль",
            "реестр", "акт освидетельствования",
        ]
        if any(kw in text for kw in id_keywords):
            return IncomingClassification(
                target_agent="pto",
                category="id_feedback",
                confidence=0.80,
                reason="Обратная связь по ИД",
            )

        # ── Общая корреспонденция ──
        return IncomingClassification(
            target_agent="archive",
            category="general",
            confidence=0.60,
            reason="Общая корреспонденция → Делопроизводитель",
        )

    # =========================================================================
    # Вложения
    # =========================================================================

    def download_attachments(
        self, msg_id: str, save_dir: str = ""
    ) -> List[Path]:
        """
        Скачать вложения из письма для передачи в Ingestion Pipeline.

        Args:
            msg_id: ID сообщения Gmail
            save_dir: директория для сохранения (по умолчанию /tmp/asd_inbox)

        Returns:
            Список путей к сохранённым файлам
        """
        if not save_dir:
            save_dir = f"/tmp/asd_inbox/{msg_id}"
        os.makedirs(save_dir, exist_ok=True)

        # Gmail API get + извлечение attachmentId...
        # В production — замена на прямые вызовы API с download attachment
        logger.info("Attachment download: msg=%s → %s", msg_id, save_dir)

        # Возвращаем существующие файлы в директории
        saved = list(Path(save_dir).glob("*"))
        return saved


# =============================================================================
# RFQ Builder — формирование запроса КП
# =============================================================================

class RFQBuilder:
    """
    Формирует профессиональный запрос коммерческого предложения.

    Принимает ведомость материалов от Логиста → формирует письмо
    поставщику с таблицей материалов и условиями.
    """

    @staticmethod
    def build_from_spec(
        materials: List[Dict[str, Any]],
        project_name: str = "",
        delivery_address: str = "",
        delivery_deadline: str = "",
        payment_terms: str = "стандартные",
    ) -> Dict[str, str]:
        """
        Сформировать RFQ из спецификации материалов.

        Returns:
            {to, subject, body} — готовое к отправке
        """
        # Таблица материалов
        table = "№  | Наименование                         | Кол-во    | Ед.  | ГОСТ/ТУ\n"
        table += "---|--------------------------------------|-----------|------|--------\n"
        total_positions = 0
        for i, mat in enumerate(materials, 1):
            table += (
                f"{i:<3}| {mat.get('name', '—'):36} | "
                f"{mat.get('quantity', '—'):>9} | "
                f"{mat.get('unit', '—'):4} | "
                f"{mat.get('gost', '—')}\n"
            )
            total_positions += 1

        body = f"""Уважаемые коллеги!

ООО «КСК №1» просит предоставить коммерческое предложение (КП)
на поставку материалов для объекта:

    «{project_name or 'строительный объект'}»

Необходимые материалы ({total_positions} поз.):

{table}

Условия запроса:
• Адрес доставки: {delivery_address or 'сообщим дополнительно'}
• Желаемый срок поставки: {delivery_deadline or 'сообщите минимальный'}
• Условия оплаты: {payment_terms}

Просим указать в ответе:
1. Цену за единицу и общую стоимость (с НДС)
2. Срок отгрузки с момента заявки
3. Условия доставки (включена в цену / отдельно)
4. Наличие сертификатов качества и паспортов
5. Срок действия КП
6. Контактное лицо и телефон

Срок ответа: 3 рабочих дня.

Заранее благодарим за оперативность.

С уважением,
"""

        return {
            "subject": f"Запрос КП: {materials[0].get('name', 'материалы')} — {project_name or 'объект'}",
            "body": body,
        }

    @staticmethod
    def build_multi_supplier(
        suppliers: List[Dict[str, str]],
        materials: List[Dict[str, Any]],
        project_name: str = "",
        delivery_address: str = "",
    ) -> List[Dict[str, str]]:
        """
        Сформировать RFQ для нескольких поставщиков.

        Returns:
            [{supplier, email, subject, body}, ...]
        """
        rfq_data = RFQBuilder.build_from_spec(
            materials, project_name, delivery_address
        )
        return [
            {
                "supplier": s.get("name", ""),
                "email": s.get("email", ""),
                "subject": rfq_data["subject"],
                "body": f"Уважаемый {s.get('name', 'поставщик')}!\n\n{rfq_data['body'].split('Уважаемые коллеги!')[1] if 'Уважаемые коллеги!' in rfq_data['body'] else rfq_data['body']}",
            }
            for s in suppliers
        ]


# =============================================================================
# Singleton
# =============================================================================

agent_mailbox = AgentMailbox()
rfq_builder = RFQBuilder()
