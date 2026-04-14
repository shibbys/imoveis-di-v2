import re
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from bs4 import BeautifulSoup
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int
from scrapers.platforms.kenlo import KenloScraper


class JoelBlumeScraper(KenloScraper):
    """
    Scraper for Joel Blume Corretor (joelblumecorretor.com.br).
    Voa platform with a custom article-based template.
    CDN: cdn.voaimgs.com.br (and own upload/)

    Card: article.item
    Link: figcaption > a.ab-t-l[href] (relative, no leading slash)
    Text (pipe-separated):
      "Title | Neighborhood, City | N quartos | N suíte | N vaga | X.XXm² | Venda/Aluguel | R$ XXX.XXX,XX | Cód.: XXXXX"
    Image: img[src] or img[data-src]
    """

    CARD_SELECTOR = "article.item"

    def _parse_card(self, card, base_url: str):
        try:
            # Link is an absolute-positioned <a> inside figcaption
            a = card.select_one("figcaption a[href], a[href]")
            if not a:
                return None
            href = a["href"]
            if not href or href == "#":
                return None
            # href is relative without leading slash: "imovel/casa-..."
            if not href.startswith("http"):
                base = base_url.split("?")[0].rstrip("/")
                # Strip any path components after the domain
                from urllib.parse import urlparse
                parsed = urlparse(base_url)
                base = f"{parsed.scheme}://{parsed.netloc}"
                source_url = f"{base}/{href.lstrip('/')}"
            else:
                source_url = href

            raw = card.get_text(separator=" | ").replace("\xa0", " ")
            parts = [p.strip() for p in re.split(r"\s*\|\s*", raw)
                     if p.strip() and p.strip() not in ("Ver mais", "Novo")]

            # Title: first long descriptive part
            title = ""
            for p in parts:
                if len(p) > 10 and not re.match(r"^\d", p) and "Cód" not in p:
                    title = p
                    break

            category = self._detect_category(title, source_url)

            # Location: "Neighborhood, City" (first part containing comma + city name)
            neighborhood = ""
            city = "Dois Irmãos"
            for p in parts:
                if "," in p and ("Dois Irm" in p or "Morro Reuter" in p):
                    loc_parts = p.split(",", 1)
                    neighborhood = loc_parts[0].strip()
                    city = loc_parts[1].strip() if len(loc_parts) > 1 else city
                    break

            # Features via regex on raw text
            bedrooms = bathrooms = parking_spots = area_m2 = None
            m = re.search(r"(\d+)\s*quarto", raw, re.IGNORECASE)
            if m:
                bedrooms = int(m.group(1))
            m = re.search(r"(\d+)\s*banheiro", raw, re.IGNORECASE)
            if m:
                bathrooms = int(m.group(1))
            m = re.search(r"(\d+)\s*vaga", raw, re.IGNORECASE)
            if m:
                parking_spots = int(m.group(1))
            m = re.search(r"([\d.,]+)\s*m²", raw, re.IGNORECASE)
            if m:
                area_m2 = normalize_area(m.group(0))

            # Price
            price = None
            m = re.search(r"R\$\s*[\d.,]+", raw)
            if m:
                price = normalize_price(m.group(0))

            # Images: prefer data-src (lazy), fall back to src
            images = []
            for img in card.find_all("img"):
                src = img.get("data-src") or img.get("src", "")
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
        for card in cards:
            prop = self._parse_card(card, base_url)
            if prop:
                results.append(prop)
        return results

    def _get_next_page_url(self, soup: BeautifulSoup, current_url: str):
        parsed = urlparse(current_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        page = int(params.get("pagina", ["1"])[0])
        params["pagina"] = [str(page + 1)]
        new_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=new_query))

    async def scrape(self) -> list:
        return await self._scrape_url_pages(self.url)
