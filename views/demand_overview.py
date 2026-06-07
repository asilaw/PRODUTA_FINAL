"""
ANALISIS DEMAND & FORECASTING
----------------------------------------------------------------------
Tab 1 — FORECASTING   (domain Ubay)
  · Upload raw historical → jalankan forecast (stub → Ubay isi)
  · Visualisasi hasil forecast per SKU + summary + backtest
  · Upload manual CSV forecast jika pipeline belum jalan

Tab 2 — INPUT SIMULASI DES   (domain Asil)
  · Pakai output Tab 1 ATAU upload CSV forecast manual
  · Upload Master SKU (Asil) → auto-merge + generate ForecastInput DES

Tab 3 — VISUALISASI DEMAND   (domain Gibran)
  · Upload CSV forecast Ubay (prophet_forecast_output.csv)
  · KPI cards: SKU Aktif (total>0), Volume/Bulan, Periode, Akurasi Model
  · Charts: Volume per SKU & kemasan, donut proporsi, Top 10, Tren bulanan
----------------------------------------------------------------------
CATATAN MASTER DATA:
  · Master SKU Gibran (master_sku.csv): SKU ↔ kemasan, lini, status produksi,
    machine hours, OPEX, biaya maklon — digunakan di Tab 3 (enrichment warna)
    dan di Capacity Planning / Production Allocation.
  · Master Data Asil (Master_data.xlsx): SKU ↔ SpeedD, Speed, IsChocolate,
    port_type, Allergen, ShelfLife — digunakan untuk generate ForecastInput DES
    di Tab 2. Semua 62 SKU Asil ada di master Gibran → gunakan Asil untuk DES.
"""

import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import io

from modules.theme import hero
from modules.session import get_state, set_state
from modules.io_utils import read_table

# ─── Konstanta & Palet ──────────────────────────────────────────────────────
PKG_COLORS = {
    "SSS":       "#071952",
    "BIB":       "#37B7C3",
    "STICKPACK": "#088395",
}
CHART_BG   = "#FFFFFF"
FONT_COLOR = "#071952"

# ─── Utility functions ──────────────────────────────────────────────────────
def _detect_pkg_from_master(sku: str, master_gibran: pd.DataFrame) -> str:
    """Ambil jenis kemasan dari master SKU Gibran jika tersedia."""
    if master_gibran is not None and not master_gibran.empty:
        row = master_gibran[master_gibran["_sku"] == sku]
        if not row.empty:
            pt = str(row["PRODUCT TYPE"].iloc[0]).upper()
            if "STICK" in pt: return "STICKPACK"
            if "BIB" in pt:   return "BIB"
            return "SSS"
    return _detect_pkg_fallback(sku)

def _detect_pkg_fallback(val: str) -> str:
    """Fallback: deteksi dari deskripsi/SKU string."""
    d = str(val).upper()
    if "SAC" in d or "STICK" in d: return "STICKPACK"
    if "BIB" in d:                  return "BIB"
    return "SSS"

def _chart_layout(**kw):
    base = dict(
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=FONT_COLOR,
        margin=dict(l=10, r=10, t=36, b=10),
        legend=dict(orientation="h", y=-0.24, font=dict(size=11)),
        font=dict(family="Inter, sans-serif"),
    )
    base.update(kw)
    return base

def _load_master_gibran() -> pd.DataFrame | None:
    """Load master_sku.csv Gibran dari session (jika sudah diupload)."""
    df = get_state("master_sku_gibran")
    if isinstance(df, pd.DataFrame) and not df.empty:
        return df
    return None

def _clean_forecast(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize forecast DataFrame columns."""
    col_map = {}
    for c in df.columns:
        cl = c.strip().lower()
        if cl == "date": col_map[c] = "date"
        elif cl == "forecast": col_map[c] = "forecast"
        elif cl == "forecast_lower": col_map[c] = "forecast_lower"
        elif cl == "forecast_upper": col_map[c] = "forecast_upper"
        elif cl in ("sku", "skuid"): col_map[c] = "sku"
        elif cl in ("description", "descriptionforecast", "item_name", "itemname"): col_map[c] = "description"
        elif cl in ("mape_backtest", "mape", "mape_cv"): col_map[c] = "mape_backtest"
    df = df.rename(columns=col_map)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "forecast" in df.columns:
        df["forecast"] = pd.to_numeric(df["forecast"], errors="coerce").fillna(0).clip(lower=0)
    return df


# ═══════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ═══════════════════════════════════════════════════════════════════════════
def render():
    # Judul: BOLD + UPPERCASE
    st.markdown(
        '<div class="page-title">ANALISIS DEMAND & FORECASTING</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="color:#088395;font-size:.88rem;margin:-12px 0 18px 0;">'
        'Forecasting permintaan, konversi ke input simulasi DES, dan visualisasi kapasitas.</p>',
        unsafe_allow_html=True,
    )

    # Tab names UPPERCASE
    tab1, tab2, tab3 = st.tabs(["FORECASTING", "INPUT SIMULASI DES", "VISUALISASI DEMAND"])

    # ══════════════════════════════════════════════════════════════════════
    # TAB 1 — FORECASTING (domain Ubay)
    # ══════════════════════════════════════════════════════════════════════
    with tab1:
        _tab_forecasting()

    # ══════════════════════════════════════════════════════════════════════
    # TAB 2 — INPUT SIMULASI DES (domain Asil)
    # ══════════════════════════════════════════════════════════════════════
    with tab2:
        _tab_des_input()

    # ══════════════════════════════════════════════════════════════════════
    # TAB 3 — VISUALISASI DEMAND (domain Gibran)
    # ══════════════════════════════════════════════════════════════════════
    with tab3:
        _tab_visualisasi()


# ─────────────────────────────────────────────────────────────────────────
# TAB 1: FORECASTING
# ─────────────────────────────────────────────────────────────────────────
def _tab_forecasting():
    # ── Section A: Upload Raw Historical ────────────────────────────────
    st.markdown("<div class='section-title'>Data Historis</div>", unsafe_allow_html=True)
    st.caption("Upload data historis permintaan untuk menjalankan pipeline forecast.")

    raw_file = st.file_uploader(
        "Upload Data Historis (CSV/Excel)", type=["csv","xlsx","xls","tsv"],
        key="raw_hist_upload", label_visibility="collapsed",
    )
    if raw_file:
        try:
            raw_df = read_table(raw_file)
            set_state("forecast_raw", raw_df)
            st.success(f"Data historis dimuat: {len(raw_df):,} baris, {raw_df.shape[1]} kolom.")
            with st.expander("Preview Data Historis"):
                st.dataframe(raw_df.head(50), use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Gagal membaca: {e}")

    # ── Section B: Parameter & Run Forecast ─────────────────────────────
    raw_df  = get_state("forecast_raw")
    has_raw = isinstance(raw_df, pd.DataFrame) and not raw_df.empty

    st.markdown("<div class='section-title'>Parameter Forecast</div>", unsafe_allow_html=True)
    fc1, fc2, fc3 = st.columns(3)
    with fc1: method  = st.selectbox("Metode", ["Auto","Prophet","Croston","Moving Average"], key="fc_method")
    with fc2: horizon = st.number_input("Horizon (bulan)", 3, 36, 12, 1, key="fc_horizon")
    with fc3: st.markdown("<br>", unsafe_allow_html=True)

    if st.button("Jalankan Forecast", type="primary", disabled=not has_raw, key="btn_run_fc"):
        try:
            from modules.forecast_engine import run_forecast
            with st.spinner("Memproses pipeline forecast..."):
                fc_result = run_forecast(raw_df, horizon_months=horizon, method=method)
            fc_result = _clean_forecast(fc_result)
            set_state("forecast_output", fc_result)
            st.success(f"Forecast selesai: {len(fc_result):,} baris untuk {fc_result['sku'].nunique() if 'sku' in fc_result.columns else '?'} SKU.")
        except NotImplementedError:
            st.info("Pipeline forecast sedang dalam pengembangan. Upload hasil forecast di bawah.")
        except Exception as e:
            st.error(f"Error: {e}")

    if not has_raw:
        st.markdown("<div class='note-box'>Upload data historis untuk mengaktifkan pipeline forecast.</div>", unsafe_allow_html=True)

    # ── Section C: Upload manual jika pipeline belum ada ────────────────
    st.markdown("<div class='section-title'>Atau Upload Hasil Forecast (CSV)</div>", unsafe_allow_html=True)
    st.caption("Upload file prophet_forecast_output.csv atau format serupa.")

    fc_manual = st.file_uploader(
        "Upload CSV Forecast", type=["csv","xlsx"], key="fc_manual_upload",
        label_visibility="collapsed",
    )
    if fc_manual:
        try:
            df_man = _clean_forecast(read_table(fc_manual))
            set_state("forecast_output", df_man)
            st.success(f"Forecast dimuat: {len(df_man):,} baris.")
        except Exception as e:
            st.error(f"Gagal membaca: {e}")

    # ── Section D: Visualisasi hasil forecast (sama dgn Tab Visualisasi) ─
    fc_df  = get_state("forecast_output")
    has_fc = isinstance(fc_df, pd.DataFrame) and not fc_df.empty

    if not has_fc:
        st.markdown("<div class='note-box'>Belum ada data forecast. Upload file atau jalankan pipeline.</div>", unsafe_allow_html=True)
        return

    fc_df = _clean_forecast(fc_df)

    # Filter SKU aktif
    if "sku" in fc_df.columns and "forecast" in fc_df.columns:
        sku_totals = fc_df.groupby("sku")["forecast"].sum()
        active_skus = sku_totals[sku_totals > 0].index
        fc_df = fc_df[fc_df["sku"].isin(active_skus)].copy()

    # Tambah kolom _pkg
    master_g = _load_master_gibran()
    if "sku" in fc_df.columns:
        fc_df["_pkg"] = fc_df["sku"].apply(lambda x: _detect_pkg_from_master(x, master_g))
    elif "description" in fc_df.columns:
        fc_df["_pkg"] = fc_df["description"].apply(_detect_pkg_fallback)
    else:
        fc_df["_pkg"] = "SSS"

    _render_forecast_charts(fc_df, context="tab1")


# ─────────────────────────────────────────────────────────────────────────
# TAB 2: INPUT SIMULASI DES
# ─────────────────────────────────────────────────────────────────────────
def _tab_des_input():
    st.markdown("<div class='section-title'>Output Forecast</div>", unsafe_allow_html=True)
    st.caption("Gunakan hasil forecast dari tab FORECASTING, atau upload file forecast secara langsung.")

    fc_df  = get_state("forecast_output")
    has_fc = isinstance(fc_df, pd.DataFrame) and not fc_df.empty

    if has_fc:
        fc_df = _clean_forecast(fc_df)
        # Filter aktif
        if "sku" in fc_df.columns and "forecast" in fc_df.columns:
            sku_totals = fc_df.groupby("sku")["forecast"].sum()
            active = sku_totals[sku_totals > 0].index
            fc_df  = fc_df[fc_df["sku"].isin(active)].copy()
        n_sku = fc_df["sku"].nunique() if "sku" in fc_df.columns else "?"
        st.success(f"Output forecast terdeteksi — {len(fc_df):,} baris, {n_sku} SKU aktif.")

        sub_a, sub_b = st.tabs(["Forecast", "SKU Stats"])
        with sub_a:
            if "sku" in fc_df.columns:
                all_skus = sorted(fc_df["sku"].dropna().unique().tolist())
                sel_skus = st.multiselect("Filter SKU", all_skus, default=all_skus[:5], key="des_sku_filter")
                show_df  = fc_df[fc_df["sku"].isin(sel_skus)] if sel_skus else fc_df
            else:
                show_df = fc_df
            st.dataframe(show_df.head(300), use_container_width=True, hide_index=True)
        with sub_b:
            # Tampilkan sku_classification jika ada
            try:
                sc = pd.read_csv("data/forecast/sku_classification.csv")
                st.dataframe(sc, use_container_width=True, hide_index=True)
            except Exception:
                st.info("File sku_classification.csv tidak ditemukan.")
    else:
        st.markdown("<div class='note-box'>Belum ada output forecast. Upload di tab FORECASTING terlebih dahulu.</div>", unsafe_allow_html=True)
        fc_upload = st.file_uploader(
            "Atau upload file forecast di sini", type=["csv","xlsx"], key="fc_des_bridge",
            label_visibility="collapsed",
        )
        if fc_upload:
            try:
                df_tmp = _clean_forecast(read_table(fc_upload))
                set_state("forecast_output", df_tmp)
                has_fc = True
                fc_df  = df_tmp
                st.success(f"Forecast dimuat: {len(df_tmp):,} baris.")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal membaca: {e}")

    if not has_fc:
        return

    # ── Master Data (Asil format — untuk DES) ───────────────────────────
    st.markdown("<div class='section-title'>Master Data SKU (Untuk DES)</div>", unsafe_allow_html=True)
    st.caption(
        "Upload Master Data SKU yang berisi kecepatan mesin, port type, dan parameter simulasi. "
        "Format: ItemName, SkuId, SkuGr, SpeedD, Speed, IsChocolate, port_type, Allergen, ShelfLife."
    )

    master_asil_state = get_state("master_data_asil")
    has_master_asil   = isinstance(master_asil_state, pd.DataFrame) and not master_asil_state.empty

    master_asil_file = st.file_uploader(
        "Upload Master Data (Excel/CSV)", type=["xlsx","xls","csv"],
        key="master_asil_upload", label_visibility="collapsed",
    )
    if master_asil_file:
        try:
            ma = read_table(master_asil_file)
            set_state("master_data_asil", ma)
            has_master_asil   = True
            master_asil_state = ma
            st.success(f"Master Data dimuat: {len(ma)} SKU.")
        except Exception as e:
            st.error(f"Gagal membaca: {e}")

    if has_master_asil:
        with st.expander("Preview Master Data"):
            st.dataframe(master_asil_state.head(20), use_container_width=True, hide_index=True)

    # ── Parameter ────────────────────────────────────────────────────────
    st.markdown("<div class='section-title'>Parameter</div>", unsafe_allow_html=True)
    p1, p2 = st.columns(2)
    with p1:
        adj = st.slider(
            "Adjustment forecast (%)", -30.0, 30.0, 0.0, 0.5,
            help="Koreksi volume forecast sebelum masuk simulasi.",
            key="des_adj",
        )
    with p2:
        qty_def = st.number_input("Qty default per SKU-bulan", 1, 100, 1, key="des_qty")

    if not has_master_asil:
        st.warning("Upload Master Data untuk mengaktifkan generator ForecastInput DES.")
        return

    # ── Generate button ──────────────────────────────────────────────────
    if st.button("Generate ForecastInput DES", type="primary", key="btn_gen_des"):
        try:
            with st.spinner("Membuat input simulasi..."):
                result = _build_des_input(fc_df, master_asil_state, adj, qty_def)
            if result is not None and not result.empty:
                set_state("forecast_input_des", result)
                st.success(f"ForecastInput DES berhasil: {len(result):,} baris.")

                m1, m2, m3, m4 = st.columns(4)
                n_mon = result["MonthIndex"].nunique() if "MonthIndex" in result.columns else 1
                m1.metric("Jumlah SKU", result["SkuId"].nunique() if "SkuId" in result.columns else "?")
                m2.metric("Jumlah Bulan", n_mon)
                ft_col = "ForecastTon" if "ForecastTon" in result.columns else None
                if ft_col:
                    m3.metric("Total Forecast", f"{result[ft_col].sum():,.1f} ton")
                    m4.metric("Rata-rata/Bulan", f"{result[ft_col].sum()/n_mon:,.1f} ton")

                st.markdown("<div class='section-title'>Preview</div>", unsafe_allow_html=True)
                st.dataframe(result.head(50), use_container_width=True, hide_index=True)
                st.download_button(
                    "Unduh ForecastInput DES",
                    data=result.to_csv(index=False).encode(),
                    file_name="ForecastInput_DES.csv", mime="text/csv",
                    key="dl_des",
                )
            else:
                st.error("Hasil kosong. Periksa kolom SkuId di Master Data dan sku di forecast.")
        except Exception as e:
            import traceback
            st.error(f"Error: {e}")
            st.code(traceback.format_exc())


def _build_des_input(fc_df: pd.DataFrame, master_asil: pd.DataFrame,
                     adj_pct: float, qty_default: int) -> pd.DataFrame:
    """
    Gabungkan forecast + Master Data Asil → format ForecastInput DES.
    Format output: ItemName, Qty, SkuId, ForecastTon, SkuGr, SpeedD, Speed,
                   IsChocolate, port_type, Allergen, ShelfLife, MonthIndex
    """
    # Normalize master column names
    ma = master_asil.copy()
    col_map = {}
    for c in ma.columns:
        cl = c.strip()
        if cl in ["SkuId","sku","SKU","ItemCode"]: col_map[c] = "SkuId"
        elif cl == "ItemName": col_map[c] = "ItemName"
    ma = ma.rename(columns=col_map)
    if "SkuId" not in ma.columns:
        raise ValueError("Master Data tidak memiliki kolom SkuId.")

    # Normalize forecast
    fc = fc_df.copy()
    if "sku" not in fc.columns:
        raise ValueError("Forecast tidak memiliki kolom sku.")

    # Adjustment
    mult = 1 + adj_pct / 100
    fc["forecast"] = (fc["forecast"] * mult).clip(lower=0)

    # Merge
    merged = fc.merge(ma, left_on="sku", right_on="SkuId", how="inner")
    if merged.empty:
        raise ValueError("Tidak ada SKU yang cocok antara forecast dan Master Data.")

    # Build output
    des_rows = []
    for _, row in merged.iterrows():
        ton = float(row.get("forecast", 0))
        qty = max(int(round(ton)), qty_default) if ton > 0 else qty_default
        des_rows.append({
            "ItemName":    row.get("ItemName", row.get("description", "")),
            "Qty":         qty,
            "SkuId":       row.get("SkuId", row["sku"]),
            "ForecastTon": round(ton, 6),
            "SkuGr":       row.get("SkuGr", ""),
            "SpeedD":      row.get("SpeedD", 0),
            "Speed":       row.get("Speed", 0),
            "IsChocolate": row.get("IsChocolate", ""),
            "port_type":   row.get("port_type", ""),
            "Allergen":    row.get("Allergen", ""),
            "ShelfLife":   row.get("ShelfLife", ""),
            "MonthIndex":  row.get("date", ""),
        })
    return pd.DataFrame(des_rows)


# ─────────────────────────────────────────────────────────────────────────
# TAB 3: VISUALISASI DEMAND
# ─────────────────────────────────────────────────────────────────────────
def _tab_visualisasi():
    # Upload master SKU Gibran untuk enrichment kemasan
    with st.expander("Upload Master SKU (Opsional — untuk deteksi kemasan otomatis)", expanded=False):
        msku_file = st.file_uploader(
            "Upload master_sku.csv", type=["csv","xlsx"], key="msku_gibran_upload",
            label_visibility="collapsed",
        )
        if msku_file:
            try:
                msku = read_table(msku_file)
                # Normalize sku column
                first_col = msku.columns[0]
                msku = msku.rename(columns={first_col: "_sku"})
                msku["_sku"] = msku["_sku"].astype(str).str.strip()
                set_state("master_sku_gibran", msku)
                st.success(f"Master SKU dimuat: {len(msku)} baris.")
            except Exception as e:
                st.error(f"Gagal membaca: {e}")

    # ── Upload CSV forecast (TIDAK auto-load dari DB) ────────────────────
    st.markdown("<div class='section-title'>Upload Data Forecast</div>", unsafe_allow_html=True)
    st.caption(
        "Upload file hasil forecast (prophet_forecast_output.csv atau format serupa). "
        "Kolom yang diperlukan: date, sku, forecast. Kolom opsional: description, mape_backtest."
    )

    # Cek apakah sudah ada di session dari Tab 1
    fc_session = get_state("forecast_output")
    has_session_fc = isinstance(fc_session, pd.DataFrame) and not fc_session.empty

    use_session = False
    if has_session_fc:
        use_session = st.checkbox(
            "Gunakan data forecast dari tab FORECASTING",
            value=True, key="viz_use_session",
        )

    viz_df = None
    if use_session and has_session_fc:
        viz_df = fc_session.copy()
    else:
        viz_file = st.file_uploader(
            "Upload CSV Forecast", type=["csv","xlsx"], key="viz_upload",
            label_visibility="collapsed",
        )
        if viz_file:
            try:
                viz_df = read_table(viz_file)
                set_state("viz_forecast_df", viz_df)
            except Exception as e:
                st.error(f"Gagal membaca: {e}")
        else:
            # Coba dari session viz khusus (dari upload sebelumnya di tab ini)
            prev = get_state("viz_forecast_df")
            if isinstance(prev, pd.DataFrame) and not prev.empty:
                viz_df = prev

    if viz_df is None or (isinstance(viz_df, pd.DataFrame) and viz_df.empty):
        st.markdown(
            '<div class="note-box">Upload file forecast untuk menampilkan visualisasi demand.</div>',
            unsafe_allow_html=True,
        )
        return

    # Normalize + filter aktif
    viz_df = _clean_forecast(viz_df)
    master_g = _load_master_gibran()

    if "sku" in viz_df.columns:
        viz_df["_pkg"] = viz_df["sku"].apply(lambda x: _detect_pkg_from_master(x, master_g))
    elif "description" in viz_df.columns:
        viz_df["_pkg"] = viz_df["description"].apply(_detect_pkg_fallback)
    else:
        viz_df["_pkg"] = "SSS"

    if "sku" in viz_df.columns and "forecast" in viz_df.columns:
        sku_totals = viz_df.groupby("sku")["forecast"].sum()
        active_skus = sku_totals[sku_totals > 0].index
        viz_df = viz_df[viz_df["sku"].isin(active_skus)].copy()

    _render_forecast_charts(viz_df, context="tab3")


# ─────────────────────────────────────────────────────────────────────────
# SHARED: Render forecast charts (dipakai Tab 1 & Tab 3)
# ─────────────────────────────────────────────────────────────────────────
def _render_forecast_charts(df: pd.DataFrame, context: str = ""):
    has_date  = "date" in df.columns
    has_sku   = "sku" in df.columns
    has_val   = "forecast" in df.columns
    has_desc  = "description" in df.columns
    has_mape  = "mape_backtest" in df.columns

    label_col = "description" if has_desc else "sku" if has_sku else None

    # ── KPI Cards ─────────────────────────────────────────────────────────
    st.markdown("<div class='section-title'>RINGKASAN</div>", unsafe_allow_html=True)

    n_sku   = df["sku"].nunique() if has_sku else "-"
    n_month = df["date"].dropna().nunique() if has_date else 1
    avg_m   = df["forecast"].sum() / max(n_month, 1) if has_val else 0

    period_str = ""
    if has_date:
        mn, mx = df["date"].dropna().min(), df["date"].dropna().max()
        if pd.notna(mn) and pd.notna(mx):
            period_str = f"{mn.strftime('%b %Y')} – {mx.strftime('%b %Y')}"

    # Avg MAPE per SKU (bukan per baris)
    avg_mape = None
    if has_mape and has_sku:
        avg_mape = df.groupby("sku")["mape_backtest"].first().mean()
    elif has_mape:
        avg_mape = df["mape_backtest"].mean()

    k1, k2, k3, k4 = st.columns(4)
    for col_obj, lbl, val in [
        (k1, "SKU AKTIF",     str(n_sku)),
        (k2, "VOLUME/BULAN",  f"{avg_m:,.1f} ton" if has_val else "-"),
        (k3, "PERIODE",       period_str or "-"),
        (k4, "AKURASI MODEL", f"{avg_mape:.1f}%" if avg_mape is not None else "N/A"),
    ]:
        col_obj.markdown(
            f'<div class="kpi-box">'
            f'<div class="kpi-label">{lbl}</div>'
            f'<div class="kpi-value">{val}</div></div>',
            unsafe_allow_html=True,
        )

    # Warning MAPE
    if avg_mape is not None and avg_mape > 30 and has_sku and has_mape:
        n_hi = (df.groupby("sku")["mape_backtest"].first() > 30).sum()
        if n_hi:
            st.markdown(
                f'<div class="warn-box">{n_hi} SKU memiliki MAPE &gt; 30% — gunakan angka dengan hati-hati.</div>',
                unsafe_allow_html=True,
            )

    if not has_val or not label_col:
        st.dataframe(df, use_container_width=True, hide_index=True)
        return

    # ── Row 1: Volume per SKU + Donut Kemasan ───────────────────────────
    st.markdown(
        "<div class='section-title'>VOLUME PER SKU & PROPORSI KEMASAN</div>",
        unsafe_allow_html=True,
    )
    ch1, ch2 = st.columns([3, 2])

    # Pilih bulan
    if has_date:
        months = sorted(df["date"].dropna().unique())
        sel_m  = st.selectbox(
            "Tampilkan untuk:",
            months,
            format_func=lambda x: pd.Timestamp(x).strftime("%b %Y"),
            key=f"sel_month_{context}",
        )
        m_df = df[df["date"] == sel_m].sort_values("forecast", ascending=True).tail(20)
        pie_src = df[df["date"] == sel_m]
        bulan_label = pd.Timestamp(sel_m).strftime("%b %Y")
    else:
        m_df = df.groupby([label_col, "_pkg"])["forecast"].sum().reset_index().sort_values("forecast").tail(20)
        pie_src = df
        bulan_label = "Semua"

    with ch1:
        fig_b = px.bar(
            m_df, y=label_col, x="forecast", color="_pkg",
            orientation="h", color_discrete_map=PKG_COLORS,
            height=440,
            labels={"forecast": "ton", "_pkg": "Kemasan"},
        )
        fig_b.update_layout(**_chart_layout(
            yaxis_title="", xaxis_title=f"ton ({bulan_label})",
        ))
        st.plotly_chart(fig_b, use_container_width=True)

    with ch2:
        pkg_sum = pie_src.groupby("_pkg")["forecast"].sum().reset_index()
        pkg_sum.columns = ["Kemasan", "Volume"]
        pkg_sum = pkg_sum[pkg_sum["Volume"] > 0]

        fig_pie = go.Figure(data=[go.Pie(
            labels=pkg_sum["Kemasan"], values=pkg_sum["Volume"],
            hole=0.45,
            marker_colors=[PKG_COLORS.get(k, "#EBF4F6") for k in pkg_sum["Kemasan"]],
            textinfo="percent+label", textfont_size=12,
        )])
        fig_pie.update_layout(
            plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=FONT_COLOR,
            showlegend=False,
            margin=dict(l=10, r=10, t=36, b=10),
            height=440,
            title=dict(text=f"Kemasan — {bulan_label}", x=0.5, font=dict(size=13)),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # ── Row 2: Top 10 SKU ─────────────────────────────────────────────────
    st.markdown("<div class='section-title'>TOP 10 SKU — RATA-RATA PER BULAN</div>", unsafe_allow_html=True)
    top10 = df.groupby([label_col, "_pkg"])["forecast"].mean().reset_index()
    top10.columns = ["nama", "kemasan", "avg"]
    top10 = top10.sort_values("avg").tail(10)

    fig_t = px.bar(
        top10, y="nama", x="avg", color="kemasan", orientation="h",
        color_discrete_map=PKG_COLORS, height=380,
        labels={"avg": "avg ton/bln", "kemasan": "Kemasan"},
    )
    fig_t.update_layout(**_chart_layout(yaxis_title="", xaxis_title="avg ton/bln"))
    st.plotly_chart(fig_t, use_container_width=True)

    # ── Row 3: Tren Bulanan per Kemasan ──────────────────────────────────
    if has_date:
        st.markdown(
            "<div class='section-title'>TREN BULANAN PER TIPE KEMASAN</div>",
            unsafe_allow_html=True,
        )
        trend = df.groupby(["date", "_pkg"])["forecast"].sum().reset_index()
        fig_l = px.line(
            trend, x="date", y="forecast", color="_pkg", markers=True,
            color_discrete_map=PKG_COLORS, height=300,
            labels={"forecast": "ton", "_pkg": "Kemasan"},
        )
        fig_l.update_layout(**_chart_layout(xaxis_title="", yaxis_title="ton"))
        st.plotly_chart(fig_l, use_container_width=True)
