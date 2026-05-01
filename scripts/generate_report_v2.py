"""Generate system-level analysis report PDF for MAC ASD v12.0."""
from fpdf import FPDF

FONT_DIR = "C:/Windows/Fonts/"

class Report(FPDF):
    def __init__(self):
        super().__init__("P", "mm", "A4")
        self.add_font("Arial", "", FONT_DIR + "arial.ttf")
        self.add_font("Arial", "B", FONT_DIR + "arialbd.ttf")
        self.add_font("Arial", "BI", FONT_DIR + "arialbi.ttf")
        self.set_auto_page_break(True, 20)

    def header(self):
        self.set_font("Arial", "B", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, "MAC ASD v12.0 — Системный анализ", align="R")
        self.ln(10)

    def footer(self):
        self.set_y(-18)
        self.set_font("Arial", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Страница {self.page_no()}/{{nb}}", align="C")

    def doc_title(self, text):
        self.set_font("Arial", "B", 18)
        self.set_text_color(20, 60, 120)
        self.cell(0, 12, text)
        self.ln(16)

    def h1(self, text):
        self.ln(4)
        self.set_font("Arial", "B", 14)
        self.set_text_color(20, 60, 120)
        self.cell(0, 10, text)
        self.ln(10)

    def h2(self, text):
        self.ln(2)
        self.set_font("Arial", "B", 11)
        self.set_text_color(40, 80, 140)
        self.cell(0, 8, text)
        self.ln(8)

    def body(self, text):
        self.set_font("Arial", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def bullet(self, text):
        self.set_font("Arial", "", 10)
        self.set_text_color(30, 30, 30)
        self.cell(6, 5.5, "•")
        self.multi_cell(0, 5.5, text)
        self.ln(0.5)

    def bullet_pair(self, bold_text, text):
        self.set_font("Arial", "", 10)
        self.set_text_color(30, 30, 30)
        self.cell(6, 5.5, "•")
        self.set_font("Arial", "B", 10)
        bw = self.get_string_width(bold_text) + 1
        self.cell(bw, 5.5, bold_text)
        self.set_font("Arial", "", 10)
        self.multi_cell(0, 5.5, text)
        self.ln(0.5)

    def verdict_box(self, title, lines, color):
        self.set_fill_color(*color)
        self.ln(1)
        self.set_font("Arial", "B", 11)
        self.set_text_color(255, 255, 255)
        self.cell(0, 8, f"  {title}", fill=True)
        self.ln(9)
        self.set_text_color(30, 30, 30)
        for line in lines:
            self.set_font("Arial", "", 10)
            self.bullet(line)
        self.ln(2)

    def section_sep(self):
        self.ln(2)
        self.set_draw_color(180, 180, 180)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def table_row(self, cells, widths, bold=False):
        style = "B" if bold else ""
        for text, w in zip(cells, widths):
            self.set_font("Arial", style, 9)
            self.cell(w, 6, text, border=0)
        self.ln(6)

    def rating_bar(self, label, pct, color):
        self.set_font("Arial", "B", 10)
        self.set_text_color(30, 30, 30)
        self.cell(45, 6, label)
        bar_w = 80
        self.set_fill_color(230, 230, 230)
        self.rect(self.get_x(), self.get_y(), bar_w, 5, style="F")
        fill_w = bar_w * pct / 100
        self.set_fill_color(*color)
        self.rect(self.get_x(), self.get_y(), fill_w, 5, style="F")
        self.set_x(self.get_x() + bar_w + 3)
        self.set_font("Arial", "", 9)
        self.cell(0, 6, f"{pct:.0f}%")
        self.ln(7)


pdf = Report()
pdf.alias_nb_pages()
pdf.add_page()

# =============================================================================
# TITLE PAGE
# =============================================================================
pdf.doc_title("MAC ASD v12.0")
pdf.set_font("Arial", "B", 13)
pdf.set_text_color(40, 80, 140)
pdf.cell(0, 8, "Системный анализ проекта")
pdf.ln(14)

pdf.body("Дата: 2 мая 2026 | Профиль: deepseek (dev) / mac_studio (prod)")
pdf.body("Мультиагентная система на базе LLM для строительного документооборота.")

pdf.section_sep()

# =============================================================================
# EXECUTIVE SUMMARY
# =============================================================================
pdf.h1("Резюме")

pdf.body(
    "Проект MAC ASD v12.0 — это не просто набор агентов, а два "
    "параллельных пайплайна с разной степенью готовности."
)
pdf.ln(1)
pdf.body(
    "Первый — Forensic E2E — работает и протестирован: "
    "сканы → OCR → классификация → извлечение сущностей → NetworkX-граф "
    "→ форензик-проверки → задания оператору → DOCX-генерация. "
    "Это готовый инструмент для аудита ИД."
)
pdf.ln(1)
pdf.body(
    "Второй — LangGraph Agent Pipeline — находится в активной "
    "разработке: PM-оркестрация с параллельным Send() fan-out, "
    "агенты с RAG-инъекцией уроков, генерация протоколов "
    "разногласий и исков. Сейчас этот пайплайн "
    "не имеет ни одного E2E-теста и запускается "
    "только через main.py с plain-dict состоянием "
    "вместо AgentState v2.0."
)
pdf.ln(1)
pdf.body(
    "Ключевая проблема: существуют два конкурирующих "
    "механизма оркестрации — статический "
    "hermes_node (nodes.py) и PM-драйвер (nodes_v2.py). "
    "База знаний PTO работает локально "
    "(как и задумано), онлайн-скрапер удалён."
)

pdf.section_sep()

# =============================================================================
# 1. SYSTEM ARCHITECTURE — WIRING MAP
# =============================================================================
pdf.h1("1. Архитектура: карта реальных связей")

pdf.body(
    "Ниже — не диаграмма из README, "
    "а то, что реально подключено и работает."
)

pdf.h2("Pipeline A: Forensic E2E (работает, протестирован)")
pdf.verdict_box("Статус: ГОТОВО", [
    "IngestionPipeline → сканирование + OCR + классификация (18 типов документов)",
    "HybridClassifier: keyword + LLM fallback + Guidance System",
    "GraphService (NetworkX): документы → партии → сертификаты → АОСР",
    "Auditor: 4 оси проверки (документарная/количественная/темпоральная/нормативная)",
    "OutputPipeline: генерация DOCX АОСР по 344/пр",
    "test_e2e_forensic.py: сквозной тест с реальным сценарием (Шпунт Л5)",
], (30, 130, 60))

pdf.h2("Pipeline B: LangGraph Agent Pipeline (в разработке)")
pdf.verdict_box("Статус: В РАЗРАБОТКЕ", [
    "PM Planning Node → создаёт WorkPlan через LLM (или fallback-шаблон)",
    "PM Fan-Out Router → Send() параллельное исполнение независимых задач",
    "Agent Worker Nodes → вызывают те же функции из nodes.py с RAG-инъекцией",
    "PM Evaluate Node → оценка результатов, accept/retry/abort/replan",
    "НЕТ E2E-тестов: нельзя подтвердить, что параллельный граф корректно завершается",
    "НЕТ тестов на pm_fan_out_router или pm_evaluate_node",
], (200, 140, 40))

pdf.h2("Пересечения и дублирование")

pdf.bullet_pair(
    "Два движка вердиктов: ",
    "hermes_node (nodes.py) и pm_evaluate_node (nodes_v2.py) "
    "оба вычисляют weighted score + veto + zone. "
    "hermes_node использует статический маршрут "
    "(archive→procurement→pto→smeta→legal→logistics), "
    "pm_evaluate_node — динамический из WorkPlan. "
    "Второй должен заменить первый, но оба живы."
)
pdf.bullet_pair(
    "Две версии графа: ",
    "asd_app (параллельный) и asd_app_sequential "
    "(последовательный). Последовательный "
    "использует agent_executor_node и pm_dispatch_router, "
    "параллельный — agent_worker_node и pm_fan_out_router. "
    "Оба компилируются и экспортируются."
)
pdf.bullet_pair(
    "Два способа создания состояния: ",
    "create_initial_state() в state.py создаёт полное "
    "AgentState v2.0. main.py создаёт plain dict без половины "
    "полей (work_plan, compliance_delta, completed_task_ids, parallel_results...). "
    "Фактически main.py — мёртвый код, "
    "который упадёт при первом же запуске "
    "на реальном графе."
)

pdf.section_sep()

# =============================================================================
# 2. KNOWLEDGE BASE & INTEGRATIONS
# =============================================================================
pdf.h1("2. База знаний и интеграции")

pdf.h2("Локальная база знаний PTO (работает)")

pdf.body(
    "Источник данных: вручную скачанные DOCX-чеклисты "
    "с id-prosto.ru, конвертированные в JSON "
    "(data/knowledge/idprosto_worktype_docs.json)."
)
pdf.bullet("31 вид работ, 569 маппингов документов, 356+ нормативных ссылок")
pdf.bullet("IdProstoLoader: fuzzy-поиск по 150+ compound-шаблонам (напр. \"буронабивные сваи\" → 05_bored-piles)")
pdf.bullet("TemplateRegistry: 149 DOCX-шаблонов из 39 пакетов форм")
pdf.bullet("InvalidationEngine: проверка актуальности нормативных ссылок")
pdf.body("")
pdf.bullet_pair(
    "Важно: ",
    "это локальный загрузчик JSON-файла, "
    "а не онлайн-клиент. Название "
    "\"idprosto_loader\" отражает источник данных, "
    "не способ интеграции. "
    "Онлайн-скрапер (удалённый "
    "id_prosto_client.py) был ненужным дубликатом."
)

pdf.h2("Интеграции (все локальные или бесплатные)")

pdf.bullet_pair("TelegramScout: ", "ингест сообщений из Telegram-каналов (через Telethon)")
pdf.bullet_pair("GeoContextService: ", "Яндекс.Геокодер (бесплатно) + Open-Meteo (бесплатно) — погода, климат, координаты")
pdf.bullet_pair("Google Workspace: ", "интеграция с почтой/документами (по требованию)")

pdf.section_sep()

# =============================================================================
# 3. DEAD CODE & CONTRADICTIONS
# =============================================================================
pdf.h1("3. Мёртвый код и противоречия")

pdf.h2("Что не подключено")

pdf.table_row(
    ["Компонент", "Файл", "Проблема"],
    [55, 55, 80], bold=True
)
pdf.table_row(
    ["Reflection Node", "nodes.py:1296", "Нет в графе — мёртвый код"],
    [55, 55, 80]
)
pdf.table_row(
    ["Legal Docs Gen", "nodes.py:746-879", "Протокол/претензия/иск — нет в графе"],
    [55, 55, 80]
)
pdf.table_row(
    ["VOR/PD/AОСР tools", "pto_tools.py:481-511", "Возвращают mock-данные"],
    [55, 55, 80]
)
pdf.table_row(
    ["hermes_node", "nodes.py:259", "Дублирует pm_evaluate_node"],
    [55, 55, 80]
)
pdf.table_row(
    ["asd_app_sequential", "workflow.py:89", "Легаси-граф, не нужен после полного перехода на parallel"],
    [55, 55, 80]
)
pdf.table_row(
    ["main.py", "main.py", "Создаёт plain-dict без полей AgentState v2.0"],
    [55, 55, 80]
)

pdf.h2("Что удалено в этой итерации")

pdf.bullet("id_prosto_client.py (~700 строк) — онлайн-скрапер SaaS, противоречивший идеологии локальной установки")
pdf.bullet("4 настройки в config.py: ID_PROSTO_LOGIN/PASSWORD/COOKIES + TWOCAPTCHA_API_KEY")
pdf.bullet("2 MCP-инструмента: asd_id_search, asd_id_download (единственные потребители IdProstoClient)")
pdf.bullet("4 переменные окружения в .env.example")
pdf.bullet("Ссылки на id-prosto.ru в PTO_Rules.md и generate_report.py")

pdf.section_sep()

# =============================================================================
# 4. TESTS
# =============================================================================
pdf.h1("4. Тесты: системный взгляд")

pdf.h2("Покрытие по компонентам")

pdf.rating_bar("Решающий движок", 95, (30, 130, 60))
pdf.rating_bar("WorkPlan/TaskNode", 90, (30, 130, 60))
pdf.rating_bar("Юридический анализ", 75, (180, 160, 30))
pdf.rating_bar("RAG Pipeline", 70, (180, 160, 30))
pdf.rating_bar("Ингест-пайплайн", 65, (180, 160, 30))
pdf.rating_bar("LangGraph граф (интеграционно)", 5, (200, 60, 40))
pdf.rating_bar("Output Pipeline", 10, (200, 60, 40))
pdf.rating_bar("Journal Restorer", 10, (200, 60, 40))
pdf.rating_bar("IS Generator (DXF)", 40, (200, 60, 40))
pdf.rating_bar("PPR Generator", 30, (200, 60, 40))

pdf.h2("Чего не хватает")

pdf.bullet("Нет ни одного теста на узлы LangGraph: pm_planning_node, pm_fan_out_router, agent_worker_node, pm_evaluate_node")
pdf.bullet("Нет теста на параллельное исполнение с Send() fan-out")
pdf.bullet("Нет теста на сквозной проход графа с моками LLM")
pdf.bullet("Нельзя проверить, что WorkPlan корректно проходит весь цикл: planning → dispatch → execute → evaluate → complete")
pdf.bullet("WorkPlan и TaskNode покрыты отлично (36 тестов), но изолированно от графа")

pdf.section_sep()

# =============================================================================
# 5. CODE QUALITY — EXCEPTION HANDLING
# =============================================================================
pdf.h1("5. Качество кода")

pdf.h2("Обработка исключений")

pdf.body(
    "После удаления id_prosto_client.py (15 broad except) "
    "и замены в document_repository.py (8 → ImportError/OSError) "
    "и dxf_parser.py (14 → OSError/ValueError/KeyError/AttributeError) ситуация "
    "улучшилась, но остаётся проблема:"
)

pdf.bullet_pair(
    "nodes.py: ",
    "большинство агентов имеют try/except Exception вокруг JSON-парсинга и LLM-вызовов. "
    "Это оправдано на границе с LLM, но должно использовать LLMResponseError."
)
pdf.bullet_pair(
    "nodes_v2.py и nodes.py: ",
    "общие try/except Exception в агентах маскируют ошибки конфигурации и сетевые сбои."
)
pdf.bullet_pair(
    "Созданный модуль exceptions.py: ",
    "содержит доменные исключения, но пока не используется в nodes.py или nodes_v2.py. "
    "Это инфраструктура без потребителей."
)

pdf.h2("Типизация и стиль")

pdf.bullet_pair("Python 3.8 совместимость: ", "List[X] вместо list[X], Tuple вместо tuple — поправлено в is_generator/schemas.py")
pdf.bullet_pair("Pydantic V2: ", "используется в схемах, но несколько моделей используют устаревший class Config вместо ConfigDict (3 warnings)")
pdf.bullet_pair("AgentState v2.0: ", "хорошо спроектирован — версионирование, миграция, audit trail, rollback. Но не используется в main.py.")

pdf.section_sep()

# =============================================================================
# 6. PM AGENT & ORCHESTRATION
# =============================================================================
pdf.h1("6. PM-оркестрация")

pdf.h2("Что работает")

pdf.bullet("WorkPlan + TaskNode: полноценная модель с dependency resolution, parallel-ready отбором, retry, priority ordering")
pdf.bullet("ProjectManager.dispatch(): выбирает следующую готовую задачу из WorkPlan")
pdf.bullet("evaluate_result_sync(): быстрый путь оценки без LLM — accept/retry/abort по confidence threshold")
pdf.bullet("pm_fan_out_router: Send() fan-out для параллельных задач с учётом RAM-статуса")
pdf.bullet("Fallback-планы: два шаблона для lot_search и construction_support без LLM")

pdf.h2("Что не подключено")

pdf.bullet("LLM-путь оценки (grey zone): evaluate_result может обращаться к LLM, но этот код не протестирован")
pdf.bullet("replan(): PM может адаптировать план после ошибок, но это не протестировано")
pdf.bullet("Хранение планов: только in-memory _plan_cache (теряется при рестарте)")

pdf.section_sep()

# =============================================================================
# 7. MODEL STRATEGY
# =============================================================================
pdf.h1("7. Стратегия моделей")

pdf.body(
    "Продакшен-таргет (не текущая реальность): "
    "Mac Studio M4 Max 128GB с Llama 3.3 70B 4-bit (PM, ~40GB) + Gemma 4 31B 4-bit "
    "(общая для 5 агентов, ~23GB) + Gemma 4 E4B 4-bit "
    "(делопроизводитель, ~3GB). Всего 66.3GB RAM под модели."
)

pdf.body(
    "Текущая реальность: DeepSeek API "
    "(как временный мост до Mac Studio). "
    "DeepSeek-chat для всех агентов, "
    "deepseek-reasoner для PM. Эмбеддинги через Ollama bge-m3."
)

pdf.h2("Проблемы")

pdf.bullet("MLX-бэкенд содержит заглушки для нескольких методов (generate, embed) — нельзя проверить работу на Mac Studio до получения железа")
pdf.bullet("DeepSeek Vision не поддерживается — техдолг. Вместо него используется Ollama minicpm-v")
pdf.bullet("Общая модель для 5 агентов (Gemma 4 31B) — это правильно для RAM, но требует очереди запросов. Это не реализовано в текущем коде.")

pdf.section_sep()

# =============================================================================
# 8. PRIORITY ROADMAP
# =============================================================================
pdf.h1("8. Дорожная карта")

pdf.h2("Неделя 1 — Критическое")

pdf.table_row(
    ["#", "Задача", "Статус"],
    [8, 120, 60], bold=True
)
pdf.table_row(
    ["1", "Написать E2E-тест для параллельного графа с моками LLM", "Срочно"],
    [8, 120, 60]
)
pdf.table_row(
    ["2", "Переписать main.py через create_initial_state()", "Срочно"],
    [8, 120, 60]
)
pdf.table_row(
    ["3", "Удалить или пометить deprecated hermes_node и asd_app_sequential", "Срочно"],
    [8, 120, 60]
)
pdf.table_row(
    ["4", "Подключить доменные исключения к nodes.py и nodes_v2.py", "Выполнено частично"],
    [8, 120, 60]
)

pdf.h2("Недели 2-3 — Важное")

pdf.table_row(
    ["5", "Интеграционные тесты графа с моками LLM (pm_planning → evaluate)", "Необходимо"],
    [8, 120, 60]
)
pdf.table_row(
    ["6", "Тесты для OutputPipeline, JournalRestorer, IS Generator", "Необходимо"],
    [8, 120, 60]
)
pdf.table_row(
    ["7", "Подключить Legal Doc Gen (protocol/claim/lawsuit) к графу", "Необходимо"],
    [8, 120, 60]
)
pdf.table_row(
    ["8", "Удалить или реализовать Reflection Node", "Решение"],
    [8, 120, 60]
)
pdf.table_row(
    ["9", "WorkPlan persistence в PostgreSQL", "Отложено"],
    [8, 120, 60]
)

pdf.h2("Месяц 2 — Улучшения")

pdf.table_row(
    ["10", "DI-контейнер вместо синглтонов", "Отложено"],
    [8, 120, 60]
)
pdf.table_row(
    ["11", "Очередь запросов к общей модели (5 агентов → 1 модель)", "Отложено"],
    [8, 120, 60]
)
pdf.table_row(
    ["12", "Property-based тесты для scoring engine (Hypothesis)", "Отложено"],
    [8, 120, 60]
)
pdf.table_row(
    ["13", "Переход на ConfigDict в Pydantic-моделях", "Отложено"],
    [8, 120, 60]
)

pdf.section_sep()

# =============================================================================
# 9. VERDICT
# =============================================================================
pdf.h1("9. Итоговая оценка")

pdf.body(
    "Проект находится на стадии активной разработки "
    "с частично работающим продуктом. "
    "Сильные стороны: архитектура "
    "(чёткое разделение слоёв, "
    "версионирование состояния), "
    "Forensic E2E пайплайн (полностью "
    "работает), PM оркестрация "
    "(продумана, хорошо покрыта тестами), "
    "база знаний PTO (полноценная, локальная)."
)
pdf.ln(2)
pdf.body(
    "Главный риск: нет ни одного "
    "интеграционного теста LangGraph-графа. "
    "Параллельный граф с Send() fan-out "
    "сложен и ошибки в нём будут "
    "трудно отлаживать. "
    "Первый приоритет — написать "
    "E2E-тест с моками LLM, который "
    "подтвердит, что граф "
    "проходит полный цикл: "
    "planning → dispatch → execute → evaluate → complete."
)
pdf.ln(2)
pdf.body(
    "Второй приоритет — удалить "
    "дублирующий код (hermes_node, asd_app_sequential) "
    "и переписать main.py через create_initial_state(). "
    "Это уберёт путаницу для "
    "будущих разработчиков."
)

pdf.ln(3)

# Progress chart
pdf.h2("Прогресс по слоям")

pdf.rating_bar("Forensic E2E Pipeline", 90, (30, 130, 60))
pdf.rating_bar("PM Agent (чистые функции)", 85, (30, 130, 60))
pdf.rating_bar("База знаний PTO", 85, (30, 130, 60))
pdf.rating_bar("Схемы (Pydantic)", 80, (30, 130, 60))
pdf.rating_bar("LangGraph Граф (интеграционно)", 25, (200, 140, 40))
pdf.rating_bar("Доступ к данным (БД + RAG)", 55, (180, 160, 30))
pdf.rating_bar("Генерация документов", 50, (180, 160, 30))

pdf.ln(6)
pdf.set_font("Arial", "", 8)
pdf.set_text_color(150, 150, 150)
pdf.cell(0, 5, "Сгенерировано 2 мая 2026 | MAC ASD v12.0 | Claude Code", align="C")

# Save
out = "C:/MAC_ASD/report_02052026.pdf"
pdf.output(out)
print(f"Report saved to {out}")
