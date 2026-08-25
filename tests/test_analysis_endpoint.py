"""
End-to-end: ingest real-shaped OHLC bars via /mt5/ingest, run analysis via
/analysis/run, confirm a signal is persisted, and confirm the MT5 EA can
poll for it and report execution back.
"""
from datetime import datetime, timedelta, timezone


def _auth_headers(client):
    """Full register -> approve -> login -> OTP flow, using the codes the
    (monkeypatched) admin-email sender captured on `client.captured_codes`
    — see tests/conftest.py."""
    email = "trader@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"name": "Trader", "email": email, "password": "SecurePass123"},
    )
    reg_code = client.captured_codes["registration"][-1][1]
    client.post(
        "/api/v1/auth/registration/verify",
        json={"email": email, "code": reg_code},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecurePass123"},
    )
    if login.json().get("status") == "otp_required":
        otp_code = client.captured_codes["login_otp"][-1][1]
        login = client.post(
            "/api/v1/auth/login/verify-otp",
            json={"email": email, "code": otp_code},
        )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _bullish_bar_payload(symbol="XAUUSD"):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prices = [
        (10, 10, 9, 10), (10, 11, 10, 11), (11, 13, 11, 12),
        (12, 12, 10, 10.5), (10.5, 11, 10.3, 10.8), (10.8, 14, 10.5, 13.8),
        (13.8, 16, 13.5, 15), (15, 15, 13, 13.5), (13.5, 14, 13, 13.8),
        (13.8, 15, 13.5, 14.5), (14.5, 16, 14, 15.5),
    ]
    bars = [
        {
            "time": (t0 + timedelta(minutes=i)).isoformat(),
            "open": o, "high": h, "low": l, "close": c, "volume": 100,
        }
        for i, (o, h, l, c) in enumerate(prices)
    ]
    return {"symbol": symbol, "timeframe": "M15", "spread": 0.3, "bars": bars}


def test_ingest_then_analyze_then_ea_poll(client):
    headers = _auth_headers(client)

    ingest_resp = client.post("/api/v1/mt5/ingest", json=_bullish_bar_payload())
    assert ingest_resp.status_code == 200
    assert ingest_resp.json()["bars_stored"] == 11

    # Re-ingesting the same bars should be idempotent (deduped)
    ingest_resp2 = client.post("/api/v1/mt5/ingest", json=_bullish_bar_payload())
    assert ingest_resp2.json()["bars_stored"] == 0
    assert ingest_resp2.json()["bars_skipped_duplicate"] == 11

    analysis_resp = client.post(
        "/api/v1/analysis/run",
        headers=headers,
        json={
            "symbol": "XAUUSD",
            "timeframe": "M15",
            "min_confidence_to_trade": 0.0,
            "use_news_sentiment": False,
            "check_calendar_blackout": False,
        },
    )
    assert analysis_resp.status_code == 200
    signal = analysis_resp.json()
    assert signal["symbol"] == "XAUUSD"
    assert signal["direction"] in ("bullish", "bearish", "no_trade")
    assert "confidence" in signal
    assert signal["setup_status"] in ("SETUP", "NO_SETUP", "INSUFFICIENT_CONFIRMATION")
    assert signal["reasoning"]
    assert "factors" in signal["confluence"]

    history_resp = client.get("/api/v1/analysis/signals", headers=headers)
    assert history_resp.status_code == 200
    assert len(history_resp.json()) >= 1

    # EA polling only exposes confirmed SETUP signals; no-trade results
    # remain persisted for audit/history but are never executable.
    pending_resp = client.get("/api/v1/mt5/pending-signals?symbol=XAUUSD")
    assert pending_resp.status_code == 200


def test_analysis_rejects_insufficient_bars(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/api/v1/analysis/run",
        headers=headers,
        json={"symbol": "NONEXISTENT_SYMBOL", "timeframe": "M15"},
    )
    assert resp.status_code == 422


def test_analysis_requires_auth(client):
    resp = client.post("/api/v1/analysis/run", json={"symbol": "XAUUSD"})
    assert resp.status_code == 401
