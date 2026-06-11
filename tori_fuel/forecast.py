"""未來油耗預測與加油建議。

- 已發生日期：使用每日航務記錄的實際油耗。
- 未來日期：依船期表狀態（出航/靠港/進塢）採用每日平均油耗預測。
  預設值：出航 4.7 KL/天、靠港 1.6 KL/天、進塢 0 KL/天。
  可由使用者手動調整，亦可由歷史數據自動計算。

加油替代邏輯：
- 若在下次可加油日前，預測最低 ROB 會低於警戒線（150 KL），
  則建議在最近的可加油日加油，加油量 = 465 - 加油前 ROB。
- 若無法在低於警戒線前安排加油，輸出風險提醒。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .classifier import STATUS_DOCK, STATUS_IN_PORT, STATUS_SAILING
from .rob import RobParams

DEFAULT_RATES: dict[str, float] = {
    STATUS_SAILING: 4.7,
    STATUS_IN_PORT: 1.6,
    STATUS_DOCK: 0.0,
}


def historical_rates(classified_daily: pd.DataFrame) -> dict[str, float]:
    """由歷史每日記錄計算各狀態平均油耗 (KL/天)；無資料的狀態回傳預設值。"""
    rates = dict(DEFAULT_RATES)
    if classified_daily.empty or "status" not in classified_daily.columns:
        return rates
    grouped = (
        classified_daily.groupby("status")["total_fuel_consumed"].mean().dropna()
    )
    for status, value in grouped.items():
        if status in rates:
            rates[status] = round(float(value), 3)
    return rates


def expand_schedule(schedule: pd.DataFrame) -> pd.DataFrame:
    """將船期表（期間）展開為逐日列：date / status / refuel_allowed / voyage_no。"""
    rows: list[dict] = []
    for _, seg in schedule.iterrows():
        start = pd.to_datetime(seg["start_date"]).normalize()
        end = pd.to_datetime(seg["end_date"]).normalize()
        if pd.isna(start) or pd.isna(end) or end < start:
            continue
        allowed = _to_bool(seg.get("refuel_allowed"))
        for day in pd.date_range(start, end, freq="D"):
            rows.append(
                {
                    "date": day,
                    "status": str(seg["status"]).strip(),
                    "refuel_allowed": allowed,
                    "voyage_no": seg.get("voyage_no"),
                }
            )
    df = pd.DataFrame(rows, columns=["date", "status", "refuel_allowed", "voyage_no"])
    # 同日重疊以後列為準
    return df.drop_duplicates(subset="date", keep="last").sort_values("date").reset_index(drop=True)


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value) if not isinstance(value, str) else False:
        return False
    return str(value).strip().upper() in {"Y", "YES", "TRUE", "1", "是", "可", "V"}


@dataclass
class ForecastResult:
    daily: pd.DataFrame
    refuel_plan: list[dict] = field(default_factory=list)
    risk_alerts: list[str] = field(default_factory=list)


def forecast_rob(
    start_rob: float,
    future_days: pd.DataFrame,
    rates: dict[str, float] | None = None,
    params: RobParams | None = None,
    auto_refuel: bool = True,
) -> ForecastResult:
    """由起始 ROB 與逐日船期推算未來 ROB，並產生加油建議。

    future_days 欄位：date / status / refuel_allowed（expand_schedule 的輸出）。

    演算法：依日期前進，遇到可加油日時，往前看到「下一個可加油日」之間
    的最低預測 ROB；若該最低值會低於警戒線，則在本可加油日建議加油補滿。
    若已低於警戒線而其後才有可加油日（或完全沒有），輸出風險提醒。
    """
    p = params or RobParams()
    r = {**DEFAULT_RATES, **(rates or {})}

    days = future_days.sort_values("date").reset_index(drop=True)
    n = len(days)
    consumption = [float(r.get(str(days.loc[i, "status"]), 0.0)) for i in range(n)]
    refuel_ok = [bool(days.loc[i, "refuel_allowed"]) for i in range(n)]

    rob_values: list[float] = []
    refuel_amounts: list[float] = [0.0] * n
    plan: list[dict] = []
    alerts: list[str] = []

    prev = float(start_rob)
    for i in range(n):
        if auto_refuel and refuel_ok[i]:
            # 模擬不加油情況下，到下一個可加油日（含其當日耗油前）的最低 ROB
            sim = prev
            min_ahead = prev - consumption[i]
            j = i
            while True:
                sim -= consumption[j]
                min_ahead = min(min_ahead, sim)
                j += 1
                if j >= n or refuel_ok[j]:
                    break
            if min_ahead < p.warning_level:
                amount = round(p.tank_capacity - prev, 3)
                if amount > 0:
                    refuel_amounts[i] = amount
                    plan.append(
                        {
                            "date": days.loc[i, "date"],
                            "rob_before": round(prev, 3),
                            "refuel_amount": amount,
                            "rob_after": p.tank_capacity,
                            "reason": (
                                f"下次可加油日前預測最低 ROB {min_ahead:.1f} KL，"
                                f"低於警戒線 {p.warning_level:.0f} KL"
                            ),
                        }
                    )
                    prev = p.tank_capacity

        prev = min(prev, p.tank_capacity) - consumption[i]
        rob_values.append(round(prev, 3))

        if prev < p.warning_level and refuel_amounts[i] == 0:
            day_str = pd.to_datetime(days.loc[i, "date"]).strftime("%Y-%m-%d")
            if not refuel_ok[i] and not any(refuel_ok[i + 1 : n]):
                alerts.append(
                    f"風險提醒：{day_str} 預測 ROB {prev:.1f} KL 低於警戒線，"
                    f"且其後已無可加油日，請立即安排加油。"
                )
            else:
                alerts.append(
                    f"風險提醒：{day_str} 預測 ROB {prev:.1f} KL 低於警戒線 "
                    f"{p.warning_level:.0f} KL，無法在低於警戒線前安排加油。"
                )

    out = days.copy()
    out["predicted_fuel"] = consumption
    out["refuel_amount"] = refuel_amounts
    out["rob_forecast"] = rob_values
    out["below_warning"] = [v < p.warning_level for v in rob_values]
    # 去除重複提醒（連續多日低於警戒線只保留首日與最終提醒）
    alerts = alerts[:1] + ([alerts[-1]] if len(alerts) > 1 and alerts[-1] != alerts[0] else [])
    return ForecastResult(daily=out, refuel_plan=plan, risk_alerts=alerts)
