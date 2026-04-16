"""
Dedicated scraper for Felippe Alfredo Imobiliária.

The site is a Next.js / Jetimob V2 SPA:
  - Cards: [itemprop="itemListElement"] (itemtype varies: House, Apartment, …)
  - Links to detail pages contain /imovel/<id>
  - Items lazy-load as the user scrolls — a single page may hold all results
  - URL pagination via &pagina=N exists but the page may load all items on page 1
    via infinite scroll; we scroll until count stabilises, then try the next pagina
    only if the current page was "full" (i.e. returned as many items as expected)

Scroll strategy:
  1. Load page, wait for first card
  2. Scroll to bottom, wait 2 s, check card count
  3. Repeat until count is unchanged for 3 consecutive rounds
  4. Capture HTML, parse cards
  5. If any new items were found AND we haven't exceeded max_pages, try pagina+1
"""
import re
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from scrapers.base import BaseScraper, PropertyData, normalize_price, normalize_area


_SCHEMA_TO_CATEGORY: dict[str, str] = {
    "house":                   "Casa",
    "singlefamilyresidence":   "Casa",
    "residence":               "Casa",
    "apartment":               "Apartamento",
    "lodgingbusiness":         "Apartamento",
    "realestatelisting":       "Imóvel",
}

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Card container — itemprop="itemListElement" is consistent across property types
_CARD_SEL = '[itemprop="itemListElement"]'


def _category_from_itemtype(itemtype: str) -> str:
    key = itemtype.rstrip("/").rsplit("/", 1)[-1].lower()
    return _SCHEMA_TO_CATEGORY.get(key, "Imóvel")


def _parse_card(card, base_url: str, site_name: str, transaction_type: str):
    try:
        # Detail URL — first /imovel/ link inside the card
        a = card.find("a", href=re.compile(r"/imovel/\d+"))
        if not a:
            return None
        href = a["href"]
        source_url = href if href.startswith("http") else urljoin(base_url, href)

        itemtype = card.get("itemtype", "")
        category = _category_from_itemtype(itemtype)

        raw = card.get_text(separator="\n").replace("\xa0", " ")
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

        # Neighborhood — look for the "Bairro, Cidade - UF" line
        neighborhood = ""
        for line in lines:
            m = re.match(r"^([^,]+),\s*(?:Dois Irm|Morro Reuter)", line)
            if m:
                neighborhood = m.group(1).strip()
                break

        # Numeric features via regex on full raw text
        area_m2 = bedrooms = bathrooms = parking_spots = None

        m = re.search(r"([\d.,]+)\s*m[²2]", raw, re.IGNORECASE)
        if m:
            area_m2 = normalize_area(m.group(0))

        m = re.search(r"(\d+)\s*(?:quarto|dormit)", raw, re.IGNORECASE)
        if m:
            bedrooms = int(m.group(1))

        m = re.search(r"(\d+)\s*banheiro", raw, re.IGNORECASE)
        if m:
            bathrooms = int(m.group(1))

        m = re.search(r"(\d+)\s*vaga", raw, re.IGNORECASE)
        if m:
            parking_spots = int(m.group(1))

        # Price
        price = None
        m = re.search(r"R\$\s*[\d.,]+", raw)
        if m:
            price = normalize_price(m.group(0))

        # Title — first non-trivial line that isn't a feature or location
        title = category
        for line in lines:
            if (
                len(line) > 3
                and not re.match(r"^[\d.,R$]", line)
                and "m²" not in line
                and "Dois Irm" not in line
                and "Morro Reuter" not in line
                and "quarto" not in line.lower()
                and "banheiro" not in line.lower()
                and "vaga" not in line.lower()
            ):
                title = line
                break

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
            bathrooms=bathrooms,
            parking_spots=parking_spots,
            area_m2=area_m2,
            land_area_m2=None,
            images=[],
        )
    except Exception:
        return None


async def _scroll_until_stable(page, card_sel: str, max_rounds: int = 15) -> None:
    """
    Scroll to the bottom repeatedly until the card count stops growing.
    Considers count stable after 3 consecutive rounds with no change.
    """
    prev_count = 0
    stable = 0
    for _ in range(max_rounds):
        count = await page.eval_on_selector_all(card_sel, "els => els.length")
        if count == prev_count:
            stable += 1
            if stable >= 3:
                break
        else:
            stable = 0
        prev_count = count
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)


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

                    # Load and wait for first cards
                    await page.goto(url, wait_until="load", timeout=30000)
                    try:
                        await page.wait_for_selector(_CARD_SEL, timeout=15000)
                    except Exception:
                        break  # No cards at all — done

                    # Scroll until all lazy-loaded cards are in the DOM
                    await _scroll_until_stable(page, _CARD_SEL)

                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    cards = soup.select(_CARD_SEL)

                    new_this_page = 0
                    for card in cards:
                        prop = _parse_card(
                            card, url, self.site_name, self.transaction_type
                        )
                        if prop and prop.source_url not in seen_urls:
                            seen_urls.add(prop.source_url)
                            all_results.append(prop)
                            new_this_page += 1

                    if new_this_page == 0:
                        break  # Pagina N returned nothing new — done

            finally:
                await browser.close()

        return all_results
