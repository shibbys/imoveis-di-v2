import re
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper, PropertyData, normalize_price, normalize_area, normalize_int


CATEGORY_KEYWORDS = [
    ("apartamento", "Apartamento"),
    ("apto", "Apartamento"),
    ("terreno", "Terreno"),
    ("lote", "Terreno"),
    ("comercial", "Comercial"),
    ("sala", "Comercial"),
    ("kitnet", "Kitnet"),
    ("sobrado", "Sobrado"),
    ("cobertura", "Cobertura"),
    ("sítio", "Sítio/Chácara"),
    ("sitio", "Sítio/Chácara"),
    ("chácara", "Sítio/Chácara"),
    ("chacara", "Sítio/Chácara"),
]


def _detect_category(title: str) -> str:
    combined = title.lower()
    for keyword, cat_name in CATEGORY_KEYWORDS:
        if keyword in combined:
            return cat_name
    return "Casa"


class SmartimobScraper(BaseScraper):
    """
    Scraper for sites running on the Smartimob platform (Next.js App Router).

    Cards have no <a href> — React onClick navigates to the property page.
    We capture each URL by clicking the card, recording the navigated URL,
    then going back. Card data (title, price, features, image) is extracted
    before each click from the current DOM.
    """

    CARD_SELECTOR = ".group.cursor-pointer.overflow-hidden"

    def _page_url(self, n: int) -> str:
        """Build URL for page N. Page 1 = base URL. Page 2+ appends /pagina-N."""
        base = self.url.rstrip("/")
        if n <= 1:
            return base
        # Remove any existing /pagina-X suffix before appending the new one
        base = re.sub(r"/pagina-\d+$", "", base)
        return f"{base}/pagina-{n}"

    async def _scrape_page(self, page, page_url: str, seen_urls: set) -> list:
        """Scrape a single listing page: click each card, capture URL, go back."""
        await page.goto(page_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        cards = await page.query_selector_all(self.CARD_SELECTOR)
        count = len(cards)
        results = []

        for i in range(count):
            try:
                await page.wait_for_selector(self.CARD_SELECTOR, timeout=10000)
                cards = await page.query_selector_all(self.CARD_SELECTOR)
                if i >= len(cards):
                    break
                card = cards[i]
                card_data = await _parse_card_element(card)

                async with page.expect_navigation(timeout=15000):
                    await card.click()
                source_url = page.url
                await page.go_back(wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(500)

                if not source_url or source_url == page_url or source_url in seen_urls:
                    continue
                seen_urls.add(source_url)

                results.append(PropertyData(
                    source_site=self.site_name,
                    source_url=source_url,
                    title=card_data["title"],
                    city=card_data["city"],
                    neighborhood=card_data["neighborhood"],
                    category=_detect_category(card_data["title"]),
                    transaction_type=self.transaction_type,
                    price=card_data["price"],
                    bedrooms=card_data["bedrooms"],
                    bathrooms=card_data["bathrooms"],
                    parking_spots=card_data["parking_spots"],
                    area_m2=card_data["area_m2"],
                    land_area_m2=None,
                    images=card_data["images"],
                ))
            except Exception:
                try:
                    if page.url != page_url:
                        await page.goto(page_url, wait_until="networkidle", timeout=20000)
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass
                continue

        return results

    async def scrape(self) -> list:
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

                all_results = []
                seen_urls: set = set()

                for page_num in range(1, self.max_pages + 1):
                    page_url = self._page_url(page_num)
                    page_results = await self._scrape_page(page, page_url, seen_urls)
                    all_results.extend(page_results)
                    if not page_results:
                        break

                return all_results
            finally:
                await browser.close()


async def _parse_card_element(card) -> dict:
    """Extract all visible data from a Smartimob property card element."""
    # Title from h3
    title_el = await card.query_selector("h3")
    title = (await title_el.inner_text()).strip() if title_el else ""

    # Location: look for "Bairro - Cidade" pattern
    neighborhood = ""
    city = "Dois Irmãos"
    # Try common location element patterns
    for sel in ["p.text-sm", "p.text-xs", "span.text-sm", "span.text-xs"]:
        els = await card.query_selector_all(sel)
        for el in els:
            text = (await el.inner_text()).strip()
            if " - " in text and len(text) < 60:
                parts = text.split(" - ")
                neighborhood = parts[0].strip()
                city_raw = parts[-1].strip()
                # Normalize city name
                city = city_raw if city_raw else "Dois Irmãos"
                break
        if neighborhood:
            break

    # Price: look for R$ pattern
    price = None
    price_el = await card.query_selector("p.font-bold, p.text-lg, strong")
    if price_el:
        price_text = (await price_el.inner_text()).strip()
        price_text = price_text.split("/")[0]  # strip /mês, /ano
        price = normalize_price(price_text)

    # Features from grid cells
    bedrooms = bathrooms = parking_spots = area_m2 = None
    grid = await card.query_selector("div.grid")
    if grid:
        cells = await grid.query_selector_all("> div")
        for cell in cells:
            text = (await cell.inner_text()).strip().lower()
            if "dorm" in text or "quarto" in text or "suite" in text or "suíte" in text:
                bedrooms = normalize_int(text)
            elif "banheiro" in text or " wc" in text:
                bathrooms = normalize_int(text)
            elif "vaga" in text or "garagem" in text:
                parking_spots = normalize_int(text)
            elif "m²" in text or "m2" in text:
                area_m2 = normalize_area(text)

    # Image: background-image style on a div
    images = []
    img_div = await card.query_selector("div[style*='background-image']")
    if img_div:
        style = await img_div.get_attribute("style") or ""
        m = re.search(r"url\(['\"]?(https?://[^'\")\s]+)['\"]?\)", style)
        if m:
            images.append(m.group(1))
    # Also check regular <img> tags
    for img in await card.query_selector_all("img"):
        src = await img.get_attribute("src") or await img.get_attribute("data-src") or ""
        if src and not src.startswith("data:") and src not in images:
            images.append(src)

    return {
        "title": title,
        "city": city,
        "neighborhood": neighborhood,
        "price": price,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "parking_spots": parking_spots,
        "area_m2": area_m2,
        "images": images,
    }
