"""TORI 勵進研究船燃油消耗管理系統 — Streamlit 主程式。

啟動方式：streamlit run app.py
"""

from __future__ import annotations

import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tori_fuel import classifier, forecast, rob, sample_data, schema, stats

st.set_page_config(
    page_title="TORI 勵進研究船燃油消耗管理系統",
    page_icon="⚓",
    layout="wide",
)

st.markdown(
    """
    <style>
    .main-title {font-size: 1.7rem; font-weight: 700; color: #0b3d62;
                 border-bottom: 3px solid #0b3d62; padding-bottom: .4rem;}
    .sub-note {color: #5a6b7b; font-size: .9rem;}
    div[data-testid="stMetric"] {background: #f4f7fa; border: 1px solid #d7e0e8;
                                 border-radius: 6px; padding: 10px 14px;}
    </style>
    <div class="main-title">⚓ TORI 勵進研究船燃油消耗管理系統</div>
    <div class="sub-note">R/V Legend — Fuel Consumption Management System｜
    油艙容量 465 KL｜警戒線 150 KL｜加油策略：補滿至 465 KL</div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state 初始化
# ---------------------------------------------------------------------------
for key in ("daily_log", "voyages", "schedule"):
    st.session_state.setdefault(key, None)
st.session_state.setdefault("rates", dict(forecast.DEFAULT_RATES))


def read_excel(uploaded) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(uploaded.getvalue()))


def mapping_ui(label: str, df: pd.DataFrame, fields: dict, key_prefix: str) -> dict:
    """欄位對應介面：每個標準欄位選擇對應的原始欄位。"""
    st.markdown(f"**{label} — 欄位對應**（原始欄位 → 標準欄位）")
    guessed = schema.guess_mapping(list(df.columns), fields)
    options = ["（不對應）"] + [str(c) for c in df.columns]
    mapping: dict[str, str | None] = {}
    cols = st.columns(3)
    for i, (field_name, (zh, required)) in enumerate(fields.items()):
        with cols[i % 3]:
            default = guessed.get(field_name)
            idx = options.index(str(default)) if default is not None else 0
            choice = st.selectbox(
                f"{zh}{' *' if required else ''}（{field_name}）",
                options,
                index=idx,
                key=f"{key_prefix}_{field_name}",
            )
            mapping[field_name] = None if choice == "（不對應）" else choice
    return mapping


def coerce_daily(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    for c in schema.NUMERIC_DAILY_FIELDS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def status_color(s: str) -> str:
    return {"出航": "#1f77b4", "靠港": "#2ca02c", "進塢": "#7f7f7f"}.get(s, "#999")


tab_import, tab_daily, tab_voyage, tab_rob, tab_refuel = st.tabs(
    ["📥 資料匯入與欄位對應", "📋 每日油耗報告", "🚢 航次油耗統計",
     "🛢 ROB 推算", "⛽ 油量預測與加油建議"]
)

# ===========================================================================
# 一、資料匯入與欄位對應
# ===========================================================================
with tab_import:
    st.subheader("資料匯入")
    if st.button("載入示範資料（模擬 2026-04 ~ 2026-07 資料）"):
        raw = sample_data.make_sample_daily_log()
        m = schema.guess_mapping(list(raw.columns), schema.DAILY_LOG_FIELDS)
        st.session_state.daily_log = classifier.classify_dataframe(
            coerce_daily(schema.apply_mapping(raw, m, schema.DAILY_LOG_FIELDS))
        )
        rawv = sample_data.make_sample_voyages()
        mv = schema.guess_mapping(list(rawv.columns), schema.VOYAGE_FIELDS)
        st.session_state.voyages = schema.apply_mapping(rawv, mv, schema.VOYAGE_FIELDS)
        raws = sample_data.make_sample_schedule()
        ms = schema.guess_mapping(list(raws.columns), schema.SCHEDULE_FIELDS)
        st.session_state.schedule = schema.apply_mapping(raws, ms, schema.SCHEDULE_FIELDS)
        st.success("示範資料已載入。")

    st.markdown("---")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("#### 1. 每日航務記錄")
        st.caption("SMF-07-05 TORI Daily log Abstract（Excel）")
        f1 = st.file_uploader("上傳每日航務記錄", type=["xlsx", "xls"], key="up_daily")
        if f1:
            raw = read_excel(f1)
            st.dataframe(raw.head(5), use_container_width=True)
            m = mapping_ui("每日航務記錄", raw, schema.DAILY_LOG_FIELDS, "d")
            if st.button("套用對應並匯入", key="apply_daily"):
                try:
                    std = coerce_daily(schema.apply_mapping(raw, m, schema.DAILY_LOG_FIELDS))
                    st.session_state.daily_log = classifier.classify_dataframe(std)
                    st.success(f"已匯入 {len(std)} 筆每日記錄並完成分類。")
                except ValueError as e:
                    st.error(str(e))

    with c2:
        st.markdown("#### 2. 航次總表")
        st.caption("航次編號、委託單位、起迄日期（Excel）")
        f2 = st.file_uploader("上傳航次總表", type=["xlsx", "xls"], key="up_voy")
        if f2:
            raw = read_excel(f2)
            st.dataframe(raw.head(5), use_container_width=True)
            m = mapping_ui("航次總表", raw, schema.VOYAGE_FIELDS, "v")
            if st.button("套用對應並匯入", key="apply_voy"):
                try:
                    st.session_state.voyages = schema.apply_mapping(raw, m, schema.VOYAGE_FIELDS)
                    st.success(f"已匯入 {len(raw)} 筆航次。")
                except ValueError as e:
                    st.error(str(e))

    with c3:
        st.markdown("#### 3. 船期表")
        st.caption("未來航次／靠港／進塢期間與可加油時機（Excel 或圖片）")
        f3 = st.file_uploader("上傳船期表", type=["xlsx", "xls", "png", "jpg", "jpeg"], key="up_sch")
        if f3 and f3.name.lower().endswith((".png", ".jpg", ".jpeg")):
            st.image(f3, caption="船期表圖片（請依圖片內容於下方手動編輯船期）")
        elif f3:
            raw = read_excel(f3)
            st.dataframe(raw.head(5), use_container_width=True)
            m = mapping_ui("船期表", raw, schema.SCHEDULE_FIELDS, "s")
            if st.button("套用對應並匯入", key="apply_sch"):
                try:
                    st.session_state.schedule = schema.apply_mapping(raw, m, schema.SCHEDULE_FIELDS)
                    st.success(f"已匯入 {len(raw)} 段船期。")
                except ValueError as e:
                    st.error(str(e))

    st.markdown("---")
    st.markdown("#### 船期表編輯（圖片船期請在此手動輸入；亦可修正匯入結果）")
    base = st.session_state.schedule
    if base is None:
        base = pd.DataFrame(columns=list(schema.SCHEDULE_FIELDS))
    edited = st.data_editor(
        base,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "status": st.column_config.SelectboxColumn("狀態", options=["出航", "靠港", "進塢"]),
            "refuel_allowed": st.column_config.SelectboxColumn("可加油", options=["Y", "N"]),
        },
        key="schedule_editor",
    )
    if st.button("儲存船期表"):
        st.session_state.schedule = edited
        st.success("船期表已更新。")

# ===========================================================================
# 二、每日油耗報告（含分類與資料異常）
# ===========================================================================
with tab_daily:
    st.subheader("每日油耗報告")
    daily = st.session_state.daily_log
    if daily is None:
        st.info("請先於「資料匯入」頁匯入每日航務記錄，或載入示範資料。")
    else:
        n_anom = int(daily["is_anomaly"].sum())
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("記錄天數", f"{len(daily)} 天")
        m2.metric("出航天數", f"{(daily['status'] == '出航').sum()} 天")
        m3.metric("靠港天數", f"{(daily['status'] == '靠港').sum()} 天")
        m4.metric("進塢天數", f"{(daily['status'] == '進塢').sum()} 天")
        m5.metric("資料異常", f"{n_anom} 筆", delta_color="inverse")

        show = daily.copy()
        show["date"] = show["date"].dt.strftime("%Y-%m-%d")
        show["資料異常"] = show["anomaly_reasons"].where(show["is_anomaly"], "")
        rename = {f: zh for f, (zh, _) in schema.DAILY_LOG_FIELDS.items()}
        rename["status"] = "分類"
        only_anom = st.checkbox("僅顯示資料異常列")
        view = show[show["is_anomaly"]] if only_anom else show
        st.dataframe(
            view.drop(columns=["is_anomaly", "anomaly_reasons"]).rename(columns=rename),
            use_container_width=True, height=420,
        )

        fig = go.Figure()
        for s in ("出航", "靠港", "進塢"):
            part = daily[daily["status"] == s]
            fig.add_bar(x=part["date"], y=part["total_fuel_consumed"],
                        name=s, marker_color=status_color(s))
        fig.update_layout(title="每日總油耗（依分類）", yaxis_title="KL/天",
                          barmode="overlay", height=380, legend_orientation="h")
        st.plotly_chart(fig, use_container_width=True)

        st.download_button(
            "下載每日報告 (Excel)",
            sample_data.to_excel_bytes(view.rename(columns=rename), "每日油耗報告"),
            file_name="TORI_每日油耗報告.xlsx",
        )

# ===========================================================================
# 三、航次油耗統計
# ===========================================================================
with tab_voyage:
    st.subheader("航次油耗統計")
    daily = st.session_state.daily_log
    if daily is None:
        st.info("請先匯入每日航務記錄。")
    else:
        summary = stats.voyage_summary(daily, st.session_state.voyages)
        if summary.empty:
            st.warning("每日記錄中沒有航次編號，無法彙整航次統計。")
        else:
            disp = summary.copy()
            disp["start_date"] = disp["start_date"].dt.strftime("%Y-%m-%d")
            disp["end_date"] = disp["end_date"].dt.strftime("%Y-%m-%d")
            disp = disp.rename(columns={
                "voyage_no": "航次編號", "client": "委託單位",
                "start_date": "開始日期", "end_date": "結束日期",
                "days": "總天數", "sailing_days": "出航天數",
                "propulsion_fuel": "推進油耗(KL)", "operation_fuel": "作業油耗(KL)",
                "in_port_fuel": "靠港油耗(KL)", "total_fuel": "總油耗(KL)",
                "distance": "航行距離(nm)", "fuel_per_day": "平均日油耗(KL/天)",
                "fuel_per_nm": "每浬油耗(KL/nm)", "anomaly_days": "異常天數",
            })
            st.dataframe(disp, use_container_width=True)

            fig = go.Figure()
            fig.add_bar(x=summary["voyage_no"], y=summary["propulsion_fuel"], name="推進油耗")
            fig.add_bar(x=summary["voyage_no"], y=summary["operation_fuel"], name="作業油耗")
            fig.add_bar(x=summary["voyage_no"], y=summary["in_port_fuel"], name="靠港油耗")
            fig.update_layout(barmode="stack", title="各航次油耗組成",
                              yaxis_title="KL", height=380, legend_orientation="h")
            st.plotly_chart(fig, use_container_width=True)

            st.download_button(
                "下載航次統計 (Excel)",
                sample_data.to_excel_bytes(disp, "航次油耗統計"),
                file_name="TORI_航次油耗統計.xlsx",
            )

# ===========================================================================
# 四、ROB 推算
# ===========================================================================
with tab_rob:
    st.subheader("ROB 推算（當日 ROB = 前一日 ROB + 當日加油量 − 當日總油耗）")
    daily = st.session_state.daily_log
    if daily is None:
        st.info("請先匯入每日航務記錄。")
    else:
        init = st.number_input(
            "期初 ROB（KL；0 = 依第一筆記錄 ROB 自動回推）",
            min_value=0.0, max_value=rob.TANK_CAPACITY_KL, value=0.0, step=1.0,
        )
        result = rob.compute_rob_series(daily, initial_rob=init or None)

        if result.empty:
            st.warning("每日記錄為空，無法推算 ROB。")
            st.stop()

        last = result.iloc[-1]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("最新推算 ROB", f"{last['rob_calc']:.1f} KL")
        m2.metric("油艙容量", f"{rob.TANK_CAPACITY_KL:.0f} KL")
        m3.metric("警戒線", f"{rob.WARNING_LEVEL_KL:.0f} KL")
        m4.metric("與記錄 ROB 不符天數", f"{int(result['rob_mismatch'].sum())} 天")

        fig = go.Figure()
        fig.add_scatter(x=result["date"], y=result["rob_calc"], name="推算 ROB",
                        mode="lines+markers", line_color="#0b3d62")
        if result["rob"].notna().any():
            fig.add_scatter(x=result["date"], y=result["rob"], name="記錄 ROB",
                            mode="markers", marker_color="#d62728", marker_symbol="x")
        fig.add_hline(y=rob.WARNING_LEVEL_KL, line_dash="dash", line_color="red",
                      annotation_text="警戒線 150 KL")
        fig.add_hline(y=rob.TANK_CAPACITY_KL, line_dash="dot", line_color="gray",
                      annotation_text="油艙容量 465 KL")
        fig.update_layout(title="ROB 推算 vs 記錄", yaxis_title="KL",
                          height=420, legend_orientation="h")
        st.plotly_chart(fig, use_container_width=True)

        showr = result[["date", "status", "refuel", "total_fuel_consumed",
                        "rob", "rob_calc", "rob_diff", "rob_mismatch", "below_warning"]].copy()
        showr["date"] = showr["date"].dt.strftime("%Y-%m-%d")
        showr = showr.rename(columns={
            "date": "日期", "status": "分類", "refuel": "加油量(KL)",
            "total_fuel_consumed": "總油耗(KL)", "rob": "記錄ROB(KL)",
            "rob_calc": "推算ROB(KL)", "rob_diff": "差異(KL)",
            "rob_mismatch": "差異超容差", "below_warning": "低於警戒線",
        })
        st.dataframe(showr, use_container_width=True, height=360)

# ===========================================================================
# 五、油量預測與加油建議
# ===========================================================================
with tab_refuel:
    st.subheader("剩餘航次油量預測與加油建議")
    daily = st.session_state.daily_log
    sched = st.session_state.schedule
    if daily is None:
        st.info("請先匯入每日航務記錄。")
    elif sched is None or sched.dropna(subset=["start_date"]).empty:
        st.info("請先於「資料匯入」頁匯入或編輯船期表（未來期間）。")
    else:
        st.markdown("#### 預測參數（KL/天）")
        auto_rates = forecast.historical_rates(daily)
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1.4])
        with c1:
            r_sail = st.number_input("出航", value=float(st.session_state.rates["出航"]), step=0.1)
        with c2:
            r_port = st.number_input("靠港", value=float(st.session_state.rates["靠港"]), step=0.1)
        with c3:
            r_dock = st.number_input("進塢", value=float(st.session_state.rates["進塢"]), step=0.1)
        with c4:
            st.caption(
                f"歷史平均：出航 {auto_rates['出航']:.2f}／靠港 {auto_rates['靠港']:.2f}"
                f"／進塢 {auto_rates['進塢']:.2f}"
            )
            if st.button("採用歷史平均油耗"):
                st.session_state.rates = auto_rates
                st.rerun()
        st.session_state.rates = {"出航": r_sail, "靠港": r_port, "進塢": r_dock}

        rob_series = rob.compute_rob_series(daily)
        if rob_series.empty:
            st.warning("每日記錄為空，無法推算 ROB。")
            st.stop()
        start_rob = float(rob_series.iloc[-1]["rob_calc"])
        last_date = rob_series.iloc[-1]["date"]
        st.caption(f"預測起點：{pd.to_datetime(last_date):%Y-%m-%d} 推算 ROB {start_rob:.1f} KL")

        future = forecast.expand_schedule(sched)
        future = future[future["date"] > pd.to_datetime(last_date)]
        if future.empty:
            st.warning("船期表中沒有晚於最後記錄日期的未來期間。")
        else:
            result = forecast.forecast_rob(start_rob, future, st.session_state.rates)

            for alert in result.risk_alerts:
                st.error(alert)
            if result.refuel_plan:
                st.markdown("#### ⛽ 加油建議")
                plan = pd.DataFrame(result.refuel_plan)
                plan["date"] = pd.to_datetime(plan["date"]).dt.strftime("%Y-%m-%d")
                st.dataframe(
                    plan.rename(columns={
                        "date": "建議加油日", "rob_before": "加油前ROB(KL)",
                        "refuel_amount": "建議加油量(KL)", "rob_after": "加油後ROB(KL)",
                        "reason": "理由",
                    }),
                    use_container_width=True,
                )
            elif not result.risk_alerts:
                st.success("預測期間 ROB 均高於警戒線，暫無加油需求。")

            hist = rob_series[["date", "rob_calc"]]
            fig = go.Figure()
            fig.add_scatter(x=hist["date"], y=hist["rob_calc"], name="實際推算 ROB",
                            mode="lines", line_color="#0b3d62")
            fig.add_scatter(x=result.daily["date"], y=result.daily["rob_forecast"],
                            name="預測 ROB", mode="lines+markers",
                            line=dict(color="#ff7f0e", dash="dash"))
            for item in result.refuel_plan:
                fig.add_vline(x=pd.to_datetime(item["date"]), line_color="green", line_dash="dot")
            fig.add_hline(y=rob.WARNING_LEVEL_KL, line_dash="dash", line_color="red",
                          annotation_text="警戒線 150 KL")
            fig.update_layout(title="ROB 實際與預測（綠虛線＝建議加油日）",
                              yaxis_title="KL", height=420, legend_orientation="h")
            st.plotly_chart(fig, use_container_width=True)

            showf = result.daily.copy()
            showf["date"] = pd.to_datetime(showf["date"]).dt.strftime("%Y-%m-%d")
            showf = showf.rename(columns={
                "date": "日期", "status": "狀態", "refuel_allowed": "可加油",
                "voyage_no": "航次編號", "predicted_fuel": "預測油耗(KL)",
                "refuel_amount": "建議加油量(KL)", "rob_forecast": "預測ROB(KL)",
                "below_warning": "低於警戒線",
            })
            st.dataframe(showf, use_container_width=True, height=360)
            st.download_button(
                "下載預測報告 (Excel)",
                sample_data.to_excel_bytes(showf, "油量預測"),
                file_name="TORI_油量預測與加油建議.xlsx",
            )
