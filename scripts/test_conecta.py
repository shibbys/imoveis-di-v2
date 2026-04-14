"""Quick test: count property cards vs nav links with new selector."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import re

_HREF_RE = re.compile(r"/imovel/\d+", re.I)

async def test(name, url):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(800)
        html = await page.content()
        await browser.close()
    soup = BeautifulSoup(html, "html.parser")
    all_links = soup.select('a[href*="/imovel/"]')
    props = [a for a in all_links if _HREF_RE.search(a.get("href",""))]
    print(f"{name}: {len(props)} property links (was {len(soup.select('a[href*=\"/imoveis/\"]'))} with old selector)")
    for a in props[:3]:
        text = " | ".join(p.strip() for p in a.get_text(separator="|").split("|") if p.strip())
        print(f"  {a['href'][:70]}")
        print(f"  {text[:120]}")

async def main():
    await test("conecta_aluguel",
               "https://www.conectaimoveisdi.com.br/imoveis/aluguel/dois-irmaos/-/-/-?filtros&pagination=1")
    await test("conecta_compra",
               "https://www.conectaimoveisdi.com.br/imoveis/venda/dois-irmaos/-/-/casa?filtros&min=0&max=4600000&ordem=desc-inclusao&pagination=1")
    await test("larissa p1",
               "https://www.larissadillimoveis.com.br/imoveis/venda/dois-irmaos/-/-/casa?pagination=1")
    await test("larissa p2",
               "https://www.larissadillimoveis.com.br/imoveis/venda/dois-irmaos/-/-/casa?pagination=2")

asyncio.run(main())
