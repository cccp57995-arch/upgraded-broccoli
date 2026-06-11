# TORI 勵進研究船燃油消耗管理系統

R/V Legend Fuel Consumption Management System — 用於讀取勵進研究船的 Excel
航務數據，提供燃油消耗管理、每日油耗報告、航次油耗統計、ROB 推算、
加油建議與剩餘航次油量預測。

## 2026 加油計畫產生器（CLI）

依航次任務類型與歷史實績計算油耗（取代固定 4.5–4.7 KL/day 估算值），
一鍵輸出 5 頁加油計畫 Excel：

```bash
python build_plan.py \
    --history data/TORI_FuelConsumption_Summary.xlsx \
    --voyages data/TORI_2026_voyages.csv \
    --out output/TORI_2026_加油計畫.xlsx
```

輸出工作表：

| 頁 | 內容 |
|---|---|
| 用油分析摘要 | 判定規則、歷史全體統計、各任務類型油耗率（日均/P25/P50/P75）與建議採用值 |
| 月份統計 | 歷史實際月份用油（出航/靠港/進塢分色） |
| 每日明細 | 歷史逐日油耗（含加油量欄，加油日黃底） |
| 2026加油預估 | 各航次依類型套用油耗率、加油時機與加油量、ROB 警示 |
| 2026逐日ROB | 預估 ROB、實際 ROB（有資料才填）、日耗油誤差（實際−預估） |

核心邏輯：

- **任務類型油耗率**：由 2026 航次表的委託單位分類（國科會／內政部＋國海院
  水深測量／震測／試航／中研院／地礦中心／中華電信）。類型出航日樣本
  ≥ 10 天採類型中位數，不足則退回全體出航日中位數並於摘要頁標註依據。
- **加油時機自動推導**：航次備註含「出塢加油」→ 塢修結束次日；含「加燃油」
  → 該航次返港次日；補滿至 465 KL（已發生加油採實際加油量）。
- **加油判定**（SMF 原始格式）：前後兩日 ROB 差值 > 10 KL 即視為加油。
- **ROB 參數**：油艙上限 465 KL、警戒線 150 KL，低於警戒線自動產生警示。

歷史檔支援 `TORI_FuelConsumption_Summary` 整理格式，或以 `--smf` 讀取
SMF-07-05 原始 Daily Log（固定欄位：col 22-24 時數、col 26 距離、
col 33-37 油耗、col 42 ROB）。

## 互動介面（Streamlit）

```bash
pip install -r requirements.txt
streamlit run app.py
```

開啟後可直接點「載入示範資料」體驗完整流程，或上傳實際 Excel 檔案。

## 資料來源

| 來源 | 內容 | 格式 |
|---|---|---|
| SMF-07-05 TORI Daily log Abstract | 每日航務記錄：推進/作業/靠港時數與油耗、總油耗、加油量、ROB、航行距離 | Excel |
| 航次總表 | 航次編號、委託單位、起迄日期 | Excel |
| 船期表 | 未來航次、靠港期間、進塢期間與可加油時機 | Excel 或圖片（圖片以內建編輯表手動輸入） |

## 功能

### 一、Excel 匯入與欄位對應
- 上傳三種資料來源後，系統自動猜測欄位對應，並提供欄位對應介面
  讓使用者將原始欄位轉換為標準欄位。
- 每日記錄標準欄位：`date, voyage_no, client, propulsion_hours,
  operation_hours, in_port_hours, propulsion_fuel, operation_fuel,
  in_port_fuel, total_fuel_consumed, refuel, rob, distance, remark`。

### 二、航次日分類（順序固定）
1. `total_fuel_consumed == 0` → **進塢**（優先於其他規則）
2. 否則 `propulsion_hours > 0` 或 `operation_hours > 0` 或 `distance ≠ 0`
   或 `propulsion_fuel > 0` 或 `operation_fuel > 0` 或 `in_port_fuel == 0`
   → **出航**
3. 其餘 → **靠港**

欄位相互矛盾時仍依上述規則分類，但標示「資料異常」並列出原因
（如分項油耗加總與總油耗不符、進塢日卻有推進時數等）。

### 三、ROB 推算
- 油艙容量 465 KL、警戒線 150 KL、加油策略補滿至 465 KL。
- 當日推算 ROB = 前一日 ROB + 當日加油量 − 當日總油耗。
- 加油量 = 465 − 加油前 ROB；加油後 ROB 不得超過 465 KL。
- 推算值與記錄 ROB 比對，差異超過容差即標示。

### 四、加油替代邏輯
- 在每個可加油日，模擬到下一個可加油日之間的最低預測 ROB；
  若會低於 150 KL，則建議在該（最近）可加油日加油補滿。
- 若無法在低於警戒線前安排加油，顯示風險提醒。

### 五、預測油耗
- 已發生日期使用實際油耗；未來日期依船期狀態採平均油耗預測。
- 預設值：出航 4.7 KL/天、靠港 1.6 KL/天、進塢 0 KL/天。
- 參數可手動調整，亦可一鍵採用由歷史數據自動計算的平均油耗。

## 專案結構

```
build_plan.py           2026 加油計畫產生器（CLI，輸出 5 頁 Excel）
app.py                  Streamlit 主程式（匯入、報告、統計、ROB、預測五個頁籤）
data/                   輸入資料（歷史每日油耗 Excel、2026 航次總表 CSV）
tori_fuel/
  history.py            歷史每日資料載入（SMF-07-05 原始格式／整理格式）、
                        分類與 ROB 差值加油判定
  voyage_types.py       航次任務類型分類（委託單位＋震測關鍵字）
  typestats.py          各類型油耗統計（日均/P25/P50/P75）與建議油耗率
  plan2026.py           2026 航次展開、ROB 推算與加油排程
  report.py             5 頁加油計畫 Excel 報表
  schema.py             標準欄位定義、欄位自動猜測與對應
  classifier.py         航次日分類與資料異常檢查
  rob.py                ROB 推算（465 KL / 150 KL 參數）
  forecast.py           船期展開、油耗預測、加油建議與風險提醒
  stats.py              航次油耗統計
  sample_data.py        示範資料產生器
tests/                  pytest 單元測試
```

## 測試

```bash
python -m pytest tests/ -v
```
