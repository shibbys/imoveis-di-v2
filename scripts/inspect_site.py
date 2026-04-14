"""
Deep-inspect a single site: loads the page and shows the top-level structure
of the first matching card for a set of candidate selectors.

Usage:
    python scripts/inspect_site.py <site_name> [--selector "css selector"]
"""
import argparse
import asyncio
import sys
import yaml
from pathlib import Path


async def inspect(url: str, selector: str = None):
    from playwright.async_api import async_playwright

    CANDIDATES = [
        ".card-listing",
        "article.imovel",
        ".CardProperty",
        "a.box-imovel",
        ".group.cursor-pointer",
        "[class*='card-imovel']",
        "[class*='imovel-card']",
        "[class*='property-card']",
        "[class*='CardProperty']",
        ".property",
        "article",
        ".item",
        "li.imovel",
        "a[href*='/imovel']",
    ]
    if selector:
        CANDIDATES = [selector] + CANDIDATES

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
        print(f"Loading: {url}")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        print(f"Title: {await page.title()}")
        print(f"Final URL: {page.url}\n")

        print("=== Selector counts ===")
        for sel in CANDIDATES:
            els = await page.query_selector_all(sel)
            if els:
                print(f"  {len(els):>4}  {sel}")

        # Show first card HTML for the best selector
        print("\n=== First card HTML (best selector) ===")
        best_sel = None
        best_count = 0
        for sel in CANDIDATES:
            els = await page.query_selector_all(sel)
            if len(els) > best_count:
                best_count = len(els)
                best_sel = sel

        if best_sel:
            els = await page.query_selector_all(best_sel)
            first = els[0]
            inner = await first.inner_html()
            # Truncate to keep readable
            if len(inner) > 3000:
                inner = inner[:3000] + "\n... [truncated]"
            print(f"Selector: {best_sel}  ({best_count} found)\n")
            print(inner)
        else:
            print("No selector found any elements.\n")
            # Show body structure hints
            body_text = await page.evaluate("() => document.body.innerHTML.substring(0, 2000)")
            print("Body snippet:")
            print(body_text)

        await browser.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("site", help="Site name from sites.yaml")
    parser.add_argument("--selector", help="Force this selector as primary")
    args = parser.parse_args()

    yaml_path = Path(__file__).parent.parent / "config" / "sites.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    site = next((s for s in config["sites"] if s["name"] == args.site), None)
    if not site:
        print(f"Site '{args.site}' not found.")
        sys.exit(1)

    print(f"Site: {site['name']}  (platform: {site['platform']})")
    await inspect(site["url"], args.selector)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
