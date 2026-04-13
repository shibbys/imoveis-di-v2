from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int


def test_property_data_defaults():
    p = PropertyData(
        source_site="test",
        source_url="http://x.com/1",
        title="Casa",
        city="Dois Irmãos",
        neighborhood="Centro",
        category="Casa",
        transaction_type="aluguel",
    )
    assert p.images == []
    assert p.price is None
    assert p.bedrooms is None
    assert p.bathrooms is None
    assert p.parking_spots is None
    assert p.area_m2 is None
    assert p.land_area_m2 is None


def test_property_data_id_is_stable():
    p1 = PropertyData(
        source_site="test", source_url="http://x.com/1",
        title="Casa", city="Dois Irmãos", neighborhood="Centro",
        category="Casa", transaction_type="aluguel",
    )
    p2 = PropertyData(
        source_site="test", source_url="http://x.com/1",
        title="Different title", city="Dois Irmãos", neighborhood="Centro",
        category="Casa", transaction_type="aluguel",
    )
    assert p1.id == p2.id  # ID is based on source_site + source_url only


def test_property_data_id_differs_by_url():
    p1 = PropertyData(
        source_site="test", source_url="http://x.com/1",
        title="Casa", city="Dois Irmãos", neighborhood="Centro",
        category="Casa", transaction_type="aluguel",
    )
    p2 = PropertyData(
        source_site="test", source_url="http://x.com/2",
        title="Casa", city="Dois Irmãos", neighborhood="Centro",
        category="Casa", transaction_type="aluguel",
    )
    assert p1.id != p2.id


def test_normalize_price_br_format():
    assert normalize_price("R$ 1.500,00") == 1500.0
    assert normalize_price("R$ 2.300,50") == 2300.5


def test_normalize_price_plain():
    assert normalize_price("1500") == 1500.0
    assert normalize_price("2300.50") == 2300.5


def test_normalize_price_empty():
    assert normalize_price("") is None
    assert normalize_price(None) is None
    assert normalize_price("   ") is None


def test_normalize_area():
    assert normalize_area("120 m²") == 120.0
    assert normalize_area("85,5m²") == 85.5
    assert normalize_area("75.5 m2") == 75.5
    assert normalize_area("") is None
    assert normalize_area(None) is None


def test_normalize_int():
    assert normalize_int("3 quartos") == 3
    assert normalize_int("2") == 2
    assert normalize_int("1 vaga") == 1
    assert normalize_int("") is None
    assert normalize_int(None) is None
