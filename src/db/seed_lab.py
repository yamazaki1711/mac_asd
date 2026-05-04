"""
ASD v12.0.0 — Seed Lab Organizations.

Заполняет реестр аккредитованных лабораторий начальными данными.
Лаборатории НК (неразрушающий контроль) и испытательные центры бетона.
"""

import logging
from src.db.init_db import Session
from src.db.models import LabOrganization

logger = logging.getLogger(__name__)


# Типовые аккредитованные лаборатории для строительного контроля
SEED_LABS = [
    {
        "name": "СтройКонтроль-НК",
        "inn": "7700000001",
        "accreditation_number": "РОСС RU.0001.21НК01",
        "category": "НК",
        "scope": [
            {"method": "ВИК", "gost": "ГОСТ 3242-79", "description": "Визуально-измерительный контроль сварных соединений"},
            {"method": "МПК", "gost": "ГОСТ 21105-87", "description": "Магнито-порошковый контроль"},
            {"method": "УЗК", "gost": "ГОСТ Р 55724-2013", "description": "Ультразвуковой контроль сварных соединений"},
            {"method": "РК", "gost": "ГОСТ 7512-82", "description": "Радиографический контроль сварных соединений"},
            {"method": "Капиллярный", "gost": "ГОСТ 18442-80", "description": "Капиллярный неразрушающий контроль"},
        ],
        "contact_info": {
            "email": "nk@stroycontrol.ru",
            "phone": "+7 (495) 000-00-01",
            "representative": "Петров А.В.",
            "address": "г. Москва, ул. Промышленная, д. 15"
        },
        "rating": 5,
        "is_accredited": True,
        "notes": "Основной партнёр по НК сварных соединений. Быстрая реакция на срочные заявки."
    },
    {
        "name": "Испытательный Центр БетонЛаб",
        "inn": "7700000002",
        "accreditation_number": "РОСС RU.0001.21ИЦ02",
        "category": "Бетон",
        "scope": [
            {"method": "Сжатие", "gost": "ГОСТ 10180-2012", "description": "Определение прочности бетона на сжатие"},
            {"method": "Изгиб", "gost": "ГОСТ 10180-2012", "description": "Определение прочности бетона на изгиб"},
            {"method": "Морозостойкость", "gost": "ГОСТ 10060-2012", "description": "Определение морозостойкости бетона"},
            {"method": "Водонепроницаемость", "gost": "ГОСТ 12730.5-2018", "description": "Определение водонепроницаемости бетона"},
            {"method": "Средняя плотность", "gost": "ГОСТ 12730.1-2020", "description": "Определение средней плотности бетона"},
        ],
        "contact_info": {
            "email": "lab@betonlab.ru",
            "phone": "+7 (495) 000-00-02",
            "representative": "Сидорова Е.Н.",
            "address": "г. Москва, ул. Лабораторная, д. 8"
        },
        "rating": 4,
        "is_accredited": True,
        "notes": "Полный цикл испытаний бетона. Принимают образцы-кубы 150×150×150 и 100×100×100."
    },
    {
        "name": "СтройЭкспертиза-Комплекс",
        "inn": "7700000003",
        "accreditation_number": "РОСС RU.0001.21ИЦ03",
        "category": "Общая",
        "scope": [
            {"method": "ВИК", "gost": "ГОСТ 3242-79", "description": "Визуально-измерительный контроль"},
            {"method": "УЗК", "gost": "ГОСТ Р 55724-2013", "description": "Ультразвуковой контроль"},
            {"method": "МПК", "gost": "ГОСТ 21105-87", "description": "Магнито-порошковый контроль"},
            {"method": "Сжатие", "gost": "ГОСТ 10180-2012", "description": "Прочность бетона на сжатие"},
            {"method": "Входной контроль", "gost": "СП 73.13330.2016", "description": "Входной контроль строительных материалов"},
        ],
        "contact_info": {
            "email": "info@stroyexpertiza.ru",
            "phone": "+7 (495) 000-00-03",
            "representative": "Козлов Д.А.",
            "address": "г. Москва, ш. Энтузиастов, д. 22"
        },
        "rating": 4,
        "is_accredited": True,
        "notes": "Комплексная лаборатория — НК + бетон + входной контроль. Удобно одним договором."
    },
    {
        "name": "Диагностик-НК",
        "inn": "7700000004",
        "accreditation_number": "РОСС RU.0001.21НК04",
        "category": "НК",
        "scope": [
            {"method": "УЗК", "gost": "ГОСТ Р 55724-2013", "description": "Ультразвуковой контроль"},
            {"method": "РК", "gost": "ГОСТ 7512-82", "description": "Радиографический контроль"},
            {"method": "ВИК", "gost": "ГОСТ 3242-79", "description": "Визуально-измерительный контроль"},
            {"method": "Тепловой контроль", "gost": "ГОСТ Р 54852-2011", "description": "Тепловой неразрушающий контроль"},
        ],
        "contact_info": {
            "email": "order@diagnostik-nk.ru",
            "phone": "+7 (495) 000-00-04",
            "representative": "Иванов М.С.",
            "address": "г. Москва, ул. Электродная, д. 5"
        },
        "rating": 3,
        "is_accredited": True,
        "notes": "Специализация на радиографическом контроле. Дороже, но заключения принимаются без вопросов."
    },
]


def seed_lab_organizations():
    """Заполняет реестр лабораторий начальными данными."""
    logger.info("Seeding lab organizations...")

    with Session() as session:
        existing_count = session.query(LabOrganization).count()
        if existing_count > 0:
            logger.info(f"Lab organizations already seeded ({existing_count} found). Skipping.")
            return

        for lab_data in SEED_LABS:
            lab = LabOrganization(**lab_data)
            session.add(lab)

        session.commit()
        logger.info(f"Seeded {len(SEED_LABS)} lab organizations successfully.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_lab_organizations()
