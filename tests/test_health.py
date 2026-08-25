def test_health_returns_200(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_health_alias_at_root(client):
    response = client.get("/health")
    assert response.status_code == 200
