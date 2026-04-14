import re
from urllib.parse import urljoin, unquote, urlparse, parse_qs, urlencode, urlunparse
from bs4 import BeautifulSoup
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int
from scrapers.platforms.kenlo import KenloScraper


class SmtximobScraper(KenloScraper):
    """
    Scraper for sites running on the SmtxiMob platform (wssite.smtximob.com CDN).
    This is a Next.js app where each card is a <a href="/imovel/{id}"> with full data.

    Unlike adriana (Smartimob), these sites include proper <a href> links so no
    click-navigate is needed.

    Text content of each card (lines):
      1. Neighborhood
      2. "Neighborhood - City"
      3. Full title (e.g. "Casa para Locação no Travessão em Dois Irmãos")
      4. "#code"
      5+. Area (e.g. "130m²"), optional "N Vagas", "N Quartos"
      Then: "VENDA" / "LOCAÇÃO" label followed by "R$ price"

    Images: srcset URLs from /_next/image?url=<encoded-original-url>
    """

    CARD_SELECTOR = 'a[href*="/imovel/"]'
    _CARD_HREF_RE = re.compile(r"^/imovel/\d+")

    def _parse_card(self, card, base_url: str):
        try:
            href = card.get("href", "")
            if not self._CARD_HREF_RE.match(href):
                return None
            source_url = urljoin(base_url, href)

            # Get full text, normalise whitespace (incl. non-breaking spaces)
            raw_text = card.get_text(separator="\n")
            raw_text = raw_text.replace("\xa0", " ")  # NBSP → space
            lines = [ln.strip() for ln in raw_text.splitlines()
                     if ln.strip() and ln.strip() not in ("VER DETALHES", "Consulte")]

            # Line 1: neighborhood, Line 2: "Bairro - Cidade"
            neighborhood = lines[0] if lines else ""
            city = "Dois Irmãos"
            if len(lines) > 1 and " - " in lines[1]:
                city = lines[1].split(" - ", 1)[-1].strip()

            # Title: longest descriptive line (usually line 3)
            title = ""
            for line in lines[2:6]:
                if len(line) > 10 and not line.startswith("#") and "m²" not in line and line not in ("m²",):
                    title = line
                    break

            category = self._detect_category(title, source_url)

            # Parse features and price from raw_text with regex
            # (BeautifulSoup may split "130m²" → "130" + "m²" across lines)
            bedrooms = bathrooms = parking_spots = area_m2 = land_area_m2 = None
            price = None

            # Area: look for number followed by m² (possibly with space or on adjacent lines)
            for m in re.finditer(r"(\d[\d.,]*)\s*m²", raw_text, re.IGNORECASE):
                area_val = normalize_area(m.group(0))
                if area_val:
                    if area_val >= 10000:
                        land_area_m2 = area_val
                    else:
                        area_m2 = area_val
                    break

            # Features
            for line in lines:
                lower = line.lower()
                if "vaga" in lower:
                    parking_spots = normalize_int(line)
                if "quarto" in lower or "dorm" in lower:
                    bedrooms = normalize_int(line)
                if "banheiro" in lower or " wc" in lower:
                    bathrooms = normalize_int(line)

            # Price: find R$ value after transaction label (case-insensitive)
            # aluguel → look for "locação" then R$; compra → "venda" then R$
            tt_keyword = "locação" if self.transaction_type == "aluguel" else "venda"
            for i, line in enumerate(lines):
                if tt_keyword in line.lower() and i + 1 < len(lines):
                    candidate = lines[i + 1]
                    if candidate.startswith("R$") or candidate.startswith("R$ "):
                        price = normalize_price(candidate)
                        break

            # Images: extract original URL from Next.js /_next/image?url=... srcset
            images = []
            for img in card.find_all("img"):
                srcset = img.get("srcset", "")
                # Take first srcset entry (smallest), decode the url= param
                m = re.search(r"/_next/image\?url=([^&\s]+)", srcset)
                if m:
                    orig_url = unquote(m.group(1))
                    if orig_url and orig_url not in images:
                        images.append(orig_url)
                else:
                    src = img.get("src", "")
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

    def _parse_page(self, soup: BeautifulSoup, base_url: str) -> list:
        cards = soup.select(self.CARD_SELECTOR)
        results = []
        for card in cards:
            href = card.get("href", "")
            if self._CARD_HREF_RE.match(href):
                prop = self._parse_card(card, base_url)
                if prop:
                    results.append(prop)
        return results

    def _get_next_page_url(self, soup: BeautifulSoup, current_url: str):
        parsed = urlparse(current_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        page = int(params.get("page", ["1"])[0])
        params["page"] = [str(page + 1)]
        new_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=new_query))

    async def scrape(self) -> list:
        return await self._scrape_url_pages(self.url)
