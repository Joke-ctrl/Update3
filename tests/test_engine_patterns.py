from datetime import datetime, timedelta, timezone

from app.engine.fvg import detect_fair_value_gaps
from app.engine.order_blocks import detect_order_blocks
from app.engine.liquidity import detect_liquidity_sweeps, find_equal_levels
from app.engine.premium_discount import compute_dealing_range
from app.engine.types import Bar


def _mk_bars(prices: list[tuple[float, float, float, float]]) -> list[Bar]:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(time=t0 + timedelta(minutes=i), open=o, high=h, low=l, close=c)
        for i, (o, h, l, c) in enumerate(prices)
    ]


def test_bullish_fvg_detected():
    # candle0 high=10; candle1 huge displacement bullish body; candle2 low=13 (>10 -> gap)
    bars = _mk_bars(
        [
            (9, 10, 8, 9.5),     # index 0: small range candle (sets low avg range)
            (9.5, 10, 9, 9.7),   # index 1
            (9.7, 10, 9.4, 9.8), # index 2
            (9.8, 20, 9.8, 19.5),# index 3: huge displacement candle (body ~9.7 vs avg range ~1)
            (19.5, 21, 13, 20),  # index 4: low=13, > candle2 high(10) -> bullish FVG at index3
        ]
    )
    gaps = detect_fair_value_gaps(bars, require_displacement=True)
    bullish_gaps = [g for g in gaps if g.direction == "bullish"]
    assert len(bullish_gaps) >= 1
    assert bullish_gaps[0].bottom == 10  # prev candle high
    assert bullish_gaps[0].top == 13     # next candle low


def test_fvg_fill_tracking():
    bars = _mk_bars(
        [
            (9, 10, 8, 9.5),
            (9.5, 10, 9, 9.7),
            (9.7, 10, 9.4, 9.8),
            (9.8, 20, 9.8, 19.5),
            (19.5, 21, 13, 20),
            (20, 20, 9, 12),  # traverses the full 10-13 gap -> fill
        ]
    )
    gaps = detect_fair_value_gaps(bars, require_displacement=True)
    assert any(g.filled for g in gaps)


def test_order_block_forms_before_bullish_bos():
    bars = _mk_bars(
        [
            (10, 10, 9, 10),
            (10, 11, 10, 11),
            (11, 13, 11, 12),  # swing high @ index2 price13
            (12, 12, 11, 10.5),  # bearish candle (close<open) -- should become the OB
            (10.5, 11, 10.3, 10.8),  # bullish candle (close>open), not eligible as OB
            (10.8, 14, 10.5, 13.8),  # breaks above 13 -> bullish BOS
            (13.8, 16, 13.5, 15),
        ]
    )
    obs = detect_order_blocks(bars, lookback=1)
    bullish_obs = [ob for ob in obs if ob.direction == "bullish"]
    assert len(bullish_obs) >= 1
    # the OB should be the bearish candle at index 3
    assert bullish_obs[0].index == 3


def test_equal_highs_clustered():
    bars = _mk_bars(
        [
            (10, 15.00, 9, 10),
            (10, 10, 9, 10),
            (10, 10, 9, 10),
            (10, 15.02, 9, 10),  # equal high within tolerance of 15.00
            (10, 10, 9, 10),
            (10, 10, 9, 10),
            (10, 15.01, 9, 10),  # another equal high
            (10, 10, 9, 10),
        ]
    )
    levels = find_equal_levels(bars, lookback=1, tolerance_pct=0.5)
    assert len(levels["highs"]) >= 1


def test_liquidity_sweep_detected():
    bars = _mk_bars(
        [
            (10, 10, 9, 10),
            (10, 15, 9, 10),   # swing high @ 15
            (10, 10, 9, 10),
            (10, 15, 9, 10),   # second equal swing high
            (10, 10, 9, 10),
            (10, 10, 9, 10),
            (10, 16, 9, 12),   # sweeps above pooled 15 and closes back below
        ]
    )
    sweeps = detect_liquidity_sweeps(bars, lookback=1, tolerance_pct=0.5)
    assert any(s.direction == "buy_side" for s in sweeps)


def test_dealing_range_and_zones():
    bars = _mk_bars(
        [
            (10, 10, 9, 10),
            (10, 20, 10, 15),  # swing high @ 20
            (15, 15, 5, 10),   # swing low @ 5
            (10, 10, 9, 10),
        ]
    )
    dr = compute_dealing_range(bars, lookback=1)
    assert dr is not None
    assert dr.range_high == 20
    assert dr.range_low == 5
    assert dr.equilibrium == 12.5
    assert dr.zone_for(18) == "premium"
    assert dr.zone_for(7) == "discount"
