"""Full card text + links for lis, joel_blume, dmk."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def show(name, url, selector):
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
    cards = soup.select(selector)
    print(f"  Cards: {len(cards)}")
    for i, card in enumerate(cards[:3]):
        print(f"\n  --- card {i} ---")
        # Normalized text
        text = card.get_text(separator=" | ").replace("\xa0", " ")
        text = " ".join(text.split())
        print(f"  TEXT: {text[:400]}")
        # First image
        img = card.find("img")
        if img:
            print(f"  IMG src: {img.get('src','')[:120]}")
            print(f"  IMG data-src: {img.get('data-src','')[:120]}")
        # href
        a = card.find("a", href=True) if card.name != "a" else card
        if a:
            print(f"  HREF: {a.get('href','')[:120]}")

async def main():
    await show("lis",
               "https://www.imobiliarialis.com.br/imoveis/para-alugar?ordenar=recentes",
               "a.card-with-buttons")
    await show("joel_blume compra",
               "https://www.joelblumecorretor.com.br/imoveis/?disponibilidade=a-venda&categoria=casa&cidade=dois-irmaos&bairro=&area-min=&area-max=&finalidade=&quartos=3&order=padr%C3%A3o",
               "article.item")
    await show("dmk",
               "https://www.dmkimoveis.com.br/venda/casa+chacara/dois-irmaos/?&pagina=1",
               "a[href*='/imovel/']")

asyncio.run(main())
