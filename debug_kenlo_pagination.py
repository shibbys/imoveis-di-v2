"""
Investigate Kenlo "Ver mais" pagination:
1. Intercept all XHR/fetch requests when page loads and when button is clicked
2. Inspect the pagination element's data attributes and surrounding JS
"""
import asyncio
from playwright.async_api import async_playwright

URL = "https://www.imobiliariadoisirmaos.com.br/imoveis/para-alugar"

async def main():
    requests_seen = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await ctx.new_page()

        # Intercept all requests
        async def on_request(req):
            if req.resource_type in ("xhr", "fetch"):
                requests_seen.append(("INITIAL", req.method, req.url))

        page.on("request", on_request)

        await page.goto(URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # Inspect the pagination element
        pagination = await page.query_selector(".pagination, .pagination-cell")
        if pagination:
            html = await pagination.inner_html()
            print(f"PAGINATION HTML: {html[:500]}")
            # Check data attributes
            attrs = await pagination.evaluate("el => Object.fromEntries([...el.attributes].map(a => [a.name, a.value]))")
            print(f"PAGINATION ATTRS: {attrs}")

        # Count current cards
        cards = await page.query_selector_all(".card-listing")
        print(f"\nCards before click: {len(cards)}")

        # Intercept requests after click
        async def on_request2(req):
            if req.resource_type in ("xhr", "fetch"):
                requests_seen.append(("AFTER_CLICK", req.method, req.url))

        page.on("request", on_request2)

        # Click "Ver mais"
        btn = await page.query_selector(".pagination-cell, .pagination")
        if btn:
            print("\nClicking Ver mais...")
            await btn.click()
            await page.wait_for_timeout(3000)
            cards_after = await page.query_selector_all(".card-listing")
            print(f"Cards after click: {len(cards_after)}")
        else:
            print("No pagination button found")

        # Print all XHR/fetch requests
        print(f"\n=== XHR/Fetch requests ({len(requests_seen)}) ===")
        for stage, method, url in requests_seen:
            print(f"  [{stage}] {method} {url}")

        await browser.close()

asyncio.run(main())
