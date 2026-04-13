from scrapers.platforms.kenlo import KenloScraper


class VistaScraper(KenloScraper):
    """Scraper for sites running on Vista Soft platform."""
    CARD_SELECTOR = (
        ".listagem-imovel, .card-imovel, [class*='listing-item'], "
        "[class*='imovel-item'], .resultado .item"
    )
    NEXT_PAGE_SELECTOR = (
        "a.proximo, a[title='Próxima página'], a[title='Proxima página'], "
        ".paginacao a.ativo + a, .pagination a[rel='next']"
    )
