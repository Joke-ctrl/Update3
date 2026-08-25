def test_mt5_ingest_accepts_valid_payload(client):
    response = client.post(
        "/api/v1/mt5/ingest",
        json={
            "symbol": "XAUUSD",
            "timeframe": "M1",
            "spread": 2.5,
            "bars": [
                {
                    "time": "2026-07-15T12:00:00Z",
                    "open": 3350,
                    "high": 3352,
                    "low": 3349,
                    "close": 3351,
                    "volume": 120,
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["bars_stored"] == 1
    assert body["bars_skipped_duplicate"] == 0


def test_mt5_ingest_rejects_malformed_payload(client):
    response = client.post("/api/v1/mt5/ingest", json={"symbol": "XAUUSD"})
    assert response.status_code == 422
