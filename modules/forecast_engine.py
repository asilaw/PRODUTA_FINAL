"""
Forecast engine — reads Ubay's Prophet output CSVs if available.
Contract: run_forecast() returns DataFrame with columns [sku, date, forecast, ...]
"""
import pandas as pd
from pathlib import Path
import streamlit as st

FORECAST_DIR = Path("data/forecast")

def _find_forecast_csv():
    """Locate Ubay's output CSV regardless of exact filename."""
    if not FORECAST_DIR.exists(): return None
    for name in ["prophet_forecast_output.csv", "forecast_output.csv",
                 "forecast.csv", "demand_forecast.csv"]:
        p = FORECAST_DIR / name
        if p.exists(): return p
    return None

@st.cache_data(ttl=3600)
def load_ubay_outputs():
    """Load all of Ubay's pre-computed CSV outputs."""
    fdir = FORECAST_DIR
    results = {}
    mappings = {
        "forecast":  ["prophet_forecast_output.csv","forecast_output.csv","forecast.csv"],
        "sku_stats": ["sku_classification.csv","sku_stats.csv"],
        "backtest":  ["backtest_results.csv","backtest.csv"],
        "actuals":   ["actuals.csv"],
    }
    for key, names in mappings.items():
        for name in names:
            p = fdir / name
            if p.exists():
                parse_dates = ["date"] if key == "forecast" else (["ds"] if key == "actuals" else [])
                try:
                    results[key] = pd.read_csv(p, parse_dates=parse_dates if parse_dates else None)
                    break
                except: pass
    return results

def run_forecast(raw_df: pd.DataFrame, horizon_months: int = 12, method: str = "Auto") -> pd.DataFrame:
    """
    Jalankan forecasting. Ubay perlu mengisi bagian Prophet/Croston di sini.
    Sementara ini, coba baca hasil pre-computed dari data/forecast/
    """
    outputs = load_ubay_outputs()
    if "forecast" in outputs and not outputs["forecast"].empty:
        return outputs["forecast"]
    raise NotImplementedError(
        "Forecast CSV belum ada di data/forecast/. "
        "Upload prophet_forecast_output.csv dari hasil notebook Ubay."
    )
