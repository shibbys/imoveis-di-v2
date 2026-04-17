"""
Dedicated scraper for Felippe Alfredo Imobiliária (Jetimob V2 / Next.js).

Strategy (in order of reliability):
  1. __NEXT_DATA__ — Next.js SSR script tag embeds full page props; often
     contains the complete property list before any scroll/hydration.
  2. Response interception — capture /_next/data/ and property API JSON
     responses triggered by page load and scrolling.
  3. HTML card parsing — fallback; reads rendered <a> cards from DOM.
     Unreliable on ARM64 because lazy-load timing varies.

Card selector (HTML fallback):
  a[class*='vertical-property-card_info__']
  The <a> element IS the card; its href points to /imovel/...
"""
import json
import re
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from scrapers.base import BaseScraper, PropertyData, normalize_price, normalize_area

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_CARD_SEL = "a[class*='vertical-property-card_info__']"


# ── JSON / API helpers ────────────────────────────────────────────────────────

def _is_property_obj(obj: dict) -> bool:
    """Heuristic: does this dict look like a single property listing?"""
    if not isinstance(obj, dict):
        return False
    has_id = any(k in obj for k in ("id", "codigo", "code", "referencia"))
    has_loc = any(k in obj for k in (
        "bairro", "neighborhood", "cidade", "city", "address", "logradouro",
    ))
    has_type_or_price = any(k in obj for k in (
        "tipo", "type", "categoria", "category",
        "price", "preco", "valor", "rentPrice", "salePrice",
    ))
    return has_id and has_loc and has_type_or_price


def _find_property_arrays(data, _depth: int = 0) -> list[dict]:
    """
    Recursively walk a JSON structure and return the first large array of
    property-like objects found.
    """
    if _depth > 8:
        return []
    if isinstance(data, list):
        candidates = [x for x in data if _is_property_obj(x)]
        if len(candidates) >= 3:
            return candidates
        # Recurse into list items (e.g. nested arrays)
        for item in data:
            found = _find_property_arrays(item, _depth + 1)
            if found:
                return found
        return []
    if isinstance(data, dict):
        # Prioritise keys that commonly hold property lists
        priority = ("properties", "imoveis", "listings", "items", "data", "results", "list")
        for key in priority:
            if key in data:
                found = _find_property_arrays(data[key], _depth + 1)
                if found:
                    return found
        for val in data.values():
            found = _find_property_arrays(val, _depth + 1)
            if found:
                return found
    return []


def _build_source_url(prop: dict, base_url: str) -> str | None:
    for key in ("url", "link", "permalink", "canonical"):
        val = prop.get(key, "")
        if isinstance(val, str) and "/imovel/" in val:
            return val if val.startswith("http") else urljoin(base_url, val)
    slug = (
        prop.get("slug") or prop.get("friendlyUrl") or
        prop.get("friendly_url") or prop.get("slugUrl") or ""
    )
    prop_id = prop.get("id") or prop.get("codigo") or prop.get("code") or ""
    if slug and prop_id:
        return urljoin(base_url, f"/imovel/{slug}/{prop_id}")
    return None


def _parse_api_prop(
    prop: dict, base_url: str, site_name: str, transaction_type: str
) -> PropertyData | None:
    try:
        source_url = _build_source_url(prop, base_url)
        if not source_url:
            return None

        # Category
        category = str(
            prop.get("type") or prop.get("tipo") or
            prop.get("category") or prop.get("categoria") or ""
        )
        if not category:
            m = re.search(r"/imovel/([a-z]+)", source_url.lower())
            category = m.group(1).capitalize() if m else "Imóvel"

        # Neighborhood
        nbh = (
            prop.get("neighborhood") or prop.get("bairro") or
            prop.get("district") or prop.get("distrito") or ""
        )
        if isinstance(nbh, dict):
            nbh = nbh.get("name") or nbh.get("nome") or ""
        neighborhood = str(nbh)

        # Price
        price = None
        for key in ("price", "preco", "valor", "rentPrice", "salePrice", "aluguel", "venda"):
            val = prop.get(key)
            if val is not None:
                try:
                    p = float(
                        str(val).replace(".", "").replace(",", ".")
                        .replace("R$", "").replace(" ", "").strip()
                    )
                    if p > 0:
                        price = p
                        break
                except Exception:
                    pass

        # Bedrooms
        bedrooms = None
        for key in ("bedrooms", "quartos", "rooms", "dormitorios", "dorms"):
            val = prop.get(key)
            if val is not None:
                try:
                    bedrooms = int(val)
                    break
                except Exception:
                    pass
        if bedrooms is None:
            m = re.search(r"com-(\d+)-quartos?", source_url.lower())
            if m:
                bedrooms = int(m.group(1))

        # Area
        area_m2 = None
        for key in ("area", "areaUtil", "usefulArea", "buildingArea", "totalArea", "areaTotal"):
            val = prop.get(key)
            if val is not None:
                try:
                    a = float(str(val).replace(",", "."))
                    if a > 0:
                        area_m2 = a
                        break
                except Exception:
                    pass

        # Title
        title = str(prop.get("title") or prop.get("titulo") or prop.get("name") or "")
        if not title:
            m = re.search(r"/imovel/([^/?#]+)", source_url)
            if m:
                slug = re.sub(r"-\d+$", "", m.group(1).rstrip("/"))
                slug = re.sub(r"-(rs|sc|pr|sp)$", "", slug)
                title = " ".join(p.capitalize() for p in slug.split("-"))
        title = title[:80]

        return PropertyData(
            source_site=site_name,
            source_url=source_url,
            title=title,
            city="Dois Irmãos",
            neighborhood=neighborhood,
            category=category,
            transaction_type=transaction_type,
            price=price,
            bedrooms=bedrooms,
            bathrooms=None,
            parking_spots=None,
            area_m2=area_m2,
            land_area_m2=None,
            images=[],
        )
    except Exception:
        return None


# ── HTML card helpers ─────────────────────────────────────────────────────────

def _first_text(card, class_fragment: str) -> str:
    el = card.find(class_=re.compile(re.escape(class_fragment)))
    return el.get_text(strip=True) if el else ""


def _parse_card(card, base_url: str, site_name: str, transaction_type: str) -> PropertyData | None:
    try:
        href = card.get("href", "")
        if not href:
            return None
        source_url = href if href.startswith("http") else urljoin(base_url, href)

        category = _first_text(card, "vertical-property-card_type__")
        if not category:
            m = re.search(r"/imovel/([a-z]+)", source_url.lower())
            category = m.group(1).capitalize() if m else "Imóvel"

        neighborhood = _first_text(card, "vertical-property-card_neighborhood__")
        if not neighborhood:
            m = re.search(r"bairro-([a-z-]+)-em-", source_url.lower())
            if m:
                neighborhood = m.group(1).replace("-", " ").title()

        price_text = _first_text(card, "contracts_priceNumber__")
        price = normalize_price(price_text) if price_text else None
        if not price:
            m = re.search(r"R\$\s*[\d.,]+", card.get_text())
            price = normalize_price(m.group(0)) if m else None

        bedrooms = None
        m = re.search(r"com-(\d+)-quartos?", source_url.lower())
        if m:
            bedrooms = int(m.group(1))

        area_m2 = None
        m = re.search(r"([\d.,]+)\s*m[²2]", card.get_text(), re.IGNORECASE)
        if m:
            area_m2 = normalize_area(m.group(0))

        m = re.search(r"/imovel/([^/?#]+)", source_url)
        if m:
            slug = re.sub(r"-\d+$", "", m.group(1).rstrip("/"))
            slug = re.sub(r"-(rs|sc|pr|sp)$", "", slug)
            title = " ".join(p.capitalize() for p in slug.split("-"))
            title = title[:80]
        else:
            title = f"{category} em {neighborhood}" if neighborhood else category or "Imóvel"

        return PropertyData(
            source_site=site_name,
            source_url=source_url,
            title=title,
            city="Dois Irmãos",
            neighborhood=neighborhood,
            category=category,
            transaction_type=transaction_type,
            price=price,
            bedrooms=bedrooms,
            bathrooms=None,
            parking_spots=None,
            area_m2=area_m2,
            land_area_m2=None,
            images=[],
        )
    except Exception:
        return None


# ── Scroll helper ────────────────────────────────────────────────────────────

async def _scroll_until_count(
    page, card_sel: str, target: int | None, max_seconds: int = 240
) -> None:
    """
    Scroll to bottom repeatedly until the DOM card count reaches `target`
    (extracted from "N resultados" on the page) or `max_seconds` elapses.
    If target is unknown, falls back to 5 stable rounds.

    After each scroll we wait for networkidle (so the triggered lazy-load
    fetch completes before we re-count) with a fixed fallback timeout.
    """
    import time

    start = time.monotonic()
    prev = 0
    stable = 0

    while True:
        count = await page.eval_on_selector_all(card_sel, "els => els.length")

        if target is not None and count >= target:
            break

        if time.monotonic() - start > max_seconds:
            break

        if count == prev:
            stable += 1
            if target is None and stable >= 5:
                break
        else:
            stable = 0

        prev = count
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        # Wait for the lazy-load fetch triggered by scroll to finish.
        # networkidle is more accurate than a fixed timeout, but we cap it
        # so a never-settling analytics call doesn't stall us.
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            await page.wait_for_timeout(4000)


# ── Scraper ───────────────────────────────────────────────────────────────────

class FelippeAlfredoScraper(BaseScraper):

    async def scrape(self) -> list:
        all_results: list[PropertyData] = []
        seen_urls: set[str] = set()

        parsed = urlparse(self.url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        params = parse_qs(parsed.query, keep_blank_values=True)
        # This site uses infinite scroll — all properties on a single "page".
        # We keep pagina=1 and rely on scroll + response interception.
        params["pagina"] = ["1"]
        page_url = urlunparse(
            parsed._replace(query=urlencode({k: v[0] for k, v in params.items()}))
        )

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(user_agent=_UA)
                page = await ctx.new_page()
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                # ── Strategy 2: intercept JSON API responses ──────────────────
                intercepted: list[dict] = []

                async def on_response(response):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" not in ct:
                            return
                        # No URL filter — rely on _find_property_arrays to gate quality.
                        # The lazy-load API endpoint URL is unknown; checking content is safer.
                        body = await response.body()
                        if len(body) < 200:  # skip tiny responses (tracking pixels etc.)
                            return
                        data = json.loads(body)
                        found = _find_property_arrays(data)
                        if found:
                            intercepted.extend(found)
                    except Exception:
                        pass

                page.on("response", on_response)

                # ── Load page ─────────────────────────────────────────────────
                await page.goto(page_url, wait_until="load", timeout=30000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                try:
                    await page.wait_for_selector(_CARD_SEL, timeout=10000)
                except Exception:
                    pass

                # ── Extract total count from page ("81 resultados") ───────────
                initial_html = await page.content()
                m = re.search(r"(\d+)\s+resultado", initial_html, re.IGNORECASE)
                total_expected = int(m.group(1)) if m else None

                # ── Scroll until we reach total or stable ─────────────────────
                await _scroll_until_count(page, _CARD_SEL, total_expected)

                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                # ── Strategy 1: __NEXT_DATA__ (SSR — timing-independent) ──────
                nd_script = soup.find("script", id="__NEXT_DATA__")
                if nd_script and nd_script.string:
                    try:
                        nd_props = _find_property_arrays(json.loads(nd_script.string))
                        for prop in nd_props:
                            pd = _parse_api_prop(prop, base_url, self.site_name, self.transaction_type)
                            if pd and pd.source_url and pd.source_url not in seen_urls:
                                seen_urls.add(pd.source_url)
                                all_results.append(pd)
                    except Exception:
                        pass

                # ── Strategy 2 results: intercepted API responses ─────────────
                for prop in intercepted:
                    pd = _parse_api_prop(prop, base_url, self.site_name, self.transaction_type)
                    if pd and pd.source_url and pd.source_url not in seen_urls:
                        seen_urls.add(pd.source_url)
                        all_results.append(pd)

                # ── Strategy 3: HTML card parsing (scroll-timing-dependent) ───
                for card in soup.select(_CARD_SEL):
                    pd = _parse_card(card, page_url, self.site_name, self.transaction_type)
                    if pd and pd.source_url not in seen_urls:
                        seen_urls.add(pd.source_url)
                        all_results.append(pd)

            finally:
                await browser.close()

        return all_results
