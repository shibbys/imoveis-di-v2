import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int
from scrapers.platforms.kenlo import KenloScraper


class ImoviewScraper(KenloScraper):
    """
    Scraper for sites running on the Imoview platform.
    CDN: cdn.imoview.com.br

    Card: a[href*='/imovel/'] (card IS the <a> element)
    Text (pipe-separated):
      "Neighborhood | City | Código. XXX | Title | Price | Area m² | N quartos | N vagas"

    Images: img.img-imovel[src]
    """

    CARD_SELECTOR = "a[href*='/imovel/']"
    _CARD_HREF_RE = re.compile(r"/imovel/", re.I)

    def _parse_card(self, card, base_url: str):
        try:
            href = card.get("href", "")
            if not self._CARD_HREF_RE.search(href):
                return None
            source_url = href if href.startswith("http") else urljoin(base_url, href)

            raw = card.get_text(separator=" | ").replace("\xa0", " ")
            parts = [p.strip() for p in re.split(r"\s*\|\s*", raw)
                     if p.strip() and p.strip() not in ("arrow_back_ios", "arrow_forward_ios",
                                                         "Previous", "Next")]

            # Text structure: Neighborhood | City | Código. XXX | Title | Price | ...
            neighborhood = parts[0] if parts else ""
            city = parts[1] if len(parts) > 1 else "Dois Irmãos"

            # Title: part containing "à venda" or "para locação"
            title = ""
            for p in parts:
                if "venda" in p.lower() or "locação" in p.lower() or "aluguel" in p.lower():
                    title = p
                    break
            if not title:
                # Fall back to first long part that isn't code/location/price
                for p in parts[2:]:
                    if (len(p) > 8 and not p.startswith("Código")
                            and not p.startswith("R$")
                            and not re.match(r"^\d", p)):
                        title = p
                        break

            category = self._detect_category(title or neighborhood, source_url)

            # Price
            price = None
            p_m = re.search(r"R\$\s*[\d.,]+", raw)
            if p_m:
                price = normalize_price(p_m.group(0))

            # Features
            bedrooms = bathrooms = parking_spots = area_m2 = None
            m = re.search(r"([\d.,]+)\s*m²", raw, re.IGNORECASE)
            if m:
                area_m2 = normalize_area(m.group(0))
            m = re.search(r"(\d+)\s*quarto", raw, re.IGNORECASE)
            if m:
                bedrooms = int(m.group(1))
            m = re.search(r"(\d+)\s*(?:banheiro|wc)", raw, re.IGNORECASE)
            if m:
                bathrooms = int(m.group(1))
            m = re.search(r"(\d+)\s*vaga", raw, re.IGNORECASE)
            if m:
                parking_spots = int(m.group(1))

            # Images: img.img-imovel
            images = []
            for img in card.find_all("img", class_="img-imovel"):
                src = img.get("src", "")
                if src and not src.startswith("data:"):
                    if not src.startswith("http"):
                        src = urljoin(base_url, src)
                    if src not in images:
                        images.append(src)
            # Fallback: any img
            if not images:
                for img in card.find_all("img"):
                    src = img.get("src", "")
                    if src and not src.startswith("data:") and ".svg" not in src.lower():
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
