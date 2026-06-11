from datetime import date

from tori_fuel import voyage_types as vt
from tori_fuel.history import Actual2026
from tori_fuel.plan2026 import (
    TANK_CAPACITY_KL, Voyage, build_plan, derive_refuel_days,
)
from tori_fuel.typestats import RateTable, TypeStat


def _rates(sail=4.0, port=1.5):
    overall = TypeStat(vtype="全體", sail_fuels=[sail], port_fuels=[port])
    return RateTable(
        sail_rates={t: sail for t in vt.ALL_TYPES},
        sail_basis={t: "測試" for t in vt.ALL_TYPES},
        port_rate=port, overall=overall, by_type={},
    )


def _voyage(no, client, start, end, remark="", pi=""):
    v = Voyage(voyage_no=no, client=client, pi=pi, start=start, end=end,
               remark=remark)
    v.vtype = vt.classify_voyage(client, pi, remark)
    return v


def test_derive_refuel_days_from_remarks():
    voyages = [
        _voyage("LGD-塢修", "—", date(2026, 1, 29), date(2026, 2, 12),
                "全月進塢，含出塢加油", pi="進塢維修"),
        _voyage("LGD-2603", "國科會", date(2026, 4, 8), date(2026, 4, 22),
                "含加燃油、設備裝卸"),
        _voyage("LGD-2604", "中研院", date(2026, 4, 27), date(2026, 5, 3)),
    ]
    days = dict(derive_refuel_days(voyages))
    assert days == {date(2026, 2, 13): "LGD-塢修", date(2026, 4, 23): "LGD-2603"}


def test_build_plan_statuses_and_refuel_cap():
    voyages = [
        _voyage("LGD-塢修", "—", date(2026, 1, 10), date(2026, 1, 20),
                "含出塢加油", pi="進塢維修"),
        _voyage("LGD-2601", "國科會", date(2026, 2, 1), date(2026, 2, 10)),
    ]
    actual = Actual2026(rob={date(2026, 1, 1): 300.0},
                        daily_fuel={date(2026, 1, 1): 1.5})
    plan = build_plan(voyages, _rates(), actual)
    assert plan.initial_rob == 301.5
    by_day = {pd.day: pd for pd in plan.days}
    assert by_day[date(2026, 1, 15)].status == "進塢"
    assert by_day[date(2026, 1, 15)].est_fuel == 0.0
    assert by_day[date(2026, 2, 5)].status == "出航"
    assert by_day[date(2026, 2, 5)].est_fuel == 4.0
    assert by_day[date(2026, 3, 1)].status == "靠港"
    # 1/21 出塢加油補滿至 465
    ev = plan.refuels[0]
    assert ev.day == date(2026, 1, 21)
    assert ev.rob_after == TANK_CAPACITY_KL
    assert not ev.is_actual


def test_build_plan_uses_actual_refuel_amount():
    voyages = [_voyage("LGD-2603", "國科會", date(2026, 1, 5), date(2026, 1, 10),
                       "含加燃油")]
    actual = Actual2026(rob={date(2026, 1, 1): 200.0},
                        daily_fuel={date(2026, 1, 1): 1.5},
                        refuel={date(2026, 1, 11): 100.0})
    plan = build_plan(voyages, _rates(), actual)
    ev = plan.refuels[0]
    assert ev.day == date(2026, 1, 11)
    assert ev.amount == 100.0 and ev.is_actual
    assert ev.rob_after < TANK_CAPACITY_KL


def test_alert_when_below_warning():
    voyages = [_voyage("LGD-2601", "國科會", date(2026, 1, 1), date(2026, 3, 31))]
    actual = Actual2026(rob={date(2026, 1, 1): 160.0},
                        daily_fuel={date(2026, 1, 1): 4.0})
    plan = build_plan(voyages, _rates(), actual)
    assert plan.alerts
    assert any(pd.below_warning for pd in plan.days)


def test_fuel_error_actual_minus_estimate():
    voyages = [_voyage("LGD-2601", "國科會", date(2026, 1, 1), date(2026, 1, 5))]
    actual = Actual2026(rob={date(2026, 1, 2): 300.0},
                        daily_fuel={date(2026, 1, 2): 5.2})
    plan = build_plan(voyages, _rates(sail=4.0), actual)
    pd = next(p for p in plan.days if p.day == date(2026, 1, 2))
    assert pd.fuel_error == 1.2
    pd3 = next(p for p in plan.days if p.day == date(2026, 1, 3))
    assert pd3.fuel_error is None
