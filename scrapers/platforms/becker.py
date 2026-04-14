import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int
from scrapers.platforms.kenlo import KenloScraper


class BeckerScraper(KenloScraper):
    """
    Scraper for Empreendimentos Becker (empreendimentosbecker.com.br).
    Custom .NET platform with 'carteira' URL param (L=locacao, V=venda).

    Card structure (.imovel):
      img[src]                        → thumbnail (relative URL)
      h4 > b.text-primary             → category ("Apartamento")
      h4 > small#cidade               → "Bela Vista - Dois Irmãos"
      div.valor                       → "R$ 880,00"
      span[title*="Código do imóvel"] → includes property code in title attr

    Property URL: /Imoveis/Detalhes/{code}/{L_or_V}
    Pagination: /Imoveis/Busca/{page}/0 in the URL path
    """

    CARD_SELECTOR = ".imovel"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # carteira=L → aluguel, carteira=V → compra
        m = re.search(r"carteira=([LV])", self.url)
        self._carteira = m.group(1) if m else ("L" if self.transaction_type == "aluguel" else "V")

    def _page_url(self, n: int) -> str:
        """Replace page number in path: /Imoveis/Busca/{n}/0"""
        return re.sub(r"/Busca/\d+/", f"/Busca/{n}/", self.url)

    async def scrape(self) -> list:
        all_results = []
        seen_urls: set = set()

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

                for page_num in range(1, self.max_pages + 1):
                    page_url = self._page_url(page_num)
                    await page.goto(page_url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(1000)

                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    results = self._parse_page(soup, page_url)

                    new_results = [r for r in results if r.source_url not in seen_urls]
                    for r in new_results:
                        seen_urls.add(r.source_url)
                    all_results.extend(new_results)

                    if not new_results:
                        break
            finally:
                await browser.close()

        return all_results

    def _parse_card(self, card, base_url: str):
        try:
            # Property code from span title attr: "Código do imóvel: 2228"
            code_span = card.find("span", title=re.compile(r"Código do imóvel:", re.I))
            if not code_span:
                return None
            m = re.search(r"\d+", code_span["title"])
            if not m:
                return None
            code = m.group(0)

            parsed = urljoin(base_url, "/")
            base = parsed.rstrip("/")
            source_url = f"{base}/Imoveis/Detalhes/{code}/{self._carteira}"

            # Category
            b = card.select_one("h4 b.text-primary")
            category_text = b.get_text(strip=True) if b else ""
            category = self._detect_category(category_text, source_url)

            # Neighborhood
            loc = card.select_one("h4 small#cidade, h4 small")
            neighborhood = ""
            if loc:
                text = loc.get_text(strip=True)
                # "Bela Vista - Dois Irmãos"
                parts = re.split(r"\s*[-–]\s*", text)
                neighborhood = parts[0].strip() if parts else text

            # Price
            valor = card.select_one("div.valor")
            price = normalize_price(valor.get_text() if valor else None)

            # Features: look for fa icons
            bedrooms = bathrooms = parking_spots = area_m2 = None
            for icon in card.find_all("i", class_=re.compile(r"fa-")):
                classes = " ".join(icon.get("class", []))
                parent_text = icon.parent.get_text(strip=True) if icon.parent else ""
                if "fa-bed" in classes:
                    bedrooms = normalize_int(parent_text)
                elif "fa-bath" in classes or "fa-shower" in classes:
                    bathrooms = normalize_int(parent_text)
                elif "fa-car" in classes:
                    parking_spots = normalize_int(parent_text)
                elif "fa-expand" in classes or "fa-arrows" in classes:
                    area_m2 = normalize_area(parent_text)

            # Image: thumbnail is relative
            images = []
            img = card.find("img")
            if img:
                src = img.get("src", "")
                if src and not src.startswith("data:"):
                    if not src.startswith("http"):
                        src = urljoin(base_url, src)
                    images.append(src)

            return PropertyData(
                source_site=self.site_name, source_url=source_url,
                title=category_text or category,
                city="Dois Irmãos", neighborhood=neighborhood,
                category=category, transaction_type=self.transaction_type,
                price=price, bedrooms=bedrooms, bathrooms=bathrooms,
                parking_spots=parking_spots, area_m2=area_m2,
                land_area_m2=None, images=images,
            )
        except Exception:
            return None
