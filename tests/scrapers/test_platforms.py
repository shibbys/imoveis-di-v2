import pytest
from pathlib import Path
from bs4 import BeautifulSoup
from scrapers.platforms.kenlo import KenloScraper

FIXTURES = Path(__file__).parent / "fixtures"


def make_soup(filename: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / filename).read_text(encoding="utf-8"), "html.parser")


def test_kenlo_parses_properties():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    properties = scraper._parse_page(soup, "https://example.com")
    assert len(properties) == 2


def test_kenlo_extracts_price():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    props = scraper._parse_page(soup, "https://example.com")
    assert props[0].price == 2500.0
    assert props[1].price == 1800.0


def test_kenlo_extracts_images():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    props = scraper._parse_page(soup, "https://example.com")
    assert len(props[0].images) == 2
    assert "img1.jpg" in props[0].images[0]


def test_kenlo_extracts_bedrooms():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    props = scraper._parse_page(soup, "https://example.com")
    assert props[0].bedrooms == 3
    assert props[1].bedrooms == 2


def test_kenlo_extracts_area():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    props = scraper._parse_page(soup, "https://example.com")
    assert props[0].area_m2 == 120.0


def test_kenlo_extracts_neighborhood():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    props = scraper._parse_page(soup, "https://example.com")
    assert props[0].neighborhood == "Centro"


def test_kenlo_extracts_source_url():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    props = scraper._parse_page(soup, "https://example.com")
    assert "12345" in props[0].source_url
    assert props[0].source_url.startswith("https://example.com")


def test_kenlo_next_page_url():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com/imoveis", "aluguel")
    next_url = scraper._get_next_page_url(soup, "https://example.com/imoveis")
    assert next_url is not None
    assert "page=2" in next_url


def test_kenlo_category_from_title():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    props = scraper._parse_page(soup, "https://example.com")
    assert props[0].category == "Casa"
    assert props[1].category == "Apartamento"
