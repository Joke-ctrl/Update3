from app.services.market_data_providers import _normalise_symbol, _float


def test_normalise_symbol():
    assert _normalise_symbol("xau/usd") == "XAUUSD"
    assert _normalise_symbol("EUR_USD") == "EURUSD"


def test_safe_float():
    assert _float("1.25") == 1.25
    assert _float("bad") is None
