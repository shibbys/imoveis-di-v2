import re
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int
from scrapers.platforms.kenlo import KenloScraper


# Font-Awesome icon class → feature type
_ICON_MAP = {
    "fa-bed": "bedrooms",
    "fa-bath": "bathrooms",
    "fa-shower": "bathrooms",
    "fa-car": "parking_spots",
    "fa-car-side": "parking_spots",
    "fa-arrows-h": "area_m2",
    "fa-expand": "area_m2",
    "fa-ruler": "area_m2",
    "fa-home": "area_m2",
}


class ImobiBrasilScraper(KenloScraper):
    """
    Scraper for sites using the ImobiBrasil platform.
    CDN: imgs2.cdn-imobibrasil.com.br

    Card structure (.imovelcard):
      a.imovelcard__img[href]  → source URL + image
      h2.imovelcard__info__local  → "Bairro, Cidade / RS"
      p.imovelcard__info__ref  → "Ref: XX - Category name"
      .imovelcard__info__feature (multiple):
        i.fa-*  (icon identifies type)
        p > b (value) + span (label)
      p.imovelcard__valor__valor  → "R$ 1.800"
    """

    CARD_SELECTOR = ".imovelcard"
    # Some ImobiBrasil deployments use different wrapper class names
    CARD_SELECTOR_FALLBACKS = [
        ".imovelcard",
        "a[href*='/imovel/']",
        ".card-imovel",
        ".property-card",
    ]

    def _parse_page(self, soup: BeautifulSoup, base_url: str) -> list:
        cards = soup.select(self.CARD_SELECTOR)
        if not cards:
            for sel in self.CARD_SELECTOR_FALLBACKS[1:]:
                cards = soup.select(sel)
                if cards:
                    break
        results = []
        for card in cards:
            prop = self._parse_card(card, base_url)
            if prop:
                results.append(prop)
        return results

    def _parse_card(self, card, base_url: str):
        try:
            # URL + image
            img_link = card.select_one("a.imovelcard__img[href], a[href*='/imovel/']")
            if not img_link:
                return None
            href = img_link.get("href", "")
            if not href:
                return None
            source_url = urljoin(base_url, href)

            img = img_link.find("img")
            images = []
            if img:
                src = img.get("src", "")
                if src and not src.startswith("data:"):
                    if not src.startswith("http"):
                        src = urljoin(base_url, src)
                    images.append(src)

            # Location: "Primavera, Dois Irmãos / RS"
            neighborhood = ""
            loc_el = card.select_one("h2.imovelcard__info__local")
            if loc_el:
                text = loc_el.get_text(strip=True)
                # "Primavera, Dois Irmãos / RS" → neighborhood = "Primavera"
                parts = re.split(r",\s*|\s*/\s*", text)
                neighborhood = parts[0].strip() if parts else ""

            # Title / category from ref text
            ref_el = card.select_one("p.imovelcard__info__ref")
            title = ""
            if ref_el:
                text = ref_el.get_text(strip=True)
                # "Ref: LC0021 - Casa" → extract after " - "
                m = re.search(r"[-–]\s+(.+)$", text)
                title = m.group(1).strip() if m else text
            if not title:
                # Fallback: use h2.imovelcard__info__tag
                tag_el = card.select_one("h2.imovelcard__info__tag")
                title = tag_el.get_text(strip=True) if tag_el else ""

            category = self._detect_category(title, source_url)

            # Features: icon class → value
            bedrooms = bathrooms = parking_spots = area_m2 = land_area_m2 = None
            for feat in card.select(".imovelcard__info__feature"):
                icon = feat.find("i")
                icon_class = " ".join(icon.get("class", [])) if icon else ""
                # Value is in <b> or first text node
                b = feat.find("b")
                val_text = b.get_text(strip=True) if b else feat.get_text(strip=True)
                feat_type = None
                for fa_cls, ftype in _ICON_MAP.items():
                    if fa_cls in icon_class:
                        feat_type = ftype
                        break
                if feat_type is None:
                    # Fallback: check text labels
                    full = feat.get_text(strip=True).lower()
                    if "dorm" in full or "quarto" in full:
                        feat_type = "bedrooms"
                    elif "banheiro" in full or "wc" in full:
                        feat_type = "bathrooms"
                    elif "vaga" in full or "garagem" in full:
                        feat_type = "parking_spots"
                    elif "m²" in full or "m2" in full:
                        feat_type = "area_m2"

                if feat_type == "bedrooms":
                    bedrooms = normalize_int(val_text)
                elif feat_type == "bathrooms":
                    bathrooms = normalize_int(val_text)
                elif feat_type == "parking_spots":
                    parking_spots = normalize_int(val_text)
                elif feat_type == "area_m2":
                    area_m2 = normalize_area(val_text)

            # Price
            price_el = card.select_one("p.imovelcard__valor__valor")
            price = normalize_price(price_el.get_text() if price_el else None)

            # Discard phantom records with no meaningful data
            if not title and price is None and not neighborhood:
                return None

            return PropertyData(
                source_site=self.site_name, source_url=source_url,
                title=title, city="Dois Irmãos", neighborhood=neighborhood,
                category=category, transaction_type=self.transaction_type,
                price=price, bedrooms=bedrooms, bathrooms=bathrooms,
                parking_spots=parking_spots, area_m2=area_m2,
                land_area_m2=land_area_m2, images=images,
            )
        except Exception:
            return None

    def _get_next_page_url(self, soup: BeautifulSoup, current_url: str):
        """ImobiBrasil paginates with &pag=N or &pagina=N in query string."""
        parsed = urlparse(current_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        # Detect which param name this deployment uses
        pag_key = "pagina" if "pagina" in params else "pag"
        try:
            page = int(params.get(pag_key, ["1"])[0])
        except (ValueError, IndexError):
            page = 1
        params[pag_key] = [str(page + 1)]
        new_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=new_query))

    async def scrape(self) -> list:
        parsed_url = urlparse(self.url)
        params = parse_qs(parsed_url.query, keep_blank_values=True)
        use_url_pagination = "pag" in params or "pagina" in params

        if not use_url_pagination:
            return await super().scrape()

        all_results = []
        seen_urls: set = set()
        current_url = self.url

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

                for _ in range(self.max_pages):
                    await page.goto(current_url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(1000)

                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    results = self._parse_page(soup, current_url)

                    new_results = [r for r in results if r.source_url not in seen_urls]
                    for r in new_results:
                        seen_urls.add(r.source_url)
                    all_results.extend(new_results)

                    if not new_results:
                        break
                    next_url = self._get_next_page_url(soup, current_url)
                    if not next_url:
                        break
                    current_url = next_url
            finally:
                await browser.close()

        return all_results
