"""Dapper card detail + DMK scraper test."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def dapper_cards():
    print("=== DAPPER ===")
    url = "https://www.dapperimoveis.com.br/imoveis/vendas#tipo_negociacao=2&tipo_imovel=54,62,59&cidade=Dois%20Irm%C3%A3os&valor_ate=1500000&currentPage=1&ordem=2"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(4000)
        html = await page.content()
        await browser.close()
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("a[href*='/imovel/']")
    print(f"Total cards: {len(cards)}")
    # Show full text + href for first 5
    for i, card in enumerate(cards[:5]):
        text = " | ".join(p.strip() for p in card.get_text(separator="|").split("|") if p.strip())
        href = card.get("href","")
        print(f"\n[{i}] {href[:80]}")
        print(f"     {text[:300]}")

async def dmk_test():
    print("\n=== DMK scraper test ===")
    from scrapers.platforms.imoview import ImoviewScraper
    s = ImoviewScraper(site_name="dmk_compra", url="https://www.dmkimoveis.com.br/venda/casa+chacara/dois-irmaos/?&pagina=1",
                       transaction_type="compra", max_pages=5)
    results = await s.scrape()
    print(f"Results: {len(results)}")
    for r in results:
        print(f"  {r.source_url}")
        print(f"  city={r.city} neighborhood={r.neighborhood} price={r.price} bedrooms={r.bedrooms}")

async def main():
    await dapper_cards()
    await dmk_test()

asyncio.run(main())
