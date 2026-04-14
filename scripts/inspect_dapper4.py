"""Intercept Dapper API calls + inspect full card container HTML."""
import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

URL = "https://www.dapperimoveis.com.br/imoveis/vendas#tipo_negociacao=2&tipo_imovel=54,62,59&cidade=Dois%20Irm%C3%A3os&valor_ate=1500000&currentPage=1&ordem=2"

async def main():
    api_calls = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # Capture API calls
        async def on_request(req):
            if any(x in req.url for x in ["api", "json", "busca", "imoveis", "search", "list"]):
                api_calls.append(req.url)

        async def on_response(resp):
            if resp.status == 200 and "json" in resp.headers.get("content-type", ""):
                try:
                    body = await resp.json()
                    # If it looks like property data, print it
                    text = json.dumps(body)[:200]
                    if any(k in text.lower() for k in ["imovel", "preco", "bairro", "cidade"]):
                        print(f"\n[API JSON] {resp.url[:80]}")
                        print(f"  {text}")
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        await page.goto(URL, wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(5000)

        print("API calls captured:")
        for u in api_calls[:20]:
            print(f"  {u[:120]}")

        # Get full HTML of first card container
        result = await page.evaluate("""() => {
            const cards = document.querySelectorAll("a[href*='/imovel/']");
            if (!cards.length) return [];
            return Array.from(cards).slice(0,3).map(a => {
                // Walk up to find the card container
                let el = a;
                for (let i = 0; i < 5; i++) {
                    if (el.parentElement) el = el.parentElement;
                }
                return {
                    href: a.href,
                    containerHtml: el.outerHTML.substring(0, 1500),
                    containerText: el.innerText.substring(0, 400),
                };
            });
        }""")

        print("\n\nCard containers (5 levels up):")
        for r in result[:2]:
            print(f"\nhref: {r['href'][:80]}")
            print(f"text: {repr(r['containerText'][:300])}")
            print(f"html: {r['containerHtml'][:800]}")

        await browser.close()

asyncio.run(main())
