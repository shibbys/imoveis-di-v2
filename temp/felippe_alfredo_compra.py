"""
Scraper: Felippe Alfredo Imobiliária — Venda
Herda FelippeAlfredoScraper integralmente (Jetimob, mesma estrutura de card/imagem).
"""
from .felippe_alfredo import FelippeAlfredoScraper


class FelippeAlfredoCompraScraper(FelippeAlfredoScraper):
    site_name = "Felippe Alfredo"
    base_url = (
        "https://www.felippealfredoimobiliaria.com.br/venda/rio-grande-do-sul/dois-irmaos/casa"
        "/com-mais-de-5-quartos?tipos=%22casa%22&quartos=%223%2C4%2C5%2C2%22"
        "&ordenacao=%22mais-recente%22&pagina=1&transacao=%22venda%22"
        "&endereco=%5B%7B%22label%22%3A%22Dois+Irm%C3%A3os+-+RS%22%2C%22valor%22%3A%7B%22cidade%22%3A7650%2C%22estado%22%3A23%7D%2C%22cidade%22%3A%22dois-irmaos%22%2C%22estado%22%3A%22rio-grande-do-sul%22%7D%5D"
    )
    transaction_type = "compra"
