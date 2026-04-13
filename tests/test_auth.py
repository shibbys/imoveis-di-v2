import pytest
import bcrypt
import os
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_user():
    os.environ["WORKSPACE"] = ":memory:"
    os.environ["SESSION_SECRET"] = "test-secret"
    from storage.database import get_connection, init_db, create_user
    conn = get_connection(":memory:")
    init_db(":memory:", conn=conn)
    pw = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
    create_user(conn, "testuser", pw)
    conn.commit()
    conn.close()
    # Re-import app fresh
    import importlib
    import app as app_module
    importlib.reload(app_module)
    from app import app
    return TestClient(app, raise_server_exceptions=True)


def test_login_page_loads(client_with_user):
    r = client_with_user.get("/login")
    assert r.status_code == 200
    assert "Imoveis DI" in r.text


def test_login_success_redirects(client_with_user):
    r = client_with_user.post(
        "/login",
        data={"username": "testuser", "password": "password123"},
        follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/aluguel"


def test_login_wrong_password(client_with_user):
    r = client_with_user.post(
        "/login",
        data={"username": "testuser", "password": "wrong"},
        follow_redirects=False
    )
    assert r.status_code == 200
    assert "Usuário ou senha incorretos" in r.text


def test_login_unknown_user(client_with_user):
    r = client_with_user.post(
        "/login",
        data={"username": "nobody", "password": "anything"},
        follow_redirects=False
    )
    assert r.status_code == 200
    assert "Usuário ou senha incorretos" in r.text


def test_protected_route_redirects_unauthenticated(client_with_user):
    r = client_with_user.get("/aluguel", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


def test_logout_clears_session(client_with_user):
    # Login first
    client_with_user.post("/login", data={"username": "testuser", "password": "password123"})
    # Logout
    r = client_with_user.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    # Should be redirected to login now
    r2 = client_with_user.get("/aluguel", follow_redirects=False)
    assert r2.status_code == 303
    assert "/login" in r2.headers["location"]
