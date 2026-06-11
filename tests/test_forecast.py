import pandas as pd

from tori_fuel.forecast import (
    DEFAULT_RATES,
    expand_schedule,
    forecast_rob,
    historical_rates,
)


def make_schedule(rows):
    return pd.DataFrame(rows, columns=["start_date", "end_date", "status",
                                       "voyage_no", "refuel_allowed", "remark"])


def test_default_rates():
    assert DEFAULT_RATES == {"出航": 4.7, "靠港": 1.6, "進塢": 0.0}


def test_expand_schedule_daily_rows():
    sched = make_schedule([
        ("2026-06-01", "2026-06-03", "靠港", "", "Y", ""),
        ("2026-06-04", "2026-06-05", "出航", "V1", "N", ""),
    ])
    days = expand_schedule(sched)
    assert len(days) == 5
    assert days.iloc[0]["refuel_allowed"] is True or days.iloc[0]["refuel_allowed"] == True
    assert days.iloc[-1]["status"] == "出航"


def test_historical_rates_from_data():
    df = pd.DataFrame({
        "status": ["出航", "出航", "靠港", "進塢"],
        "total_fuel_consumed": [5.0, 4.0, 2.0, 0.0],
    })
    rates = historical_rates(df)
    assert rates["出航"] == 4.5
    assert rates["靠港"] == 2.0
    assert rates["進塢"] == 0.0


def test_no_refuel_needed_when_rob_high():
    sched = make_schedule([("2026-06-01", "2026-06-05", "靠港", "", "Y", "")])
    result = forecast_rob(400.0, expand_schedule(sched))
    assert result.refuel_plan == []
    assert result.risk_alerts == []


def test_refuel_recommended_before_breach():
    # 起始 200 KL：靠港 2 天可加油，之後出航 20 天（4.7*20=94 KL）
    # 不加油最低 ROB = 200 - 3.2 - 94 = 102.8 < 150 → 應在可加油日建議加油
    sched = make_schedule([
        ("2026-06-01", "2026-06-02", "靠港", "", "Y", ""),
        ("2026-06-03", "2026-06-22", "出航", "V1", "N", ""),
    ])
    result = forecast_rob(200.0, expand_schedule(sched))
    assert len(result.refuel_plan) >= 1
    first = result.refuel_plan[0]
    assert first["rob_after"] == 465.0
    assert first["refuel_amount"] == 465.0 - first["rob_before"]
    assert result.risk_alerts == []
    # 加油後整段預測不應低於警戒線
    assert not result.daily["below_warning"].any()


def test_risk_alert_when_no_refuel_possible():
    # 起始 160 KL 直接長時間出航且無可加油日 → 必然跌破警戒線
    sched = make_schedule([("2026-06-01", "2026-06-10", "出航", "V1", "N", "")])
    result = forecast_rob(160.0, expand_schedule(sched))
    assert result.refuel_plan == []
    assert result.risk_alerts
    assert result.daily["below_warning"].any()


def test_refuel_fills_to_capacity_exactly():
    sched = make_schedule([
        ("2026-06-01", "2026-06-01", "靠港", "", "Y", ""),
        ("2026-06-02", "2026-06-30", "出航", "V1", "N", ""),
    ])
    result = forecast_rob(180.0, expand_schedule(sched))
    assert result.refuel_plan[0]["refuel_amount"] == 465.0 - 180.0
