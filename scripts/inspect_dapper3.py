"""Inspect Dapper card parent structure and inner text via Playwright."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

URL = "https://www.dapperimoveis.com.br/imoveis/vendas#tipo_negociacao=2&tipo_imovel=54,62,59&cidade=Dois%20Irm%C3%A3os&valor_ate=1500000&currentPage=1&ordem=2"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(URL, wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(5000)

        # Try Playwright inner_text on first card
        cards = await page.query_selector_all("a[href*='/imovel/']")
        print(f"Cards via Playwright: {len(cards)}")

        if cards:
            card = cards[0]
            href = await card.get_attribute("href")
            inner = await card.inner_text()
            print(f"\nCard 0 href: {href}")
            print(f"Card 0 inner_text: {repr(inner[:300])}")

            # Parent
            parent = await page.evaluate("el => el.parentElement.outerHTML.substring(0, 800)", card)
            print(f"\nParent HTML:\n{parent}")

        # Also try: get text of first card via JS
        result = await page.evaluate("""() => {
            const cards = document.querySelectorAll("a[href*='/imovel/']");
            return Array.from(cards).slice(0,3).map(a => ({
                href: a.href,
                text: a.innerText,
                parentText: a.parentElement ? a.parentElement.innerText : ''
            }));
        }""")
        print("\n--- JS evaluation ---")
        for r in result:
            print(f"href: {r['href'][:80]}")
            print(f"text: {repr(r['text'][:200])}")
            print(f"parent: {repr(r['parentText'][:300])}")
            print()

        await browser.close()

asyncio.run(main())
