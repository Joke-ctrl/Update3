from app.services.instruments import canonical_symbol, instrument_payload


def test_index_aliases_are_canonical():
    assert canonical_symbol("NASDAQ") == "NAS100"
    assert canonical_symbol("US100") == "NAS100"
    assert canonical_symbol("DOW30") == "US30"
    assert canonical_symbol("US30") == "US30"


def test_instrument_catalog_contains_tradable_indices():
    symbols = {item["symbol"] for item in instrument_payload()}
    assert {"NAS100", "US30", "XAUUSD"}.issubset(symbols)
