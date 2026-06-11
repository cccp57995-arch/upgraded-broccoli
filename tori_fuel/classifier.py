"""航次日分類規則。

分類順序固定：
1. total_fuel_consumed == 0           -> 進塢（優先於其他規則）
2. propulsion_hours > 0 或 operation_hours > 0 或 distance != 0
   或 propulsion_fuel > 0 或 operation_fuel > 0 或 in_port_fuel == 0
                                      -> 出航
3. 其餘                                -> 靠港

若欄位相互矛盾仍依上述規則分類，但標示「資料異常」並列出原因。
"""

from __future__ import annotations

import pandas as pd

STATUS_DOCK = "進塢"
STATUS_SAILING = "出航"
STATUS_IN_PORT = "靠港"

# 元件油耗加總與總油耗的容許誤差 (KL)
FUEL_SUM_TOLERANCE = 0.05


def _num(value) -> float:
    """空值視為 0，無法轉數字也視為 0（同時會被異常檢查捕捉）。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if pd.isna(v) else v


def classify_day(row: dict | pd.Series) -> tuple[str, list[str]]:
    """分類單一航務日，回傳 (分類, 異常原因清單)。"""
    prop_h = _num(row.get("propulsion_hours"))
    oper_h = _num(row.get("operation_hours"))
    prop_f = _num(row.get("propulsion_fuel"))
    oper_f = _num(row.get("operation_fuel"))
    port_f = _num(row.get("in_port_fuel"))
    total_f = _num(row.get("total_fuel_consumed"))
    dist = _num(row.get("distance"))

    # --- 固定順序分類 ---
    if total_f == 0:
        status = STATUS_DOCK
    elif prop_h > 0 or oper_h > 0 or dist != 0 or prop_f > 0 or oper_f > 0 or port_f == 0:
        status = STATUS_SAILING
    else:
        status = STATUS_IN_PORT

    # --- 資料異常檢查（不影響分類結果） ---
    anomalies: list[str] = []

    component_sum = prop_f + oper_f + port_f
    if total_f > 0 and abs(component_sum - total_f) > FUEL_SUM_TOLERANCE:
        anomalies.append(
            f"分項油耗加總 {component_sum:.2f} 與總油耗 {total_f:.2f} 不符"
        )

    if status == STATUS_DOCK:
        if prop_h > 0 or oper_h > 0:
            anomalies.append("總油耗為 0（進塢）但仍有推進/作業時數")
        if dist != 0:
            anomalies.append("總油耗為 0（進塢）但航行距離不為 0")
        if component_sum > 0:
            anomalies.append("總油耗為 0（進塢）但分項油耗不為 0")

    if status == STATUS_SAILING:
        if prop_h > 0 and prop_f == 0:
            anomalies.append("有推進時數但推進油耗為 0")
        if prop_f > 0 and prop_h == 0:
            anomalies.append("有推進油耗但推進時數為 0")
        if oper_h > 0 and oper_f == 0:
            anomalies.append("有作業時數但作業油耗為 0")
        if dist == 0 and prop_h > 0:
            anomalies.append("有推進時數但航行距離為 0")

    if status == STATUS_IN_PORT and port_f == 0:
        anomalies.append("分類為靠港但靠港油耗為 0")

    return status, anomalies


def classify_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """對整份每日航務記錄分類，新增 status / is_anomaly / anomaly_reasons 欄位。"""
    results = df.apply(lambda r: classify_day(r), axis=1)
    out = df.copy()
    out["status"] = [r[0] for r in results]
    out["anomaly_reasons"] = ["；".join(r[1]) for r in results]
    out["is_anomaly"] = [bool(r[1]) for r in results]
    return out
