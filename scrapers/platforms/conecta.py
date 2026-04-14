import re
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int
from scrapers.platforms.kenlo import KenloScraper


class ConectaScraper(KenloScraper):
    """
    Scraper for Conecta Imóveis DI (conectaimoveisdi.com.br) and similar sites
    (e.g. larissadillimoveis.com.br) on the same platform.

    Property links follow: /imoveis/{tt}/{city}/{neigh}/{-}/{cat}/{code}/imovel/{id}
    Navigation/filter links follow: /imoveis/{tt}/{city}/... (NO /imovel/ segment)

    The key distinction: property cards always contain "/imovel/" (singular) with a
    numeric ID in the href, while nav/filter links only have "/imoveis/" (plural).

    Card text structure (lines):
      "Código: AL14"
      "Casa"
      "Dois Irmãos / União"       ← "City / Neighborhood"
      "1.109,00 m²"               ← area (optional)
      "N Dormitórios"
      "N Banheiros"
      "N Vagas"
      "Aluguel: R$ 5.500,00"

    Pagination: URL param ?pagination=N (incremented per page).
    """

    # Match ONLY actual property links — must contain /imovel/ followed by digits
    CARD_SELECTOR = 'a[href*="/imovel/"]'
    _CARD_HREF_RE = re.compile(r"/imovel/\d+", re.I)

    def _parse_card(self, card, base_url: str):
        try:
            href = card.get("href", "")
            if not self._CARD_HREF_RE.search(href):
                return None
            source_url = urljoin(base_url, href)

            raw = card.get_text(separator="\n").replace("\xa0", " ")
            lines = [ln.strip() for ln in raw.splitlines()
                     if ln.strip() and ln.strip().lower() not in ("ver detalhes", "consulte")]

            # Category: first non-code, non-numeric, non-area descriptive line
            title = ""
            category = "Casa"
            for line in lines:
                if line.startswith("Código") or line.startswith("Ref"):
                    continue
                if len(line) > 2 and not re.match(r"^\d", line) and "m²" not in line:
                    title = line
                    category = self._detect_category(line, source_url)
                    break

            # Location: "City / Neighborhood"
            neighborhood = ""
            city = "Dois Irmãos"
            for line in lines:
                if " / " in line and not line.startswith("R$") and "m²" not in line:
                    parts = line.split(" / ", 1)
                    city_part = parts[0].strip()
                    neigh_part = parts[1].strip() if len(parts) > 1 else ""
                    if city_part:
                        city = city_part
                    neighborhood = neigh_part
                    break

            # Features
            bedrooms = bathrooms = parking_spots = area_m2 = None
            feat_m = re.search(r"([\d.,]+)\s*m²", raw, re.IGNORECASE)
            if feat_m:
                area_m2 = normalize_area(feat_m.group(0))
            q_m = re.search(r"(\d+)\s*[Dd]orm", raw)
            if q_m:
                bedrooms = int(q_m.group(1))
            b_m = re.search(r"(\d+)\s*[Bb]anheiro", raw)
            if b_m:
                bathrooms = int(b_m.group(1))
            v_m = re.search(r"(\d+)\s*[Vv]aga", raw)
            if v_m:
                parking_spots = int(v_m.group(1))

            # Price: "Aluguel: R$ 5.500,00" or "Venda: R$ ..."
            price = None
            p_m = re.search(r"(?:Aluguel|Venda|Locação):\s*(R\$\s*[\d.,]+)", raw, re.IGNORECASE)
            if p_m:
                price = normalize_price(p_m.group(1))
            else:
                p_m2 = re.search(r"R\$\s*[\d.,]+", raw)
                if p_m2:
                    price = normalize_price(p_m2.group(0))

            # Image
            images = []
            img = card.find("img")
            if img:
                src = img.get("src", "") or img.get("data-src", "")
                if src and not src.startswith("data:"):
                    if not src.startswith("http"):
                        src = urljoin(base_url, src)
                    images.append(src)

            return PropertyData(
                source_site=self.site_name, source_url=source_url,
                title=title or category,
                city=city, neighborhood=neighborhood,
                category=category, transaction_type=self.transaction_type,
                price=price, bedrooms=bedrooms, bathrooms=bathrooms,
                parking_spots=parking_spots, area_m2=area_m2,
                land_area_m2=None, images=images,
            )
        except Exception:
            return None

    def _parse_page(self, soup: BeautifulSoup, base_url: str) -> list:
        cards = soup.select(self.CARD_SELECTOR)
        results = []
        seen = set()
        for card in cards:
            href = card.get("href", "")
            if self._CARD_HREF_RE.search(href) and href not in seen:
                seen.add(href)
                prop = self._parse_card(card, base_url)
                if prop:
                    results.append(prop)
        return results

    def _page_url(self, page_num: int) -> str:
        """Build URL for page N by setting ?pagination=N."""
        parsed = urlparse(self.url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params["pagination"] = [str(page_num)]
        new_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=new_query))

    async def scrape(self) -> list:
        all_results = []
        seen_urls = set()

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

                for page_num in range(1, self.max_pages + 1):
                    url = self._page_url(page_num)
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(800)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(600)

                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    page_results = self._parse_page(soup, url)

                    # Filter out already-seen URLs (dedup across pages)
                    new_on_page = [r for r in page_results if r.source_url not in seen_urls]
                    for r in new_on_page:
                        seen_urls.add(r.source_url)
                    all_results.extend(new_on_page)

                    # Stop when page returns no new properties
                    if not new_on_page:
                        break

            finally:
                await browser.close()

        return all_results
