import pytest
import os
from storage.database import init_db, get_connection


@pytest.fixture
def db():
    conn = get_connection(":memory:")
    init_db(":memory:", conn=conn)
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    os.environ["WORKSPACE"] = ":memory:"
    os.environ["SESSION_SECRET"] = "test-secret"
    from app import app
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=True)
