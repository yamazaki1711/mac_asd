"""
ASD v12.0 — Synthetic Document Generator.

Генерирует реалистичные строительные документы с артефактами для обучения
и тестирования VLM-классификатора. Вдохновлено подходом АФИДЫ (Газпром ЦПС):
синтетические документы с кофейными пятнами, сгибами, следами ботинок,
«замыливанием» текста и мятой бумагой.

Генерируемые типы документов:
  - АОСР (акт освидетельствования скрытых работ)
  - Сертификат качества
  - КС-2 (акт о приёмке выполненных работ)
  - Исполнительная схема
  - Журнал работ

Артефакты:
  - coffee_stain: кофейное пятно (кольцо от кружки)
  - fold_lines: линии сгиба (вертикальные/горизонтальные)
  - boot_print: след ботинка
  - blur: замыливание текста (как от плохого принтера)
  - crumpled_paper: фон мятой бумаги
  - handwriting: рукописные пометки
  - scan_noise: шум сканирования
  - stamp_overlay: наложение печати
  - low_resolution: пониженное разрешение

Использование:
    # Сгенерировать 50 документов всех типов
    PYTHONPATH=. python scripts/generate_synthetic_docs.py \
        --count 50 --output-dir data/synthetic_docs

    # Только АОСР с пятнами и сгибами
    PYTHONPATH=. python scripts/generate_synthetic_docs.py \
        --count 20 --types aosr --artifacts coffee_stain,fold_lines \
        --output-dir data/synthetic_docs

    # Пакетная генерация для обучения VLM
    PYTHONPATH=. python scripts/generate_synthetic_docs.py \
        --count 200 --all-types --all-artifacts \
        --output-dir data/synthetic_docs/training
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Проверка PIL
try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

# =============================================================================
# Константы
# =============================================================================

A4_WIDTH = 2480  # 210mm @ 300 DPI
A4_HEIGHT = 3508  # 297mm @ 300 DPI

# Строительная лексика для генерации текста
CONSTRUCTION_WORDS = {
    "работы": [
        "земляные работы", "бетонные работы", "свайные работы",
        "монтаж металлоконструкций", "кровельные работы",
        "отделочные работы", "электромонтажные работы",
        "сантехнические работы", "погружение шпунта",
        "разработка котлована", "обратная засыпка",
        "устройство фундамента", "монтаж опалубки",
        "армирование", "гидроизоляция",
    ],
    "материалы": [
        "бетон B25 F200 W6", "арматура А500С Ø12 мм",
        "шпунт Ларсена Л5-УМ", "профнастил Н75-750-0.8",
        "труба 530х8 ст.20", "кабель ВВГнг-LS 5х2.5",
        "кирпич М150", "цемент М500", "песок строительный",
        "щебень фракции 20-40", "битумная мастика",
    ],
    "организации": [
        "ООО «СтройИнвест»", "АО «МонолитСтрой»", "ООО «КСК-1»",
        "ООО «РОТЕК»", "АО «ГлавСтрой»", "ООО «ТехноСтрой»",
        "ООО «ИнжСтройПроект»", "АО «СтройКомплект»",
    ],
    "объекты": [
        "Жилой комплекс «Солнечный»", "Торговый центр «Галактика»",
        "Бизнес-центр «Башня»", "Складской комплекс «Логистик»",
        "Школа на 1100 мест", "Детский сад на 250 мест",
        "Очистные сооружения ЛОС", "Котельная №5",
    ],
    "должности": [
        "Главный инженер проекта", "Начальник участка",
        "Производитель работ", "Инженер ПТО",
        "Инженер строительного контроля", "Главный сварщик",
    ],
    "фамилии": [
        "Иванов А.В.", "Петров С.М.", "Сидоров К.Н.",
        "Кузнецов Д.Л.", "Морозов Е.В.", "Волков А.П.",
        "Зайцев М.И.", "Смирнов О.Б.",
    ],
}

# =============================================================================
# Генерация текста документов
# =============================================================================


def _pick(items: List[str]) -> str:
    return random.choice(items)


def generate_aosr_text() -> str:
    """Сгенерировать текст акта освидетельствования скрытых работ."""
    work = _pick(CONSTRUCTION_WORDS["работы"])
    org = _pick(CONSTRUCTION_WORDS["организации"])
    obj = _pick(CONSTRUCTION_WORDS["объекты"])
    engineer = _pick(CONSTRUCTION_WORDS["фамилии"])
    date = (datetime.now() - timedelta(days=random.randint(30, 365))).strftime("%d.%m.%Y")

    return f"""АКТ
ОСВИДЕТЕЛЬСТВОВАНИЯ СКРЫТЫХ РАБОТ
№ {random.randint(1, 200)}-АОСР

Объект капитального строительства: {obj}

Представитель застройщика (технического заказчика): {engineer}, действующий на основании приказа №{random.randint(10, 99)} от {date}

Представитель лица, осуществляющего строительство: {_pick(CONSTRUCTION_WORDS["фамилии"])}, действующий на основании приказа №{random.randint(10, 99)} от {date}

произвели осмотр работ, выполненных {org},
и составили настоящий акт о нижеследующем:

1. К освидетельствованию предъявлены следующие работы: {work}

2. Работы выполнены по проектной документации: шифр ПД-{random.randint(100, 999)}-{random.choice(['КЖ', 'КМ', 'АР', 'ЭМ', 'ВК'])}

3. При выполнении работ применены:
   - {_pick(CONSTRUCTION_WORDS["материалы"])}
   - {_pick(CONSTRUCTION_WORDS["материалы"])}

4. При выполнении работ предъявлены документы, подтверждающие качество:
   - Сертификат соответствия №{random.randint(10000, 99999)} от {date}

5. Дата начала работ: {date}
6. Дата окончания работ: {(datetime.strptime(date, '%d.%m.%Y') + timedelta(days=random.randint(5, 30))).strftime('%d.%m.%Y')}

7. Разрешается производство последующих работ: {_pick(CONSTRUCTION_WORDS["работы"])}

Представитель застройщика: _________________ /{engineer}/
Представитель подрядчика: _________________ /{_pick(CONSTRUCTION_WORDS["фамилии"])}/
"""


def generate_certificate_text() -> str:
    """Сгенерировать текст сертификата качества."""
    material = _pick(CONSTRUCTION_WORDS["материалы"])
    org = _pick(CONSTRUCTION_WORDS["организации"])
    gost = random.choice([
        "ГОСТ 34028-2016", "ГОСТ 5781-82", "ГОСТ 7473-2010",
        "ГОСТ 27772-2015", "ГОСТ 19281-2014", "ГОСТ 31914-2012",
    ])
    date = (datetime.now() - timedelta(days=random.randint(30, 180))).strftime("%d.%m.%Y")

    return f"""СЕРТИФИКАТ КАЧЕСТВА № {random.randint(1000, 9999)}

Наименование продукции: {material}

Производитель: {org}
Дата изготовления: {date}
Номер партии: П{random.randint(100, 999)}-{random.randint(1, 12):02d}
Размер партии: {random.randint(5, 500)} {random.choice(['т', 'м³', 'шт', 'п.м.'])}

Продукция соответствует требованиям: {gost}

Химический состав (фактический):
- Углерод (C): {random.uniform(0.12, 0.45):.2f}%
- Марганец (Mn): {random.uniform(0.4, 1.2):.2f}%
- Кремний (Si): {random.uniform(0.15, 0.35):.2f}%
- Сера (S): ≤0.04%
- Фосфор (P): ≤0.035%

Механические свойства (фактические):
- Предел текучести: {random.randint(235, 500)} МПа
- Временное сопротивление: {random.randint(370, 650)} МПа
- Относительное удлинение: {random.randint(16, 28)}%

Заключение: Продукция соответствует заявленным требованиям и признана годной.

Начальник ОТК: _________________ /{_pick(CONSTRUCTION_WORDS["фамилии"])}/
Дата выдачи: {date}

М.П.
"""


def generate_ks2_text() -> str:
    """Сгенерировать текст КС-2 (акт о приёмке выполненных работ)."""
    org = _pick(CONSTRUCTION_WORDS["организации"])
    obj = _pick(CONSTRUCTION_WORDS["объекты"])
    date = (datetime.now() - timedelta(days=random.randint(30, 365))).strftime("%d.%m.%Y")
    period = f"{(datetime.strptime(date, '%d.%m.%Y') - timedelta(days=30)).strftime('%d.%m.%Y')} по {date}"

    total_cost = random.randint(500000, 5000000)

    return f"""Унифицированная форма № КС-2
Утверждена постановлением Госкомстата РФ от 11 ноября 1999 г. № 100

АКТ О ПРИЁМКЕ ВЫПОЛНЕННЫХ РАБОТ
№ {random.randint(1, 100)} от {date}

Инвестор: {org}
Заказчик (Генподрядчик): {org}
Подрядчик (Субподрядчик): {_pick(CONSTRUCTION_WORDS["организации"])}

Стройка: {obj}
Объект: {obj}

Сметная (договорная) стоимость: {total_cost:,} руб.

Отчётный период: {period}

┌──────┬────────────────────────────────┬──────┬──────────┬──────────┐
│  №   │ Наименование работ             │ Ед.  │ Колич.   │ Стоимость │
├──────┼────────────────────────────────┼──────┼──────────┼──────────┤
│  1   │ {random.choice(CONSTRUCTION_WORDS['работы']):<30} │ {random.choice(['м³','т','м²']):<4} │ {random.randint(10,500):>6}   │ {random.randint(50000,500000):>8,} │
│  2   │ {random.choice(CONSTRUCTION_WORDS['работы']):<30} │ {random.choice(['м³','т','м²']):<4} │ {random.randint(10,500):>6}   │ {random.randint(50000,500000):>8,} │
│  3   │ {random.choice(CONSTRUCTION_WORDS['работы']):<30} │ {random.choice(['м³','т','м²']):<4} │ {random.randint(10,500):>6}   │ {random.randint(50000,500000):>8,} │
└──────┴────────────────────────────────┴──────┴──────────┴──────────┘

Итого по акту: {total_cost:,} руб.

Сдал: _________________ /{_pick(CONSTRUCTION_WORDS['фамилии'])}/
Принял: _________________ /{_pick(CONSTRUCTION_WORDS['фамилии'])}/
"""


# =============================================================================
# Генераторы документов для разных типов
# =============================================================================

DOCUMENT_GENERATORS = {
    "aosr": generate_aosr_text,
    "certificate": generate_certificate_text,
    "ks2": generate_ks2_text,
    # Остальные типы используют шаблоны
    "journal": generate_aosr_text,  # Заглушка — позже можно добавить таблицы
    "executive_scheme": generate_aosr_text,  # Заглушка
    "contract": generate_aosr_text,  # Заглушка
    "claim": generate_aosr_text,  # Заглушка
    "upd": generate_ks2_text,  # УПД похож на КС-2 по структуре
}


# =============================================================================
# Артефакты (применяются к изображению)
# =============================================================================


def apply_coffee_stain(image: Image.Image, intensity: float = 0.3) -> Image.Image:
    """Наложить кофейное пятно (кольцо от кружки)."""
    img = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Случайное положение кольца
    cx = random.randint(img.width // 4, 3 * img.width // 4)
    cy = random.randint(img.height // 4, 3 * img.height // 4)
    outer_r = random.randint(80, 200)
    inner_r = outer_r - random.randint(10, 30)

    # Коричневый цвет с прозрачностью
    stain_color = (139, 90, 43, int(255 * intensity * random.uniform(0.5, 1.0)))

    # Рисуем кольцо (внешний круг минус внутренний)
    draw.ellipse(
        [cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r],
        fill=stain_color,
    )
    # «Вырезаем» середину
    draw.ellipse(
        [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
        fill=(0, 0, 0, 0),
    )

    # Добавляем несколько случайных капель рядом
    for _ in range(random.randint(1, 5)):
        dx = random.randint(-outer_r, outer_r)
        dy = random.randint(-outer_r, outer_r)
        drop_r = random.randint(5, 20)
        drop_alpha = int(255 * intensity * random.uniform(0.3, 0.7))
        draw.ellipse(
            [cx + dx - drop_r, cy + dy - drop_r, cx + dx + drop_r, cy + dy + drop_r],
            fill=(139, 90, 43, drop_alpha),
        )

    # Слегка размываем для реалистичности
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=2))

    return Image.alpha_composite(img, overlay).convert("RGB")


def apply_fold_lines(image: Image.Image) -> Image.Image:
    """Наложить линии сгиба (как от складывания листа А4 втрое)."""
    img = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Вертикальные линии сгиба (складывание втрое)
    positions = [img.width // 3, 2 * img.width // 3]
    for x in positions:
        # Основная линия сгиба
        x_jitter = x + random.randint(-5, 5)
        draw.line(
            [(x_jitter, 0), (x_jitter, img.height)],
            fill=(80, 80, 80, 30),
            width=1,
        )
        # Тень рядом с линией
        shadow_x = x_jitter + random.choice([-2, 2])
        draw.line(
            [(shadow_x, 0), (shadow_x, img.height)],
            fill=(200, 200, 200, 15),
            width=random.randint(5, 15),
        )

    # Горизонтальная линия сгиба (реже)
    if random.random() < 0.4:
        y = random.randint(img.height // 3, 2 * img.height // 3)
        draw.line(
            [(0, y), (img.width, y)],
            fill=(80, 80, 80, 25),
            width=1,
        )

    # Добавляем «пыль» вдоль сгибов
    for x in positions:
        for _ in range(random.randint(5, 15)):
            px = x + random.randint(-20, 20)
            py = random.randint(0, img.height)
            dot_r = random.randint(1, 3)
            draw.ellipse(
                [px - dot_r, py - dot_r, px + dot_r, py + dot_r],
                fill=(180, 180, 180, random.randint(20, 60)),
            )

    return Image.alpha_composite(img, overlay).convert("RGB")


def apply_boot_print(image: Image.Image) -> Image.Image:
    """Наложить след ботинка (реалистичный отпечаток подошвы)."""
    img = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Случайное положение
    bx = random.randint(100, img.width - 200)
    by = random.randint(100, img.height - 300)

    # Очертание подошвы (овал с сужением)
    sole_color = (100, 80, 60, random.randint(30, 80))
    draw.ellipse(
        [bx, by, bx + 180, by + 70],
        fill=sole_color,
    )
    # Носок
    draw.ellipse(
        [bx + 140, by - 10, bx + 200, by + 40],
        fill=sole_color,
    )

    # Протектор (горизонтальные линии)
    for i in range(6):
        ly = by + 10 + i * 12
        draw.line(
            [(bx + 20, ly), (bx + 160, ly)],
            fill=(80, 60, 40, random.randint(50, 100)),
            width=3,
        )

    # Размываем для реалистичности
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=3))

    return Image.alpha_composite(img, overlay).convert("RGB")


def apply_blur(image: Image.Image, intensity: float = 0.5) -> Image.Image:
    """Замыливание текста (как от плохого принтера/сканера)."""
    radius = int(1 + intensity * 2.5)
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def apply_crumpled_paper(image: Image.Image) -> Image.Image:
    """Наложить текстуру мятой бумаги."""
    img = image.copy()

    # Генерируем шумовую текстуру
    noise = np.random.rand(img.height // 8, img.width // 8) * 30 - 15
    from PIL import Image as PILImage
    noise_img = PILImage.fromarray(noise.astype(np.uint8), mode='L')
    noise_img = noise_img.resize((img.width, img.height), Image.BILINEAR)
    noise_img = noise_img.filter(ImageFilter.GaussianBlur(radius=10))

    # Затемняем складки
    noise_arr = np.array(noise_img, dtype=np.float32)
    img_arr = np.array(img, dtype=np.float32)

    # Затемнение в складках (noise < -10)
    darken_mask = noise_arr < -10
    img_arr[darken_mask] *= 0.85

    # Осветление на выпуклостях (noise > 10)
    lighten_mask = noise_arr > 10
    img_arr[lighten_mask] = np.clip(img_arr[lighten_mask] * 1.1, 0, 255)

    return Image.fromarray(img_arr.astype(np.uint8))


def apply_handwriting(image: Image.Image) -> Image.Image:
    """Добавить рукописные пометки (симулированные)."""
    img = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Используем встроенный шрифт (или курсив)
    try:
        font_size = random.randint(20, 36)
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            size=font_size,
        )
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Случайные пометки на полях
    notes = [
        "исправить", "переделать", "согласовано",
        "см. замечания", f"№{random.randint(1, 50)}",
        f"от {random.randint(1, 31):02d}.{random.randint(1, 12):02d}",
    ]
    for _ in range(random.randint(1, 4)):
        x = random.randint(20, img.width - 200)
        y = random.randint(100, img.height - 100)
        note = random.choice(notes)
        ink_color = random.choice([
            (0, 0, 255, 180),   # синяя ручка
            (255, 0, 0, 180),   # красная ручка
            (0, 100, 0, 160),   # зелёная ручка
        ])
        # Поворот текста для имитации рукописного наклона
        angle = random.randint(-15, 15)
        txt_img = Image.new("RGBA", (300, 60), (0, 0, 0, 0))
        txt_draw = ImageDraw.Draw(txt_img)
        txt_draw.text((10, 10), note, fill=ink_color, font=font)
        txt_img = txt_img.rotate(angle, expand=True, fillcolor=(0, 0, 0, 0))
        overlay.paste(txt_img, (x, y), txt_img)

    return Image.alpha_composite(img, overlay).convert("RGB")


def apply_scan_noise(image: Image.Image) -> Image.Image:
    """Добавить шум сканирования (соль/перец + полосы)."""
    img_arr = np.array(image)

    # Соль и перец
    noise_mask = np.random.random(img_arr.shape[:2]) < 0.01
    img_arr[noise_mask] = np.random.choice([0, 255], size=noise_mask.sum())

    # Вертикальные полосы от сканера
    if random.random() < 0.3:
        stripe_x = random.randint(0, image.width - 3)
        stripe_alpha = random.uniform(0.3, 0.6)
        img_arr[:, stripe_x:stripe_x+2] = (
            img_arr[:, stripe_x:stripe_x+2] * stripe_alpha
        ).astype(np.uint8)

    return Image.fromarray(img_arr)


def apply_stamp_overlay(image: Image.Image) -> Image.Image:
    """Наложить синюю печать организации."""
    img = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Круглая печать
    cx = random.randint(img.width // 2, img.width - 100)
    cy = random.randint(img.height // 2, img.height - 100)
    r = random.randint(40, 60)

    # Внешнее кольцо
    stamp_color = (0, 50, 150, 120)
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        outline=stamp_color,
        width=3,
    )
    # Внутреннее кольцо
    draw.ellipse(
        [cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8],
        outline=stamp_color,
        width=1,
    )

    # Текст по кругу (упрощённо — просто надпись в центре)
    org_name = random.choice(CONSTRUCTION_WORDS["организации"])[:20]
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            size=9,
        )
    except (OSError, IOError):
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), org_name, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(
        (cx - tw // 2, cy - 5),
        org_name,
        fill=stamp_color,
        font=font,
    )

    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=1))

    return Image.alpha_composite(img, overlay).convert("RGB")


def apply_low_resolution(image: Image.Image) -> Image.Image:
    """Понизить разрешение (симулирует старый сканер)."""
    # Уменьшаем и увеличиваем обратно
    small = image.resize(
        (image.width // 3, image.height // 3),
        Image.NEAREST,
    )
    return small.resize(image.size, Image.NEAREST)


# =============================================================================
# Реестр артефактов
# =============================================================================

ARTIFACT_REGISTRY: Dict[str, callable] = {
    "coffee_stain": apply_coffee_stain,
    "fold_lines": apply_fold_lines,
    "boot_print": apply_boot_print,
    "blur": apply_blur,
    "crumpled_paper": apply_crumpled_paper,
    "handwriting": apply_handwriting,
    "scan_noise": apply_scan_noise,
    "stamp_overlay": apply_stamp_overlay,
    "low_resolution": apply_low_resolution,
}

ARTIFACT_WEIGHTS = {
    "coffee_stain": 4,
    "fold_lines": 8,
    "boot_print": 2,
    "blur": 5,
    "crumpled_paper": 6,
    "handwriting": 7,
    "scan_noise": 5,
    "stamp_overlay": 3,
    "low_resolution": 4,
}


# =============================================================================
# Генерация PDF из текста
# =============================================================================


def text_to_image(text: str, width: int = A4_WIDTH, height: int = A4_HEIGHT) -> Image.Image:
    """Преобразовать текст в изображение A4 @ 300 DPI."""
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # Шрифт
    try:
        font_body = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            size=28,
        )
        font_title = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            size=36,
        )
    except (OSError, IOError):
        font_body = ImageFont.load_default()
        font_title = ImageFont.load_default()

    # Поля
    x = 120
    y = 120
    line_height = 40
    max_width = width - 240

    lines = text.split("\n")
    for line in lines:
        # Определяем размер шрифта
        font = font_title if (
            line.strip() and
            (line.isupper() or line.strip().startswith("АКТ") or
             line.strip().startswith("СЕРТИФИКАТ"))
        ) else font_body

        # Перенос длинных строк
        words = line.split()
        current_line = ""

        for word in words:
            test_line = current_line + " " + word if current_line else word
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] > max_width and current_line:
                draw.text((x, y), current_line, fill="black", font=font)
                y += line_height
                current_line = word
            else:
                current_line = test_line

        if current_line:
            draw.text((x, y), current_line, fill="black", font=font)
            y += line_height

        # Увеличенный отступ после заголовков/разделителей
        if not line.strip() or line.startswith("───") or line.startswith("==="):
            y += line_height // 2

        if y > height - 100:
            break

    # Добавляем «строчку подписи» если есть
    if y < height - 200:
        draw.text((x, y + 40), "М.П.", fill="black", font=font_body)

    return img


def generate_document_image(doc_type: str) -> Image.Image:
    """Сгенерировать изображение документа заданного типа."""
    generator = DOCUMENT_GENERATORS.get(doc_type, generate_aosr_text)
    text = generator()
    # Добавляем случайные строительные термины для разнообразия
    return text_to_image(text)


def apply_artifacts(
    image: Image.Image,
    artifact_names: List[str],
    intensity: float = 0.5,
) -> Image.Image:
    """Применить список артефактов к изображению."""
    img = image
    for name in artifact_names:
        if name not in ARTIFACT_REGISTRY:
            continue
        try:
            if name in ("blur", "coffee_stain"):
                img = ARTIFACT_REGISTRY[name](img, intensity=intensity)
            else:
                img = ARTIFACT_REGISTRY[name](img)
        except Exception:
            pass  # Пропускаем неудавшиеся артефакты
    return img


def random_artifacts(count: int = 3) -> List[str]:
    """Выбрать случайные артефакты с весами."""
    names = list(ARTIFACT_WEIGHTS.keys())
    weights = list(ARTIFACT_WEIGHTS.values())
    selected = []
    available = list(zip(names, weights))

    for _ in range(min(count, len(names))):
        if not available:
            break
        names_avail, weights_avail = zip(*available)
        total_w = sum(weights_avail)
        probs = [w / total_w for w in weights_avail]
        choice = np.random.choice(names_avail, p=probs)
        selected.append(choice)
        available = [(n, w) for n, w in available if n != choice]

    return selected


def generate_synthetic_document(
    doc_type: str,
    artifacts: Optional[List[str]] = None,
    artifact_count: int = 3,
    intense: bool = False,
) -> Image.Image:
    """Сгенерировать один синтетический документ с артефактами.

    Args:
        doc_type: тип документа (aosr, certificate, ks2, ...)
        artifacts: список артефактов (None = случайные)
        artifact_count: количество артефактов (если artifacts=None)
        intense: высокая интенсивность артефактов

    Returns:
        PIL Image с документом и артефактами
    """
    # Генерируем чистый документ
    img = generate_document_image(doc_type)

    # Выбираем артефакты
    if artifacts is None:
        artifacts = random_artifacts(artifact_count)

    intensity = 0.7 if intense else 0.4

    # Применяем артефакты
    img = apply_artifacts(img, artifacts, intensity=intensity)

    return img


# =============================================================================
# Пакетная генерация
# =============================================================================


@dataclass
class GenerationConfig:
    """Конфигурация пакетной генерации."""
    doc_types: List[str] = field(default_factory=lambda: ["aosr", "certificate", "ks2"])
    artifacts: Optional[List[str]] = None
    artifact_count: int = 3
    count_per_type: int = 10
    intense_ratio: float = 0.2  # доля документов с высокой интенсивностью
    output_dir: Path = Path("data/synthetic_docs")
    format: str = "png"  # png или pdf
    seed: Optional[int] = None


def generate_batch(config: GenerationConfig) -> List[Path]:
    """Пакетная генерация синтетических документов.

    Returns:
        Список путей к сгенерированным файлам
    """
    if config.seed is not None:
        random.seed(config.seed)
        np.random.seed(config.seed)

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_files = []
    manifest = {"documents": [], "artifacts_used": [], "config": {}}

    for doc_type in config.doc_types:
        type_dir = output_dir / doc_type
        type_dir.mkdir(exist_ok=True)

        for i in range(config.count_per_type):
            intense = random.random() < config.intense_ratio
            artifacts = (
                config.artifacts
                if config.artifacts
                else random_artifacts(config.artifact_count + (2 if intense else 0))
            )

            print(f"  [{doc_type}] {i+1}/{config.count_per_type}: "
                  f"{', '.join(artifacts)} {'(intense)' if intense else ''}")

            img = generate_synthetic_document(
                doc_type=doc_type,
                artifacts=artifacts,
                intense=intense,
            )

            # Сохранить
            clean_type = "clean" if not artifacts else "artifact"
            filename = f"{doc_type}_{clean_type}_{i+1:03d}.{config.format}"

            if config.format == "pdf":
                filepath = type_dir / filename
                img_rgb = img.convert("RGB")
                img_rgb.save(filepath, "PDF", resolution=300)
            else:
                filepath = type_dir / filename
                img.save(filepath, "PNG")

            generated_files.append(filepath)

            manifest["documents"].append({
                "file": str(filepath),
                "doc_type": doc_type,
                "artifacts": artifacts,
                "intense": intense,
            })

    # Сохранить манифест
    manifest["artifacts_used"] = list(set(
        a for d in manifest["documents"] for a in d["artifacts"]
    ))
    manifest["config"] = {
        "doc_types": config.doc_types,
        "count_per_type": config.count_per_type,
        "total": len(generated_files),
    }
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\nСгенерировано: {len(generated_files)} файлов")
    print(f"Манифест: {manifest_path}")
    print(f"Типы артефактов: {manifest['artifacts_used']}")

    return generated_files


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="ASD Synthetic Document Generator — генератор синтетических строй-документов с артефактами",
    )
    parser.add_argument(
        "--count", type=int, default=50,
        help="Общее количество документов",
    )
    parser.add_argument(
        "--types", type=str, default="aosr,certificate,ks2",
        help="Типы документов через запятую (aosr,certificate,ks2,journal,executive_scheme,contract,claim,upd)",
    )
    parser.add_argument(
        "--all-types", action="store_true",
        help="Генерировать все типы документов",
    )
    parser.add_argument(
        "--artifacts", type=str, default=None,
        help="Артефакты через запятую (coffee_stain,fold_lines,boot_print,blur,crumpled_paper,handwriting,scan_noise,stamp_overlay,low_resolution)",
    )
    parser.add_argument(
        "--all-artifacts", action="store_true",
        help="Использовать все доступные артефакты",
    )
    parser.add_argument(
        "--artifact-count", type=int, default=3,
        help="Количество артефактов на документ (если --artifacts не указан)",
    )
    parser.add_argument(
        "--intense", type=float, default=0.2,
        help="Доля документов с высокой интенсивностью артефактов (0.0–1.0)",
    )
    parser.add_argument(
        "--output-dir", type=str, default="data/synthetic_docs",
        help="Папка для сохранения сгенерированных документов",
    )
    parser.add_argument(
        "--format", type=str, default="png", choices=["png", "pdf"],
        help="Формат выходных файлов",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed для воспроизводимости",
    )

    args = parser.parse_args()

    if not HAS_PIL:
        print("❌ Требуется Pillow: pip install Pillow")
        sys.exit(1)

    # Определяем типы документов
    if args.all_types:
        doc_types = list(DOCUMENT_GENERATORS.keys())
    else:
        doc_types = [t.strip() for t in args.types.split(",")]
        for dt in doc_types:
            if dt not in DOCUMENT_GENERATORS:
                print(f"⚠️ Неизвестный тип документа: {dt}. Доступны: {list(DOCUMENT_GENERATORS.keys())}")
                doc_types.remove(dt)

    # Определяем артефакты
    artifacts = None
    if args.artifacts:
        artifacts = [a.strip() for a in args.artifacts.split(",")]
        for a in artifacts:
            if a not in ARTIFACT_REGISTRY:
                print(f"⚠️ Неизвестный артефакт: {a}. Доступны: {list(ARTIFACT_REGISTRY.keys())}")
                artifacts.remove(a)

    # Распределяем count по типам
    count_per_type = max(1, args.count // len(doc_types))

    config = GenerationConfig(
        doc_types=doc_types,
        artifacts=artifacts,
        artifact_count=args.artifact_count,
        count_per_type=count_per_type,
        intense_ratio=args.intense,
        output_dir=Path(args.output_dir),
        format=args.format,
        seed=args.seed,
    )

    print(f"\nГенерация синтетических документов ASD v12.0")
    print(f"  Типы: {', '.join(doc_types)}")
    print(f"  По {count_per_type} каждого типа (всего {count_per_type * len(doc_types)})")
    print(f"  Артефакты: {artifacts if artifacts else 'случайные ' + str(args.artifact_count) + ' шт.'}")
    print(f"  Интенсивных: {args.intense:.0%}")
    print(f"  Формат: {args.format}")
    print(f"  Папка: {args.output_dir}")
    print()

    files = generate_batch(config)

    print(f"\n✅ Готово. {len(files)} файлов в {args.output_dir}")


if __name__ == "__main__":
    main()
