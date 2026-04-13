import pytest, bcrypt, os
from fastapi.testclient import TestClient
from storage.database import init_db, get_connection, create_user


@pytest.fixture
def auth_client():
    os.environ["WORKSPACE"] = ":memory:"
    os.environ["SESSION_SECRET"] = "test"
    from app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        # Lifespan has run (init_db called) — now create user on the shared
        # in-memory connection and log in.
        conn = get_connection(":memory:")
        pw = bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode()
        create_user(conn, "u", pw)
        conn.commit()
        resp = c.post("/login", data={"username": "u", "password": "pw"}, allow_redirects=False)
        assert resp.status_code == 303
        yield c


def test_aluguel_page_loads(auth_client):
    r = auth_client.get("/aluguel")
    assert r.status_code == 200
    assert "aluguel" in r.text.lower()


def test_compra_page_loads(auth_client):
    r = auth_client.get("/compra")
    assert r.status_code == 200


def test_partial_imoveis_empty(auth_client):
    r = auth_client.get("/partials/imoveis?tipo=aluguel")
    assert r.status_code == 200
    assert "Nenhum imóvel" in r.text


def test_historico_page_loads(auth_client):
    r = auth_client.get("/historico")
    assert r.status_code == 200


def test_configuracoes_page_loads(auth_client):
    r = auth_client.get("/configuracoes")
    assert r.status_code == 200


def test_unauthenticated_redirects_to_login():
    os.environ["WORKSPACE"] = ":memory:"
    os.environ["SESSION_SECRET"] = "test"
    from app import app
    c = TestClient(app, raise_server_exceptions=True)
    resp = c.get("/aluguel", allow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers.get("location", "")
