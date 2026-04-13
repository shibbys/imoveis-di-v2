from scrapers.platforms.kenlo import KenloScraper


class JetimobScraper(KenloScraper):
    """Scraper for sites running on Jetimob platform."""
    CARD_SELECTOR = (
        ".imovel-item, .property-item, [data-imovel-id], "
        "[class*='card-property'], .listing-card"
    )
    NEXT_PAGE_SELECTOR = (
        "a.page-link[aria-label='Next'], .pagination li:last-child a, "
        "a[rel='next'], .next-page"
    )
