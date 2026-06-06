import streamlit as st
import pandas as pd
import numpy as np
import io
import json
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
from modules.session import get, set_
from modules.financial_calc import (compute_financial, capex_multiline,
    capex_stickpack_line, capex_new_line, DEFAULT_PARAMS, MACHINES)
from modules.data_loader import load_master_sku

def render():
    """pages/4_coman_analysis.py — Perencanaan Produksi  [v2025-05-25d]"""
    import streamlit as st
    import pandas as pd
    import numpy as np
    import plotly.graph_objects as go
    import io, sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from modules.data_loader    import load_master_sku
    from modules.session        import get, set_, upload_widget
    from modules.financial_calc import (compute_financial, capex_stickpack_line,
                                        capex_new_line, capex_multiline,
                                        MACHINES, DEFAULT_PARAMS, fmt_rp)

    # ── Constants ─────────────────────────────────────────────────────────────────
    COMAN_SAVINGS_PER_TON = 2_100_000  # Rp 2.1M/ton default
    UTIL_WARN = 65
    UTIL_OVERFLOW = 90  # threshold untuk rekomendasi upgrade lini existing

    # Calibrated throughput rates (ton/hr) from simulation + machine specs
    # Line B/G single (SSS+BIB): avg of B+G rates from S35 simulation
    RATE_SSBIB_SINGLE   = 0.897
    RATE_SSBIB_MULTI    = 0.897 * 3.0
    RATE_SSS_SINGLE     = 0.070         # per lane, calibrated from Line D (6-lane SSS)
    RATE_SSS_MULTI      = 0.070 * 6.0
    # Stickpack: Shiputec SPMP-480 spec — 480 sticks/min × 15g avg = 432 kg/hr = 0.432 ton/hr
    # Cross-validated: Line D SSS per-lane = 0.070 ton/hr (25g sachets)
    # Stickpack at 15g with 3× speed advantage = 0.070 × 3 × 15/25 = 0.126 × 4 lanes = ~0.45 ton/hr
    RATE_STICKPACK      = 0.432         # ton/hr (calibrated from SPMP-480 spec, 480 sticks/min × 15g)

    RATES = {
        ("SSS+BIB","single"):    RATE_SSBIB_SINGLE,
        ("SSS+BIB","multiline"): RATE_SSBIB_MULTI,
        ("SSS",    "single"):    RATE_SSS_SINGLE,
        ("SSS",    "multiline"): RATE_SSS_MULTI,
        ("STICKPACK","single"):  RATE_STICKPACK,
        ("STICKPACK","multiline"):RATE_STICKPACK,
    }
    TYPE_COMPAT = {
        "SSS+BIB":  ["SSS","BIB","PILLOW"],
        "SSS":      ["SSS"],
        "STICKPACK":["STICKPACK"],
    }
    ANNUAL_MANPOWER = 83_200_000   # Rp/org/tahun


    def _sf(x, d=0.0):
        v=str(x).strip().replace("%","").replace(" ","")
        if not v or v.lower() in ("nan","none","-",""): return float(d)
        if "," in v and "." not in v: v=v.replace(",",".")
        elif "," in v and "." in v:   v=v.replace(".","").replace(",",".")
        try: return float(v)
        except: return float(d)

    def classify_port(p):
        p=str(p).upper().strip()
        if "STICK" in p: return "STICKPACK"
        if "BIB" in p or "PILLOW" in p: return "BIB"
        return "SSS"

    def can_handle(line_type, pkg_class):
        return pkg_class in TYPE_COMPAT.get(line_type, [])

    def annual_cap_from_rate(line_type, config, eff_days=349, work_hrs=24, util_pct=65):
        rate = RATES.get((line_type, config), RATE_SSBIB_SINGLE)
        return rate * eff_days * work_hrs * (util_pct/100)

    def machine_cards_row(machine_list):
        if not machine_list: return
        cols=st.columns(min(len(machine_list),4))
        for i,(key,qty) in enumerate(machine_list):
            m=MACHINES.get(key,{}); col=cols[i%4]
            ct=m.get("capex",0)*qty; oy=m.get("capex",0)*m.get("opex_rate",0)*qty
            with col:
                found=False
                for ext in ("jpg","jpeg","png"):
                    p=Path(f"assets/machines/{key}.{ext}")
                    if p.exists():
                        try:
                            from PIL import Image as _P
                            pil=_P.open(p).convert("RGBA"); bg=_P.new("RGBA",pil.size,(22,27,34,255))
                            bg.paste(pil,mask=pil.split()[3]); buf=io.BytesIO()
                            bg.convert("RGB").save(buf,format="JPEG",quality=88); buf.seek(0)
                            st.image(buf,use_container_width=True); found=True; break
                        except: pass
                if not found:
                    st.markdown('<div style="height:65px;background:#1e2a3a;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:1.4rem;margin-bottom:5px;">⚙️</div>',unsafe_allow_html=True)
                st.markdown(
                    f'<div style="text-align:center;">'
                    f'<div style="font-size:0.7rem;font-weight:700;color:#f0f6fc;">{m.get("name","—")}{"" if qty==1 else f" ×{qty}"}</div>'
                    f'<div style="font-size:0.72rem;color:#58a6ff;">{fmt_rp(ct)}</div>'
                    f'<a href="{m.get("url","#")}" target="_blank" style="font-size:0.62rem;color:#58a6ff;">Detail ↗</a>'
                    f'</div>', unsafe_allow_html=True)


    # ── Sidebar ───────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### Data")
        upload_widget("master_sku","Master SKU",load_master_sku)
        st.markdown("---")
        st.markdown("### Horizon Proyeksi")
        proj_months=st.number_input("Proyeksi (bulan)",1,60,12)
        st.markdown("---")
        st.markdown("### Finansial")
        discount_rate=st.number_input("Discount Rate",0.05,0.30,DEFAULT_PARAMS["discount_rate"],0.01,format="%.2f")
        proj_years=st.number_input("Umur Proyek (thn)",3,15,int(DEFAULT_PARAMS["project_lifetime_year"]))
        pb_thresh=st.number_input("Batas Payback (thn)",1,7,int(DEFAULT_PARAMS["payback_threshold_year"]))
        real_factor=st.slider("Faktor Realisasi",0.5,1.0,DEFAULT_PARAMS["realization_factor"],0.05)
        st.markdown("---")
        st.markdown("### Utilisasi & Rekomendasi")
        util_reco_thresh = st.slider("Batas Utilisasi Rekomendasi (%)",70,100,90,5,
            help="Utilisasi ≥ nilai ini akan memicu rekomendasi upgrade lini")
        st.markdown("---")
        st.markdown("### Nilai Finansial per Ton")
        val_per_ton_internal = st.number_input(
            "Nilai Internal/Ton (Rp)",100_000,10_000_000,2_100_000,100_000,format="%d",
            help="Margin kontribusi per ton untuk produksi internal")
        COMAN_SAVINGS_PER_TON = 1_500_000  # Rp 6.5M - Rp 5M = Rp 1.5M (fixed)
        val_per_ton = val_per_ton_internal  # default
        st.caption("Penghematan produksi CO-MAN: Rp 1.500.000/ton")

    params={
        "discount_rate":discount_rate,"project_lifetime_year":proj_years,
        "payback_threshold_year":pb_thresh,"realization_factor":real_factor,
        "internal_value_per_ton":val_per_ton,
        "minimum_irr":DEFAULT_PARAMS["minimum_irr"],
        "minimum_roi":DEFAULT_PARAMS["minimum_roi"],
        "minimum_npv":DEFAULT_PARAMS["minimum_npv"],
    }


    # ── Header ────────────────────────────────────────────────────────────────────
    st.markdown('<p class="page-title">Production Allocation</p>',unsafe_allow_html=True)
    st.caption("Pemetaan volume ke kapasitas lini dan analisis kelayakan finansial.")

    # ── Latar Belakang Skenario ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Latar Belakang & Urgensi Investasi</div>',unsafe_allow_html=True)
    _SKENARIO_OPTS = {
        "CO-MAN Pull-back (Penarikan dari Maklon)": {
            "icon": "🏭",
            "desc": "Memindahkan produksi dari pihak maklon ke lini internal. "
                    "**Justifikasi:** penghematan biaya produksi (selisih maklon − internal), "
                    "peningkatan kendali kualitas, dan pengurangan ketergantungan pada pihak ketiga.",
            "benefit_basis": "Selisih biaya maklon vs internal per ton (Rp 6.5M − Rp 5M = Rp 1.5M/ton)",
        },
        "Pemenuhan Lonjakan Demand": {
            "icon": "📈",
            "desc": "Kapasitas existing tidak mencukupi untuk memenuhi pertumbuhan demand yang diproyeksikan. "
                    "**Justifikasi:** potensi kehilangan penjualan jika kapasitas tidak ditingkatkan.",
            "benefit_basis": "Nilai produksi tambahan per ton dari demand yang dipenuhi",
        },
        "Ekspansi Produk Baru (Stickpack/Format Baru)": {
            "icon": "✨",
            "desc": "Membuka lini produksi untuk format kemasan baru yang belum ada. "
                    "**Justifikasi:** penetrasi segmen pasar baru, diversifikasi portofolio produk.",
            "benefit_basis": "Revenue per ton dari produk baru yang dapat diproduksi",
        },
        "Optimasi Kapasitas & Utilisasi": {
            "icon": "⚙️",
            "desc": "Utilisasi lini existing sudah mendekati atau melebihi batas aman. "
                    "**Justifikasi:** mencegah risiko over-utilization yang berdampak pada kualitas dan kehandalan produksi.",
            "benefit_basis": "Nilai dari risk mitigation dan peningkatan kapasitas buffer",
        },
    }

    _skenario_key = st.selectbox(
        "Pilih skenario investasi:",
        list(_SKENARIO_OPTS.keys()),
        key="skenario_bg"
    )
    _sken = _SKENARIO_OPTS[_skenario_key]
    _bg1, _bg2 = st.columns([1, 2])
    with _bg1:
        st.markdown(f"### {_sken['icon']} {_skenario_key}")
        st.markdown(_sken["desc"])
    with _bg2:
        _trig_col1, _trig_col2 = st.columns(2)
        with _trig_col1:
            _trigger = st.text_area("Pemicu / Kondisi Spesifik", height=80,
                placeholder="Contoh: Forecast demand SKU X meningkat 800 ton/thn mulai Q3 2026",
                key="sken_trigger")
        with _trig_col2:
            _target_yr = st.text_input("Target Implementasi", placeholder="Contoh: Q1 2027", key="sken_target")
        st.caption(f"**Dasar perhitungan manfaat:** {_sken['benefit_basis']}")

    if _trigger:
        st.info(f"📋 **Urgensi:** {_trigger}", icon="📋")
    st.markdown("---")

    # ═══ SECTION 1: KONFIGURASI LINI ════════════════════════════════════════════
    st.markdown('<div class="section-title">Konfigurasi Lini Produksi</div>',unsafe_allow_html=True)
    cap_mode=st.radio("Input kapasitas:",["Upload CSV","Manual"],horizontal=True)
    lines=[]   # [{name, type, config, tons, util, cap_annual, days, hours}]

    if cap_mode=="Upload CSV":
        cap_file=st.file_uploader("CSV Kapasitas (dari Export Kapasitas — menu Kapasitas & Investasi)",
            type=["csv","tsv"],key="cap_csv")
        if cap_file:
            set_("_cap_bytes",cap_file.getvalue()); set_("_cap_name",cap_file.name)
        cb=get("_cap_bytes"); cn=get("_cap_name") if isinstance(get("_cap_name"),str) else ""
        if cb and len(cb)>0:
            try:
                sep="\t" if cn.endswith(".tsv") else ","
                cap_df=pd.read_csv(io.BytesIO(cb) if isinstance(cb,bytes) else io.StringIO(cb.decode()),sep=sep)

                # ── Auto-detect all lines from Tons_X columns ──────────────────
                import re as _re
                detected_ids=[]
                for col in cap_df.columns:
                    m=_re.match(r"Tons_([A-Za-z0-9]+)$",col)
                    if m:
                        lid=m.group(1)
                        if lid not in detected_ids:
                            detected_ids.append(lid)
                if not detected_ids:
                    detected_ids=["B","G","D"]  # fallback

                # Display table (drop meta columns, show cleanly)
                disp=cap_df.drop(columns=[c for c in cap_df.columns
                    if c.lower() in ("scenario","option","batch_mode","growth","batch mode")],errors="ignore").copy()
                _col_rename={
                    "B_Days":"Hari B","B_Hours":"Jam B","G_Days":"Hari G","G_Hours":"Jam G",
                    "D_Days":"Hari D","D_Hours":"Jam D","C_Days":"Hari C","C_Hours":"Jam C",
                    "Tons_B":"Produksi B (ton)","Util_B":"Utilisasi B (%)","Line_B_Type":"Tipe B","Line_B_Config":"Konfigurasi B",
                    "Tons_G":"Produksi G (ton)","Util_G":"Utilisasi G (%)","Line_G_Type":"Tipe G","Line_G_Config":"Konfigurasi G",
                    "Tons_D":"Produksi D (ton)","Util_D":"Utilisasi D (%)","Line_D_Type":"Tipe D","Line_D_Config":"Konfigurasi D",
                    "Tons_C":"Produksi C (ton)","Util_C":"Utilisasi C (%)","Line_C_Type":"Tipe C","Line_C_Config":"Konfigurasi C",
                }
                disp=disp.rename(columns={c:_col_rename.get(c,c) for c in disp.columns})
                st.dataframe(disp,use_container_width=True,hide_index=True)

                row=cap_df.iloc[-1]
                for lid in detected_ids:
                    tons_col=next((c for c in cap_df.columns if c==f"Tons_{lid}"),None)
                    util_col=next((c for c in cap_df.columns if c in (f"Util_{lid}",f"Util_{lid}(%)")),None)
                    type_col=next((c for c in cap_df.columns if c in (f"Line_{lid}_Type",f"Line_{lid} Type")),None)
                    cfg_col =next((c for c in cap_df.columns if c in (f"Line_{lid}_Config",f"Line_{lid} Config")),None)
                    days_col=next((c for c in cap_df.columns if c in (f"{lid}_Days",f"Line {lid} Days",f"Line_{lid}_Days")),None)
                    hrs_col =next((c for c in cap_df.columns if c in (f"{lid}_Hours",f"Line {lid} Hours",f"Line_{lid}_Hours")),None)

                    if tons_col and _sf(row.get(tons_col,0))>0:
                        tons=_sf(row.get(tons_col,0))
                        util=_sf(row.get(util_col,0)) if util_col else 0
                        ltp=str(row.get(type_col,"SSS+BIB")).strip() if type_col else ("SSS" if lid=="D" else "SSS+BIB")
                        lcf=str(row.get(cfg_col,"single")).strip() if cfg_col else ("multiline" if lid=="D" else "single")
                        days=int(_sf(row.get(days_col,7))) if days_col else 7
                        hrs =int(_sf(row.get(hrs_col,24))) if hrs_col else 24
                        # Calibrated annual capacity from schedule + utilization
                        avail_hrs=(days/7*349)*hrs
                        cap100=(tons/(util/100)) if util>0 else avail_hrs*RATE_SSBIB_SINGLE
                        lines.append({"name":f"Lini {lid}","type":ltp,"config":lcf,
                            "tons":tons,"util":util,"cap_annual":cap100,"days":days,"hours":hrs})

                if lines:
                    pass  # lini terdeteksi, tidak perlu pesan
                else:
                    st.warning("Tidak ada lini valid terdeteksi di CSV.")

            except Exception as e: st.error(f"Gagal membaca CSV: {e}")
        if not cb: st.info("Upload file CSV kapasitas hasil export dari menu Kapasitas & Investasi.")

    else:
        # ── Manual — per-line days/hours/tons/util ─────────────────────────────
        if "ml4" not in st.session_state:
            st.session_state["ml4"]=[
                {"name":"Lini B","type":"SSS+BIB","config":"single", "days":7,"hours":24,"tons":4081.0,"util":87.8},
                {"name":"Lini G","type":"SSS+BIB","config":"single", "days":7,"hours":24,"tons":4610.5,"util":87.8},
                {"name":"Lini D","type":"SSS",    "config":"multiline","days":7,"hours":24,"tons":2752.6,"util":83.5},
            ]
        ml=st.session_state["ml4"]
        for i,ln in enumerate(ml):
            with st.expander(f"{ln['name']} — {ln['type']} ({ln['config']}) | {ln.get('days',7)}D/{ln.get('hours',24)}H",
                             expanded=i<4):
                r1=st.columns([2,2,2,1])
                with r1[0]: ml[i]["name"]=st.text_input("Nama Lini",ln["name"],key=f"mn_{i}")
                with r1[1]: ml[i]["type"]=st.selectbox("Kemasan",["SSS+BIB","SSS","STICKPACK"],
                    index=["SSS+BIB","SSS","STICKPACK"].index(ln["type"]) if ln["type"] in ["SSS+BIB","SSS","STICKPACK"] else 0,key=f"mt_{i}")
                with r1[2]: ml[i]["config"]=st.selectbox("Konfigurasi",["single","multiline"],
                    index=0 if ln["config"]=="single" else 1,key=f"mc_{i}")
                with r1[3]:
                    st.markdown("<br>",unsafe_allow_html=True)
                    if st.button("🗑",key=f"md_{i}") and len(ml)>1: ml.pop(i); st.rerun()
                # Per-line schedule
                rs=st.columns(2)
                with rs[0]: ml[i]["days"]=st.select_slider("Hari Kerja/Minggu",[5,6,7],
                    value=int(ln.get("days",7)),key=f"mdays_{i}")
                with rs[1]: ml[i]["hours"]=st.select_slider("Jam Kerja/Hari",[8,16,24],
                    value=int(ln.get("hours",24)),key=f"mhrs_{i}")
                # Existing production data
                r2=st.columns(2)
                with r2[0]: ml[i]["tons"]=st.number_input("Produksi Existing (ton)",0.0,50000.0,
                    float(ln.get("tons",0)),100.0,key=f"mtons_{i}")
                with r2[1]: ml[i]["util"]=st.number_input("Utilisasi Existing (%)",0.0,100.0,
                    float(ln.get("util",0)),0.5,key=f"mutil_{i}")
                # Estimated capacity from per-line schedule
                _d=ml[i]["days"]; _h=ml[i]["hours"]
                _avail=(_d/7*349)*_h
                _rate=RATES.get((ml[i]["type"],ml[i]["config"]),RATE_SSBIB_SINGLE)
                _cap_est=_rate*_avail
                st.caption(f"Kapasitas maks estimasi: **{_cap_est:,.0f} ton/tahun** "
                           f"({_d}D/{_h}H · {_rate:.3f} ton/jam × {_avail:,.0f} jam/tahun)")
        if len(ml)<7:
            if st.button("＋ Tambah Lini"):
                next_id=chr(65+len(ml))
                ml.append({"name":f"Lini {next_id}","type":"SSS+BIB","config":"single",
                            "days":7,"hours":24,"tons":0.0,"util":0.0})
                st.rerun()
        for ln in ml:
            _d=ln.get("days",7); _h=ln.get("hours",24)
            _avail=(_d/7*349)*_h
            rate=RATES.get((ln["type"],ln["config"]),RATE_SSBIB_SINGLE)
            cap_yr=rate*_avail
            lines.append({"name":ln["name"],"type":ln["type"],"config":ln["config"],
                "tons":ln["tons"],"util":ln["util"],"days":_d,"hours":_h,
                "cap_annual":cap_yr if cap_yr>0 else (ln["tons"]/(ln["util"]/100) if ln["util"]>0 else 0)})

    if not lines:
        st.info("Konfigurasi lini untuk melanjutkan."); st.stop()

    covered_types={pt for ln in lines for pt in TYPE_COMPAT.get(ln["type"],[])}

    # ═══ SECTION 2: VOLUME PRODUKSI ═════════════════════════════════════════════
    st.markdown("---")
    st.markdown('<div class="section-title">Volume Produksi yang Diproyeksikan</div>',unsafe_allow_html=True)

    sku_df=get("master_sku")
    vol_mode=st.radio("Sumber volume:",["Master SKU","Upload CSV","Input Manual"],horizontal=True)
    products=[]
    financial_basis="co-man"  # or "custom"

    if vol_mode=="Master SKU":
        if sku_df.empty: st.warning("Upload Master SKU di sidebar."); st.stop()
        financial_basis="co-man"
        status_col=next((c for c in sku_df.columns if "STATUS" in c.upper()),None)
        port_col=next((c for c in sku_df.columns if "PORT" in c.upper()),None)
        vol_col=next((c for c in sku_df.columns if "VOLUME" in c.upper()),None)
        sku_col=sku_df.columns[0]
        if status_col:
            avail=sorted(sku_df[status_col].astype(str).str.strip().unique().tolist())
            sel_st=st.multiselect("Filter Status:",avail,
                default=[s for s in avail if any(k in s.upper() for k in ["CO-MAN","COMAN","MAKLON"])])
            filtered=(sku_df[sku_df[status_col].astype(str).str.strip().isin(sel_st)] if sel_st else sku_df).copy()
        else: filtered=sku_df.copy()
        if port_col:
            all_pkgs=sorted({classify_port(v) for v in filtered[port_col].dropna()})
            sel_pkg=st.multiselect("Jenis Kemasan:",all_pkgs,default=all_pkgs)
            filtered=filtered[filtered[port_col].apply(classify_port).isin(sel_pkg)]
        if filtered.empty: st.warning("Tidak ada SKU setelah filter."); st.stop()
        # SKU checkbox
        check_all=st.checkbox("✓ Pilih semua SKU",value=True)
        rows_for_sku=[(str(r[sku_col]),classify_port(r.get(port_col,"SSS") if port_col else "SSS"),
                       _sf(r.get(vol_col,0) if vol_col else 0,0)) for _,r in filtered.iterrows()]
        if check_all:
            sel_skus={name for name,_,_ in rows_for_sku}
        else:
            with st.expander("Pilih SKU"):
                cols4=st.columns(3)
                sel_skus=set()
                for i,(name,ptype,vol) in enumerate(rows_for_sku):
                    with cols4[i%3]:
                        if st.checkbox(f"{name} ({ptype}, {vol:.2f} t/bln)",value=True,key=f"sk_{i}"):
                            sel_skus.add(name)
        for name,ptype,vol in rows_for_sku:
            if name in sel_skus:
                products.append({"name":name,"port_type":ptype,"vol_per_month":vol,"vol_total":vol*proj_months})

    elif vol_mode=="Upload CSV":
        financial_basis="custom"
        # info removed — value shown in sidebar
        vol_file=st.file_uploader("CSV Volume (kolom: SKU, Port_Type, Vol_Per_Month)",type=["csv","tsv"],key="vol_csv")
        if vol_file:
            set_("_vol_bytes",vol_file.getvalue()); set_("_vol_name",vol_file.name)
        vb=get("_vol_bytes"); vn=get("_vol_name") if isinstance(get("_vol_name"),str) else ""
        if vb and len(vb)>0:
            try:
                sep="\t" if vn.endswith(".tsv") else ","
                vol_df=pd.read_csv(io.BytesIO(vb) if isinstance(vb,bytes) else io.StringIO(vb.decode()),sep=sep)
                # Cross-ref with master SKU
                internal_skus=set()
                if not sku_df.empty:
                    st_c=next((c for c in sku_df.columns if "STATUS" in c.upper()),None)
                    if st_c:
                        internal_skus={str(r.iloc[0]) for _,r in sku_df.iterrows() if "INTERNAL" in str(r[st_c]).upper()}
                vol_df["_flag"]=vol_df.iloc[:,0].astype(str).apply(lambda s:"⚠ Sudah Internal" if s in internal_skus else "")
                st.dataframe(vol_df,use_container_width=True,hide_index=True)
                if vol_df["_flag"].str.len().gt(0).any():
                    st.warning("SKU bertanda ⚠ sudah diproduksi internal — pastikan tidak terjadi double-counting.")
                check_all_csv=st.checkbox("✓ Pilih semua",value=True,key="ca_csv")
                sel_csv=set()
                if check_all_csv:
                    sel_csv={str(r.iloc[0]) for _,r in vol_df.iterrows()}
                else:
                    with st.expander("Pilih SKU"):
                        for i,(_,row) in enumerate(vol_df.iterrows()):
                            nm=str(row.iloc[0])
                            if st.checkbox(f"{nm} ({row.get('Port_Type','')}){' ⚠' if row.get('_flag') else ''}",
                                           value=not row.get("_flag"),key=f"csk_{i}"):
                                sel_csv.add(nm)
                for _,row in vol_df.iterrows():
                    if str(row.iloc[0]) in sel_csv:
                        pt=classify_port(row.get("Port_Type","SSS"))
                        vol=_sf(row.get("Vol_Per_Month",0),0)
                        products.append({"name":str(row.iloc[0]),"port_type":pt,"vol_per_month":vol,
                            "vol_total":vol*proj_months,"financial_status":"CO-MAN","fin_value":COMAN_SAVINGS_PER_TON})
            except Exception as e: st.error(f"Gagal membaca CSV: {e}")
        else: st.info("Upload CSV volume.")

    else:  # Input Manual
        financial_basis="custom"
        # info text removed
        if "mp4" not in st.session_state:
            st.session_state["mp4"]=[{"name":"Produk 1","port_type":"SSS","vol_per_month":5.0}]
        mp=st.session_state["mp4"]
        for i,prod in enumerate(mp):
            mc=st.columns([3,2,2,1])
            with mc[0]: mp[i]["name"]=st.text_input("Nama SKU/Produk",prod["name"],key=f"pn_{i}")
            with mc[1]: mp[i]["port_type"]=st.selectbox("Kemasan",["SSS","BIB","STICKPACK"],
                index=["SSS","BIB","STICKPACK"].index(prod["port_type"]) if prod["port_type"] in ["SSS","BIB","STICKPACK"] else 0,key=f"pt_{i}")
            with mc[2]: mp[i]["vol_per_month"]=st.number_input("Vol/Bulan (ton)",0.01,10000.0,float(prod["vol_per_month"]),0.1,key=f"pv_{i}")
            with mc[3]:
                st.markdown("<br>",unsafe_allow_html=True)
                if st.button("🗑",key=f"pd_{i}") and len(mp)>1: mp.pop(i); st.rerun()
        if st.button("＋ Tambah SKU"):
            mp.append({"name":f"Produk {len(mp)+1}","port_type":"SSS","vol_per_month":1.0}); st.rerun()
        for prod in mp:
            products.append({"name":prod["name"],"port_type":prod["port_type"],
                "vol_per_month":prod["vol_per_month"],"vol_total":prod["vol_per_month"]*proj_months,
                    "financial_status":"CO-MAN","fin_value":COMAN_SAVINGS_PER_TON})

    if not products:
        st.info("Tambahkan data volume untuk melanjutkan."); st.stop()

    # Volume summary KPI
    pkg_volumes={}
    for p in products:
        pkg_volumes[p["port_type"]]=pkg_volumes.get(p["port_type"],0)+p["vol_total"]

    # Per-product status logic
    _statuses = set(p.get("financial_status","CO-MAN") for p in products)
    _is_master_sku = (vol_mode == "Master SKU")

    if _is_master_sku:
        # Master SKU: status auto-detected per product
        if len(_statuses) > 1:
            # Mix of CO-MAN & INTERNAL: show per-product toggles
            st.markdown("**Status Produksi per Produk** (terdeteksi dari Master SKU, dapat diubah):")
            _updated = []
            for idx_p, p in enumerate(products):
                c_nm, c_st, c_vl = st.columns([4,2,2])
                with c_nm: st.markdown(f"**{p['name']}** ({p['port_type']})")
                with c_st:
                    _st = st.selectbox("",["CO-MAN","INTERNAL"],
                        index=0 if p.get("financial_status","CO-MAN")=="CO-MAN" else 1,
                        key=f"pst_{idx_p}",label_visibility="collapsed")
                    p["financial_status"] = _st
                    p["fin_value"] = COMAN_SAVINGS_PER_TON if _st=="CO-MAN" else val_per_ton_internal
                with c_vl: st.caption(f"Rp {p['fin_value']:,.0f}/ton")
                _updated.append(p)
            products = _updated
        else:
            # All same → just show summary caption
            _only = next(iter(_statuses))
            _val  = COMAN_SAVINGS_PER_TON if _only=="CO-MAN" else val_per_ton_internal
            st.caption(f"Semua produk: **{_only}** — Rp {_val:,.0f}/ton")
    else:
        # CSV / Manual: bulk selector first, then per-product if mixed
        _bulk = st.radio("Status produksi:",["Semua CO-MAN","Semua INTERNAL","Campuran (per produk)"],
            horizontal=True, key="vol_bulk_status")
        if _bulk == "Semua CO-MAN":
            for p in products:
                p["financial_status"]="CO-MAN"; p["fin_value"]=COMAN_SAVINGS_PER_TON
        elif _bulk == "Semua INTERNAL":
            for p in products:
                p["financial_status"]="INTERNAL"; p["fin_value"]=val_per_ton_internal
        else:
            _updated = []
            for idx_p, p in enumerate(products):
                c_nm, c_st, c_vl = st.columns([4,2,2])
                with c_nm: st.markdown(f"**{p['name']}** ({p['port_type']})")
                with c_st:
                    _st = st.selectbox("",["CO-MAN","INTERNAL"],
                        index=0 if p.get("financial_status","CO-MAN")=="CO-MAN" else 1,
                        key=f"pst_{idx_p}",label_visibility="collapsed")
                    p["financial_status"] = _st
                    p["fin_value"] = COMAN_SAVINGS_PER_TON if _st=="CO-MAN" else val_per_ton_internal
                with c_vl: st.caption(f"Rp {p['fin_value']:,.0f}/ton")
                _updated.append(p)
            products = _updated

    c1,c2,c3,c4=st.columns(4)
    for col,val,lbl,clr in [
        (c1,f"{len(products)} SKU","Total SKU","#58a6ff"),
        (c2,f"{(pkg_volumes.get('SSS',0)+pkg_volumes.get('BIB',0)):,.1f} ton",f"SSS+BIB ({proj_months} bln)","#3fb950"),
        (c3,f"{pkg_volumes.get('STICKPACK',0):,.1f} ton",f"Stickpack ({proj_months} bln)","#d29922"),
        (c4,f"{sum(pkg_volumes.values()):,.1f} ton","Total Volume","#f0f6fc"),
    ]:
        with col:
            st.markdown(f'<div class="kpi-box" style="border-left-color:{clr};"><div class="kpi-label">{lbl}</div><div class="kpi-value" style="color:{clr};font-size:1rem;">{val}</div></div>',unsafe_allow_html=True)
    st.markdown("<br>",unsafe_allow_html=True)

    # ═══ SECTION 3: ANALISIS KAPASITAS ═══════════════════════════════════════════
    st.markdown("---")
    st.markdown('<div class="section-title">Analisis Kapasitas</div>',unsafe_allow_html=True)

    uncovered={pt for pt in pkg_volumes if pt not in covered_types and pkg_volumes[pt]>0}
    if uncovered:
        st.warning(f"⚠ Jenis kemasan tidak memiliki lini kompatibel: **{', '.join(uncovered)}** — diperlukan investasi lini baru.")

    # Allocate volume to compatible existing lines (SSS prefers D, then B/G)
    new_tons={l["name"]:l["tons"] for l in lines}
    new_util={l["name"]:l["util"] for l in lines}

    for pkg_type,vol in pkg_volumes.items():
        if vol==0: continue
        # Routing: SSS → prefer D (SSS-only) first, then B/G; BIB → only B/G
        compat=[l for l in lines if can_handle(l["type"],pkg_type)]
        if not compat: continue
        spare={l["name"]:max(0,l["cap_annual"]-l["tons"]) for l in compat}
        total_spare=sum(spare.values())
        if total_spare<=0: continue
        for l in compat:
            alloc=vol*(spare[l["name"]]/total_spare)
            new_tons[l["name"]]+=alloc
            new_util[l["name"]]=(new_tons[l["name"]]/l["cap_annual"]*100) if l["cap_annual"]>0 else l["util"]

    existing_max_util=max((new_util[l["name"]] for l in lines),default=0)
    existing_ok=existing_max_util<=UTIL_OVERFLOW

    # ═══ SECTION 4: GRAFIK ═══════════════════════════════════════════════════════
    # Include both existing lines AND recommended new lines (stickpack)
    stickpack_vols=pkg_volumes.get("STICKPACK",0)
    stickpack_annual=stickpack_vols/proj_months*12 if proj_months>0 else 0

    # Prepare line data for charts (existing + potential stickpack line)
    chart_lines=list(lines)
    chart_new_tons=dict(new_tons)
    chart_new_util=dict(new_util)

    if stickpack_vols>0 and "STICKPACK" not in covered_types:
        # Schedule selector for new stickpack line
        st.markdown("**Jadwal Operasi Lini Stickpack Baru:**")
        _sp1, _sp2 = st.columns(2)
        with _sp1:
            sp_days = st.select_slider("Hari Kerja/Minggu (Stickpack)", [5,6,7], value=7, key="sp_days")
        with _sp2:
            sp_hrs  = st.select_slider("Jam Kerja/Hari (Stickpack)", [8,16,24], value=24, key="sp_hrs")
        sp_avail_hrs = (sp_days/7*349)*sp_hrs
        sp_cap_annual = RATE_STICKPACK * sp_avail_hrs
        sp_util = min(100, stickpack_annual/sp_cap_annual*100) if sp_cap_annual>0 else 0
        st.caption(f"Kapasitas estimasi lini stickpack: **{sp_cap_annual:,.0f} ton/tahun** "
                   f"({sp_days}D/{sp_hrs}H · {RATE_STICKPACK:.3f} ton/jam)")
        chart_lines.append({"name":"Lini Stickpack (Baru)","type":"STICKPACK","config":"single",
            "tons":0,"util":0,"cap_annual":sp_cap_annual,"days":sp_days,"hours":sp_hrs})
        chart_new_tons["Lini Stickpack (Baru)"]=stickpack_annual
        chart_new_util["Lini Stickpack (Baru)"]=sp_util

    all_lnames=[l["name"] for l in chart_lines]
    colors_by_type={"SSS+BIB":"#58a6ff","SSS":"#3fb950","STICKPACK":"#d29922"}

    cl,cr=st.columns(2)
    with cl:
        st.markdown('<div class="section-title">Utilisasi per Lini</div>',unsafe_allow_html=True)
        fig_u=go.Figure()
        fig_u.add_trace(go.Bar(x=all_lnames,y=[l["util"] for l in chart_lines],name="Sebelum",marker_color="#484f58"))
        fig_u.add_trace(go.Bar(x=all_lnames,y=[chart_new_util[l["name"]] for l in chart_lines],name="Setelah",
            marker_color=[colors_by_type.get(l["type"],"#58a6ff") for l in chart_lines]))
        fig_u.add_hline(y=util_reco_thresh,line_dash="dot",line_color="#f85149",annotation_text=f"{util_reco_thresh}%")
        fig_u.update_layout(template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            barmode="group",height=250,legend=dict(orientation="h",y=-0.25),margin=dict(l=0,r=0,t=8,b=44),
            yaxis=dict(title="%",gridcolor="#21262d",range=[0,max(110,existing_max_util+15)]))
        st.plotly_chart(fig_u,use_container_width=True)
    with cr:
        st.markdown('<div class="section-title">Tonase per Lini</div>',unsafe_allow_html=True)
        ft=go.Figure()
        ft.add_trace(go.Bar(x=all_lnames,y=[l["tons"] for l in chart_lines],name="Existing",marker_color="#484f58"))
        ft.add_trace(go.Bar(x=all_lnames,y=[chart_new_tons[l["name"]]-l["tons"] for l in chart_lines],
            name="Tambahan",marker_color=[colors_by_type.get(l["type"],"#3fb950") for l in chart_lines]))
        ft.update_layout(template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            barmode="stack",height=250,legend=dict(orientation="h",y=-0.25),margin=dict(l=0,r=0,t=8,b=44),
            yaxis=dict(title="ton",gridcolor="#21262d"))
        st.plotly_chart(ft,use_container_width=True)

    with st.expander("Tabel kapasitas per lini"):
        tbl=[{"Lini":l["name"],"Kemasan":l["type"],"Konfigurasi":l["config"],
              "Kapasitas Tersedia (ton)":f"{l['cap_annual']:,.0f}",
              "Produksi Existing (ton)":f"{l['tons']:,.0f}",
              "Utilisasi Existing (%)":f"{l['util']:.1f}",
              "Setelah Penambahan (ton)":f"{chart_new_tons[l['name']]:,.0f}",
              "Utilisasi Baru (%)":f"{chart_new_util[l['name']]:.1f}",
              "Keterangan":"Lini baru (rekomendasi)" if l["tons"]==0 and l["name"]=="Lini Stickpack (Baru)" else "Existing"
              } for l in chart_lines]
        st.dataframe(pd.DataFrame(tbl),use_container_width=True,hide_index=True)
        # throughput caption removed

    # ═══ SECTION 5: REKOMENDASI INVESTASI ════════════════════════════════════════
    st.markdown("---")
    st.markdown('<div class="section-title">Rekomendasi Investasi</div>',unsafe_allow_html=True)

    invest_items=[]  # [(label, capex_data, annual_vol, reason)]
    UTIL_RECOMMEND = util_reco_thresh  # dari sidebar

    # A) Lini baru untuk kemasan yang tidak tertampung
    for pt in uncovered:
        vol_ann=pkg_volumes.get(pt,0)/proj_months*12 if proj_months>0 else 0
        if vol_ann==0: continue
        if pt=="STICKPACK":
            cd=capex_stickpack_line()
            invest_items.append(("Investasi Lini Stickpack Baru",cd,vol_ann,"Volume Stickpack tidak ada lini kompatibel"))
            st.markdown("**Komponen — Lini Stickpack Baru:**")
            machine_cards_row(cd["machine_list"])

    # B) Tiered recommendation for existing lines — like Capacity Planning
    from modules.financial_calc import capex_multiline as _cap_multi

    # Find all single lines with util >= threshold (before OR after allocation)
    _overloaded = []
    for ln in lines:
        _ua = chart_new_util.get(ln["name"], ln["util"])
        _ub = ln["util"]
        if (_ua >= util_reco_thresh or _ub >= util_reco_thresh) and        ln["config"]=="single" and ln["type"] in ("SSS+BIB","SSS"):
            _overloaded.append({"name":ln["name"],"util_before":_ub,"util_after":_ua,"line":ln})
        elif (_ua >= util_reco_thresh or _ub >= util_reco_thresh) and ln["config"]=="multiline":
            st.warning(f"⚠ {ln['name']} utilisasi {_ua:.1f}% ≥ {util_reco_thresh}% namun sudah multiline.",icon="⚠")

    # Sort by util_after descending — most critical first
    _overloaded.sort(key=lambda x: -x["util_after"])

    # Build tier options
    _tier_opts = []
    if _overloaded:
        for _i, _ov in enumerate(_overloaded):
            _lbl = (f"Tier {_i+1} — Upgrade {_ov['name']} → Multiline "
                    f"(utilisasi {_ov['util_before']:.1f}% → {_ov['util_after']:.1f}%)")
            _tier_opts.append(_lbl)
        if len(_overloaded) > 1:
            _tier_opts.append(f"Semua {len(_overloaded)} lini → Multiline (upgrade penuh)")
        _tier_opts = ["Tidak perlu upgrade lini existing"] + _tier_opts

    if _tier_opts:
        _sel_tier = st.selectbox("Pilih opsi upgrade lini existing:", _tier_opts, key="tier_sel")
    else:
        _sel_tier = "Tidak perlu upgrade lini existing"

    # Determine which lines to upgrade based on selection
    _to_upgrade = []
    if "Semua" in _sel_tier:
        _to_upgrade = [_ov["line"] for _ov in _overloaded]
    elif "Tier" in _sel_tier:
        _tier_idx = int(_sel_tier.split("Tier")[1].split("—")[0].strip()) - 1
        if _tier_idx < len(_overloaded):
            _to_upgrade = [_overloaded[_tier_idx]["line"]]

    # Simulate capacity after selected upgrades + update chart_new_util
    MULTILINE_FACTOR = 3.0  # calibrated: 6 filling heads vs 2 → 3× throughput
    _updated_caps = {}
    for _uln in _to_upgrade:
        _old_cap = _uln["cap_annual"]
        _new_cap = _old_cap * MULTILINE_FACTOR
        _tons_after = chart_new_tons.get(_uln["name"], _uln["tons"])
        _util_after_upgrade = min(999, (_tons_after / _new_cap * 100)) if _new_cap > 0 else 0
        chart_new_util[_uln["name"]] = _util_after_upgrade
        _updated_caps[_uln["name"]] = _new_cap
        # Add to invest_items
        _cd_up = _cap_multi(qty_lines=1)
        _reason_up = (f"Utilisasi {_uln['util']:.1f}% → {chart_new_util[_uln['name']]:.1f}% "
                      f"setelah upgrade (kapasitas ×{MULTILINE_FACTOR:.0f})")
        invest_items.append((f"Upgrade {_uln['name']} → Multiline", _cd_up, 0, _reason_up))
        st.markdown(f"**Komponen — Upgrade {_uln['name']} → Multiline:**")
        machine_cards_row(_cd_up["machine_list"])

    # Refresh capacity table if upgrades selected
    if _to_upgrade:
        st.markdown("**Kapasitas Lini Setelah Upgrade:**")
        _tbl2 = []
        for l in chart_lines:
            _nm = l["name"]
            _cap_disp = _updated_caps.get(_nm, l["cap_annual"])
            _cfg_disp = "multiline" if _nm in [u["name"] for u in _to_upgrade] else l["config"]
            _tbl2.append({
                "Lini":_nm,"Kemasan":l["type"],"Konfigurasi":_cfg_disp,
                "Kap. Maks (ton/thn)":f"{_cap_disp:,.0f}",
                "Produksi Eksisting (ton)":f"{l['tons']:,.0f}",
                "Utilisasi Eksisting (%)":f"{l['util']:.1f}",
                "Tonase Dialokasikan (ton)":f"{chart_new_tons.get(_nm,0):,.0f}",
                "Utilisasi Setelah Alokasi (%)":f"{chart_new_util.get(_nm,l['util']):.1f}",
                "Keterangan":("Setelah upgrade" if _nm in [u['name'] for u in _to_upgrade]
                             else ("Lini baru" if l['tons']==0 else "Existing"))
            })
        st.dataframe(pd.DataFrame(_tbl2),use_container_width=True,hide_index=True)


    # ── CAPEX/OPEX detail expander ───────────────────────────────────────────────
    if invest_items:
        with st.expander("Rincian CAPEX & OPEX"):
            for inv_label, cd, vol_ann, reason in invest_items:
                st.markdown(f"**{inv_label}**")
                st.caption(reason)
                _cr, _or = st.columns(2)
                with _cr:
                    st.markdown("**CAPEX (investasi awal)**")
                    _c_rows = [(k.upper().replace("_"," "), f"Rp {v:,.0f}")
                               for k,v in cd.get("breakdown",{}).items()]
                    if _c_rows:
                        st.dataframe(pd.DataFrame(_c_rows, columns=["Item","Biaya"]),
                                     use_container_width=True, hide_index=True)
                    st.markdown(f"**Total CAPEX: {fmt_rp(cd.get('total',0))}**")
                with _or:
                    st.markdown("**OPEX tahunan (estimasi)**")
                    _maint = cd.get("annual_opex_maintenance", cd.get("annual_opex_total",0)*0.6)
                    _op_sal = cd.get("annual_operator_salary", 83_200_000)  # 1 operator
                    _qc_sal = cd.get("annual_qc_salary", 83_200_000)         # 1 QC
                    _opex_total = _maint + _op_sal + _qc_sal
                    _o_rows = [
                        ("Perawatan mesin", fmt_rp(_maint)),
                        ("Gaji operator (1 org)", fmt_rp(_op_sal)),
                        ("Gaji QC (1 org)", fmt_rp(_qc_sal)),
                    ]
                    st.dataframe(pd.DataFrame(_o_rows, columns=["Item","Biaya/Tahun"]),
                                 use_container_width=True, hide_index=True)
                    st.markdown(f"**Total OPEX / Tahun: {fmt_rp(_opex_total)}**")
                st.markdown("---")

    # Aggregate CAPEX/OPEX from all investment items
    # Compute annual volume from all selected products
    annual_total_vol = sum(p.get('vol_per_month',0) for p in products)*12 if products else sum(pkg_volumes.values())
    # Per-product weighted benefit
    # CO-MAN: fixed Rp 1.5M (no realization factor — selisih biaya, bukan margin)
    # INTERNAL: val_per_ton_internal × realization_factor
    _rf = params["realization_factor"]
    annual_benefit_direct = sum(
        p.get("vol_per_month",0)*12 * (
            COMAN_SAVINGS_PER_TON                        # CO-MAN: fixed, no RF
            if p.get("financial_status","CO-MAN")=="CO-MAN"
            else val_per_ton_internal * _rf              # INTERNAL: × realization factor
        )
        for p in products
    ) if products else annual_total_vol * val_per_ton_internal * _rf
    # Effective val_per_ton for display (weighted avg, pre-RF for CO-MAN)
    val_per_ton = annual_benefit_direct/annual_total_vol if annual_total_vol>0 else val_per_ton_internal
    total_capex=sum(cd.get("total",0) for _,cd,*_ in invest_items)
    total_opex=sum(cd.get("annual_opex_total",0) for _,cd,*_ in invest_items)
    params["internal_value_per_ton"]=val_per_ton
    # Use annual_benefit_direct directly (RF already applied per-product above)
    params["_benefit_override"] = annual_benefit_direct
    fin=compute_financial(total_capex,annual_total_vol,params,annual_opex_extra=total_opex)
    N=int(params["project_lifetime_year"]); ar=fin["roi_pct"]/N
    breakeven=total_opex/(val_per_ton*params["realization_factor"]) if val_per_ton>0 else 0

    kc=st.columns(4)
    for col,lbl,val,ok in [
        (kc[0],"NPV",fmt_rp(fin["npv"]),fin["npv"]>0),
        (kc[1],"IRR",f"{fin['irr_pct']:.1f}%" if fin["irr_pct"] else "N/A",(fin["irr_pct"] or 0)/100>=params["minimum_irr"]),
        (kc[2],"ROI/Tahun",f"{ar:.1f}%",ar>=10),
        (kc[3],"Payback",f"{fin['payback_year']:.2f} thn" if fin["payback_year"] else "N/A",(fin["payback_year"] or 99)<=params["payback_threshold_year"]),
    ]:
        clr="#3fb950" if ok else "#f85149"
        with col:
            st.markdown(f'<div class="kpi-box" style="border-left-color:{clr};"><div class="kpi-label">{lbl}</div><div class="kpi-value" style="color:{clr};font-size:1.1rem;">{val}</div></div>',unsafe_allow_html=True)
    st.markdown("<br>",unsafe_allow_html=True)
    # Verdict
    _feas=fin["feasible"]
    _bv="badge-feasible" if _feas else "badge-infeasible"
    _vdict="LAYAK" if _feas else "TIDAK LAYAK"
    _vfc,_vv=st.columns([1,2])
    with _vfc:
        st.markdown(f'<b>Verdict:</b> <span class="{_bv}">{_vdict}</span>',unsafe_allow_html=True)
        st.markdown("<br>",unsafe_allow_html=True)
        for _flag,_ok in fin["flags"].items():
            _flag2="ROI/thn ≥ 10%" if "ROI" in _flag else _flag
            _ok2=ar>=10 if "ROI" in _flag else _ok
            _clr="#3fb950" if _ok2 else "#f85149"
            _chk="✓" if _ok2 else "✗"
            st.markdown(f'<span style="color:{_clr};">{_chk} {_flag2}</span>',unsafe_allow_html=True)
    with _vv:
        # Cash flow chart next to verdict
        if total_capex>0 and fin.get("cash_flows"):
            cfs=fin["cash_flows"]
            yrs=list(range(len(cfs)))
            cum=[sum(cfs[:j+1]) for j in range(len(cfs))]
            fig_cf=go.Figure()
            fig_cf.add_bar(x=yrs,y=[c/1e6 for c in cfs],name="Arus Kas",
                marker_color=["#f85149"]+["#3fb950"]*(len(cfs)-1))
            fig_cf.add_scatter(x=yrs,y=[c/1e6 for c in cum],mode="lines+markers",
                name="Kumulatif",line=dict(color="#58a6ff",width=2))
            fig_cf.add_hline(y=0,line_dash="dash",line_color="#8b949e")
            fig_cf.update_layout(height=220,plot_bgcolor="#0d1117",paper_bgcolor="#0d1117",
                font_color="#c9d1d9",legend=dict(orientation="h",y=-0.3),
                xaxis_title="Tahun",yaxis_title="Rp Juta",margin=dict(t=10,b=10))
            st.plotly_chart(fig_cf,use_container_width=True)
    if total_capex > 0:
        _vpt_disp = annual_benefit_direct / annual_total_vol if annual_total_vol > 0 else val_per_ton
        _ann_b = annual_benefit_direct
        _fin_rows = [
            ("Investasi (CAPEX)", fmt_rp(total_capex), ""),
            ("Biaya Operasi (OPEX/thn)", fmt_rp(total_opex), f"× {N} thn = {fmt_rp(total_opex*N)}"),
            ("Manfaat / tahun", fmt_rp(_ann_b), f"= {annual_total_vol:,.0f} ton × Rp {_vpt_disp:,.0f}/ton"),
            ("Selisih kumulatif", "", fmt_rp(_ann_b*N - total_capex - total_opex*N)),
        ]
        st.dataframe(pd.DataFrame(_fin_rows, columns=["Item","Per Tahun","Kumulatif"]),
                     use_container_width=True, hide_index=True)

    # cash flow chart moved to side-by-side with verdict

    if total_opex>0:
        beven_str=""
    # (beven removed)

    # ── Rekomendasi Terpilih ──────────────────────────────────────────────────────
    if invest_items:
        st.markdown("---")
        from modules.financial_calc import MACHINES as _MC4
        for _ri,(inv_label,cd,vol_ann,reason) in enumerate(invest_items):
            # Build machine list
            _comps_rc=[]
            for _cm in cd.get("machine_list",[]):
                if isinstance(_cm,dict):
                    _k=_cm.get("key",""); _q=_cm.get("qty",1)
                    _nm=_MC4.get(_k,{}).get("name",_k.upper()) if _k else str(_cm)
                    _comps_rc.append(f"{_nm} ×{_q}" if int(_q)>1 else _nm)
            # Stickpack schedule chip if applicable
            _sp_chip=""
            if "Stickpack" in inv_label or "STICKPACK" in inv_label:
                _sp_d=st.session_state.get("sp_days",7); _sp_h=st.session_state.get("sp_hrs",24)
                _sp_chip=(f'<span style="background:#0d1117;border:1px solid #388bfd;border-radius:4px;'                       f'padding:4px 14px;font-size:.82rem;color:#58a6ff;margin:2px;">'                       f'Lini Stickpack (Baru): {_sp_d}D/{_sp_h}H</span>')
            _chips="".join(
                f'<span style="display:inline-block;background:#161b22;border:1px solid #30363d;'             f'border-radius:6px;padding:4px 12px;margin:4px 3px;font-size:0.82rem;color:#c9d1d9;">{c}</span>'
                for c in _comps_rc)
            # Line config chips
            _lini_chips="".join(
                f'<span style="background:#161b22;border:1px solid #30363d;border-radius:4px;'             f'padding:4px 14px;font-size:.82rem;color:#c9d1d9;margin:2px;">'             f'{l["name"]}: {l.get("days",7)}D/{l.get("hours",24)}H</span>'
                for l in lines[:5])
            _vc="#3fb950" if fin.get("feasible") else "#f85149"
            _vt="LAYAK" if fin.get("feasible") else "TIDAK LAYAK"
            st.markdown(f'''
    <div class="dss-card" style="border:1px solid #30363d;border-radius:12px;padding:2rem;text-align:center;margin-bottom:1.5rem;">
      <div class="kpi-label" style="letter-spacing:0.15em;">REKOMENDASI TERPILIH</div>
      <div style="font-size:1.6rem;font-weight:800;color:#f0f6fc;margin:0.4rem 0;">{inv_label}</div>
      <span style="background:{_vc};color:#fff;font-weight:700;padding:6px 22px;border-radius:8px;font-size:0.9rem;">{_vt}</span>
      <div style="margin-top:0.8rem;">{_chips}</div>
      <div style="font-size:0.78rem;color:#8b949e;margin-top:1rem;">KONFIGURASI LINI</div>
      <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:.5rem;margin-top:0.4rem;">{_lini_chips}{_sp_chip}</div>
      <div style="font-size:0.78rem;color:#8b949e;margin-top:1rem;">
        CAPEX: <b>{fmt_rp(cd.get("total",0))}</b> &nbsp;|&nbsp; OPEX: <b>{fmt_rp(cd.get("annual_opex_total",0))}/thn</b>
      </div>
    </div>''',unsafe_allow_html=True)



