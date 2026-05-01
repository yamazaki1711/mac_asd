"""Generate analysis report PDF for MAC ASD v12.0."""
import json as _json
from fpdf import FPDF

FONT_DIR = "C:/Windows/Fonts/"

class Report(FPDF):
    def __init__(self):
        super().__init__("P", "mm", "A4")
        self.add_font("Arial", "", FONT_DIR + "arial.ttf")
        self.add_font("Arial", "B", FONT_DIR + "arialbd.ttf")
        self.set_auto_page_break(True, 20)

    def header(self):
        self.set_font("Arial", "B", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, "MAC ASD v12.0 — Анализ проекта", align="R")
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

    def bullet(self, text, bold_prefix=""):
        self.set_font("Arial", "", 10)
        self.set_text_color(30, 30, 30)
        self.cell(6, 5.5, "•")
        if bold_prefix:
            self.set_font("Arial", "B", 10)
            self.cell(self.get_string_width(bold_prefix) + 1, 5.5, bold_prefix)
            self.set_font("Arial", "", 10)
        self.multi_cell(0, 5.5, text)
        self.ln(0.5)

    def metric(self, label, value, color=(30, 30, 30)):
        self.set_font("Arial", "B", 10)
        self.set_text_color(*color)
        self.cell(0, 6, f"{label}: {value}")
        self.ln(6)

    def section_sep(self):
        self.ln(2)
        self.set_draw_color(180, 180, 180)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def star_rating(self, stars):
        return "".join("★" * int(stars) + "☆" * (5 - int(stars)))


pdf = Report()
pdf.alias_nb_pages()
pdf.add_page()

# ── Title ──
pdf.doc_title("MAC ASD v12.0 — Полный анализ проекта")
pdf.body("Дата: 2 мая 2026 | Профиль: deepseek (dev) / mac_studio (prod) | Python 3.11+ | LangGraph")

pdf.section_sep()

# ── 1. Architecture ──
pdf.h1("1. Архитектура — оценка: ★★★★☆ (4/5)")

pdf.h2("Сильные стороны")
pdf.bullet("Чёткое разделение слоёв: agents/ (LangGraph), core/ (бизнес-логика), schemas/ (Pydantic), core/services/ (агенты-работники). Соответствует DDD-lite.", "")
pdf.bullet("Версионирование состояния: AgentState с schema_version и migrate_v1_to_v2() — грамотная эволюция схемы без breaking changes.", "")
pdf.bullet("Три профиля бэкендов: dev_linux (Ollama), mac_studio (MLX), deepseek (API) — переключение без изменения кода агентов через PROFILE_MODELS.", "")
pdf.bullet("PM-оркестрация: переход от статического HermesRouter к динамическому ProjectManager с WorkPlan/Workflow. Send() fan-out для параллельного исполнения независимых задач.", "")
pdf.bullet("3-стадийная модель принятия решений: Weighted Scoring → LLM Reasoning → Veto Engine — даёт скорость (быстрый путь) и глубину (LLM для серых зон).", "")

pdf.h2("Зоны роста")
pdf.bullet("Модульный кэш планов _plan_cache (nodes_v2.py:69) хранится в памяти процесса. При рестарте теряются все активные планы. Рекомендация: вынести WorkPlan в PostgreSQL.", "")
pdf.bullet("Синглтоны как глобальные переменные: llm_engine, pm_agent, ram_manager, journal_restorer, delo_agent. Затрудняет тестирование и будущую многопользовательскую поддержку. Рекомендация: DI-контейнер.", "")
pdf.bullet("Отсутствие абстракции хранилища: данные в PostgreSQL, NetworkX (in-memory), _plan_cache (in-memory), Artifact Store (файлы). Нет единого интерфейса StorageBackend.", "")

pdf.section_sep()

# ── 2. Code Quality ──
pdf.h1("2. Качество кода — оценка: ★★★☆☆ (3/5)")

pdf.h2("Сильные стороны")
pdf.bullet("Типизированные структуры данных: TypedDict для состояния, dataclass для доменных объектов, Pydantic для API-схем.", "")
pdf.bullet("Отказ от Dict[str, Any] в пользу VORResult, LegalResult, SmetaResult — улучшает читаемость и защиту от опечаток.", "")
pdf.bullet("Единый LLMEngine — все LLM-вызовы через один класс с автоматическим роутингом бэкендов.", "")

pdf.h2("Проблемы")
pdf.bullet("42 вхождения except Exception в src/ — маскирует баги, невозможно отличить сетевую ошибку от ошибки парсинга.", "except Exception: ")
pdf.bullet("9 вхождений голого except: без указания типа исключения (document_repository.py, delo_agent.py).", "Голый except: ")
pdf.bullet("7 TODO без тикетов в бэкендах и Google-интеграциях. Технический долг не трекается.", "TODO без тикетов: ")
pdf.bullet("import внутри функций: delo_agent.py:536 — import json as _json и from pathlib import Path as _Path в методе load_regulation_templates.", "Ленивые импорты: ")
pdf.bullet("Смешение sync/async: ram_manager синхронный, но вызывается из async-узлов LangGraph. Под нагрузкой может блокировать event loop.", "")

pdf.section_sep()

# ── 3. Tests ──
pdf.h1("3. Тесты — оценка: ★★★☆☆ (3/5)")

pdf.h2("Текущее состояние")
pdf.bullet("275 тестов: 244 passed, 16 failed, 15 skipped.", "")
pdf.bullet("9 test files, ~3 700 строк тестового кода.", "")
pdf.bullet("Хорошее покрытие decision engine (weighted scoring, veto rules).", "")
pdf.bullet("Слабое покрытие интеграционных сценариев и output-пайплайнов.", "")

pdf.h2("Зоны роста")
pdf.bullet("16 упавших тестов (~6.5% от общего числа). Каждый упавший тест теряет доверие и перестаёт быть сигналом.", "КРИТИЧНО: ")
pdf.bullet("Нет тестов на WorkPlan/TaskNode/get_parallel_ready_tasks() — критический код оркестрации без покрытия.", "")
pdf.bullet("Нет тестов на OutputPipeline — генерация DOCX (АОСР, реестры) без верификации.", "")
pdf.bullet("Нет тестов на JournalRestorer — восстановление журналов без покрытия.", "")
pdf.bullet("Нет property-based тестов. Для scoring engine можно использовать Hypothesis для проверки инвариантов.", "")

pdf.section_sep()

# ── 4. Security ──
pdf.h1("4. Безопасность — оценка: ★★★★☆ (4/5)")

pdf.body("Контекст: система локальная (Linux/Mac Studio), что снимает большинство OWASP-угроз.")
pdf.ln(2)
pdf.bullet(".env (3,666 bytes) отслеживается git. Необходимо проверить на наличие реальных ключей API.", "Проверить: ")
pdf.bullet("Дефолтные креды в config.py: POSTGRES_USER=oleg, POSTGRES_PASSWORD=asd_password. OK для dev, но в production должны быть переопределены через переменные окружения.", "")
pdf.bullet("Prompt injection risk: пользовательский task_description вставляется в LLM-промпты без санитизации. Низкий риск для локального использования, критично для будущего SaaS.", "")

pdf.section_sep()

# ── 5. Performance ──
pdf.h1("5. Производительность — оценка: ★★★★☆ (4/5)")

pdf.h2("Сильные стороны")
pdf.bullet("Send() параллельное исполнение: независимые задачи запускаются параллельно через LangGraph fan-out.", "")
pdf.bullet("RAM throttling: max_parallel адаптируется под память (WARNING → 2, CRITICAL → 1).", "")
pdf.bullet("Кэширование: cachetools.TTLCache для LLM-ответов, _plan_cache для планов.", "")
pdf.bullet("In-process cache вместо Redis: правильное решение для single-user, экономия 2GB RAM.", "")

pdf.h2("Зоны роста")
pdf.bullet("Нет кэширования эмбеддингов: каждый вызов llm_engine.embed() идёт в модель. Для bge-m3 можно закэшировать частые тексты.", "")
pdf.bullet("Нет батчинга LLM-запросов: несколько агентов на общей Gemma 4 31B делают последовательные запросы. Можно группировать смежные запросы.", "")

pdf.section_sep()

# ── 6. Tech Debt ──
pdf.h1("6. Технический долг")

pdf.body("Ключевые элементы, требующие внимания:")
pdf.ln(2)

# Simulate a table with aligned text
items = [
    ("Vision DeepSeek", "deepseek_backend.py:186", "До Mac Studio"),
    ("Google Workspace", "integrations/google.py", "По требованию"),
    ("MLX backend — заглушки", "mlx_backend.py:61,115,151", "До Mac Studio"),
    ("9× except Exception", "document_repository.py", "ASAP"),
    ("9× except Exception", "is_generator/dxf_parser.py", "ASAP"),
]
for item, loc, deadline in items:
    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(55, 6.5, item)
    pdf.set_font("Arial", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(70, 6.5, loc)
    pdf.set_font("Arial", "B", 9)
    if deadline == "ASAP":
        pdf.set_text_color(180, 40, 40)
    else:
        pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6.5, deadline)
    pdf.ln(6.5)

pdf.section_sep()

# ── 7. Recommendations ──
pdf.h1("7. Рекомендации (приоритизированные)")

pdf.h2("Критические — неделя 1")
pdf.bullet("Запустить pytest tests/ -v --tb=long, зафиксировать причины 16 падений, починить. Нельзя держать красный CI.", "1. Починить 16 упавших тестов. ")
pdf.bullet("Заменить except Exception на NetworkError, ParseError, AuthError в document_repository.py (9 шт.).", "2. Конкретные типы исключений. ")
pdf.bullet("Проверить git log -- .env на наличие реальных ключей API. Если есть — ротировать, добавить .env в .gitignore.", "3. Аудит .env. ")

pdf.h2("Важные — недели 2-3")
pdf.bullet("WorkPlan → таблица work_plans, TaskNode → plan_tasks. Позволит переживать рестарты.", "4. _plan_cache в БД. ")
pdf.bullet("Заменить синглтоны на DI-контейнер. Упростит тестирование и подготовит к многопользовательскому режиму.", "5. DI-контейнер. ")
pdf.bullet("WorkPlan, JournalRestorer, OutputPipeline — ядро ценности системы без покрытия.", "6. Тесты на критический код. ")
pdf.bullet("Вынести в src/utils/json_utils.py, использовать во всех агентах.", "7. Унифицировать _extract_json(). ")

pdf.h2("Желательные — месяц 1")
pdf.bullet("Промпты — это интерфейс к LLM. Автоматизировать проверку формата ответа при смене модели.", "8. Контрактное тестирование LLM-промптов. ")
pdf.bullet("LRU-кэш для llm_engine.embed() с ключом по hash(text).", "9. Кэширование эмбеддингов. ")
pdf.bullet("Перейти на structlog или python-json-logger для machine-readable логов.", "10. Структурированное логирование. ")
pdf.bullet("pyproject.toml уже настроен. Прогнать mypy src/ и постепенно фиксить ошибки.", "11. mypy в CI. ")

pdf.section_sep()

# ── 8. Maturity Matrix ──
pdf.h1("8. Матрица зрелости")

matrix = [
    ("Архитектура", "4/5", "Зрелая, с заделом на будущее"),
    ("Качество кода", "3/5", "Хорошие паттерны, слабая обработка ошибок"),
    ("Тесты", "3/5", "Хороший старт, 16 failures и пробелы в покрытии"),
    ("Безопасность", "4/5", "ОК для локальной, нужна санитизация промптов"),
    ("Документация", "5/5", "Отличный README, agents.md, 9 docs/ файлов"),
    ("Технический долг", "3/5", "Управляемый, но есть явные TODO без тикетов"),
]

for dim, score, comment in matrix:
    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(40, 7, dim)
    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(20, 60, 120)
    pdf.cell(15, 7, score)
    pdf.set_font("Arial", "", 9)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 7, comment)
    pdf.ln(7)

pdf.ln(4)
pdf.set_font("Arial", "B", 12)
pdf.set_text_color(20, 60, 120)
pdf.cell(0, 8, "Общая оценка: 3.5/5 — Крепкий production-grade фундамент, требует шлифовки")
pdf.ln(14)

pdf.set_font("Arial", "", 9)
pdf.set_text_color(120, 120, 120)
pdf.cell(0, 6, "Сгенерировано автоматически Claude Code | 2 мая 2026 | MAC ASD v12.0")

# ── Output ──
output_path = "C:/MAC_ASD/report_02052026.pdf"
pdf.output(output_path)
print(f"PDF saved: {output_path}")
print(f"Pages: {pdf.page_no()}")
