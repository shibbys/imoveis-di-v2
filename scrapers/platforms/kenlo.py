import asyncio
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper, PropertyData, normalize_price, normalize_area, normalize_int


class KenloScraper(BaseScraper):
    """Scraper for sites running on the Kenlo platform."""

    CARD_SELECTOR = ".card-listing"
    NEXT_PAGE_SELECTOR = ""  # not used — Kenlo uses JS-only "Ver mais" button

    # Maps text keywords to category names (checked against title and URL)
    CATEGORY_KEYWORDS = [
        ("apartamento", "Apartamento"),
        ("apto", "Apartamento"),
        ("terreno", "Terreno"),
        ("lote", "Terreno"),
        ("comercial", "Comercial"),
        ("sala", "Comercial"),
        ("galpao", "Comercial"),
        ("galpão", "Comercial"),
        ("kitnet", "Kitnet"),
        ("sobrado", "Sobrado"),
        ("cobertura", "Cobertura"),
    ]

    def _detect_category(self, title: str, url: str) -> str:
        combined = (title + " " + url).lower()
        for keyword, cat_name in self.CATEGORY_KEYWORDS:
            if keyword in combined:
                return cat_name
        return "Casa"

    def _extract_images(self, card) -> list:
        images = []
        for img in card.find_all("img"):
            for attr in ("data-src", "data-lazy-src", "src"):
                src = img.get(attr, "")
                if src and not src.startswith("data:") and src not in images:
                    images.append(src)
                    break
        # Also check background-image style
        for el in card.find_all(style=True):
            style = el.get("style", "")
            m = re.search(r"url\(['\"]?(https?://[^'\")\s]+)['\"]?\)", style)
            if m and m.group(1) not in images:
                images.append(m.group(1))
        return images

    def _extract_neighborhood(self, card, url: str) -> str:
        # Try address element
        for selector in [".property-address", "[class*='address']", "[class*='bairro']",
                         "[class*='endereco']", "[class*='localizacao']"]:
            el = card.select_one(selector)
            if el:
                text = el.get_text(strip=True)
                parts = [p.strip() for p in text.split(",")]
                if parts and parts[0]:
                    return parts[0]
        # Fallback: try to extract from URL pattern (e.g. /casa-centro-dois-irmaos)
        m = re.search(r"/(?:casa|apartamento|apto|sobrado|terreno|imovel)-([a-z-]+)-(?:dois-irmaos|morro-reuter)", url.lower())
        if m:
            return m.group(1).replace("-", " ").title()
        return ""

    def _extract_features(self, card) -> dict:
        """Extract bedrooms, bathrooms, parking_spots, area_m2, land_area_m2."""
        result = {
            "bedrooms": None, "bathrooms": None, "parking_spots": None,
            "area_m2": None, "land_area_m2": None,
        }
        # Try feature list items
        feature_els = card.select(
            ".property-features li, [class*='feature'] li, [class*='caracteristica'] li, "
            "[class*='detalhe'] li, .attributes li, [class*='attr'] li"
        )
        # Also try individual elements with known classes
        feature_els = list(feature_els)
        for cls_pattern in ["bedrooms", "bathrooms", "parking", "area", "quartos",
                             "banheiros", "vagas", "metragem"]:
            found = card.select(f"[class*='{cls_pattern}']")
            feature_els.extend(found)

        for feat in feature_els:
            text = feat.get_text(strip=True).lower()
            classes = " ".join(feat.get("class", []))

            if ("quarto" in text or "dormitório" in text or "dorm" in text
                    or "bedrooms" in classes or "quartos" in classes):
                result["bedrooms"] = normalize_int(text)
            elif ("banheiro" in text or "wc" in text or "bathrooms" in classes):
                result["bathrooms"] = normalize_int(text)
            elif ("vaga" in text or "garagem" in text or "parking" in classes or "vagas" in classes):
                result["parking_spots"] = normalize_int(text)
            elif ("terreno" in text or "lote" in text) and ("m²" in text or "m2" in text):
                result["land_area_m2"] = normalize_area(text)
            elif ("área" in text or "area" in text or "m²" in text or "m2" in text
                  or "area" in classes or "metragem" in classes) and "terreno" not in text:
                result["area_m2"] = normalize_area(text)
        return result

    def _parse_card(self, card, base_url: str):
        """Parse a single property card. Returns PropertyData or None."""
        try:
            from urllib.parse import urljoin
            a = card.find("a", href=True)
            if not a:
                return None
            source_url = urljoin(base_url, a["href"])

            neighborhood_el = card.select_one("h2.card-title, .card-title")
            neighborhood = neighborhood_el.get_text(strip=True) if neighborhood_el else ""

            cat_el = card.select_one("h3.card-text, h3")
            title = cat_el.get_text(strip=True) if cat_el else neighborhood
            category = self._detect_category(title, source_url)

            price_el = card.select_one(".h-money.location, .location")
            price_text = price_el.get_text() if price_el else None
            if price_text:
                # Strip suffixes like /mês, /ano, /dia before normalizing
                price_text = re.sub(r"/\w+", "", price_text)
            price = normalize_price(price_text)

            bedrooms = bathrooms = parking_spots = area_m2 = land_area_m2 = None
            for val in card.select(".values .value"):
                text = val.get_text(strip=True).lower()
                if "quarto" in text or "dorm" in text:
                    bedrooms = normalize_int(text)
                elif "banheiro" in text:
                    bathrooms = normalize_int(text)
                elif "vaga" in text or "garagem" in text:
                    parking_spots = normalize_int(text)
                elif "m²" in text or "m2" in text:
                    area_m2 = normalize_area(text)

            images = []
            for el in card.select(".card-loading, .card-img-top"):
                style = el.get("style", "")
                m = re.search(r"url\(['\"]?(https?://[^'\")\s]+)['\"]?\)", style)
                if m and m.group(1) not in images:
                    images.append(m.group(1))
            for img in card.find_all("img"):
                for attr in ("data-src", "src"):
                    src = img.get(attr, "")
                    if src and not src.startswith("data:") and src not in images:
                        images.append(src)
                        break

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

    def _parse_page(self, soup: BeautifulSoup, base_url: str) -> list:
        cards = soup.select(self.CARD_SELECTOR)
        results = []
        for card in cards:
            prop = self._parse_card(card, base_url)
            if prop:
                results.append(prop)
        return results

    def _get_next_page_url(self, soup: BeautifulSoup, current_url: str):
        # Kenlo uses JS-only "Ver mais" button — no URL pagination
        return None

    async def scrape(self) -> list:
        results = []
        current_url = self.url
        page_num = 0
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
                # Disable webdriver detection
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                while current_url and page_num < self.max_pages:
                    await page.goto(current_url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(1000)
                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    page_results = self._parse_page(soup, current_url)
                    if not page_results:
                        break
                    results.extend(page_results)
                    current_url = self._get_next_page_url(soup, current_url)
                    page_num += 1
                    if current_url:
                        await asyncio.sleep(self.delay_seconds)
            finally:
                await browser.close()
        return results
