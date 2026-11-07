from unittest.mock import patch

from fastapi.testclient import TestClient

from budgetcare.api.app import create_app


def test_health_endpoints():
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    deep_response = client.get("/health?deep=1")
    assert deep_response.status_code == 200
    assert deep_response.json()["status"] == "ok"
    assert deep_response.json()["deep"] is True
    assert deep_response.json()["database"] == "connected"


def test_health_deep_database_error():
    app = create_app()
    client = TestClient(app)

    with patch("budgetcare.api.routes.health.uow_factory") as mock_uow:
        mock_uow.side_effect = Exception("DB connection timeout")
        resp = client.get("/health?deep=1")
        assert resp.status_code == 503
        data = resp.json()
        assert data["detail"]["status"] == "unhealthy"
        assert data["detail"]["database"] == "disconnected"

