from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from budgetcare.api.app import create_app
from budgetcare.config import settings
from budgetcare.services.tick import TickStats

client = TestClient(create_app())


def test_tick_endpoint_requires_auth():
    # Without header -> 401
    resp = client.post("/internal/tick")
    assert resp.status_code == 401

    # With invalid header -> 401
    resp = client.post("/internal/tick", headers={"X-Tick-Secret": "wrong_secret"})
    assert resp.status_code == 401


def test_tick_endpoint_success_with_valid_secret(monkeypatch):
    monkeypatch.setattr(settings, "TICK_SECRET", "test_secret_123")

    dummy_stats = TickStats(
        periods_closed=2,
        periods_missed=1,
        goals_graduated=0,
        goals_expired=0,
    )

    with patch("budgetcare.api.routes.tick.run_tick", new_callable=AsyncMock) as mock_tick:
        mock_tick.return_value = dummy_stats
        resp = client.post("/internal/tick", headers={"X-Tick-Secret": "test_secret_123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["periods_closed"] == 2
        assert data["periods_missed"] == 1
        mock_tick.assert_called_once()
