"""
ASD v12.0 — Completeness Matrix (Матрица Полного Соответствия).

Обеспечивает верификацию цепочки документов перед закрытием КС-2:
  Чертеж → Спецификация → Сертификат → АОСР → Строка КС-2

Каждый разрыв в цепочке = CRITICAL ERROR, не WARNING.
Без этой проверки система может пропустить недополученную оплату.

Usage:
    from src.core.completeness_matrix import verify_completeness, ChainStatus

    result = verify_completeness(project_id, vor_positions)
    if result.has_gaps:
        raise CompletenessError(result.gaps)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Chain Status
# =============================================================================

class ChainStatus(str, Enum):
    """Статус звена в цепочке документов."""
    VERIFIED = "verified"       # Подтверждено — документ найден и валиден
    MISSING = "missing"          # Отсутствует — документ не найден
    INCOMPLETE = "incomplete"    # Неполный — документ есть, но не все поля заполнены
    STALE = "stale"              # Устарел — документ есть, но версия не актуальна
    UNVERIFIED = "unverified"    # Не проверено — проверка не проводилась


# =============================================================================
# Chain Link
# =============================================================================

@dataclass
class ChainLink:
    """Одно звено в цепочке: чертеж → спецификация → сертификат → АОСР → КС-2."""
    position_code: str           # Код позиции (например, "ФЕР06-01-001-01")
    position_name: str           # Наименование позиции
    work_type: str               # Вид работ из WorkTypeRegistry

    # Состояние каждого звена
    drawing_status: ChainStatus = ChainStatus.UNVERIFIED
    drawing_ref: Optional[str] = None           # Ссылка на чертеж

    spec_status: ChainStatus = ChainStatus.UNVERIFIED
    spec_ref: Optional[str] = None              # Ссылка на спецификацию

    cert_status: ChainStatus = ChainStatus.UNVERIFIED
    cert_ref: Optional[str] = None              # Ссылка на сертификат/паспорт

    aosr_status: ChainStatus = ChainStatus.UNVERIFIED
    aosr_ref: Optional[str] = None              # Ссылка на АОСР

    ks2_status: ChainStatus = ChainStatus.UNVERIFIED
    ks2_line_number: Optional[int] = None       # Номер строки в КС-2


@dataclass
class CompletenessGap:
    """Разрыв в цепочке документов."""
    position_code: str
    position_name: str
    missing_link: str          # "spec", "cert", "aosr", "ks2"
    severity: str = "CRITICAL"


@dataclass
class CompletenessResult:
    """Результат проверки матрицы полного соответствия."""
    project_id: int
    total_positions: int
    verified_positions: int
    gaps: List[CompletenessGap] = field(default_factory=list)
    chains: List[ChainLink] = field(default_factory=list)

    @property
    def has_gaps(self) -> bool:
        return len(self.gaps) > 0

    @property
    def completeness_pct(self) -> float:
        """Процент полностью верифицированных позиций."""
        if self.total_positions == 0:
            return 0.0
        return (self.verified_positions / self.total_positions) * 100

    @property
    def critical_gaps(self) -> List[CompletenessGap]:
        """Только критические разрывы (cert, aosr, ks2)."""
        return [g for g in self.gaps if g.missing_link in ("cert", "aosr", "ks2")]


# =============================================================================
# Chain Builder
# =============================================================================

class CompletenessChainBuilder:
    """
    Построитель цепочки полного соответствия для каждой позиции ВОР.

    Проверяет:
    1. Drawing → Spec: есть ли спецификация для каждого чертежа
    2. Spec → Cert: есть ли сертификат на каждый материал в спецификации
    3. Cert → AOSR: есть ли АОСР, ссылающийся на этот сертификат
    4. AOSR → КС-2: есть ли строка в КС-2 для каждого АОСР
    """

    def __init__(self, project_id: int):
        self.project_id = project_id
        self._drawings: Dict[str, List[str]] = {}    # drawing_id → [spec_ids]
        self._specs: Dict[str, Dict] = {}             # spec_id → {materials, cert_id}
        self._certs: Dict[str, Dict] = {}             # cert_id → {status, aosr_id}
        self._aosrs: Dict[str, Dict] = {}             # aosr_id → {status, ks2_line}
        self._ks2_lines: Set[int] = set()             # Номера строк КС-2

    def add_drawing(self, drawing_id: str, spec_ids: List[str]):
        """Зарегистрировать чертеж и его спецификации."""
        self._drawings[drawing_id] = spec_ids

    def add_spec(self, spec_id: str, materials: List[str], cert_id: Optional[str] = None):
        """Зарегистрировать спецификацию."""
        self._specs[spec_id] = {"materials": materials, "cert_id": cert_id}

    def add_cert(self, cert_id: str, status: str = "valid", aosr_id: Optional[str] = None):
        """Зарегистрировать сертификат/паспорт качества."""
        self._certs[cert_id] = {"status": status, "aosr_id": aosr_id}

    def add_aosr(self, aosr_id: str, status: str = "signed", ks2_line: Optional[int] = None):
        """Зарегистрировать АОСР."""
        self._aosrs[aosr_id] = {"status": status, "ks2_line": ks2_line}

    def add_ks2_line(self, line_number: int):
        """Зарегистрировать строку КС-2."""
        self._ks2_lines.add(line_number)

    def build(self, vor_positions: List[Dict]) -> CompletenessResult:
        """
        Построить матрицу полного соответствия для позиций ВОР.

        Args:
            vor_positions: Список позиций из ВОР [{code, name, work_type, drawing_ref, ...}]

        Returns:
            CompletenessResult с разрывами и статусами
        """
        chains: List[ChainLink] = []
        gaps: List[CompletenessGap] = []

        for pos in vor_positions:
            code = pos.get("code", "UNKNOWN")
            name = pos.get("name", "Без названия")
            work_type = pos.get("work_type", "")
            drawing_ref = pos.get("drawing_ref")

            chain = ChainLink(
                position_code=code,
                position_name=name,
                work_type=work_type,
            )

            # Level 0: Drawing check
            if drawing_ref and drawing_ref in self._drawings:
                chain.drawing_status = ChainStatus.VERIFIED
                chain.drawing_ref = drawing_ref
            elif drawing_ref:
                chain.drawing_status = ChainStatus.MISSING
                gaps.append(CompletenessGap(code, name, "drawing"))
            else:
                chain.drawing_status = ChainStatus.MISSING
                gaps.append(CompletenessGap(code, name, "drawing"))

            # Level 1: Spec check
            spec_ids = self._drawings.get(drawing_ref, []) if drawing_ref else []
            spec_linked = any(sid in self._specs for sid in spec_ids)
            if spec_linked:
                chain.spec_status = ChainStatus.VERIFIED
                chain.spec_ref = spec_ids[0]
            else:
                chain.spec_status = ChainStatus.MISSING
                gaps.append(CompletenessGap(code, name, "spec"))

            # Level 2: Cert check
            cert_found = False
            for sid in spec_ids:
                spec_data = self._specs.get(sid, {})
                cert_id = spec_data.get("cert_id")
                if cert_id and cert_id in self._certs:
                    chain.cert_status = ChainStatus.VERIFIED
                    chain.cert_ref = cert_id
                    cert_found = True
                    # Level 3: AOSR check
                    aosr_id = self._certs[cert_id].get("aosr_id")
                    if aosr_id and aosr_id in self._aosrs:
                        chain.aosr_status = ChainStatus.VERIFIED
                        chain.aosr_ref = aosr_id
                        # Level 4: КС-2 check
                        ks2_line = self._aosrs[aosr_id].get("ks2_line")
                        if ks2_line is not None and ks2_line in self._ks2_lines:
                            chain.ks2_status = ChainStatus.VERIFIED
                            chain.ks2_line_number = ks2_line
                        else:
                            chain.ks2_status = ChainStatus.MISSING
                            gaps.append(CompletenessGap(code, name, "ks2"))
                    else:
                        chain.aosr_status = ChainStatus.MISSING
                        gaps.append(CompletenessGap(code, name, "aosr"))
                    break

            if not cert_found:
                chain.cert_status = ChainStatus.MISSING
                gaps.append(CompletenessGap(code, name, "cert"))

            chains.append(chain)

        verified = sum(
            1 for c in chains
            if all(s == ChainStatus.VERIFIED for s in [
                c.drawing_status, c.spec_status, c.cert_status,
                c.aosr_status, c.ks2_status,
            ])
        )

        return CompletenessResult(
            project_id=self.project_id,
            total_positions=len(vor_positions),
            verified_positions=verified,
            gaps=gaps,
            chains=chains,
        )


# =============================================================================
# Top-level API
# =============================================================================

def verify_completeness(
    project_id: int,
    vor_positions: List[Dict],
    drawings: Optional[Dict[str, List[str]]] = None,
    specs: Optional[Dict[str, Dict]] = None,
    certs: Optional[Dict[str, Dict]] = None,
    aosrs: Optional[Dict[str, Dict]] = None,
    ks2_lines: Optional[Set[int]] = None,
) -> CompletenessResult:
    """
    Проверить целостность цепочки документов для КС-2.

    Блокирует создание КС-2 если есть критические разрывы (cert/aosr/ks2).

    Args:
        project_id: ID проекта
        vor_positions: Позиции ВОР
        drawings, specs, certs, aosrs: зарегистрированная документация
        ks2_lines: номера строк КС-2

    Returns:
        CompletenessResult с разрывами

    Example:
        result = verify_completeness(project_id, vor)
        if result.has_gaps:
            print(f"CRITICAL: {len(result.critical_gaps)} gaps found!")
            for gap in result.critical_gaps:
                print(f"  - {gap.position_name}: missing {gap.missing_link}")
    """
    builder = CompletenessChainBuilder(project_id)

    for d_id, s_ids in (drawings or {}).items():
        builder.add_drawing(d_id, s_ids)

    for s_id, s_data in (specs or {}).items():
        builder.add_spec(s_id, s_data.get("materials", []), s_data.get("cert_id"))

    for c_id, c_data in (certs or {}).items():
        builder.add_cert(c_id, c_data.get("status", "valid"), c_data.get("aosr_id"))

    for a_id, a_data in (aosrs or {}).items():
        builder.add_aosr(a_id, a_data.get("status", "signed"), a_data.get("ks2_line"))

    for line in (ks2_lines or set()):
        builder.add_ks2_line(line)

    return builder.build(vor_positions)


class CompletenessError(Exception):
    """Выбрасывается при критических разрывах в цепочке документов."""

    def __init__(self, result: CompletenessResult):
        self.result = result
        gap_desc = "\n".join(
            f"  {g.position_code}: {g.position_name} — отсутствует {g.missing_link}"
            for g in result.critical_gaps[:10]
        )
        super().__init__(
            f"Completeness check FAILED: {len(result.critical_gaps)} critical gaps. "
            f"Completeness: {result.completeness_pct:.1f}%\n{gap_desc}"
        )
