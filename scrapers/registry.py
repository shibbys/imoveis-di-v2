from scrapers.base import BaseScraper
from scrapers.platforms.kenlo import KenloScraper
from scrapers.platforms.vista import VistaScraper
from scrapers.platforms.jetimob import JetimobScraper
from scrapers.platforms.tecimob import TecimobScraper
from scrapers.platforms.smartimob import SmartimobScraper
from scrapers.platforms.voa import VoaScraper
from scrapers.platforms.imobibrasil import ImobiBrasilScraper
from scrapers.platforms.smtximob import SmtximobScraper
from scrapers.platforms.becker import BeckerScraper
from scrapers.platforms.conecta import ConectaScraper
from scrapers.platforms.munique import MuniqueScraper
from scrapers.platforms.lis import LisScraper
from scrapers.platforms.joelblume import JoelBlumeScraper
from scrapers.platforms.imoview import ImoviewScraper
from scrapers.platforms.dapper import DapperScraper
from scrapers.platforms.felippealfredo import FelippeAlfredoScraper
from scrapers.platforms.felippev2 import FelippeAlfredoV2Scraper

PLATFORM_MAP: dict[str, type] = {
    "kenlo": KenloScraper,
    "vista": VistaScraper,
    "jetimob": JetimobScraper,
    "tecimob": TecimobScraper,
    "smartimob": SmartimobScraper,
    "voa": VoaScraper,
    "imobibrasil": ImobiBrasilScraper,
    "smtximob": SmtximobScraper,
    "becker": BeckerScraper,
    "conecta": ConectaScraper,
    "munique": MuniqueScraper,
    "lis": LisScraper,
    "joelblume": JoelBlumeScraper,
    "imoview": ImoviewScraper,
    "dapper": DapperScraper,
    "felippealfredo": FelippeAlfredoScraper,
    "felippev2": FelippeAlfredoV2Scraper,
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
        max_pages=site.get("max_pages") or 30,
        delay_seconds=site.get("delay_seconds") or 2.0,
    )
