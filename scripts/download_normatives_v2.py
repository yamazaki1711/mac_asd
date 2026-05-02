#!/usr/bin/env python3
"""
Скачивание нормативных документов с meganorm.ru для ASD v12.0.
Использует requests + прямые URL (без поиска, search API сломан).
Стратегия: Index страница → ищем PDF или GIF → скачиваем → собираем в PDF.

Запуск: python3.12 scripts/download_normatives_v2.py
"""

import json
import os
import re
import sys
import time
import tempfile
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).resolve().parent
LIBRARY = SCRIPT_DIR.parent / "library" / "normative"
MANIFEST = SCRIPT_DIR / "normative_docs_qwen.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
TIMEOUT = 30
DELAY = 2

# ── Utils ──

def safe_name(text: str) -> str:
    t = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh','з':'z',
         'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
         'с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch',
         'ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
         'А':'A','Б':'B','В':'V','Г':'G','Д':'D','Е':'E','Ё':'Yo','Ж':'Zh','З':'Z',
         'И':'I','Й':'Y','К':'K','Л':'L','М':'M','Н':'N','О':'O','П':'P','Р':'R',
         'С':'S','Т':'T','У':'U','Ф':'F','Х':'H','Ц':'Ts','Ч':'Ch','Ш':'Sh','Щ':'Sch',
         'Ъ':'','Ы':'Y','Ь':'','Э':'E','Ю':'Yu','Я':'Ya'}
    result = ''.join(t.get(c, c) for c in text)
    result = re.sub(r'[^a-zA-Z0-9]+', '_', result).strip('_')[:120]
    return result

def get_category(doc_num: str, doc_title: str) -> str:
    """Определить категорию для library/."""
    n = doc_num.strip()
    if n.startswith('ГОСТ') or n.startswith('ГОСТ Р'):
        return 'gost/documentation' if any(k in doc_title.lower() for k in ['спдс','ескд','документац']) else 'gost/materials'
    elif n.startswith('СП'):
        return 'sp/construction'
    elif n.startswith('СНиП'):
        return 'snip'
    elif 'ФЗ' in n or 'Федеральный' in n or 'кодекс' in doc_title.lower():
        return 'fz'
    elif 'ПП' in n or 'Постановление' in n:
        return 'pp_rf'
    elif 'Приказ' in n:
        return 'prikazy/minstroy'
    elif 'ВСН' in n:
        return 'vsn'
    else:
        return 'other'

# ── Direct URL Search ──

KNOWN_INDEX_URLS = {
    # Document number → Index URL (manually verified or discovered)
    "ГОСТ 24297-2013": "https://meganorm.ru/Index/56/56263.htm",
    "ГОСТ Р 51872-2024": "https://meganorm.ru/Index2/1/4293730/4293730712.htm",
    "ГОСТ Р 21.101-2020": "https://meganorm.ru/Index2/1/4293720/4293720404.htm",
}

def search_direct(session, query: str) -> list[str]:
    """Прямой поиск через Yandex (если не заблокирован) или известные URL."""
    if query in KNOWN_INDEX_URLS:
        return [KNOWN_INDEX_URLS[query]]
    
    # Try Yandex search
    try:
        encoded = requests.utils.quote(f"site:meganorm.ru {query}")
        url = f"https://yandex.ru/search/?text={encoded}&lr=2"
        resp = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        
        if resp.status_code == 200 and len(resp.text) > 1000:
            # Check for CAPTCHA
            if 'капча' in resp.text.lower() or 'captcha' in resp.text.lower():
                return []
            
            urls = re.findall(r'meganorm\.ru/Index2?/\d+(?:/\d+)?\.htm', resp.text)
            return [f"https://{u}" for u in urls]
    except Exception:
        pass
    
    return []

# ── Download ──

def download_document(session, index_url: str, dest: Path) -> bool:
    """Скачать документ: PDF напрямую или страницы → собрать в PDF."""
    try:
        resp = session.get(index_url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code != 200:
            return False
        
        # Try direct PDF
        pdf_m = re.search(r'meganorm\.ru/(Data2?/\d+/\d+/\d+\.pdf)', resp.text)
        if not pdf_m:
            pdf_m = re.search(r'"(Data2?/\d+/\d+/\d+\.pdf)"', resp.text)
        
        if pdf_m:
            pdf_url = f"https://meganorm.ru/{pdf_m.group(1)}"
            pr = session.get(pdf_url, headers=HEADERS, timeout=60)
            if pr.status_code == 200 and len(pr.content) > 50000 and pr.content[:4] == b'%PDF':
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(pr.content)
                return True
        
        # Try page images
        img_m = re.search(r'Data/(\d+)/(\d+)/[01]\.gif', resp.text)
        if not img_m:
            return False
        
        id1, id2 = img_m.group(1), img_m.group(2)
        base = f"https://meganorm.ru/Data/{id1}/{id2}"
        
        # Download pages
        pages = []
        for p in range(50):
            ir = session.get(f"{base}/{p}.gif", headers=HEADERS, timeout=TIMEOUT)
            if ir.status_code != 200:
                break
            if len(ir.content) < 2000:
                if p > 0:
                    break
                continue
            pages.append(ir.content)
        
        if not pages:
            return False
        
        # Assemble PDF
        from fpdf import FPDF
        with tempfile.TemporaryDirectory() as tmpdir:
            img_paths = []
            for i, data in enumerate(pages):
                fpath = Path(tmpdir) / f"{i:03d}.gif"
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
        
        return False
    except Exception as e:
        print(f"    Error: {e}")
        return False

# ── Main ──

def main():
    if not MANIFEST.exists():
        print(f"Manifest not found: {MANIFEST}")
        sys.exit(1)
    
    data = json.loads(MANIFEST.read_text(encoding='utf-8'))
    documents = data['documents']
    
    # Filter only relevant types
    relevant = [d for d in documents if not d.get('number','').startswith(('СП 1.','СП 2.','СП 3.','СП 4.','СП 5.','СП 6.','СП 7.','СП 8.','СП 9.','СП 10.','СП 11.','СП 12.','СП 13.','СП 14.','СП 15.','СП 16.','СП 17.','СП 18.','СП 19.','СП 20.','СП 21.','СП 22.','СП 23.','СП 24.','СП 25.','СП 26.','СП 27.','СП 28.','СП 29.','СП 30.','СП 31.','СП 32.','СП 33.','СП 34.','СП 35.','СП 36.','СП 37.','СП 38.','СП 39.'))]
    
    print(f"Documents: {len(relevant)} (filtered)")
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    success, failed, skipped = 0, 0, 0
    
    for i, doc in enumerate(relevant):
        num = doc.get('number', '')
        title = doc.get('title', '')[:60]
        cat = get_category(num, title)
        fname = safe_name(f"{num}") + '.pdf'
        dest = LIBRARY / cat / fname
        
        if dest.exists() and dest.stat().st_size > 10000:
            skipped += 1
            continue
        
        print(f"[{i+1}/{len(relevant)}] {num}: {title}")
        
        # Search
        urls = search_direct(session, num)
        if not urls:
            # Try with title
            urls = search_direct(session, f"{num} {title}")
        
        if not urls:
            print(f"    ❌ Not found")
            failed += 1
            continue
        
        # Download with first URL
        ok = download_document(session, urls[0], dest)
        if ok:
            kb = dest.stat().st_size // 1024
            print(f"    ✅ {kb} KB")
            success += 1
        else:
            print(f"    ❌ Download failed")
            failed += 1
        
        time.sleep(DELAY)
    
    print(f"\n═══ RESULTS ═══")
    print(f"  Success: {success}")
    print(f"  Failed:  {failed}")
    print(f"  Skipped: {skipped}")
    
    pdfs = list(LIBRARY.rglob('*.pdf'))
    mb = sum(f.stat().st_size for f in pdfs if f.is_file()) // (1024*1024)
    print(f"  Library: {len(pdfs)} PDFs, {mb} MB")

if __name__ == '__main__':
    main()
