import re
import hashlib
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Optional


@dataclass
class PropertyData:
    source_site: str
    source_url: str
    title: str
    city: str
    neighborhood: str
    category: str
    transaction_type: str  # 'aluguel' | 'compra'
    price: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    parking_spots: Optional[int] = None
    area_m2: Optional[float] = None
    land_area_m2: Optional[float] = None
    images: list = field(default_factory=list)

    @property
    def id(self) -> str:
        key = f"{self.source_site}::{self.source_url}"
        return hashlib.md5(key.encode()).hexdigest()[:16]


def normalize_price(value) -> Optional[float]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Remove currency symbol, spaces, non-numeric except comma/dot
    cleaned = re.sub(r"[R$\s]", "", text)
    # Brazilian format: 1.500,00 → remove dots, replace comma with dot
    if re.search(r"\d\.\d{3},", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_area(value) -> Optional[float]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Find first number (int or decimal with comma or dot)
    m = re.search(r"(\d+[,.]?\d*)", text)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


def normalize_int(value) -> Optional[int]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    m = re.search(r"(\d+)", text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


class BaseScraper(ABC):
    """Abstract base for all platform scrapers."""

    def __init__(
        self,
        site_name: str,
        url: str,
        transaction_type: str,
        max_pages: int = 30,
        delay_seconds: float = 2.0,
    ):
        self.site_name = site_name
        self.url = url
        self.transaction_type = transaction_type
        self.max_pages = max_pages
        self.delay_seconds = delay_seconds

    @abstractmethod
    async def scrape(self) -> list:
        """Run the scraper and return all found PropertyData instances."""
        ...
