"""
Analisis Demand — 3 tab:
  1. Forecasting     (Ubay)
  2. Input Simulasi DES  (Asil)
  3. Visualisasi Demand  (Gibran)
"""
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from modules.theme import hero
from modules.session import get_state, set_state
from modules.des_input_builder import build_forecast_input_des
from modules.io_utils import read_table, first_existing_file

# ─── Palet Warna ───────────────────────────────────────────────────────────
PKG_COLORS = {
    "SSS":       "#071952",
    "BIB":       "#37B7C3",
    "STICKPACK": "#088395",
}
CHART_BG = "#FFFFFF"
FONT_COLOR = "#071952"

# ─── Utility ────────────────────────────────────────────────────────────────
def _detect_pkg(desc: str) -> str:
    d = str(desc).upper()
    if "STICK" in d or "SAC" in d:
        return "STICKPACK"
    if "BIB" in d:
        return "BIB"
    return "SSS"

def _chart_layout(**kw):
    base = dict(
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG,
        font_color=FONT_COLOR,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", y=-0.22, font=dict(size=11)),
    )
    base.update(kw)
    return base

def _load_default_forecast():
    """Auto-load dari data/forecast/ jika ada."""
    for fname in ["prophet_forecast_output.csv", "unified_forecast_output.csv"]:
        p = f"data/forecast/{fname}"
        try:
            df = pd.read_csv(p)
            if not df.empty:
                return df
        except Exception:
            pass
    return None

def _load_default_sku_class():
    for fname in ["sku_classification.csv"]:
        p = f"data/forecast/{fname}"
        try:
            return pd.read_csv(p)
        except Exception:
            pass
    return None


def render():
    hero(
        "Analisis Demand & Forecasting",
        "Forecasting permintaan, konversi ke input simulasi DES, dan visualisasi kapasitas.",
    )

    tab1, tab2, tab3 = st.tabs(["Forecasting", "Input Simulasi DES", "Visualisasi Demand"])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — FORECASTING (Ubay)
    # ══════════════════════════════════════════════════════════════════════════
    with tab1:
        st.markdown("<div class='section-title'>Data Historis</div>", unsafe_allow_html=True)
        st.caption("Upload data historis permintaan. Format: CSV atau Excel.")

        raw_file = st.file_uploader(
            "Upload Data Historis",
            type=["csv", "xlsx", "xls", "tsv"],
            key="raw_hist_upload",
            label_visibility="collapsed",
        )
        if raw_file:
            try:
                raw_df = read_table(raw_file)
                set_state("forecast_raw", raw_df)
                st.success(f"Data dimuat: {len(raw_df)} baris")
            except Exception as e:
                st.error(f"Gagal membaca: {e}")

        raw_df  = get_state("forecast_raw")
        has_raw = isinstance(raw_df, pd.DataFrame) and not raw_df.empty
        if has_raw:
            st.dataframe(raw_df.head(50), use_container_width=True, hide_index=True)

        st.markdown("<div class='section-title'>Parameter Forecast</div>", unsafe_allow_html=True)
        fc1, fc2 = st.columns(2)
        with fc1:
            method  = st.selectbox("Metode", ["Auto", "Prophet", "Croston", "Moving Average"])
        with fc2:
            horizon = st.number_input("Horizon (bulan)", 3, 36, 12, 1)

        if st.button("Jalankan Forecast", type="primary", disabled=not has_raw):
            try:
                from modules.forecast_engine import run_forecast
                with st.spinner("Memproses..."):
                    fc_result = run_forecast(raw_df, horizon_months=horizon, method=method)
                set_state("forecast_output", fc_result)
                st.success(f"Forecast selesai: {len(fc_result)} baris")
            except NotImplementedError:
                st.info("Modul forecast sedang dalam pengembangan. Upload hasil forecast di tab Input Simulasi DES.")
            except Exception as e:
                st.error(f"Error: {e}")

        fc_out = get_state("forecast_output")
        if isinstance(fc_out, pd.DataFrame) and not fc_out.empty:
            st.markdown("<div class='section-title'>Hasil Forecast</div>", unsafe_allow_html=True)
            st.dataframe(fc_out.head(100), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — INPUT SIMULASI DES (Asil)
    # ══════════════════════════════════════════════════════════════════════════
    with tab2:
        st.markdown("<div class='section-title'>Output Forecast</div>", unsafe_allow_html=True)
        st.caption("Gunakan hasil forecast dari tab Forecasting, atau upload file forecast secara langsung.")

        fc_df  = get_state("forecast_output")
        has_fc = isinstance(fc_df, pd.DataFrame) and not fc_df.empty

        # Coba auto-load default
        if not has_fc:
            _def = _load_default_forecast()
            if _def is not None:
                set_state("forecast_output", _def)
                fc_df  = _def
                has_fc = True

        if has_fc:
            st.success(f"Output forecast terdeteksi — {len(fc_df)} baris forecast")
        else:
            fc_file = st.file_uploader(
                "Upload File Forecast", type=["csv", "xlsx"],
                key="fc_bridge", label_visibility="collapsed",
            )
            if fc_file:
                try:
                    fc_df  = read_table(fc_file)
                    set_state("forecast_output", fc_df)
                    has_fc = not fc_df.empty
                    if has_fc:
                        st.success(f"Forecast dimuat: {len(fc_df)} baris")
                except Exception as e:
                    st.error(f"Gagal membaca: {e}")

        if has_fc:
            # Sub-tab preview vs DES builder
            sub_a, sub_b = st.tabs(["Forecast", "SKU Stats"])

            with sub_a:
                # Filter SKU
                sku_col_fc = next((c for c in ["sku","SKU","SkuId"] if c in fc_df.columns), None)
                if sku_col_fc:
                    all_skus = sorted(fc_df[sku_col_fc].dropna().unique().tolist())
                    sel_skus = st.multiselect("Filter SKU", all_skus, default=all_skus[:5], key="fc_sku_filter")
                    show_df  = fc_df[fc_df[sku_col_fc].isin(sel_skus)] if sel_skus else fc_df
                else:
                    show_df = fc_df
                st.dataframe(show_df.head(200), use_container_width=True, hide_index=True)

            with sub_b:
                sc_df = _load_default_sku_class()
                if sc_df is not None:
                    st.dataframe(sc_df, use_container_width=True, hide_index=True)
                else:
                    st.info("File klasifikasi SKU tidak ditemukan.")

            # ── Master SKU & Generator ────────────────────────────────────────
            st.markdown("<div class='section-title'>Master SKU</div>", unsafe_allow_html=True)
            st.caption("Data master SKU berisi informasi kecepatan produksi dan parameter lini.")

            sku_file = st.file_uploader(
                "Upload Master SKU", type=["csv", "xlsx", "xls"],
                key="sku_bridge", label_visibility="collapsed",
            )
            sku_df = pd.DataFrame()
            if sku_file:
                try:
                    sku_df = read_table(sku_file)
                    st.success(f"Master SKU dimuat: {len(sku_df)} baris")
                except Exception as e:
                    st.error(f"Gagal membaca: {e}")

            if not sku_df.empty:
                st.markdown("<div class='section-title'>Parameter</div>", unsafe_allow_html=True)
                p1, p2 = st.columns(2)
                with p1:
                    adj = st.slider("Adjustment forecast (%)", -50.0, 50.0, 0.0, 0.5,
                                    help="Koreksi volume forecast sebelum masuk simulasi.")
                with p2:
                    qty_def = st.number_input("Qty default per SKU-bulan", 1, 100, 1)

                if st.button("Generate ForecastInput DES", type="primary"):
                    try:
                        with st.spinner("Membuat input simulasi..."):
                            result = build_forecast_input_des(fc_df, sku_df,
                                                              adjustment_pct=adj,
                                                              qty_default=qty_def)
                        if result is not None and not result.empty:
                            set_state("forecast_input_des", result)
                            st.success(f"ForecastInput DES berhasil: {len(result)} baris")

                            sku_c = next((c for c in ["SkuId","sku"] if c in result.columns), result.columns[0])
                            ft_c  = next((c for c in ["ForecastTon","forecast"] if c in result.columns), None)
                            m1, m2, m3, m4 = st.columns(4)
                            m1.metric("Jumlah SKU", result[sku_c].nunique())
                            n_mon = result.get("MonthIndex", pd.Series()).nunique() or 1
                            m2.metric("Jumlah Bulan", n_mon)
                            if ft_c:
                                m3.metric("Total Forecast", f"{result[ft_c].sum():,.1f} ton")
                                m4.metric("Rata-rata/Bulan", f"{result[ft_c].sum()/n_mon:,.1f} ton")

                            st.markdown("<div class='section-title'>Preview</div>", unsafe_allow_html=True)
                            st.dataframe(result.head(50), use_container_width=True, hide_index=True)
                            st.download_button("Unduh ForecastInput DES",
                                data=result.to_csv(index=False).encode(),
                                file_name="ForecastInput_DES.csv", mime="text/csv")
                        else:
                            st.error("Hasil kosong. Periksa format kolom forecast dan master SKU.")
                    except Exception as e:
                        st.error(f"Error: {e}")
                        import traceback; st.code(traceback.format_exc())
            else:
                st.info("Upload master SKU untuk melanjutkan ke generator ForecastInput DES.")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — VISUALISASI DEMAND (Gibran)
    # ══════════════════════════════════════════════════════════════════════════
    with tab3:
        # Prioritas: session → default file → upload
        viz_df = get_state("forecast_output")
        if not isinstance(viz_df, pd.DataFrame) or viz_df.empty:
            viz_df = _load_default_forecast()
            if viz_df is not None:
                set_state("forecast_output", viz_df)

        has_viz = isinstance(viz_df, pd.DataFrame) and not viz_df.empty

        if not has_viz:
            st.markdown("<div class='section-title'>Upload Data</div>", unsafe_allow_html=True)
            viz_file = st.file_uploader("Upload Data Demand / Forecast",
                                         type=["csv", "xlsx"], key="viz_up",
                                         label_visibility="collapsed")
            if viz_file:
                try:
                    viz_df  = read_table(viz_file)
                    has_viz = not viz_df.empty
                    if has_viz:
                        set_state("forecast_output", viz_df)
                except Exception as e:
                    st.error(f"Gagal membaca: {e}")

        if not has_viz:
            st.info("Upload data forecast untuk menampilkan visualisasi.")
            st.stop()

        # ── Detect columns ────────────────────────────────────────────────────
        date_col = next((c for c in ["date","ds","Date"] if c in viz_df.columns), None)
        sku_col  = next((c for c in ["sku","SKU","SkuId"] if c in viz_df.columns), None)
        val_col  = next((c for c in ["forecast","ForecastTon","demand","value"] if c in viz_df.columns), None)
        desc_col = next((c for c in ["description","DescriptionForecast","item_name"] if c in viz_df.columns), None)
        mape_col = next((c for c in ["mape_backtest","mape","MAPE"] if c in viz_df.columns), None)

        if date_col: viz_df[date_col] = pd.to_datetime(viz_df[date_col], errors="coerce")
        if val_col:  viz_df[val_col]  = pd.to_numeric(viz_df[val_col],  errors="coerce").fillna(0)

        # Packaging
        label_src = desc_col or sku_col
        if label_src:
            viz_df["_pkg"] = viz_df[label_src].apply(_detect_pkg)
        else:
            viz_df["_pkg"] = "SSS"

        # ── Filter hanya SKU aktif (total > 0) ───────────────────────────────
        if sku_col and val_col:
            sku_total = viz_df.groupby(sku_col)[val_col].sum()
            active_skus = sku_total[sku_total > 0].index
            viz_df = viz_df[viz_df[sku_col].isin(active_skus)].copy()

        # ── KPI Cards ─────────────────────────────────────────────────────────
        st.markdown("<div class='section-title'>Ringkasan</div>", unsafe_allow_html=True)

        n_sku   = viz_df[sku_col].nunique()  if sku_col  else "-"
        n_month = viz_df[date_col].nunique() if date_col else 1
        avg_m   = viz_df[val_col].sum() / max(n_month, 1) if val_col else 0

        period_str = ""
        if date_col:
            mn, mx = viz_df[date_col].min(), viz_df[date_col].max()
            if pd.notna(mn) and pd.notna(mx):
                period_str = f"{mn.strftime('%b %Y')} – {mx.strftime('%b %Y')}"

        # Avg MAPE: per SKU (ambil nilai pertama per SKU supaya tidak double-count)
        avg_mape = None
        if mape_col and sku_col:
            avg_mape = viz_df.groupby(sku_col)[mape_col].first().mean()
        elif mape_col:
            avg_mape = viz_df[mape_col].mean()

        k1, k2, k3, k4 = st.columns(4)
        for col_obj, lbl, val in [
            (k1, "SKU Aktif",     str(n_sku)),
            (k2, "Volume/Bulan",  f"{avg_m:,.1f} ton" if val_col else "-"),
            (k3, "Periode",       period_str or "-"),
            (k4, "Akurasi Model", f"{avg_mape:.1f}%" if avg_mape is not None else "N/A"),
        ]:
            col_obj.markdown(
                f'<div class="kpi-box">'
                f'<div class="kpi-label">{lbl}</div>'
                f'<div class="kpi-value">{val}</div></div>',
                unsafe_allow_html=True,
            )

        # Warning MAPE tinggi
        if avg_mape and avg_mape > 30 and sku_col and mape_col:
            n_hi = (viz_df.groupby(sku_col)[mape_col].first() > 30).sum()
            if n_hi:
                st.markdown(
                    f'<div class="warn-box">{n_hi} SKU memiliki MAPE > 30% — gunakan angka dengan hati-hati.</div>',
                    unsafe_allow_html=True,
                )

        if not val_col or not sku_col:
            st.dataframe(viz_df, use_container_width=True, hide_index=True)
            return

        # ── Row 1: Volume per SKU + Pie Kemasan ──────────────────────────────
        st.markdown("<div class='section-title'>Volume per SKU & Proporsi Kemasan</div>", unsafe_allow_html=True)
        ch1, ch2 = st.columns([3, 2])

        with ch1:
            if date_col:
                months  = sorted(viz_df[date_col].dropna().unique())
                sel_m   = st.selectbox("Tampilkan untuk:", months,
                                       format_func=lambda x: pd.Timestamp(x).strftime("%b %Y"),
                                       key="sel_month_viz")
                m_df = viz_df[viz_df[date_col] == sel_m].copy()
                m_df = m_df.sort_values(val_col, ascending=True).tail(20)
            else:
                m_df = viz_df.groupby([label_src or sku_col, "_pkg"])[val_col].sum().reset_index() \
                             .sort_values(val_col).tail(20)

            fig_b = px.bar(
                m_df, y=label_src or sku_col, x=val_col, color="_pkg",
                orientation="h", color_discrete_map=PKG_COLORS,
                height=420, labels={val_col: "ton", "_pkg": "PACKAGING_NORM"},
            )
            fig_b.update_layout(**_chart_layout(yaxis_title="", xaxis_title=f"ton ({pd.Timestamp(sel_m).strftime('%b %Y') if date_col else ''})"))
            st.plotly_chart(fig_b, use_container_width=True)

        with ch2:
            # Donut chart proporsi kemasan per bulan terpilih
            if date_col:
                pie_src = viz_df[viz_df[date_col] == sel_m] if date_col else viz_df
            else:
                pie_src = viz_df
            pkg_sum = pie_src.groupby("_pkg")[val_col].sum().reset_index()
            pkg_sum.columns = ["Kemasan", "Volume"]
            pkg_sum = pkg_sum[pkg_sum["Volume"] > 0]

            fig_pie = go.Figure(data=[go.Pie(
                labels=pkg_sum["Kemasan"],
                values=pkg_sum["Volume"],
                hole=0.45,
                marker_colors=[PKG_COLORS.get(k, "#EBF4F6") for k in pkg_sum["Kemasan"]],
                textinfo="percent+label",
                textfont_size=12,
            )])
            fig_pie.update_layout(
                plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG,
                font_color=FONT_COLOR,
                showlegend=False,
                margin=dict(l=10, r=10, t=30, b=10),
                height=420,
                title=dict(text=f"Kemasan<br>{pd.Timestamp(sel_m).strftime('%b %Y') if date_col else 'All'}", x=0.5, font=dict(size=13)),
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        # ── Row 2: Top 10 SKU ─────────────────────────────────────────────────
        st.markdown("<div class='section-title'>Top 10 SKU — Rata-rata per Bulan</div>", unsafe_allow_html=True)
        top10 = viz_df.groupby([label_src or sku_col, "_pkg"])[val_col].mean().reset_index()
        top10.columns = ["nama", "kemasan", "avg"]
        top10 = top10.sort_values("avg").tail(10)

        fig_t = px.bar(
            top10, y="nama", x="avg", color="kemasan", orientation="h",
            color_discrete_map=PKG_COLORS, height=360,
            labels={"avg": "avg ton/bln", "kemasan": "PACKAGING_NORM"},
        )
        fig_t.update_layout(**_chart_layout(yaxis_title="", xaxis_title="avg ton/bln"))
        st.plotly_chart(fig_t, use_container_width=True)

        # ── Row 3: Tren Bulanan per Kemasan ──────────────────────────────────
        if date_col:
            st.markdown("<div class='section-title'>Tren Bulanan per Tipe Kemasan</div>", unsafe_allow_html=True)
            trend = viz_df.groupby([date_col, "_pkg"])[val_col].sum().reset_index()
            fig_l = px.line(
                trend, x=date_col, y=val_col, color="_pkg", markers=True,
                color_discrete_map=PKG_COLORS, height=300,
                labels={val_col: "ton", "_pkg": "Kemasan"},
            )
            fig_l.update_layout(**_chart_layout(xaxis_title="", yaxis_title="ton"))
            st.plotly_chart(fig_l, use_container_width=True)
