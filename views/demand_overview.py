import pandas as pd
import streamlit as st
import plotly.express as px

from modules.theme import hero, note, warning
from modules.session import set_state, get_state
from modules.io_utils import read_table, first_existing_file
from modules.des_input_builder import build_forecast_input_des
from modules.forecast_engine import run_forecast


def _load_default_from_folder(folder):
    f = first_existing_file(folder)
    if f:
        return read_table(f), str(f)
    return pd.DataFrame(), None


def render():
    hero("Demand Overview & Forecasting", "Tempat modul forecasting berjalan, lalu hasilnya dikonversi menjadi ForecastInput DES untuk capacity simulation.")

    note(
        "<b>Status base:</b> UI forecasting sudah disiapkan, tetapi logic forecasting asli masih perlu diisi oleh PIC Forecasting di <code>modules/forecast_engine.py</code>. "
        "Bagian converter forecast + master SKU → ForecastInput DES sudah aktif."
    )

    tab_forecast, tab_converter = st.tabs(["1 · Forecasting", "2 · Konversi ke DES"])

    with tab_forecast:
        # Check if Ubay's CSV outputs are available
        from modules.forecast_engine import load_ubay_outputs
        _ubay = load_ubay_outputs()
        if _ubay.get("forecast") is not None:
            st.success(f"✓ Output forecast Ubay terdeteksi — {len(_ubay['forecast'])} baris forecast")
            _uf1, _uf2 = st.tabs(["📈 Forecast", "📊 SKU Stats"])
            with _uf1:
                _fc_df = _ubay["forecast"]
                date_col = next((c for c in ["date","ds"] if c in _fc_df.columns), _fc_df.columns[0])
                sku_col  = next((c for c in ["sku","SKU","SkuId"] if c in _fc_df.columns), None)
                if sku_col:
                    _skus = sorted(_fc_df[sku_col].astype(str).unique())
                    _sel = st.multiselect("Filter SKU", _skus, default=_skus[:5] if len(_skus)>5 else _skus, key="ubay_sku_filter")
                    if _sel: _fc_df = _fc_df[_fc_df[sku_col].astype(str).isin(_sel)]
                st.dataframe(_fc_df.head(300), use_container_width=True, hide_index=True)
            with _uf2:
                if _ubay.get("sku_stats") is not None:
                    st.dataframe(_ubay["sku_stats"], use_container_width=True, hide_index=True)
            st.markdown("---")
        st.markdown("<div class='section-title'>Forecasting System</div>", unsafe_allow_html=True)
        warning(
            "Bagian ini sengaja disiapkan sebagai tempat sistem forecast, bukan hanya upload hasil forecast. "
            "PIC Forecasting perlu mengisi function <code>run_forecast()</code> di <code>modules/forecast_engine.py</code>."
        )
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            raw_file = st.file_uploader("Upload raw historical demand untuk forecasting", type=["csv", "xlsx", "xls"], key="raw_forecast_upload")
        with c2:
            method = st.selectbox("Forecast method", ["Auto", "Prophet", "Croston", "Manual/Existing Output"])
        with c3:
            horizon = st.number_input("Horizon bulan", min_value=1, max_value=36, value=12, step=1)

        if raw_file is not None:
            try:
                raw_df = read_table(raw_file)
                set_state("forecast_raw", raw_df)
                st.success(f"Raw data terbaca: {len(raw_df):,} baris.")
                st.dataframe(raw_df.head(200), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error("Gagal membaca raw data.")
                st.exception(e)

        if st.button("Jalankan Forecast"):
            raw_df = get_state("forecast_raw")
            if raw_df is None or raw_df.empty:
                st.error("Upload raw historical demand terlebih dahulu.")
            else:
                try:
                    fc = run_forecast(raw_df, horizon_months=int(horizon), method=method)
                    set_state("forecast_output", fc)
                    st.success("Forecast berhasil dibuat dan disimpan ke session.")
                    st.dataframe(fc, use_container_width=True, hide_index=True)
                except NotImplementedError as e:
                    st.warning(str(e))
                    st.info("Sementara itu, gunakan tab 'Forecast → ForecastInput DES' untuk upload output forecast yang sudah jadi.")
                except Exception as e:
                    st.error("Forecasting pipeline error.")
                    st.exception(e)

    with tab_converter:
        st.markdown("<div class='section-title'>Forecast + Master SKU → ForecastInput DES</div>", unsafe_allow_html=True)
        note(
            "Masukkan output forecast minimal kolom <b>sku, date, forecast</b>, lalu masukkan master SKU capacity. "
            "Master SKU bisa diletakkan di folder <code>data/master_sku_here/</code>."
        )

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Forecast output**")
            f_default, f_path = _load_default_from_folder("data/forecast_module_here")
            if f_path:
                st.caption(f"Ditemukan file default: {f_path}")
            f_upload = st.file_uploader("Upload forecast output", type=["csv", "xlsx", "xls"], key="forecast_output_upload")
            if f_upload is not None:
                forecast_df = read_table(f_upload)
            elif not get_state("forecast_output").empty:
                forecast_df = get_state("forecast_output")
                st.caption("Menggunakan hasil forecast dari session.")
            else:
                forecast_df = f_default
        with c2:
            st.markdown("**Master SKU capacity**")
            m_default, m_path = _load_default_from_folder("data/master_sku_here")
            if m_path:
                st.caption(f"Ditemukan file default: {m_path}")
            m_upload = st.file_uploader("Upload master SKU capacity", type=["csv", "xlsx", "xls"], key="master_upload")
            master_df = read_table(m_upload) if m_upload is not None else m_default

        if forecast_df is not None and not forecast_df.empty:
            st.markdown("**Preview forecast output**")
            st.dataframe(forecast_df.head(100), use_container_width=True, hide_index=True)
        else:
            warning("Forecast output belum tersedia. PIC forecast dapat menaruh file di <code>data/forecast_module_here/</code> atau upload di sini.")

        if master_df is not None and not master_df.empty:
            st.markdown("**Preview master SKU capacity**")
            st.dataframe(master_df.head(100), use_container_width=True, hide_index=True)
        else:
            warning("Master SKU belum tersedia. Masukkan file master ke <code>data/master_sku_here/</code> atau upload di sini.")

        ca, cb = st.columns(2)
        with ca:
            adj = st.slider("Adjustment forecast untuk input DES (%)", -30.0, 30.0, 0.0, 0.5)
        with cb:
            qty = st.number_input("Qty default", min_value=1, max_value=100, value=1, step=1)

        if st.button("Generate ForecastInput DES"):
            try:
                if forecast_df is None or forecast_df.empty:
                    st.error("Forecast output belum tersedia.")
                    return
                if master_df is None or master_df.empty:
                    st.error("Master SKU capacity belum tersedia.")
                    return
                result = build_forecast_input_des(forecast_df, master_df, adjustment_pct=adj, qty_default=qty)
                set_state("forecast_output", forecast_df)
                set_state("master_sku", master_df)
                set_state("forecast_input_des", result)
                st.success(f"ForecastInput DES berhasil dibuat: {len(result):,} baris.")
                k1, k2, k3 = st.columns(3)
                k1.metric("SKU", result["SkuId"].nunique())
                k2.metric("Periode", result["MonthIndex"].nunique())
                k3.metric("Total Forecast", f"{result['ForecastTon'].sum():,.1f} ton")
                st.dataframe(result.head(500), use_container_width=True, hide_index=True)
                st.download_button("Download ForecastInput DES CSV", data=result.to_csv(index=False).encode("utf-8"), file_name="ForecastInput_DES_generated.csv", mime="text/csv")
            except Exception as e:
                st.error("Gagal membuat ForecastInput DES.")
                st.exception(e)
