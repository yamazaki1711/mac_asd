"""
ASD v11.1 — Laboratory MCP Tools.

Полный цикл лабораторного контроля для строительства:
- НК сварных соединений (ВИК, МПК, УЗК, РК, Капиллярный)
- Испытания бетона (сжатие, изгиб, морозостойкость, водонепроницаемость)
- Входной контроль материалов

Документооборот:
  Обращение → Запрос КП → Выбор лаборатории → Договор →
  Отбор образцов → Доставка → Испытания → Акт → Заключение → Подшивка в ИД

Реестр инструментов (11 шт, по манифесту asd_manifest.yaml):
  ПТО (3): lab_control_plan_create, lab_sample_register, lab_report_review
  Закупщик (3): lab_organization_search, lab_quote_request, lab_quote_compare
  Логист (1): lab_sample_delivery
  Делопроизводитель (4): lab_request_letter_generate, lab_contract_register,
                          lab_act_register, lab_report_file

Architecture: MLX-only (Mac Studio M4 Max 128GB).
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from src.db.init_db import SessionLocal
from src.db.models import (
    LabOrganization,
    LabRequest,
    LabSample,
    LabContract,
    LabAct,
    LabReport,
    LabControlPlan,
    Document,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================

def _lab_org_to_dict(lab: LabOrganization) -> Dict[str, Any]:
    """Конвертирует LabOrganization в словарь для ответа MCP."""
    return {
        "id": lab.id,
        "name": lab.name,
        "inn": lab.inn,
        "accreditation_number": lab.accreditation_number,
        "accreditation_expiry": str(lab.accreditation_expiry) if lab.accreditation_expiry else None,
        "scope": lab.scope,
        "contact_info": lab.contact_info,
        "rating": lab.rating,
        "category": lab.category,
        "is_accredited": lab.is_accredited,
        "notes": lab.notes,
    }


def _lab_request_to_dict(req: LabRequest) -> Dict[str, Any]:
    """Конвертирует LabRequest в словарь для ответа MCP."""
    return {
        "id": req.id,
        "project_id": req.project_id,
        "lab_id": req.lab_id,
        "control_category": req.control_category,
        "control_method": req.control_method,
        "gost_standard": req.gost_standard,
        "object_description": req.object_description,
        "object_location": req.object_location,
        "quantity": req.quantity,
        "unit": req.unit,
        "deadline": str(req.deadline) if req.deadline else None,
        "urgency": req.urgency,
        "status": req.status,
        "request_number": req.request_number,
        "request_date": str(req.request_date) if req.request_date else None,
    }


def _lab_sample_to_dict(sample: LabSample) -> Dict[str, Any]:
    """Конвертирует LabSample в словарь для ответа MCP."""
    return {
        "id": sample.id,
        "request_id": sample.request_id,
        "project_id": sample.project_id,
        "sample_mark": sample.sample_mark,
        "sample_type": sample.sample_type,
        "concrete_class": sample.concrete_class,
        "concrete_grade": sample.concrete_grade,
        "dimensions": sample.dimensions,
        "weight": sample.weight,
        "manufacture_date": str(sample.manufacture_date) if sample.manufacture_date else None,
        "sampling_date": str(sample.sampling_date) if sample.sampling_date else None,
        "delivery_date": str(sample.delivery_date) if sample.delivery_date else None,
        "age_at_test_days": sample.age_at_test_days,
        "structure_element": sample.structure_element,
        "structure_location": sample.structure_location,
        "curing_conditions": sample.curing_conditions,
        "test_result": sample.test_result,
        "actual_strength": sample.actual_strength,
        "coefficient_variation": sample.coefficient_variation,
        "status": sample.status,
        "notes": sample.notes,
    }


def _lab_contract_to_dict(contract: LabContract) -> Dict[str, Any]:
    """Конвертирует LabContract в словарь для ответа MCP."""
    return {
        "id": contract.id,
        "request_id": contract.request_id,
        "lab_id": contract.lab_id,
        "project_id": contract.project_id,
        "contract_number": contract.contract_number,
        "contract_date": str(contract.contract_date) if contract.contract_date else None,
        "contract_value": contract.contract_value,
        "currency": contract.currency,
        "subject": contract.subject,
        "scope_json": contract.scope_json,
        "status": contract.status,
        "payment_status": contract.payment_status,
    }


def _lab_act_to_dict(act: LabAct) -> Dict[str, Any]:
    """Конвертирует LabAct в словарь для ответа MCP."""
    return {
        "id": act.id,
        "contract_id": act.contract_id,
        "project_id": act.project_id,
        "act_number": act.act_number,
        "act_date": str(act.act_date) if act.act_date else None,
        "act_value": act.act_value,
        "description": act.description,
        "work_scope_json": act.work_scope_json,
        "status": act.status,
        "signed_our_date": str(act.signed_our_date) if act.signed_our_date else None,
        "signed_lab_date": str(act.signed_lab_date) if act.signed_lab_date else None,
    }


def _lab_report_to_dict(report: LabReport) -> Dict[str, Any]:
    """Конвертирует LabReport в словарь для ответа MCP."""
    return {
        "id": report.id,
        "request_id": report.request_id,
        "contract_id": report.contract_id,
        "project_id": report.project_id,
        "report_number": report.report_number,
        "report_date": str(report.report_date) if report.report_date else None,
        "report_type": report.report_type,
        "overall_result": report.overall_result,
        "conclusion": report.conclusion,
        "defects_found": report.defects_found,
        "recommendations": report.recommendations,
        "normative_basis": report.normative_basis,
        "status": report.status,
        "reviewed_by": report.reviewed_by,
        "review_notes": report.review_notes,
    }


def _control_plan_to_dict(plan: LabControlPlan) -> Dict[str, Any]:
    """Конвертирует LabControlPlan в словарь для ответа MCP."""
    return {
        "id": plan.id,
        "project_id": plan.project_id,
        "plan_number": plan.plan_number,
        "plan_date": str(plan.plan_date) if plan.plan_date else None,
        "items": plan.items,
        "total_items": plan.total_items,
        "completed_items": plan.completed_items,
        "completion_pct": plan.completion_pct,
        "status": plan.status,
        "approved_by": plan.approved_by,
    }


# =============================================================================
# ПТО (3 инструмента)
# =============================================================================

async def asd_lab_control_plan_create(
    project_id: int,
    plan_number: str,
    items: List[Dict[str, Any]],
    approved_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Создание плана лабораторного контроля на объекте.

    ПТО формирует план на основе ПД (проектной документации) и ВОР.
    План определяет: ЧТО, СКОЛЬКО и КАК нужно испытать/проконтролировать.

    Args:
        project_id: ID проекта
        plan_number: Номер плана (например, "ПЛК-2024-001")
        items: Массив позиций контроля. Каждая позиция:
            {
                "work_type": "Монолитные работы",
                "control_type": "Бетон_сжатие",
                "gost": "ГОСТ 10180-2012",
                "volume": 50,
                "unit": "образец",
                "frequency": "Каждые 50 м3"
            }
        approved_by: Кто утвердил (ФИО, должность)
    """
    logger.info(f"asd_lab_control_plan_create: project={project_id}, plan={plan_number}")

    db = SessionLocal()
    try:
        plan = LabControlPlan(
            project_id=project_id,
            plan_number=plan_number,
            items=items,
            total_items=len(items),
            completed_items=0,
            completion_pct=0,
            status="approved" if approved_by else "draft",
            approved_by=approved_by,
            plan_date=datetime.now() if approved_by else None,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        return {
            "status": "success",
            "message": f"Plan {plan_number} created with {len(items)} items",
            "plan": _control_plan_to_dict(plan),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create control plan: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


async def asd_lab_sample_register(
    project_id: int,
    request_id: int,
    sample_mark: str,
    sample_type: str,
    concrete_class: Optional[str] = None,
    concrete_grade: Optional[str] = None,
    dimensions: Optional[str] = None,
    weight: Optional[str] = None,
    manufacture_date: Optional[str] = None,
    sampling_date: Optional[str] = None,
    structure_element: Optional[str] = None,
    structure_location: Optional[str] = None,
    curing_conditions: Optional[str] = None,
    age_at_test_days: Optional[int] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Регистрация отбора образцов для испытаний.

    Для бетона: образцы-кубы с маркировкой, классом, размерами.
    Для сварки: привязка к стыку/шву через object_description в LabRequest.

    Args:
        project_id: ID проекта
        request_id: ID заявки в лабораторию (LabRequest)
        sample_mark: Маркировка образца (например, "Б-1/25-01")
        sample_type: Тип образца: "Бетонный_куб", "Бетонный_цилиндр", "Бетонная_призма", "Проба_раствора", "Стальной_образец"
        concrete_class: Класс бетона: "В25", "В30", "В35"
        concrete_grade: Марка: "М300", "М400"
        dimensions: Размеры: "150x150x150 мм"
        weight: Масса: "8.2 кг"
        manufacture_date: Дата формования (ISO format)
        sampling_date: Дата отбора (ISO format)
        structure_element: Конструктивный элемент: "Фундамент Ф-1"
        structure_location: Место отбора: "Ось В/5, гор. +0.000"
        curing_conditions: Условия твердения: "Естественные", "ТВО", "Влажные"
        age_at_test_days: Возраст на момент испытания: 7, 14, 28
        notes: Примечания
    """
    logger.info(f"asd_lab_sample_register: mark={sample_mark}, request={request_id}")

    db = SessionLocal()
    try:
        # Проверяем что заявка существует
        request = db.get(LabRequest, request_id)
        if not request:
            return {"status": "error", "message": f"LabRequest {request_id} not found"}

        sample = LabSample(
            request_id=request_id,
            project_id=project_id,
            sample_mark=sample_mark,
            sample_type=sample_type,
            concrete_class=concrete_class,
            concrete_grade=concrete_grade,
            dimensions=dimensions,
            weight=weight,
            manufacture_date=datetime.fromisoformat(manufacture_date) if manufacture_date else None,
            sampling_date=datetime.fromisoformat(sampling_date) if sampling_date else None,
            structure_element=structure_element,
            structure_location=structure_location,
            curing_conditions=curing_conditions,
            age_at_test_days=age_at_test_days,
            status="manufactured",
            notes=notes,
        )
        db.add(sample)

        # Обновляем статус заявки
        request.status = "in_progress"
        db.commit()
        db.refresh(sample)

        return {
            "status": "success",
            "message": f"Sample {sample_mark} registered",
            "sample": _lab_sample_to_dict(sample),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to register sample: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


async def asd_lab_report_review(
    report_id: int,
    reviewed_by: str,
    review_notes: Optional[str] = None,
    accept: bool = True,
) -> Dict[str, Any]:
    """
    Проверка заключения лаборатории инженером ПТО.

    ПТО проверяет:
    - Соответствие результатов нормативным требованиям
    - Полноту заключения (все ли объекты проконтролированы)
    - Наличие дефектов и их критичность
    - Корректность ссылок на ГОСТ/СП

    Args:
        report_id: ID заключения (LabReport)
        reviewed_by: Кто проверил (ФИО, должность)
        review_notes: Заметки при проверке
        accept: Принять заключение (True) или вернуть на доработку (False)
    """
    logger.info(f"asd_lab_report_review: report={report_id}, accept={accept}")

    db = SessionLocal()
    try:
        report = db.get(LabReport, report_id)
        if not report:
            return {"status": "error", "message": f"LabReport {report_id} not found"}

        new_status = "accepted" if accept else "received"
        report.status = new_status
        report.reviewed_by = reviewed_by
        report.review_notes = review_notes

        # Если заключение принято — обновляем статус образцов
        if accept:
            # Обновляем все образцы, привязанные к заявке
            if report.request_id:
                samples = db.execute(
                    select(LabSample).where(
                        LabSample.request_id == report.request_id
                    )
                ).scalars().all()

                for sample in samples:
                    if sample.status == "tested":
                        sample.status = "reported"
                        # Переносим результат из заключения
                        if report.overall_result:
                            sample.test_result = report.overall_result

        db.commit()

        return {
            "status": "success",
            "message": f"Report {'accepted' if accept else 'returned for revision'}",
            "report": _lab_report_to_dict(report),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to review report: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


# =============================================================================
# Закупщик (3 инструмента)
# =============================================================================

async def asd_lab_organization_search(
    control_category: Optional[str] = None,
    control_method: Optional[str] = None,
    category: Optional[str] = None,
    min_rating: Optional[int] = None,
    accredited_only: bool = True,
) -> Dict[str, Any]:
    """
    Поиск аккредитованных лабораторий по критериям.

    Закупщик ищет лаборатории в реестре lab_organizations,
    фильтруя по области аккредитации, рейтингу, категории.

    Args:
        control_category: Вид контроля: "НК_сварка", "Бетон", "Входной_контроль"
        control_method: Метод контроля: "МПК", "УЗК", "ВИК", "РК", "Сжатие", "Отбор_образцов"
        category: Категория лаборатории: "НК", "Бетон", "Общая"
        min_rating: Минимальный рейтинг (1-5)
        accredited_only: Только с действующей аккредитацией
    """
    logger.info(
        f"asd_lab_organization_search: category={control_category}, "
        f"method={control_method}"
    )

    db = SessionLocal()
    try:
        query = select(LabOrganization)

        if accredited_only:
            query = query.where(LabOrganization.is_accredited == True)

        if category:
            query = query.where(LabOrganization.category == category)

        if min_rating:
            query = query.where(LabOrganization.rating >= min_rating)

        labs = db.execute(query).scalars().all()

        # Фильтрация по методу контроля (проверяем scope JSON)
        results = []
        for lab in labs:
            # Фильтр по методу контроля
            if control_method and lab.scope:
                method_found = any(
                    item.get("method") == control_method
                    for item in lab.scope
                )
                if not method_found:
                    continue

            # Фильтр по категории контроля
            if control_category:
                if control_category == "НК_сварка" and lab.category not in ["НК", "Общая"]:
                    continue
                elif control_category == "Бетон" and lab.category not in ["Бетон", "Общая"]:
                    continue
                elif control_category == "Входной_контроль" and lab.category != "Общая":
                    continue

            results.append(_lab_org_to_dict(lab))

        # Сортировка по рейтингу (по убыванию)
        results.sort(key=lambda x: x.get("rating", 0), reverse=True)

        return {
            "status": "success",
            "labs_found": len(results),
            "filter": {
                "control_category": control_category,
                "control_method": control_method,
                "category": category,
                "min_rating": min_rating,
                "accredited_only": accredited_only,
            },
            "labs": results,
        }
    except Exception as e:
        logger.error(f"Lab search failed: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


async def asd_lab_quote_request(
    lab_id: int,
    project_id: int,
    control_category: str,
    control_method: str,
    object_description: str,
    quantity: int,
    unit: str,
    gost_standard: Optional[str] = None,
    object_location: Optional[str] = None,
    deadline: Optional[str] = None,
    urgency: str = "normal",
) -> Dict[str, Any]:
    """
    Создание заявки в лабораторию (запрос КП).

    Закупщик формирует заявку с указанием:
    - Что нужно проконтролировать
    - Каким методом (ГОСТ)
    - Сколько объектов/образцов
    - Сроки

    Args:
        lab_id: ID лаборатории (LabOrganization)
        project_id: ID проекта
        control_category: "НК_сварка", "Бетон", "Входной_контроль"
        control_method: "МПК", "УЗК", "ВИК", "РК", "Сжатие", "Отбор_образцов"
        object_description: Описание: "Сварные стыки балки Б1", "Образцы бетона В25"
        quantity: Количество: стыков, образцов, точек
        unit: Единица: "стык", "образец", "точка", "м3"
        gost_standard: ГОСТ метода: "ГОСТ 21105-87", "ГОСТ 14782-86"
        object_location: Место: "Ось А/10-12, отм. +5.200"
        deadline: Желаемый срок (ISO format)
        urgency: "normal", "urgent", "critical"
    """
    logger.info(
        f"asd_lab_quote_request: lab={lab_id}, method={control_method}, "
        f"qty={quantity} {unit}"
    )

    db = SessionLocal()
    try:
        # Проверяем что лаборатория существует
        lab = db.get(LabOrganization, lab_id)
        if not lab:
            return {"status": "error", "message": f"LabOrganization {lab_id} not found"}

        # Проверяем что метод есть в области аккредитации
        if lab.scope:
            method_in_scope = any(
                item.get("method") == control_method
                for item in lab.scope
            )
            if not method_in_scope:
                return {
                    "status": "warning",
                    "message": (
                        f"Method '{control_method}' may not be in lab's scope. "
                        f"Available: {[s.get('method') for s in lab.scope]}"
                    ),
                }

        # Создаём заявку
        request = LabRequest(
            project_id=project_id,
            lab_id=lab_id,
            control_category=control_category,
            control_method=control_method,
            gost_standard=gost_standard,
            object_description=object_description,
            object_location=object_location,
            quantity=quantity,
            unit=unit,
            deadline=datetime.fromisoformat(deadline) if deadline else None,
            urgency=urgency,
            status="draft",
            request_date=datetime.now(),
        )
        db.add(request)
        db.commit()
        db.refresh(request)

        return {
            "status": "success",
            "message": (
                f"Request created for {lab.name}. "
                f"Next step: send letter and await КП."
            ),
            "request": _lab_request_to_dict(request),
            "lab": _lab_org_to_dict(lab),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create quote request: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


async def asd_lab_quote_compare(
    project_id: int,
    control_category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Сравнение коммерческих предложений от лабораторий.

    Закупщик сравнивает полученные КП по:
    - Цене (если уже есть договоры/оценки)
    - Срокам выполнения
    - Рейтингу лаборатории
    - Области аккредитации

    Args:
        project_id: ID проекта
        control_category: Фильтр по виду контроля (опционально)
    """
    logger.info(f"asd_lab_quote_compare: project={project_id}")

    db = SessionLocal()
    try:
        # Получаем все заявки по проекту
        query = select(LabRequest).where(LabRequest.project_id == project_id)
        if control_category:
            query = query.where(LabRequest.control_category == control_category)

        requests = db.execute(query).scalars().all()

        if not requests:
            return {
                "status": "info",
                "message": "No lab requests found for this project",
            }

        comparison = []
        for req in requests:
            lab = db.get(LabOrganization, req.lab_id)
            contract = db.execute(
                select(LabContract).where(LabContract.request_id == req.id)
            ).scalar_one_or_none()

            entry = {
                "request_id": req.id,
                "lab_id": req.lab_id,
                "lab_name": lab.name if lab else "Unknown",
                "lab_rating": lab.rating if lab else 0,
                "lab_category": lab.category if lab else "",
                "control_method": req.control_method,
                "quantity": req.quantity,
                "unit": req.unit,
                "urgency": req.urgency,
                "request_status": req.status,
                "contract_value": (
                    contract.contract_value if contract else None
                ),
                "contract_status": contract.status if contract else None,
            }
            comparison.append(entry)

        # Сортировка: приоритет — рейтинг лаборатории, затем цена
        comparison.sort(
            key=lambda x: (-x["lab_rating"], x["contract_value"] or float("inf"))
        )

        return {
            "status": "success",
            "project_id": project_id,
            "requests_found": len(comparison),
            "comparison": comparison,
            "recommendation": (
                f"Best option: {comparison[0]['lab_name']} "
                f"(rating: {comparison[0]['lab_rating']})"
                if comparison else "No data"
            ),
        }
    except Exception as e:
        logger.error(f"Quote comparison failed: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


# =============================================================================
# Логист (1 инструмент)
# =============================================================================

async def asd_lab_sample_delivery(
    request_id: int,
    delivery_type: str = "sample_transport",
    delivery_notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Координация доставки образцов / выезда дефектоскопистов.

    Логист организует:
    - Для бетона: доставку образцов-кубов в лабораторию
    - Для сварки (НК): выезд дефектоскопистов на объект

    Args:
        request_id: ID заявки (LabRequest)
        delivery_type: "sample_transport" (доставка образцов) или "specialist_dispatch" (выезд специалиста)
        delivery_notes: Примечания к доставке
    """
    logger.info(f"asd_lab_sample_delivery: request={request_id}, type={delivery_type}")

    db = SessionLocal()
    try:
        request = db.get(LabRequest, request_id)
        if not request:
            return {"status": "error", "message": f"LabRequest {request_id} not found"}

        # Обновляем статус образцов
        samples = db.execute(
            select(LabSample).where(LabSample.request_id == request_id)
        ).scalars().all()

        delivery_date = datetime.now()
        for sample in samples:
            if sample.status == "sampled":
                sample.status = "delivered"
                sample.delivery_date = delivery_date
            elif sample.status == "manufactured":
                sample.status = "sampled"
                sample.sampling_date = delivery_date
                sample.status = "delivered"
                sample.delivery_date = delivery_date

        # Обновляем статус заявки
        request.status = "in_progress"

        db.commit()

        lab = db.get(LabOrganization, request.lab_id)

        return {
            "status": "success",
            "message": (
                f"{'Samples delivered to lab' if delivery_type == 'sample_transport' else 'Specialists dispatched to site'}"
            ),
            "request": _lab_request_to_dict(request),
            "lab": _lab_org_to_dict(lab) if lab else None,
            "samples_delivered": len(samples),
            "delivery_type": delivery_type,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Delivery coordination failed: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


# =============================================================================
# Делопроизводитель (4 инструмента)
# =============================================================================

async def asd_lab_request_letter_generate(
    request_id: int,
    recipient_position: Optional[str] = None,
    signatory_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Генерация письма-обращения в лабораторию.

    Делопроизводитель формирует официальное письмо-обращение
    на основе данных заявки (LabRequest).

    Args:
        request_id: ID заявки (LabRequest)
        recipient_position: Должность получателя (для шапки письма)
        signatory_name: ФИО подписанта с нашей стороны
    """
    logger.info(f"asd_lab_request_letter_generate: request={request_id}")

    db = SessionLocal()
    try:
        request = db.get(LabRequest, request_id)
        if not request:
            return {"status": "error", "message": f"LabRequest {request_id} not found"}

        lab = db.get(LabOrganization, request.lab_id)
        if not lab:
            return {"status": "error", "message": f"Lab organization not found"}

        # Генерация текста письма
        letter_text = _generate_request_letter(request, lab, recipient_position, signatory_name)

        # Обновляем статус заявки
        request.status = "sent"
        request.request_date = datetime.now()
        db.commit()

        return {
            "status": "success",
            "message": "Request letter generated",
            "request_id": request_id,
            "letter_text": letter_text,
            "lab_name": lab.name,
            "lab_contact": lab.contact_info,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Letter generation failed: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def _generate_request_letter(
    request: LabRequest,
    lab: LabOrganization,
    recipient_position: Optional[str] = None,
    signatory_name: Optional[str] = None,
) -> str:
    """Генерирует текст письма-обращения в лабораторию."""
    contact = lab.contact_info or {}
    representative = contact.get("representative", "Руководителю лаборатории")

    # Метод контроля — название для письма
    method_names = {
        "ВИК": "визуально-измерительный контроль (ВИК)",
        "МПК": "магнито-порошковый контроль (МПК)",
        "УЗК": "ультразвуковой контроль (УЗК)",
        "РК": "радиографический контроль (РК)",
        "Капиллярный": "капиллярный неразрушающий контроль",
        "Сжатие": "испытание образцов бетона на сжатие",
        "Изгиб": "испытание образцов бетона на изгиб",
        "Морозостойкость": "определение морозостойкости бетона",
        "Водонепроницаемость": "определение водонепроницаемости бетона",
        "Отбор_образцов": "отбор образцов бетона для испытаний",
        "Входной контроль": "входной контроль строительных материалов",
    }
    method_name = method_names.get(request.control_method, request.control_method)

    category_names = {
        "НК_сварка": "неразрушающего контроля сварных соединений",
        "Бетон": "испытаний бетона",
        "Входной_контроль": "входного контроля материалов",
    }
    category_name = category_names.get(
        request.control_category, request.control_category
    )

    gost_text = f" в соответствии с {request.gost_standard}" if request.gost_standard else ""
    deadline_text = (
        f" Срок выполнения: до {request.deadline.strftime('%d.%m.%Y')}."
        if request.deadline else ""
    )
    urgency_text = ""
    if request.urgency == "urgent":
        urgency_text = "\n\nПросим рассмотреть заявку в приоритетном порядке (срочная)."
    elif request.urgency == "critical":
        urgency_text = "\n\n!!! СРОЧНАЯ ЗАЯВКА — работы на критическом пути !!!"

    letter = f"""Руководителю {lab.name}
{representative}

Уважаемый(ая) {representative.split()[0] if representative else 'Руководитель'}!

Просим Вас провести {method_name}{gost_text} в рамках {category_name}.

Объект контроля: {request.object_description or 'не указан'}
Место на объекте: {request.object_location or 'не указано'}
Количество: {request.quantity} {request.unit}
{deadline_text}{urgency_text}

Просим направить коммерческое предложение на оказание указанных услуг
по электронной почте или телефону, указанным в наших реквизитах.

С уважением,
{signatory_name or '[ФИО подписанта]'}
{recipient_position or '[Должность]'}"""

    return letter


async def asd_lab_contract_register(
    request_id: int,
    lab_id: int,
    project_id: int,
    contract_number: str,
    contract_date: str,
    contract_value: int,
    subject: str,
    scope_json: Optional[List[Dict[str, Any]]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Регистрация договора с лабораторией.

    Делопроизводитель регистрирует подписанный договор на оказание
    услуг лаборатории после проверки Юристом.

    Args:
        request_id: ID заявки (LabRequest)
        lab_id: ID лаборатории (LabOrganization)
        project_id: ID проекта
        contract_number: Номер договора
        contract_date: Дата заключения (ISO format)
        contract_value: Сумма договора (в копейках)
        subject: Описание предмета: "Проведение УЗК сварных стыков..."
        scope_json: Структурированный объём: [{"method": "УЗК", "count": 50, "unit": "стык", "price": 1500}]
        start_date: Начало оказания услуг (ISO format)
        end_date: Окончание оказания услуг (ISO format)
    """
    logger.info(f"asd_lab_contract_register: contract={contract_number}")

    db = SessionLocal()
    try:
        request = db.get(LabRequest, request_id)
        if not request:
            return {"status": "error", "message": f"LabRequest {request_id} not found"}

        contract = LabContract(
            request_id=request_id,
            lab_id=lab_id,
            project_id=project_id,
            contract_number=contract_number,
            contract_date=datetime.fromisoformat(contract_date),
            contract_value=contract_value,
            subject=subject,
            scope_json=scope_json,
            start_date=datetime.fromisoformat(start_date) if start_date else None,
            end_date=datetime.fromisoformat(end_date) if end_date else None,
            status="signed",
            payment_status="unpaid",
        )
        db.add(contract)

        # Обновляем статус заявки
        request.status = "contracted"

        db.commit()
        db.refresh(contract)

        return {
            "status": "success",
            "message": f"Contract {contract_number} registered",
            "contract": _lab_contract_to_dict(contract),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Contract registration failed: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


async def asd_lab_act_register(
    contract_id: int,
    project_id: int,
    act_number: str,
    act_date: str,
    act_value: int,
    description: str,
    work_scope_json: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Регистрация акта выполненных работ лаборатории.

    Делопроизводитель регистрирует акт после получения от лаборатории.

    Args:
        contract_id: ID договора (LabContract)
        project_id: ID проекта
        act_number: Номер акта
        act_date: Дата акта (ISO format)
        act_value: Сумма по акту (в копейках)
        description: Описание выполненных работ
        work_scope_json: [{"method": "УЗК", "planned": 50, "actual": 48, "accepted": 47, "rejected": 1}]
    """
    logger.info(f"asd_lab_act_register: act={act_number}")

    db = SessionLocal()
    try:
        contract = db.get(LabContract, contract_id)
        if not contract:
            return {"status": "error", "message": f"LabContract {contract_id} not found"}

        act = LabAct(
            contract_id=contract_id,
            project_id=project_id,
            act_number=act_number,
            act_date=datetime.fromisoformat(act_date),
            act_value=act_value,
            description=description,
            work_scope_json=work_scope_json,
            status="draft",
        )
        db.add(act)

        # Обновляем статус договора
        contract.status = "completed"

        # Обновляем статус заявки
        if contract.request_id:
            request = db.get(LabRequest, contract.request_id)
            if request:
                request.status = "completed"

        db.commit()
        db.refresh(act)

        return {
            "status": "success",
            "message": f"Act {act_number} registered",
            "act": _lab_act_to_dict(act),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Act registration failed: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


async def asd_lab_report_file(
    report_id: int,
    filing_notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Подшивка заключения лаборатории в дело (ИД).

    Делопроизводитель подшивает проверенное заключение
    в комплект исполнительной документации проекта.

    После подшивки заключение считается частью ИД.

    Args:
        report_id: ID заключения (LabReport)
        filing_notes: Примечания к подшивке
    """
    logger.info(f"asd_lab_report_file: report={report_id}")

    db = SessionLocal()
    try:
        report = db.get(LabReport, report_id)
        if not report:
            return {"status": "error", "message": f"LabReport {report_id} not found"}

        if report.status != "accepted":
            return {
                "status": "error",
                "message": (
                    f"Report must be reviewed and accepted before filing. "
                    f"Current status: {report.status}"
                ),
            }

        report.status = "filed"
        db.commit()

        # Обновляем прогресс плана контроля
        if report.request_id:
            request = db.get(LabRequest, report.request_id)
            if request and request.project_id:
                # Ищем план контроля для проекта
                plan = db.execute(
                    select(LabControlPlan).where(
                        LabControlPlan.project_id == request.project_id,
                        LabControlPlan.status.in_(["approved", "in_progress"]),
                    )
                ).scalar_one_or_none()

                if plan:
                    plan.completed_items = (plan.completed_items or 0) + 1
                    if plan.total_items and plan.total_items > 0:
                        plan.completion_pct = int(
                            (plan.completed_items / plan.total_items) * 100
                        )
                    if plan.completion_pct >= 100:
                        plan.status = "completed"
                    db.commit()

        return {
            "status": "success",
            "message": f"Report {report.report_number} filed to project documentation",
            "report": _lab_report_to_dict(report),
            "filing_notes": filing_notes,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Report filing failed: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


# =============================================================================
# Вспомогательные инструменты (не в манифесте, но полезны)
# =============================================================================

async def asd_lab_register_report(
    request_id: int,
    contract_id: int,
    project_id: int,
    report_number: str,
    report_date: str,
    report_type: str,
    overall_result: str,
    conclusion: str,
    defects_found: Optional[List[Dict[str, Any]]] = None,
    recommendations: Optional[str] = None,
    normative_basis: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Регистрация заключения лаборатории (поступившего от лаборатории).

    Вызывается когда лаборатория прислала заключение/протокол.
    Статус: "received" — ожидает проверки ПТО.

    Args:
        request_id: ID заявки (LabRequest)
        contract_id: ID договора (LabContract)
        project_id: ID проекта
        report_number: Номер заключения
        report_date: Дата заключения (ISO format)
        report_type: "Заключение_НК", "Протокол_бетон", "Протокол_входной"
        overall_result: "Соответствует", "Не_соответствует", "Частично_соответствует"
        conclusion: Текстовое заключение лаборатории
        defects_found: [{"type": "трещина", "location": "шов №15", "severity": "критический"}]
        recommendations: Рекомендации лаборатории
        normative_basis: [{"doc": "ГОСТ 21105-87", "clause": "4.3"}]
    """
    logger.info(f"asd_lab_register_report: number={report_number}")

    db = SessionLocal()
    try:
        report = LabReport(
            request_id=request_id,
            contract_id=contract_id,
            project_id=project_id,
            report_number=report_number,
            report_date=datetime.fromisoformat(report_date),
            report_type=report_type,
            overall_result=overall_result,
            conclusion=conclusion,
            defects_found=defects_found or [],
            recommendations=recommendations,
            normative_basis=normative_basis or [],
            status="received",
        )
        db.add(report)

        # Обновляем статус заявки
        request = db.get(LabRequest, request_id)
        if request:
            request.status = "report_received"

        db.commit()
        db.refresh(report)

        return {
            "status": "success",
            "message": (
                f"Report {report_number} registered. "
                f"Awaiting PTO review."
            ),
            "report": _lab_report_to_dict(report),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Report registration failed: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


async def asd_lab_request_update_status(
    request_id: int,
    new_status: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Обновление статуса заявки лаборатории.

    Допустимые статусы:
    draft → sent → kp_received → contracted → in_progress → completed → report_received

    Args:
        request_id: ID заявки
        new_status: Новый статус
        notes: Примечания к изменению статуса
    """
    logger.info(f"asd_lab_request_update_status: {request_id} → {new_status}")

    valid_statuses = [
        "draft", "sent", "kp_received", "contracted",
        "in_progress", "completed", "report_received",
    ]
    if new_status not in valid_statuses:
        return {
            "status": "error",
            "message": f"Invalid status '{new_status}'. Valid: {valid_statuses}",
        }

    db = SessionLocal()
    try:
        request = db.get(LabRequest, request_id)
        if not request:
            return {"status": "error", "message": f"LabRequest {request_id} not found"}

        request.status = new_status
        db.commit()

        return {
            "status": "success",
            "message": f"Request status updated to '{new_status}'",
            "request": _lab_request_to_dict(request),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Status update failed: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
