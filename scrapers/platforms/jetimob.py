import asyncio
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int
from scrapers.platforms.kenlo import KenloScraper


class JetimobScraper(KenloScraper):
    """Scraper for sites running on Jetimob platform.

    Supports two generations:
      V1: cards are .CardProperty with <a href> children and dt/strong feature pairs
      V2: cards are [itemtype*="schema.org/Product"] with inline text; used by
          felippe_alfredo (habbitar uses offset/limit pagination and V1 selectors)

    V2 card text (lines):
      1. Category ("Apartamento")
      2. Neighborhood ("Centro")
      3. "Neighborhood, City - UF"
      4. "109m²2 quartos1 banheiro1 vaga"  ← features concatenated by BS4
      5. "Alugar" / "Comprar"
      6. "R$ 2.200"
      7. "Cód. 98968"

    V2 link: child <a href="/imovel/...">
    """

    CARD_SELECTOR = ".CardProperty"
    NEXT_PAGE_SELECTOR = ""  # not used

    def _parse_page(self, soup: BeautifulSoup, base_url: str) -> list:
        cards = soup.select(self.CARD_SELECTOR)
        # Fallback to V2 schema.org cards if V1 yields nothing
        if not cards:
            cards = soup.select('[itemtype*="schema.org"]')
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
            source_url = urljoin(base_url, href) if not href.startswith("http") else href

            # V2 detection: schema.org itemtype present on card itself
            if card.get("itemtype"):
                return self._parse_card_v2(card, source_url)

            # V1 parsing
            # Neighborhood: find text containing "Dois Irmãos" or "Morro Reuter"
            neighborhood = ""
            for string in card.strings:
                t = string.strip()
                if "Dois Irmãos" in t or "Morro Reuter" in t:
                    neighborhood = t.split(" - ")[0].strip()
                    break

            # Title: first strong that's not a price and not "Ref.:"
            title = ""
            for strong in card.find_all("strong"):
                t = strong.get_text(strip=True)
                if t and not t.startswith("R$") and not t.startswith("Ref"):
                    title = t
                    break

            category = self._detect_category(title, source_url)

            # Price: first strong starting with R$
            price = None
            for strong in card.find_all("strong"):
                t = strong.get_text(strip=True)
                if t.startswith("R$"):
                    price = normalize_price(t)
                    break

            # Features from dt/strong pairs
            bedrooms = bathrooms = parking_spots = area_m2 = land_area_m2 = None
            for dt in card.find_all("dt"):
                label = dt.get_text(strip=True).lower()
                strong = dt.find_next_sibling("strong") or dt.find_next("strong")
                if not strong:
                    continue
                val_text = strong.get_text(strip=True)
                if "dormit" in label or "quarto" in label:
                    bedrooms = normalize_int(val_text)
                elif "banheiro" in label or "wc" in label:
                    bathrooms = normalize_int(val_text)
                elif "vaga" in label or "garagem" in label:
                    parking_spots = normalize_int(val_text)
                elif "terreno" in label:
                    land_area_m2 = _safe_float(val_text)
                elif "área" in label or "area" in label or "metr" in label or "privativa" in label:
                    area_m2 = _safe_float(val_text)

            # Images: real loaded images (skip SVG and lazy placeholders)
            images = []
            for img in card.find_all("img"):
                src = img.get("src", "")
                if (src and not src.startswith("data:")
                        and ".svg" not in src.lower()
                        and "loading" not in src.lower()
                        and src.startswith("http")):
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

    def _parse_card_v2(self, card, source_url: str):
        """Parse a Jetimob V2 schema.org card."""
        try:
            raw = card.get_text(separator="\n").replace("\xa0", " ")
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

            # Line 0: category/type ("Apartamento", "Casa", …)
            title = lines[0] if lines else ""
            category = self._detect_category(title, source_url)

            # Line 2 (index 2): "Neighborhood, City - UF"  e.g. "Centro, Dois Irmãos - RS"
            neighborhood = ""
            city = "Dois Irmãos"
            if len(lines) > 2:
                loc = lines[2]
                # "Centro, Dois Irmãos - RS"  →  neighborhood = "Centro"
                m = re.match(r"^([^,]+),\s*(.+?)\s*-\s*\w{2}$", loc)
                if m:
                    neighborhood = m.group(1).strip()
                    city = m.group(2).strip()

            # Features line: concatenated "109m²2 quartos1 banheiro1 vaga"
            # Use raw_text regex for robustness
            bedrooms = bathrooms = parking_spots = area_m2 = None
            feat_m = re.search(r"(\d[\d.,]*)\s*m²", raw, re.IGNORECASE)
            if feat_m:
                area_m2 = normalize_area(feat_m.group(0))
            q_m = re.search(r"(\d+)\s*quarto", raw, re.IGNORECASE)
            if q_m:
                bedrooms = int(q_m.group(1))
            b_m = re.search(r"(\d+)\s*banheiro", raw, re.IGNORECASE)
            if b_m:
                bathrooms = int(b_m.group(1))
            v_m = re.search(r"(\d+)\s*vaga", raw, re.IGNORECASE)
            if v_m:
                parking_spots = int(v_m.group(1))

            # Price: "R$ 2.200" or "R$2.200"
            price = None
            p_m = re.search(r"R\$\s*[\d.,]+", raw)
            if p_m:
                price = normalize_price(p_m.group(0))

            # Images
            images = []
            for img in card.find_all("img"):
                src = img.get("src", "")
                if src and not src.startswith("data:") and ".svg" not in src.lower():
                    if not src.startswith("http"):
                        from urllib.parse import urljoin as _urljoin
                        src = _urljoin(source_url, src)
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

    def _get_next_page_url(self, soup: BeautifulSoup, current_url: str):
        parsed = urlparse(current_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        # Felippe Alfredo style: &pagina=N
        if "pagina" in params:
            try:
                page = int(params["pagina"][0])
                params["pagina"] = [str(page + 1)]
                new_query = urlencode({k: v[0] for k, v in params.items()})
                return urlunparse(parsed._replace(query=new_query))
            except (ValueError, IndexError):
                pass
        # Habbitar style: offset=1&limit=21
        if "offset" in params and "limit" in params:
            try:
                offset = int(params["offset"][0])
                limit = int(params["limit"][0])
                params["offset"] = [str(offset + limit)]
                new_query = urlencode({k: v[0] for k, v in params.items()})
                return urlunparse(parsed._replace(query=new_query))
            except (ValueError, IndexError):
                pass
        return None

    async def scrape(self) -> list:
        parsed_url = urlparse(self.url)
        params = parse_qs(parsed_url.query, keep_blank_values=True)
        use_url_pagination = "pagina" in params or ("offset" in params and "limit" in params)

        if not use_url_pagination:
            return await super().scrape()

        # Felippe Alfredo lazy-loads cards on scroll — scroll=True triggers them
        return await self._scrape_url_pages(self.url, scroll=True)


def _safe_float(text: str):
    """Extract first number from text as float."""
    text = text.replace(",", ".")
    m = re.search(r'\d+\.?\d*', text)
    return float(m.group()) if m else None
