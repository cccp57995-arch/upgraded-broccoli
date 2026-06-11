import pandas as pd

from tori_fuel.classifier import classify_day, classify_dataframe


def row(**kw):
    base = dict(
        propulsion_hours=0, operation_hours=0, in_port_hours=24,
        propulsion_fuel=0, operation_fuel=0, in_port_fuel=0,
        total_fuel_consumed=0, distance=0,
    )
    base.update(kw)
    return base


def test_zero_total_fuel_is_dock():
    status, _ = classify_day(row(total_fuel_consumed=0))
    assert status == "進塢"


def test_dock_has_priority_over_sailing_signals():
    # 即使有推進時數與距離，總油耗 0 仍判進塢，但須標異常
    status, anomalies = classify_day(
        row(total_fuel_consumed=0, propulsion_hours=10, distance=80)
    )
    assert status == "進塢"
    assert anomalies  # 資料異常


def test_sailing_by_propulsion_hours():
    status, _ = classify_day(
        row(total_fuel_consumed=4.0, propulsion_hours=10,
            propulsion_fuel=3.0, operation_fuel=1.0, distance=90)
    )
    assert status == "出航"


def test_sailing_when_in_port_fuel_zero():
    # 規則 2：in_port_fuel == 0 也判出航
    status, _ = classify_day(row(total_fuel_consumed=2.0, in_port_fuel=0, propulsion_fuel=2.0,
                                 propulsion_hours=5, distance=40))
    assert status == "出航"


def test_in_port():
    status, anomalies = classify_day(row(total_fuel_consumed=1.6, in_port_fuel=1.6))
    assert status == "靠港"
    assert not anomalies


def test_fuel_sum_mismatch_flags_anomaly():
    status, anomalies = classify_day(
        row(total_fuel_consumed=10.0, in_port_fuel=1.0)
    )
    assert any("不符" in a for a in anomalies)


def test_classify_dataframe_columns():
    df = pd.DataFrame([row(total_fuel_consumed=1.6, in_port_fuel=1.6),
                       row(total_fuel_consumed=0)])
    out = classify_dataframe(df)
    assert list(out["status"]) == ["靠港", "進塢"]
    assert "is_anomaly" in out.columns and "anomaly_reasons" in out.columns
