import os
import sys
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATA_DIR"] = _tmp
os.environ["LLM_PROVIDER"] = "mock"
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["AUTH_REQUIRED"] = "true"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def _register(client, email):
    r = client.post("/api/auth/register", json={"email": email, "name": "T", "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def auth(client):
    return _register(client, "a@test.com")


@pytest.fixture(scope="session")
def auth2(client):
    return _register(client, "b@test.com")


@pytest.fixture(scope="session")
def dataset(client, auth):
    r = client.post("/api/dataset/sample/sales_data.csv", headers=auth)
    assert r.status_code == 200, r.text
    return r.json()["dataset_id"]


@pytest.fixture(scope="session")
def dataset2(client, auth):
    r = client.post("/api/dataset/sample/data2.csv", headers=auth)
    assert r.status_code == 200, r.text
    return r.json()["dataset_id"]
