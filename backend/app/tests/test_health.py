from __future__ import annotations

from app.tests.base import ApiTestBase


class TestMainApi(ApiTestBase):
    def test_health_endpoint_returns_ok(self) -> None:
        with self.create_client() as client:
            response = client.get("/api/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
