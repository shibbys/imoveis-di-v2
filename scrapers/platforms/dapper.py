import re
import json
from urllib.parse import urlparse, parse_qs, urlencode
from scrapers.base import BaseScraper, PropertyData, normalize_price


_API_BASE = "https://dapperimoveis.com.br/Services/RealEstate/JSONP/List.aspx"
_SITE_BASE = "https://www.dapperimoveis.com.br"


class DapperScraper(BaseScraper):
    """
    Scraper for Dapper Imóveis (dapperimoveis.com.br).
    Uses the internal JSONP/JSON API instead of the Svelte SPA.

    The site URL uses hash-based routing:
      /imoveis/vendas#tipo_negociacao=2&tipo_imovel=54,62,59&cidade=...

    The Svelte app calls:
      /Services/RealEstate/JSONP/List.aspx?mode=realties&callback=null&{same_params}&pageSize=33

    Response JSON:
      { CurrentPage, NumberOfPages, NumberOfItems, Items: [
          { Id, MLSID, Title, Price, CurrentRealtyTypeTitle,
            CurrentNegotiationTypeTitle, Bedrooms, Bathrooms, ParkingSpots,
            Area, LotArea,
            CurrentSpot: { City, Neighborhood, Latitude, Longitude },
            Photos: [{ Path }] }
      ]}

    Latitude/Longitude are integers scaled by 10^7:
      e.g. -295883462 → -29.5883462 (Dois Irmãos, RS)
    """

    def _hash_params(self) -> dict:
        """Extract params from the URL hash fragment."""
        parsed = urlparse(self.url)
        fragment = parsed.fragment  # e.g. "tipo_negociacao=2&tipo_imovel=54,..."
        if not fragment:
            return {}
        return {k: v[0] for k, v in parse_qs(fragment).items()}

    def _api_url(self, page: int) -> str:
        params = self._hash_params()
        params["mode"] = "realties"
        params["callback"] = "null"
        params["currentPage"] = str(page)
        params["pageSize"] = "100"  # fetch more per page to reduce requests
        return f"{_API_BASE}?{urlencode(params)}"

    def _detect_category(self, realty_type: str) -> str:
        mapping = {
            "Casa": "Casa",
            "Casa em Condomínio": "Casa",
            "Apartamento": "Apartamento",
            "Cobertura": "Cobertura",
            "Sobrado": "Sobrado",
            "Kitnet": "Kitnet",
            "Terreno": "Terreno",
            "Lote": "Terreno",
            "Sítio": "Sítio/Chácara",
            "Chácara": "Sítio/Chácara",
            "Sítio / Chácara": "Sítio/Chácara",
            "Chácara - Sítio": "Sítio/Chácara",
            "Chácara / Sítio": "Sítio/Chácara",
            "Comercial": "Comercial",
            "Sala Comercial": "Comercial",
            "Galpão": "Comercial",
        }
        return mapping.get(realty_type, realty_type or "Casa")

    async def scrape(self) -> list:
        from playwright.async_api import async_playwright

        all_results = []
        seen_ids = set()

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()

                for page_num in range(1, self.max_pages + 1):
                    api_url = self._api_url(page_num)

                    # Capture the JSON response via network interception
                    response_data = {}

                    async def handle_response(resp):
                        if "List.aspx" in resp.url and "mode=realties" in resp.url:
                            try:
                                body = await resp.text()
                                # Response is plain JSON (callback=null)
                                response_data["body"] = body
                            except Exception:
                                pass

                    page.on("response", handle_response)
                    await page.goto(api_url, wait_until="networkidle", timeout=20000)
                    page.remove_listener("response", handle_response)

                    raw = response_data.get("body") or await page.content()
                    # Strip possible JSONP wrapper
                    raw = re.sub(r"^[^{]*", "", raw).strip().rstrip(";)")

                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        # Try to extract JSON from HTML (page.content wraps in html tags)
                        m = re.search(r"\{.*\}", raw, re.DOTALL)
                        if not m:
                            break
                        data = json.loads(m.group(0))

                    items = data.get("Items") or data.get("items") or []
                    total_pages = data.get("NumberOfPages", 1)

                    for item in items:
                        imovel_id = str(item.get("Id", ""))
                        if not imovel_id or imovel_id in seen_ids:
                            continue
                        seen_ids.add(imovel_id)

                        mlsid = item.get("MLSID") or item.get("ReferenceId", "")
                        source_url = f"{_SITE_BASE}/imovel/{mlsid}" if mlsid else (
                            f"{_SITE_BASE}/imovel/{item.get('CurrentNegotiationTypeTitle','Vendas')}/{imovel_id}"
                        )

                        spot = item.get("CurrentSpot") or {}
                        neighborhood = spot.get("Neighborhood") or ""
                        city = spot.get("City") or "Dois Irmãos"

                        realty_type = item.get("CurrentRealtyTypeTitle", "")
                        title = item.get("Title") or realty_type
                        category = self._detect_category(realty_type)

                        price = None
                        if item.get("ShowPrice", True):
                            price_val = item.get("Price") or item.get("FullPrice")
                            if price_val:
                                price = float(price_val)

                        bedrooms = item.get("Bedrooms") or None
                        bathrooms = item.get("Bathrooms") or None
                        parking_spots = item.get("ParkingSpots") or None
                        area_raw = item.get("Area") or 0
                        area_m2 = float(area_raw) if area_raw > 0 else None
                        land_raw = item.get("LotArea") or 0
                        land_area_m2 = float(land_raw) if land_raw > 0 else None

                        # Images: Photos[].Path (relative)
                        images = []
                        for photo in item.get("Photos") or []:
                            path = photo.get("Path", "")
                            if path and not path.startswith("data:"):
                                img_url = f"{_SITE_BASE}{path}" if not path.startswith("http") else path
                                if img_url not in images:
                                    images.append(img_url)
                        # Fallback to main image
                        main_img = item.get("Image", "")
                        if main_img and not main_img.startswith("data:"):
                            img_url = f"{_SITE_BASE}{main_img}" if not main_img.startswith("http") else main_img
                            if img_url not in images:
                                images.append(img_url)

                        all_results.append(PropertyData(
                            source_site=self.site_name,
                            source_url=source_url,
                            title=title,
                            city=city,
                            neighborhood=neighborhood,
                            category=category,
                            transaction_type=self.transaction_type,
                            price=price,
                            bedrooms=bedrooms,
                            bathrooms=bathrooms,
                            parking_spots=parking_spots,
                            area_m2=area_m2,
                            land_area_m2=land_area_m2,
                            images=images,
                        ))

                    if page_num >= total_pages:
                        break

            finally:
                await browser.close()

        return all_results
