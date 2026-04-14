"""Full card HTML inspection for lis, joel_blume, dmk."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def show(name, url, selector, idx=0):
    print(f"\n{'='*60}\n  {name}  |  {selector}\n{'='*60}")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)
        html = await page.content()
        await browser.close()
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(selector)
    print(f"  Found: {len(cards)}")
    if len(cards) > idx:
        print(str(cards[idx])[:1200])

async def main():
    await show("lis aluguel", "https://www.imobiliarialis.com.br/imoveis/para-alugar?ordenar=recentes",
               "a[href*='/imovel/']", 0)
    await show("joel_blume aluguel", "https://www.joelblumecorretor.com.br/imoveis/para-alugar/todos/dois-irmaos/",
               "article", 0)
    await show("joel_blume compra", "https://www.joelblumecorretor.com.br/imoveis/?disponibilidade=a-venda&categoria=casa&cidade=dois-irmaos&bairro=&area-min=&area-max=&finalidade=&quartos=3&order=padr%C3%A3o",
               "article", 0)
    await show("dmk", "https://www.dmkimoveis.com.br/venda/casa+chacara/dois-irmaos/?&pagina=1",
               "a[href*='/imovel/']", 0)
    await show("dmk all imovel divs", "https://www.dmkimoveis.com.br/venda/casa+chacara/dois-irmaos/?&pagina=1",
               ".imovelcard, .card-property, .property-item, article, .list-item", 0)

asyncio.run(main())
