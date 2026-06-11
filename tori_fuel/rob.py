"""ROB（Remaining On Board）推算。

參數：
- 油艙容量 465 KL
- 警戒線 150 KL
- 加油策略：補滿至 465 KL（加油量 = 465 - 加油前 ROB，加油後不得超過 465）

推算規則：當日推算 ROB = 前一日 ROB + 當日加油量 - 當日總油耗。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

TANK_CAPACITY_KL = 465.0
WARNING_LEVEL_KL = 150.0

# 推算 ROB 與記錄 ROB 的容許誤差 (KL)
ROB_TOLERANCE = 0.5


@dataclass
class RobParams:
    tank_capacity: float = TANK_CAPACITY_KL
    warning_level: float = WARNING_LEVEL_KL


def refuel_amount(rob_before: float, params: RobParams | None = None) -> float:
    """加油量 = 油艙容量 - 加油前 ROB（不為負）。"""
    p = params or RobParams()
    return max(0.0, p.tank_capacity - rob_before)


def compute_rob_series(
    df: pd.DataFrame,
    initial_rob: float | None = None,
    params: RobParams | None = None,
) -> pd.DataFrame:
    """依日期序推算每日 ROB。

    輸入需含 total_fuel_consumed，選用 refuel 與 rob（記錄值）。
    initial_rob 為第一日「期初」存油量；未提供時以第一筆記錄 ROB 回推
    （期初 = 記錄 ROB - 加油量 + 總油耗），仍無資料則以滿艙起算。

    回傳新增欄位：
    - rob_calc      推算 ROB
    - rob_diff      推算 ROB - 記錄 ROB（無記錄值為 NaN）
    - rob_mismatch  差異超出容差
    - below_warning 推算 ROB 低於警戒線
    """
    p = params or RobParams()
    out = df.copy().reset_index(drop=True)

    fuel = out["total_fuel_consumed"].fillna(0).astype(float)
    refuel = (
        out["refuel"].fillna(0).astype(float)
        if "refuel" in out.columns
        else pd.Series(0.0, index=out.index)
    )
    recorded = (
        pd.to_numeric(out["rob"], errors="coerce")
        if "rob" in out.columns
        else pd.Series(pd.NA, index=out.index, dtype="Float64")
    )

    if initial_rob is None:
        first_valid = recorded.first_valid_index()
        if first_valid is not None and first_valid == 0:
            initial_rob = float(recorded.iloc[0]) - float(refuel.iloc[0]) + float(fuel.iloc[0])
        elif first_valid is not None:
            initial_rob = float(recorded.iloc[first_valid])
        else:
            initial_rob = p.tank_capacity

    rob_calc: list[float] = []
    prev = float(initial_rob)
    for i in out.index:
        # 加油後 ROB 不得超過油艙容量
        after_refuel = min(prev + float(refuel.iloc[i]), p.tank_capacity)
        today = after_refuel - float(fuel.iloc[i])
        rob_calc.append(round(today, 3))
        prev = today

    out["rob_calc"] = rob_calc
    out["rob_diff"] = [
        round(c - float(r), 3) if pd.notna(r) else pd.NA
        for c, r in zip(rob_calc, recorded)
    ]
    out["rob_mismatch"] = [
        (abs(d) > ROB_TOLERANCE) if pd.notna(d) else False for d in out["rob_diff"]
    ]
    out["below_warning"] = [c < p.warning_level for c in rob_calc]
    return out
