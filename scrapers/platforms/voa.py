import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int
from scrapers.platforms.kenlo import KenloScraper


class VoaScraper(KenloScraper):
    """
    Scraper for sites running on the Voa Imóveis platform.
    CDN: cdn.voaimgs.com.br

    Card structure:
      ul.list-items > li > a.between.flex-wrap[href] (relative URL)
        figure > img[src]
        div.infos
          h3.tit          span.location   (e.g. "Floresta, Dois Irmãos/RS")
          div.d-flex.flex-wrap > span  (features: "2 dormitórios", "2 banheiros", ...)
          span.price      (e.g. "R$ 2.800,00")
    """

    CARD_SELECTOR = ".list-items li"
    _CARD_SELECTOR_FALLBACKS = [
        ".list-items li",
        ".properties-list li",
        ".imoveis-list li",
        "ul.lista-imoveis li",
        ".card-imovel",
        "a[href*='/imovel/']",
    ]

    def _parse_page(self, soup: BeautifulSoup, base_url: str) -> list:
        cards = soup.select(self.CARD_SELECTOR)
        if not cards:
            for sel in self._CARD_SELECTOR_FALLBACKS[1:]:
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
            a = card.find("a", href=True)
            if not a:
                return None
            href = a["href"]
            # Voa hrefs are relative without leading slash (e.g. "imovel/casa-...")
            if not href.startswith("http"):
                base = base_url.rstrip("/")
                href = href.lstrip("/")
                source_url = f"{base}/{href}"
            else:
                source_url = href

            # Title
            h3 = card.select_one("h3.tit, h3")
            title = h3.get_text(strip=True) if h3 else ""

            # Location: "Floresta, Dois Irmãos/RS" → neighborhood="Floresta"
            neighborhood = ""
            city = "Dois Irmãos"
            loc_el = card.select_one("span.location, .location")
            if loc_el:
                for icon in loc_el.find_all("i"):
                    icon.decompose()
                text = loc_el.get_text(strip=True)
                # Split on comma or " - "
                parts = re.split(r",\s*|\s+[–-]\s+", text)
                if parts:
                    neighborhood = parts[0].strip()

            category = self._detect_category(title, source_url)

            # Features from .d-flex spans
            bedrooms = bathrooms = parking_spots = area_m2 = land_area_m2 = None
            for span in card.select(".d-flex span, .features span"):
                text = span.get_text(strip=True).lower()
                if "dorm" in text or "quarto" in text:
                    bedrooms = normalize_int(text)
                elif "banheiro" in text:
                    bathrooms = normalize_int(text)
                elif "vaga" in text or "garagem" in text:
                    parking_spots = normalize_int(text)
                elif "m²" in text or "m2" in text:
                    if "terreno" in text or "lote" in text:
                        land_area_m2 = normalize_area(text)
                    else:
                        area_m2 = normalize_area(text)

            # Price
            price_el = card.select_one("span.price, .price")
            price = normalize_price(price_el.get_text() if price_el else None)

            # Images
            images = []
            for img in card.find_all("img"):
                src = img.get("src") or img.get("data-src", "")
                if src and not src.startswith("data:"):
                    if not src.startswith("http"):
                        src = urljoin(base_url, src)
                    if src not in images:
                        images.append(src)

            return PropertyData(
                source_site=self.site_name, source_url=source_url,
                title=title, city=city, neighborhood=neighborhood,
                category=category, transaction_type=self.transaction_type,
                price=price, bedrooms=bedrooms, bathrooms=bathrooms,
                parking_spots=parking_spots, area_m2=area_m2,
                land_area_m2=land_area_m2, images=images,
            )
        except Exception:
            return None

    def _get_next_page_url(self, soup: BeautifulSoup, current_url: str):
        parsed = urlparse(current_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        page = int(params.get("pagina", ["1"])[0])
        params["pagina"] = [str(page + 1)]
        new_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=new_query))

    async def scrape(self) -> list:
        return await self._scrape_url_pages(self.url)
