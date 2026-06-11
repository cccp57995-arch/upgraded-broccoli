"""TORI 勵進研究船 2026 加油計畫產生器（CLI）。

用法：
    python build_plan.py \
        --history data/TORI_FuelConsumption_Summary.xlsx \
        --voyages data/TORI_2026_voyages.csv \
        --out output/TORI_2026_加油計畫.xlsx

歷史檔支援兩種格式：
- TORI_FuelConsumption_Summary（「每日明細」＋「2026逐日ROB」工作表）
- SMF-07-05 TORI Daily log Abstract 原始格式（--smf 指定）
"""

from __future__ import annotations

import argparse
import os

from tori_fuel import history, plan2026, typestats, voyage_types
from tori_fuel.report import build_workbook


def main() -> None:
    ap = argparse.ArgumentParser(description="TORI 2026 加油計畫產生器")
    ap.add_argument("--history", default="data/TORI_FuelConsumption_Summary.xlsx",
                    help="歷史每日油耗 Excel")
    ap.add_argument("--smf", action="store_true",
                    help="歷史檔為 SMF-07-05 原始 Daily Log 格式")
    ap.add_argument("--voyages", default="data/TORI_2026_voyages.csv",
                    help="2026 航次總表 CSV")
    ap.add_argument("--out", default="output/TORI_2026_加油計畫.xlsx")
    args = ap.parse_args()

    if args.smf:
        records = history.load_smf_daily_log(args.history)
        actual = history.Actual2026()
    else:
        records = history.load_summary_daily(args.history)
        actual = history.load_actual_2026(args.history)
    print(f"歷史記錄 {len(records)} 天"
          f"（{records[0].day:%Y/%m/%d} – {records[-1].day:%Y/%m/%d}）")

    voyages = plan2026.load_voyages_csv(args.voyages)
    print(f"2026 航次 {len(voyages)} 段")

    type_map = voyage_types.history_type_map(voyages)
    rates = typestats.build_rate_table(records, type_map)
    print("各類型出航油耗率（KL/日）：")
    for vtype in voyage_types.ALL_TYPES:
        print(f"  {vtype}: {rates.sail_rates[vtype]}（{rates.sail_basis[vtype]}）")
    print(f"  靠港日: {rates.port_rate}")

    plan = plan2026.build_plan(voyages, rates, actual)
    print(f"年初 ROB {plan.initial_rob:.1f} KL；加油 {len(plan.refuels)} 次：")
    for ev in plan.refuels:
        tag = "實際" if ev.is_actual else "預估"
        print(f"  {ev.day:%Y/%m/%d} {ev.after}: {ev.amount:.1f} KL "
              f"({ev.rob_before:.1f} → {ev.rob_after:.1f}) [{tag}]")
    for alert in plan.alerts:
        print(f"  ⚠ {alert}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    build_workbook(records, rates, plan).save(args.out)
    print(f"已輸出：{args.out}")


if __name__ == "__main__":
    main()
