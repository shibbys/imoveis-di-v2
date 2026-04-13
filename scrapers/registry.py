from scrapers.base import BaseScraper
from scrapers.platforms.kenlo import KenloScraper
from scrapers.platforms.vista import VistaScraper
from scrapers.platforms.jetimob import JetimobScraper
from scrapers.platforms.tecimob import TecimobScraper

PLATFORM_MAP: dict[str, type] = {
    "kenlo": KenloScraper,
    "vista": VistaScraper,
    "jetimob": JetimobScraper,
    "tecimob": TecimobScraper,
}


def get_scraper(site: dict) -> BaseScraper:
    """
    Build a scraper for the given site config dict.

    Expected site dict keys:
      name (str): site identifier
      url (str): base URL to scrape
      platform (str): one of kenlo, vista, jetimob, tecimob
      transaction_type (str): 'aluguel' or 'compra'
      max_pages (int, optional): default 30
      delay_seconds (float, optional): default 2.0
    """
    platform = site.get("platform", "kenlo")
    cls = PLATFORM_MAP.get(platform, KenloScraper)
    return cls(
        site_name=site["name"],
        url=site["url"],
        transaction_type=site["transaction_type"],
        max_pages=site.get("max_pages", 30),
        delay_seconds=site.get("delay_seconds", 2.0),
    )
