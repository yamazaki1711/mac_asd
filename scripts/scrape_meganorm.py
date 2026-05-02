#!/usr/bin/env python3
"""
Meganorm.ru scraper for ASD v12.0 normative library.
Uses Playwright (headless Chromium) to search meganorm via Yandex,
extract document page URLs, and download content.

Usage:
    ASD_PROFILE=dev_linux .venv/bin/python scripts/scrape_meganorm.py
    ASD_PROFILE=dev_linux .venv/bin/python scripts/scrape_meganorm.py --dry-run
    ASD_PROFILE=dev_linux .venv/bin/python scripts/scrape_meganorm.py --critical-only
    ASD_PROFILE=dev_linux .venv/bin/python scripts/scrape_meganorm.py --max 5
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
LIBRARY = PROJECT_ROOT / "library" / "normative"
MANIFEST = SCRIPT_DIR / "to_download.json"
# Override with full manifest if exists
_fm = SCRIPT_DIR / "missing_normative_full.json"
if _fm.exists():
    MANIFEST = _fm
STATUS_FILE = SCRIPT_DIR / ".meganorm_progress.json"

MEGANORM = "https://meganorm.ru"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
}

# ── Helpers ───────────────────────────────────────────────────────────────

def safe_name(name: str) -> str:
    """Cyrillic → latin filename."""
    t = {
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh','з':'z',
        'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
        'с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch',
        'ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
        'А':'A','Б':'B','В':'V','Г':'G','Д':'D','Е':'E','Ё':'Yo','Ж':'Zh','З':'Z',
        'И':'I','Й':'Y','К':'K','Л':'L','М':'M','Н':'N','О':'O','П':'P','Р':'R',
        'С':'S','Т':'T','У':'U','Ф':'F','Х':'H','Ц':'Ts','Ч':'Ch','Ш':'Sh','Щ':'Sch',
        'Ъ':'','Ы':'Y','Ь':'','Э':'E','Ю':'Yu','Я':'Ya',
    }
    result = ''.join(t.get(c, c) for c in name)
    result = re.sub(r'[^a-zA-Z0-9]+', '_', result).strip('_')[:120]
    return result


def load_status() -> dict:
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text())
    return {"done": [], "failed": []}


def save_status(status: dict):
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2))


# ── Downloader (curl-based, fast) ─────────────────────────────────────────

def download_page_images(index_url: str, dest: Path) -> bool:
    """
    Visit meganorm Index page, find page images, download and convert to PDF.
    Pattern: Data/{id1}/{id2}/N.gif
    """
    r = requests.get(index_url, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return False
    
    # Find image base
    m = re.search(r'(Data(?:2)?/\d+/\d+)/[01]\.gif', r.text)
    if not m:
        m = re.search(r'Data/(\d+)/(\d+)/', r.text)
        if not m:
            return False
        base = f"https://meganorm.ru/Data/{m.group(1)}/{m.group(2)}"
    else:
        base = f"https://meganorm.ru/{m.group(1)}"
    
    # Try direct PDF first
    pdf_m = re.search(r'(Data2?/\d+/\d+/\d+\.pdf)', r.text)
    if pdf_m:
        pdf_url = f"https://meganorm.ru/{pdf_m.group(1)}"
        pr = requests.get(pdf_url, headers=HEADERS, timeout=60)
        if pr.status_code == 200 and len(pr.content) > 50000 and pr.content[:4] == b'%PDF':
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(pr.content)
            return True
    
    # Download page images
    pages = []
    for p in range(50):
        img_url = f"{base}/{p}.gif"
        ir = requests.get(img_url, headers=HEADERS, timeout=30)
        if ir.status_code != 200:
            break
        if len(ir.content) < 2000:
            if p > 0:  # page 0 is sometimes a 1x1 spacer
                break
            continue
        pages.append(ir.content)
    
    if not pages:
        return False
    
    # Assemble PDF with fpdf2
    import tempfile
    from fpdf import FPDF
    
    tmpdir = Path(tempfile.mkdtemp())
    try:
        img_paths = []
        for i, data in enumerate(pages):
            fpath = tmpdir / f"{i:03d}.gif"
            fpath.write_bytes(data)
            img_paths.append(str(fpath))
        
        pdf = FPDF(unit='pt', format='A4')
        for ip in img_paths:
            pdf.add_page()
            try:
                pdf.image(ip, x=0, y=0, w=595.28, h=841.89)
            except Exception:
                continue
        
        if pdf.pages:
            dest.parent.mkdir(parents=True, exist_ok=True)
            pdf.output(str(dest))
            return True
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    
    return False


# ── Browser-based search (Playwright) ──────────────────────────────────────

async def search_one(page, query: str) -> list[str]:
    """
    Search meganorm for one query via Yandex, return list of meganorm Index URLs.
    
    Strategy: navigate directly to Yandex search results (avoids cross-origin iframe issues).
    """
    try:
        encoded = quote_plus(f'site:meganorm.ru {query}')
        yandex_url = f'https://yandex.ru/search/?text={encoded}&lr=2'
        
        await page.goto(yandex_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)  # Wait for dynamic results
        
        # Extract meganorm Index URLs from Yandex results page
        urls = set()
        
        # Method 1: Direct links to meganorm
        try:
            links = await page.evaluate("""
                () => {
                    const links = [];
                    document.querySelectorAll('a[href*="meganorm.ru/Index"]').forEach(a => {
                        links.push(a.href);
                    });
                    return links;
                }
            """)
            urls.update(links)
        except Exception:
            pass
        
        # Method 2: Text extraction (Yandex shows URLs as visible text)
        try:
            text = await page.evaluate("() => document.body.innerText")
            # Match meganorm.ru/Index or Index2 paths
            found = re.findall(r'meganorm\.ru/Index2?/\d+(?:/\d+)?\.htm', text)
            urls.update(f"https://{u}" for u in found)
            # Also find Data2 PDF links
            found_pdf = re.findall(r'meganorm\.ru/Data2?/\d+/\d+/\d+\.pdf', text)
            urls.update(f"https://{u}" for u in found_pdf)
        except Exception:
            pass
        
        # Method 3: Check for CAPTCHA (if Yandex blocks us)
        try:
            captcha = await page.evaluate("() => !!document.querySelector('.captcha') || document.body.innerText.includes('капча')")
            if captcha:
                print(f"    ⚠️ Yandex CAPTCHA detected")
        except Exception:
            pass
        
        return list(urls)
    
    except Exception as e:
        print(f"    Search error: {e}")
        return []


async def scrape_all(documents: list, dry_run: bool = False, max_docs: int = None):
    """Main scraper loop."""
    from playwright.async_api import async_playwright
    
    status = load_status()
    
    if max_docs:
        documents = documents[:max_docs]
    
    # Filter already done
    remaining = [d for d in documents if d['id'] not in status['done'] and d['id'] not in status['failed']]
    
    print(f"Документов: {len(documents)} всего, {len(remaining)} осталось")
    if dry_run:
        print("РЕЖИМ: dry-run (только поиск URL, без загрузки)")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = await browser.new_page()
        
        found_urls = {}  # doc_id → [(url, is_pdf)]
        
        # Phase 1: Search and collect URLs
        print("\n─── ФАЗА 1: Поиск ───")
        for i, doc in enumerate(remaining):
            doc_id = doc['id']
            query = doc['query']
            print(f"[{i+1}/{len(remaining)}] {doc_id}: {query[:60]}...")
            
            urls = await search_one(page, query)
            
            if urls:
                # Deduplicate and prefer Index2 (newer format)
                index_urls = sorted(set(u for u in urls if '/Index' in u))
                found_urls[doc_id] = index_urls
                print(f"    Найдено: {len(index_urls)} URL")
                for u in index_urls[:2]:
                    print(f"      {u}")
            else:
                status['failed'].append(doc_id)
                print(f"    ❌ Не найдено")
            
            save_status(status)
            await asyncio.sleep(1.5)  # Rate limit
        
        # Phase 2: Download content
        if not dry_run:
            print(f"\n─── ФАЗА 2: Загрузка ({len(found_urls)} док.) ───")
            for doc_id, urls in found_urls.items():
                doc = next(d for d in documents if d['id'] == doc_id)
                dest = LIBRARY / doc['category'] / (safe_name(doc['name']) + '.pdf')
                
                if dest.exists() and dest.stat().st_size > 10000:
                    print(f"  SKIP (exists): {doc['name'][:50]}")
                    status['done'].append(doc_id)
                    continue
                
                print(f"  {doc_id}: загрузка...")
                success = False
                for url in urls[:3]:  # Try up to 3 URLs
                    if download_page_images(url, dest):
                        kb = dest.stat().st_size // 1024
                        print(f"    ✅ {kb} KB → {dest.name}")
                        success = True
                        break
                    await asyncio.sleep(0.5)
                
                if success:
                    status['done'].append(doc_id)
                else:
                    status['failed'].append(doc_id)
                    print(f"    ❌ Не удалось скачать")
                
                save_status(status)
        else:
            # Dry run: just print what we'd download
            print(f"\n─── DRY RUN: URLs collected for {len(found_urls)} documents ───")
            for doc_id, urls in found_urls.items():
                doc = next(d for d in documents if d['id'] == doc_id)
                dest = LIBRARY / doc['category'] / (safe_name(doc['name']) + '.pdf')
                print(f"  {doc_id} → {dest.name}")
                print(f"    URL: {urls[0] if urls else 'N/A'}")
        
        await browser.close()
    
    # Report
    print(f"\n═══ ИТОГИ ═══")
    print(f"  Успешно: {len(status['done'])}")
    print(f"  Не удалось: {len(status['failed'])}")
    
    # Library stats
    pdfs = list(LIBRARY.rglob('*.pdf'))
    total_mb = sum(f.stat().st_size for f in pdfs if f.is_file()) // (1024*1024)
    print(f"  Библиотека: {len(pdfs)} PDF, {total_mb} MB")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    dry_run = '--dry-run' in sys.argv
    critical_only = '--critical-only' in sys.argv
    
    # Parse --max N
    max_docs = None
    for i, arg in enumerate(sys.argv):
        if arg == '--max' and i + 1 < len(sys.argv):
            max_docs = int(sys.argv[i+1])
    
    if not MANIFEST.exists():
        print(f"Manifest not found: {MANIFEST}")
        print("Run first: python scripts/prepare_missing_list.py")
        sys.exit(1)
    
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    documents = manifest['documents']
    
    if critical_only:
        documents = [d for d in documents if d['priority'] == 'critical']
    
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  Meganorm Scraper — ASD v12.0               ║")
    print(f"║  Playwright + curl  |  {len(documents)} док.  {'DRY' if dry_run else 'LIVE'}  ║")
    print(f"╚══════════════════════════════════════════════╝")
    
    asyncio.run(scrape_all(documents, dry_run=dry_run, max_docs=max_docs))


if __name__ == '__main__':
    main()
