"""產生示範資料（模擬 SMF-07-05 每日航務記錄、航次總表、船期表）。

供使用者在尚未上傳實際 Excel 前體驗系統，也作為欄位格式範例。
"""

from __future__ import annotations

import io
import random

import pandas as pd

from .rob import TANK_CAPACITY_KL


def make_sample_daily_log(start: str = "2026-04-01", days: int = 60, seed: int = 7) -> pd.DataFrame:
    """產生帶有出航/靠港/進塢循環的每日航務記錄（含原始中文欄名）。"""
    rng = random.Random(seed)
    dates = pd.date_range(start, periods=days, freq="D")

    # 期間腳本：(天數, 型態, 航次)
    plan: list[tuple[int, str, str | None]] = [
        (4, "port", None),
        (10, "sail", "TORI-2026-08"),
        (3, "port", None),
        (12, "sail", "TORI-2026-09"),
        (5, "dock", None),
        (4, "port", None),
        (14, "sail", "TORI-2026-10"),
        (8, "port", None),
    ]
    kinds: list[tuple[str, str | None]] = []
    for n, kind, voy in plan:
        kinds += [(kind, voy)] * n
    kinds = kinds[:days]

    clients = {"TORI-2026-08": "國海院", "TORI-2026-09": "臺大海研所", "TORI-2026-10": "中山大學"}

    rows = []
    rob = 430.0
    for date, (kind, voy) in zip(dates, kinds):
        refuel = 0.0
        if kind == "sail":
            ph = round(rng.uniform(8, 16), 1)
            oh = round(rng.uniform(4, 10), 1)
            pf = round(ph * rng.uniform(0.22, 0.30), 2)
            of = round(oh * rng.uniform(0.12, 0.18), 2)
            inf = 0.0
            dist = round(ph * rng.uniform(8, 11), 1)
            iph = round(max(0.0, 24 - ph - oh), 1)
        elif kind == "port":
            ph = oh = pf = of = dist = 0.0
            inf = round(rng.uniform(1.2, 2.0), 2)
            iph = 24.0
        else:  # dock
            ph = oh = pf = of = inf = dist = 0.0
            iph = 24.0
        total = round(pf + of + inf, 2)
        if rob - total < 170 and kind == "port":
            refuel = round(TANK_CAPACITY_KL - rob, 2)
        rob = min(rob + refuel, TANK_CAPACITY_KL) - total
        rows.append(
            {
                "日期": date,
                "航次編號": voy or "",
                "委託單位": clients.get(voy, ""),
                "推進時數(hr)": ph,
                "作業時數(hr)": oh,
                "靠港時數(hr)": iph,
                "推進油耗(KL)": pf,
                "作業油耗(KL)": of,
                "靠港油耗(KL)": inf,
                "總油耗(KL)": total,
                "加油量(KL)": refuel,
                "ROB(KL)": round(rob, 2),
                "航行距離(nm)": dist,
                "備註": "進塢保養" if kind == "dock" else "",
            }
        )
    return pd.DataFrame(rows)


def make_sample_voyages() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "航次編號": ["TORI-2026-08", "TORI-2026-09", "TORI-2026-10", "TORI-2026-11"],
            "委託單位": ["國海院", "臺大海研所", "中山大學", "海洋中心"],
            "起始日期": ["2026-04-05", "2026-04-18", "2026-05-09", "2026-06-20"],
            "結束日期": ["2026-04-14", "2026-04-29", "2026-05-22", "2026-07-05"],
            "備註": ["", "", "", "預定"],
        }
    )


def make_sample_schedule(after: str = "2026-05-31") -> pd.DataFrame:
    """產生未來船期表（接在每日記錄之後）。"""
    return pd.DataFrame(
        {
            "開始日期": ["2026-06-01", "2026-06-08", "2026-06-20", "2026-07-06", "2026-07-16"],
            "結束日期": ["2026-06-07", "2026-06-19", "2026-07-05", "2026-07-15", "2026-07-31"],
            "狀態": ["靠港", "出航", "出航", "靠港", "進塢"],
            "航次編號": ["", "TORI-2026-11A", "TORI-2026-11", "", ""],
            "可加油": ["Y", "N", "N", "Y", "N"],
            "備註": ["高雄港待命", "", "", "返港整補", "歲修"],
        }
    )


def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buf.getvalue()
