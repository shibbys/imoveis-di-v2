import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scrapers.base import PropertyData, normalize_price, normalize_int
from scrapers.platforms.kenlo import KenloScraper


class TecimobScraper(KenloScraper):
    """Scraper for sites running on Tecimob platform."""

    CARD_SELECTOR = "a.box-imovel"
    NEXT_PAGE_SELECTOR = ""  # not used

    def _parse_card(self, card, base_url: str):
        try:
            href = card.get("href", "")
            if not href:
                return None
            source_url = urljoin(base_url, href)

            # Neighborhood from h4 — strip icon text
            neighborhood = ""
            h4 = card.select_one("h4")
            if h4:
                # Remove icon elements
                for icon in h4.find_all("i"):
                    icon.decompose()
                text = h4.get_text(strip=True)
                neighborhood = text.split(" - ")[0].strip()

            # Category from .imo-title
            cat_el = card.select_one(".imo-title")
            title = cat_el.get_text(strip=True) if cat_el else ""
            category = self._detect_category(title, source_url)

            # Price
            price_el = card.select_one(".price")
            price = normalize_price(price_el.get_text() if price_el else None)

            # Features from .imo-caracs — use img src to identify type
            bedrooms = bathrooms = parking_spots = None
            for feat in card.select(".imo-caracs > div"):
                img = feat.find("img")
                qtd = feat.select_one(".qtd")
                if not img or not qtd:
                    continue
                src = img.get("src", "").lower()
                val = normalize_int(qtd.get_text(strip=True))
                if "quarto" in src or "dorm" in src:
                    bedrooms = val
                elif "banheiro" in src or "wc" in src:
                    bathrooms = val
                elif "garagem" in src or "vaga" in src or "carro" in src:
                    parking_spots = val

            # Images (Tecimob uses data-src for lazy loading)
            images = []
            for img in card.find_all("img"):
                src = img.get("data-src") or img.get("src", "")
                if src and not src.startswith("/img/_layout") and not src.startswith("data:"):
                    if not src.startswith("http"):
                        src = urljoin(base_url, src)
                    if src not in images:
                        images.append(src)

            return PropertyData(
                source_site=self.site_name, source_url=source_url,
                title=title, city="Dois Irmãos", neighborhood=neighborhood,
                category=category, transaction_type=self.transaction_type,
                price=price, bedrooms=bedrooms, bathrooms=bathrooms,
                parking_spots=parking_spots, area_m2=None,
                land_area_m2=None, images=images,
            )
        except Exception:
            return None

    def _get_next_page_url(self, soup: BeautifulSoup, current_url: str):
        return None  # Tecimob uses JS pagination
