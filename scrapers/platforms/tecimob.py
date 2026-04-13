from scrapers.platforms.kenlo import KenloScraper


class TecimobScraper(KenloScraper):
    """Scraper for sites running on Tecimob platform."""
    CARD_SELECTOR = (
        ".item-imovel, .resultado-busca .imovel, [class*='resultado-imovel'], "
        ".imovel-resultado, [class*='card-imovel']"
    )
    NEXT_PAGE_SELECTOR = (
        "a.proxima-pagina, .paginacao .next, a[rel='next'], "
        ".pagination .next a"
    )
