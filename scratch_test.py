import asyncio
from scrapers.platforms.felippev2 import FelippeAlfredoV2Scraper
import logging

logging.basicConfig(level=logging.INFO)

async def test_venda():
    url = 'https://www.felippealfredoimobiliaria.com.br/venda/rio-grande-do-sul/dois-irmaos/casa/com-mais-de-5-quartos?tipos=%22casa%22&quartos=%223%2C4%2C5%2C2%22&ordenacao=%22mais-recente%22&pagina=1&transacao=%22venda%22&endereco=%5B%7B%22label%22%3A%22Dois+Irm%C3%A3os+-+RS%22%2C%22valor%22%3A%7B%22cidade%22%3A7650%2C%22estado%22%3A23%7D%2C%22cidade%22%3A%22dois-irmaos%22%2C%22estado%22%3A%22rio-grande-do-sul%22%7D%5D'
    scraper = FelippeAlfredoV2Scraper(
        site_name="felippe_alfredo",
        url=url,
        transaction_type="compra",
        max_pages=10,
        delay_seconds=2.0
    )
    print("Starting scrape...")
    results = await scraper.scrape()
    print(f"Total results: {len(results)}")
    
if __name__ == '__main__':
    asyncio.run(test_venda())
