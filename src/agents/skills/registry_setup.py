"""
MAC_ASD v11.0 — Skill Registry Setup.

Инициализация реестра навыков. Регистрирует все доступные навыки
и предоставляет единый доступ к ним.
"""

import logging
from src.agents.skills.common.base import SkillRegistry
from src.agents.skills.pto.work_spec import PTO_WorkSpec
from src.agents.skills.delo.template_lib import DELO_TemplateLib
from src.agents.skills.legal.contract_risks import LegalContractRisks
from src.agents.skills.legal.id_composition import LegalIDComposition

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

    logger.info(f"Skill registry initialized: {len(registry.list_all())} skills")
    return registry
