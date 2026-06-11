"""2026 加油計畫：航次展開、依類型套用油耗率、ROB 推算與加油排程。

- 油艙上限 465 KL、警戒線 150 KL，加油補滿至 465 KL
  （已發生的加油以實際加油量為準）。
- 加油時機由航次備註自動推導：
  「出塢加油」→ 進塢結束次日；「加燃油」→ 該航次返港次日。
- 預估 ROB 自年初連續推算；實際欄位僅在有資料的日期填入，
  耗油誤差 = 實際日耗油 − 預估日耗油。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import voyage_types
from .history import Actual2026, STATUS_DOCK, STATUS_PORT, STATUS_SAIL, _to_date
from .typestats import RateTable

TANK_CAPACITY_KL = 465.0
WARNING_LEVEL_KL = 150.0


@dataclass
class Voyage:
    voyage_no: str
    client: str
    pi: str
    start: date
    end: date
    remark: str = ""
    vtype: str = ""

    @property
    def is_dock(self) -> bool:
        return self.vtype == voyage_types.TYPE_DOCK

    @property
    def refuel_after(self) -> bool:
        text = self.remark or ""
        return "加燃油" in text or "加油" in text


@dataclass
class PlanDay:
    day: date
    voyage_no: str = ""
    vtype: str = ""
    status: str = STATUS_PORT
    est_fuel: float = 0.0
    est_rob: float = 0.0
    refuel_est: float = 0.0
    actual_fuel: float | None = None
    actual_rob: float | None = None
    refuel_actual: float | None = None
    below_warning: bool = False

    @property
    def fuel_error(self) -> float | None:
        if self.actual_fuel is None:
            return None
        return round(self.actual_fuel - self.est_fuel, 1)


@dataclass
class RefuelEvent:
    day: date
    after: str          # 觸發來源（航次編號或塢修）
    rob_before: float = 0.0
    amount: float = 0.0
    rob_after: float = 0.0
    is_actual: bool = False


@dataclass
class VoyagePlan:
    voyage: Voyage
    sail_days: int = 0
    port_days: int = 0
    sail_rate: float = 0.0
    port_rate: float = 0.0
    est_fuel: float = 0.0
    end_rob: float = 0.0
    refuel_day: date | None = None
    refuel_amount: float = 0.0


@dataclass
class Plan2026:
    days: list[PlanDay] = field(default_factory=list)
    voyages: list[VoyagePlan] = field(default_factory=list)
    refuels: list[RefuelEvent] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    initial_rob: float = 0.0


def load_voyages_csv(path: str) -> list[Voyage]:
    voyages: list[Voyage] = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            start = _to_date(row["預計出海日"])
            end = _to_date(row["預計返港日"])
            if start is None or end is None:
                continue
            v = Voyage(
                voyage_no=row["航次"].strip(),
                client=(row.get("委託單位") or "").strip(),
                pi=(row.get("負責老師/備註") or "").strip(),
                start=start, end=end,
                remark=(row.get("備註") or "").strip(),
            )
            v.vtype = voyage_types.classify_voyage(v.client, v.pi, v.remark)
            voyages.append(v)
    voyages.sort(key=lambda v: v.start)
    return voyages


def derive_refuel_days(voyages: list[Voyage]) -> list[tuple[date, str]]:
    """加油日 = 標註加油之航段（或塢修）結束的次日。"""
    return [(v.end + timedelta(days=1), v.voyage_no)
            for v in voyages if v.refuel_after]


def _infer_initial_rob(actual: Actual2026, year: int) -> float:
    """年初 ROB：以最早一筆實際 ROB 回推（ROB + 當日油耗 − 當日加油）。"""
    if not actual.rob:
        return TANK_CAPACITY_KL * 0.55
    first = min(actual.rob)
    rob = actual.rob[first]
    fuel = actual.daily_fuel.get(first, 0.0)
    refuel = actual.refuel.get(first, 0.0)
    return round(rob + fuel - refuel, 1)


def build_plan(voyages: list[Voyage], rates: RateTable,
               actual: Actual2026 | None = None, year: int = 2026) -> Plan2026:
    actual = actual or Actual2026()
    plan = Plan2026()
    plan.initial_rob = _infer_initial_rob(actual, year)

    refuel_days = dict(derive_refuel_days(voyages))
    day_voyage: dict[date, Voyage] = {}
    for v in voyages:
        d = v.start
        while d <= v.end:
            day_voyage[d] = v
            d += timedelta(days=1)

    rob = plan.initial_rob
    d = date(year, 1, 1)
    end = date(year, 12, 31)
    while d <= end:
        pd = PlanDay(day=d)
        v = day_voyage.get(d)
        if v is not None:
            pd.voyage_no = v.voyage_no
            pd.vtype = v.vtype
            if v.is_dock:
                pd.status = STATUS_DOCK
                pd.est_fuel = 0.0
            else:
                pd.status = STATUS_SAIL
                pd.est_fuel = rates.sail_rate(v.vtype)
        else:
            pd.status = STATUS_PORT
            pd.est_fuel = rates.port_rate

        if d in refuel_days:
            rob_before = rob
            amount = actual.refuel.get(d, round(TANK_CAPACITY_KL - rob_before, 1))
            pd.refuel_est = amount
            rob = min(rob_before + amount, TANK_CAPACITY_KL)
            plan.refuels.append(RefuelEvent(
                day=d, after=refuel_days[d], rob_before=round(rob_before, 1),
                amount=round(amount, 1), rob_after=round(rob, 1),
                is_actual=d in actual.refuel,
            ))
        elif d in actual.refuel:
            # 計畫外的實際加油（保險：仍反映於預估 ROB）
            amount = actual.refuel[d]
            pd.refuel_est = amount
            rob_before = rob
            rob = min(rob + amount, TANK_CAPACITY_KL)
            plan.refuels.append(RefuelEvent(
                day=d, after="（實際）", rob_before=round(rob_before, 1),
                amount=round(amount, 1), rob_after=round(rob, 1), is_actual=True,
            ))

        rob -= pd.est_fuel
        pd.est_rob = round(rob, 1)
        pd.below_warning = rob < WARNING_LEVEL_KL
        pd.actual_fuel = actual.daily_fuel.get(d)
        pd.actual_rob = actual.rob.get(d)
        pd.refuel_actual = actual.refuel.get(d)
        plan.days.append(pd)
        d += timedelta(days=1)

    _summarize_voyages(plan, voyages, rates)
    _check_alerts(plan)
    return plan


def _summarize_voyages(plan: Plan2026, voyages: list[Voyage],
                       rates: RateTable) -> None:
    """各航次（航段）摘要：出航/靠港天數、套用油耗率、預估用油與結束 ROB。"""
    by_day = {pd.day: pd for pd in plan.days}
    refuel_by_src: dict[str, RefuelEvent] = {}
    for ev in plan.refuels:
        refuel_by_src.setdefault(ev.after, ev)
    for i, v in enumerate(voyages):
        nxt = voyages[i + 1].start if i + 1 < len(voyages) else date(v.end.year + 1, 1, 1)
        sail_days = (v.end - v.start).days + 1
        port_days = max((nxt - v.end).days - 1, 0)
        sail_rate = 0.0 if v.is_dock else rates.sail_rate(v.vtype)
        est = sail_days * sail_rate + port_days * rates.port_rate
        vp = VoyagePlan(
            voyage=v, sail_days=sail_days, port_days=port_days,
            sail_rate=sail_rate, port_rate=rates.port_rate,
            est_fuel=round(est, 1),
            end_rob=by_day[v.end].est_rob if v.end in by_day else 0.0,
        )
        ev = refuel_by_src.get(v.voyage_no)
        if ev:
            vp.refuel_day, vp.refuel_amount = ev.day, ev.amount
        plan.voyages.append(vp)


def _check_alerts(plan: Plan2026) -> None:
    run_start = None
    for pd in plan.days:
        if pd.below_warning and run_start is None:
            run_start = pd.day
        elif not pd.below_warning and run_start is not None:
            plan.alerts.append(
                f"{run_start:%Y/%m/%d}–{pd.day - timedelta(days=1):%m/%d} "
                f"預估 ROB 低於警戒線 {WARNING_LEVEL_KL:.0f} KL，請提前安排加油")
            run_start = None
    if run_start is not None:
        plan.alerts.append(
            f"{run_start:%Y/%m/%d} 起預估 ROB 低於警戒線 {WARNING_LEVEL_KL:.0f} KL，"
            f"請提前安排加油")
