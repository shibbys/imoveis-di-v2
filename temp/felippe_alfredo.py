"""
Scraper: Felippe Alfredo Imobiliária — felippealfredoimobiliaria.com.br
Plataforma: Jetimob (CDN jetimgs.com confirma)

Estrutura do card (confirmada via debug_felippe_alfredo.html):
  O card É um <a class="vertical-property-card_info__HASH">
  → o href fica no próprio elemento (closest() retorna self)

  Seletores estáveis (CSS modules — prefixo é estável, hash muda por deploy):
    a[class*='vertical-property-card_info__']   ← o card completo
    span[class*='vertical-property-card_type__']        ← tipo (ex: "Apartamento")
    span[class*='vertical-property-card_neighborhood__'] ← bairro (ex: "Floresta")
    span[class*='contracts_priceNumber__']               ← preço (ex: "R$ 2.700")
    img.image-gallery-image                              ← foto (CDN jetimgs.com)

  URL pattern (encoda quartos):
    /imovel/apartamento-com-2-quartos-para-alugar-e-1-vaga-bairro-floresta.../98907

O problema anterior: '[class*='property-card']' catchava 208 sub-elementos por página.
  Seletor correto captura ~10-15 cards por página.

Paginação: &pagina=N
"""
import re
import asyncio
from typing import Optional
from playwright.async_api import Page
from .generic import GenericScraper
from .base import PropertyData


class FelippeAlfredoScraper(GenericScraper):
    site_name = "Felippe Alfredo"
    base_url = (
        "https://www.felippealfredoimobiliaria.com.br/alugar/apartamento"
        "?ordenacao=%22mais-recente%22&pagina=1"
        "&tipos=%22apartamento%2Ccasa%22&transacao=%22alugar%22"
    )
    transaction_type = "aluguel"
    default_city = "Dois Irmãos"

    # Jetimob: o card inteiro é um <a> — um seletor por card, não sub-elementos
    card_selectors = [
        "a[class*='vertical-property-card_info__']",  # seletor primário (Jetimob CSS modules)
        "a[class*='vertical-property-card_']",        # fallback: qualquer sub-componente do card
    ]

    async def scrape_listing_page(self, page: Page) -> list:
        # Jetimob (Next.js): espera networkidle e depois captura imagens no nível
        # da página via page.evaluate() — mais confiável que element handle, pois
        # o JS corre no contexto atual do browser e lê o DOM no momento exato.
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        try:
            await page.wait_for_function(
                "() => document.querySelectorAll(\"a[class*='vertical-property-card_info__']\").length > 0",
                timeout=10000,
            )
        except Exception:
            pass

        # Cache href → image_url construído no nível da página.
        # ESTRUTURA JETIMOB: cada imóvel tem dois <a href> irmãos com o mesmo href:
        #   1) <a class="vertical-property-card_info__..."> → texto/preço, SEM img
        #   2) <a href="/imovel/..."> (pai do carousel)     → contém img.image-gallery-image
        # Solução: iterar todos os img.image-gallery-image e subir com closest('a[href]').
        try:
            self._image_cache: dict = await page.evaluate("""() => {
                const result = {};
                document.querySelectorAll('img.image-gallery-image').forEach(img => {
                    const anchor = img.closest('a[href]');
                    if (!anchor) return;
                    const href = anchor.getAttribute('href');
                    if (!href || result[href]) return;
                    var s = img.getAttribute('src') || '';
                    if (s && s.startsWith('http')) { result[href] = s; return; }
                    var ss = img.getAttribute('srcset') || '';
                    if (ss) { result[href] = ss.split(',')[0].trim().split(' ')[0]; return; }
                    if (img.currentSrc && img.currentSrc.startsWith('http')) {
                        result[href] = img.currentSrc;
                    }
                });
                return result;
            }""")
        except Exception:
            self._image_cache = {}

        return await super().scrape_listing_page(page)

    async def _parse_card(self, card) -> Optional[PropertyData]:
        # ── Link ──────────────────────────────────────────────────────────────
        # O card É o <a> — _resolve_card_url via closest() retorna o próprio elemento
        url = await self._resolve_card_url(card, self.base_url)
        if not url:
            return None

        # ── Extração via URL (Jetimob encoda quartos no slug) ─────────────────
        url_lower = url.lower()
        bedrooms: Optional[int] = None
        qrt_match = re.search(r"com-(\d+)-quartos?", url_lower)
        if qrt_match:
            bedrooms = int(qrt_match.group(1))

        # ── Tipo / Categoria ──────────────────────────────────────────────────
        category = ""
        try:
            type_el = await card.query_selector("[class*='vertical-property-card_type__']")
            if type_el:
                category = self.normalize_category((await type_el.inner_text()).strip())
        except Exception:
            pass
        # Fallback via URL
        if not category or category == "Outro":
            tipo_match = re.search(r"/imovel/([a-z]+)", url_lower)
            if tipo_match:
                category = self.normalize_category(tipo_match.group(1))

        # ── Bairro ────────────────────────────────────────────────────────────
        neighborhood = ""
        try:
            neigh_el = await card.query_selector("[class*='vertical-property-card_neighborhood__']")
            if neigh_el:
                neighborhood = (await neigh_el.inner_text()).strip()
        except Exception:
            pass
        # Fallback: extrair "bairro-BAIRRO-em-" do slug
        if not neighborhood:
            bairro_match = re.search(r"bairro-([a-z-]+)-em-", url_lower)
            if bairro_match:
                neighborhood = bairro_match.group(1).replace("-", " ").title()

        # ── Preço ─────────────────────────────────────────────────────────────
        price = None
        try:
            price_el = await card.query_selector("[class*='contracts_priceNumber__']")
            if price_el:
                price = self.parse_price((await price_el.inner_text()).strip())
        except Exception:
            pass
        if not price:
            price = self.parse_price((await card.inner_text()).strip())

        # ── Imagem ────────────────────────────────────────────────────────────
        # Usa cache construído no nível da página (page.evaluate) para evitar
        # problemas de timing com element handles e React hydration.
        image_url = ""
        cache = getattr(self, "_image_cache", {})
        from urllib.parse import urlparse
        url_path = urlparse(url).path  # "/imovel/apartamento-.../98907"
        cached_src = cache.get(url_path) or cache.get(url_path.rstrip("/"))
        if cached_src and self._is_valid_img_src(cached_src):
            image_url = cached_src
        else:
            # Fallback: card.evaluate() direto
            try:
                src = await card.evaluate("""el => {
                    const img = el.querySelector('img.image-gallery-image')
                              || el.querySelector('img[src]');
                    if (!img) return '';
                    var s = img.getAttribute('src') || '';
                    if (s && s.startsWith('http')) return s;
                    var ss = img.getAttribute('srcset') || '';
                    if (ss) return ss.split(',')[0].trim().split(' ')[0];
                    return img.currentSrc || '';
                }""")
                src = (src or "").strip()
                if self._is_valid_img_src(src):
                    image_url = src
            except Exception:
                pass

        # ── Área ─────────────────────────────────────────────────────────────
        area_m2: Optional[float] = None
        try:
            card_text = (await card.inner_text()).strip()
            area_m2 = self.parse_area(card_text)
        except Exception:
            pass

        # Jetimob encoda a descrição no slug da URL — usa isso como título
        m = re.search(r"/imovel/([^/?#]+)", url)
        if m:
            slug = re.sub(r"-\d+$", "", m.group(1).rstrip("/"))
            slug = re.sub(r"-rs$|-sc$|-pr$|-sp$", "", slug)   # remove sufixo de estado
            title = " ".join(p.capitalize() for p in slug.split("-"))
            if len(title) > 80:
                title = title[:77] + "..."
        else:
            title = f"{category} em {neighborhood}" if category and neighborhood else category or neighborhood or "Imóvel"

        return PropertyData(
            source_site=self.site_name,
            source_url=url,
            transaction_type=self.transaction_type,
            title=title,
            city=self.default_city,
            neighborhood=neighborhood,
            category=category,
            bedrooms=bedrooms,
            area_m2=area_m2,
            price=price,
            image_url=image_url,
        )

    async def get_next_page_url(self, page: Page, current_page: int) -> Optional[str]:
        url = await super().get_next_page_url(page, current_page)
        if url:
            return url

        current_url = page.url
        match = re.search(r"pagina=(\d+)", current_url)
        if match:
            n = int(match.group(1)) + 1
            return re.sub(r"pagina=\d+", f"pagina={n}", current_url)
        return current_url + "&pagina=2"
