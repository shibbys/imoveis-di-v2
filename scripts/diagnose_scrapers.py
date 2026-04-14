"""
Diagnostic script: visit each site in sites.yaml and check whether the
configured platform's card selector finds any cards. For 0-result sites,
also tries a set of common alternative selectors and reports the best match.

Usage:
    python scripts/diagnose_scrapers.py
    python scripts/diagnose_scrapers.py --site becker
    python scripts/diagnose_scrapers.py --only-broken
"""
import argparse
import asyncio
import sys
import yaml
from pathlib import Path

# Map platform → card selector used by each scraper
PLATFORM_SELECTORS = {
    "kenlo":     ".card-listing",
    "vista":     "article.imovel",
    "jetimob":   ".CardProperty",
    "tecimob":   "a.box-imovel",
    "smartimob": ".group.cursor-pointer.overflow-hidden",
}

# Broader set of selectors to try when the primary one finds nothing
FALLBACK_SELECTORS = [
    ".card-listing",
    ".property-card",
    ".imovel-card",
    "article.imovel",
    ".CardProperty",
    "a.box-imovel",
    ".group.cursor-pointer.overflow-hidden",
    "[class*='card'][class*='imovel']",
    "[class*='property']",
    "[class*='listing-item']",
    "[class*='imovel-item']",
    "article",
    ".item",
    "li.imovel",
    "div[itemtype*='RealEstateListing']",
]


async def diagnose_site(site: dict, only_broken: bool) -> dict:
    from playwright.async_api import async_playwright

    name = site["name"]
    url = site["url"]
    platform = site.get("platform", "kenlo")
    primary_sel = PLATFORM_SELECTORS.get(platform, ".card-listing")

    result = {
        "name": name,
        "platform": platform,
        "primary_count": 0,
        "best_selector": None,
        "best_count": 0,
        "error": None,
        "page_title": "",
    }

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
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
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1500)

            result["page_title"] = await page.title()

            # Try primary selector
            cards = await page.query_selector_all(primary_sel)
            result["primary_count"] = len(cards)

            if result["primary_count"] == 0:
                # Try fallback selectors
                for sel in FALLBACK_SELECTORS:
                    if sel == primary_sel:
                        continue
                    els = await page.query_selector_all(sel)
                    if len(els) > result["best_count"]:
                        result["best_count"] = len(els)
                        result["best_selector"] = sel

        except Exception as e:
            result["error"] = str(e)[:100]
        finally:
            await browser.close()

    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", help="Only check this site name")
    parser.add_argument("--only-broken", action="store_true",
                        help="Only show sites with 0 results")
    args = parser.parse_args()

    yaml_path = Path(__file__).parent.parent / "config" / "sites.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    sites = config["sites"]
    if args.site:
        sites = [s for s in sites if s["name"] == args.site]
        if not sites:
            print(f"Site '{args.site}' not found in sites.yaml")
            sys.exit(1)

    print(f"Checking {len(sites)} sites...\n")
    print(f"{'Site':<35} {'Platform':<12} {'Primary':>8}  {'Best fallback':<45} {'Best':>6}")
    print("-" * 115)

    broken = []
    for site in sites:
        result = await diagnose_site(site, args.only_broken)
        name = result["name"]
        platform = result["platform"]
        pc = result["primary_count"]
        best_sel = result["best_selector"] or ""
        best_cnt = result["best_count"]
        err = result["error"]

        if args.only_broken and pc > 0 and not err:
            continue

        if err:
            line = f"{name:<35} {platform:<12} {'ERR':>8}  {err:<45}"
        else:
            line = f"{name:<35} {platform:<12} {pc:>8}  {best_sel:<45} {best_cnt:>6}"

        if pc == 0 and not err:
            line = "!  " + line
            broken.append(result)
        elif err:
            line = "X  " + line
        else:
            line = "OK " + line

        print(line)

    print(f"\n{'-'*115}")
    print(f"Done. {len(broken)} sites with 0 results (check ! lines above).")

    if broken:
        print("\n=== SUGGESTED FIXES ===")
        for r in broken:
            if r["best_count"] > 0:
                print(f"  {r['name']}: try selector '{r['best_selector']}' ({r['best_count']} found)")
            else:
                print(f"  {r['name']}: no known selector matched — may need manual inspection")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
