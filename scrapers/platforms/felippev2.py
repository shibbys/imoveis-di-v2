import re
import asyncio
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page
import logging

from scrapers.base import BaseScraper, PropertyData, normalize_price, normalize_area


class FelippeAlfredoV2Scraper(BaseScraper):
    """
    Scraper alternative for Felippe Alfredo based on the old temp/felippe_alfredo.py script
    that used paginated approach with pagination param (&pagina=N) instead of infinite scroll api interception.
    Contains fallback/retry mechanisms checking the expected result count on the page.
    """

    async def scrape(self) -> list:
        parsed = urlparse(self.url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            all_results: list[PropertyData] = []
            seen_urls: set[str] = set()
            expected_count: Optional[int] = None

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    # Add a realistic user agent
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                    page = await context.new_page()

                    current_url = self.url
                    page_num = 1

                    while True:
                        if page_num > self.max_pages:
                            break

                        try:
                            await page.goto(current_url, wait_until="load", timeout=30000)
                        except Exception:
                            pass
                        
                        try:
                            await page.wait_for_load_state("networkidle", timeout=15000)
                        except Exception:
                            pass
                            
                        try:
                            await page.wait_for_function(
                                "() => document.querySelectorAll(\"a[class*='vertical-property-card_info__']\").length > 0",
                                timeout=10000,
                            )
                        except Exception:
                            # Se não encontrar, pode ter chegado ao fim da paginação ou a página está vazia
                            pass
                            
                        # Extrair HTML para buscar expected_count (apenas na página 1)
                        if page_num == 1 and expected_count is None:
                            initial_html = await page.content()
                            m = re.search(r"(\d+)\s+resultado", initial_html, re.IGNORECASE)
                            if m:
                                expected_count = int(m.group(1))

                        # Scroll para forçar o carregamento (usamos scrollBy para disparar IntersectionObservers de forma robusta)
                        prev_count = 0
                        stable = 0
                        for _ in range(25):
                            try:
                                cards_len = await page.evaluate("() => document.querySelectorAll(\"a[class*='vertical-property-card_info__']\").length")
                                if cards_len > prev_count:
                                    stable = 0
                                else:
                                    stable += 1
                                    
                                if stable >= 3:
                                    break
                                    
                                prev_count = cards_len
                                # Rolar a página em pedaços (smooth scroll programático)
                                await page.evaluate("window.scrollBy(0, 1200)")
                                await asyncio.sleep(1.2)
                            except Exception:
                                break

                        # Construir cache de imagens no navegador (mesmo do script antigo)
                        try:
                            image_cache: dict = await page.evaluate("""() => {
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
                            image_cache = {}

                        # Extrair HTML da página para usar BeautifulSoup
                        html = await page.content()
                        soup = BeautifulSoup(html, "html.parser")
                        
                        # JETIMOB V2: o card primário
                        cards = soup.select("a[class*='vertical-property-card_info__']")
                        if not cards:
                            # Fallback (do script antigo)
                            cards = soup.select("a[class*='vertical-property-card_']")
                        
                        if not cards:
                            print(f"Page {page_num}: No cards found, stopping.")
                            break # Nenhum card nesta página, fim.

                        new_items_found = 0

                        for card in cards:
                            href = card.get("href")
                            if not href:
                                continue
                                
                            source_url = urljoin(base_url, href) if not href.startswith("http") else href
                            if source_url in seen_urls:
                                continue

                            # Link para acessar o cache
                            url_path = urlparse(source_url).path
                            image_url = image_cache.get(url_path) or image_cache.get(url_path.rstrip("/")) or ""

                            # ── Extração via URL (quartos encodados no slug) ─────────────────
                            url_lower = source_url.lower()
                            bedrooms = None
                            qrt_match = re.search(r"com-(\d+)-quartos?", url_lower)
                            if qrt_match:
                                bedrooms = int(qrt_match.group(1))

                            # ── Tipo / Categoria ──────────────────────────────────────────────
                            type_el = card.select_one("[class*='vertical-property-card_type__']")
                            category = type_el.get_text(strip=True) if type_el else ""
                            
                            if not category or category.lower() == "outro":
                                tipo_match = re.search(r"/imovel/([a-z]+)", url_lower)
                                if tipo_match:
                                    category = tipo_match.group(1).capitalize()

                            # ── Bairro ────────────────────────────────────────────────────────
                            neigh_el = card.select_one("[class*='vertical-property-card_neighborhood__']")
                            neighborhood = neigh_el.get_text(strip=True) if neigh_el else ""
                            
                            if not neighborhood:
                                bairro_match = re.search(r"bairro-([a-z-]+)-em-", url_lower)
                                if bairro_match:
                                    neighborhood = bairro_match.group(1).replace("-", " ").title()

                            # ── Preço ─────────────────────────────────────────────────────────
                            price_el = card.select_one("[class*='contracts_priceNumber__']")
                            price = normalize_price(price_el.get_text(strip=True)) if price_el else None
                            if not price:
                                m = re.search(r"R\$\s*[\d.,]+", card.get_text())
                                if m:
                                    price = normalize_price(m.group(0))

                            # ── Área ──────────────────────────────────────────────────────────
                            area_m2 = None
                            m = re.search(r"([\d.,]+)\s*m[²2]", card.get_text(), re.IGNORECASE)
                            if m:
                                area_m2 = normalize_area(m.group(0))

                            # ── Título ────────────────────────────────────────────────────────
                            m_url = re.search(r"/imovel/([^/?#]+)", source_url)
                            if m_url:
                                slug = re.sub(r"-\d+$", "", m_url.group(1).rstrip("/"))
                                slug = re.sub(r"-rs$|-sc$|-pr$|-sp$", "", slug)
                                title = " ".join(p.capitalize() for p in slug.split("-"))
                                if len(title) > 80:
                                    title = title[:77] + "..."
                            else:
                                title = f"{category} em {neighborhood}" if category and neighborhood else category or neighborhood or "Imóvel"

                            images = [image_url] if image_url else []

                            pd = PropertyData(
                                source_site=self.site_name,
                                source_url=source_url,
                                transaction_type=self.transaction_type,
                                title=title,
                                city="Dois Irmãos",
                                neighborhood=neighborhood,
                                category=category,
                                bedrooms=bedrooms,
                                area_m2=area_m2,
                                price=price,
                                images=images,
                            )
                            
                            seen_urls.add(source_url)
                            all_results.append(pd)
                            new_items_found += 1

                        print(f"Page {page_num}: Found {len(cards)} cards, {new_items_found} new items. Unique so far: {len(seen_urls)}")
                        if new_items_found == 0:
                            print(f"Page {page_num}: No new items found, breaking.")
                            break # Nenhum item novo encontrado, evitar loop infinito
                            
                        # Paginação
                        parsed_current = urlparse(current_url)
                        params = parse_qs(parsed_current.query, keep_blank_values=True)
                        page_num += 1
                        params['pagina'] = [str(page_num)]
                        new_query = urlencode({k: v[0] for k, v in params.items()})
                        current_url = urlunparse(parsed_current._replace(query=new_query))
                        
                        # Aguardar entre páginas
                        await asyncio.sleep(self.delay_seconds)

                finally:
                    await browser.close()

            # Verificação de fallback (Retry se muito abaixo do esperado)
            if expected_count:
                if len(all_results) >= expected_count * 0.9:
                    break # Success
                else:
                    print(f"Attempt {attempt}/{max_attempts}: Found {len(all_results)} but expected {expected_count}. Retrying...")
                    if attempt == max_attempts:
                        raise Exception(f"Missing items: Expected {expected_count}, got {len(all_results)}")
                    await asyncio.sleep(5) # Cooldown before retry
            else:
                break # Sem contagem esperada = sem necessidade de retry iterativo

        return all_results
