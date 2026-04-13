import asyncio
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int
from scrapers.platforms.kenlo import KenloScraper


class VistaScraper(KenloScraper):
    """Scraper for sites running on Vista Soft platform."""

    CARD_SELECTOR = "article.imovel"
    NEXT_PAGE_SELECTOR = ""  # not used directly

    def _parse_card(self, card, base_url: str):
        try:
            a = card.select_one("a.imolink")
            if not a:
                return None
            source_url = a.get("href", "")
            if not source_url:
                return None
            if not source_url.startswith("http"):
                source_url = urljoin(base_url, source_url)

            h3 = card.select_one("figure span.ft h3, figure h3, h3")
            neighborhood = h3.get_text(strip=True) if h3 else ""

            cat_el = card.select_one(".tipo-co span, .tipo-co")
            title = cat_el.get_text(strip=True) if cat_el else ""
            category = self._detect_category(title, source_url)

            price_el = card.select_one(".val span, .val")
            price = normalize_price(price_el.get_text() if price_el else None)

            bedrooms = bathrooms = parking_spots = area_m2 = land_area_m2 = None
            for li in card.select("ul li"):
                text = li.get_text(strip=True).lower()
                if "quarto" in text or "dorm" in text:
                    bedrooms = normalize_int(text)
                elif "banheiro" in text:
                    bathrooms = normalize_int(text)
                elif "vaga" in text or "garagem" in text:
                    parking_spots = normalize_int(text)
                elif "m²" in text or "m2" in text:
                    area_m2 = normalize_area(text)

            images = []
            for img in card.find_all("img"):
                src = img.get("src") or img.get("data-src", "")
                if src and not src.startswith("data:") and "loading" not in src.lower():
                    if not src.startswith("http"):
                        src = urljoin(base_url, src)
                    if src not in images:
                        images.append(src)

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
        # Vista uses trailing /N/ page number in URL
        m = re.search(r'/(\d+)/?$', current_url.split('?')[0])
        if m:
            page = int(m.group(1))
            next_url = re.sub(r'/\d+/?$', f'/{page + 1}/', current_url.split('?')[0])
            return next_url
        return None
