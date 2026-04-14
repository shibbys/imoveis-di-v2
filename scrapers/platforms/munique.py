import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int
from scrapers.platforms.kenlo import KenloScraper


class MuniqueScraper(KenloScraper):
    """
    Scraper for Munique Imóveis (muniqueimoveis.com.br).
    Custom platform — cards are <a href*="/imovel/"> links.

    Card text structure (lines):
      "Ref.: 2666CS"
      "Bela Vista, Dois Irmãos - RS"     ← "Neighborhood, City - UF"
      "Venda"                            ← or "Locação"
      "R$ 1.490.000,00"
      "3 dorms."
      "4 vagas"
      "3 banhs."

    Image: img[src] inside card
    """

    CARD_SELECTOR = 'a[href*="/imovel/"]'
    _CARD_HREF_RE = re.compile(r"/imovel/", re.I)

    def _parse_card(self, card, base_url: str):
        try:
            href = card.get("href", "")
            if not self._CARD_HREF_RE.search(href):
                return None
            source_url = urljoin(base_url, href)

            raw = card.get_text(separator="\n").replace("\xa0", " ")
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

            # Location: "Neighborhood, City - UF"
            neighborhood = ""
            city = "Dois Irmãos"
            for line in lines:
                # Pattern: "Bela Vista, Dois Irmãos - RS"
                m = re.match(r"^([^,]+),\s*(.+?)\s*-\s*\w{2}$", line)
                if m:
                    neighborhood = m.group(1).strip()
                    city = m.group(2).strip()
                    break

            # Category from title tag or URL
            title = ""
            for line in lines:
                if line.startswith("Ref") or line.startswith("R$") or "," in line:
                    continue
                lower = line.lower()
                if lower in ("venda", "locação", "aluguel", "compra"):
                    continue
                if re.match(r"^\d", line):
                    continue
                if len(line) > 2:
                    title = line
                    break

            category = self._detect_category(title or neighborhood, source_url)

            # Price
            price = None
            p_m = re.search(r"R\$\s*[\d.,]+", raw)
            if p_m:
                price = normalize_price(p_m.group(0))

            # Features
            bedrooms = bathrooms = parking_spots = area_m2 = None
            feat_m = re.search(r"([\d.,]+)\s*m²", raw, re.IGNORECASE)
            if feat_m:
                area_m2 = normalize_area(feat_m.group(0))
            q_m = re.search(r"(\d+)\s*(?:dorms?\.?|quartos?|dormitórios?)", raw, re.IGNORECASE)
            if q_m:
                bedrooms = int(q_m.group(1))
            b_m = re.search(r"(\d+)\s*(?:banhs?\.?|banheiros?)", raw, re.IGNORECASE)
            if b_m:
                bathrooms = int(b_m.group(1))
            v_m = re.search(r"(\d+)\s*vagas?", raw, re.IGNORECASE)
            if v_m:
                parking_spots = int(v_m.group(1))

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
