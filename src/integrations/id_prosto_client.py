"""
MAC_ASD v12.0 — id-prosto.ru Авторизованный Клиент

Методы авторизации:
  1. Cookie-передача (основной) — используется готовая сессия
  2. 2Captcha API (fallback) — автоматическое разгадывание капчи
  3. agent-browser CLI (резерв) — браузерная автоматизация

Использование:
  from src.integrations.id_prosto_client import IdProstoClient

  # Способ 1: через cookies
  client = IdProstoClient(cookies={"session_id": "..."})

  # Способ 2: через логин/пароль + 2Captcha
  client = IdProstoClient(
      login="user@example.com",
      password="secret",
      twocaptcha_api_key="abc123..."
  )

  # Скачивание шаблонов
  templates = client.get_category("earth")
  pdf_bytes = client.download_pdf(url="https://id-prosto.ru/...")

  # Поиск по базе
  results = client.search(query="АОСР бетонирование фундамента")
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Константы
# ──────────────────────────────────────────────
BASE_URL = "https://id-prosto.ru"
LOGIN_URL = f"{BASE_URL}/auth/login"
LISTS_URL = f"{BASE_URL}/lists"
FORMS_URL = f"{BASE_URL}/forms"
EXAMPLES_URL = f"{BASE_URL}/examples"
PROJECTS_URL = f"{BASE_URL}/projects"
FAQ_URL = f"{BASE_URL}/faq"

# ═══════════════════════════════════════════════
# Яндекс SmartCaptcha (НЕ reCAPTCHA!)
# ═══════════════════════════════════════════════
SMARTCAPTCHA_SITEKEY = "ysc1_MyTawGAah44rcHpuIRcS9W2HMgervcCgVVHhQZKm3668a2e9"
SMARTCAPTCHA_JS_URL = "https://smartcaptcha.cloud.yandex.ru/captcha.js?render=onload&onload=__onSmartCaptchaReady"

# ═══════════════════════════════════════════════
# Карта сайта (результаты разведки 2026-04-21)
# ═══════════════════════════════════════════════

# Категории перечней ИД (31 раздел — /lists/{slug})
LIST_CATEGORIES = [
    {"slug": "permit", "name": "Разрешительная документация"},
    {"slug": "geodethic", "name": "Геодезические работы"},
    {"slug": "earth", "name": "Земляные работы"},
    {"slug": "piles", "name": "Свайные работы"},
    {"slug": "bored-piles", "name": "Буровые сваи"},
    {"slug": "concrete", "name": "Бетонные работы"},
    {"slug": "precast-concrete", "name": "Сборные ЖБК"},
    {"slug": "steel", "name": "Металлические конструкции"},
    {"slug": "demolition", "name": "Демонтаж"},
    {"slug": "anticorrosive", "name": "Антикоррозийная защита"},
    {"slug": "drilling", "name": "Бурение"},
    {"slug": "extelectric", "name": "Наружное электроснабжение"},
    {"slug": "electric", "name": "Электромонтажные работы"},
    {"slug": "elevators", "name": "Лифты"},
    {"slug": "equipment", "name": "Технологическое оборудование"},
    {"slug": "extinguishing", "name": "Пожаротушение"},
    {"slug": "extsewerage", "name": "Наружная канализация"},
    {"slug": "extwatersupply", "name": "Наружное водоснабжение"},
    {"slug": "finishing-works", "name": "Отделочные работы"},
    {"slug": "fire-alarm", "name": "Пожарная сигнализация"},
    {"slug": "heat-pipelines", "name": "Тепловые сети"},
    {"slug": "heating", "name": "Отопление"},
    {"slug": "intsewerage", "name": "Внутренняя канализация"},
    {"slug": "intwatersupply", "name": "Внутреннее водоснабжение"},
    {"slug": "pipelines", "name": "Трубопроводы"},
    {"slug": "roads", "name": "Дорожные работы"},
    {"slug": "sks", "name": "Структурированные кабельные системы"},
    {"slug": "steam-boiler", "name": "Паровые котлы"},
    {"slug": "tanks", "name": "Резервуары"},
    {"slug": "ventilation", "name": "Вентиляция"},
    {"slug": "automatic", "name": "Автоматика"},
]

# Разделы форм ИД (39 разделов — /forms/{slug})
FORM_SECTIONS = [
    {"slug": "344pr", "name": "Приказ Минстроя №344/пр (АОСР, АООК, АОИС)"},
    {"slug": "1026pr", "name": "Приказ Минстроя №1026/пр (Общий журнал работ)"},
    {"slug": "sp-48-13330", "name": "СП 48.13330.2019 Организация строительства"},
    {"slug": "sp-126-13330", "name": "СП 126.13330.2017 Геодезические работы"},
    {"slug": "sp-129-13330", "name": "СП 129.13330.2019 Наружные сети"},
    {"slug": "sp-45-13330", "name": "СП 45.13330.2017 Земляные сооружения"},
    {"slug": "sp-70-13330", "name": "СП 70.13330.2012 Несущие и ограждающие"},
    {"slug": "sp-71-13330", "name": "СП 71.13330.2017 Отделочные работы"},
    {"slug": "sp-72-13330", "name": "СП 72.13330.2016 Антикоррозийная защита"},
    {"slug": "sp-73-13330", "name": "СП 73.13330.2016 Внутренние системы"},
    {"slug": "sp-74-13330", "name": "СП 74.13330.2016 Наружные сети связи"},
    {"slug": "sp-76-13330", "name": "СП 76.13330.2016 Электроустановки"},
    {"slug": "sp-77-13330", "name": "СП 77.13330.2016 Автоматизация"},
    {"slug": "sp-341-1325800", "name": "СП 341.1325800 Сваи"},
    {"slug": "sp-365-1325800", "name": "СП 365.1325800 Резервуары"},
    {"slug": "sp-392-1325800", "name": "СП 392.1325800 Земляные работы"},
    {"slug": "sp-399-1325800", "name": "СП 399.1325800 Дорожные работы"},
    {"slug": "sp-412-1325800", "name": "СП 412.1325800 Демонтаж"},
    {"slug": "sp-520-1325800", "name": "СП 520.1325800 Тепловые сети"},
    {"slug": "sp-543-1325800", "name": "СП 543.1325800 Приемка в эксплуатацию"},
    {"slug": "sp-336-1325800", "name": "СП 336.1325800 Лифты"},
    {"slug": "sp-347-1325800", "name": "СП 347.1325800 Автоматизация"},
    {"slug": "sp-42-101-2003", "name": "СП 42-101-2003 Газораспределение"},
    {"slug": "sp-40-102-2000", "name": "СП 40-102-2000 Водоснабжение"},
    {"slug": "sp-68-13330", "name": "СП 68.13330.2017 Металлические конструкции"},
    {"slug": "gost-32569", "name": "ГОСТ 32569 Трубопроводы"},
    {"slug": "gost-22845", "name": "ГОСТ 22845 Сваи"},
    {"slug": "gost-23118", "name": "ГОСТ 23118 Стальные конструкции"},
    {"slug": "gost-59638", "name": "ГОСТ Р 59604.3 Сварка"},
    {"slug": "gost-59639", "name": "ГОСТ Р 59604.4 Материалы сварочные"},
    {"slug": "gost-r-59492", "name": "ГОСТ Р 59492 Бетонные работы"},
    {"slug": "i-1-13-07", "name": "И 1-13-07 Электромонтаж"},
    {"slug": "rd-11-02-2006", "name": "РД 11-02-2006 Состав ИД"},
    {"slug": "rd-11-05-2007", "name": "РД 11-05-2007 Журналы работ"},
    {"slug": "rd-45-156-2000", "name": "РД 45.156-2000 Кабельные линии"},
    {"slug": "rtn-pr8", "name": "РТН Пр-8 Подъёмные сооружения"},
    {"slug": "snip-42-01-2002", "name": "СНиП 42-01-2002 Газораспределение"},
    {"slug": "vsn-012", "name": "ВСН 012-88 Строительство трубопроводов"},
    {"slug": "vsn-478", "name": "ВСН 478-86 Электромонтаж"},
]

# Разделы примеров оформления (18 разделов — /examples/{slug})
EXAMPLE_SECTIONS = [
    "344-pr", "1026-pr", "gost-32569", "i-1-13-07",
    "rd-11-02-2006", "sp-126-13330", "sp-129-13330",
    "sp-341-1325800", "sp-365-1325800", "sp-392-1325800",
    "sp-45-13330", "sp-48-13330", "sp-543-1325800",
    "sp-70-13330", "sp-71-13330", "sp-72-13330",
    "sp-73-13330", "sp-76-13330",
]

# Для обратной совместимости
CATEGORIES = [c["slug"] for c in LIST_CATEGORIES]

# Страницы сайта
SITE_PAGES = {
    "main": "/",
    "lists": "/lists",
    "forms": "/forms",
    "examples": "/examples",
    "faq": "/faq",
    "projects": "/projects",
    "login": "/auth/login",
    "register": "/register",
    "forgot_password": "/forgot-password",
    "license": "/license",
    "offer": "/offer",
    "privacy": "/privacy",
}

# Контактная информация
SITE_INFO = {
    "email": "info@id-prosto.ru",
    "authors": ["Александр Субботин", "Андрей Архипов"],
    "copyright": "id-prosto, 2022-2026",
    "tech_stack": "Next.js + Mantine UI",
    "captcha_type": "Yandex SmartCaptcha (invisible)",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


@dataclass
class IdProstoDocument:
    """Модель документа из id-prosto.ru."""
    name: str
    category: str = ""
    url: str = ""
    pdf_url: str = ""
    form_type: str = ""
    ntd_reference: str = ""
    description: str = ""
    fields: List[Dict[str, Any]] = field(default_factory=list)
    example_urls: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "url": self.url,
            "pdf_url": self.pdf_url,
            "form_type": self.form_type,
            "ntd_reference": self.ntd_reference,
            "description": self.description,
            "fields": self.fields,
            "example_urls": self.example_urls,
        }


class IdProstoClient:
    """
    Авторизованный клиент для id-prosto.ru.

    Три стратегии авторизации (по приоритету):
      1. Cookie-передача — самый быстрый, без капчи
      2. Логин/пароль + 2Captcha — полная автоматизация
      3. agent-browser CLI — для JS-тяжёлых страниц
    """

    def __init__(
        self,
        login: Optional[str] = None,
        password: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        twocaptcha_api_key: Optional[str] = None,
        timeout: int = 30,
    ):
        self.login = login
        self.password = password
        self.twocaptcha_api_key = twocaptcha_api_key
        self.timeout = timeout

        self._client = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
            cookies=cookies or {},
        )

        self._kb_path = (
            Path(__file__).parent.parent.parent
            / "artifacts" / "pto_knowledge_base"
        )
        self._templates_cache: Optional[Dict] = None
        self._authenticated = bool(cookies)

        if cookies:
            logger.info("IdProstoClient: авторизация через cookies (%d)", len(cookies))

    # ═══════════════════════════════════════════════
    #  АВТОРИЗАЦИЯ
    # ═══════════════════════════════════════════════

    def authenticate(self) -> bool:
        """
        Полная авторизация. Пробует стратегии по порядку:
          cookies → login+2captcha → agent-browser
        """
        if self._authenticated:
            return True

        # 1. Проверяем текущие cookies
        if self._check_session():
            self._authenticated = True
            logger.info("Cookies валидны — авторизация успешна")
            return True

        # 2. Логин + 2Captcha
        if self.login and self.password:
            if self._login_with_captcha():
                self._authenticated = True
                return True

        # 3. agent-browser
        if self._login_with_agent_browser():
            self._authenticated = True
            return True

        logger.error("Все методы авторизации не сработали")
        return False

    def _check_session(self) -> bool:
        """Проверяет валидность текущей сессии."""
        try:
            resp = self._client.get("/profile", follow_redirects=False)
            return resp.status_code != 302
        except Exception as e:
            logger.warning("Ошибка проверки сессии: %s", e)
            return False

    # ─── 2Captcha ───────────────────────────────

    def _login_with_captcha(self) -> bool:
        """
        Авторизация через форму входа + разгадывание reCAPTCHA.

        Алгоритм:
          1. GET /auth/login → HTML с формой
          2. Извлечь sitekey reCAPTCHA
          3. Отправить на 2Captcha API
          4. Дождаться решения (20-60 сек)
          5. POST /auth/login с token
        """
        if not self.twocaptcha_api_key:
            logger.warning("2Captcha API key не предоставлен — пробуем без капчи")
            return self._submit_login()

        try:
            # Шаг 1: загружаем страницу входа
            resp = self._client.get("/auth/login")
            if resp.status_code != 200:
                logger.error("Страница входа недоступна: %d", resp.status_code)
                return False

            # Шаг 2: ищем sitekey
            sitekey = self._extract_recaptcha_sitekey(resp.text)
            if not sitekey:
                logger.info("reCAPTCHA не найдена — пробуем без неё")
                return self._submit_login()

            # Шаг 3: решаем капчу
            logger.info("Решаем reCAPTCHA (sitekey=%s...) через 2Captcha", sitekey[:16])
            token = self._solve_recaptcha(sitekey)
            if not token:
                logger.error("Не удалось решить капчу")
                return False

            # Шаг 4: отправляем форму
            return self._submit_login(captcha_token=token)

        except Exception as e:
            logger.error("Ошибка авторизации: %s", e)
            return False

    def _extract_recaptcha_sitekey(self, html: str) -> Optional[str]:
        """
        Извлекает sitekey капчи из HTML.

        Важно: id-prosto.ru использует Яндекс SmartCaptcha (НЕ Google reCAPTCHA).
        Sitekey уже известен из анализа JS-чанка: ysc1_MyTawGAah44rcHpuIRcS9W2HMgervcCgVVHhQZKm3668a2e9
        """
        # Сначала пробуем известный sitekey
        if SMARTCAPTCHA_SITEKEY:
            return SMARTCAPTCHA_SITEKEY
        # Fallback: ищем в HTML
        patterns = [
            r'sitekey["\s:=]+["\']([^"\']+)["\']',
            r'data-sitekey="([^"]+)"',
            r'siteKey["\s:=]+["\']([^"\']+)["\']',
        ]
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                return m.group(1)
        return None

    def _solve_recaptcha(self, sitekey: str) -> Optional[str]:
        """
        Решает Яндекс SmartCaptcha через 2Captcha.

        id-prosto.ru использует Яндекс SmartCaptcha (invisible mode),
        загружаемую с smartcaptcha.cloud.yandex.ru.
        2Captcha поддерживает решение через метод solver.recaptcha().
        """
        try:
            from twocaptcha import TwoCaptcha

            solver = TwoCaptcha(self.twocaptcha_api_key)
            result = solver.recaptcha(sitekey=sitekey, url=LOGIN_URL)
            token = result.get("code", "")
            if token:
                logger.info("Капча решена успешно")
                return token
        except Exception as e:
            logger.error("2Captcha ошибка: %s", e)
        return None

    def _submit_login(self, captcha_token: str = "") -> bool:
        """POST-запрос формы авторизации."""
        data = {"email": self.login, "password": self.password}
        if captcha_token:
            data["g-recaptcha-response"] = captcha_token

        try:
            resp = self._client.post("/auth/login", data=data, follow_redirects=False)

            if resp.status_code in (302, 303):
                loc = resp.headers.get("location", "")
                if "/auth" not in loc:
                    logger.info("Вход успешен → %s", loc)
                    return True

            if resp.status_code == 200 and "/auth/login" not in str(resp.url):
                return True

            logger.warning("Авторизация отклонена: %d", resp.status_code)
            return False
        except Exception as e:
            logger.error("Ошибка отправки формы: %s", e)
            return False

    # ─── agent-browser ──────────────────────────

    def _login_with_agent_browser(self) -> bool:
        """Авторизация через agent-browser CLI (Playwright под капотом)."""
        import subprocess

        try:
            subprocess.run(
                ["agent-browser", "open", LOGIN_URL],
                capture_output=True, timeout=30,
            )
            time.sleep(3)

            # Заполняем email
            subprocess.run(
                ["agent-browser", "find", "text", "email", "click"],
                capture_output=True, timeout=10,
            )
            time.sleep(0.5)
            subprocess.run(
                ["agent-browser", "type", self.login or ""],
                capture_output=True, timeout=10,
            )

            # Заполняем пароль
            subprocess.run(
                ["agent-browser", "find", "text", "пароль", "click"],
                capture_output=True, timeout=10,
            )
            time.sleep(0.5)
            subprocess.run(
                ["agent-browser", "type", self.password or ""],
                capture_output=True, timeout=10,
            )

            # Кнопка «Войти»
            subprocess.run(
                ["agent-browser", "find", "text", "Войти", "click"],
                capture_output=True, timeout=10,
            )
            time.sleep(5)

            # Забираем cookies
            result = subprocess.run(
                ["agent-browser", "eval", "document.cookie"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                for item in result.stdout.strip().split(";"):
                    if "=" in item:
                        k, v = item.strip().split("=", 1)
                        self._client.cookies.set(k.strip(), v.strip())
                return self._check_session()

        except Exception as e:
            logger.error("agent-browser ошибка: %s", e)
        return False

    # ═══════════════════════════════════════════════
    #  ПОЛУЧЕНИЕ ДАННЫХ
    # ═══════════════════════════════════════════════

    def get_category(self, category: str) -> List[IdProstoDocument]:
        """Список документов для категории (локально → онлайн)."""
        docs = self._get_from_local_kb(category)
        if docs:
            return docs
        return self._get_category_online(category)

    def _get_from_local_kb(self, category: str) -> List[IdProstoDocument]:
        """Из локальной базы знаний (артефакты)."""
        db_path = self._kb_path / "pto_templates_database.json"
        if not db_path.exists():
            return []

        try:
            if self._templates_cache is None:
                with open(db_path, "r", encoding="utf-8") as f:
                    self._templates_cache = json.load(f)

            for cat in self._templates_cache.get("work_categories", []):
                slug = cat.get("slug", "").lower()
                name = cat.get("name", "").lower()
                if slug == category.lower() or name == category.lower():
                    return [
                        IdProstoDocument(
                            name=d.get("name", ""),
                            category=cat.get("name", ""),
                            form_type=d.get("form_type", ""),
                            ntd_reference=d.get("ntd_reference", ""),
                            description=d.get("description", ""),
                            fields=d.get("fields", []),
                        )
                        for d in cat.get("documents", [])
                    ]
        except Exception as e:
            logger.error("Ошибка локальной БД: %s", e)
        return []

    def _get_category_online(self, category: str) -> List[IdProstoDocument]:
        """Онлайн-запрос категории (HTTP → agent-browser)."""
        docs: List[IdProstoDocument] = []

        # HTTP
        try:
            resp = self._client.get(f"/lists/{category}")
            if resp.status_code == 200:
                docs = self._parse_buttons(resp.text, category)
        except Exception as e:
            logger.warning("HTTP-запрос не удался: %s", e)

        # agent-browser fallback
        if not docs:
            import subprocess
            url = f"{LISTS_URL}/{category}"
            try:
                subprocess.run(
                    ["agent-browser", "open", url],
                    capture_output=True, timeout=30,
                )
                time.sleep(3)
                result = subprocess.run(
                    [
                        "agent-browser", "eval",
                        "Array.from(document.querySelectorAll"
                        "('main article button'))"
                        ".map(b=>b.textContent.trim()).join('|||')",
                    ],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode == 0 and result.stdout.strip():
                    for name in result.stdout.strip().split("|||"):
                        name = name.strip()
                        if name:
                            docs.append(IdProstoDocument(name=name, category=category))
            except Exception as e:
                logger.error("agent-browser fallback: %s", e)

        return docs

    def _parse_buttons(self, html: str, category: str) -> List[IdProstoDocument]:
        """Парсит кнопки из HTML."""
        matches = re.findall(r'<button[^>]*>(.*?)</button>', html, re.DOTALL)
        docs = []
        for m in matches:
            name = re.sub(r'<[^>]+>', '', m).strip()
            if name:
                docs.append(IdProstoDocument(name=name, category=category))
        return docs

    # ─── Поиск ──────────────────────────────────

    def search(self, query: str) -> List[IdProstoDocument]:
        """Поиск документов (локально → онлайн)."""
        results: List[IdProstoDocument] = []
        ql = query.lower()

        # Локально
        db_path = self._kb_path / "pto_templates_database.json"
        if db_path.exists():
            try:
                if self._templates_cache is None:
                    with open(db_path, "r", encoding="utf-8") as f:
                        self._templates_cache = json.load(f)

                for cat in self._templates_cache.get("work_categories", []):
                    for doc in cat.get("documents", []):
                        if (
                            ql in doc.get("name", "").lower()
                            or ql in doc.get("description", "").lower()
                            or ql in doc.get("ntd_reference", "").lower()
                        ):
                            results.append(IdProstoDocument(
                                name=doc.get("name", ""),
                                category=cat.get("name", ""),
                                form_type=doc.get("form_type", ""),
                                ntd_reference=doc.get("ntd_reference", ""),
                                description=doc.get("description", ""),
                            ))
            except Exception as e:
                logger.error("Ошибка поиска: %s", e)

        # Онлайн
        if self._authenticated and len(results) < 5:
            try:
                resp = self._client.get("/search", params={"q": query})
                if resp.status_code == 200:
                    pat = r'<a[^>]*href="(/examples/[^"]*)"[^>]*>.*?<h[23][^>]*>(.*?)</h[23]>'
                    for url, title in re.findall(pat, resp.text, re.DOTALL):
                        results.append(IdProstoDocument(
                            name=re.sub(r'<[^>]+>', '', title).strip(),
                            url=f"{BASE_URL}{url}",
                        ))
            except Exception as e:
                logger.warning("Онлайн-поиск: %s", e)

        return results

    # ─── Скачивание ─────────────────────────────

    def download_pdf(self, url: str, save_path: Optional[str] = None) -> Optional[bytes]:
        """Скачивает PDF с id-prosto.ru."""
        try:
            resp = self._client.get(url, follow_redirects=True)
            if resp.status_code == 200 and "pdf" in resp.headers.get("content-type", "").lower():
                if save_path:
                    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(save_path).write_bytes(resp.content)
                    logger.info("PDF сохранён: %s (%d байт)", save_path, len(resp.content))
                return resp.content
            logger.error("PDF не скачан: %d", resp.status_code)
        except Exception as e:
            logger.error("Ошибка скачивания: %s", e)
        return None

    # ─── Формы и примеры ────────────────────────

    def get_forms(self) -> List[IdProstoDocument]:
        """Список форм из локальной базы или онлайн."""
        forms_path = self._kb_path / "id_forms_raw.json"
        if forms_path.exists():
            try:
                with open(forms_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return [
                    IdProstoDocument(
                        name=f.get("name", f.get("title", "")),
                        category=f.get("category", ""),
                        url=f.get("url", ""),
                        form_type="form",
                    )
                    for f in (data if isinstance(data, list) else [])
                    if isinstance(f, dict)
                ]
            except Exception:
                pass

        try:
            resp = self._client.get("/forms")
            if resp.status_code == 200:
                return self._parse_buttons(resp.text, "forms")
        except Exception as e:
            logger.error("Формы: %s", e)
        return []

    def get_examples(self, category: Optional[str] = None) -> List[IdProstoDocument]:
        """Примеры документов из локальной базы."""
        path = self._kb_path / "id_examples_structured.json"
        if not path.exists():
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            docs = []
            for ntd_name, info in data.items() if isinstance(data, dict) else []:
                if not isinstance(info, dict):
                    continue
                if category and category.lower() not in ntd_name.lower():
                    continue
                for doc_name in info.get("doc_names", []):
                    docs.append(IdProstoDocument(
                        name=doc_name,
                        category=ntd_name,
                        example_urls=info.get("example_urls", []),
                        ntd_reference=ntd_name,
                    ))
            return docs
        except Exception as e:
            logger.error("Примеры: %s", e)
        return []

    # ═══════════════════════════════════════════════
    #  УПРАВЛЕНИЕ СЕССИЕЙ
    # ═══════════════════════════════════════════════

    def get_cookies(self) -> Dict[str, str]:
        return dict(self._client.cookies)

    def save_session(self, path: str = "~/.id_prosto_session.json") -> bool:
        """Сохраняет cookies в файл для повторного использования."""
        try:
            data = {
                "cookies": self.get_cookies(),
                "login": self.login,
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            p = Path(path).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("Сессия сохранена: %s", p)
            return True
        except Exception as e:
            logger.error("Ошибка сохранения: %s", e)
            return False

    @classmethod
    def from_session_file(cls, path: str = "~/.id_prosto_session.json") -> "IdProstoClient":
        """Создаёт клиент из сохранённой сессии."""
        try:
            p = Path(path).expanduser()
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                return cls(login=data.get("login"), cookies=data.get("cookies", {}))
        except Exception as e:
            logger.error("Ошибка загрузки сессии: %s", e)
        return cls()

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
