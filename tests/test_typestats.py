from datetime import date

from tori_fuel import voyage_types as vt
from tori_fuel.history import DailyRecord, STATUS_PORT, STATUS_SAIL
from tori_fuel.typestats import build_rate_table, monthly_summary, percentile


def test_percentile_linear_interpolation():
    vals = [1.0, 2.0, 3.0, 4.0]
    assert percentile(vals, 50) == 2.5
    assert percentile(vals, 25) == 1.75
    assert percentile(vals, 0) == 1.0
    assert percentile(vals, 100) == 4.0
    assert percentile([], 50) == 0.0


def _sail(d, voyage, fuel):
    return DailyRecord(day=d, voyage_no=voyage, status=STATUS_SAIL, total_fuel=fuel)


def _port(d, voyage, fuel):
    return DailyRecord(day=d, voyage_no=voyage, status=STATUS_PORT, total_fuel=fuel)


def test_rate_table_uses_type_median_when_enough_samples():
    recs = [_sail(date(2026, 1, 1 + i), "LGD-2601", 4.0 + i * 0.1) for i in range(12)]
    recs += [_port(date(2026, 2, 1 + i), "", 1.5) for i in range(5)]
    mapping = {"LGD-2601": vt.TYPE_NSTC}
    rates = build_rate_table(recs, mapping)
    st = rates.by_type[vt.TYPE_NSTC]
    assert st.sail_days == 12
    assert rates.sail_rates[vt.TYPE_NSTC] == round(st.sail_p(50), 2)
    assert "類型中位數" in rates.sail_basis[vt.TYPE_NSTC]
    assert rates.port_rate == 1.5


def test_rate_table_falls_back_when_sample_too_small():
    recs = [_sail(date(2026, 1, 1 + i), "LGD-2601", 4.0) for i in range(20)]
    recs += [_sail(date(2026, 2, 1), "LGD-2604", 9.0)]  # 中研院僅 1 天
    mapping = {"LGD-2601": vt.TYPE_NSTC, "LGD-2604": vt.TYPE_SINICA}
    rates = build_rate_table(recs, mapping)
    overall_p50 = round(rates.overall.sail_p(50), 2)
    assert rates.sail_rates[vt.TYPE_SINICA] == overall_p50
    assert "樣本不足" in rates.sail_basis[vt.TYPE_SINICA]
    assert "無歷史樣本" in rates.sail_basis[vt.TYPE_SEISMIC]


def test_monthly_summary_groups_and_sums():
    recs = [
        _sail(date(2026, 1, 1), "V", 5.0),
        _port(date(2026, 1, 2), "V", 1.5),
        _sail(date(2026, 2, 1), "V", 4.0),
    ]
    recs[1].refuel = 100.0
    months = monthly_summary(recs)
    assert [m["month"] for m in months] == ["2026/01", "2026/02"]
    jan = months[0]
    assert jan["sail_days"] == 1 and jan["port_days"] == 1
    assert jan["total_fuel"] == 6.5 and jan["refuel"] == 100.0
