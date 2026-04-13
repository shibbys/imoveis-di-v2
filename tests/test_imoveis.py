import pytest, bcrypt, os
from fastapi.testclient import TestClient
from storage.database import init_db, get_connection, create_user


@pytest.fixture
def client():
    os.environ["WORKSPACE"] = ":memory:"
    os.environ["SESSION_SECRET"] = "test"
    from app import app
    with TestClient(app) as c:
        # Lifespan has run (init_db called) — now create user on the shared
        # in-memory connection and log in.
        conn = get_connection(":memory:")
        pw = bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode()
        create_user(conn, "u", pw)
        conn.commit()
        c.post("/login", data={"username": "u", "password": "pw"})
        yield c


def test_aluguel_page_loads(client):
    r = client.get("/aluguel")
    assert r.status_code == 200


def test_compra_page_loads(client):
    r = client.get("/compra")
    assert r.status_code == 200


def test_partial_imoveis_empty(client):
    r = client.get("/partials/imoveis?tipo=aluguel")
    assert r.status_code == 200
    assert "Nenhum imóvel" in r.text


def test_historico_page_loads(client):
    r = client.get("/historico")
    assert r.status_code == 200


def test_configuracoes_page_loads(client):
    r = client.get("/configuracoes")
    assert r.status_code == 200
