"""
ASD v13.0 — Inference Engine.

Symbolic inference rules для Evidence Graph v2.
Выводит недостающие факты из имеющихся — быстро, объяснимо, без галлюцинаций.

Правила:
  1. Поставка + типовой темп → даты работ
  2. КС-2 + подписи → WorkUnit существовал
  3. Фото с меткой → DateEvent
  4. Поставка → локация
  5. Технологическая цепочка → даты
  6. Подтверждение → повышение уверенности

Usage:
    from src.core.inference_engine import inference_engine

    findings = inference_engine.run_all(evidence_graph)
    # → List[InferenceResult] — что выведено, с confidence
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class InferenceResult:
    """Результат одного инференс-правила."""
    rule_name: str
    description: str
    new_facts: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    evidence_nodes: List[str] = field(default_factory=list)


# =============================================================================
# Typical Rates Loader
# =============================================================================

def _load_rates() -> Dict[str, Dict[str, Any]]:
    """Загрузить typical_rates.yaml."""
    rates_path = Path(__file__).parent.parent.parent / "data" / "typical_rates.yaml"
    try:
        with open(rates_path) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Failed to load typical_rates.yaml: %s", e)
        return {"default": {"rate": 1, "unit": "ед/день"}}


# =============================================================================
# Inference Engine
# =============================================================================

class InferenceEngine:
    """
    Symbolic inference engine.

    Запускает правила на Evidence Graph, создаёт новые узлы
    (WorkUnit, DateEvent) и связи с confidence < 1.0.
    """

    def __init__(self):
        self._rates = _load_rates()
        self._total_inferences = 0

    @property
    def rates(self) -> Dict[str, Dict[str, Any]]:
        """Публичный доступ к typical_rates (типовые темпы работ)."""
        return self._rates

    def run_all(self, graph) -> List[InferenceResult]:
        """
        Запустить все inference-правила на графе.

        Args:
            graph: EvidenceGraph instance

        Returns:
            Список InferenceResult — что выведено
        """
        from src.core.evidence_graph import (
            WorkUnitStatus, FactSource, DocType, EvidenceDocStatus as DocStatus,
            EventType, TimePrecision, EdgeType,
        )

        results = []

        # Правило 1: Поставка → даты работ
        r1 = self._rule_delivery_to_dates(graph)
        if r1.new_facts:
            results.append(r1)

        # Правило 2: КС-2 → WorkUnit существовал
        r2 = self._rule_ks2_to_workunit(graph)
        if r2.new_facts:
            results.append(r2)

        # Правило 3: Фото → DateEvent
        r3 = self._rule_photo_to_event(graph)
        if r3.new_facts:
            results.append(r3)

        # Правило 4: Поставка → локация
        r4 = self._rule_delivery_to_location(graph)
        if r4.new_facts:
            results.append(r4)

        # Правило 5: Технологическая цепочка → даты
        r5 = self._rule_temporal_chain(graph)
        if r5.new_facts:
            results.append(r5)

        # Правило 6: Повышение уверенности через подтверждение
        r6 = self._rule_confidence_boost(graph)
        if r6.new_facts:
            results.append(r6)

        self._total_inferences += sum(len(r.new_facts) for r in results)
        logger.info("Inference complete: %d rules fired, %d new facts",
                   len(results), sum(len(r.new_facts) for r in results))

        return results

    # ── Rule 1: Delivery → Dates ────────────────────────────────────────

    def _rule_delivery_to_dates(self, graph) -> InferenceResult:
        """
        IF MaterialBatch.delivery_date известен
           AND MaterialBatch → [USED_IN] → WorkUnit
           AND WorkUnit.volume известен
           AND typical_rate(WorkUnit.work_type) известен
        THEN
           INFER WorkUnit.start_date ≈ delivery_date + 1d
           INFER WorkUnit.end_date ≈ start_date + ceil(volume / rate) days
           confidence = batch.confidence * 0.9, capped at 0.85
        """
        result = InferenceResult(
            rule_name="delivery_to_dates",
            description="Поставка материала → вывод дат работ",
        )

        from src.core.evidence_graph import EdgeType, WorkUnitStatus, FactSource

        for batch_id, batch_data in graph.graph.nodes(data=True):
            if batch_data.get("node_type") != "MaterialBatch":
                continue

            delivery_str = batch_data.get("delivery_date")
            if not delivery_str:
                continue

            try:
                delivery_date = date.fromisoformat(delivery_str)
            except (ValueError, TypeError):
                continue

            batch_conf = batch_data.get("confidence", 1.0)

            # Ищем WorkUnit, связанные с этой партией
            for wu_id in graph.graph.successors(batch_id):
                wu_data = graph.graph.nodes[wu_id]
                if wu_data.get("node_type") != "WorkUnit":
                    continue

                edge_data = graph.graph.edges[batch_id, wu_id]
                if edge_data.get("edge_type") != EdgeType.USED_IN.value:
                    continue

                wu_volume = wu_data.get("volume")
                if not wu_volume:
                    continue

                wu_type = wu_data.get("work_type", "")
                rate_info = self._rates.get(wu_type, self._rates.get("default", {"rate": 1}))
                daily_rate = rate_info.get("rate", 1)
                work_days = max(1, int(wu_volume / daily_rate + 0.5))

                start = delivery_date + timedelta(days=1)
                end = start + timedelta(days=work_days - 1)

                conf = min(batch_conf * 0.9, 0.85)

                # Обновляем WorkUnit
                if not wu_data.get("start_date"):
                    graph.graph.nodes[wu_id]["start_date"] = start.isoformat()
                    graph.graph.nodes[wu_id]["end_date"] = end.isoformat()
                    graph.graph.nodes[wu_id]["confidence"] = conf
                    if wu_data.get("status") != WorkUnitStatus.CONFIRMED.value:
                        graph.graph.nodes[wu_id]["status"] = WorkUnitStatus.INFERRED.value
                        graph.graph.nodes[wu_id]["source"] = FactSource.INFERENCE.value

                    result.new_facts.append({
                        "type": "work_unit_dates",
                        "work_unit_id": wu_id,
                        "work_type": wu_type,
                        "inferred_start": start.isoformat(),
                        "inferred_end": end.isoformat(),
                        "work_days": work_days,
                        "daily_rate": daily_rate,
                        "confidence": round(conf, 2),
                    })
                    result.evidence_nodes.extend([batch_id, wu_id])

        if result.new_facts:
            result.confidence = min(
                0.85, sum(n["confidence"] for n in result.new_facts) / len(result.new_facts)
            )
            graph.save()

        return result

    # ── Rule 2: KS-2 → WorkUnit Existed ─────────────────────────────────

    def _rule_ks2_to_workunit(self, graph) -> InferenceResult:
        """
        IF Document[doc_type=KS2] подписан
           AND Document[KS2] → [CONFIRMED_BY] → WorkUnit
        THEN
           INFER WorkUnit существовал на дату КС-2
           confidence = 0.8
        """
        result = InferenceResult(
            rule_name="ks2_to_workunit",
            description="КС-2 с подписями → подтверждение WorkUnit",
        )

        from src.core.evidence_graph import DocType, EdgeType, WorkUnitStatus, FactSource

        for doc_id, doc_data in graph.graph.nodes(data=True):
            if doc_data.get("node_type") != "Document":
                continue
            if doc_data.get("doc_type") != DocType.KS2.value:
                continue
            if not doc_data.get("signatures_present"):
                continue

            doc_date_str = doc_data.get("doc_date")
            if not doc_date_str:
                continue

            # Ищем WorkUnit, подтверждённый этим КС-2
            for pred_id in graph.graph.predecessors(doc_id):
                pred_data = graph.graph.nodes[pred_id]
                if pred_data.get("node_type") != "WorkUnit":
                    continue

                edge = graph.graph.edges[pred_id, doc_id]
                if edge.get("edge_type") != EdgeType.CONFIRMED_BY.value:
                    continue

                if pred_data.get("status") in (WorkUnitStatus.INFERRED.value,):
                    # Повышаем статус
                    graph.graph.nodes[pred_id]["status"] = WorkUnitStatus.CONFIRMED.value
                    graph.graph.nodes[pred_id]["confidence"] = min(
                        pred_data.get("confidence", 0.5) + 0.2, 0.95
                    )
                    graph.graph.nodes[pred_id]["source"] = FactSource.INFERENCE.value

                    result.new_facts.append({
                        "type": "work_unit_confirmed",
                        "work_unit_id": pred_id,
                        "confirmed_by_doc": doc_id,
                        "ks2_date": doc_date_str,
                        "new_confidence": graph.graph.nodes[pred_id]["confidence"],
                    })
                    result.evidence_nodes.extend([doc_id, pred_id])

        if result.new_facts:
            result.confidence = 0.8
            graph.save()

        return result

    # ── Rule 3: Photo → DateEvent ───────────────────────────────────────

    def _rule_photo_to_event(self, graph) -> InferenceResult:
        """
        IF Document[doc_type=PHOTO] имеет EXIF-дату
           AND Document[PHOTO] → [CONFIRMED_BY] → WorkUnit
        THEN
           CREATE DateEvent(PHOTO_TAKEN, timestamp=EXIF_date, confidence=0.85)
        """
        result = InferenceResult(
            rule_name="photo_to_event",
            description="Фото с меткой времени → DateEvent",
        )

        from src.core.evidence_graph import DocType, EdgeType, EventType, TimePrecision

        for doc_id, doc_data in graph.graph.nodes(data=True):
            if doc_data.get("node_type") != "Document":
                continue
            if doc_data.get("doc_type") != DocType.PHOTO.value:
                continue

            # Ищем EXIF-дату (поле doc_date или metadata)
            photo_date_str = doc_data.get("doc_date")
            if not photo_date_str:
                continue

            try:
                photo_date = date.fromisoformat(photo_date_str)
            except (ValueError, TypeError):
                continue

            # К какому WorkUnit относится фото?
            wu_ids = [
                pred_id for pred_id in graph.graph.predecessors(doc_id)
                if graph.graph.nodes[pred_id].get("node_type") == "WorkUnit"
                and graph.graph.edges[pred_id, doc_id].get("edge_type") == EdgeType.CONFIRMED_BY.value
            ]

            for wu_id in wu_ids:
                evt_id = graph.add_date_event(
                    event_type=EventType.PHOTO_TAKEN,
                    timestamp=datetime(photo_date.year, photo_date.month, photo_date.day, 12, 0),
                    description=f"Фото: {doc_data.get('content_summary', doc_id)}",
                    precision=TimePrecision.DAY,
                    source_document_id=doc_id,
                    confidence=0.85,
                )
                graph.link(wu_id, evt_id, EdgeType.HAS_EVENT, confidence=0.85)

                result.new_facts.append({
                    "type": "date_event_from_photo",
                    "event_id": evt_id,
                    "work_unit_id": wu_id,
                    "photo_date": photo_date_str,
                })
                result.evidence_nodes.extend([doc_id, wu_id, evt_id])

        if result.new_facts:
            result.confidence = 0.85
            graph.save()

        return result

    # ── Rule 4: Delivery → Location ─────────────────────────────────────

    def _rule_delivery_to_location(self, graph) -> InferenceResult:
        """
        IF MaterialBatch имеет location_id
           AND MaterialBatch → [USED_IN] → WorkUnit
           AND WorkUnit.location_id IS NULL
        THEN
           INFER WorkUnit.location_id = MaterialBatch.location_id
           confidence = 0.7
        """
        result = InferenceResult(
            rule_name="delivery_to_location",
            description="Поставка на площадку → локация работ",
        )

        from src.core.evidence_graph import EdgeType

        # Правило срабатывает, когда у MaterialBatch есть location_id
        # (например, из ТТН с адресом доставки). Если location_id отсутствует —
        # правило не даёт новых фактов, но это ожидаемое поведение.

        # Ищем WorkUnit без локации, но с материалами
        for wu_id, wu_data in graph.graph.nodes(data=True):
            if wu_data.get("node_type") != "WorkUnit":
                continue
            if wu_data.get("location_id"):
                continue  # Уже есть

            # Есть ли поставки с локацией?
            for pred_id in graph.graph.predecessors(wu_id):
                pred_data = graph.graph.nodes[pred_id]
                if pred_data.get("node_type") != "MaterialBatch":
                    continue
                if not pred_data.get("location_id"):
                    continue

                edge = graph.graph.edges[pred_id, wu_id]
                if edge.get("edge_type") != EdgeType.USED_IN.value:
                    continue

                loc_id = pred_data["location_id"]
                graph.graph.nodes[wu_id]["location_id"] = loc_id
                graph.link(wu_id, loc_id, EdgeType.LOCATED_AT, confidence=0.7)

                result.new_facts.append({
                    "type": "location_inferred",
                    "work_unit_id": wu_id,
                    "location_id": loc_id,
                    "confidence": 0.7,
                })
                result.evidence_nodes.extend([pred_id, wu_id, loc_id])

        if result.new_facts:
            result.confidence = 0.7
            graph.save()

        return result

    # ── Rule 5: Temporal Chain → Dates ──────────────────────────────────

    def _rule_temporal_chain(self, graph) -> InferenceResult:
        """
        IF WorkUnit_A → [TEMPORAL_BEFORE] → WorkUnit_B
           AND WorkUnit_A.end_date известен
           AND WorkUnit_B.start_date IS NULL
        THEN
           INFER WorkUnit_B.start_date = WorkUnit_A.end_date + 1 день
           confidence = WorkUnit_A.confidence * 0.85
        """
        result = InferenceResult(
            rule_name="temporal_chain",
            description="Технологическая цепочка → даты последующих работ",
        )

        from src.core.evidence_graph import EdgeType, WorkUnitStatus, FactSource

        for wu_a_id, wu_a_data in graph.graph.nodes(data=True):
            if wu_a_data.get("node_type") != "WorkUnit":
                continue

            end_str = wu_a_data.get("end_date")
            if not end_str:
                continue

            try:
                end_a = date.fromisoformat(end_str)
            except (ValueError, TypeError):
                continue

            conf_a = wu_a_data.get("confidence", 0.5)

            for wu_b_id in graph.graph.successors(wu_a_id):
                edge = graph.graph.edges[wu_a_id, wu_b_id]
                if edge.get("edge_type") != EdgeType.TEMPORAL_BEFORE.value:
                    continue

                wu_b_data = graph.graph.nodes[wu_b_id]
                if wu_b_data.get("start_date"):
                    continue  # Уже известна

                if wu_b_data.get("node_type") != "WorkUnit":
                    continue

                start_b = end_a + timedelta(days=1)
                chain_conf = min(conf_a * 0.85, 0.8)

                graph.graph.nodes[wu_b_id]["start_date"] = start_b.isoformat()
                graph.graph.nodes[wu_b_id]["confidence"] = chain_conf
                if wu_b_data.get("status") not in (WorkUnitStatus.CONFIRMED.value,):
                    graph.graph.nodes[wu_b_id]["status"] = WorkUnitStatus.INFERRED.value
                    graph.graph.nodes[wu_b_id]["source"] = FactSource.INFERENCE.value

                result.new_facts.append({
                    "type": "temporal_chain_start",
                    "work_unit_id": wu_b_id,
                    "inferred_start": start_b.isoformat(),
                    "from_work_unit": wu_a_id,
                    "from_end_date": end_str,
                    "confidence": round(chain_conf, 2),
                })
                result.evidence_nodes.extend([wu_a_id, wu_b_id])

        if result.new_facts:
            result.confidence = min(
                0.8, sum(n["confidence"] for n in result.new_facts) / len(result.new_facts)
            )
            graph.save()

        return result

    # ── Rule 6: Confidence Boost ─────────────────────────────────────────

    def _rule_confidence_boost(self, graph) -> InferenceResult:
        """
        IF WorkUnit_A → [DERIVED_FROM] → WorkUnit_B
           AND WorkUnit_B.status = CONFIRMED
        THEN
           WorkUnit_A.confidence *= 1.2 (capped at 0.95)
        """
        result = InferenceResult(
            rule_name="confidence_boost",
            description="Подтверждение производного WorkUnit → повышение уверенности исходного",
        )

        from src.core.evidence_graph import EdgeType, WorkUnitStatus

        for wu_a_id, wu_a_data in graph.graph.nodes(data=True):
            if wu_a_data.get("node_type") != "WorkUnit":
                continue

            for wu_b_id in graph.graph.successors(wu_a_id):
                edge = graph.graph.edges[wu_a_id, wu_b_id]
                if edge.get("edge_type") != EdgeType.DERIVED_FROM.value:
                    continue

                wu_b_data = graph.graph.nodes[wu_b_id]
                if wu_b_data.get("status") != WorkUnitStatus.CONFIRMED.value:
                    continue

                old_conf = wu_a_data.get("confidence", 0.5)
                new_conf = min(old_conf * 1.2, 0.95)
                if new_conf > old_conf:
                    graph.graph.nodes[wu_a_id]["confidence"] = new_conf
                    result.new_facts.append({
                        "type": "confidence_boost",
                        "work_unit_id": wu_a_id,
                        "old_confidence": round(old_conf, 2),
                        "new_confidence": round(new_conf, 2),
                        "boosted_by": wu_b_id,
                    })
                    result.evidence_nodes.append(wu_a_id)

        if result.new_facts:
            result.confidence = 0.7
            graph.save()

        return result


# Модульный синглтон
inference_engine = InferenceEngine()
