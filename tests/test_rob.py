import pandas as pd

from tori_fuel.rob import RobParams, compute_rob_series, refuel_amount


def test_refuel_amount_fills_to_capacity():
    assert refuel_amount(200.0) == 265.0
    assert refuel_amount(465.0) == 0.0
    assert refuel_amount(500.0) == 0.0  # 不為負


def test_rob_chain_basic():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=3),
        "total_fuel_consumed": [5.0, 3.0, 2.0],
        "refuel": [0.0, 0.0, 0.0],
        "rob": [None, None, None],
    })
    out = compute_rob_series(df, initial_rob=100.0)
    assert list(out["rob_calc"]) == [95.0, 92.0, 90.0]


def test_refuel_capped_at_capacity():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=2),
        "total_fuel_consumed": [2.0, 2.0],
        "refuel": [0.0, 300.0],  # 過量加油
        "rob": [None, None],
    })
    out = compute_rob_series(df, initial_rob=400.0)
    # 加油後不得超過 465：第二日 = min(398+300, 465) - 2 = 463
    assert out["rob_calc"].iloc[1] == 463.0


def test_initial_rob_back_calculated_from_first_record():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=2),
        "total_fuel_consumed": [5.0, 5.0],
        "refuel": [0.0, 0.0],
        "rob": [395.0, 390.0],
    })
    out = compute_rob_series(df)  # 期初 = 395 - 0 + 5 = 400
    assert list(out["rob_calc"]) == [395.0, 390.0]
    assert not out["rob_mismatch"].any()


def test_mismatch_and_warning_flags():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=2),
        "total_fuel_consumed": [10.0, 10.0],
        "refuel": [0.0, 0.0],
        "rob": [140.0, 200.0],  # 第二筆與推算不符
    })
    out = compute_rob_series(df, initial_rob=150.0)
    assert out["below_warning"].all()
    assert not out["rob_mismatch"].iloc[0]
    assert out["rob_mismatch"].iloc[1]


def test_custom_params():
    p = RobParams(tank_capacity=100.0, warning_level=50.0)
    assert refuel_amount(30.0, p) == 70.0
