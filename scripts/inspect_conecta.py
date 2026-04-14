"""Inspect Conecta card structure to find proper selectors."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from collections import Counter

SITES = [
    ("conecta_aluguel",
     "https://www.conectaimoveisdi.com.br/imoveis/aluguel/dois-irmaos/-/-/-?filtros&pagination=1"),
    ("conecta_compra",
     "https://www.conectaimoveisdi.com.br/imoveis/venda/dois-irmaos/-/-/casa?filtros&min=0&max=4600000&ordem=desc-inclusao&pagination=1"),
    ("larissa_compra",
     "https://www.larissadillimoveis.com.br/imoveis/venda/dois-irmaos/-/-/casa"),
]

async def inspect(name, url):
    print(f"\n{'='*70}\n  {name}\n{'='*70}")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)
        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")

    # Show ALL a[href*="/imoveis/"] links grouped by href pattern
    all_links = soup.select('a[href*="/imoveis/"]')
    print(f"  Total a[href*='/imoveis/']: {len(all_links)}")

    # Group by href prefix to see patterns
    patterns = Counter()
    for a in all_links:
        href = a.get("href", "")
        # Take first 3 path segments
        parts = href.split("/")[:5]
        patterns["/".join(parts)] += 1

    print("  Href patterns (first 5 segments):")
    for pat, cnt in patterns.most_common(20):
        print(f"    {cnt:3d}  {pat}")

    # Show first 3 card-candidate links with full text
    print("\n  First 3 links sample:")
    for i, a in enumerate(all_links[:3]):
        href = a.get("href", "")
        text = " | ".join(p.strip() for p in a.get_text(separator="|").replace("\xa0"," ").split("|") if p.strip())
        print(f"\n  [{i}] href={href[:80]}")
        print(f"       text={text[:200]}")
        img = a.find("img")
        if img:
            print(f"       img={img.get('src','')[:80]}")

    # What does a real property card look like - try common card wrappers
    print("\n  Candidate card selectors:")
    for sel in [".imovel-card", ".property-card", ".card", "[class*='imovel']",
                "article", ".listing-item", ".result-item", "li[class]"]:
        cards = soup.select(sel)
        if cards:
            print(f"    {len(cards):3d}  {sel}")

async def main():
    for name, url in SITES:
        await inspect(name, url)

asyncio.run(main())
