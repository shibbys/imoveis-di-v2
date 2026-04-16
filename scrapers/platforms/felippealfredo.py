"""
Dedicated scraper for Felippe Alfredo Imobiliária (Jetimob V2 / Next.js).

Card structure (confirmed from production HTML):
  - The card IS an <a class="vertical-property-card_info__HASH"> element
    The /imovel/ href is on the card element itself, not a child.
  - A sibling <a href="/imovel/..."> holds the image gallery (not the card data).
  - CSS module hashes change on deploy but the prefix is stable:
      a[class*='vertical-property-card_info__']          ← one per property
      [class*='vertical-property-card_type__']           ← category text
      [class*='vertical-property-card_neighborhood__']   ← neighborhood text
      [class*='contracts_priceNumber__']                 ← price text
  - Bedrooms / title encoded in the URL slug:
      /imovel/apartamento-com-2-quartos-...-bairro-floresta.../98907

Pagination: &pagina=N  (no anchor tags — URL is built manually)
Lazy-load: cards render on scroll; scroll until count stabilises before parsing.
"""
import re
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from scrapers.base import BaseScraper, PropertyData, normalize_price, normalize_area

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_CARD_SEL = "a[class*='vertical-property-card_info__']"


def _first_text(card, class_fragment: str) -> str:
    el = card.find(class_=re.compile(re.escape(class_fragment)))
    return el.get_text(strip=True) if el else ""


def _parse_card(card, base_url: str, site_name: str, transaction_type: str):
    try:
        href = card.get("href", "")
        if not href:
            return None
        source_url = href if href.startswith("http") else urljoin(base_url, href)

        # Category from dedicated span
        category = _first_text(card, "vertical-property-card_type__")
        if not category:
            m = re.search(r"/imovel/([a-z]+)", source_url.lower())
            category = m.group(1).capitalize() if m else "Imóvel"

        # Neighborhood from dedicated span
        neighborhood = _first_text(card, "vertical-property-card_neighborhood__")
        if not neighborhood:
            m = re.search(r"bairro-([a-z-]+)-em-", source_url.lower())
            if m:
                neighborhood = m.group(1).replace("-", " ").title()

        # Price from dedicated span
        price_text = _first_text(card, "contracts_priceNumber__")
        price = normalize_price(price_text) if price_text else None
        if not price:
            m = re.search(r"R\$\s*[\d.,]+", card.get_text())
            price = normalize_price(m.group(0)) if m else None

        # Bedrooms from URL slug: "com-2-quartos"
        bedrooms = None
        m = re.search(r"com-(\d+)-quartos?", source_url.lower())
        if m:
            bedrooms = int(m.group(1))

        # Area from card text
        area_m2 = None
        m = re.search(r"([\d.,]+)\s*m[²2]", card.get_text(), re.IGNORECASE)
        if m:
            area_m2 = normalize_area(m.group(0))

        # Title from URL slug
        m = re.search(r"/imovel/([^/?#]+)", source_url)
        if m:
            slug = re.sub(r"-\d+$", "", m.group(1).rstrip("/"))
            slug = re.sub(r"-(rs|sc|pr|sp)$", "", slug)
            title = " ".join(p.capitalize() for p in slug.split("-"))
            title = title[:80] if len(title) > 80 else title
        else:
            title = f"{category} em {neighborhood}" if neighborhood else category or "Imóvel"

        return PropertyData(
            source_site=site_name,
            source_url=source_url,
            title=title,
            city="Dois Irmãos",
            neighborhood=neighborhood,
            category=category,
            transaction_type=transaction_type,
            price=price,
            bedrooms=bedrooms,
            bathrooms=None,
            parking_spots=None,
            area_m2=area_m2,
            land_area_m2=None,
            images=[],
        )
    except Exception:
        return None


async def _scroll_until_stable(page, card_sel: str, max_rounds: int = 20) -> None:
    """Scroll to bottom repeatedly until card count stops growing (5 stable rounds)."""
    prev_count = 0
    stable = 0
    for _ in range(max_rounds):
        count = await page.eval_on_selector_all(card_sel, "els => els.length")
        if count == prev_count:
            stable += 1
            if stable >= 5:
                break
        else:
            stable = 0
        prev_count = count
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(3500)


class FelippeAlfredoScraper(BaseScraper):

    async def scrape(self) -> list:
        all_results: list[PropertyData] = []
        seen_urls: set[str] = set()

        parsed = urlparse(self.url)
        params = parse_qs(parsed.query, keep_blank_values=True)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(user_agent=_UA)
                page = await ctx.new_page()
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                for page_num in range(1, self.max_pages + 1):
                    params["pagina"] = [str(page_num)]
                    url = urlunparse(
                        parsed._replace(
                            query=urlencode({k: v[0] for k, v in params.items()})
                        )
                    )

                    await page.goto(url, wait_until="load", timeout=30000)

                    # 1) Wait for JS + API calls to settle (mirrors the old scraper's strategy)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=20000)
                    except Exception:
                        pass  # Analytics / GTM may never settle — proceed anyway

                    # 2) Confirm cards are present (quick check, not a break condition)
                    try:
                        await page.wait_for_selector(_CARD_SEL, timeout=10000)
                    except Exception:
                        pass  # Will naturally return 0 and stop via new_this_page check

                    # 3) Scroll until all lazy-loaded cards are in DOM
                    await _scroll_until_stable(page, _CARD_SEL)

                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    cards = soup.select(_CARD_SEL)

                    new_this_page = 0
                    for card in cards:
                        prop = _parse_card(card, url, self.site_name, self.transaction_type)
                        if prop and prop.source_url not in seen_urls:
                            seen_urls.add(prop.source_url)
                            all_results.append(prop)
                            new_this_page += 1

                    if new_this_page == 0:
                        break  # pagina N returned nothing new — done

            finally:
                await browser.close()

        return all_results
