import pytest
from fastapi.testclient import TestClient

from app.server.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # runs the lifespan: loads and warms up the model once for the whole session
        yield c
