"""標準欄位定義與欄位對應工具。

三種資料來源（每日航務記錄、航次總表、船期表）各有一組標準欄位。
匯入時由使用者在介面上將原始 Excel 欄位對應到標準欄位。
"""

from __future__ import annotations

import re

import pandas as pd

# ---------------------------------------------------------------------------
# 每日航務記錄（SMF-07-05 TORI Daily log Abstract）標準欄位
# key = 標準欄位名稱, value = (中文顯示名稱, 是否必填)
# ---------------------------------------------------------------------------
DAILY_LOG_FIELDS: dict[str, tuple[str, bool]] = {
    "date": ("日期", True),
    "voyage_no": ("航次編號", False),
    "client": ("委託單位", False),
    "propulsion_hours": ("推進時數 (hr)", False),
    "operation_hours": ("作業時數 (hr)", False),
    "in_port_hours": ("靠港時數 (hr)", False),
    "propulsion_fuel": ("推進油耗 (KL)", False),
    "operation_fuel": ("作業油耗 (KL)", False),
    "in_port_fuel": ("靠港油耗 (KL)", False),
    "total_fuel_consumed": ("總油耗 (KL)", True),
    "refuel": ("加油量 (KL)", False),
    "rob": ("ROB 存油量 (KL)", False),
    "distance": ("航行距離 (nm)", False),
    "remark": ("備註", False),
}

# 航次總表標準欄位
VOYAGE_FIELDS: dict[str, tuple[str, bool]] = {
    "voyage_no": ("航次編號", True),
    "client": ("委託單位", False),
    "start_date": ("起始日期", True),
    "end_date": ("結束日期", False),
    "remark": ("備註", False),
}

# 船期表（未來航次／靠港／進塢期間）標準欄位
SCHEDULE_FIELDS: dict[str, tuple[str, bool]] = {
    "start_date": ("開始日期", True),
    "end_date": ("結束日期", True),
    "status": ("狀態（出航/靠港/進塢）", True),
    "voyage_no": ("航次編號", False),
    "refuel_allowed": ("可加油 (Y/N)", False),
    "remark": ("備註", False),
}

NUMERIC_DAILY_FIELDS = [
    "propulsion_hours",
    "operation_hours",
    "in_port_hours",
    "propulsion_fuel",
    "operation_fuel",
    "in_port_fuel",
    "total_fuel_consumed",
    "refuel",
    "rob",
    "distance",
]

# 自動猜測欄位對應用的關鍵字（依序比對，先中後英）
_GUESS_PATTERNS: dict[str, list[str]] = {
    "date": [r"日期", r"^date$", r"date"],
    "voyage_no": [r"航次", r"voyage", r"cruise"],
    "client": [r"委託", r"單位", r"client", r"charter"],
    "propulsion_hours": [r"推進.*(時|hr)", r"propul.*h(ou)?r", r"steam.*h(ou)?r"],
    "operation_hours": [r"作業.*(時|hr)", r"oper.*h(ou)?r", r"work.*h(ou)?r"],
    "in_port_hours": [r"靠港.*(時|hr)", r"port.*h(ou)?r", r"berth.*h(ou)?r"],
    "propulsion_fuel": [r"推進.*(油|fuel|kl)", r"propul.*(fuel|cons)"],
    "operation_fuel": [r"作業.*(油|fuel|kl)", r"oper.*(fuel|cons)"],
    "in_port_fuel": [r"靠港.*(油|fuel|kl)", r"port.*(fuel|cons)"],
    "total_fuel_consumed": [r"總油耗", r"合計.*油", r"total.*(fuel|cons)"],
    "refuel": [r"加油", r"補油", r"bunker", r"refuel"],
    "rob": [r"rob", r"存油", r"餘油"],
    "distance": [r"距離", r"浬", r"distance", r"miles?"],
    "remark": [r"備註", r"remark", r"note"],
    "start_date": [r"起始|開始|起訖", r"start", r"from"],
    "end_date": [r"結束|迄", r"end", r"to"],
    "status": [r"狀態|類別", r"status", r"type"],
    "refuel_allowed": [r"可加油", r"refuel", r"bunker"],
}


def guess_mapping(columns: list[str], fields: dict[str, tuple[str, bool]]) -> dict[str, str | None]:
    """依欄名關鍵字自動猜測「標準欄位 -> 原始欄位」的對應。"""
    mapping: dict[str, str | None] = {}
    used: set[str] = set()
    for field in fields:
        mapping[field] = None
        for pattern in _GUESS_PATTERNS.get(field, []):
            hit = next(
                (c for c in columns if c not in used and re.search(pattern, str(c), re.IGNORECASE)),
                None,
            )
            if hit is not None:
                mapping[field] = hit
                used.add(hit)
                break
    return mapping


def apply_mapping(
    df: pd.DataFrame,
    mapping: dict[str, str | None],
    fields: dict[str, tuple[str, bool]],
) -> pd.DataFrame:
    """依欄位對應將原始 DataFrame 轉成標準欄位 DataFrame。

    未對應的選填欄位以空值補齊；必填欄位缺對應時拋出 ValueError。
    """
    missing = [
        fields[f][0] for f, (_, required) in fields.items() if required and not mapping.get(f)
    ]
    if missing:
        raise ValueError(f"必填欄位尚未對應：{'、'.join(missing)}")

    out = pd.DataFrame(index=df.index)
    for field in fields:
        src = mapping.get(field)
        out[field] = df[src] if src else pd.NA
    return out
