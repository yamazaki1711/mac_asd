#!/usr/bin/env python3
"""
Автозагрузчик нормативных документов с meganorm.ru для ASD v12.0.

Источник: meganorm.ru — бесплатная база ГОСТ, СП, СНиП, ФЗ, ПП РФ.
Стратегия:
  1. Прямые PDF (Data2/{id}/{id}.pdf) — для ~20% документов
  2. Постраничные GIF (Data/{id}/{id}/N.gif) → сборка в PDF через fpdf2 — для ~80%
  3. HTML-версии (ФЗ, ПП РФ) — захват текста и конвертация в PDF

Usage:
    ASD_PROFILE=dev_linux .venv/bin/python scripts/download_meganorm.py
    ASD_PROFILE=dev_linux .venv/bin/python scripts/download_meganorm.py --dry-run
    ASD_PROFILE=dev_linux .venv/bin/python scripts/download_meganorm.py --only-critical
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import requests
from fpdf import FPDF

# ── Config ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
LIBRARY = PROJECT_ROOT / "library" / "normative"
MANIFEST = SCRIPT_DIR / "missing_normative.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

TIMEOUT = 30
RETRIES = 2
DELAY = 2.0  # секунд между запросами — уважаем сервер


# ── Utils ──────────────────────────────────────────────────────────────────

def log(msg: str):
    print(f"  {msg}", flush=True)


def safe_filename(name: str) -> str:
    """Привести имя файла к латинице с подчёркиваниями."""
    translit = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
    }
    # Latinize
    result = ''.join(translit.get(c, c) for c in name)
    # Replace non-alphanumeric with underscore
    result = re.sub(r'[^a-zA-Z0-9]+', '_', result)
    result = re.sub(r'_+', '_', result).strip('_')
    return result[:120]


def http_get(url: str, stream: bool = False, timeout: int = TIMEOUT) -> Optional[requests.Response]:
    """GET с ретраями."""
    for attempt in range(RETRIES + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, stream=stream)
            return r
        except requests.RequestException as e:
            if attempt < RETRIES:
                log(f"Retry {attempt+1}/{RETRIES}: {e}")
                time.sleep(DELAY * (attempt + 1))
            else:
                log(f"FAILED: {url[:80]} — {e}")
                return None


# ── Meganorm Search ────────────────────────────────────────────────────────

def search_meganorm(query: str) -> Optional[str]:
    """
    Поиск документа на meganorm.ru через Yandex.
    Возвращает URL страницы документа (Index/Index2) или None.
    """
    encoded = quote_plus(query)
    url = f"https://yandex.ru/search/?text=site%3Ameganorm.ru+{encoded}&lr=2"
    
    r = http_get(url)
    if not r or r.status_code != 200:
        return None
    
    text = r.text
    
    # Ищем Index или Index2 страницы
    patterns = [
        r'meganorm\.ru/Index2?/\d+/\d+\.htm',
        r'meganorm\.ru/Index2?/\d+(?:/\d+)?\.htm',
    ]
    for pat in patterns:
        matches = re.findall(pat, text)
        if matches:
            return f"https://{matches[0]}"
    
    return None


def find_pdf_url(index_url: str) -> Optional[str]:
    """
    По Index-странице найти прямой PDF (если есть).
    Паттерн: Data2/{level}/{id}/{id}.pdf
    """
    r = http_get(index_url)
    if not r or r.status_code != 200:
        return None
    
    # Ищем PDF ссылки
    pdf_patterns = [
        r'Data2?/\d+/\d+/\d+\.pdf',
        r'meganorm\.ru/Data2?/\d+/\d+/\d+\.pdf',
    ]
    for pat in pdf_patterns:
        m = re.search(pat, r.text)
        if m:
            url = m.group(0)
            if not url.startswith('http'):
                url = f"https://meganorm.ru/{url}"
            return url
    
    return None


def find_image_pattern(index_url: str) -> Optional[tuple[str, int]]:
    """
    По Index-странице найти паттерн изображений страниц.
    Returns: (base_url, page_count) или None.
    Паттерн: Data/{id}/{id}/N.gif
    """
    r = http_get(index_url)
    if not r or r.status_code != 200:
        return None
    
    # Ищем первый image
    m = re.search(r'Data/(\d+)/(\d+)/0\.gif', r.text)
    if not m:
        # Попробуем ещё паттерн
        m = re.search(r'Data/(\d+)/(\d+)/1\.gif', r.text)
        if not m:
            return None
    
    id1, id2 = m.group(1), m.group(2)
    
    # Считаем количество страниц
    page_count = 0
    for p in range(50):
        img_url = f"https://meganorm.ru/Data/{id1}/{id2}/{p}.gif"
        resp = http_get(img_url)
        if resp and resp.status_code == 200 and len(resp.content) > 500:
            page_count = p + 1
        elif resp and resp.status_code == 200 and len(resp.content) < 200:
            # Last page — tiny GIF (1x1 or similar)
            pass
        else:
            break
    
    if page_count == 0:
        return None
    
    base = f"https://meganorm.ru/Data/{id1}/{id2}"
    return base, page_count


# ── Downloaders ────────────────────────────────────────────────────────────

def download_pdf(pdf_url: str, dest: Path) -> bool:
    """Скачать прямой PDF."""
    r = http_get(pdf_url, stream=True)
    if not r or r.status_code != 200:
        return False
    
    content = b''
    for chunk in r.iter_content(8192):
        if chunk:
            content += chunk
    
    if len(content) < 1000 or content[:4] != b'%PDF':
        log(f"Not a valid PDF ({len(content)}B)")
        return False
    
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return True


def download_images(base_url: str, page_count: int, dest: Path) -> bool:
    """Скачать все страницы как GIF и собрать в PDF через fpdf2."""
    import tempfile
    
    images = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for p in range(page_count):
            img_url = f"{base_url}/{p}.gif"
            r = http_get(img_url)
            if not r or r.status_code != 200:
                log(f"Missing page {p}")
                continue
            
            fname = Path(tmpdir) / f"{p:03d}.gif"
            fname.write_bytes(r.content)
            
            if len(r.content) > 2000:  # Пропускаем пустые/заглушки
                images.append(str(fname))
        
        if not images:
            return False
        
        # Сборка PDF
        try:
            pdf = FPDF(unit='pt', format='A4')
            for img_path in images:
                pdf.add_page()
                pdf.image(img_path, x=0, y=0, w=595.28, h=841.89)
            
            dest.parent.mkdir(parents=True, exist_ok=True)
            pdf.output(str(dest))
            return True
        except Exception as e:
            log(f"PDF assembly failed: {e}")
            return False


def download_html_text(index_url: str, dest: Path) -> bool:
    """
    Для ФЗ и ПП РФ: захватить HTML-текст и сохранить как PDF.
    Meganorm показывает текст закона прямо на Index-странице.
    """
    r = http_get(index_url)
    if not r or r.status_code != 200:
        return False
    
    text = r.text
    
    # Извлекаем текст из HTML (простая очистка)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Обрезаем по ключевым словам
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    if len(''.join(lines)) < 500:
        log(f"Too little text extracted ({len(''.join(lines))} chars)")
        return False
    
    # Генерируем PDF через fpdf2
    try:
        pdf = FPDF(unit='mm', format='A4')
        pdf.add_font('DejaVu', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', uni=True)
        pdf.add_font('DejaVu', 'B', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', uni=True)
        
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font('DejaVu', '', 10)
        
        for line in lines[:500]:  # Ограничение по страницам
            try:
                pdf.multi_cell(0, 5, line)
            except Exception:
                pdf.multi_cell(0, 5, line.encode('latin-1', errors='replace').decode('latin-1'))
        
        dest.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(dest))
        return True
    except Exception as e:
        log(f"HTML→PDF failed: {e}")
        # Fallback: сохраняем как .txt
        txt_dest = dest.with_suffix('.txt')
        txt_dest.parent.mkdir(parents=True, exist_ok=True)
        txt_dest.write_text('\n'.join(lines[:500]), encoding='utf-8')
        log(f"Saved as .txt instead: {txt_dest.name}")
        return True


# ── Main Pipeline ──────────────────────────────────────────────────────────

def process_document(doc: dict, dry_run: bool = False) -> bool:
    """Обработать один документ: найти → скачать → сохранить."""
    doc_id = doc['id']
    query = doc['query']
    name = doc['name']
    category = doc['category']
    priority = doc['priority']
    
    dest_dir = LIBRARY / category
    fname = safe_filename(name) + '.pdf'
    dest = dest_dir / fname
    
    # Пропускаем уже существующие
    if dest.exists() and dest.stat().st_size > 10000:
        log(f"SKIP (exists): {name}")
        return True
    
    log(f"[{priority.upper()}] {name}")
    
    if dry_run:
        log(f"  DRY RUN — would save to {dest}")
        return False
    
    # Шаг 1: Поиск на meganorm
    index_url = search_meganorm(query)
    if not index_url:
        log(f"  NOT FOUND on meganorm")
        return False
    
    log(f"  Found: {index_url}")
    time.sleep(DELAY)
    
    # Шаг 2: Пробуем прямой PDF
    pdf_url = find_pdf_url(index_url)
    if pdf_url:
        log(f"  PDF: {pdf_url}")
        time.sleep(DELAY)
        if download_pdf(pdf_url, dest):
            size_kb = dest.stat().st_size // 1024
            log(f"  ✅ PDF {size_kb} KB")
            return True
        else:
            log(f"  PDF download failed, trying images...")
    
    # Шаг 3: Пробуем постраничные изображения
    img_info = find_image_pattern(index_url)
    if img_info:
        base_url, page_count = img_info
        log(f"  Images: {page_count} pages")
        time.sleep(DELAY)
        if download_images(base_url, page_count, dest):
            size_kb = dest.stat().st_size // 1024
            log(f"  ✅ Images→PDF {size_kb} KB, {page_count} стр.")
            return True
    
    # Шаг 4: HTML-текст (для ФЗ и ПП РФ)
    if category in ('fz', 'pp_rf'):
        log(f"  Trying HTML text extraction...")
        time.sleep(DELAY)
        if download_html_text(index_url, dest):
            size_kb = dest.stat().st_size // 1024
            log(f"  ✅ HTML→PDF {size_kb} KB")
            return True
    
    log(f"  ❌ FAILED — no downloadable content")
    return False


def main():
    dry_run = '--dry-run' in sys.argv
    only_critical = '--only-critical' in sys.argv
    
    if not MANIFEST.exists():
        print(f"Manifest not found: {MANIFEST}")
        sys.exit(1)
    
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    documents = manifest['documents']
    
    if only_critical:
        documents = [d for d in documents if d['priority'] == 'critical']
        print(f"Ограничение: только CRITICAL ({len(documents)} док.)")
    
    print(f"╔══════════════════════════════════════════════════════╗")
    print(f"║  Meganorm Downloader — ASD v12.0                    ║")
    print(f"║  Всего: {len(documents)} док.  Режим: {'DRY RUN' if dry_run else 'DOWNLOAD'}  ║")
    print(f"╚══════════════════════════════════════════════════════╝")
    print()
    
    success = 0
    failed = 0
    skipped = 0
    
    for i, doc in enumerate(documents):
        print(f"[{i+1}/{len(documents)}] {doc['id']}", end=' ')
        try:
            result = process_document(doc, dry_run=dry_run)
            if result:
                # Check if destination exists and is > 10KB
                dest_dir = LIBRARY / doc['category']
                fname = safe_filename(doc['name']) + '.pdf'
                dest = dest_dir / fname
                if dest.exists() and dest.stat().st_size > 10000:
                    success += 1
                elif not dry_run:
                    failed += 1
            else:
                if not dry_run:
                    failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1
        
        print()
        time.sleep(DELAY)
    
    # Итоги
    print(f"═══ ИТОГИ ═══")
    print(f"  Успешно:     {success}")
    print(f"  Не удалось:  {failed}")
    print(f"  Пропущено:   {skipped}")
    print(f"  Всего:       {len(documents)}")
    
    # Статистика библиотеки
    total_files = sum(1 for _ in LIBRARY.rglob('*') if _.is_file() and _.suffix == '.pdf')
    total_size = sum(f.stat().st_size for f in LIBRARY.rglob('*.pdf') if f.is_file())
    print(f"\n  Библиотека: {total_files} PDF, {total_size // (1024*1024)} MB")


if __name__ == '__main__':
    main()
