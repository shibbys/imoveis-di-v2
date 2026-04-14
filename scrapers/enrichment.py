"""
Detail-page image enrichment.

Called separately from the main scraper run — visits each property's source_url
and extracts the full image gallery using platform-specific selectors confirmed
against real pages.

Lookup order: site_name → platform → empty list (not yet configured).

Usage:
    from scrapers.enrichment import fetch_detail_images
    images = await fetch_detail_images(site_name="dois_irmaos", platform="kenlo", url=prop.source_url)
"""

import asyncio
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


# ---------------------------------------------------------------------------
# Gallery selectors — CSS selectors that match ALL gallery <img> elements on
# the detail page.  Confirmed one-by-one against real pages.
#
# Lookup: _BY_SITE takes precedence over _BY_PLATFORM (for sites on the same
# platform whose deployments have different HTML structures, e.g. habbitar vs
# felippe_alfredo both on jetimob).
# ---------------------------------------------------------------------------

# Site-name-specific overrides (aluguel and compra variants share the same
# detail page layout so they share an entry via a helper at the bottom).
_BY_SITE: dict[str, str] = {
    # dapper — LightGallery thumbnail strip; all items in DOM; absolute URLs
    "dapper":   ".lg-thumb-item img",
    # dmk — imoview platform; li items with <img>; last item uses background-image (skipped)
    "dmk":      ".galeria-vs2 img",
    # lis — Kenlo platform but different detail layout: thumbnail strip already in DOM
    "lis":      ".digital-thumbnails img",
    # platano — Smartimob platform; multi-frame carousel, each photo repeated 3× as
    # prev/center/next — seen set deduplicates; logo overlays lack data-nimg="fill"
    "platano":  "img[data-nimg='fill']",
    # habbitar — styled-components carousel (NOT Slick); 3 WrapperImage slides are
    # pre-rendered in the DOM. Remaining photos require carousel interaction (skipped).
    # WrapperImage is the stable display name on the styled-component div.
    "habbitar": ".WrapperImage img",
    # adriana — Next.js thumbnail strip at bottom of gallery; container has
    # overflow-x-auto, each button holds one image with data-nimg="fill".
    # src already contains the full-size /_next/image?...&w=3840 absolute URL.
    "adriana": "[class*='overflow-x-auto'] button img[data-nimg='fill']",
}

# Platform-level defaults (used when site_name not in _BY_SITE)
_BY_PLATFORM: dict[str, str] = {
    # dois_irmaos — .top-listing > .gallery-slider-full.photos > .slider-wrap img
    "kenlo":      ".top-listing .gallery-slider-full.photos .slider-wrap img",
    # sao_miguel — Slick carousel; :not(.slick-cloned) prevents duplicate clones
    "voa":        ".slick-list .slick-slide:not(.slick-cloned) img",
    # becker — #galeria Slick carousel; img src is root-relative (see _USE_ORIGIN)
    "becker":     "#galeria .slick-slide img",
    # felippe_alfredo — Next.js CSS Modules mosaic; match on stable class prefix
    "jetimob":    "[class*='media-gallery-tour-mosaic_imageItem'] img",
    # identita — ImobiBrasil Glide.js carousel; all slides in DOM, no virtualisation
    "imobibrasil": ".lista-inicial-container img.item-lista",
    # munique — custom data-slider; all [data-item] divs rendered; src is root-relative
    "munique":     "[data-item] img",
    # postai/confianca — Tecimob platform; all figures (incl. hidden d-none) in DOM
    "tecimob":     'figure[data-gallery="gallery-fotos"] img',
    # conecta — Next.js CSS Modules mosaic; all slides in DOM; absolute CDN URLs
    "conecta":     "[class*='GalleryPiecesProperties_container_img'] img",
}

# Anchor-based galleries: image URLs live in <a> href/data-* attributes, not <img>.
# The fancybox triggers are always present in the DOM before the gallery opens —
# no need to interact with the carousel (which virtualises slides).
# Value: (CSS selector, attribute name containing the image URL)
_ANCHOR_BY_PLATFORM: dict[str, tuple[str, str]] = {
    # investir — Vista Soft platform uses <a data-fancybox href="cdn.vistahost...">
    "vista": ("a[data-fancybox]", "href"),
}
_ANCHOR_BY_SITE: dict[str, tuple[str, str]] = {
    # joel_blume — VOA platform but static fancybox grid (not Slick); all <a> in DOM
    "joel_blume": ('a[data-fancybox="imovel"]', "href"),
}

# Platforms whose img src paths are root-relative WITHOUT a leading slash
# (e.g. "viasw/fotos/123.jpg"). urljoin must use the site origin, not the
# full page URL, otherwise the path resolves into the page's directory.
_USE_ORIGIN: set[str] = {"becker"}

# Sites whose gallery is hidden behind a React/JS state change (lightbox not open
# on initial load). A click is needed to reveal the thumbnail strip before extraction.
# Value: (click_selector, wait_selector_after_click)
# The extract selector is the regular _BY_SITE entry (unchanged).
_CLICK_TO_REVEAL: dict[str, tuple[str, str]] = {
    # adriana — Smartimob: thumbnail strip is React lightbox state, only rendered
    # after clicking a mosaic image. Click any gallery photo, then wait for the strip.
    "adriana": (
        "img[data-nimg='fill']",              # click first visible gallery image
        "[class*='overflow-x-auto'] button",  # wait for lightbox thumbnail strip
    ),
    # felippe_alfredo — Jetimob V2: clicking any mosaic image opens a full-screen modal
    # (media-gallery-tour_modal) that renders the complete image grid (all N photos).
    # Without the click, only the initial 3-image preview mosaic is in the DOM.
    "felippe_alfredo": (
        "[class*='media-gallery-tour-mosaic_imageItem'] img",  # click first preview img
        "[class*='media-gallery-tour_modal']",                  # wait for full modal
    ),
}

# ---------------------------------------------------------------------------
# Helper: register compra/aluguel variants that share the same selector
# ---------------------------------------------------------------------------
def _mirror(base_site: str) -> None:
    """Register _aluguel and _compra variants with the same img selector as base."""
    sel = _BY_SITE.get(base_site)
    if sel:
        _BY_SITE[f"{base_site}_aluguel"] = sel
        _BY_SITE[f"{base_site}_compra"] = sel


def _mirror_anchor(base_site: str) -> None:
    """Register _aluguel and _compra variants with the same anchor selector as base."""
    rule = _ANCHOR_BY_SITE.get(base_site)
    if rule:
        _ANCHOR_BY_SITE[f"{base_site}_aluguel"] = rule
        _ANCHOR_BY_SITE[f"{base_site}_compra"] = rule


def _mirror_click(base_site: str) -> None:
    """Register _aluguel and _compra variants with the same click rule as base."""
    rule = _CLICK_TO_REVEAL.get(base_site)
    if rule:
        _CLICK_TO_REVEAL[f"{base_site}_aluguel"] = rule
        _CLICK_TO_REVEAL[f"{base_site}_compra"] = rule


_mirror("habbitar")
_mirror("adriana")
_mirror("dapper")
_mirror("dmk")
_mirror("lis")
_mirror("platano")
_mirror_anchor("joel_blume")
_mirror_click("adriana")
_mirror_click("felippe_alfredo")


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def _img_src(img) -> str:
    """Return the best available src from an <img> tag (handles lazy loading)."""
    for attr in ("data-src", "data-lazy-src", "data-original", "src"):
        val = img.get(attr, "")
        if val and not val.startswith("data:"):
            return val
    return ""


def extract_images_from_soup(
    soup: BeautifulSoup,
    site_name: str,
    platform: str,
    base_url: str,
) -> list[str]:
    """
    Extract all gallery images from an already-rendered detail page soup.
    Returns absolute URLs, deduped, in document order.
    """
    images: list[str] = []
    seen: set[str] = set()

    def _add(src: str) -> None:
        if not src or src.startswith("data:"):
            return
        if src.lower().endswith(".svg"):
            return
        if not src.startswith("http"):
            src = urljoin(base_url, src)
        if src not in seen:
            seen.add(src)
            images.append(src)

    # Anchor-based galleries (fancybox / lightbox triggers already in the DOM)
    anchor_rule = _ANCHOR_BY_SITE.get(site_name) or _ANCHOR_BY_PLATFORM.get(platform)
    if anchor_rule:
        sel, attr = anchor_rule
        for a in soup.select(sel):
            _add(a.get(attr, ""))
        return images

    # Standard img-based galleries
    selector = _BY_SITE.get(site_name) or _BY_PLATFORM.get(platform)
    if selector:
        for img in soup.select(selector):
            _add(_img_src(img))

    return images


async def enrich_properties_batch(
    items: list[dict],
    on_progress: Optional[Callable[[str, int, int], None]] = None,
    concurrency: int = 2,
) -> dict[str, list[str]]:
    """
    Fetch gallery images for multiple properties using a pool of parallel tabs.

    items: list of {"id": str, "site_name": str, "platform": str, "url": str}
    on_progress(imovel_id, current_index, total): optional callback after each item.
    concurrency: simultaneous browser tabs (default 2 — speed vs. rate-limit balance).

    Strategy per page:
      - wait_until="load" (faster than networkidle for SSR/static galleries)
      - wait_for_selector(gallery_css, timeout=8s) to confirm gallery is in DOM
      - fallback: extract whatever is there if selector times out

    Returns {imovel_id: [image_urls]}.
    Skips items whose site/platform has no selector configured.
    """
    eligible = [
        it for it in items
        if (
            it["site_name"] in _BY_SITE or it["platform"] in _BY_PLATFORM
            or it["site_name"] in _ANCHOR_BY_SITE or it["platform"] in _ANCHOR_BY_PLATFORM
            or it["site_name"] in _CLICK_TO_REVEAL
        )
    ]
    if not eligible:
        return {}

    results: dict[str, list[str]] = {}
    total = len(eligible)
    counter = [0]  # mutable for closure; asyncio is single-threaded so no lock needed

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

            # Build a pool of reusable pages
            n_pages = min(concurrency, total)
            page_pool: asyncio.Queue = asyncio.Queue()
            for _ in range(n_pages):
                p = await ctx.new_page()
                await p.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                await page_pool.put(p)

            async def _process(item: dict) -> None:
                page = await page_pool.get()
                try:
                    imovel_id = item["id"]
                    site_name = item["site_name"]
                    platform  = item["platform"]
                    url       = item["url"]

                    if platform in _USE_ORIGIN:
                        parsed = urlparse(url)
                        base_url = f"{parsed.scheme}://{parsed.netloc}"
                    else:
                        base_url = url

                    # Pick the CSS selector to wait for (confirms gallery is in DOM)
                    anchor_rule = _ANCHOR_BY_SITE.get(site_name) or _ANCHOR_BY_PLATFORM.get(platform)
                    wait_sel = anchor_rule[0] if anchor_rule else (
                        _BY_SITE.get(site_name) or _BY_PLATFORM.get(platform)
                    )

                    try:
                        await page.goto(url, wait_until="load", timeout=30000)
                        if wait_sel:
                            try:
                                await page.wait_for_selector(wait_sel, timeout=8000)
                            except Exception:
                                pass  # selector absent — still attempt extraction

                        # Some sites hide their full gallery behind a JS interaction
                        # (e.g. clicking opens a React lightbox with all thumbnails).
                        click_rule = _CLICK_TO_REVEAL.get(site_name)
                        if click_rule:
                            click_sel, wait_after = click_rule
                            try:
                                el = await page.query_selector(click_sel)
                                if el:
                                    await el.click()
                                    await page.wait_for_selector(wait_after, timeout=5000)
                            except Exception:
                                pass  # fallback: extract whatever loaded

                        html = await page.content()
                        soup = BeautifulSoup(html, "html.parser")
                        images = extract_images_from_soup(soup, site_name, platform, base_url)
                        results[imovel_id] = images
                    except Exception:
                        results[imovel_id] = []

                    counter[0] += 1
                    if on_progress:
                        on_progress(imovel_id, counter[0], total)
                finally:
                    await page_pool.put(page)

            await asyncio.gather(*[_process(item) for item in eligible])

        finally:
            await browser.close()

    return results


async def fetch_detail_images(
    site_name: str,
    platform: str,
    url: str,
) -> list[str]:
    """
    Load a property detail page with Playwright and return its gallery images.
    Returns an empty list if the site/platform has no selector configured yet.
    """
    has_selector = (
        site_name in _BY_SITE or platform in _BY_PLATFORM
        or site_name in _ANCHOR_BY_SITE or platform in _ANCHOR_BY_PLATFORM
        or site_name in _CLICK_TO_REVEAL
    )
    if not has_selector:
        return []

    # Some platforms use root-relative src paths without a leading slash.
    # Resolve against origin, not the full page URL.
    if platform in _USE_ORIGIN:
        p = urlparse(url)
        base_url = f"{p.scheme}://{p.netloc}"
    else:
        base_url = url

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
            anchor_rule = _ANCHOR_BY_SITE.get(site_name) or _ANCHOR_BY_PLATFORM.get(platform)
            wait_sel = anchor_rule[0] if anchor_rule else (
                _BY_SITE.get(site_name) or _BY_PLATFORM.get(platform)
            )
            await page.goto(url, wait_until="load", timeout=30000)
            if wait_sel:
                try:
                    await page.wait_for_selector(wait_sel, timeout=8000)
                except Exception:
                    pass
            click_rule = _CLICK_TO_REVEAL.get(site_name)
            if click_rule:
                click_sel, wait_after = click_rule
                try:
                    el = await page.query_selector(click_sel)
                    if el:
                        await el.click()
                        await page.wait_for_selector(wait_after, timeout=5000)
                except Exception:
                    pass
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            return extract_images_from_soup(soup, site_name, platform, base_url)
        finally:
            await browser.close()
