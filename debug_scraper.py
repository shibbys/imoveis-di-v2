import asyncio, os
os.environ.setdefault("WORKSPACE", ":memory:")

SITES = [
    {"name": "dois_irmaos", "url": "https://www.imobiliariadoisirmaos.com.br/imoveis/para-alugar", "platform": "kenlo", "transaction_type": "aluguel", "active": True},
    {"name": "habbitar", "url": "https://habbitar.com.br/alugar/imoveis?profile%5B0%5D=1&typeArea=total_area&floorComparision=equals&sort=-is_price_shown%2Cby_calculated_price&offset=1&limit=21", "platform": "jetimob", "transaction_type": "aluguel", "active": True},
    {"name": "investir", "url": "https://www.investirimoveisdi.com.br/busca/alugar/cidade/todas/categoria/apartamento_casa-sobrado_terrenos/data/desc/1/", "platform": "vista", "transaction_type": "aluguel", "active": True},
    {"name": "postai_compra", "url": "https://www.postaiimoveis.com.br/imoveis/tipo=casa-em-condominio,casas-e-sobrados&transacao=vendas&termo=Dois%20Irm%C3%A3os", "platform": "tecimob", "transaction_type": "compra", "active": True},
]

async def main():
    from scrapers.registry import get_scraper
    for site in SITES:
        print(f"Testing {site['name']} ({site['platform']})...")
        try:
            scraper = get_scraper(site)
            results = await scraper.scrape()
            print(f"  OK: {len(results)} properties")
            if results:
                r = results[0]
                print(f"  First: neighborhood={r.neighborhood!r} price={r.price} bedrooms={r.bedrooms} area={r.area_m2} images={len(r.images)}")
        except Exception as e:
            print(f"  ERROR: {e}")

asyncio.run(main())
