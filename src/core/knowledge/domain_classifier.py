"""
ASD v12.0 — Domain Classifier.

Determines domain relevance of incoming content (Telegram, web, etc.)
and filters out noise, ads, and spam.

Domains: legal, pto, smeta, procurement, logistics
Noise categories: ad, spam, news_fluff, irrelevant

Strategy (3-tier):
  Tier 1 — Keyword signal scan (fast, <1ms): ad patterns, domain keywords
  Tier 2 — Channel metadata (when available): known channel → domain mapping
  Tier 3 — LLM classification (reserved for edge cases, not auto-triggered)

Usage:
    from src.core.knowledge.domain_classifier import domain_classifier

    result = domain_classifier.classify(text, source_channel="@advokatgrikevich")
    if result.domain and not result.is_noise:
        # Store in knowledge base
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set

logger = logging.getLogger(__name__)


# =============================================================================
# Data structures
# =============================================================================

@dataclass
class ClassificationResult:
    """Result of domain/noise classification."""
    domain: Optional[str] = None       # legal | pto | smeta | procurement | logistics | None
    is_noise: bool = True              # True if content should be rejected
    noise_type: str = ""               # ad | spam | news_fluff | irrelevant | empty
    confidence: float = 0.0            # 0.0–1.0
    signals: List[str] = field(default_factory=list)  # Which signals fired
    suggested_category: str = ""       # Domain-specific subcategory
    word_count: int = 0
    has_legal_refs: bool = False       # Contains GOST/SP/SNiP/law references
    has_construction_terms: bool = False

    @property
    def is_relevant(self) -> bool:
        return not self.is_noise and self.domain is not None


# =============================================================================
# Noise Patterns (Реклама / Спам / Шум)
# =============================================================================

# ---- Tier 1: Ad / Commercial patterns ----
AD_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b(скидка|скидки|акция|распродажа|спецпредложение|суперцена|выгодн|дешевл)\b', re.IGNORECASE),
    re.compile(r'\b(прайс[-\s]лист|прайсы|цены снижен|успей купить|только сегодня|ограниченное предложение)\b', re.IGNORECASE),
    re.compile(r'\b(купить|продам|продажа|заказать со скидкой|бесплатная доставка|заказ online|оформить заказ)\b', re.IGNORECASE),
    re.compile(r'\b(коммерческое предложение|КП\s*[№#]|отправим КП|запросить КП|счёт на оплату)\b', re.IGNORECASE),
    re.compile(r'\b(промокод|промо-код| % |процент скидки|кешбэк|cashback)\b', re.IGNORECASE),
    re.compile(r'\b(реклама|рекламный пост|партнёрский материал|спонсор|на правах рекламы|erid:|токен маркировки)\b', re.IGNORECASE),
    re.compile(r'(\bцена\b.*\b₽\b|\b\d{1,3}(?:[.,]\d{1,3})*\s*(?:₽|руб|р\.)\b.*\bкупить\b)', re.IGNORECASE),
    re.compile(r'\b(выгодное вложение|инвестиц|пассивный доход|заработок без|доходность|окупаемость)\b', re.IGNORECASE),
]

# ---- Tier 1: Pure spam / junk ----
SPAM_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b(заработок в интернете|работа на дому|ваканси[яи]|требу[ею]тся|набор сотрудников|MLM|сетевой маркетинг)\b', re.IGNORECASE),
    re.compile(r'\b(криптовалют|биткоин|bitcoin|токен|майнинг|ферма|блокчейн-проект)\b', re.IGNORECASE),
    re.compile(r'\b(казино|ставки на спорт|букмекер|лотерея|розыгрыш призов|1xbet|фонбет)\b', re.IGNORECASE),
    re.compile(r'\b(похуде[йт]|диета|целлюлит|омоложени|ботокс|косметолог|увеличение губ|пластическая)\b', re.IGNORECASE),
    re.compile(r'\b(психолог|коуч|тренинг личностного|марафон желаний|трансформаци[яи]|энергетическ|чакры|медитаци[яи])\b', re.IGNORECASE),
    re.compile(r'\b(продам аккаунт|куплю аккаунт|взлом|хакер|слив базы|пробив)\b', re.IGNORECASE),
]

# ---- Tier 1: News fluff (not domain-relevant) ----
NEWS_FLUFF_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b(погода на|прогноз погоды|дожди|снегопад|жара|похолодание|циклон)\b', re.IGNORECASE),
    re.compile(r'\b(курс валют|доллар|евро|юань|биржа|индекс Мосбиржи|котировки)\b', re.IGNORECASE),
    re.compile(r'\b(политик|выборы|госдума|путин|оппозици[яи]|митинг|протест)\b', re.IGNORECASE),
    re.compile(r'\b(футбол|хоккей|чемпионат|спортсмен|олимпиад|сборная)\b', re.IGNORECASE),
    re.compile(r'\b(шоу[-\s]бизнес|звезда|певиц|акт[её]р|сериал|премьера фильма|кинопремьера)\b', re.IGNORECASE),
    re.compile(r'\b(DDoS|хакерская атака|утечка данных|санкци[ия]|санкционный)\b', re.IGNORECASE),
]


# =============================================================================
# Domain Signal Patterns
# =============================================================================

# ---- LEGAL — юридическая тематика ----
LEGAL_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b(арбитражный суд|арбитражная практика|апелляци[яи]|кассаци[яи]|постановление суда|определение ВС|пленум ВС)\b', re.IGNORECASE),
    re.compile(r'\b(ГК РФ|ГрК РФ|АПК РФ|ГПК РФ|ФЗ[-\s]?\d{2,3}|Федеральный закон|КоАП|НК РФ|ТК РФ)\b', re.IGNORECASE),
    re.compile(r'\b(неустойк[аи]|пен[яи]|штраф|проценты по 395|ст\.\s*395|ст\.\s*333|убытки|реальный ущерб|упущенная выгода)\b', re.IGNORECASE),
    re.compile(r'\b(договор подряда|субподряд|генподряд|заказчик|подрядчик|исполнитель|контрагент|приёмк[аи] работ|сдача[-\s]приёмка)\b', re.IGNORECASE),
    re.compile(r'\b(протокол разногласий|досудебная претензия|исковое заявление|мотивированный отказ|претензи[яи]|иск|ответчик|истец)\b', re.IGNORECASE),
    re.compile(r'\b(банкротств|наблюдение|конкурсный управляющий|реестр требований|субсидиарная ответственность|мораторий)\b', re.IGNORECASE),
    re.compile(r'\b(ФЗ-44|ФЗ-223|госзакупки|тендер|аукцион|конкурс|закупочная документация|НМЦК|обеспечени[ея] контракта)\b', re.IGNORECASE),
    re.compile(r'\b(БЛС|ловушк[аи] подрядчика|риск|обременительн|кабальн|ничтожн|оспорим|недействительн)\b', re.IGNORECASE),
]

# ---- PTO — производственно-технический отдел ----
PTO_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b(исполнительная документаци[яи]|ИД|АОСР|АООК|акт освидетельствовани[яи]|скрытые работы|спецжурнал|ОЖР|ЖБР|ЖСР|ЖВК)\b', re.IGNORECASE),
    re.compile(r'\b(ГОСТ|СП\s*\d|СНиП|ВСН|343/пр|344/пр|468/пр|нормативн|технический регламент|техрегламент)\b', re.IGNORECASE),
    re.compile(r'\b(исполнительная схема|ИГС|геодезическая съёмка|отклонени[ея]|допуск|проектная документаци[яи]|ПД|РД|рабочая документаци[яи])\b', re.IGNORECASE),
    re.compile(r'\b(стройконтроль|технадзор|авторский надзор|лабораторный контроль|протокол испытани[йя]|неразрушающий контроль|УЗК|ультразвуковой|рентгенографи[яи]|ВИК)\b', re.IGNORECASE),
    re.compile(r'\b(КС-2|КС-3|КС-6а|акт выполненных работ|справка о стоимости|процент выполнени[яи]|освоени[ея]|сметная стоимость|единичная расценка)\b', re.IGNORECASE),
    re.compile(r'\b(захватк[аи]|стройплощадк[аи]|армирование|бетонирование|опалубк[аи]|монолит|сва[ия]|шпунт|котлован|земляные работы|обратная засыпка)\b', re.IGNORECASE),
    re.compile(r'\b(сертификат качества|паспорт издели[яй]|входной контроль|парти[яи] ТМЦ|документ[ыа] о качестве|завод-изготовитель)\b', re.IGNORECASE),
    re.compile(r'\b(BIM|ТИМ|цифровая модель|Revit|Navisworks|информационное моделирование|среда общих данных)\b', re.IGNORECASE),
]

# ---- SMETA — сметное дело ----
SMETA_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b(смет[аы]|сметный расчёт|ЛСР|локальная смета|объектная смета|ССР|сводный сметный расчёт|сметная документаци[яи])\b', re.IGNORECASE),
    re.compile(r'\b(ФЕР|ТЕР|ГЭСН|МДС|единичная расценка|прямые затраты|накладные расходы|сметная прибыль|зимнее удорожание|коэффициент|индекс пересчёта)\b', re.IGNORECASE),
    re.compile(r'\b(ценообразование|Минстрой|приказ Минстроя|индексы Минстроя|мониторинг цен|конъюнктурный анализ|прайс-лист|коммерческое предложение)\b', re.IGNORECASE),
    re.compile(r'\b(ВОР|ведомость объёмов работ|объём[ыа] работ|спецификаци[яи]|дефектная ведомость|акт технического обследования)\b', re.IGNORECASE),
    re.compile(r'\b(заработная плата|трудозатраты|чел\.-час|чел\.-день|машино-час|эксплуатация машин|материалы|стоимость материалов)\b', re.IGNORECASE),
]

# ---- PROCUREMENT / LOGISTICS — закупки и логистика ----
PROCUREMENT_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b(поставщик|поставк[аи]|логистик[аи]|транспортная компания|доставка|фрахт|перевозчик|склад|хранение|отгрузка|приёмка ТМЦ|накладная|ТОРГ-12|УПД)\b', re.IGNORECASE),
    re.compile(r'\b(материал[ыа]|оборудование|труба|арматура|металлопрокат|железобетон|бетон|кирпич|щебень|песок|цемент|кабель|светильник)\b', re.IGNORECASE),
    re.compile(r'\b(тендер|аукцион|госзакупк[аи]|электронная площадка|закупк[аи]|конкурентная закупка|единственный поставщик|коммерческое предложение|техническое задание|ТЗ)\b', re.IGNORECASE),
    re.compile(r'\b(завод|производитель|дистрибьютор|дилер|оптов[аы][яй]|розниц[аы]|отсрочка платежа|предоплата|аванс|аккредитив|банковская гарантия)\b', re.IGNORECASE),
]


# =============================================================================
# Domain Classifier
# =============================================================================

class DomainClassifier:
    """
    Multi-domain content classifier with noise filtering.

    Determines:
      1. Is this noise/ad/spam? → reject immediately
      2. Which domain does it belong to? → legal/pto/smeta/procurement/logistics
      3. Confidence level
    """

    # Minimum word count for meaningful classification
    MIN_WORDS = 15

    # Maps domain to its patterns
    DOMAIN_PATTERNS: Dict[str, List[re.Pattern]] = {
        "legal": LEGAL_PATTERNS,
        "pto": PTO_PATTERNS,
        "smeta": SMETA_PATTERNS,
        "procurement": PROCUREMENT_PATTERNS,
        "logistics": PROCUREMENT_PATTERNS,  # shares procurement patterns
    }

    # Known channel → domain mapping (from telegram_channels.yaml)
    _channel_domain_map: Dict[str, str] = {}
    _loaded = False

    @classmethod
    def _load_channel_map(cls) -> None:
        """Load channel→domain mapping from YAML config."""
        if cls._loaded:
            return
        try:
            import yaml
            from pathlib import Path
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "telegram_channels.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    data = yaml.safe_load(f)
                for ch in data.get("channels", []):
                    username = ch.get("username", "").lower().replace("@", "")
                    domain = ch.get("domain", "")
                    if username and domain:
                        cls._channel_domain_map[username] = domain
                logger.info("Loaded %d channel→domain mappings", len(cls._channel_domain_map))
        except Exception as e:
            logger.warning("Failed to load channel map: %s", e)
        cls._loaded = True

    @classmethod
    def classify(
        cls,
        text: str,
        source_channel: Optional[str] = None,
        strict_noise: bool = True,
    ) -> ClassificationResult:
        """
        Classify content by domain and noise status.

        Args:
            text: Content text (from Telegram post, web article, etc.)
            source_channel: @username of source Telegram channel (for metadata-based boost)
            strict_noise: If True, aggressively filter borderline content

        Returns:
            ClassificationResult with domain, noise status, confidence
        """
        result = ClassificationResult()

        # --- Pre-check: Empty / too short ---
        if not text or len(text.strip()) < 20:
            result.is_noise = True
            result.noise_type = "empty"
            result.word_count = 0
            return result

        words = text.split()
        result.word_count = len(words)
        if result.word_count < cls.MIN_WORDS:
            result.is_noise = True
            result.noise_type = "too_short"
            return result

        # --- Tier 1: Noise detection (must come first) ---
        noise_hits, noise_type = cls._scan_noise(text, strict_noise)
        if noise_hits >= 2:
            result.is_noise = True
            result.noise_type = noise_type
            result.signals = [f"noise:{noise_type}:{noise_hits}"]
            return result

        # --- Check for legal/construction references ---
        result.has_legal_refs = cls._has_legal_references(text)

        # --- Check for construction terms ---
        result.has_construction_terms = cls._has_construction_terms(text)

        # --- Tier 2: Domain classification ---
        domain_scores = cls._score_domains(text, source_channel)

        if not domain_scores:
            # No domain signals at all — likely irrelevant
            if strict_noise:
                result.is_noise = True
                result.noise_type = "irrelevant"
                return result
            result.is_noise = False
            result.confidence = 0.0
            return result

        # Best domain
        best_domain, best_score = max(domain_scores.items(), key=lambda x: x[1])

        # Confidence thresholds
        if best_score >= 3:
            result.confidence = min(0.9, 0.5 + best_score * 0.1)
        elif best_score >= 2:
            result.confidence = 0.4 + best_score * 0.1
        else:
            result.confidence = 0.3

        # Boost confidence if channel metadata matches
        if source_channel:
            channel_domain = cls._get_channel_domain(source_channel)
            if channel_domain and channel_domain == best_domain:
                result.confidence = min(1.0, result.confidence + 0.15)

        # Boost if has legal/construction references
        if result.has_legal_refs:
            result.confidence = min(1.0, result.confidence + 0.1)
        if result.has_construction_terms:
            result.confidence = min(1.0, result.confidence + 0.1)

        # Final decision
        if result.confidence >= 0.35:
            result.domain = best_domain
            result.is_noise = False
            result.signals = [f"domain:{best_domain}:{best_score}"]
        elif strict_noise:
            result.is_noise = True
            result.noise_type = "low_confidence"
        else:
            result.is_noise = False
            result.domain = best_domain

        return result

    # =========================================================================
    # Noise scanning
    # =========================================================================

    @classmethod
    def _scan_noise(cls, text: str, strict: bool) -> tuple:
        """
        Scan text for noise signals.

        Returns:
            (total_noise_hits, noise_type)
        """
        ad_hits = sum(1 for p in AD_PATTERNS if p.search(text))
        spam_hits = sum(1 for p in SPAM_PATTERNS if p.search(text))
        fluff_hits = sum(1 for p in NEWS_FLUFF_PATTERNS if p.search(text))

        total = ad_hits + spam_hits + fluff_hits

        if spam_hits >= 1:
            return (total + 2, "spam")  # Heavy penalty for spam
        if ad_hits >= 2:
            return (total + 1, "ad")
        if strict and fluff_hits >= 3:
            return (total, "news_fluff")

        return (total, "")

    # =========================================================================
    # Domain scoring
    # =========================================================================

    @classmethod
    def _score_domains(
        cls, text: str, source_channel: Optional[str] = None
    ) -> Dict[str, int]:
        """Score each domain based on keyword matches."""
        scores: Dict[str, int] = {}

        for domain, patterns in cls.DOMAIN_PATTERNS.items():
            score = sum(1 for p in patterns if p.search(text))
            if score:
                scores[domain] = score

        # Channel metadata boost
        if source_channel:
            channel_domain = cls._get_channel_domain(source_channel)
            if channel_domain:
                scores[channel_domain] = scores.get(channel_domain, 0) + 2

        return scores

    # =========================================================================
    # Reference detection
    # =========================================================================

    _LEGAL_REF_PATTERN = re.compile(
        r'\b(ГК РФ|ГрК РФ|АПК РФ|ГПК РФ|ФЗ[-\s]?\d{2,3}|ГОСТ\s*\d|СП\s*\d{2,3}|СНиП|ВСН|'
        r'ст\.\s*\d{2,4}|п\.\s*\d|ч\.\s*\d|приказ Минстроя|постановление|определение|'
        r'пленум|президиум ВАС|ВС РФ|КС РФ)\b',
        re.IGNORECASE,
    )

    _CONSTRUCTION_TERM_PATTERN = re.compile(
        r'\b(договор подряда|строительств|подрядчик|заказчик|тендер|смета|'
        r'АОСР|АООК|КС-2|КС-3|исполнительная документаци|проектная документаци|'
        r'фундамент|бетон|арматура|металлоконструкци|кирпич|кладка|монтаж|'
        r'кровл[яи]|фасад|отделк[аи]|инженерные системы|отопление|вентиляци|'
        r'водоснабжение|канализация|электрик|освещение|пожаротушение|'
        r'БЛС|ловушк[аи]|риск[аи] подрядчика|субподряд)\b',
        re.IGNORECASE,
    )

    @classmethod
    def _has_legal_references(cls, text: str) -> bool:
        return bool(cls._LEGAL_REF_PATTERN.search(text))

    @classmethod
    def _has_construction_terms(cls, text: str) -> bool:
        return bool(cls._CONSTRUCTION_TERM_PATTERN.search(text))

    # =========================================================================
    # Channel metadata
    # =========================================================================

    @classmethod
    def _get_channel_domain(cls, channel: str) -> Optional[str]:
        cls._load_channel_map()
        key = channel.lower().replace("@", "").strip()
        return cls._channel_domain_map.get(key)

    # =========================================================================
    # Batch
    # =========================================================================

    @classmethod
    def classify_batch(
        cls,
        messages: List[Dict[str, Any]],
        strict_noise: bool = True,
    ) -> List[ClassificationResult]:
        """
        Classify batch of messages.

        Each message: {"text": str, "source_channel": Optional[str], "id": Any}
        """
        results = []
        for msg in messages:
            result = cls.classify(
                text=msg.get("text", ""),
                source_channel=msg.get("source_channel"),
                strict_noise=strict_noise,
            )
            results.append(result)

        accepted = sum(1 for r in results if r.is_relevant)
        rejected = sum(1 for r in results if r.is_noise)
        logger.info(
            "Batch classified: %d messages → %d accepted, %d rejected",
            len(results), accepted, rejected,
        )
        return results


# Singleton
domain_classifier = DomainClassifier()
