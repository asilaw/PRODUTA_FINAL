# PRODUTA DSS — Integrated
**PT FBMI (Lactalis Group) · TIN IPB 2026**

## Tim
| PIC | Kontribusi | View |
|-----|-----------|------|
| Ubay | Demand Forecasting (Prophet) | Demand Overview → tab Forecast |
| Asil | Capacity Simulation (DES) | Capacity Simulation (sudah jalan) |
| Gibran | DSS + FIS + Financial | Capacity Planning, Production Allocation, Investment Catalog |

## Jalankan
```bash
pip install -r requirements.txt
streamlit run app.py
```
Login: `admin` / `fbmi2026`

## Integrasi Ubay (Forecasting)
Letakkan file di `data/forecast/`:
```
data/forecast/prophet_forecast_output.csv   ← WAJIB
data/forecast/sku_classification.csv         ← WAJIB
data/forecast/backtest_results.csv           ← WAJIB
data/forecast/actuals.csv                    ← opsional
```
Format kolom forecast: `sku`, `date`, `forecast` (bisa ditambah `forecast_lower`, `forecast_upper`, dll)

## Alur Data
```
Ubay CSV → Demand Overview (tab Forecast)
         → Generate ForecastInput DES
         → Capacity Simulation (DES Engine — Asil)
         → Capacity Planning (FIS scoring — Gibran)
         → Production Allocation (Gibran)
```
