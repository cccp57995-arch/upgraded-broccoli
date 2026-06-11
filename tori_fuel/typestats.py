"""各任務類型油耗統計與建議油耗率。

依任務類型彙整歷史出航日/靠港日油耗，輸出日均與 P25/P50/P75 分布；
2026 加油預估各航次套用對應類型的建議值（樣本不足時退回全體統計）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import voyage_types
from .history import DailyRecord, STATUS_PORT, STATUS_SAIL

MIN_SAMPLE_DAYS = 10  # 出航日樣本低於此數即退回全體統計


def percentile(values: list[float], p: float) -> float:
    """線性內插百分位數（與 numpy linear 法一致）。"""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


@dataclass
class TypeStat:
    vtype: str
    voyages: list[str] = field(default_factory=list)
    sail_fuels: list[float] = field(default_factory=list)
    port_fuels: list[float] = field(default_factory=list)

    @property
    def sail_days(self) -> int:
        return len(self.sail_fuels)

    @property
    def sail_mean(self) -> float:
        return sum(self.sail_fuels) / len(self.sail_fuels) if self.sail_fuels else 0.0

    @property
    def port_mean(self) -> float:
        return sum(self.port_fuels) / len(self.port_fuels) if self.port_fuels else 0.0

    def sail_p(self, p: float) -> float:
        return percentile(self.sail_fuels, p)


@dataclass
class RateTable:
    """2026 預估採用的油耗率與依據說明。"""

    sail_rates: dict[str, float]
    sail_basis: dict[str, str]
    port_rate: float
    overall: TypeStat
    by_type: dict[str, TypeStat]

    def sail_rate(self, vtype: str) -> float:
        return self.sail_rates.get(vtype, round(self.overall.sail_p(50), 2))


def collect_type_stats(records: list[DailyRecord],
                       type_map: dict[str, str]) -> tuple[dict[str, TypeStat], TypeStat]:
    """彙整各類型與全體的出航日/靠港日油耗樣本。"""
    by_type: dict[str, TypeStat] = {}
    overall = TypeStat(vtype="全體")
    for rec in records:
        if rec.status == STATUS_SAIL:
            overall.sail_fuels.append(rec.total_fuel)
        elif rec.status == STATUS_PORT:
            overall.port_fuels.append(rec.total_fuel)
        else:
            continue
        vtype = voyage_types.type_of_history_voyage(rec.voyage_no, type_map)
        st = by_type.setdefault(vtype, TypeStat(vtype=vtype))
        base = voyage_types.base_voyage(rec.voyage_no)
        if base and base not in st.voyages:
            st.voyages.append(base)
        if rec.status == STATUS_SAIL:
            st.sail_fuels.append(rec.total_fuel)
        else:
            st.port_fuels.append(rec.total_fuel)
    return by_type, overall


def build_rate_table(records: list[DailyRecord],
                     type_map: dict[str, str]) -> RateTable:
    """建立各類型建議油耗率（中位數；樣本不足退回全體中位數）。"""
    by_type, overall = collect_type_stats(records, type_map)
    overall_p50 = round(overall.sail_p(50), 2)
    sail_rates: dict[str, float] = {}
    sail_basis: dict[str, str] = {}
    for vtype in voyage_types.ALL_TYPES:
        st = by_type.get(vtype)
        if st and st.sail_days >= MIN_SAMPLE_DAYS:
            sail_rates[vtype] = round(st.sail_p(50), 2)
            sail_basis[vtype] = f"類型中位數（出航日 n={st.sail_days}）"
        elif st and st.sail_days > 0:
            sail_rates[vtype] = overall_p50
            sail_basis[vtype] = (f"全體出航日中位數（類型樣本不足 n={st.sail_days}"
                                 f" < {MIN_SAMPLE_DAYS}）")
        else:
            sail_rates[vtype] = overall_p50
            sail_basis[vtype] = "全體出航日中位數（無歷史樣本）"
    port_rate = round(percentile(overall.port_fuels, 50), 2)
    return RateTable(sail_rates=sail_rates, sail_basis=sail_basis,
                     port_rate=port_rate, overall=overall, by_type=by_type)


def monthly_summary(records: list[DailyRecord]) -> list[dict]:
    """歷史月份統計：各分類天數、用油與加油量。"""
    months: dict[str, dict] = {}
    for rec in records:
        key = f"{rec.day.year}/{rec.day.month:02d}"
        m = months.setdefault(key, {
            "month": key, "sail_days": 0, "port_days": 0, "dock_days": 0,
            "sail_fuel": 0.0, "port_fuel": 0.0, "total_fuel": 0.0, "refuel": 0.0,
        })
        if rec.status == STATUS_SAIL:
            m["sail_days"] += 1
            m["sail_fuel"] += rec.total_fuel
        elif rec.status == STATUS_PORT:
            m["port_days"] += 1
            m["port_fuel"] += rec.total_fuel
        else:
            m["dock_days"] += 1
        m["total_fuel"] += rec.total_fuel
        m["refuel"] += rec.refuel
    return [months[k] for k in sorted(months)]
