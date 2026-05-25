from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_accessible():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "paths" in data
    assert "/api/v1/profiles/{elder_id}" in data["paths"]
    assert "/api/v1/risk/check" in data["paths"]
    assert "/api/v1/reminders/due" in data["paths"]
