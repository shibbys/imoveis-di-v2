import asyncio
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int
from scrapers.platforms.kenlo import KenloScraper


class JetimobScraper(KenloScraper):
    """Scraper for sites running on Jetimob platform."""

    CARD_SELECTOR = ".CardProperty"
    NEXT_PAGE_SELECTOR = ""  # not used

    def _parse_card(self, card, base_url: str):
        try:
            a = card.find("a", href=True)
            if not a:
                return None
            href = a["href"]
            source_url = urljoin(base_url, href) if not href.startswith("http") else href

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
                # Find the next strong sibling or child
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

    def _get_next_page_url(self, soup: BeautifulSoup, current_url: str):
        # Jetimob uses offset/limit query params: offset=1&limit=21
        parsed = urlparse(current_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
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


def _safe_float(text: str):
    """Extract first number from text as float."""
    text = text.replace(",", ".")
    m = re.search(r'\d+\.?\d*', text)
    return float(m.group()) if m else None
