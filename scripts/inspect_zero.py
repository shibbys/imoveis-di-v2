"""
Quick HTML inspection for sites returning 0 results.
Loads each page with Playwright, tries several selectors, prints count + first card snippet.
Usage: python scripts/inspect_zero.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

SITES = [
    ("lis",           "https://www.imobiliarialis.com.br/imoveis/para-alugar?ordenar=recentes"),
    ("lis_compra",    "https://www.imobiliarialis.com.br/imoveis/a-venda/casa+chacara?quartos=2+&preco-de-venda=0~1500000"),
    ("joel_blume",    "https://www.joelblumecorretor.com.br/imoveis/para-alugar/todos/dois-irmaos/"),
    ("joel_blume_c",  "https://www.joelblumecorretor.com.br/imoveis/?disponibilidade=a-venda&categoria=casa&cidade=dois-irmaos&bairro=&area-min=&area-max=&finalidade=&quartos=3&order=padr%C3%A3o"),
    ("dmk_compra",    "https://www.dmkimoveis.com.br/venda/casa+chacara/dois-irmaos/?&pagina=1"),
]

SELECTORS = [
    ".list-items li",
    ".properties-list li",
    "ul.lista-imoveis li",
    "a[href*='/imovel/']",
    ".imovelcard",
    ".card-imovel",
    ".imovel-card",
    ".property-item",
    "article",
    "[class*='imovel']",
    "[class*='property']",
    "[class*='card']",
]


async def inspect(name, url):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"  {url}")
    print(f"{'='*60}")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1500)
            html = await page.content()
        finally:
            await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    best = None
    best_count = 0
    for sel in SELECTORS:
        cards = soup.select(sel)
        if len(cards) > best_count:
            best_count = len(cards)
            best = (sel, cards)
        if cards:
            print(f"  {len(cards):3d}  {sel}")

    if best and best_count > 0:
        print(f"\n  >> Best: {best[0]}  ({best_count} cards)")
        card_html = str(best[1][0])[:600]
        print(f"\n  First card snippet:\n{card_html}")
    else:
        print("\n  No cards found with any selector!")
        # Show what classes are most common on the page
        from collections import Counter
        classes = []
        for el in soup.find_all(True):
            for c in el.get("class", []):
                classes.append(c)
        top = Counter(classes).most_common(20)
        print("  Most common CSS classes on page:")
        for cls, cnt in top:
            print(f"    {cnt:4d}  .{cls}")


async def main():
    for name, url in SITES:
        await inspect(name, url)

asyncio.run(main())
