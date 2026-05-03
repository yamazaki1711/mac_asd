"""
ASD v12.0 — Knowledge Invalidation Engine.

Platform-level service for regulatory change detection, knowledge invalidation,
and versioned validity tracking across ALL agents (ПТО, Юрист, Сметчик, Закупщик).

Architecture:
  TelegramScout → DomainTrap (domain=legal/pto/smeta) → InvalidationEngine
    → affected knowledge entries (idprosto, traps, templates, norms)
    → agents query check_validity() before generating responses

Two modes:
  1. LLM-powered (Gemma 4 31B, Mac Studio) — semantic matching
  2. Keyword-based (fallback, weak GPU) — normative ref string matching

Usage:
    from src.core.knowledge.invalidation_engine import invalidation_engine

    # Process incoming DomainTrap — detect if it's a regulatory change
    affected = await invalidation_engine.process_trap(domain_trap_dict)

    # Agent-side: check validity before generating response
    status = invalidation_engine.check_validity("СП 70.13330.2012 п.3.5")
    # → {"valid": True/False, "status": "active"|"stale"|"replaced", ...}
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Persistence
_STORE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "knowledge"
_STORE_PATH = _STORE_DIR / "knowledge_invalidation.json"

# =============================================================================
# Enums
# =============================================================================


class ChangeType(str, Enum):
    REPEAL = "repeal"            # Полная отмена документа
    REPLACEMENT = "replacement"  # Замена новым документом
    AMENDMENT = "amendment"      # Изменение/дополнение
    CLARIFICATION = "clarification"  # Разъяснение/уточнение
    NEW = "new"                  # Новый документ (добавляет, не отменяет)


class EntryStatus(str, Enum):
    ACTIVE = "active"            # Действует
    STALE = "stale"              # Устарел (отменён, не заменён)
    REPLACED = "replaced"        # Заменён новым
    AMENDED = "amended"          # Изменён (частично недействителен)
    UNDER_REVIEW = "under_review"  # На рассмотрении (помечено, ждёт подтверждения)


# =============================================================================
# Data Models
# =============================================================================


class RegulatoryChange:
    """One detected regulatory change from external source."""
    def __init__(
        self,
        change_id: str,
        domain: str,               # "legal", "pto", "smeta"
        change_type: ChangeType,
        title: str,
        description: str,
        affected_norms: List[str],  # List of normative refs affected
        new_norms: List[str] = None,  # Replacement norms (if REPLACEMENT)
        source: str = "",           # "telegram/минстрой/prikaz-1234"
        effective_date: str = "",   # When the change takes effect
        confidence: float = 0.7,
        created_at: str = "",
    ):
        self.change_id = change_id
        self.domain = domain
        self.change_type = change_type
        self.title = title
        self.description = description
        self.affected_norms = affected_norms or []
        self.new_norms = new_norms or []
        self.source = source
        self.effective_date = effective_date
        self.confidence = confidence
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_id": self.change_id,
            "domain": self.domain,
            "change_type": self.change_type.value,
            "title": self.title,
            "description": self.description,
            "affected_norms": self.affected_norms,
            "new_norms": self.new_norms,
            "source": self.source,
            "effective_date": self.effective_date,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RegulatoryChange":
        return cls(
            change_id=d["change_id"],
            domain=d["domain"],
            change_type=ChangeType(d["change_type"]),
            title=d["title"],
            description=d["description"],
            affected_norms=d.get("affected_norms", []),
            new_norms=d.get("new_norms", []),
            source=d.get("source", ""),
            effective_date=d.get("effective_date", ""),
            confidence=d.get("confidence", 0.7),
            created_at=d.get("created_at", ""),
        )


class AffectedEntry:
    """Result: a specific knowledge entry affected by a regulatory change."""
    def __init__(
        self,
        entry_type: str,            # "normative_ref", "template", "checklist_row", "trap"
        entry_ref: str,             # The normative reference or entry ID
        agent_domain: str,           # Which agent is affected
        change: RegulatoryChange,
        new_status: EntryStatus,
        detail: str = "",
    ):
        self.entry_type = entry_type
        self.entry_ref = entry_ref
        self.agent_domain = agent_domain
        self.change = change
        self.new_status = new_status
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_type": self.entry_type,
            "entry_ref": self.entry_ref,
            "agent_domain": self.agent_domain,
            "change_id": self.change.change_id,
            "new_status": self.new_status.value,
            "detail": self.detail,
        }


# =============================================================================
# Keyword-based change detection (fallback mode, no LLM)
# =============================================================================

# Patterns that indicate a regulatory change in Russian legal/construction texts
_CHANGE_INDICATORS: Dict[ChangeType, List[str]] = {
    ChangeType.REPEAL: [
        r"отмен[еи]н[ао]?\s+(?:действие\s+)?(?:приказ|постановлен|распоряжен|норма|документ)",
        r"утратил[ао]?\s+силу",
        r"призна[нт][ао]?\s+утративш",
        r"прекратил[ао]?\s+действие",
        r"не\s+действует\s+(?:с|на\s+основании)",
        r"отмен[еи]ть\s+действие",
        r"исключ[еи]н[аыо]\s+(?:из|пункт|раздел)",
    ],
    ChangeType.REPLACEMENT: [
        r"взамен\s+(?:ранее\s+)?действовавш",
        r"замен[яи]ет(?:ся)?\s+(?:собой\s+)?(?:приказ|документ|норм)",
        r"в\s+новой\s+редакции",
        r"вместо\s+(?:приказ|документ|норм|СП|ГОСТ)",
        r"новая\s+редакция\s+(?:приказ|документ|СП|ГОСТ)",
        r"актуализированная\s+редакция",
    ],
    ChangeType.AMENDMENT: [
        r"внесен[ыо]\s+изменен",
        r"дополнен[ыо]\s+(?:пункт|раздел|приложен)",
        r"изменен[ия]\s+(?:в|вступа)",
        r"ввести\s+(?:в\s+действие\s+)?изменен",
        r"утвержден[ыо]\s+изменен",
        r"изложить\s+(?:в|пункт|редакци)",
    ],
    ChangeType.CLARIFICATION: [
        r"разъясн[еи]н[ия]\s+(?:порядк|применен|положен)",
        r"письмо\s+(?:минстро|ростехнадзор|минприрод)",
        r"информаци[яю]\s+(?:об|о|минстро)",
        r"рекомендаци[ия]\s+по\s+применени",
        r"методическ[ия][ех]\s+(?:указани|рекомендаци|пособи)",
    ],
    ChangeType.NEW: [
        r"утвержден[аоы]\s+(?:нов[аяоеый]|приказ|постановлен|распоряжен)",
        r"вступает\s+в\s+силу",
        r"введён\s+в\s+действие",
        r"опубликован[ао]\s+(?:приказ|постановлен|СП|ГОСТ)",
        r"принят[ао]\s+(?:нов[аяоеый]|приказ|закон|постановлен)",
    ],
}

# Keywords mapping to domains
_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "pto": [
        r"исполнительн\w*\s+документац", "АОСР", "АООК", r"скрыт\w*\s+работ",
        r"журнал\w*\s+работ", "ОЖР", "стройконтрол", r"строительн\w*\s+контрол",
        r"СП\s*\d{2,3}\.?\d*\.?\d*", r"ГОСТ\s*(?:Р\s*)?\d",
        r"приказ\s+минстро", "344/пр", "1026/пр",
        r"проект\w*\s+документац", r"рабоч\w*\s+чертеж", "геодезическ",
        r"испытани\w*\s+(?:бетон|грунт|свар)", r"сертификат\s+соответств",
    ],
    "legal": [
        "44-ФЗ", "223-ФЗ", "контракт", r"договор\s+подряд", "субподряд",
        "закупк", "тендер", "аукцион", "конкурс", r"единственн\w*\s+поставщик",
        r"обеспечен\w*\s+(?:контракт|заявк|гарант)", "неустойк", "штраф",
        "банкротств", "ликвидаци", r"исключен\w*\s+(?:из|из\s+ЕГРЮЛ|из\s+реестр)",
        r"арбитражн\w*\s+суд", r"ВС\s+РФ", "кассаци", "апелляци",
        r"постановлен\w*\s+(?:правительств|Правительств|пленум)",
        "ФАС", "УФАС", "РНП", "недобросовестн",
    ],
    "smeta": [
        "ФЕР", "ТЕР", "ГЭСН", r"сметн\w*\s+(?:норматив|стоимост|расчёт)",
        "НМЦК", r"начальн\w*\s+(?:максимальн|цен)", "коэффициент",
        r"индекс\w*\s+(?:изменен|пересчёт|цен)",
        "КС-2", "КС-3", r"акт\w*\s+(?:приёмк|выполнен)",
        "рентабельност", "прибыль", r"накладн\w*\s+расход",
    ],
}


# =============================================================================
# Invalidation Engine
# =============================================================================


class InvalidationEngine:
    """
    Knowledge Invalidation Engine.

    Detects regulatory changes from DomainTraps, computes affected knowledge
    entries, maintains versioned validity records, and provides a check_validity()
    API for all agents.
    """

    def __init__(self, llm_engine=None):
        self._llm = llm_engine
        self._changes: Dict[str, RegulatoryChange] = {}  # change_id → change
        self._affected: Dict[str, List[AffectedEntry]] = {}  # norm_ref → [entries]
        self._norm_status: Dict[str, EntryStatus] = {}  # norm_ref → current status
        self._norm_replacements: Dict[str, str] = {}  # stale norm → replacement norm
        self._load()

    # =========================================================================
    # Persistence
    # =========================================================================

    def _load(self) -> None:
        """Load invalidation store from disk."""
        if not _STORE_PATH.exists():
            return
        try:
            with open(_STORE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for cd in data.get("changes", []):
                change = RegulatoryChange.from_dict(cd)
                self._changes[change.change_id] = change
            for k, v in data.get("status", {}).items():
                self._norm_status[k] = EntryStatus(v)
            self._norm_replacements = data.get("replacements", {})
            logger.info("Loaded %d changes, %d statuses from invalidation store",
                        len(self._changes), len(self._norm_status))
        except Exception as e:
            logger.warning("Failed to load invalidation store: %s", e)

    def _save(self) -> None:
        """Persist invalidation store to disk."""
        _STORE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "changes": [c.to_dict() for c in self._changes.values()],
            "status": {k: v.value for k, v in self._norm_status.items()},
            "replacements": self._norm_replacements,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # =========================================================================
    # Change Detection
    # =========================================================================

    def detect_change_type(self, text: str) -> Optional[ChangeType]:
        """
        Keyword-based detection: does this text describe a regulatory change?

        Returns ChangeType if detected, None if not a regulatory announcement.
        """
        text_lower = text.lower()
        scored: Dict[ChangeType, int] = {}

        for ct, patterns in _CHANGE_INDICATORS.items():
            score = 0
            for pat in patterns:
                if re.search(pat, text_lower):
                    score += 1
            if score > 0:
                scored[ct] = score

        if not scored:
            return None

        # Return the type with the most pattern matches
        return max(scored, key=scored.get)

    def classify_domain(self, text: str, source_domain: str = "") -> List[str]:
        """
        Determine which agent domains are affected by a regulatory change text.

        Returns list of domains: ["pto", "legal", "smeta"]
        """
        text_lower = text.lower()
        domains = []

        if source_domain and source_domain in ("pto", "legal", "smeta"):
            domains.append(source_domain)

        for domain, keywords in _DOMAIN_KEYWORDS.items():
            if domain in domains:
                continue
            for kw in keywords:
                if re.search(kw, text_lower, re.IGNORECASE):
                    domains.append(domain)
                    break

        return domains or ["legal"]  # default to legal if nothing matches

    def extract_norms_from_text(self, text: str) -> List[str]:
        """Extract normative references from free text."""
        refs = set()

        patterns = [
            r'(?:Приказ[а]?\s+(?:Минстроя|Ростехнадзора|Минприроды)\s*(?:России\s*)?(?:№|N|от\s+)?\s*[\d/а-я]+(?:/\d+)?)',
            r'(?:СП\s*\d{2,3}[.\d]*\d{4})',
            r'(?:ГОСТ\s*(?:Р\s*)?[\d.]+[\w\d.-]*)',
            r'(?:ПП\s*РФ\s*№?\s*[\d]+)',
            r'(?:Федеральн\w*\s+закон\s*(?:№|от\s+)?\s*[\d]+-ФЗ)',
            r'(?:(?:44|223)-ФЗ)',
            r'(?:РД[\s-]*[\d.]+[\w\d.-]*)',
            r'(?:ВСН\s*[\d.]+[\w\d.-]*)',
            r'(?:СНиП\s*[\d.]+[\w\d.-]*)',
            r'(?:ФЕР|ТЕР|ГЭСН)[\s\d\w.-]*',
        ]

        for pat in patterns:
            for m in re.findall(pat, text, re.IGNORECASE):
                refs.add(m.strip())

        return list(refs)

    # =========================================================================
    # Main Pipeline: process incoming trap → detect change → compute affected
    # =========================================================================

    async def process_trap(self, trap: Dict[str, Any]) -> List[AffectedEntry]:
        """
        Process an incoming DomainTrap and check if it's a regulatory change.

        Args:
            trap: DomainTrap-like dict with:
                domain, title, description, source, category

        Returns:
            List of AffectedEntry if changes were detected, empty list if not.
        """
        domain = trap.get("domain", "legal")
        title = trap.get("title", "")
        description = trap.get("description", "")
        source = trap.get("source", trap.get("channel", ""))
        full_text = f"{title}. {description}"

        # 1. Detect if this is a regulatory change
        change_type = self.detect_change_type(full_text)
        if change_type is None:
            logger.debug("No regulatory change detected in trap: %s", title[:80])
            return []

        # 2. Extract affected normative references
        affected_norms = self.extract_norms_from_text(full_text)
        if not affected_norms:
            logger.debug("No normative refs extracted from: %s", title[:80])

        # 3. Determine affected domains
        domains = self.classify_domain(full_text, domain)

        # 4. Try LLM for better extraction if available
        if self._llm is not None and affected_norms:
            try:
                llm_change = await self._llm_extract_change(full_text, domain)
                if llm_change:
                    affected_norms = list(set(affected_norms + llm_change.get("affected_norms", [])))
                    change_type = ChangeType(llm_change.get("change_type", change_type.value))
            except Exception as e:
                logger.debug("LLM extraction fallback failed: %s", e)

        # 5. Create RegulatoryChange record
        change_id = _hash_id(f"{domain}:{title}:{datetime.now(timezone.utc).isoformat()}")
        change = RegulatoryChange(
            change_id=change_id,
            domain=domain,
            change_type=change_type,
            title=title,
            description=description,
            affected_norms=affected_norms,
            source=source,
            effective_date=_extract_effective_date(full_text),
            confidence=0.75 if self._llm else 0.60,
        )

        # 6. Compute affected entries across all knowledge bases
        affected = self._compute_affected(change, domains)

        # 7. Persist
        self._changes[change_id] = change
        for entry in affected:
            self._norm_status[entry.entry_ref] = entry.new_status
            if change_type == ChangeType.REPLACEMENT and change.new_norms:
                self._norm_replacements[entry.entry_ref] = change.new_norms[0]
        self._save()

        if affected:
            logger.info(
                "Invalidation: %s → %d affected entries across %s",
                change_type.value, len(affected), ",".join(domains),
            )

        return affected

    async def _llm_extract_change(
        self, text: str, domain: str
    ) -> Optional[Dict[str, Any]]:
        """LLM-powered extraction of regulatory change details."""
        prompt = f"""Проанализируй текст на наличие изменений в нормативной базе.

ДОМЕН: {domain}
ТЕКСТ: {text[:3000]}

ОПРЕДЕЛИ:
1. change_type: repeal (отмена), replacement (замена), amendment (изменение),
   clarification (разъяснение), new (новый документ)
2. affected_norms: список затронутых нормативных документов (коды)
3. new_norms: список новых/заменяющих документов (если есть)
4. effective_date: дата вступления в силу (YYYY-MM-DD)

Верни JSON:
{{"change_type": "replacement", "affected_norms": ["СП 70.13330.2012"], "new_norms": ["СП 70.13330.2025"], "effective_date": "2026-06-01"}}

Если текст НЕ содержит нормативных изменений, верни {{"is_change": false}}."""

        try:
            response = await self._llm.chat("pto", [
                {"role": "system", "content": "Ты — эксперт по нормативной базе строительства. Отвечай только JSON."},
                {"role": "user", "content": prompt},
            ], temperature=0.1)
            import json as _json
            result = _json.loads(response)
            if result.get("is_change") is False:
                return None
            return result
        except Exception as e:
            logger.debug("LLM extraction failed: %s", e)
            return None

    # =========================================================================
    # Affected Knowledge Computation
    # =========================================================================

    def _compute_affected(
        self, change: RegulatoryChange, domains: List[str]
    ) -> List[AffectedEntry]:
        """
        Compute which knowledge entries are affected by a regulatory change.

        Scans across:
          - idprosto_loader normative refs
          - template_registry templates
          - DomainTrap / LessonLearned entries
        """
        affected: List[AffectedEntry] = []

        # For each affected norm, determine agent domain and entry type
        for norm in change.affected_norms:
            norm_lower = norm.lower().replace(" ", "").replace("_", "")

            for domain in domains:
                # Check idprosto knowledge base
                affected.extend(self._check_idprosto_norms(norm, norm_lower, domain, change))

                # Check templates
                affected.extend(self._check_templates(norm, norm_lower, domain, change))

            # Cross-domain impact: a PTO norm change also affects Legal
            # (because contracts reference СП/ГОСТ compliance)
            if "pto" in domains and "legal" not in domains:
                affected.extend(self._check_legal_impact(norm, norm_lower, change))

        return affected

    def _check_idprosto_norms(
        self, norm: str, norm_lower: str, domain: str, change: RegulatoryChange
    ) -> List[AffectedEntry]:
        """Check idprosto knowledge base for affected normative refs."""
        entries = []
        try:
            from src.core.knowledge.idprosto_loader import idprosto_loader
            all_norms = idprosto_loader.get_all_normative_refs()
        except Exception:
            return entries

        for ref in all_norms:
            ref_lower = ref.lower().replace(" ", "").replace("_", "")
            if norm_lower in ref_lower or ref_lower in norm_lower:
                new_status = EntryStatus.STALE
                detail = f"Нормативный документ затронут изменением: {change.change_type.value}"
                if change.change_type == ChangeType.REPLACEMENT:
                    new_status = EntryStatus.REPLACED
                    detail += f". Замена: {', '.join(change.new_norms)}"
                elif change.change_type == ChangeType.AMENDMENT:
                    new_status = EntryStatus.AMENDED

                entries.append(AffectedEntry(
                    entry_type="normative_ref",
                    entry_ref=ref,
                    agent_domain=domain,
                    change=change,
                    new_status=new_status,
                    detail=detail,
                ))
        return entries

    def _check_templates(
        self, norm: str, norm_lower: str, domain: str, change: RegulatoryChange
    ) -> List[AffectedEntry]:
        """Check template registry for affected templates."""
        entries = []
        try:
            from src.core.knowledge.template_registry import template_registry
            matching = template_registry.resolve_form(norm)
        except Exception:
            return entries

        for tpl in matching:
            new_status = EntryStatus.STALE if change.change_type in (
                ChangeType.REPEAL, ChangeType.REPLACEMENT
            ) else EntryStatus.UNDER_REVIEW

            entries.append(AffectedEntry(
                entry_type="template",
                entry_ref=tpl.get("file_name", ""),
                agent_domain=domain,
                change=change,
                new_status=new_status,
                detail=f"Шаблон {tpl.get('file_name', '')} затронут изменением нормативной базы",
            ))
        return entries

    def _check_legal_impact(
        self, norm: str, norm_lower: str, change: RegulatoryChange
    ) -> List[AffectedEntry]:
        """
        PTO norm changes that also affect Legal domain.
        Contracts reference СП/ГОСТ compliance — if the norm is repealed,
        contracts may become non-compliant.
        """
        entries = []
        # Only cross-impact for major structural norms
        major_norms = [
            "сп 48.13330", "сп 70.13330", "сп 543.1325800",
            "гост р 51872", "344/пр", "1026/пр",
        ]
        if not any(mn in norm_lower for mn in major_norms):
            return entries

        entries.append(AffectedEntry(
            entry_type="cross_domain",
            entry_ref=norm,
            agent_domain="legal",
            change=change,
            new_status=EntryStatus.UNDER_REVIEW,
            detail=(
                f"Изменение строительной нормативной базы ({norm}) "
                f"может повлиять на соответствие контрактов. "
                f"Требуется проверка договорных условий на ссылки к {norm}."
            ),
        ))
        return entries

    # =========================================================================
    # Agent API: check validity
    # =========================================================================

    def check_validity(self, norm_ref: str, as_of_date: str = "") -> Dict[str, Any]:
        """
        Check if a normative reference is still valid.

        Called by agents before generating responses.

        Args:
            norm_ref: normative reference like "СП 70.13330.2012 п.3.5"
            as_of_date: optional date for historical queries (ISO format)

        Returns:
            {
                "valid": bool,
                "status": "active"|"stale"|"replaced"|"amended"|"under_review",
                "replaced_by": str or None,
                "since": ISO date or None,
                "change_description": str or "",
                "warning": str or "",  # Human-readable warning for agent context
            }
        """
        norm_lower = norm_ref.lower().replace(" ", "").replace("_", "")
        norm_stripped = norm_ref.strip()

        # Exact match check
        for ref, status in self._norm_status.items():
            ref_lower = ref.lower().replace(" ", "").replace("_", "")
            if norm_lower in ref_lower or ref_lower in norm_lower:
                replacement = self._norm_replacements.get(ref)
                # Find the change that caused this
                change_desc = ""
                change_date = ""
                for entry_list in self._affected.values():
                    for entry in entry_list:
                        if entry.entry_ref == ref:
                            change_desc = entry.detail
                            change_date = entry.change.created_at[:10]
                            break

                warning = self._format_warning(status, replacement, change_desc)

                return {
                    "valid": status in (EntryStatus.ACTIVE, EntryStatus.AMENDED),
                    "status": status.value,
                    "replaced_by": replacement,
                    "change_date": change_date,
                    "change_description": change_desc,
                    "warning": warning,
                }

        # Fuzzy match
        for ref, status in self._norm_status.items():
            ref_lower = ref.lower().replace(" ", "").replace("_", "")
            # Check partial overlap (at least 60% of shorter string)
            shorter = min(len(norm_lower), len(ref_lower))
            if shorter < 10:
                continue
            overlap = 0
            for i in range(len(norm_lower) - 3):
                if norm_lower[i:i + 4] in ref_lower:
                    overlap += 1
            if overlap >= shorter * 0.4:
                replacement = self._norm_replacements.get(ref)
                warning = self._format_warning(status, replacement, "")
                return {
                    "valid": status in (EntryStatus.ACTIVE, EntryStatus.AMENDED),
                    "status": status.value,
                    "replaced_by": replacement,
                    "change_date": "",
                    "change_description": f"Нечёткое совпадение с {ref}",
                    "warning": warning,
                }

        # Not found — assume active
        return {
            "valid": True,
            "status": "active",
            "replaced_by": None,
            "change_date": "",
            "change_description": "",
            "warning": "",
        }

    def check_validity_batch(
        self, norm_refs: List[str], as_of_date: str = ""
    ) -> Dict[str, Dict[str, Any]]:
        """Check validity for multiple normative references at once."""
        return {ref: self.check_validity(ref, as_of_date) for ref in norm_refs}

    def _format_warning(
        self, status: EntryStatus, replacement: str, detail: str
    ) -> str:
        """Format a human-readable warning for agent context injection."""
        if status == EntryStatus.ACTIVE:
            return ""
        if status == EntryStatus.STALE:
            return f"ПРЕДУПРЕЖДЕНИЕ: документ утратил силу. {detail}"
        if status == EntryStatus.REPLACED:
            rep = f" Заменён на: {replacement}." if replacement else ""
            return f"ПРЕДУПРЕЖДЕНИЕ: документ заменён.{rep} {detail}"
        if status == EntryStatus.AMENDED:
            return f"ВНИМАНИЕ: в документ внесены изменения. {detail}"
        if status == EntryStatus.UNDER_REVIEW:
            return f"ВНИМАНИЕ: возможны изменения нормативной базы. Требуется проверка. {detail}"
        return ""

    # =========================================================================
    # Reporting
    # =========================================================================

    def get_stale_norms(self, domain: str = "") -> List[Dict[str, Any]]:
        """Get all stale/replaced norms, optionally filtered by domain."""
        result = []
        for norm, status in self._norm_status.items():
            if status in (EntryStatus.STALE, EntryStatus.REPLACED):
                if domain and domain not in self._get_norm_domain(norm):
                    continue
                result.append({
                    "norm": norm,
                    "status": status.value,
                    "replaced_by": self._norm_replacements.get(norm),
                })
        return result

    def _get_norm_domain(self, norm: str) -> str:
        """Guess which domain a norm belongs to."""
        norm_lower = norm.lower()
        if any(kw in norm_lower for kw in ["сп ", "гост", "приказ минстро", "снип", "всн", "рд"]):
            return "pto"
        if any(kw in norm_lower for kw in ["фз", "44-фз", "223-фз", "постановлен"]):
            return "legal"
        if any(kw in norm_lower for kw in ["фер", "тер", "гэсн"]):
            return "smeta"
        return "unknown"

    def get_summary(self) -> Dict[str, Any]:
        """Get invalidation summary for dashboard."""
        return {
            "total_changes": len(self._changes),
            "stale_norms": sum(
                1 for s in self._norm_status.values()
                if s in (EntryStatus.STALE, EntryStatus.REPLACED)
            ),
            "amended_norms": sum(
                1 for s in self._norm_status.values()
                if s == EntryStatus.AMENDED
            ),
            "active_norms": sum(
                1 for s in self._norm_status.values()
                if s == EntryStatus.ACTIVE
            ),
            "by_domain": {
                domain: len(self.get_stale_norms(domain))
                for domain in ("pto", "legal", "smeta")
            },
            "last_updated": max(
                (c.created_at for c in self._changes.values()),
                default="never",
            ),
        }

    def process_text(self, text: str, domain: str = "legal", source: str = "manual") -> List[AffectedEntry]:
        """
        Process a raw text (not from DomainTrap) — for CLI / manual input.

        Detects regulatory changes in arbitrary text and computes affected entries.
        """
        change_type = self.detect_change_type(text)
        if change_type is None:
            return []

        affected_norms = self.extract_norms_from_text(text)
        domains = self.classify_domain(text, domain)

        change_id = _hash_id(f"text:{domain}:{text[:80]}:{datetime.now(timezone.utc).isoformat()}")
        change = RegulatoryChange(
            change_id=change_id,
            domain=domain,
            change_type=change_type,
            title=text[:120],
            description=text,
            affected_norms=affected_norms,
            source=source,
            effective_date=_extract_effective_date(text),
            confidence=0.55,  # Lower confidence for raw text
        )

        affected = self._compute_affected(change, domains)

        self._changes[change_id] = change
        for entry in affected:
            self._norm_status[entry.entry_ref] = entry.new_status
            if change_type == ChangeType.REPLACEMENT and change.new_norms:
                self._norm_replacements[entry.entry_ref] = change.new_norms[0]
        self._save()

        return affected


# =============================================================================
# Helpers
# =============================================================================


def _hash_id(raw: str) -> str:
    import hashlib
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _extract_effective_date(text: str) -> str:
    """Try to extract effective date from text."""
    date_patterns = [
        r'(\d{4}-\d{2}-\d{2})',  # ISO
        r'с\s+(\d{1,2})[./](\d{1,2})[./](\d{4})',
        r'вступает\s+в\s+силу\s+(\d{1,2})[./](\d{1,2})[./](\d{4})',
        r'действует\s+с\s+(\d{1,2})[./](\d{1,2})[./](\d{4})',
    ]
    for pat in date_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            if len(m.groups()) == 3:
                day, month, year = int(m[1]), int(m[2]), int(m[3])
                return f"{year:04d}-{month:02d}-{day:02d}"
            return m.group(1)
    return ""


# Singleton
invalidation_engine = InvalidationEngine()
