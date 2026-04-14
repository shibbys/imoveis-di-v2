"""
Fetch rendered HTML from one representative site per platform.
Saves HTML to debug_html_<platform>.html for selector inspection.
"""
import asyncio
import sys
from playwright.async_api import async_playwright

SITES = [
    ("kenlo",   "https://www.imobiliariadoisirmaos.com.br/imoveis/para-alugar"),
    ("jetimob", "https://habbitar.com.br/alugar/imoveis?profile%5B0%5D=1&typeArea=total_area&floorComparision=equals&sort=-is_price_shown%2Cby_calculated_price&offset=1&limit=21"),
    ("vista",   "https://www.investirimoveisdi.com.br/busca/alugar/cidade/todas/categoria/apartamento_casa-sobrado_terrenos/data/desc/1/"),
    ("tecimob", "https://www.postaiimoveis.com.br/imoveis/tipo=casa-em-condominio,casas-e-sobrados&transacao=vendas&termo=Dois%20Irm%C3%A3os"),
]

async def fetch(name, url):
    print(f"Fetching {name}: {url}")
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
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            # Extra wait for lazy content
            await page.wait_for_timeout(2000)
            html = await page.content()
            out = f"debug_html_{name}.html"
            with open(out, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  Saved {len(html)} chars to {out}")
        except Exception as e:
            print(f"  ERROR: {e}")
        finally:
            await browser.close()

async def main():
    targets = sys.argv[1:] if sys.argv[1:] else [s[0] for s in SITES]
    for name, url in SITES:
        if name in targets:
            await fetch(name, url)

asyncio.run(main())
