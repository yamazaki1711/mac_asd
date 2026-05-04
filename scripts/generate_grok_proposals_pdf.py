#!/usr/bin/env python3
"""
Generate Grok_ASD_Proposals.pdf — complete analysis of Grok AI's 35 proposals
for MAC_ASD v13.0 → v14.0, cross-referenced against actual codebase state.
"""
import os, sys, textwrap
from datetime import datetime
from fpdf import FPDF, XPos, YPos

# Add DejaVu for Cyrillic (bundled with fpdf2)
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

# Fallback font paths
for path in [FONT_PATH, "/usr/share/fonts/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
    if os.path.exists(path):
        FONT_PATH = path
        break
for path in [FONT_BOLD, "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
    if os.path.exists(path):
        FONT_BOLD = path
        break
for path in [FONT_MONO, "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]:
    if os.path.exists(path):
        FONT_MONO = path
        break

# =============================================================================
# DATA — all 35 Grok proposals, cross-referenced with codebase verification
# =============================================================================

# Each proposal: (id, phase, proposal_text, codebase_status, evidence, priority, implementation_plan)
PROPOSALS = [
    # === PHASE 1: UI ===
    ("1.1", "Фаза 1: UI + HITL",
     "Desktop-приложение (Electron / Tauri)",
     "НЕТ", "Нулевой фронтенд-код. MCP-сервер работает через stdio.",
     "Rejected", "Заменено на локальный веб-интерфейс (Flask/FastAPI + HTML/JS). См. план 1.1b."),

    ("1.1b", "Фаза 1: UI + HITL",
     "Локальный веб-интерфейс (вместо Electron/Tauri)",
     "НЕТ", "В проекте нет веб-фреймворка для UI. Единственный FastAPI — IS Generator.",
     "P0", "Запустить FastAPI на localhost:8080, Jinja2-шаблоны. 6 разделов. ~1500 строк кода."),

    ("1.2", "Фаза 1: UI + HITL",
     "Главный дашборд проекта (Delta ИД, % комплектности, риски, HITL-задачи)",
     "Частично", "Метрики собираются (Observability, HITLSystem.progress, CompletenessResult.completeness_pct). Дашборда нет.",
     "P0", "REST endpoint /api/dashboard/{project_id} → JSON + HTML-рендеринг с диаграммами (Chart.js). 2 дня."),

    ("1.3", "Фаза 1: UI + HITL",
     "Разделы UI: Проекты, Документы, Агенты, Граф доказательств, HITL, Отчёты",
     "НЕТ", "Нет UI-слоя.",
     "P0", "6 вкладок в web-интерфейсе. Навигация через sidebar. Каждая — отдельный шаблон Jinja2."),

    ("1.4", "Фаза 1: UI + HITL",
     "Drag & drop загрузка документов + массовый импорт папки",
     "НЕТ", "Нет UI загрузки. IngestionPipeline.scan_folder() — CLI.",
     "P0", "HTML5 File API + dropzone.js. POST /api/upload — сохраняет во временную папку → IngestionPipeline."),

    ("1.5", "Фаза 1: UI + HITL",
     "Просмотр результатов анализа с подсветкой и комментариями",
     "НЕТ", "Нет UI-отображения результатов.",
     "P1", "JSON → HTML рендеринг с highlight.js для секций договора. Поле комментария к каждому finding."),

    ("1.6", "Фаза 1: UI + HITL",
     "История действий и изменений по проекту",
     "Частично", "AuditLog (DB-модель), audit_trail в AgentState. Без UI-просмотра.",
     "P1", "Страница /project/{id}/history — временная шкала из audit_logs + audit_trail."),

    ("1.7", "Фаза 1: UI + HITL",
     "HITL-интерфейс: приоритет, контекст, варианты, прикрепление файлов",
     "Частично", "HITLSystem (421 строк) — приоритеты, вопросы, опции. Только MCP-тулы + Telegram.",
     "P0", "Web-интерфейс HITL: /hitl/{project_id} — список вопросов, фильтр по приоритету, форма ответа с файлом."),

    ("1.8", "Фаза 1: UI + HITL",
     "Комментирование и доопределение данных",
     "НЕТ", "HITLSystem принимает ответы, но без свободного комментария оператора.",
     "P1", "+ поле comment в HITLAnswer, сохранение в hitl_sessions DB. UI: textarea под вариантами."),

    ("1.9", "Фаза 1: UI + HITL",
     "Уведомления о новых задачах HITL",
     "НЕТ", "Нет системы уведомлений.",
     "P1", "WebSocket / SSE канал /api/hitl/events. Браузерное уведомление через Notification API."),

    ("1.10", "Фаза 1: UI + HITL",
     "История всех вопросов и ответов оператора",
     "Частично", "HITLSession хранит questions/answers в памяти. Нет персистентного хранения.",
     "P1", "DB-таблица hitl_history. UI: /hitl/{project_id}/history."),

    ("1.11", "Фаза 1: UI + HITL",
     "Визуализация текущего этапа жизненного цикла проекта",
     "НЕТ", "BUILDING_LIFECYCLE_WORKFLOW.md описывает 6 фаз текстом. StateGraph enum — без визуализации.",
     "P1", "SVG-пайплайн: 6 шагов lifecycle с цветовой индикацией текущего этапа (зелёный/серый)."),

    ("1.12", "Фаза 1: UI + HITL",
     "Очередь задач и приоритизация от PM",
     "Частично", "HITLSystem сортирует вопросы по приоритету в памяти. Нет очереди задач PM.",
     "P1", "DB-таблица task_queue. PM-agent генерирует recommended_next_actions → UI /project/{id}/tasks."),

    # === PHASE 2: STABILITY ===
    ("2.1", "Фаза 2: Стабильность",
     "Улучшенная обработка ошибок + авто-восстановление",
     "✅ ДА", "LLMEngine.safe_chat() — retry с exponential backoff (3 попытки, 1→30 сек). FallbackRouter — rule-based PM при недоступности LLM. Typed exception hierarchy (13 классов).",
     "P0 (улучшать)", "Добавить self-healing: переподключение к Ollama после падения, авто-перезагрузка моделей после OOM."),

    ("2.2", "Фаза 2: Стабильность",
     "Graceful degradation (система продолжает работать при падении модулей)",
     "✅ ДА", "Реализовано: LLM→rule-based fallback, DB→stub fallback, optional deps (structlog, ezdxf, PyMuPDF), RAM degradation (3 уровня).",
     "P0 (улучшать)", "Добавить индикатор degraded mode в UI. Расширить stub fallback на все критические пути."),

    ("2.3", "Фаза 2: Стабильность",
     "Автоматические бэкапы БД и графов",
     "НЕТ", "Только однострочная рекомендация в DEPLOYMENT_PLAN.md. Ни скриптов, ни cron-задач, ни scheduled tasks.",
     "P0", "Cron-задача (ежечасно): pg_dump + tar czf graphs + artifacts → backup/директория. Ротация: 24 часовых + 7 дневных + 4 недельных."),

    ("2.4", "Фаза 2: Стабильность",
     "Логирование всех важных действий и ошибок",
     "Частично", "AuditLog-модель + audit_trail + JSON structured logging. НО: только действия агентов, не оператора.",
     "P1", "Middleware: перехват всех MCP-tool вызовов → AuditLog. UI для просмотра: /admin/logs."),

    ("2.5", "Фаза 2: Стабильность",
     "Улучшение RAM Manager: предиктивная выгрузка моделей",
     "НЕТ", "RAM Manager — чисто реактивный. Разгружает только при превышении порогов (WARNING/CRITICAL/OOM_DANGER).",
     "P1", "Тренд-анализ: скользящее среднее RAM за 5 минут → прогноз на 5 минут вперёд → превентивная выгрузка."),

    ("2.6", "Фаза 2: Стабильность",
     "Мониторинг и алерты при высоком давлении памяти",
     "Частично", "Мониторинг: psutil + nvidia-smi + gc (хороший). Алерты: только logger.warning().",
     "P1", "Telegram-алерт при pressure > 80%. Health-check endpoint /api/health с JSON-статусом RAM."),

    ("2.7", "Фаза 2: Стабильность",
     "Оптимизация работы с большими документами",
     "Частично", "Map-Reduce для контрактов >280K символов. Структурный чанкинг (по разделам/таблицам).",
     "P2", "Параллельный Map-Reduce для независимых чанков. Кэширование embeddings. Потоковый стриминг из БД."),

    ("2.8", "Фаза 2: Стабильность",
     "Улучшение шаблонов DOCX/PDF (единообразие стиля, штампы, нумерация)",
     "Частично", "A4Template (Times New Roman 12pt). GOSTStamp (DXF). NumberingService (JSON). TemplateLib v2.0. НО: нет колонтитулов, нет сквозной нумерации страниц.",
     "P1", "Единый стилевой конфиг для всех DOCX/PDF. Авто-колонтитулы. ГОСТ 21.101 штамп в DOCX. Префиксы страниц."),

    ("2.9", "Фаза 2: Стабильность",
     "Версионирование сгенерированных документов",
     "Частично", "ArtifactStore: artifact_write() с авто-инкрементом версий. Registry JSON. НО: нет draft/review/approved workflow.",
     "P1", "Добавить статусную модель (draft→review→approved→signed). Блокировка approved-версий от изменений."),

    ("2.10", "Фаза 2: Стабильность",
     "Возможность редактирования документов перед сохранением",
     "НЕТ", "Артефакты записываются атомарно — без предпросмотра и редактирования.",
     "P2", "Preview-режим: генерация HTML-превью → правки оператора → конвертация в DOCX/PDF. 3-шаговый процесс."),

    # === PHASE 3: TESTING ===
    ("3.1", "Фаза 3: Тестирование",
     "E2E-тесты по полным сценариям (тендер → договор → производство → сдача)",
     "Частично", "2 E2E-файла (forensic + parallel_graph), 16+ сценариев. 605 тестов, 590 pass. НО: полный сквозной сценарий (тендер→КС-11) не покрыт.",
     "P2", "E2E-тест tender_to_ks11.py: 12 шагов от поиска тендера до подписания КС-11. 500-страничный проект."),

    ("3.2", "Фаза 3: Тестирование",
     "Тестирование на реальных документах разных объектов",
     "Частично", "Benchmark script (run_benchmark.py) на проекте LOS (12 PDF). 20 test-файлов. НО: только один объект.",
     "P2", "Собрать тестовый набор из 3+ реальных объектов. Автоматизировать прогон через CI."),

    ("3.3", "Фаза 3: Тестирование",
     "Тесты на edge-кейсы (длинные договоры, сильно повреждённые сканы)",
     "Частично", "Тест forensic имеет obsolete material и quantity mismatch. НО: нет теста на 500-стр. договор, нет теста на испорченный скан.",
     "P2", "Synthetic doc generator: создать повреждённый скан (шум, размытие). Договор 500 стр. → тест Map-Reduce."),

    ("3.4", "Фаза 3: Тестирование",
     "Запуск системы в shadow-режиме на 1–2 реальных объектах",
     "НЕТ", "Нет shadow mode. Система работает в одном «боевом» режиме.",
     "P2", "Режим: обрабатывает реальные документы, но НЕ генерирует финальные DOCX. Только отчёт о найденных проблемах."),

    ("3.5", "Фаза 3: Тестирование",
     "Сбор обратной связи от ПТО, юристов, сметчиков",
     "НЕТ", "Нет механизма сбора обратной связи.",
     "P2", "Форма обратной связи в UI: /feedback. Сохраняется в DB. Еженедельный отчёт."),

    # === PHASE 4: DOCUMENTATION ===
    ("4.1", "Фаза 4: Документация",
     "User Guide — как работать с системой",
     "НЕТ", "Нет пользовательской документации. Только технические документы для разработчиков.",
     "P2", "Markdown → PDF: пошаговые инструкции для 5 ролей (оператор, ПТО, юрист, сметчик, PM). Скриншоты."),

    ("4.2", "Фаза 4: Документация",
     "Инструкции по типовым сценариям (анализ договора, восстановление ИД, доп. объёмы)",
     "НЕТ", "Сценарии описаны в CONCEPT_v12.md на уровне архитектуры, не инструкций.",
     "P2", "3 сценария с полными последовательностями действий. Workflow-диаграммы (Mermaid) + описание шагов."),

    ("4.3", "Фаза 4: Документация",
     "Видео-инструкции",
     "НЕТ (Rejected)", "Команда из 4 чел. обучается за день работы с системой.",
     "— (отклонено)", "Не требуется. Очное обучение при развёртывании."),

    ("4.4", "Фаза 4: Документация",
     "Обновление всех архитектурных документов под текущее состояние",
     "Частично", "COMPONENT_ARCHITECTURE.md (1693 строки), DATA_SCHEMA.md, MCP_TOOLS_SPEC.md, CONCEPT_v12.md — обширная, но местами расходится с кодом.",
     "P2", "Аудит документации: сверить все md-файлы с актуальным кодом. Удалить устаревшие секции. Единый индекс."),

    ("4.5", "Фаза 4: Документация",
     "API/MCP документация для разработчиков",
     "Частично", "MCP_TOOLS_SPEC.md описывает 74 инструмента. НО: не все документированы (WorkSpec, Lab, Google, Lessons Learned).",
     "P2", "Документировать оставшиеся группы инструментов: WorkSpec (8), Lab (13), Google (16), Lessons (7)."),

    # === PHASE 5: SECURITY ===
    ("5.1", "Фаза 5: Безопасность",
     "Аудит логов действий пользователей",
     "Частично", "AuditLog-модель для агентов. НЕТ логирования действий оператора (загрузки, HITL-ответы, экспорт).",
     "P1", "Middleware-перехват всех user-facing вызовов → AuditLog. НЕ агентских."),

    ("5.2", "Фаза 5: Безопасность",
     "Цифровая подпись и верификация сгенерированных документов",
     "НЕТ (Rejected)", "Документы подписываются физически на бумаге.",
     "— (отклонено)", "Не требуется для антикризисного сценария. Документы идут на бумагу с мокрыми подписями."),

    ("5.3", "Фаза 5: Безопасность",
     "Контроль доступа (роли: руководитель, ПТО, юрист, сметчик)",
     "НЕТ (Rejected)", "Single-user система. 4 человека в одной комнате, один Mac Studio.",
     "— (отклонено)", "Не требуется. Физический контроль доступа (команда работает вместе)."),

    ("5.4", "Фаза 5: Безопасность",
     "Шифрование чувствительных данных",
     "НЕТ", "CONCEPT заявляет «ни байта коммерческой информации не покидает устройство», но шифрования на диске нет.",
     "P2", "LUKS-шифрование диска на уровне ОС. Пароль при старте сервиса. Не Python-решение."),

    ("5.5", "Фаза 5: Безопасность",
     "Установка с ограниченными правами",
     "НЕТ", "Система запускается от текущего пользователя без ограничений.",
     "P2", "Docker-контейнер с read-only FS кроме volumes. Запуск от непривилегированного пользователя."),

    # === PHASE 6: ANALYTICS ===
    ("6.1", "Фаза 6: Аналитика",
     "Дашборд с ключевыми показателями по всем проектам",
     "НЕТ (Rejected)", "Антикризис: один объект за раз.",
     "— (отклонено)", "Не для v1.0. Может быть добавлено после пилотного внедрения при переходе к сопровождению."),

    ("6.2", "Фаза 6: Аналитика",
     "Отчёты: найденные ловушки, неучтённые объёмы, Delta ИД",
     "Частично", "Ловушки: DomainTrap + TelegramScout + БЛС (61 ловушка) — работает. Неучтённые объёмы: vor_compare / vor_check — работает. Delta ИД: completeness_matrix. НО: нет консолидированного отчёта.",
     "P1", "Консолидированный PDF-отчёт: 3 секции (ловушки, расхождения ВОР, Delta ИД). Генерация одним вызовом."),

    ("6.3", "Фаза 6: Аналитика",
     "Экономический эффект (сэкономленное время, предотвращённые риски)",
     "Минимально", "Только в procurement: margin_absolute, potential_savings. Общего расчёта нет.",
     "P2", "Метрики: часы работы оператора × ставка, сумма предотвращённых рисков, стоимость кассового разрыва."),

    ("6.4", "Фаза 6: Аналитика",
     "Экспорт отчётов в PDF/Excel",
     "Частично", "PDF: 12+ скриптов, ReportLab v3 в PPR, fpdf2 в скриптах. Excel: НЕТ. Только чтение.",
     "P2", "Excel: openpyxl writer для табличных отчётов (ловушки, VOR-сравнение). PDF: унифицировать на ReportLab."),

    # === PHASE 7: EXPANSION ===
    ("7.1", "Фаза 7: Расширение",
     "Интеграция с Telegram (WorkEntry от полевых инженеров)",
     "✅ ДА", "Полностью: WorkEntryService, TelegramScout (40+ каналов), TelegramIngester, WorkEntry DB-модель. Сообщения → WorkEntry → АОСР.",
     "P0 (улучшать)", "Бот для приёма сообщений от полевых инженеров: /workentry фото+текст → WorkEntryParsing. Ответ бота с результатом."),

    ("7.2", "Фаза 7: Расширение",
     "Мобильное приложение / лёгкая версия для планшета",
     "НЕТ (Rejected)", "Команда работает стационарно на Mac Studio.",
     "— (отклонено)", "Telegram-бот покрывает потребность полевого ввода. Мобильное приложение не нужно."),

    ("7.3", "Фаза 7: Расширение",
     "Интеграция с 1С и Смета.ру (экспорт/импорт)",
     "НЕТ (Rejected)", "Антикризис: работаем автономно. Не привязаны к учётным системам заказчика.",
     "— (отклонено)", "При необходимости: CSV-экспорт/импорт как универсальный формат обмена."),

    ("7.4", "Фаза 7: Расширение",
     "Автоматическое улучшение промптов на основе обратной связи",
     "НЕТ (Rejected)", "Схема LessonLearned есть, пайплайна автоулучшения нет.",
     "P2 (долгосрок)", "После накопления 100+ confirmed lessons: fine-tuning промптов через LLM-as-Judge сравнение."),

    ("7.5", "Фаза 7: Расширение",
     "Версионирование и сравнение разных редакций документов",
     "Частично", "Доменные comparison engines (vor_compare, pd_analysis). ArtifactStore с версиями. НО: нет общего diff.",
     "P2", "Generic doc diff: difflib по тексту + LLM-резюме изменений («что изменилось между v1 и v2»)."),

    ("7.6", "Фаза 7: Расширение",
     "Расширенная аналитика по поставщикам и логистике",
     "Базово", "Модели Vendor/PriceList/MaterialCatalog. Margin-расчёт. Калькуляция доставки. НО: rule-based, без ML.",
     "P2", "Взвешенный scoring поставщиков: цена × стабильность × качество × логистика. После пилота."),
]

# =============================================================================
# PDF Class
# =============================================================================

class GrokPDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self.add_font("DejaVu", "", FONT_PATH, uni=True)
        self.add_font("DejaVu", "B", FONT_BOLD, uni=True)
        self.add_font("DejaVuMono", "", FONT_MONO, uni=True)
        self.set_auto_page_break(True, 20)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("DejaVu", "", 7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 4, "Grok AI → MAC_ASD Proposals Analysis  |  04.05.2026  |  Конфиденциально", align="C")
        self.ln(6)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, str(self.page_no()), align="C")

    def cover_page(self):
        self.add_page()
        self.ln(40)
        self.set_font("DejaVu", "B", 28)
        self.set_text_color(25, 25, 80)
        self.multi_cell(0, 12, "Grok AI → MAC_ASD\nРекомендации по развитию\nv13.0 → v14.0", align="C")
        self.ln(12)
        self.set_draw_color(25, 25, 80)
        self.set_line_width(1)
        mid = self.w / 2
        self.line(mid - 30, self.get_y(), mid + 30, self.get_y())
        self.ln(12)
        self.set_font("DejaVu", "", 12)
        self.set_text_color(60, 60, 60)
        self.cell(0, 8, "Статус предложений: верификация по коду на 04.05.2026", align="C")
        self.ln(8)
        self.cell(0, 8, "Всего предложений: 35 (7 фаз Grok) + 1 адаптация (веб-интерфейс)", align="C")
        self.ln(8)
        self.cell(0, 8, "Реализовано: 3  |  Частично: 18  |  Не реализовано: 15  |  Отклонено: 8", align="C")
        self.ln(16)
        self.set_font("DejaVu", "", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, "Подготовлено для: Руководитель проекта MAC_ASD", align="C")
        self.ln(6)
        self.cell(0, 6, "Документ содержит: полный список, статус, приоритет, план реализации", align="C")
        self.ln(6)
        self.cell(0, 6, "На основе диалога с Grok AI от 04.05.2026 + полной верификации кодовой базы", align="C")

    def section_title(self, title):
        self.ln(4)
        self.set_font("DejaVu", "B", 14)
        self.set_text_color(25, 25, 80)
        self.cell(0, 8, title)
        self.ln(10)
        self.set_draw_color(25, 25, 80)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(6)

    def proposal_block(self, prop_id, proposal, status, evidence, priority, plan):
        # Check if we need a page break (estimate ~60mm per block)
        if self.get_y() > self.h - 70:
            self.add_page()

        # Status badge color
        colors = {
            "✅ ДА": (0, 130, 0),
            "Частично": (200, 150, 0),
            "НЕТ": (180, 40, 40),
            "НЕТ (Rejected)": (120, 120, 120),
            "Минимально": (200, 150, 0),
            "Базово": (200, 150, 0),
        }
        r, g, b = colors.get(status, (100, 100, 100))

        # ID + Status tag
        self.set_font("DejaVu", "B", 10)
        self.set_text_color(r, g, b)
        self.cell(14, 6, prop_id)
        self.set_fill_color(r, g, b)
        self.set_text_color(255, 255, 255)
        status_text = status.replace("НЕТ (Rejected)", "ОТКЛОНЕНО").replace("✅ ДА", "РЕАЛИЗОВАНО")
        self.cell(42, 6, f" {status_text} ", fill=True)
        self.set_text_color(25, 25, 80)
        self.set_font("DejaVu", "B", 10)
        self.cell(0, 6, proposal)
        self.ln(7)

        # Evidence
        self.set_font("DejaVu", "", 8)
        self.set_text_color(80, 80, 80)
        self.cell(14, 4, "")
        self.cell(0, 4, f"Состояние в коде: {evidence}")
        self.ln(5)

        # Priority
        self.set_font("DejaVu", "B", 8)
        self.set_text_color(60, 60, 60)
        self.cell(14, 4, "")
        self.cell(18, 4, "Приоритет: ")
        self.set_font("DejaVu", "", 8)
        priority_color = {
            "P0": (180, 40, 40),
            "P1": (200, 130, 0),
            "P2": (60, 100, 180),
            "— (отклонено)": (120, 120, 120),
        }
        pc = priority_color.get(priority, (60, 60, 60))
        self.set_text_color(*pc)
        self.cell(0, 4, priority)
        self.ln(5)

        # Implementation plan (only for non-rejected)
        if "отклонено" not in priority:
            self.set_font("DejaVu", "B", 8)
            self.set_text_color(60, 60, 60)
            self.cell(14, 4, "")
            self.cell(22, 4, "План: ")
            self.set_font("DejaVu", "", 8)
            self.set_text_color(40, 40, 40)
            # Word-wrap the plan text
            x = self.get_x()
            self.set_x(x + 14)
            self.multi_cell(self.w - self.l_margin - self.r_margin - 14, 4, plan)
        else:
            self.set_font("DejaVu", "", 8)
            self.set_text_color(120, 120, 120)
            self.cell(14, 4, "")
            self.cell(0, 4, plan)

        self.ln(4)
        # Separator
        self.set_draw_color(230, 230, 230)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    def summary_matrix(self):
        """Full summary matrix of all proposals"""
        self.add_page()
        self.section_title("Сводная матрица: все 35 предложений Grok (+ 1 адаптация)")

        # Table header
        self.set_font("DejaVu", "B", 7)
        self.set_fill_color(25, 25, 80)
        self.set_text_color(255, 255, 255)
        col_w = [12, 72, 26, 26, 26]
        headers = ["ID", "Предложение", "Статус", "Приоритет", "Фаза"]
        for i, h in enumerate(headers):
            self.cell(col_w[i], 6, h, border=1, fill=True)
        self.ln()

        # Table rows
        self.set_font("DejaVu", "", 7)
        status_colors = {
            "✅ ДА": (0, 100, 0),
            "Частично": (180, 130, 0),
            "НЕТ": (180, 40, 40),
            "НЕТ (Rejected)": (120, 120, 120),
            "Минимально": (180, 100, 0),
            "Базово": (180, 130, 0),
        }
        for p in PROPOSALS:
            pid, phase, proposal, status, evidence, priority, plan = p
            if self.get_y() > self.h - 20:
                self.add_page()
                self.set_font("DejaVu", "B", 7)
                self.set_fill_color(25, 25, 80)
                self.set_text_color(255, 255, 255)
                for i, h in enumerate(headers):
                    self.cell(col_w[i], 6, h, border=1, fill=True)
                self.ln()
                self.set_font("DejaVu", "", 7)

            r, g, b = status_colors.get(status, (60, 60, 60))
            # Strip "НЕТ (Rejected)" → "Отклонено"
            display_status = status.replace("НЕТ (Rejected)", "Отклонено").replace("✅ ДА", "Реализовано")
            short_phase = phase.replace("Фаза 1: UI + HITL", "UI+HITL").replace("Фаза 2: Стабильность", "Стабильность").replace("Фаза 3: Тестирование", "Тестирование").replace("Фаза 4: Документация", "Документация").replace("Фаза 5: Безопасность", "Безопасность").replace("Фаза 6: Аналитика", "Аналитика").replace("Фаза 7: Расширение", "Расширение")
            short_priority = priority.replace("P0 (улучшать)", "P0*").replace("— (отклонено)", "—")

            self.set_text_color(40, 40, 40)
            self.cell(col_w[0], 5, pid, border=1)
            self.cell(col_w[1], 5, proposal[:42], border=1)
            self.set_text_color(r, g, b)
            self.set_font("DejaVu", "B", 7)
            self.cell(col_w[2], 5, display_status[:14], border=1)
            self.set_font("DejaVu", "", 7)
            self.set_text_color(40, 40, 40)
            self.cell(col_w[3], 5, short_priority, border=1)
            self.cell(col_w[4], 5, short_phase, border=1)
            self.ln()

        self.ln(6)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(80, 80, 80)
        self.cell(0, 5, "Цвета: зелёный = реализовано, оранжевый = частично, красный = не реализовано, серый = отклонено")
        self.ln(5)
        self.cell(0, 5, "P0 = критический (антикризис), P1 = важный (до пилота), P2 = желательный (после пилота), «—» = не делаем")

    def recommendations_page(self):
        """Executive recommendations page"""
        self.add_page()
        self.section_title("Рекомендации руководителю")

        self.set_font("DejaVu", "", 10)
        self.set_text_color(40, 40, 40)

        recommendations = [
            ("Немедленно (P0, май 2026)", [
                "1. Веб-интерфейс (локальный localhost:8080) — главный пробел. Без UI система — «чёрный ящик» для оператора.",
                "2. HITL-интерфейс в вебе — оператор должен видеть вопросы и отвечать на них, не читая JSON.",
                "3. Дашборд проекта — Delta ИД, % комплектности, активные риски. Команда не должна работать вслепую.",
                "4. Drag & drop загрузка — тотальная инвентаризация начинается с массового сканирования.",
                "5. Авто-бэкапы БД и графов — результат антикризисной операции не может быть потерян.",
                "6. Улучшение Telegram-бота — полевые инженеры шлют WorkEntry → автоматическая генерация АОСР.",
            ]),
            ("До пилота (P1, июнь 2026)", [
                "7. Просмотр результатов анализа с подсветкой — юрист должен видеть risky clauses в контракте.",
                "8. История действий и HITL-ответов — аудит решений оператора.",
                "9. Визуализация жизненного цикла проекта — на каком этапе мы сейчас находимся.",
                "10. Очередь задач от PM — рекомендованные следующие действия.",
                "11. Мониторинг RAM с алертами (Telegram) — предотвращение OOM на объекте.",
                "12. Общее логирование (user actions + agent actions) → AuditLog.",
                "13. Улучшение DOCX/PDF шаблонов — единый стиль, авто-штампы, нумерация.",
                "14. Версионирование документов (draft→review→approved→signed).",
                "15. Консолидированный PDF-отчёт (ловушки + расхождения ВОР + Delta ИД).",
            ]),
            ("После пилота (P2, июль–август 2026)", [
                "16. E2E-тест полного цикла (тендер → КС-11), 500-страничный проект.",
                "17. Shadow-режим на реальных объектах.",
                "18. User Guide и сценарные инструкции.",
                "19. Экспорт в Excel (ловушки, VOR-сравнение).",
                "20. Экономический эффект: время × ставка + предотвращённые риски.",
                "21. Generic document diff + LLM-резюме изменений.",
                "22. Шифрование диска (LUKS), Docker с ограниченными правами.",
            ]),
            ("Не делать (отклонено)", [
                "• Desktop-приложение (Electron/Tauri) → локальный веб лучше.",
                "• Мобильное приложение → Telegram-бот покрывает.",
                "• Интеграция с 1С/Смета.ру → CSV экспорт при необходимости.",
                "• Видео-инструкции → очное обучение.",
                "• RBAC → физический контроль доступа (одна комната).",
                "• Цифровая подпись → физические подписи на бумаге.",
                "• Дашборд по всем проектам → один объект за раз.",
                "• Автоулучшение промптов → не для v1.0.",
            ]),
        ]

        for section_title, items in recommendations:
            self.set_font("DejaVu", "B", 11)
            self.set_text_color(25, 25, 80)
            self.cell(0, 8, section_title)
            self.ln(10)
            self.set_font("DejaVu", "", 9)
            self.set_text_color(40, 40, 40)
            for item in items:
                self.set_x(self.l_margin + 4)
                self.multi_cell(self.w - self.l_margin - self.r_margin - 8, 5.5, item)
                self.ln(1)
            self.ln(4)

    def stats_page(self):
        """Quantitative summary"""
        self.add_page()
        self.section_title("Количественная сводка")

        stats = [
            ("Всего предложений Grok", "35 + 1 адаптация (веб-интерфейс) = 36"),
            ("Реализовано полностью", "3 (8%) — обработка ошибок, graceful degradation, Telegram WorkEntry"),
            ("Реализовано частично", "18 (50%) — HITL, дашборд, E2E, шаблоны, аудит, PDF, версионирование"),
            ("Не реализовано", "7 (19%) — веб-интерфейс, drag&drop, бэкапы, shadow mode, User Guide, шифрование, предпросмотр"),
            ("Отклонено (Rejected)", "8 (22%) — Electron, мобильное, 1С, видео, RBAC, ЭЦП, мульти-дашборд, авто-промпты"),
            ("Ближайшие действия (P0)", "6 задач, оценка: ~14 дней"),
            ("До пилота (P1)", "9 задач, оценка: ~20 дней"),
            ("После пилота (P2)", "13 задач, оценка: ~30 дней"),
            ("Общая оценка", "~64 человеко-дня до полного v14.0"),
        ]

        self.set_font("DejaVu", "", 9)
        for label, value in stats:
            self.set_text_color(25, 25, 80)
            self.set_font("DejaVu", "B", 9)
            self.cell(70, 7, label)
            self.set_font("DejaVu", "", 9)
            self.set_text_color(40, 40, 40)
            self.cell(0, 7, value)
            self.ln(8)

        self.ln(8)
        self.section_title("Текущее состояние кодовой базы")
        self.set_font("DejaVu", "", 9)
        self.set_text_color(40, 40, 40)

        code_stats = [
            "• 605 тестов (590 passed, 15 skipped) — 97.5% pass rate",
            "• 74 MCP инструмента, 7 агентов + PM + Auditor",
            "• 7 типов узлов Evidence Graph, 11 типов связей",
            "• 61 ловушка БЛС в 10 категориях",
            "• 33 типа работ в IDRequirementsRegistry",
            "• 5-этапный Journal Reconstructor с цветовой разметкой",
            "• 3-стадийный PD Analysis (spatial + completeness + LLM)",
            "• 4-шаговая гибридная проверка контрактов (pattern + semantic + LLM + RAG)",
            "• 12+ PDF-генераторов, ReportLab v3 (TrueType шрифты, 0 Type 3 bitmap)",
            "• 40+ Telegram-каналов мониторинга через TelegramScout",
            "• Model: DeepSeek V4 Pro[1M] (dev_linux) / Gemma 4 31B + Llama 3.3 70B (mac_studio)",
        ]
        for s in code_stats:
            self.cell(0, 6, s)
            self.ln(6)

    def rejected_rationale(self):
        """Rationale for rejected items"""
        self.add_page()
        self.section_title("Отклонённые предложения: обоснование")

        rejected = [
            ("1.1 Desktop-приложение (Electron/Tauri)",
             "Тяжёлый фреймворк (Chromium ~150MB). В антикризисном сценарии команда из 4 человек "
             "работает в одной комнате через локальный сервер. Локальный веб-интерфейс (Flask + HTML/JS) "
             "даёт тот же результат при в 10 раз меньшем объёме кода."),
            ("4.3 Видео-инструкции",
             "Команда из 4 человек проводит очное обучение (1 день) при развёртывании на объекте. "
             "Видео не добавляет ценности — система должна быть интуитивной."),
            ("5.2 Цифровая подпись (ЭЦП)",
             "В антикризисном сценарии документы распечатываются и подписываются физически "
             "на бумаге. ЭЦП требует интеграции с УЦ, что невозможно в offline-режиме на объекте."),
            ("5.3 Ролевая модель доступа (RBAC)",
             "4 человека работают в одной комнате, один Mac Studio. Физический контроль доступа. "
             "Единственный оператор за клавиатурой. Роли реализованы на уровне агентов, "
             "а не на уровне UI-доступа."),
            ("6.1 Дашборд по всем проектам",
             "Антикризисная операция: одна команда — один объект. Мульти-проектный дашборд "
             "потребуется на фазе эксплуатации (сопровождение нескольких объектов), "
             "не для v1.0."),
            ("7.2 Мобильное приложение",
             "Полевой ввод данных (WorkEntry от инженеров на объекте) покрывается "
             "Telegram-ботом. Мобильное приложение — избыточно для v1.0."),
            ("7.3 Интеграция с 1С и Смета.ру",
             "В антикризисном сценарии команда работает автономно. Обмен данными "
             "при необходимости — через CSV экспорт/импорт."),
            ("7.4 Автоулучшение промптов",
             "Требует накопления статистики (100+ confirmed lessons) для значимого "
             "улучшения. Не для v1.0. Схема LessonLearned готова для будущего использования."),
        ]

        for title, rationale in rejected:
            self.set_font("DejaVu", "B", 9)
            self.set_text_color(25, 25, 80)
            self.cell(0, 6, title)
            self.ln(7)
            self.set_font("DejaVu", "", 8)
            self.set_text_color(80, 80, 80)
            self.set_x(self.l_margin + 4)
            self.multi_cell(self.w - self.l_margin - self.r_margin - 8, 5, rationale)
            self.ln(4)


def main():
    pdf = GrokPDF()

    # --- Cover ---
    pdf.cover_page()

    # --- Executive recommendations ---
    pdf.recommendations_page()

    # --- Stats ---
    pdf.stats_page()

    # --- Summary matrix ---
    pdf.summary_matrix()

    # --- Detailed per-proposal pages, grouped by phase ---
    phases = {}
    for p in PROPOSALS:
        phase = p[1]
        phases.setdefault(phase, []).append(p)

    for phase_name, props in phases.items():
        pdf.add_page()
        pdf.section_title(phase_name)
        for prop in props:
            pid, _, proposal, status, evidence, priority, plan = prop
            pdf.proposal_block(pid, proposal, status, evidence, priority, plan)

    # --- Rejected rationale ---
    pdf.rejected_rationale()

    # --- Final page ---
    pdf.add_page()
    pdf.section_title("Заключение")
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(40, 40, 40)
    conclusion = (
        "Grok AI предоставил структурированную дорожную карту из 35 предложений по 7 фазам. "
        "После фильтрации через призму стратегической цели MAC_ASD (антикризисное восстановление ИД "
        "«под ключ» командой из 4 человек) и верификации каждого предложения по текущему коду:\n\n"
        "• 3 предложения уже полностью реализованы в коде (обработка ошибок, graceful degradation, "
        "Telegram WorkEntry).\n"
        "• 18 — частично реализованы и требуют доводки.\n"
        "• 7 — не реализованы (главный пробел: отсутствие UI).\n"
        "• 8 — осознанно отклонены как нецелесообразные для антикризисного сценария.\n\n"
        "КЛЮЧЕВОЙ ВЫВОД: Проект имеет мощный backend (74 MCP-инструмента, 605 тестов, 7 агентов), "
        "но нулевой фронтенд. Без веб-интерфейса команда операторов не сможет эффективно "
        "взаимодействовать с системой. Первоочередная задача — локальный веб-интерфейс "
        "(P0, ~14 дней) как «лицо» системы для антикризисной команды.\n\n"
        "После добавления UI система становится готовой к пилотному внедрению на реальном объекте."
    )
    pdf.multi_cell(0, 6, conclusion)

    # --- Save ---
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "Grok_ASD_Proposals.pdf")
    pdf.output(output_path)
    print(f"PDF saved: {output_path}")
    print(f"Pages: {pdf.page_no()}")
    return output_path


if __name__ == "__main__":
    main()
