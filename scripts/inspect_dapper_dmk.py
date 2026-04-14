"""Inspect Dapper and DMK to find working selectors."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from collections import Counter

async def inspect(name, url, extra_wait=2000):
    print(f"\n{'='*70}\n  {name}\n  {url[:80]}\n{'='*70}")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(extra_wait)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)
        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    print(f"  Page title: {soup.title.string if soup.title else '?'}")

    # Try common selectors
    for sel in [
        "a[href*='/imovel/']", ".imovelcard", "article",
        "[class*='card']", "[class*='imovel']", "[class*='property']",
        "li[class]", ".listing", ".result",
    ]:
        found = soup.select(sel)
        if found:
            print(f"  {len(found):3d}  {sel}")

    # Show first property-looking link
    for sel in ["a[href*='/imovel/']", "a[href*='imovel']"]:
        links = soup.select(sel)
        if links:
            a = links[0]
            text = " | ".join(p.strip() for p in a.get_text(separator="|").split("|") if p.strip())
            print(f"\n  First {sel}:")
            print(f"    href: {a.get('href','')[:100]}")
            print(f"    text: {text[:200]}")
            img = a.find("img")
            if img:
                print(f"    img:  {(img.get('src') or img.get('data-src',''))[:100]}")
            break

    # Top CSS classes
    classes = Counter(c for el in soup.find_all(True) for c in el.get("class", []))
    print("\n  Top classes:")
    for cls, cnt in classes.most_common(15):
        print(f"    {cnt:4d}  .{cls}")

async def main():
    await inspect("dapper_compra",
        "https://www.dapperimoveis.com.br/imoveis/vendas#tipo_negociacao=2&tipo_imovel=54,62,59&cidade=Dois%20Irm%C3%A3os&valor_ate=1500000&currentPage=1&ordem=2",
        extra_wait=4000)
    await inspect("dmk_compra",
        "https://www.dmkimoveis.com.br/venda/casa+chacara/dois-irmaos/?&pagina=1",
        extra_wait=2000)

asyncio.run(main())
