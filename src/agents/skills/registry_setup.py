"""
MAC_ASD v11.3 — Skill Registry Setup.

Инициализация реестра навыков. Регистрирует все доступные навыки
и предоставляет единый доступ к ним.

Зарегистрированные навыки (7):
  PTO:     PTO_WorkSpec — специализация по видам работ
  DELO:    DELO_TemplateLib — библиотека шаблонов ИД
  LEGAL:   LegalContractRisks — типовые риски в договорах
  LEGAL:   LegalIDComposition — проверка состава ИД
  SMETA:   SmetaRateLookup — поиск расценок ФЕР/ГЭСН
  SMETA:   SmetaCalc — расчёт локальной сметы
  SMETA:   SmetaVorCompare — сверка ВОР со сметой
"""

import logging
from src.agents.skills.common.base import SkillRegistry
from src.agents.skills.pto.work_spec import PTO_WorkSpec
from src.agents.skills.delo.template_lib import DELO_TemplateLib
from src.agents.skills.legal.contract_risks import LegalContractRisks
from src.agents.skills.legal.id_composition import LegalIDComposition
from src.agents.skills.smeta.rate_lookup import SmetaRateLookup
from src.agents.skills.smeta.calc import SmetaCalc
from src.agents.skills.smeta.vor_compare import SmetaVorCompare

logger = logging.getLogger(__name__)


def create_skill_registry(llm_engine=None) -> SkillRegistry:
    """
    Создать и инициализировать реестр навыков.

    Args:
        llm_engine: Экземпляр LLMEngine (опционально)

    Returns:
        SkillRegistry со всеми зарегистрированными навыками
    """
    registry = SkillRegistry()

    # PTO Skills
    registry.register(PTO_WorkSpec(llm_engine=llm_engine))

    # Delo Skills
    registry.register(DELO_TemplateLib(llm_engine=llm_engine))

    # Legal Skills
    registry.register(LegalContractRisks(llm_engine=llm_engine))
    registry.register(LegalIDComposition(llm_engine=llm_engine))

    # Smeta Skills (Package 4)
    registry.register(SmetaRateLookup(llm_engine=llm_engine))
    registry.register(SmetaCalc(llm_engine=llm_engine))
    registry.register(SmetaVorCompare(llm_engine=llm_engine))

    logger.info(f"Skill registry initialized: {len(registry.list_all())} skills")
    return registry
