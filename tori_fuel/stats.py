"""航次油耗統計。"""

from __future__ import annotations

import pandas as pd

from .classifier import STATUS_SAILING


def voyage_summary(classified_daily: pd.DataFrame, voyages: pd.DataFrame | None = None) -> pd.DataFrame:
    """以航次編號彙整油耗統計。

    輸出欄位：航次編號、委託單位、起迄日期、總天數、出航天數、
    推進/作業/靠港油耗、總油耗、航行距離、平均每日油耗、每浬油耗。
    """
    df = classified_daily.copy()
    df = df[df["voyage_no"].notna() & (df["voyage_no"].astype(str).str.strip() != "")]
    if df.empty:
        return pd.DataFrame()

    num_cols = [
        "propulsion_fuel",
        "operation_fuel",
        "in_port_fuel",
        "total_fuel_consumed",
        "distance",
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["date"] = pd.to_datetime(df["date"])

    grouped = df.groupby("voyage_no", sort=False)
    summary = grouped.agg(
        start_date=("date", "min"),
        end_date=("date", "max"),
        days=("date", "nunique"),
        propulsion_fuel=("propulsion_fuel", "sum"),
        operation_fuel=("operation_fuel", "sum"),
        in_port_fuel=("in_port_fuel", "sum"),
        total_fuel=("total_fuel_consumed", "sum"),
        distance=("distance", "sum"),
        anomaly_days=("is_anomaly", "sum"),
    ).reset_index()

    sailing_days = (
        df[df["status"] == STATUS_SAILING].groupby("voyage_no")["date"].nunique()
    )
    summary["sailing_days"] = summary["voyage_no"].map(sailing_days).fillna(0).astype(int)

    summary["fuel_per_day"] = (summary["total_fuel"] / summary["days"]).round(2)
    summary["fuel_per_nm"] = (
        summary["total_fuel"] / summary["distance"].replace(0, pd.NA)
    ).astype(float).round(3)

    if voyages is not None and not voyages.empty and "client" in voyages.columns:
        client_map = (
            voyages.dropna(subset=["voyage_no"])
            .drop_duplicates("voyage_no")
            .set_index("voyage_no")["client"]
        )
        summary["client"] = summary["voyage_no"].map(client_map)
    elif "client" in df.columns:
        first_client = grouped["client"].first()
        summary["client"] = summary["voyage_no"].map(first_client)
    else:
        summary["client"] = pd.NA

    cols = [
        "voyage_no", "client", "start_date", "end_date", "days", "sailing_days",
        "propulsion_fuel", "operation_fuel", "in_port_fuel", "total_fuel",
        "distance", "fuel_per_day", "fuel_per_nm", "anomaly_days",
    ]
    return summary[cols]
