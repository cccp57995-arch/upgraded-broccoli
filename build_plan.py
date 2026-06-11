"""TORI 勵進研究船 2026 加油計畫產生器（CLI）。

用法（預設：兩份資料合併）：
    python build_plan.py \
        --history data/TORI_FuelConsumption_Summary.xlsx \
        --smf     data/SMF0705_TORI_Daily_log_Abstract.xlsx \
        --voyages data/TORI_2026_voyages.csv \
        --out     output/TORI_2026_加油計畫.xlsx

只用整理格式（無原始 SMF）：
    python build_plan.py --history data/TORI_FuelConsumption_Summary.xlsx

只用原始 SMF（無整理格式）：
    python build_plan.py --smf data/SMF0705_TORI_Daily_log_Abstract.xlsx

資料合併策略：SMF 中有的日期以 SMF 為準（覆蓋整理格式同日資料）。
2026 年 actual 資料從 SMF 自動回填至 Actual2026（超過整理格式最後一天者）。
"""

from __future__ import annotations

import argparse
import os
from datetime import date

from tori_fuel import history, voyage_types
from tori_fuel.history import Actual2026
from tori_fuel.plan2026 import build_plan, load_voyages_csv
from tori_fuel.report import build_workbook
from tori_fuel.typestats import build_rate_table


def _smf_to_actual(smf_records: list, from_day: date) -> Actual2026:
    """從 SMF 記錄補充 actual（取 from_day 以後的日期）。"""
    actual = Actual2026()
    for r in smf_records:
        if r.day < from_day:
            continue
        actual.daily_fuel[r.day] = r.total_fuel
        if r.rob is not None:
            actual.rob[r.day] = r.rob
        if r.refuel > 0:
            actual.refuel[r.day] = r.refuel
        if r.voyage_no:
            actual.voyage[r.day] = r.voyage_no
    return actual


def _merge_actual(base: Actual2026, overlay: Actual2026) -> Actual2026:
    merged = Actual2026(
        daily_fuel={**base.daily_fuel, **overlay.daily_fuel},
        rob={**base.rob, **overlay.rob},
        refuel={**base.refuel, **overlay.refuel},
        voyage={**base.voyage, **overlay.voyage},
    )
    return merged


def main() -> None:
    ap = argparse.ArgumentParser(description="TORI 2026 加油計畫產生器")
    ap.add_argument("--history", default="data/TORI_FuelConsumption_Summary.xlsx",
                    help="整理格式每日油耗 Excel（含每日明細＋2026逐日ROB）")
    ap.add_argument("--smf", default="data/SMF0705_TORI_Daily_log_Abstract.xlsx",
                    help="SMF-07-05 V2 原始 Daily Log（覆蓋同日整理格式資料）")
    ap.add_argument("--voyages", default="data/TORI_2026_voyages.csv",
                    help="2026 航次總表 CSV")
    ap.add_argument("--out", default="output/TORI_2026_加油計畫.xlsx")
    args = ap.parse_args()

    # 1. 歷史記錄（整理格式 + SMF 覆蓋）
    smf_records = []
    records = []
    if os.path.exists(args.history):
        records = history.load_summary_daily(args.history)
        print(f"整理格式 {len(records)} 天（{records[0].day} ~ {records[-1].day}）")
    if os.path.exists(args.smf):
        smf_records = history.load_smf_daily_log(args.smf)
        print(f"SMF 原始 {len(smf_records)} 天（{smf_records[0].day} ~ {smf_records[-1].day}）")
        records = history.merge_records(records, smf_records) if records else smf_records
    if not records:
        print("ERROR: 未找到任何歷史資料，請至少提供 --history 或 --smf 其中之一。")
        return
    print(f"合併後歷史 {len(records)} 天（{records[0].day} ~ {records[-1].day}）")

    # 2. actual 2026（整理格式為主，SMF 補充更新部分）
    actual = Actual2026()
    if os.path.exists(args.history):
        actual = history.load_actual_2026(args.history)
        print(f"整理格式 actual：{len(actual.daily_fuel)} 天")
    if smf_records:
        summary_last = max(actual.daily_fuel) if actual.daily_fuel else date(2025, 12, 31)
        smf_actual = _smf_to_actual(smf_records, from_day=date(summary_last.year, 1, 1))
        actual = _merge_actual(actual, smf_actual)
        print(f"合併後 actual：{len(actual.daily_fuel)} 天，最後 {max(actual.daily_fuel)}")

    # 3. 航次與油耗率
    voyages = load_voyages_csv(args.voyages)
    print(f"2026 航次 {len(voyages)} 段")
    type_map = voyage_types.history_type_map(voyages)
    rates = build_rate_table(records, type_map)
    print("各類型出航油耗率（KL/日）：")
    for vtype in voyage_types.ALL_TYPES:
        print(f"  {vtype}: {rates.sail_rates[vtype]}（{rates.sail_basis[vtype]}）")
    print(f"  靠港日: {rates.port_rate}")

    # 4. 建立計畫
    plan = build_plan(voyages, rates, actual)
    print(f"年初 ROB {plan.initial_rob:.1f} KL；加油 {len(plan.refuels)} 次：")
    for ev in plan.refuels:
        tag = "實際" if ev.is_actual else "預估"
        print(f"  {ev.day:%Y/%m/%d} {ev.after}: {ev.amount:.1f} KL "
              f"({ev.rob_before:.1f}→{ev.rob_after:.1f}) [{tag}]")
    for alert in plan.alerts:
        print(f"  ⚠ {alert}")

    # 5. 輸出
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    build_workbook(records, rates, plan).save(args.out)
    print(f"已輸出：{args.out}")


if __name__ == "__main__":
    main()
