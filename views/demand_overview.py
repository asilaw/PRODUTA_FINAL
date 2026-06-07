"""
ANALISIS DEMAND & FORECASTING
==========================================================================
Konteks pengerjaan Ubay (Model Peramalan Permintaan):
  · 60 SKU lokal internal diklasifikasikan dengan metode Croston 2001
    berdasarkan p (inter-demand interval) dan CV² (variasi permintaan):
      SMOOTH       p < 1.32 & CV² < 0.49 → Prophet
      ERRATIC      p < 1.32 & CV² ≥ 0.49 → Prophet
      INTERMITTENT p ≥ 1.32 & CV² < 0.49 → CrostonSBA
      LUMPY        p ≥ 1.32 & CV² ≥ 0.49 → CrostonSBA
  · Prophet: Bayesian Optimization, feature engineering (event, lag, rolling,
    holiday window ±31 hari Lebaran), train Aug'23–Oct'25 test Nov'25–Jan'26
  · CrostonSBA: Croston + weighted ensemble, wmape sebagai metrik utama
  · Output utama: unified_forecast_output.csv (12 kolom termasuk demand_pattern,
    model_used, wmape_backtest, bias_pct, holiday_adjusted)

Alur Tab 1 — FORECASTING:
  1. Upload data historis (format FBMI Volume_F24-F26 atau long format)
  2. Sistem parse & tampilkan ringkasan + klasifikasi pola
  3. Jalankan forecast (pipeline Ubay — NotImplementedError = stub)
  4. Tampilkan hasil: tabel + metrik akurasi per SKU
  5. Export CSV → untuk tab VISUALISASI DEMAND
  6. Visualisasi langsung

Tab 2 — INPUT SIMULASI DES (Asil)
Tab 3 — VISUALISASI DEMAND (Gibran)
==========================================================================
"""

import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

from modules.session import get_state, set_state
from modules.io_utils import read_table
from modules.raw_volume_parser import parse_raw_volume

# ─── Palet & Konstanta ──────────────────────────────────────────────────────
PKG_COLORS = {"SSS": "#37B7C3", "BIB": "#071952", "STICKPACK": "#088395"}
SEG_COLORS = {
    "SMOOTH": "#088395", "ERRATIC": "#37B7C3",
    "INTERMITTENT": "#e6a817", "LUMPY": "#c0392b",
}
MODEL_COLORS = {"Prophet": "#088395", "CrostonSBA": "#071952", "Croston": "#37B7C3"}
CHART_BG = "#FFFFFF"
FONT_COLOR = "#071952"

MASTER_SKU_PATH  = Path("data/masters/master_sku.csv")
MASTER_DATA_PATH = Path("data/masters/master_data.xlsx")

# Kolom rename untuk tabel yang user-friendly
FORECAST_COL_LABELS = {
    "date": "Tanggal",
    "sku": "Kode SKU",
    "description": "Deskripsi Produk",
    "forecast": "Forecast (ton)",
    "forecast_lower": "Batas Bawah (ton)",
    "forecast_upper": "Batas Atas (ton)",
    "mape_backtest": "MAPE (%)",
    "wmape_backtest": "WMAPE (%)",
    "bias_pct": "Bias (%)",
    "demand_pattern": "Pola Permintaan",
    "model_used": "Model Digunakan",
    "holiday_adjusted": "Koreksi Lebaran",
    "_pkg": "Jenis Kemasan",
    "ds": "Tanggal",
    "y": "Volume (ton)",
    "p": "Interval Rata-rata (p)",
    "CV Squared": "CV² (Variasi)",
    "model": "Model",
    "segment": "Pola Permintaan",
    "category": "Kategori Brand",
}


def _col_label(col: str) -> str:
    return FORECAST_COL_LABELS.get(col, col.replace("_", " ").title())


def _rename_cols(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={c: _col_label(c) for c in df.columns})


# ─── Master loaders ──────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _load_pkg_map() -> dict:
    if not MASTER_SKU_PATH.exists():
        return {}
    try:
        df = pd.read_csv(MASTER_SKU_PATH, encoding="latin-1", on_bad_lines="skip")
        df.columns = [c.strip() for c in df.columns]
        df = df.rename(columns={df.columns[0]: "sku"})
        df["sku"] = df["sku"].astype(str).str.strip()
        result = {}
        for _, row in df.iterrows():
            pt = str(row.get("PORT TYPE", "")).strip().upper()
            if "STICK" in pt:   result[row["sku"]] = "STICKPACK"
            elif "SSS" in pt:   result[row["sku"]] = "SSS"
            else:               result[row["sku"]] = "BIB"
        return result
    except Exception:
        return {}


@st.cache_data(show_spinner=False)
def _load_master_data_db() -> pd.DataFrame | None:
    if not MASTER_DATA_PATH.exists():
        return None
    try:
        return pd.read_excel(MASTER_DATA_PATH)
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def _load_sku_classification() -> pd.DataFrame | None:
    p = Path("data/forecast/sku_classification.csv")
    if not p.exists():
        return None
    try:
        return pd.read_csv(p)
    except Exception:
        return None


def _load_best_forecast_file() -> pd.DataFrame | None:
    """
    Load output forecast terbaik yang tersedia dari database Ubay.
    Prioritas: unified_forecast_output (lebih lengkap) > prophet_forecast_output.
    """
    for fname in ["unified_forecast_output.csv", "prophet_forecast_output.csv"]:
        p = Path(f"data/forecast/{fname}")
        if p.exists():
            try:
                df = pd.read_csv(p)
                if not df.empty:
                    return df
            except Exception:
                pass
    return None


# ─── Utility ─────────────────────────────────────────────────────────────────
def _clean_forecast(df: pd.DataFrame) -> pd.DataFrame:
    col_map = {}
    for c in df.columns:
        cl = c.strip().lower()
        if cl == "date":                         col_map[c] = "date"
        elif cl in ("ds",):                      col_map[c] = "date"
        elif cl == "forecast":                   col_map[c] = "forecast"
        elif cl == "forecast_lower":             col_map[c] = "forecast_lower"
        elif cl == "forecast_upper":             col_map[c] = "forecast_upper"
        elif cl in ("sku", "skuid"):             col_map[c] = "sku"
        elif cl in ("description","descriptionforecast",
                    "item_name","itemname"):     col_map[c] = "description"
        elif cl == "mape_backtest":              col_map[c] = "mape_backtest"
        elif cl == "wmape_backtest":             col_map[c] = "wmape_backtest"
        elif cl == "bias_pct":                   col_map[c] = "bias_pct"
        elif cl == "demand_pattern":             col_map[c] = "demand_pattern"
        elif cl == "model_used":                 col_map[c] = "model_used"
        elif cl == "holiday_adjusted":           col_map[c] = "holiday_adjusted"
        elif cl == "model":                      col_map[c] = "model"
    df = df.rename(columns=col_map)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "forecast" in df.columns:
        df["forecast"] = pd.to_numeric(df["forecast"], errors="coerce").fillna(0).clip(lower=0)
    return df


def _filter_active(df: pd.DataFrame) -> pd.DataFrame:
    if "sku" in df.columns and "forecast" in df.columns:
        tot = df.groupby("sku")["forecast"].sum()
        df  = df[df["sku"].isin(tot[tot > 0].index)].copy()
    return df


def _add_pkg(df: pd.DataFrame, pkg_map: dict) -> pd.DataFrame:
    df = df.copy()
    if "sku" in df.columns:
        df["_pkg"] = df["sku"].apply(lambda x: pkg_map.get(str(x).strip(), "BIB"))
    else:
        df["_pkg"] = "BIB"
    return df


def _chart_kw(**kw) -> dict:
    base = dict(
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=FONT_COLOR,
        margin=dict(l=10, r=10, t=36, b=10),
        legend=dict(orientation="h", y=-0.24, font=dict(size=11)),
        font=dict(family="Inter, sans-serif"),
    )
    base.update(kw)
    return base


def _kpi(col, label, val):
    col.markdown(
        f'<div class="kpi-box"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{val}</div></div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ══════════════════════════════════════════════════════════════════════════════
def render():
    st.markdown(
        '<div class="page-title">ANALISIS DEMAND & FORECASTING</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="color:#088395;font-size:.88rem;margin:-12px 0 18px 0;">'
        "Forecasting permintaan, konversi ke input simulasi DES, dan visualisasi kapasitas.</p>",
        unsafe_allow_html=True,
    )
    tab1, tab2, tab3 = st.tabs(["FORECASTING", "INPUT SIMULASI DES", "VISUALISASI DEMAND"])
    with tab1: _tab_forecasting()
    with tab2: _tab_des_input()
    with tab3: _tab_visualisasi()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — FORECASTING
# ══════════════════════════════════════════════════════════════════════════════
def _tab_forecasting():
    pkg_map = _load_pkg_map()
    sc_df   = _load_sku_classification()  # klasifikasi pola 60 SKU Ubay

    # ── A: Upload Data Historis ──────────────────────────────────────────
    st.markdown("<div class='section-title'>DATA HISTORIS</div>", unsafe_allow_html=True)
    st.caption("Upload data historis volume permintaan bulanan.")

    raw_file = st.file_uploader(
        "Upload Data Historis", type=["csv","xlsx","xls","tsv"],
        key="raw_hist_upload", label_visibility="collapsed",
    )
    if raw_file:
        try:
            # Coba format FBMI raw volume
            try:
                raw_df = parse_raw_volume(raw_file)
            except Exception:
                raw_df = read_table(raw_file)

            set_state("forecast_raw", raw_df)

            # Tampilkan ringkasan
            cols = raw_df.columns.tolist()
            has_ds  = "ds" in cols or "date" in cols
            has_sku = "sku" in cols
            has_y   = "y" in cols or "volume" in cols or "forecast" in cols

            if has_ds and has_sku and has_y:
                ds_col = "ds" if "ds" in cols else "date"
                y_col  = "y"  if "y" in cols else ("volume" if "volume" in cols else "forecast")
                raw_df[ds_col] = pd.to_datetime(raw_df[ds_col], errors="coerce")
                n_sku   = raw_df["sku"].nunique()
                n_month = raw_df[ds_col].dropna().nunique()
                tot_vol = raw_df[y_col].sum()
                d_min   = raw_df[ds_col].min().strftime("%b %Y")
                d_max   = raw_df[ds_col].max().strftime("%b %Y")
                st.success(
                    f"Data historis dimuat: **{n_sku} SKU**, **{n_month} periode** "
                    f"({d_min} – {d_max}), total volume: **{tot_vol:,.0f} ton**."
                )

                # Preview tabel dengan nama kolom user-friendly
                prev = raw_df.head(60).copy()
                prev[ds_col] = prev[ds_col].dt.strftime("%Y-%m")
                with st.expander("Preview Data Historis"):
                    st.dataframe(
                        _rename_cols(prev), use_container_width=True, hide_index=True
                    )

                # Klasifikasi pola dari sku_classification jika ada
                if sc_df is not None and has_sku:
                    _show_sku_classification(sc_df, raw_df["sku"].unique())
            else:
                st.success(f"Data dimuat: {len(raw_df):,} baris.")
                with st.expander("Preview"):
                    st.dataframe(
                        _rename_cols(raw_df.head(40)), use_container_width=True, hide_index=True
                    )

        except Exception as e:
            st.error(f"Gagal membaca file: {e}")

    raw_df  = get_state("forecast_raw")
    has_raw = isinstance(raw_df, pd.DataFrame) and not raw_df.empty

    if not has_raw:
        st.markdown(
            '<div class="note-box">Upload data historis untuk mengaktifkan pipeline forecast.</div>',
            unsafe_allow_html=True,
        )

    # ── B: Parameter & Run ───────────────────────────────────────────────
    st.markdown("<div class='section-title'>PARAMETER FORECAST</div>", unsafe_allow_html=True)
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        method  = st.selectbox("Metode", ["Auto (Prophet + CrostonSBA)","Prophet","CrostonSBA","Ensemble"], key="fc_method")
    with fc2:
        horizon = st.number_input("Horizon (bulan)", 3, 36, 12, 1, key="fc_horizon")
    with fc3:
        optimize = st.checkbox("Bayesian Optimization", value=True, key="fc_optimize",
                               help="Optimasi parameter model secara otomatis (lebih lambat, lebih akurat).")

    if st.button("Jalankan Forecast", type="primary", disabled=not has_raw, key="btn_run_fc"):
        try:
            from modules.forecast_engine import run_forecast
            with st.spinner("Memproses pipeline forecast..."):
                fc_result = run_forecast(raw_df, horizon_months=horizon, method=method)
            fc_result = _clean_forecast(fc_result)
            set_state("forecast_output", fc_result)
            st.success(f"Forecast selesai: {len(fc_result):,} baris.")
        except NotImplementedError:
            # Pipeline Ubay belum terintegrasi → load existing output sebagai simulasi
            existing = _load_best_forecast_file()
            if existing is not None:
                existing = _clean_forecast(existing)
                set_state("forecast_output", existing)
                st.info(
                    f"Pipeline sedang dalam pengembangan. "
                    f"Menampilkan output forecast yang tersedia "
                    f"({existing['sku'].nunique() if 'sku' in existing.columns else '?'} SKU)."
                )
            else:
                st.info("Pipeline forecast sedang dalam pengembangan.")
        except Exception as e:
            st.error(f"Error: {e}")

    # ── C: Cek apakah ada forecast ───────────────────────────────────────
    fc_df  = get_state("forecast_output")
    has_fc = isinstance(fc_df, pd.DataFrame) and not fc_df.empty

    # Auto-load existing forecast jika belum ada di session (tapi jangan tampilkan chart-nya)
    if not has_fc:
        st.markdown(
            '<div class="note-box">Jalankan forecast atau upload data historis terlebih dahulu.</div>',
            unsafe_allow_html=True,
        )
        return

    fc_df = _clean_forecast(fc_df)
    fc_df = _filter_active(fc_df)

    # ── D: Ringkasan Hasil Forecast ──────────────────────────────────────
    st.markdown("<div class='section-title'>HASIL FORECAST</div>", unsafe_allow_html=True)

    n_sku = fc_df["sku"].nunique() if "sku" in fc_df.columns else "-"
    n_mon = fc_df["date"].dropna().nunique() if "date" in fc_df.columns else "-"

    # Metrik akurasi
    has_mape  = "mape_backtest"  in fc_df.columns
    has_wmape = "wmape_backtest" in fc_df.columns
    has_model = "model_used"     in fc_df.columns
    has_patt  = "demand_pattern" in fc_df.columns

    # Avg akurasi per SKU (bukan per baris)
    avg_mape, avg_wmape = None, None
    if has_sku and "sku" in fc_df.columns:
        if has_mape:
            avg_mape  = fc_df.groupby("sku")["mape_backtest"].first().dropna().mean()
        if has_wmape:
            avg_wmape = fc_df.groupby("sku")["wmape_backtest"].first().dropna().mean()

    # KPI row
    km1, km2, km3, km4 = st.columns(4)
    _kpi(km1, "SKU AKTIF",      str(n_sku))
    _kpi(km2, "HORIZON",        f"{n_mon} bulan")
    _kpi(km3, "MAPE RATA-RATA", f"{avg_mape:.1f}%" if avg_mape is not None else
         (f"{avg_wmape:.1f}%" if avg_wmape is not None else "N/A"))
    if has_model:
        n_prophet = (fc_df.drop_duplicates("sku")["model_used"] == "Prophet").sum() if has_sku else "?"
        n_croston = (fc_df.drop_duplicates("sku")["model_used"] != "Prophet").sum() if has_sku else "?"
        _kpi(km4, "MODEL", f"Prophet: {n_prophet} | Croston: {n_croston}")
    else:
        _kpi(km4, "MODEL", "Prophet + CrostonSBA")

    # Warning akurasi
    if avg_mape and avg_mape > 30:
        st.markdown(
            '<div class="warn-box">Rata-rata MAPE tinggi — beberapa SKU perlu diverifikasi manual.</div>',
            unsafe_allow_html=True,
        )

    # ── E: Ringkasan Pola Permintaan (dari sku_classification) ───────────
    if sc_df is not None:
        _show_sku_classification_summary(sc_df)

    # ── F: Tabel Forecast ────────────────────────────────────────────────
    st.markdown("<div class='section-title'>TABEL FORECAST PER SKU</div>", unsafe_allow_html=True)

    # Filter SKU
    if "sku" in fc_df.columns:
        all_skus = sorted(fc_df["sku"].dropna().unique().tolist())
        sel_skus = st.multiselect(
            "Filter Kode SKU", all_skus, default=all_skus[:5], key="fc_tbl_filter"
        )
        tbl = fc_df[fc_df["sku"].isin(sel_skus)].copy() if sel_skus else fc_df.copy()
    else:
        tbl = fc_df.copy()

    # Format kolom untuk tampilan
    if "date" in tbl.columns:
        tbl["date"] = tbl["date"].dt.strftime("%Y-%m-%d")
    for col in ["forecast","forecast_lower","forecast_upper","mape_backtest","wmape_backtest","bias_pct"]:
        if col in tbl.columns:
            tbl[col] = pd.to_numeric(tbl[col], errors="coerce").round(4)

    # Drop kolom internal
    drop_cols = [c for c in ["_pkg"] if c in tbl.columns]
    tbl = tbl.drop(columns=drop_cols, errors="ignore")

    st.dataframe(_rename_cols(tbl), use_container_width=True, hide_index=True)

    # ── G: Akurasi per SKU (card accordion) ─────────────────────────────
    if (has_mape or has_wmape) and "sku" in fc_df.columns:
        with st.expander("Akurasi Model per SKU"):
            acc_df = fc_df.drop_duplicates("sku")[
                ["sku"] +
                (["description"] if "description" in fc_df.columns else []) +
                (["demand_pattern"] if has_patt else []) +
                (["model_used"] if has_model else []) +
                (["mape_backtest"] if has_mape else []) +
                (["wmape_backtest"] if has_wmape else []) +
                (["bias_pct"] if "bias_pct" in fc_df.columns else [])
            ].sort_values(
                "wmape_backtest" if has_wmape else "mape_backtest",
                na_position="last"
            )
            for col in ["mape_backtest","wmape_backtest","bias_pct"]:
                if col in acc_df.columns:
                    acc_df[col] = acc_df[col].round(2)
            st.dataframe(_rename_cols(acc_df), use_container_width=True, hide_index=True)

    # ── H: Export CSV ────────────────────────────────────────────────────
    st.markdown("<div class='section-title'>EXPORT FORECAST</div>", unsafe_allow_html=True)
    st.caption("Download file ini dan upload di tab VISUALISASI DEMAND untuk melihat chart kapasitas.")
    exp = fc_df.copy()
    if "date" in exp.columns:
        exp["date"] = exp["date"].dt.strftime("%Y-%m-%d")
    drop_exp = [c for c in ["_pkg"] if c in exp.columns]
    exp = exp.drop(columns=drop_exp, errors="ignore")
    st.download_button(
        "Unduh Forecast CSV",
        data=exp.to_csv(index=False).encode(),
        file_name="forecast_output.csv",
        mime="text/csv",
        key="dl_fc_csv",
    )

    # ── I: Visualisasi langsung ──────────────────────────────────────────
    st.markdown("<div class='section-title'>VISUALISASI DEMAND</div>", unsafe_allow_html=True)
    viz = _add_pkg(fc_df, pkg_map)
    _render_charts(viz, ctx="t1", sc_df=sc_df)


# ─── Helper: tampilkan klasifikasi pola setelah upload historis ──────────────
def _show_sku_classification(sc_df: pd.DataFrame, raw_skus):
    """Tampilkan ringkasan pola permintaan untuk SKU yang ada di data historis."""
    # Match SKU dari raw data ke klasifikasi
    matched = sc_df[sc_df["sku"].isin(raw_skus)] if "sku" in sc_df.columns else sc_df
    if matched.empty:
        return

    st.markdown("<div class='section-title'>KLASIFIKASI POLA PERMINTAAN</div>", unsafe_allow_html=True)
    st.caption(
        "Klasifikasi berdasarkan interval rata-rata permintaan (p) dan koefisien variasi kuadrat (CV²) "
        "menggunakan metode Croston 2001."
    )

    seg_counts = matched["segment"].value_counts() if "segment" in matched.columns else pd.Series()
    col_order = ["SMOOTH","ERRATIC","INTERMITTENT","LUMPY"]
    cols = st.columns(4)
    for i, seg in enumerate(col_order):
        n = seg_counts.get(seg, 0)
        model = "Prophet" if seg in ["SMOOTH","ERRATIC"] else "CrostonSBA"
        cols[i].markdown(
            f'<div class="kpi-box" style="border-left:4px solid {SEG_COLORS.get(seg,"#088395")};">'
            f'<div class="kpi-label">{seg}</div>'
            f'<div class="kpi-value">{n}</div>'
            f'<div style="font-size:.7rem;color:#088395;margin-top:4px;">→ {model}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _show_sku_classification_summary(sc_df: pd.DataFrame):
    """Tampilkan ringkasan klasifikasi di bagian hasil forecast."""
    if sc_df is None or sc_df.empty:
        return
    seg_counts = sc_df["segment"].value_counts() if "segment" in sc_df.columns else pd.Series()
    if seg_counts.empty:
        return

    with st.expander("Distribusi Pola Permintaan (60 SKU Klasifikasi)", expanded=False):
        col_order = ["SMOOTH","ERRATIC","INTERMITTENT","LUMPY"]
        c1, c2, c3, c4 = st.columns(4)
        for col_obj, seg in zip([c1,c2,c3,c4], col_order):
            n = seg_counts.get(seg, 0)
            model = "Prophet" if seg in ["SMOOTH","ERRATIC"] else "CrostonSBA"
            col_obj.markdown(
                f'<div class="kpi-box" style="border-left:4px solid {SEG_COLORS.get(seg,"#088395")};">'
                f'<div class="kpi-label">{seg}</div>'
                f'<div class="kpi-value">{n} SKU</div>'
                f'<div style="font-size:.7rem;color:#088395;margin-top:4px;">→ {model}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        # Scatter plot p vs CV²
        if all(c in sc_df.columns for c in ["p","CV Squared","segment","sku"]):
            fig = px.scatter(
                sc_df, x="p", y="CV Squared", color="segment",
                color_discrete_map=SEG_COLORS, hover_data=["sku"],
                height=300,
                labels={"p": "p (interval rata-rata permintaan)",
                        "CV Squared": "CV² (variasi permintaan)", "segment": "Pola"},
            )
            fig.add_hline(y=0.49, line_dash="dash", line_color="gray", opacity=0.6)
            fig.add_vline(x=1.32, line_dash="dash", line_color="gray", opacity=0.6)
            fig.update_layout(**_chart_kw(showlegend=True))
            st.plotly_chart(fig, use_container_width=True, key="scatter_seg")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — INPUT SIMULASI DES
# ══════════════════════════════════════════════════════════════════════════════
def _tab_des_input():
    # ── Sumber Forecast ──────────────────────────────────────────────────
    st.markdown("<div class='section-title'>OUTPUT FORECAST</div>", unsafe_allow_html=True)

    fc_df  = get_state("forecast_output")
    has_fc = isinstance(fc_df, pd.DataFrame) and not fc_df.empty

    if has_fc:
        fc_df = _clean_forecast(_filter_active(fc_df))
        n_sku = fc_df["sku"].nunique() if "sku" in fc_df.columns else "?"
        st.success(f"Forecast tersedia dari tab FORECASTING — {n_sku} SKU aktif.")
    else:
        st.caption("Belum ada data forecast. Upload di sini:")
        fc_up = st.file_uploader(
            "Upload File Forecast", type=["csv","xlsx"], key="fc_des_bridge",
            label_visibility="collapsed",
        )
        if fc_up:
            try:
                df_tmp = _clean_forecast(_filter_active(read_table(fc_up)))
                set_state("forecast_output", df_tmp)
                fc_df = df_tmp; has_fc = True
                st.success(f"Forecast dimuat: {len(df_tmp):,} baris.")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal membaca: {e}")

    if not has_fc:
        return

    # ── Master Data Asil ─────────────────────────────────────────────────
    st.markdown("<div class='section-title'>MASTER DATA SKU</div>", unsafe_allow_html=True)

    ma_session = get_state("master_data_asil")
    if isinstance(ma_session, pd.DataFrame) and not ma_session.empty:
        master_asil = ma_session; src = "upload sebelumnya"
    else:
        master_asil = _load_master_data_db(); src = "database"
        if master_asil is not None:
            set_state("master_data_asil", master_asil)

    if master_asil is not None:
        st.markdown(
            f'<div class="note-box">Master Data aktif: <b>{len(master_asil)}</b> SKU ({src}).</div>',
            unsafe_allow_html=True,
        )
        with st.expander("Ganti Master Data atau muat ulang dari database", expanded=False):
            opt = st.radio("Sumber", ["Database","Upload Manual"], horizontal=True, key="des_master_opt")
            if opt == "Upload Manual":
                ma_file = st.file_uploader(
                    "Upload Master Data", type=["xlsx","xls","csv"],
                    key="master_asil_upload", label_visibility="collapsed",
                )
                if ma_file:
                    try:
                        ma_new = read_table(ma_file)
                        set_state("master_data_asil", ma_new)
                        master_asil = ma_new
                        _load_master_data_db.clear()
                        st.success(f"Master Data diperbarui: {len(ma_new)} SKU.")
                    except Exception as e:
                        st.error(f"Gagal: {e}")
            else:
                if st.button("Muat ulang dari database", key="des_reload"):
                    _load_master_data_db.clear()
                    db_ma = _load_master_data_db()
                    if db_ma is not None:
                        set_state("master_data_asil", db_ma)
                        master_asil = db_ma
                        st.success("Dimuat dari database.")

            # Preview kolom penting saja
            show_cols = [c for c in ["SkuId","ItemName","port_type","Speed","SpeedD"] if c in master_asil.columns]
            if show_cols:
                st.dataframe(
                    _rename_cols(master_asil[show_cols].head(12)),
                    use_container_width=True, hide_index=True,
                )
    else:
        st.warning("Master Data tidak tersedia. Upload di bawah.")
        ma_file = st.file_uploader(
            "Upload Master Data", type=["xlsx","xls","csv"],
            key="master_asil_upload_req", label_visibility="collapsed",
        )
        if ma_file:
            try:
                master_asil = read_table(ma_file)
                set_state("master_data_asil", master_asil)
                st.success(f"Master Data dimuat: {len(master_asil)} SKU.")
            except Exception as e:
                st.error(f"Gagal: {e}")

    if master_asil is None:
        return

    # ── Parameter & Generate ─────────────────────────────────────────────
    st.markdown("<div class='section-title'>PARAMETER</div>", unsafe_allow_html=True)
    p1, p2 = st.columns(2)
    with p1:
        adj = st.slider("Penyesuaian Forecast (%)", -30.0, 30.0, 0.0, 0.5, key="des_adj",
                        help="Faktor koreksi volume sebelum masuk simulasi.")
    with p2:
        qty_def = st.number_input("Qty minimum per SKU-bulan", 1, 100, 1, key="des_qty")

    if st.button("Generate Input Simulasi DES", type="primary", key="btn_gen_des"):
        try:
            with st.spinner("Membuat input simulasi..."):
                result = _build_des_input(fc_df, master_asil, adj, qty_def)
            set_state("forecast_input_des", result)
            st.success(f"Input simulasi berhasil dibuat: {len(result):,} baris.")
            m1, m2, m3, m4 = st.columns(4)
            n_mon = result["MonthIndex"].nunique() if "MonthIndex" in result.columns else 1
            _kpi(m1, "JUMLAH SKU", result["SkuId"].nunique() if "SkuId" in result.columns else "?")
            _kpi(m2, "JUMLAH BULAN", n_mon)
            if "ForecastTon" in result.columns:
                _kpi(m3, "TOTAL FORECAST", f"{result['ForecastTon'].sum():,.1f} ton")
                _kpi(m4, "RATA-RATA/BULAN", f"{result['ForecastTon'].sum()/n_mon:,.1f} ton")
            st.dataframe(_rename_cols(result.head(30)), use_container_width=True, hide_index=True)
            st.download_button(
                "Unduh ForecastInput DES",
                data=result.to_csv(index=False).encode(),
                file_name="ForecastInput_DES.csv", mime="text/csv", key="dl_des",
            )
        except Exception as e:
            import traceback
            st.error(f"Error: {e}")
            with st.expander("Detail error"):
                st.code(traceback.format_exc())


def _build_des_input(fc_df, master_asil, adj_pct, qty_default):
    ma = master_asil.copy()
    col_map = {}
    for c in ma.columns:
        cs = c.strip()
        if cs in ["SkuId","sku","SKU","ItemCode"]: col_map[c] = "SkuId"
        elif cs == "ItemName": col_map[c] = "ItemName"
    ma = ma.rename(columns=col_map)
    if "SkuId" not in ma.columns:
        raise ValueError("Master Data tidak memiliki kolom SkuId.")
    fc = fc_df.copy()
    mult = 1 + adj_pct / 100
    fc["forecast"] = (fc["forecast"] * mult).clip(lower=0)
    merged = fc.merge(ma, left_on="sku", right_on="SkuId", how="inner")
    if merged.empty:
        raise ValueError("Tidak ada SKU yang cocok antara forecast dan Master Data.")
    rows = []
    for _, row in merged.iterrows():
        ton = float(row.get("forecast", 0))
        qty = max(int(round(ton)), qty_default) if ton > 0 else qty_default
        rows.append({
            "ItemName": row.get("ItemName", row.get("description", "")),
            "Qty": qty, "SkuId": row.get("SkuId", row["sku"]),
            "ForecastTon": round(ton, 6),
            "SkuGr": row.get("SkuGr", ""),
            "SpeedD": row.get("SpeedD", 0), "Speed": row.get("Speed", 0),
            "IsChocolate": row.get("IsChocolate", ""),
            "port_type": row.get("port_type", ""),
            "Allergen": row.get("Allergen", ""), "ShelfLife": row.get("ShelfLife", ""),
            "MonthIndex": str(row.get("date", ""))[:10],
        })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — VISUALISASI DEMAND
# ══════════════════════════════════════════════════════════════════════════════
def _tab_visualisasi():
    pkg_map = _load_pkg_map()

    # ── Master SKU (opsi DB / upload) ────────────────────────────────────
    has_db = MASTER_SKU_PATH.exists()
    with st.expander(
        "Master SKU — " + ("aktif dari database" if has_db else "belum tersedia"),
        expanded=not has_db,
    ):
        if has_db:
            try:
                msku = pd.read_csv(MASTER_SKU_PATH, encoding="latin-1", on_bad_lines="skip")
                msku.columns = [c.strip() for c in msku.columns]
                sku_col = msku.columns[0]
                msku = msku.rename(columns={sku_col: "Kode SKU"})
                show_cols = [c for c in ["Kode SKU","SIZE (g)","PORT TYPE"] if c in msku.columns]
                st.markdown(f"**{len(msku)} SKU tersedia.**")
                st.dataframe(msku[show_cols].head(12), use_container_width=True, hide_index=True)
            except Exception:
                pass
        opt = st.radio("Sumber Master SKU", ["Database","Upload Manual"],
                       horizontal=True, key="viz_msku_opt")
        if opt == "Upload Manual":
            mf = st.file_uploader("Upload master_sku.csv", type=["csv","xlsx"],
                                  key="msku_upload_viz", label_visibility="collapsed")
            if mf:
                try:
                    df_new = read_table(mf)
                    Path("data/masters").mkdir(parents=True, exist_ok=True)
                    df_new.to_csv(MASTER_SKU_PATH, index=False)
                    _load_pkg_map.clear()
                    st.success("Master SKU diperbarui.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal: {e}")

    pkg_map = _load_pkg_map()

    # ── Upload CSV forecast ───────────────────────────────────────────────
    st.markdown("<div class='section-title'>DATA FORECAST</div>", unsafe_allow_html=True)
    st.caption("Upload file forecast dari export tab FORECASTING, atau gunakan data dari sesi ini.")

    fc_session = get_state("forecast_output")
    has_sess   = isinstance(fc_session, pd.DataFrame) and not fc_session.empty

    viz_df = None
    if has_sess:
        if st.checkbox("Gunakan data dari tab FORECASTING", value=True, key="viz_use_sess"):
            viz_df = fc_session.copy()

    if viz_df is None:
        vf = st.file_uploader("Upload CSV Forecast", type=["csv","xlsx"],
                               key="viz_upload", label_visibility="collapsed")
        if vf:
            try:
                viz_df = read_table(vf)
                set_state("viz_cache", viz_df)
            except Exception as e:
                st.error(f"Gagal membaca: {e}")
        else:
            c = get_state("viz_cache")
            if isinstance(c, pd.DataFrame) and not c.empty:
                viz_df = c

    if viz_df is None:
        st.markdown(
            '<div class="note-box">Upload file forecast untuk menampilkan visualisasi.</div>',
            unsafe_allow_html=True,
        )
        return

    viz_df = _clean_forecast(viz_df)
    viz_df = _filter_active(viz_df)
    viz_df = _add_pkg(viz_df, pkg_map)
    sc_df  = _load_sku_classification()
    _render_charts(viz_df, ctx="t3", sc_df=sc_df)


# ══════════════════════════════════════════════════════════════════════════════
# SHARED CHARTS
# ══════════════════════════════════════════════════════════════════════════════
def _render_charts(df: pd.DataFrame, ctx: str = "x", sc_df=None):
    has_date  = "date" in df.columns
    has_val   = "forecast" in df.columns
    has_sku   = "sku" in df.columns
    has_desc  = "description" in df.columns
    has_mape  = "mape_backtest" in df.columns
    has_wmape = "wmape_backtest" in df.columns
    has_patt  = "demand_pattern" in df.columns
    has_model = "model_used" in df.columns
    label_col = "description" if has_desc else ("sku" if has_sku else None)

    if not has_val or label_col is None:
        st.dataframe(df, use_container_width=True, hide_index=True)
        return

    # ── KPI ───────────────────────────────────────────────────────────────
    st.markdown("<div class='section-title'>RINGKASAN</div>", unsafe_allow_html=True)
    n_sku   = df["sku"].nunique() if has_sku else "-"
    n_month = int(df["date"].dropna().nunique()) if has_date else 1
    avg_m   = df["forecast"].sum() / max(n_month, 1)
    period_str = ""
    if has_date:
        mn = df["date"].dropna().min(); mx = df["date"].dropna().max()
        if pd.notna(mn) and pd.notna(mx):
            period_str = f"{mn.strftime('%b %Y')} – {mx.strftime('%b %Y')}"

    acc_val = None
    acc_lbl = "AKURASI"
    if has_sku and has_wmape:
        acc_val = df.groupby("sku")["wmape_backtest"].first().dropna().mean()
        acc_lbl = "WMAPE RATA-RATA"
    elif has_sku and has_mape:
        acc_val = df.groupby("sku")["mape_backtest"].first().dropna().mean()
        acc_lbl = "MAPE RATA-RATA"

    k1, k2, k3, k4 = st.columns(4)
    _kpi(k1, "SKU AKTIF",     str(n_sku))
    _kpi(k2, "VOLUME/BULAN",  f"{avg_m:,.1f} ton")
    _kpi(k3, "PERIODE",       period_str or "-")
    _kpi(k4, acc_lbl,         f"{acc_val:.1f}%" if acc_val is not None else "N/A")

    if acc_val and acc_val > 30:
        st.markdown(
            '<div class="warn-box">Beberapa SKU memiliki akurasi rendah — verifikasi manual disarankan.</div>',
            unsafe_allow_html=True,
        )

    # ── Distribusi Model (jika ada) ───────────────────────────────────────
    if has_model and has_patt and has_sku:
        with st.expander("Distribusi Model & Pola Permintaan", expanded=False):
            mc1, mc2 = st.columns(2)
            with mc1:
                seg_ct = df.drop_duplicates("sku")["demand_pattern"].value_counts().reset_index()
                seg_ct.columns = ["Pola", "Jumlah SKU"]
                fig_seg = px.bar(
                    seg_ct, x="Pola", y="Jumlah SKU",
                    color="Pola", color_discrete_map=SEG_COLORS, height=240,
                )
                fig_seg.update_layout(**_chart_kw(showlegend=False, title_text="Pola Permintaan"))
                st.plotly_chart(fig_seg, use_container_width=True, key=f"seg_{ctx}")
            with mc2:
                mod_ct = df.drop_duplicates("sku")["model_used"].value_counts().reset_index()
                mod_ct.columns = ["Model", "Jumlah SKU"]
                fig_mod = px.pie(
                    mod_ct, names="Model", values="Jumlah SKU",
                    color="Model", color_discrete_map=MODEL_COLORS, height=240, hole=0.4,
                )
                fig_mod.update_layout(**_chart_kw(showlegend=True, title_text="Model Digunakan"))
                st.plotly_chart(fig_mod, use_container_width=True, key=f"mod_{ctx}")

    # ── Bar + Donut ───────────────────────────────────────────────────────
    st.markdown(
        "<div class='section-title'>VOLUME PER SKU & PROPORSI KEMASAN</div>",
        unsafe_allow_html=True,
    )
    ch1, ch2 = st.columns([3, 2])

    if has_date:
        months = sorted(df["date"].dropna().unique())
        sel_m  = st.selectbox(
            "Tampilkan untuk:", months,
            format_func=lambda x: pd.Timestamp(x).strftime("%b %Y"),
            key=f"sel_month_{ctx}",
        )
        m_df    = df[df["date"] == sel_m].sort_values("forecast").tail(20)
        pie_src = df[df["date"] == sel_m]
        bl      = pd.Timestamp(sel_m).strftime("%b %Y")
    else:
        m_df    = df.groupby([label_col,"_pkg"])["forecast"].sum().reset_index().sort_values("forecast").tail(20)
        pie_src = df; bl = "Semua"

    with ch1:
        fig_b = px.bar(
            m_df, y=label_col, x="forecast", color="_pkg", orientation="h",
            color_discrete_map=PKG_COLORS, height=460,
            labels={"forecast": "ton (volume)", "_pkg": "Jenis Kemasan"},
        )
        fig_b.update_layout(**_chart_kw(yaxis_title="", xaxis_title=f"Volume ton ({bl})"))
        st.plotly_chart(fig_b, use_container_width=True, key=f"bar_{ctx}")

    with ch2:
        ps = pie_src.groupby("_pkg")["forecast"].sum().reset_index()
        ps.columns = ["Kemasan","Volume"]
        ps = ps[ps["Volume"] > 0]
        fig_pie = go.Figure(data=[go.Pie(
            labels=ps["Kemasan"], values=ps["Volume"], hole=0.45,
            marker_colors=[PKG_COLORS.get(k,"#EBF4F6") for k in ps["Kemasan"]],
            textinfo="percent+label", textfont_size=12,
        )])
        fig_pie.update_layout(
            plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=FONT_COLOR,
            showlegend=False, margin=dict(l=10,r=10,t=36,b=10), height=460,
            title=dict(text=f"Proporsi Kemasan — {bl}", x=0.5, font=dict(size=13)),
        )
        st.plotly_chart(fig_pie, use_container_width=True, key=f"pie_{ctx}")

    # ── Top 10 ───────────────────────────────────────────────────────────
    st.markdown(
        "<div class='section-title'>TOP 10 PRODUK — RATA-RATA PER BULAN</div>",
        unsafe_allow_html=True,
    )
    top10 = df.groupby([label_col,"_pkg"])["forecast"].mean().reset_index()
    top10.columns = ["Produk","Kemasan","Rata-rata (ton/bln)"]
    top10 = top10.sort_values("Rata-rata (ton/bln)").tail(10)
    fig_t = px.bar(
        top10, y="Produk", x="Rata-rata (ton/bln)", color="Kemasan", orientation="h",
        color_discrete_map=PKG_COLORS, height=380,
    )
    fig_t.update_layout(**_chart_kw(yaxis_title="", xaxis_title="Rata-rata ton/bulan"))
    st.plotly_chart(fig_t, use_container_width=True, key=f"top10_{ctx}")

    # ── Tren ─────────────────────────────────────────────────────────────
    if has_date:
        st.markdown(
            "<div class='section-title'>TREN BULANAN PER JENIS KEMASAN</div>",
            unsafe_allow_html=True,
        )
        trend = df.groupby(["date","_pkg"])["forecast"].sum().reset_index()
        trend.columns = ["Tanggal","Kemasan","Volume (ton)"]
        fig_l = px.line(
            trend, x="Tanggal", y="Volume (ton)", color="Kemasan", markers=True,
            color_discrete_map=PKG_COLORS, height=300,
        )
        fig_l.update_layout(**_chart_kw(xaxis_title="", yaxis_title="Volume (ton)"))
        st.plotly_chart(fig_l, use_container_width=True, key=f"trend_{ctx}")
