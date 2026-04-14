import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper, PropertyData, normalize_price, normalize_area, normalize_int


_SKIP_PATTERNS = (
    "logo", "icon", "favicon", "sprite", "placeholder",
    "loading", "blank", "noimage", "no-image", "sem-imagem",
    "/_layout/", "/img/layout", "/img/_layout", "/assets/icon",
    "/static/img/ui", "avatar", "banner-", "header-",
)

# These patterns in a URL strongly suggest a property photo (not a logo/banner).
# Intentionally narrow: .jpg/.png alone are too broad and match everything.
_PHOTO_HINTS = (
    "/upload", "/fotos/", "/photos/", "/imovel/", "/imoveis/",
    "/imagens/", "/imgs/", "cloudinary", "amazonaws",
    "imgix", "voaimgs", "kenlo", "imobibrasil", "tecimob", "jetimob",
    "vistahost", "vistasoft",
)

# CSS selectors for sections that contain "related / similar properties" listings.
# These appear on every detail page and would make all properties share the same images.
_RELATED_SELS = (
    "[class*='similar']", "[class*='relacionad']", "[class*='semelhante']",
    "[class*='recomend']", "[class*='suggest']", "[class*='outros-imoveis']",
    "[class*='mais-imoveis']", "[class*='veja-tambem']", "[class*='other-prop']",
    "[id*='similar']", "[id*='relacionad']", "[id*='outros']",
)


def extract_detail_images(soup: BeautifulSoup, base_url: str) -> list:
    """Extract the property's own gallery images from a rendered detail page.

    Strategy:
    1. Strip footer, nav, and "related properties" sections so their thumbnails
       don't contaminate the result (they're the same on every detail page).
    2. Try gallery-specific CSS selectors in priority order; stop at the FIRST
       selector that yields valid images (prevents merging main gallery with
       secondary carousels).
    3. Fall back to background-image styles if no <img> gallery found.
    4. Last resort: all <img> tags filtered by platform-specific URL patterns.
    """
    import copy
    # Work on a shallow copy so we can decompose without affecting the caller's soup
    scope = copy.copy(soup)

    # Remove noise sections
    for sel in (*_RELATED_SELS, "footer", "nav", "header", "aside"):
        for el in scope.select(sel):
            el.decompose()

    seen: set = set()

    def _valid(src: str) -> bool:
        if not src or not src.startswith("http"):
            return False
        lower = src.lower()
        return not any(s in lower for s in _SKIP_PATTERNS)

    def _resolve(src: str) -> str:
        return urljoin(base_url, src) if src and not src.startswith("http") else src

    def _from_img(img) -> str:
        for attr in ("data-src", "data-lazy-src", "data-original", "src"):
            val = img.get(attr, "")
            if val and not val.startswith("data:"):
                return _resolve(val)
        return ""

    def _collect(candidates) -> list:
        result = []
        for src in candidates:
            if src and src not in seen and _valid(src):
                seen.add(src)
                result.append(src)
        return result

    _IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".avif")

    def _is_image_url(url: str) -> bool:
        lower = url.lower().split("?")[0]
        return any(lower.endswith(ext) for ext in _IMG_EXTS)

    # Fancybox / lightbox galleries (Vista, and others): full images are in
    # the href of <a data-fancybox> / <a data-lightbox> / <a data-gallery>.
    # There are no <img> tags inside — only the href matters.
    for attr in ("data-fancybox", "data-lightbox", "data-gallery", "data-image"):
        anchors = scope.select(f"a[{attr}]")
        if anchors:
            hrefs = _collect(
                href for a in anchors
                for href in [a.get("href", "")]
                if href and _is_image_url(href)
            )
            if hrefs:
                return hrefs

    # Gallery containers tried in priority order.
    # IMPORTANT: we stop at the FIRST selector that produces images so we don't
    # accidentally merge images from secondary carousels (e.g. "more properties").
    gallery_sels = [
        ".swiper-slide img",
        ".carousel-item img",
        ".slick-slide img",
        "[class*='gallery'] img", "[class*='galeria'] img",
        "[class*='foto'] img",   "[class*='fotos'] img",
        "[class*='photo'] img",  "[class*='photos'] img",
        "[class*='imagem'] img", "[class*='imagens'] img",
        "[class*='slider'] img",
        "figure img",
    ]
    for sel in gallery_sels:
        imgs = _collect(_from_img(img) for img in scope.select(sel))
        if imgs:
            return imgs

    # Background-image styles (used by some CSS-only carousels)
    bg_imgs = _collect(
        m.group(1)
        for el in scope.find_all(style=True)
        for m in [re.search(r"url\(['\"]?(https?://[^'\")\s]+)['\"]?\)", el.get("style", ""))]
        if m
    )
    if bg_imgs:
        return bg_imgs

    # Last-resort fallback: all <img> filtered by platform-specific URL patterns.
    # Deliberately narrow — generic extensions like .jpg alone match logos/banners.
    fallback = _collect(
        src for img in scope.find_all("img")
        for src in [_from_img(img)]
        if src and any(h in src.lower() for h in _PHOTO_HINTS)
    )
    return fallback


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

    @staticmethod
    def _extract_detail_images(soup: BeautifulSoup, base_url: str) -> list:
        """Delegate to module-level helper."""
        return extract_detail_images(soup, base_url)

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

    async def _scrape_url_pages(self, start_url: str, scroll: bool = False) -> list:
        """
        Generic URL-pagination loop for subclasses that paginate via URL.
        Calls _get_next_page_url(soup, current_url) after each page.
        Stops when a page yields no new results or _get_next_page_url returns None.
        Pass scroll=True to scroll-trigger lazy-loaded cards before parsing.
        """
        all_results = []
        seen_urls: set = set()
        current_url = start_url

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

                    if scroll:
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(1500)
                        await page.evaluate("window.scrollTo(0, 0)")
                        await page.wait_for_timeout(500)

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
                await page.goto(self.url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(1000)

                # Scroll to trigger lazy-loaded content
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(800)
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(400)

                # Click "Ver mais" until button disappears or max_pages reached
                clicks = 0
                while clicks < self.max_pages - 1:
                    btn = await page.query_selector("button.btn-next, .pagination-cell button, .pagination button")
                    if not btn:
                        break
                    try:
                        await btn.click(timeout=10000)
                        await page.wait_for_timeout(1500)
                        clicks += 1
                    except Exception:
                        break

                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")
                results = self._parse_page(soup, self.url)
                return results
            finally:
                await browser.close()
