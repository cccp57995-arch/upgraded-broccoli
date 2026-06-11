"""航次任務類型分類。

依委託單位與備註將航次歸入任務類型，供「各任務類型油耗率」統計與
2026 加油預估套用對應油耗率使用。
"""

from __future__ import annotations

import re

# 任務類型（統計與報表的固定順序）
TYPE_NSTC = "國科會"
TYPE_HYDRO = "內政部＋國海院（水深測量）"
TYPE_SEISMIC = "震測"
TYPE_TRIAL = "試航"
TYPE_SINICA = "中研院"
TYPE_GEO = "地礦中心"
TYPE_CHT = "中華電信"
TYPE_DOCK = "進塢"
TYPE_OTHER = "其他/未分類"

ALL_TYPES = [
    TYPE_NSTC, TYPE_HYDRO, TYPE_SEISMIC, TYPE_TRIAL,
    TYPE_SINICA, TYPE_GEO, TYPE_CHT,
]

_CLIENT_TYPE = {
    "國科會": TYPE_NSTC,
    "中研院": TYPE_SINICA,
    "地礦中心": TYPE_GEO,
    "中華電信": TYPE_CHT,
    "試航": TYPE_TRIAL,
}

_BASE_RE = re.compile(r"^(LGD-(?:T\d+|\d{4}))")


def base_voyage(voyage_no: str) -> str:
    """去除航次編號的延伸後綴：LGD-2602-1 → LGD-2602、LGD-T65-B → LGD-T65。"""
    if not voyage_no:
        return ""
    m = _BASE_RE.match(str(voyage_no).strip().upper().replace("LGD", "LGD-").replace("--", "-"))
    return m.group(1) if m else str(voyage_no).strip()


def classify_voyage(client: str, pi_remark: str = "", remark: str = "") -> str:
    """由委託單位與備註判定任務類型。震測關鍵字優先於委託單位。"""
    text = f"{pi_remark or ''}{remark or ''}"
    if "進塢" in text or "塢修" in text:
        return TYPE_DOCK
    if "震測" in text:
        return TYPE_SEISMIC
    client = (client or "").strip()
    if "內政部" in client or "國海院" in client:
        return TYPE_HYDRO
    if "TORI" in client.upper():
        return TYPE_OTHER
    return _CLIENT_TYPE.get(client, TYPE_OTHER if client else TYPE_OTHER)


def history_type_map(voyages: list) -> dict[str, str]:
    """由航次總表建立「航次編號 → 任務類型」對照（含 T 航次規則）。

    歷史每日記錄中的航次以 base_voyage 正規化後查表；查不到且編號為
    LGD-Txx 者視為試航，其餘歸「其他/未分類」。
    """
    mapping: dict[str, str] = {}
    for v in voyages:
        mapping[base_voyage(v.voyage_no)] = v.vtype
    return mapping


def type_of_history_voyage(voyage_no: str, mapping: dict[str, str]) -> str:
    base = base_voyage(voyage_no)
    if base in mapping:
        return mapping[base]
    if base.startswith("LGD-T"):
        return TYPE_TRIAL
    return TYPE_OTHER
