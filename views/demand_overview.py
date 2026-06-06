"""
Demand Overview — 3 tabs:
  1. Forecasting System (Ubay) — input raw historical, run forecast
  2. Forecast → ForecastInput DES (Asil) — bridge ke capacity simulation
  3. Demand Overview (Gibran) — visualisasi demand/forecast
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


def render():
    hero("Demand Overview", "Forecasting, konversi ForecastInput DES, dan visualisasi demand.")

    tab_ubay, tab_asil, tab_gibran = st.tabs([
        "1 · Forecasting System",
        "2 · Forecast → ForecastInput DES",
        "3 · Demand Overview"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — UBAY: Upload raw historical → run forecast
    # ══════════════════════════════════════════════════════════════════════════
    with tab_ubay:
        st.markdown("<div class='section-title'>Input Raw Historical Demand</div>", unsafe_allow_html=True)
        st.caption("Upload data historis demand mentah. Sistem akan menjalankan pipeline forecasting (Prophet).")

        raw_file = st.file_uploader("Upload Raw Historical Demand",
            type=["csv","xlsx","xls","tsv"], key="raw_hist_upload")

        if raw_file:
            try:
                raw_df = read_table(raw_file)
                set_state("forecast_raw", raw_df)
                st.success(f"✓ Data historis dimuat: {len(raw_df)} baris, {len(raw_df.columns)} kolom")
            except Exception as e:
                st.error(f"Gagal membaca file: {e}")

        raw_df = get_state("forecast_raw")
        has_raw = isinstance(raw_df, pd.DataFrame) and not raw_df.empty

        if has_raw:
            st.dataframe(raw_df.head(50), use_container_width=True, hide_index=True)

        # Forecast parameters
        st.markdown("<div class='section-title'>Forecasting Pipeline</div>", unsafe_allow_html=True)
        fp1, fp2 = st.columns(2)
        with fp1:
            method = st.selectbox("Forecast Method", ["Auto", "Prophet", "Croston", "Moving Average"])
        with fp2:
            horizon = st.number_input("Horizon (bulan)", 3, 36, 12, 1)

        if st.button("Run Forecasting Pipeline", type="primary", disabled=not has_raw):
            if not has_raw:
                st.error("Upload data historis terlebih dahulu.")
            else:
                try:
                    from modules.forecast_engine import run_forecast
                    with st.spinner("Menjalankan forecast..."):
                        fc_result = run_forecast(raw_df, horizon_months=horizon, method=method)
                    set_state("forecast_output", fc_result)
                    st.success(f"✓ Forecast selesai: {len(fc_result)} baris")
                except NotImplementedError as e:
                    st.warning(f"⚠ {e}")
                    st.info("Upload hasil forecast CSV yang sudah jadi di tab 'Demand Overview' sebagai alternatif.")
                except Exception as e:
                    st.error(f"Error: {e}")

        # Show forecast output if available
        fc_out = get_state("forecast_output")
        if isinstance(fc_out, pd.DataFrame) and not fc_out.empty:
            st.markdown("---")
            st.markdown("<div class='section-title'>Hasil Forecast</div>", unsafe_allow_html=True)
            st.dataframe(fc_out.head(100), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — ASIL: Forecast → ForecastInput DES
    # ══════════════════════════════════════════════════════════════════════════
    with tab_asil:
        st.markdown("<div class='section-title'>Konversi Forecast → ForecastInput DES</div>",
                    unsafe_allow_html=True)
        st.caption("Gabungkan output forecast dengan master SKU untuk menghasilkan input simulasi DES.")

        # Forecast source: from Tab 1 or upload
        fc_df = get_state("forecast_output")
        has_fc = isinstance(fc_df, pd.DataFrame) and not fc_df.empty

        if has_fc:
            st.success(f"✓ Menggunakan forecast dari Tab 1: {len(fc_df)} baris")
        else:
            st.info("Forecast belum tersedia dari Tab 1. Upload file output forecast di bawah.")
            fc_file = st.file_uploader("Upload Output Forecast CSV", type=["csv","xlsx"], key="fc_bridge_upload")
            if fc_file:
                fc_df = read_table(fc_file)
                set_state("forecast_output", fc_df)
                has_fc = not fc_df.empty
                if has_fc:
                    st.success(f"✓ Forecast dimuat: {len(fc_df)} baris")

        if not has_fc:
            st.stop()

        # Master SKU
        st.markdown("<div class='section-title'>Master SKU</div>", unsafe_allow_html=True)
        default_sku = first_existing_file("data/master_sku")
        sku_file = st.file_uploader("Upload Master SKU", type=["csv","xlsx","xls"], key="sku_bridge")
        sku_df = pd.DataFrame()
        if sku_file:
            sku_df = read_table(sku_file)
        elif default_sku:
            sku_df = read_table(default_sku)
            st.caption(f"Default: {default_sku}")

        if sku_df.empty:
            st.info("Upload master SKU untuk melanjutkan.")
            st.stop()

        # Parameters
        st.markdown("<div class='section-title'>Parameter</div>", unsafe_allow_html=True)
        p1, p2 = st.columns(2)
        with p1:
            adj = st.slider("Adjustment forecast (%)", -50.0, 50.0, 0.0, 0.5)
        with p2:
            qty_def = st.number_input("Qty default per SKU-bulan", 1, 100, 1)

        if st.button("Generate ForecastInput DES", type="primary"):
            try:
                with st.spinner("Membuat ForecastInput DES..."):
                    result = build_forecast_input_des(fc_df, sku_df, adjustment_pct=adj, qty_default=qty_def)
                if result is not None and not result.empty:
                    set_state("forecast_input_des", result)
                    st.success(f"✓ ForecastInput DES: {len(result)} baris")
                    # Metrics
                    sku_c = next((c for c in ["SkuId","sku"] if c in result.columns), result.columns[0])
                    ft_c  = next((c for c in ["ForecastTon","forecast"] if c in result.columns), None)
                    m1,m2,m3,m4 = st.columns(4)
                    m1.metric("Jumlah SKU", result[sku_c].nunique())
                    m2.metric("Jumlah Bulan", result.get("MonthIndex",pd.Series()).nunique() or "-")
                    if ft_c:
                        m3.metric("Total Forecast", f"{result[ft_c].sum():,.1f} ton")
                        m4.metric("Rata-rata/Bulan", f"{result[ft_c].sum()/max(result.get('MonthIndex',pd.Series([1])).nunique(),1):,.1f} ton")
                    st.dataframe(result.head(50), use_container_width=True, hide_index=True)
                    st.download_button("Download ForecastInput DES CSV",
                        data=result.to_csv(index=False).encode("utf-8"),
                        file_name="ForecastInput_DES.csv", mime="text/csv")
            except Exception as e:
                st.error(f"Error: {e}")
                import traceback; st.code(traceback.format_exc())

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — GIBRAN: Demand Overview visualization
    # ══════════════════════════════════════════════════════════════════════════
    with tab_gibran:
        st.markdown("<div class='section-title'>Upload Data Demand / Forecast</div>", unsafe_allow_html=True)
        st.caption("Upload file demand/forecast untuk divisualisasikan. Bisa dari output forecast Ubay atau sumber lain.")

        # Use forecast_output if available, or allow upload
        viz_df = get_state("forecast_output")
        has_viz = isinstance(viz_df, pd.DataFrame) and not viz_df.empty

        if has_viz:
            st.success(f"✓ Menggunakan data forecast yang sudah dimuat ({len(viz_df)} baris)")
            use_existing = st.checkbox("Gunakan data ini", value=True, key="use_existing_fc")
            if not use_existing:
                has_viz = False

        if not has_viz:
            viz_file = st.file_uploader("Upload Forecast/Demand CSV", type=["csv","xlsx"], key="viz_upload")
            if viz_file:
                viz_df = read_table(viz_file)
                has_viz = not viz_df.empty

        if not has_viz:
            st.info("Upload file forecast/demand untuk menampilkan visualisasi.", icon="📂")
            st.stop()

        # ── Identify columns ──────────────────────────────────────────────────
        date_col = next((c for c in ["date","ds","Date","tanggal"] if c in viz_df.columns), None)
        sku_col  = next((c for c in ["sku","SKU","SkuId","sku_id","name"] if c in viz_df.columns), None)
        val_col  = next((c for c in ["forecast","ForecastTon","demand","value","ton"] if c in viz_df.columns), None)
        desc_col = next((c for c in ["description","deskripsi","itemname","item_name","DescriptionForecast"] if c in viz_df.columns), None)
        mape_col = next((c for c in ["mape_backtest","mape","MAPE"] if c in viz_df.columns), None)
        pkg_col  = next((c for c in ["PACKAGING_NORM","port_type","kemasan","packaging"] if c in viz_df.columns), None)

        if date_col:
            viz_df[date_col] = pd.to_datetime(viz_df[date_col], errors="coerce")
        if val_col:
            viz_df[val_col] = pd.to_numeric(viz_df[val_col], errors="coerce").fillna(0)

        # ── KPI Row ───────────────────────────────────────────────────────────
        st.markdown("<div class='section-title'>Ringkasan Forecast</div>", unsafe_allow_html=True)

        n_sku = viz_df[sku_col].nunique() if sku_col else 0
        total_vol = viz_df[val_col].sum() if val_col else 0
        n_month = viz_df[date_col].nunique() if date_col else 1
        avg_monthly = total_vol / max(n_month, 1)
        avg_mape = viz_df[mape_col].mean() if mape_col and mape_col in viz_df.columns else None

        period_str = ""
        if date_col:
            dmin = viz_df[date_col].min()
            dmax = viz_df[date_col].max()
            if pd.notna(dmin) and pd.notna(dmax):
                period_str = f"{dmin.strftime('%b %Y')} – {dmax.strftime('%b %Y')}"

        kc1,kc2,kc3,kc4 = st.columns(4)
        kc1.markdown(f'''<div class="kpi-box"><div class="kpi-label">SKU AKTIF</div>
            <div class="kpi-value">{n_sku}</div></div>''', unsafe_allow_html=True)
        kc2.markdown(f'''<div class="kpi-box"><div class="kpi-label">VOLUME / BULAN</div>
            <div class="kpi-value">{avg_monthly:,.1f} ton</div>
            <div style="font-size:.72rem;color:#8b949e;">rata-rata</div></div>''', unsafe_allow_html=True)
        kc3.markdown(f'''<div class="kpi-box"><div class="kpi-label">PERIODE</div>
            <div class="kpi-value" style="font-size:1rem;">{period_str or "-"}</div></div>''', unsafe_allow_html=True)
        kc4.markdown(f'''<div class="kpi-box"><div class="kpi-label">AKURASI MODEL</div>
            <div class="kpi-value" style="color:{"#3fb950" if avg_mape and avg_mape<30 else "#d29922"}">{f"{avg_mape:.1f}%" if avg_mape else "N/A"}</div>
            <div style="font-size:.72rem;color:#8b949e;">avg MAPE</div></div>''', unsafe_allow_html=True)

        # MAPE warning
        if mape_col and avg_mape and avg_mape > 30:
            high_mape_count = (viz_df.groupby(sku_col)[mape_col].first() > 30).sum() if sku_col else 0
            if high_mape_count > 0:
                st.warning(f"{high_mape_count} SKU memiliki MAPE > 30% — gunakan angka dengan hati-hati.", icon="⚠️")

        if not val_col or not sku_col:
            st.warning("Kolom `sku` dan `forecast`/`demand` tidak ditemukan — visualisasi terbatas.")
            st.dataframe(viz_df, use_container_width=True, hide_index=True)
            st.stop()

        # ── Charts ────────────────────────────────────────────────────────────
        # Detect packaging if possible (from description or separate column)
        if not pkg_col and desc_col:
            def _detect_pkg(desc):
                d = str(desc).upper()
                if "STICKPACK" in d or "STICK" in d: return "STICKPACK"
                if "BIB" in d or "BAG IN BOX" in d: return "BIB"
                return "SSS"
            viz_df["_pkg"] = viz_df[desc_col].apply(_detect_pkg)
            pkg_col = "_pkg"
        elif not pkg_col:
            viz_df["_pkg"] = "SSS"
            pkg_col = "_pkg"

        # Volume per SKU (top SKUs by avg monthly)
        sku_agg = viz_df.groupby([sku_col, pkg_col]).agg(
            total=(val_col, "sum"),
            avg_monthly=(val_col, "mean")
        ).reset_index().sort_values("avg_monthly", ascending=False)

        ch1, ch2 = st.columns(2)

        with ch1:
            st.markdown("<div class='section-title'>Volume per SKU & Kemasan</div>", unsafe_allow_html=True)
            if date_col:
                months = sorted(viz_df[date_col].dropna().unique())
                sel_month = st.selectbox("Tampilkan untuk:", [m for m in months],
                    format_func=lambda x: pd.Timestamp(x).strftime("%b %Y"), key="vol_month")
                month_df = viz_df[viz_df[date_col]==sel_month].sort_values(val_col, ascending=True).tail(15)
            else:
                month_df = sku_agg.sort_values("total", ascending=True).tail(15)

            fig_bar = px.bar(month_df, y=desc_col or sku_col, x=val_col,
                            color=pkg_col, orientation="h",
                            color_discrete_map={"SSS":"#58a6ff","BIB":"#3fb950","STICKPACK":"#d29922"},
                            height=400)
            fig_bar.update_layout(plot_bgcolor="#0d1117",paper_bgcolor="#0d1117",
                font_color="#c9d1d9",yaxis_title="",xaxis_title=f"ton ({pd.Timestamp(sel_month).strftime('%b %Y') if date_col else 'total'})",
                legend=dict(orientation="h",y=-0.15))
            st.plotly_chart(fig_bar, use_container_width=True)

        with ch2:
            st.markdown("<div class='section-title'>Top 10 SKU — Rata-rata per Bulan</div>", unsafe_allow_html=True)
            top10 = sku_agg.head(10).sort_values("avg_monthly", ascending=True)
            fig_top = px.bar(top10, y=desc_col or sku_col if (desc_col or sku_col) in top10.columns else sku_agg.columns[0],
                            x="avg_monthly", color=pkg_col, orientation="h",
                            color_discrete_map={"SSS":"#58a6ff","BIB":"#3fb950","STICKPACK":"#d29922"},
                            height=400)
            fig_top.update_layout(plot_bgcolor="#0d1117",paper_bgcolor="#0d1117",
                font_color="#c9d1d9",yaxis_title="",xaxis_title="avg ton/bln",
                legend=dict(orientation="h",y=-0.15))
            st.plotly_chart(fig_top, use_container_width=True)

        # Trend line by packaging type
        if date_col:
            st.markdown("<div class='section-title'>Tren Bulanan per Tipe Kemasan</div>", unsafe_allow_html=True)
            trend = viz_df.groupby([date_col, pkg_col])[val_col].sum().reset_index()
            fig_trend = px.line(trend, x=date_col, y=val_col, color=pkg_col,
                              color_discrete_map={"SSS":"#58a6ff","BIB":"#3fb950","STICKPACK":"#d29922"},
                              markers=True, height=300)
            fig_trend.update_layout(plot_bgcolor="#0d1117",paper_bgcolor="#0d1117",
                font_color="#c9d1d9",xaxis_title="",yaxis_title="ton",
                legend=dict(orientation="h",y=-0.2))
            st.plotly_chart(fig_trend, use_container_width=True)

        # Packaging proportion (pie/donut)
        pkg_total = viz_df.groupby(pkg_col)[val_col].sum().reset_index()
        fig_pie = px.pie(pkg_total, values=val_col, names=pkg_col, hole=0.4,
                        color=pkg_col,
                        color_discrete_map={"SSS":"#58a6ff","BIB":"#3fb950","STICKPACK":"#d29922"})
        fig_pie.update_layout(plot_bgcolor="#0d1117",paper_bgcolor="#0d1117",
            font_color="#c9d1d9",height=280)
        st.plotly_chart(fig_pie, use_container_width=True)
