from datetime import date

from tori_fuel.history import (
    DailyRecord, STATUS_DOCK, STATUS_PORT, STATUS_SAIL,
    classify_day, detect_refuels,
)


def test_classify_dock_when_zero_total():
    assert classify_day(5, 0, 100, 2, 0, 0, 0) == STATUS_DOCK


def test_classify_sail_conditions():
    assert classify_day(1, 0, 0, 0, 0, 1, 3) == STATUS_SAIL   # 推進時數
    assert classify_day(0, 2, 0, 0, 0, 1, 3) == STATUS_SAIL   # 作業時數
    assert classify_day(0, 0, 50, 0, 0, 1, 3) == STATUS_SAIL  # 距離
    assert classify_day(0, 0, 0, 0, 0, 0, 3) == STATUS_SAIL   # 靠港油耗 = 0


def test_classify_port_otherwise():
    assert classify_day(0, 0, 0, 0, 0, 1.5, 1.5) == STATUS_PORT


def _rec(d, rob, fuel=2.0):
    return DailyRecord(day=d, total_fuel=fuel, rob=rob)


def test_detect_refuels_over_10kl_delta():
    recs = [
        _rec(date(2026, 1, 1), 200.0),
        _rec(date(2026, 1, 2), 198.0),   # -2：正常消耗
        _rec(date(2026, 1, 3), 440.0),   # +242：加油
        _rec(date(2026, 1, 4), 445.0),   # +5：低於門檻，不算加油
    ]
    detect_refuels(recs)
    assert recs[1].refuel == 0.0
    assert recs[2].refuel == 244.0  # 242 + 當日油耗 2
    assert recs[3].refuel == 0.0


def test_detect_refuels_skips_missing_rob():
    recs = [
        _rec(date(2026, 1, 1), 200.0),
        _rec(date(2026, 1, 2), None),
        _rec(date(2026, 1, 3), 195.0),
    ]
    detect_refuels(recs)
    assert all(r.refuel == 0.0 for r in recs)
