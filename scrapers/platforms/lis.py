import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int
from scrapers.platforms.kenlo import KenloScraper


class LisScraper(KenloScraper):
    """
    Scraper for Imobiliária Lis (imobiliarialis.com.br).
    Kenlo-hosted platform with a different card template.

    Card: a.card-with-buttons[href='/imovel/...']
    Text structure (pipe-separated after get_text):
      "AP0049-LISJ | Apartamento | Bairro Industrial - Dois Irmãos - RS | 2 Quartos | 1 Banheiro | 1 Vaga | Aluguel | R$ 2.200/mês"

    Images: img[src] pointing to imgs.kenlo.io
    """

    CARD_SELECTOR = "a.card-with-buttons"

    def _parse_card(self, card, base_url: str):
        try:
            href = card.get("href", "")
            if not href or "/imovel/" not in href:
                return None
            # Strip query params like ?from=rent
            clean_href = href.split("?")[0]
            source_url = urljoin(base_url, clean_href)

            raw = card.get_text(separator=" | ").replace("\xa0", " ")
            # Normalize — collapse runs of whitespace/pipes
            parts = [p.strip() for p in re.split(r"\s*\|\s*", raw) if p.strip()]

            # Category: first part that looks like a property type
            title = ""
            for p in parts:
                cat = self._detect_category(p, source_url)
                if cat != "Casa" or any(kw in p.lower() for kw in
                                         ("casa", "apto", "apartamento", "sala",
                                          "terreno", "lote", "galpão", "sobrado",
                                          "kitnet", "cobertura")):
                    title = p
                    break
            if not title:
                title = parts[1] if len(parts) > 1 else ""

            category = self._detect_category(title, source_url)

            # Location: "Neighborhood - City - UF"
            neighborhood = ""
            city = "Dois Irmãos"
            for p in parts:
                m = re.match(r"^(.+?)\s*[-–]\s*(.+?)\s*[-–]\s*\w{2}$", p)
                if m:
                    neighborhood = m.group(1).strip()
                    city = m.group(2).strip()
                    break

            # Features
            bedrooms = bathrooms = parking_spots = area_m2 = None
            for p in parts:
                lower = p.lower()
                if "quarto" in lower or "dorm" in lower:
                    bedrooms = normalize_int(p)
                elif "banheiro" in lower or " wc" in lower:
                    bathrooms = normalize_int(p)
                elif "vaga" in lower or "garagem" in lower:
                    parking_spots = normalize_int(p)
                elif "m²" in lower or "m2" in lower:
                    area_m2 = normalize_area(p)

            # Price: "R$ 2.200/mês" or "R$ 450.000"
            price = None
            for p in parts:
                if p.startswith("R$"):
                    price = normalize_price(re.sub(r"/\w+", "", p))
                    break

            # Images
            images = []
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
            href = card.get("href", "").split("?")[0]
            if href and "/imovel/" in href and href not in seen:
                seen.add(href)
                prop = self._parse_card(card, base_url)
                if prop:
                    results.append(prop)
        return results
