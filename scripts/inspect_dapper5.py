"""Capture full Dapper API URL and inspect the JSON response."""
import asyncio, sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from playwright.async_api import async_playwright

URL = "https://www.dapperimoveis.com.br/imoveis/vendas#tipo_negociacao=2&tipo_imovel=54,62,59&cidade=Dois%20Irm%C3%A3os&valor_ate=1500000&currentPage=1&ordem=2"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        api_responses = []

        async def on_response(resp):
            url = resp.url
            if "List.aspx" in url and "mode=realties" in url:
                try:
                    body = await resp.text()
                    api_responses.append((url, body))
                except Exception as e:
                    api_responses.append((url, f"ERROR: {e}"))

        page.on("response", on_response)
        await page.goto(URL, wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(3000)
        await browser.close()

    for url, body in api_responses:
        print(f"URL: {url}\n")
        # Show first 2000 chars of response
        print(f"BODY (first 2000 chars):\n{body[:2000]}")

asyncio.run(main())
