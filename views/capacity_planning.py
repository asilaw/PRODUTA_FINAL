import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
from modules.session import get, set_
from modules.data_loader import load_simulation, load_master_sku
from modules.fis_engine import compute_fis
from modules.capacity_model import estimate_upgrade
from modules.financial_calc import compute_financial, capex_multiline, capex_new_line, capex_stickpack_line, DEFAULT_PARAMS, MACHINES


def render():
    """pages/2_scenario_evaluation.py — Kapasitas & Investasi  [v2025-05-25]"""
    # VERSION: v2025-05-25 — cek judul halaman untuk konfirmasi versi terbaru
    import streamlit as st
    import pandas as pd
    import numpy as np
    import plotly.graph_objects as go
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from modules.data_loader    import load_simulation
    from modules.session        import get, upload_widget
    from modules.fis_engine     import compute_fis
    from modules.capacity_model import (diagnose_bottleneck, estimate_upgrade,
                                        recommend_options)
    from modules.financial_calc import (compute_financial, monte_carlo_npv,
                                        CAPEX_FN, DEFAULT_PARAMS, MACHINES, fmt_rp)

    def _s(row, key, d=0.0):
        v = str(row.get(key, d)).replace("%","").strip().replace("[cek P_D]","0")
        try: return float(v)
        except: return float(d)


    def machine_cards(machine_list):
        """Show machine cards using st.image() — supports JPG and PNG."""
        import base64 as _b64
        cols = st.columns(min(len(machine_list), 4))
        for i, item in enumerate(machine_list):
            key=item["key"]; qty=item.get("qty",1)
            m=MACHINES.get(key,{}); col=cols[i%len(cols)]
            capex_t=m.get("capex",0)*qty; opex_yr=m.get("capex",0)*m.get("opex_rate",0)*qty
            url=m.get("url","#")
            link=f'<a href="{url}" target="_blank" style="font-size:0.72rem;color:#58a6ff;text-decoration:none;">Lihat Detail ↗</a>'
            img_html='<div style="width:100%;height:90px;background:#1e2a3a;border-radius:4px;display:flex;align-items:center;justify-content:center;margin-bottom:8px;font-size:2rem;">⚙️</div>'
            qty_str=f" ×{qty}" if qty>1 else ""
            with col:
                img_found=None
                for ext,mime in [("jpg","image/jpeg"),("jpeg","image/jpeg"),("png","image/png")]:
                    p=Path(f"assets/machines/{key}.{ext}")
                    if p.exists():
                        img_found=p; break
                if img_found:
                    try:
                        from PIL import Image as _PIL; import io as _io
                        pil=_PIL.open(img_found).convert("RGBA")
                        bg=_PIL.new("RGBA",pil.size,(22,27,34,255))
                        bg.paste(pil,mask=pil.split()[3])
                        buf=_io.BytesIO(); bg.convert("RGB").save(buf,format="JPEG",quality=92)
                        buf.seek(0); st.image(buf,use_container_width=True)
                    except: st.image(str(img_found),use_container_width=True)
                else:
                    st.markdown(img_html,unsafe_allow_html=True)
                st.markdown(
                    f'<div style="text-align:center;padding:2px 4px 8px;">'
                    f'<div style="font-size:0.8rem;font-weight:700;color:#f0f6fc;letter-spacing:.03em;margin-bottom:5px;">{m.get("name","—")}{qty_str}</div>'
                    f'<div style="font-size:0.85rem;color:#58a6ff;font-weight:600;margin-bottom:2px;">{fmt_rp(capex_t)}</div>'
                    f'<div style="font-size:0.7rem;color:#8b949e;margin-bottom:7px;">~{fmt_rp(opex_yr)}/thn</div>'
                    f'{link}</div>', unsafe_allow_html=True)


    # ── Sidebar ───────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### Data")
        upload_widget("simulation","Hasil Simulasi",load_simulation)
        st.markdown("---")
        st.markdown("### Parameter")
        util_warn=st.slider("Batas Utilisasi (%)",60,95,85,5,
            help="Utilisasi di atas batas ini = MODIFY (risiko kapasitas, meski demand terpenuhi)")
        maintain_thresh=2.0  # hardcoded fallback — tidak perlu diekspos user
        st.markdown("---")
        st.markdown("### Finansial")
        params={
            "discount_rate":st.number_input("Discount Rate",0.05,0.30,DEFAULT_PARAMS["discount_rate"],0.01,format="%.2f"),
            "project_lifetime_year":st.number_input("Umur Proyek (thn)",3,15,int(DEFAULT_PARAMS["project_lifetime_year"])),
            "payback_threshold_year":st.number_input("Batas Payback (thn)",1,7,int(DEFAULT_PARAMS["payback_threshold_year"])),
            "realization_factor":st.slider("Faktor Realisasi",0.5,1.0,DEFAULT_PARAMS["realization_factor"],0.05),
            "internal_value_per_ton":st.number_input("Opportunity Value/Ton (Rp)",500_000,5_000_000,int(DEFAULT_PARAMS["internal_value_per_ton"]),100_000),
            "minimum_irr":DEFAULT_PARAMS["minimum_irr"],
            "minimum_roi":DEFAULT_PARAMS["minimum_roi"],
            "minimum_npv":DEFAULT_PARAMS["minimum_npv"],
        }


    # ── Header ────────────────────────────────────────────────────────────────────
    st.markdown('<p class="page-title">Capacity Planning</p>',unsafe_allow_html=True)
    st.caption("v2025-05-25")  # ← version marker — ganti zip jika tidak muncul ini

    sim_df=get("simulation")
    # Force column normalization regardless of which parser was used
    if not sim_df.empty:
        from modules.data_loader import _normalize_sim_columns as _ncols
        sim_df = _ncols(sim_df)
        # Also add backward-compat per-line columns if missing
        for _col, _def in [("B_Days",7),("B_Hours",24),("G_Days",7),("G_Hours",24),
                           ("D_Days",7),("D_Hours",24),("Batch_Mode",""),("Growth","0")]:
            if _col not in sim_df.columns:
                # Try space variant first
                _alt = _col.replace("_"," ") if "_" in _col else _col
                if _alt in sim_df.columns:
                    sim_df[_col] = sim_df[_alt]
                else:
                    sim_df[_col] = _def
        # Derive Scenario_ID from "Scenario" if needed
        if "Scenario_ID" not in sim_df.columns and "Scenario" in sim_df.columns:
            sim_df["Scenario_ID"] = sim_df["Scenario"]
    if sim_df.empty:
        st.info("Upload hasil simulasi di sidebar untuk memulai.")
        st.stop()

    # ── Filter empty rows ─────────────────────────────────────────────────────────
    mask=pd.Series([True]*len(sim_df))
    for col in ["Target_Demand_Ton","Tons_Finished","Effective_Working_Days"]:
        if col in sim_df.columns:
            mask&=pd.to_numeric(sim_df[col],errors="coerce").fillna(0)>0
    if "File_Name" in sim_df.columns:
        mask&=sim_df["File_Name"].astype(str).str.strip().str.len()>0
    sim_clean=sim_df[mask].reset_index(drop=True)
    if sim_clean.empty:
        st.error("Tidak ada skenario valid."); st.stop()

    # ═══ SECTION 1: EVALUASI & RANKING ═══════════════════════════════════════════
    st.markdown('<div class="section-title">Evaluasi Skenario</div>',unsafe_allow_html=True)

    results=[]
    for _,row in sim_clean.iterrows():
        ub=_s(row,"Util_Filling_B"); ug=_s(row,"Util_Filling_G"); ud=_s(row,"Util_Filling_D")
        umx=max(ub,ug,ud); tgt=max(_s(row,"Target_Demand_Ton"),1)
        unm=_s(row,"Unmet_Demand"); fr=_s(row,"Finished_Ratio"); ur=unm/tgt*100
        eff_d=_s(row,"Effective_Working_Days"); wrk_h=_s(row,"Working_Hours")
        eff_hrs=eff_d*wrk_h
        max_q=float(str(row.get("Max_Q_DayH","0")).replace(",","") or 0)
        fis=compute_fis(umx,ur,fr); score=fis["score"]
        # Primary gate: use Capacity_Status from simulation (Asil formula #30)
        # "Unmet <= 0.05 → KAPASITAS MENCUKUPI → MAINTAIN"
        cap_status_raw = str(row.get("Capacity_Status","")).strip().upper()
        if cap_status_raw and "TIDAK MENCUKUPI" in cap_status_raw:
            level = "MODIFY"     # demand tidak terpenuhi
        elif cap_status_raw and "MENCUKUPI" in cap_status_raw and "TIDAK" not in cap_status_raw:
            # Demand terpenuhi — tapi cek utilisasi
            # Utilisasi tinggi = risiko kapasitas = MODIFY (preventif)
            level = "MODIFY" if umx >= util_warn else "MAINTAIN"
        elif unm<=0 and fr>=99.95:
            level = "MAINTAIN" if umx < util_warn else "MODIFY"
        else:
            level = "MAINTAIN" if score<maintain_thresh else "MODIFY"
        # Per-line schedule (new format) or fall back to global (old format)
        _b_d=float(str(row.get("B_Days") or row.get("Days_Per_Week") or 7).replace(",","") or 7)
        _b_h=float(str(row.get("B_Hours") or row.get("Working_Hours") or 24).replace(",","") or 24)
        _g_d=float(str(row.get("G_Days") or row.get("Days_Per_Week") or 7).replace(",","") or 7)
        _g_h=float(str(row.get("G_Hours") or row.get("Working_Hours") or 24).replace(",","") or 24)
        _d_d=float(str(row.get("D_Days") or 7).replace(",","") or 7)
        _d_h=float(str(row.get("D_Hours") or 24).replace(",","") or 24)
        _bmode=str(row.get("Batch_Mode") or row.get("WO_Mode","")).strip()
        _growth=str(row.get("Growth","0")).strip()
        _cap_st=str(row.get("Capacity_Status","")).strip()
        _plan_st=str(row.get("Planner_Status","")).strip()
        _btn=str(row.get("Bottleneck_Area","")).strip()
        _setup_b=float(str(row.get("Setup_Min_B","0")).replace(",","") or 0)
        _setup_g=float(str(row.get("Setup_Min_G","0")).replace(",","") or 0)
        _setup_d=float(str(row.get("Setup_Min_D","0")).replace(",","") or 0)
        _tons_fin=_s(row,"Tons_Finished")
        _sys_hrs=(_b_d/7*349*_b_h)+(_g_d/7*349*_g_h)+(_d_d/7*349*_d_h)
        # Format scenario label: "B:7D/24H G:7D/24H D:7D/24H | BLOSS"
        _label=(f"B:{int(_b_d)}D/{int(_b_h)}H · G:{int(_g_d)}D/{int(_g_h)}H · D:{int(_d_d)}D/{int(_d_h)}H"
                +(f" | {_bmode}" if _bmode else "")
                +(f" | G+{_growth}%" if _growth not in ("0","0%","") else ""))
        results.append({
            "Scenario":   row.get("Scenario_ID","?"),
            "Label":      _label,
            "Hari B":     int(_b_d),"Jam B":  int(_b_h),
            "Hari G":     int(_g_d),"Jam G":  int(_g_h),
            "Hari D":     int(_d_d),"Jam D":  int(_d_h),
            "Batch Mode": _bmode,  "Growth":  _growth,
            "Selesai (%)":round(fr,1),"Unmet (%)": round(ur,1),
            "Util B (%)": round(ub,1),"Util G (%)":round(ug,1),"Util D (%)":round(ud,1),
            "Util Max (%)":round(umx,1),
            "Setup B (mnt)":int(_setup_b),"Setup G (mnt)":int(_setup_g),"Setup D (mnt)":int(_setup_d),
            "Bottleneck":_btn,"Status Kapasitas":_cap_st,"Status Planner":_plan_st,
            "Total Produksi (ton)":round(_tons_fin,1),
            "Skor FIS":   round(score,3),"Keputusan":level,
            # Backward-compat aliases
            "Util B":round(ub,1),"Util G":round(ug,1),"Util D":round(ud,1),
            "Finished %":round(fr,1),"Unmet %":round(ur,1),"Util Max":round(umx,1),
            "Skor":round(score,3),
            # Raw simulation columns for display
            "Target Demand (ton)":round(_s(row,"Target_Demand_Ton"),1),
            "Produksi Selesai (ton)":round(_tons_fin,1),
            "Unmet Demand (ton)":round(_s(row,"Unmet_Demand"),1),
            "Tons B":round(_s(row,"Tons_B"),1),
            "Tons G":round(_s(row,"Tons_G"),1),
            "Tons D":round(_s(row,"Tons_D"),1),
            "_row":row,"_eff_hrs":_sys_hrs,"_total_sys_hrs":_sys_hrs,
        })

    rank_df=pd.DataFrame(results)
    # ── Ranking: FIS hanya sebagai gate MAINTAIN/MODIFY.
    # Dalam MODIFY: efisiensi (Finished% tinggi + jam sedikit = lebih efisien)
    # Ranking: FIS hanya sebagai gate MAINTAIN/MODIFY.
    # Dalam MODIFY: Finished% tinggi → Total_System_Hrs kecil (lebih efisien) → Unmet% → Util Max
    _DEC_ORDER = {"MAINTAIN":0,"MODIFY":1}
    rank_df["_sort"]=rank_df.apply(lambda r:(
        _DEC_ORDER.get(r["Keputusan"],2),
        # MODIFY: sort by Selesai% desc → FIS asc → Util Max asc
        -round(r.get("Selesai (%)",r.get("Finished %",0)),2)
            if r["Keputusan"]=="MODIFY" else 0,
        round(r.get("Skor FIS",r.get("FIS Score",3.0)),4)
            if r["Keputusan"]=="MODIFY" else 0,
        round(r.get("Util Max (%)",r.get("Util Max",0)),2)
            if r["Keputusan"]=="MODIFY" else 0,
        # MAINTAIN: sort by Util Max asc (util rendah = lebih aman)
        round(r.get("Util Max (%)",r.get("Util Max",0)),1)
            if r["Keputusan"]=="MAINTAIN" else 0,
        round(r.get("Unmet (%)",r.get("Unmet %",0)),2),
    ),axis=1)
    rank_df=rank_df.sort_values("_sort").reset_index(drop=True)
    rank_df["Rank"]=rank_df.index+1
    # Short label for chart (B/G/D hours only, no batch mode or growth)
    def _short_label(row):
        rank=int(row.get("Rank",0))
        if "Hari B" in row.index:
            bd,bh=int(row.get("Hari B",7)),int(row.get("Jam B",24))
            gd,gh=int(row.get("Hari G",7)),int(row.get("Jam G",24))
            dd,dh=int(row.get("Hari D",7)),int(row.get("Jam D",24))
            return f"#{rank} B{bd}D/{bh}H G{gd}D/{gh}H D{dd}D/{dh}H"
        return f"#{rank} "+str(row.get("Scenario","?"))[:12]
    rank_df["ChartLabel"]=rank_df.apply(_short_label,axis=1)

    n_m=(rank_df["Keputusan"]=="MAINTAIN").sum()
    n_mod=(rank_df["Keputusan"]=="MODIFY").sum()
    best=rank_df.iloc[0]; overall="MAINTAIN" if n_m>=n_mod else "MODIFY"

    kpi_items=[(str(len(rank_df)),"Total Skenario","#f0f6fc")]
    if n_m>0: kpi_items.append((str(n_m),"MAINTAIN","#3fb950"))
    if n_mod>0: kpi_items.append((str(n_mod),"MODIFY","#d29922"))
    best_disp=best.get('Label', best.get('Scenario','?'))
    kpi_items.append((best_disp,"Skenario Terbaik","#58a6ff"))
    kpi_cols=st.columns(len(kpi_items))
    for col,(val,lbl,clr) in zip(kpi_cols,kpi_items):
        with col:
            st.markdown(f'<div class="kpi-box" style="border-left-color:{clr};"><div class="kpi-label">{lbl}</div><div class="kpi-value" style="color:{clr};font-size:0.85rem;">{val}</div></div>',unsafe_allow_html=True)
    st.markdown("<br>",unsafe_allow_html=True)
    badge="badge-maintain" if overall=="MAINTAIN" else "badge-modify"
    st.markdown(f'<b>Keputusan Keseluruhan:</b> <span class="{badge}">{overall}</span>',unsafe_allow_html=True)
    st.markdown("<br>",unsafe_allow_html=True)

    # Chart + Top5 side by side
    top_chart=rank_df.head(min(12,len(rank_df)))
    fig_r=go.Figure()
    for lvl,clr in [("MAINTAIN","#3fb950"),("MODIFY","#d29922")]:
        sub=top_chart[top_chart["Keputusan"]==lvl]
        if sub.empty: continue
        _x_col=next((c for c in ["ChartLabel","Label","Scenario"] if c in sub.columns),"Scenario")
        _skor_col=next((c for c in sub.columns if "skor" in c.lower() or "score" in c.lower()),"")
        if not _skor_col: continue
        fig_r.add_trace(go.Bar(x=sub[_x_col],y=sub[_skor_col],name=lvl,marker_color=clr,
            text=[f"#{r}" for r in sub["Rank"]],textposition="outside",
            hovertemplate="<b>%{x}</b><br>Rank: %{text}<br>Skor: %{y:.3f}<extra></extra>"))
    # FIS threshold line removed (threshold now hardcoded)
    fig_r.update_layout(template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        height=280,barmode="group",legend=dict(orientation="h",y=-0.22),margin=dict(l=0,r=0,t=8,b=44),
        yaxis=dict(title="Skor",gridcolor="#21262d",range=[0,4.3]),xaxis=dict(gridcolor="#21262d"))

    _cc,_ct=st.columns([3,2])
    with _cc: st.plotly_chart(fig_r,use_container_width=True)
    with _ct:
        st.markdown('<div class="section-title">Top 5 Skenario</div>',unsafe_allow_html=True)
        # Merge sim factors for top 5
        # Top 5: show simulation output factors + decision
        _t5_new_fmt = "Hari B" in rank_df.columns
        if _t5_new_fmt:
            t5c=["Rank","Label","Hari B","Jam B","Hari G","Jam G","Hari D","Jam D","Batch Mode",
                 "Selesai (%)","Unmet (%)","Util B (%)","Util G (%)","Util D (%)","Keputusan"]
        else:
            t5c=["Rank","Scenario","Selesai (%)","Unmet (%)","Util B (%)","Util G (%)","Util D (%)","Keputusan"]
        t5c=[c for c in t5c if c in rank_df.columns]
        # Format numeric columns cleanly (avoid 99.000000)
        t5_show=rank_df.head(5)[t5c].copy()
        for col in [c for c in t5c if "%" in c or c in ["Selesai (%)","Unmet (%)"]]:
            if col in t5_show.columns:
                t5_show[col]=t5_show[col].round(1)
        t5_styled=t5_show.style.set_properties(
            subset=[c for c in ["Keputusan"] if c in t5c], **{"font-weight":"bold","color":"#f0f6fc"})        .format({c:"{:.1f}" for c in t5c if "%" in c})
        st.dataframe(t5_styled, use_container_width=True, hide_index=True)

    with st.expander("Semua skenario"):
        _new_fmt_all = "Hari B" in rank_df.columns
        if _new_fmt_all:
            ac=["Rank","Label","Hari B","Jam B","Hari G","Jam G","Hari D","Jam D","Batch Mode","Growth",
                "Target Demand (ton)","Produksi Selesai (ton)","Unmet Demand (ton)",
                "Tons B","Tons G","Tons D",
                "Selesai (%)","Unmet (%)","Util B (%)","Util G (%)","Util D (%)","Util Max (%)",
                "Skor FIS","Keputusan"]
        else:
            ac=["Rank","Scenario","Selesai (%)","Unmet (%)","Util B (%)","Util G (%)","Util D (%)","Skor FIS","Keputusan"]
        ac=[c for c in ac if c in rank_df.columns]
        st.dataframe(rank_df[ac], use_container_width=True, hide_index=True)
        st.caption(
            f"MODIFY: kapasitas tidak mencukupi target demand, ATAU utilisasi ≥ {util_warn}% "
            "(risiko kapasitas meski demand saat ini terpenuhi). "
            "MAINTAIN: kapasitas cukup dan utilisasi aman."
        )

    st.markdown("---")
    if n_mod==0:
        st.success("Semua skenario MAINTAIN — tidak diperlukan upgrade."); st.stop()

    # ═══ SECTION 2: DIAGNOSA & OPSI ══════════════════════════════════════════════
    st.markdown('<div class="section-title">Diagnosa Bottleneck & Rekomendasi</div>',unsafe_allow_html=True)

    sel_id=st.selectbox("Skenario untuk dianalisis:",rank_df["Scenario"].tolist(),index=0,
        format_func=lambda s:(
            (lambda r:
                f"Rank #{r['Rank'].values[0]}  —  "
                + str(r.get("Label", r.get("Scenario",r)).values[0])
                + f"  |  {r['Keputusan'].values[0]}"
            )(rank_df[rank_df["Scenario"]==s])
        ))
    sel_row=rank_df[rank_df["Scenario"]==sel_id].iloc[0]
    sel_orig=sel_row["_row"]

    if sel_row["Keputusan"]=="MAINTAIN":
        st.success(f"Skenario {sel_id}: MAINTAIN — kondisi aman."); st.stop()

    diag=diagnose_bottleneck(sel_orig)
    sev_clr={"KRITIS":"#f85149","TINGGI":"#d29922","SEDANG":"#58a6ff","RENDAH":"#3fb950"}
    cl,cr=st.columns([1,2])
    with cl:
        st.markdown(f"""<div class="dss-card">
          <div class="kpi-label">Primary Bottleneck</div>
          <div style="font-size:1.3rem;font-weight:700;color:#d29922;">{diag['primary_bottleneck']}</div>
          <div style="font-size:0.82rem;color:#8b949e;margin-top:6px;">
            Utilisasi: <b>{diag['max_util']}%</b> &nbsp;|&nbsp;
            <b style="color:{sev_clr.get(diag['severity'],'#8b949e')};">{diag['severity']}</b>
          </div>
          <div style="font-size:0.82rem;color:#8b949e;margin-top:4px;">Unmet: <b>{diag['unmet_ratio']:.1f}%</b></div>
        </div>""",unsafe_allow_html=True)
    with cr:
        lines=list(diag["utils"].keys()); utils=[diag["utils"][l] for l in lines]
        colors=["#d29922" if l==diag.get("primary_bottleneck","—") else "#58a6ff" for l in lines]
        fu=go.Figure(go.Bar(x=lines,y=utils,marker_color=colors,text=[f"{v:.1f}%" for v in utils],textposition="outside"))
        fu.add_hline(y=util_warn,line_dash="dot",line_color="#f85149",annotation_text=f"{util_warn}%")
        fu.update_layout(template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            height=200,margin=dict(l=0,r=0,t=8,b=16),yaxis=dict(range=[0,105],gridcolor="#21262d"),showlegend=False)
        st.plotly_chart(fu,use_container_width=True)

    options=recommend_options(diag,float(sel_orig.get("Unmet_Demand",0) or 0))
    sel_opt_id=st.radio("Pilih opsi upgrade:",[o["id"] for o in options],
        format_func=lambda x:f"Tier {next(o for o in options if o['id']==x)['tier']} — {next(o for o in options if o['id']==x)['label']}")
    sel_opt=next(o for o in options if o["id"]==sel_opt_id)

    st.markdown("---")

    # Jadwal lini baru — hanya tampil jika opsi melibatkan tambah lini baru
    _involves_new_line = sel_opt_id in ("new_line","multiline_BG_new")
    new_line_days, new_line_hrs = 7, 24  # defaults
    if _involves_new_line:
        with st.container():
            st.markdown("**Jadwal Operasi Lini Baru:**")
            _nlc1, _nlc2 = st.columns(2)
            with _nlc1:
                new_line_days = st.select_slider(
                    "Hari Kerja/Minggu", options=[5,6,7], value=7, key="nl_days_inline",
                    help="Jumlah hari operasi lini baru per minggu")
            with _nlc2:
                new_line_hrs = st.select_slider(
                    "Jam Kerja/Hari", options=[8,16,24], value=24, key="nl_hrs_inline",
                    help="Jam operasi lini baru per hari (kelipatan 8)")
            st.caption(f"Lini baru akan beroperasi {new_line_days}D/{new_line_hrs}H — "
                       f"Kapasitas dihitung dari kalibrasi throughput lini B/G existing.")

    # ═══ SECTION 3: ESTIMASI KAPASITAS ═══════════════════════════════════════════
    st.markdown('<div class="section-title">Estimasi Dampak Kapasitas</div>',unsafe_allow_html=True)
    st.markdown('<div style="color:#d29922;font-weight:600;font-size:0.82rem;margin-bottom:0.5rem;">⚠ Estimasi analitis — hasil perlu divalidasi sebelum keputusan investasi final.</div>',unsafe_allow_html=True)

    upd=estimate_upgrade(sel_orig,sel_opt_id,new_line_days=new_line_days,new_line_hrs=new_line_hrs)
    orig_fin=_s(sel_orig,"Finished_Ratio"); orig_unmet=_s(sel_orig,"Unmet_Demand")
    target=max(_s(sel_orig,"Target_Demand_Ton"),1)
    headroom=upd.get("Practical_Headroom",0)

    c1,c2,c3,c4,c5=st.columns(5)
    for col,lbl,bef,aft,up in [
        (c1,"Finished Ratio",f"{orig_fin:.1f}%",f"{upd['Finished_Ratio_new']:.1f}%",True),
        (c2,"Unmet Demand",f"{orig_unmet:,.0f} t",f"{upd['Unmet_Demand_new']:,.0f} t",False),
        (c3,"Tambahan Prod.","-",f"+{upd['Additional_Capacity']:,.0f} t",True),
        (c4,"Kap. Praktis","-",f"{upd.get('Max_Capacity_Practical',0):,.0f} t",True),
        (c5,"Headroom","-",f"+{headroom:,.0f} t",True),
    ]:
        clr="#3fb950" if up else "#f85149"
        with col:
            st.markdown(f'<div class="kpi-box" style="border-left-color:{clr};"><div class="kpi-label">{lbl}</div><div style="font-size:0.75rem;color:#8b949e;">{bef}</div><div class="kpi-value" style="color:{clr};font-size:1.1rem;">{aft}</div></div>',unsafe_allow_html=True)
    st.markdown("<br>",unsafe_allow_html=True)

    # Charts: Utilisasi + Tonase
    # ouk = old util key; supports both 'Util B' and 'Util B (%)' via .get()
    line_keys=[("Line B","Util B","Util_Filling_B_new","Tons_B","Tons_B_new"),
               ("Line G","Util G","Util_Filling_G_new","Tons_G","Tons_G_new"),
               ("Line D","Util D","Util_Filling_D_new","Tons_D","Tons_D_new")]
    if "Util_Filling_C_new" in upd:
        line_keys.append(("Line C (Baru)","-","Util_Filling_C_new","-","Tons_C_new"))
    lines,bu,au,bt,at_=[],[],[],[],[]
    for label,ouk,nuk,otk,ntk in line_keys:
        # Try both 'Util B' and 'Util B (%)' naming
        alt_uk=ouk.replace("Util ","Util ").rstrip()+" (%)" if ouk!="-" else "-"
        bv=float(sel_row.get(ouk, sel_row.get(alt_uk, sel_row.get(ouk.replace(" "," (%)"),0)))) if ouk!="-" else 0
        nv=upd.get(nuk,bv); ot=_s(sel_orig,otk) if otk!="-" else 0; nt=upd.get(ntk,ot)
        lines.append(label); bu.append(float(bv)); au.append(float(nv)); bt.append(float(ot)); at_.append(float(nt))

    cl,cr=st.columns(2)
    with cl:
        st.markdown('<div class="section-title">Utilisasi per Lini</div>',unsafe_allow_html=True)
        fc=go.Figure()
        fc.add_trace(go.Bar(x=lines,y=bu,name="Sebelum",marker_color="#484f58"))
        fc.add_trace(go.Bar(x=lines,y=au,name="Setelah",marker_color="#58a6ff"))
        fc.add_hline(y=util_warn,line_dash="dot",line_color="#f85149",annotation_text=f"{util_warn}%")
        fc.update_layout(template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            barmode="group",height=240,legend=dict(orientation="h",y=-0.25),margin=dict(l=0,r=0,t=8,b=44),
            yaxis=dict(title="%",gridcolor="#21262d",range=[0,110]))
        st.plotly_chart(fc,use_container_width=True)
    with cr:
        st.markdown('<div class="section-title">Tonase per Lini</div>',unsafe_allow_html=True)
        ft=go.Figure()
        ft.add_trace(go.Bar(x=lines,y=bt,name="Sebelum",marker_color="#484f58"))
        ft.add_trace(go.Bar(x=lines,y=at_,name="Setelah",marker_color="#3fb950"))
        ft.update_layout(template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            barmode="group",height=240,legend=dict(orientation="h",y=-0.25),margin=dict(l=0,r=0,t=8,b=44),
            yaxis=dict(title="ton",gridcolor="#21262d"))
        st.plotly_chart(ft,use_container_width=True)

    # Tabel perbandingan
    with st.expander("Tabel perbandingan"):
        rows=[("Finished Ratio",f"{orig_fin:.1f}%",f"{upd['Finished_Ratio_new']:.1f}%"),
              ("Unmet Demand",f"{orig_unmet:,.0f}",f"{upd['Unmet_Demand_new']:,.0f}"),
              ("Tons_B",f"{_s(sel_orig,'Tons_B'):,.0f}",f"{upd['Tons_B_new']:,.0f}"),
              ("Util_B",f"{sel_row['Util B']:.1f}%",f"{upd['Util_Filling_B_new']:.1f}%"),
              ("Tons_G",f"{_s(sel_orig,'Tons_G'):,.0f}",f"{upd['Tons_G_new']:,.0f}"),
              ("Util_G",f"{sel_row['Util G']:.1f}%",f"{upd['Util_Filling_G_new']:.1f}%"),
              ("Tons_D",f"{_s(sel_orig,'Tons_D'):,.0f}",f"{upd['Tons_D_new']:,.0f}"),
              ("Util_D",f"{sel_row['Util D']:.1f}%",f"{upd['Util_Filling_D_new']:.1f}%")]
        if "Tons_C_new" in upd:
            c_note="(cadangan — demand sudah terpenuhi B+G)" if upd.get("Tons_C_new",0)==0 else ""
            rows+=[("Tons_C (Lini Baru)",f"—",f"{upd['Tons_C_new']:,.0f} t {c_note}"),
                   ("Util_C","—",f"{upd['Util_Filling_C_new']:.1f}%")]
        rows.append(("Kapasitas Praktis (est.)","—",f"{upd.get('Max_Capacity_Practical',0):,.0f}"))
        st.dataframe(pd.DataFrame(rows,columns=["Kolom","Sebelum","Setelah"]),use_container_width=True,hide_index=True)

    # Note for special cases
    if "_note_c" in upd: st.info(upd["_note_c"])

    # Komponen mesin — SETELAH tabel perbandingan
    st.markdown("<br>",unsafe_allow_html=True)
    st.markdown("**Komponen:**")
    machine_cards(sel_opt["components"])

    st.markdown("---")

    # ═══ SECTION 4: FINANSIAL ════════════════════════════════════════════════════
    st.markdown('<div class="section-title">Kelayakan Finansial</div>',unsafe_allow_html=True)
    st.markdown('<div style="color:#f85149;font-weight:600;font-size:0.82rem;margin-bottom:0.8rem;">⚠ Semua angka biaya merupakan estimasi — konfirmasi ke supplier dan manajemen sebelum keputusan.</div>',unsafe_allow_html=True)

    capex_data=CAPEX_FN.get(sel_opt_id,lambda:{"total":0,"breakdown":{},"annual_opex_total":0})()
    total_capex=capex_data["total"]
    annual_opex=capex_data.get("annual_opex_total",0)
    _is_waspada = False  # WASPADA merged into MODIFY
    _add = upd.get("Additional_Capacity",0)
    _hdroom = upd.get("Practical_Headroom",0)
    # WASPADA: demand sudah 100%, benefit = headroom (buffer kapasitas masa depan)
    # MODIFY: demand belum 100%, benefit = tambahan produksi + headroom
    annual_add = _add + _hdroom  # NPV: additional production + headroom capacity
    fin=compute_financial(total_capex,annual_add,params,annual_opex_extra=annual_opex)
    N=int(params["project_lifetime_year"]); annual_roi=fin["roi_pct"]/N


    with st.expander("Rincian CAPEX & OPEX"):
        cl2,cr2=st.columns(2)
        with cl2:
            st.markdown("**CAPEX (investasi awal)**")
            bd_df=pd.DataFrame([(k,fmt_rp(v)) for k,v in capex_data.get("breakdown",{}).items()],columns=["Item","Biaya"])
            st.dataframe(bd_df,use_container_width=True,hide_index=True)
            st.markdown(f'<div style="font-size:1.15rem;font-weight:700;color:#f0f6fc;margin-top:10px;padding-top:8px;border-top:1px solid #21262d;">Total CAPEX: {fmt_rp(total_capex)}</div>',unsafe_allow_html=True)
        with cr2:
            st.markdown("**OPEX tahunan (estimasi)**")
            opex_items=[]
            if capex_data.get("annual_maintenance",0)>0:
                opex_items.append(("Perawatan mesin",fmt_rp(capex_data["annual_maintenance"])))
            if capex_data.get("annual_manpower",0)>0:
                opex_items.append(("Manpower (operator+QC)",fmt_rp(capex_data["annual_manpower"])))
            st.dataframe(pd.DataFrame(opex_items,columns=["Item","Biaya"]),use_container_width=True,hide_index=True)
            st.markdown(f'<div style="font-size:1.15rem;font-weight:700;color:#f0f6fc;margin-top:10px;padding-top:8px;border-top:1px solid #21262d;">Total OPEX / Tahun: {fmt_rp(annual_opex)}</div>',unsafe_allow_html=True)

    r_min=params["minimum_irr"]; pb_thr=params["payback_threshold_year"]
    # Cap extreme IRR/ROI for display
    _irr_pct=fin["irr_pct"] or 0
    _irr_disp=(f"≥200%" if _irr_pct>200 else (f"{_irr_pct:.1f}%" if fin["irr_pct"] else "N/A"))
    _roi_disp=(f"≥200%" if annual_roi>200 else f"{annual_roi:.1f}%")
    _pb_val=fin["payback_year"] or 99
    _pb_disp=(f"{_pb_val:.2f} thn" if fin["payback_year"] else "N/A")
    c1,c2,c3,c4=st.columns(4)
    for col,lbl,val,ok in [
        (c1,"NPV",fmt_rp(fin["npv"]),fin["npv"]>0),
        (c2,"IRR",_irr_disp,_irr_pct/100>=r_min),
        (c3,"ROI / Tahun",_roi_disp,annual_roi>=10),
        (c4,"Payback",_pb_disp,_pb_val<=pb_thr),
    ]:
        clr="#3fb950" if ok else "#f85149"
        with col:
            st.markdown(f'''<div class="kpi-box" style="border-left-color:{clr};"><div class="kpi-label">{lbl}</div><div class="kpi-value" style="color:{clr};font-size:1.1rem;">{val}</div></div>''',unsafe_allow_html=True)
    st.markdown("<br>",unsafe_allow_html=True)
    _fv,_fc=st.columns([1,2])
    with _fv:
        verdict="LAYAK" if fin["feasible"] else "TIDAK LAYAK"
        bv="badge-feasible" if fin["feasible"] else "badge-infeasible"
        st.markdown(f'<b>Verdict:</b> <span class="{bv}">{verdict}</span>',unsafe_allow_html=True)
        st.markdown("<br>",unsafe_allow_html=True)
        for flag,ok in fin["flags"].items():
            flag2="ROI/thn ≥ 10%" if "ROI" in flag else flag
            ok2=annual_roi>=10 if "ROI" in flag else ok
            st.markdown(f'<span style="color:{"#3fb950" if ok2 else "#f85149"};">{"✓" if ok2 else "✗"} {flag2}</span>',unsafe_allow_html=True)
    with _fc:
        _vpt=params["internal_value_per_ton"]*params["realization_factor"]
        _ann_b=annual_add*_vpt; N=int(params["project_lifetime_year"])
        _fin_rows=[
            ("CAPEX (investasi awal)",fmt_rp(total_capex),""),
            ("OPEX / tahun",fmt_rp(annual_opex),f"× {N} thn = {fmt_rp(annual_opex*N)}"),
            ("Manfaat kapasitas / tahun",fmt_rp(_ann_b),f"× {N} thn = {fmt_rp(_ann_b*N)}"),
            ("Selisih kumulatif","",fmt_rp(_ann_b*N-total_capex-annual_opex*N)),
        ]
        st.dataframe(pd.DataFrame(_fin_rows,columns=["Item","Per Tahun","Total"]),use_container_width=True,hide_index=True)
        if _irr_pct>150 or annual_roi>150:
            st.caption("Estimasi berdasarkan asumsi kapasitas yang tersedia terserap sepenuhnya oleh demand.")
        else:
            st.caption(f"Manfaat kapasitas = {annual_add:,.0f} ton × Rp {_vpt:,.0f}/ton/tahun.")
    # ── Nilai Tambah Kapasitas (independent of NPV sign) ─────────────────────
    # Untuk MODIFY: pakai Additional_Capacity (demand baru yang bisa dipenuhi)
    # NPV uses Additional_Capacity + Headroom as annual benefit basis
    # Both represent capacity value created by the upgrade
    # ── Basis Perhitungan Finansial ─────────────────────────────────────────────
    # Basis finansial explained in the table above

    # Break-even: minimum annual tons to make NPV positive
    annual_opex_total = annual_opex
    net_cf_per_ton = params["internal_value_per_ton"] * params["realization_factor"]
    if net_cf_per_ton > 0:
        breakeven_opex = annual_opex_total / net_cf_per_ton  # tons to cover OPEX
        capex_amort = total_capex / (N * 1e6) * 1e6  # rough annual CAPEX amortization
        breakeven_total = (annual_opex_total + capex_amort) / net_cf_per_ton


    with _fc:
        cfs=fin["cash_flows"]; yrs=list(range(len(cfs))); cum=np.cumsum(cfs).tolist()
        fig_cf=go.Figure()
        fig_cf.add_trace(go.Bar(x=yrs,y=[v/1e6 for v in cfs],marker_color=["#f85149"]+["#3fb950"]*(len(cfs)-1),showlegend=False))
        fig_cf.add_trace(go.Scatter(x=yrs,y=[v/1e6 for v in cum],mode="lines+markers",line=dict(color="#58a6ff",width=2),name="Kumulatif"))
        fig_cf.add_hline(y=0,line_color="#8b949e",line_width=1)
        fig_cf.update_layout(template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            height=220,margin=dict(l=0,r=0,t=8,b=16),xaxis=dict(title="Tahun",gridcolor="#21262d",tickvals=yrs),
            yaxis=dict(title="Rp Juta",gridcolor="#21262d"),legend=dict(font=dict(size=10)))
        st.plotly_chart(fig_cf,use_container_width=True)

    # Monte Carlo
    fc_df=get("forecast")
    if not fc_df.empty and "forecast_upper" in fc_df.columns and "forecast_lower" in fc_df.columns:
        st.markdown("---")

    # ── Rekomendasi Terpilih (restored) ──────────────────────────────────────────
    _chosen_label = sel_opt["label"]
    _chosen_tier  = sel_opt["tier"]
    _chosen_color = {"MAINTAIN":"#3fb950","MODIFY":"#d29922"}.get(
        sel_row.get("Keputusan","MODIFY"),"#d29922")
    _fin_ok = fin.get("npv",0) >= 0
    _verdict_label = "LAYAK" if _fin_ok else "TIDAK LAYAK"
    _verdict_color = "#3fb950" if _fin_ok else "#f85149"
    _comps_raw = sel_opt.get("components",[])
    # Format component list: {'key':..,'qty':..} → "NAMA MESIN ×qty"
    try:
        from modules.financial_calc import MACHINES as _MACH
    except Exception: _MACH={}
    _comps = []
    for _c in _comps_raw:
        if isinstance(_c, dict):
            _k = _c.get("key",""); _q = _c.get("qty",1)
            _nm = _MACH.get(_k,{}).get("name",_k.upper()) if _k else str(_c)
            _comps.append(f"{_nm} ×{_q}" if int(_q)>1 else _nm)
        else:
            _comps.append(str(_c))
    st.markdown(f'''
    <div class="dss-card" style="border:1px solid #30363d;border-radius:12px;padding:2rem;text-align:center;margin-bottom:1.5rem;">
      <div class="kpi-label" style="letter-spacing:0.15em;">REKOMENDASI TERPILIH</div>
      <div style="font-size:1.6rem;font-weight:800;color:#f0f6fc;margin:0.4rem 0;">
        Tier {_chosen_tier} — {_chosen_label}
      </div>
      <div style="font-size:1rem;color:#c9d1d9;font-weight:700;margin-bottom:0.5rem;">
        {sel_row.get("Label", sel_id)}
      </div>
      <span style="background:{_verdict_color};color:#fff;font-weight:700;padding:6px 22px;
        border-radius:8px;font-size:0.9rem;">{_verdict_label}</span>
      {"".join(f'<span style="display:inline-block;background:#161b22;border:1px solid #30363d;border-radius:6px;padding:4px 12px;margin:4px 3px;font-size:0.82rem;color:#c9d1d9;">{c}</span>' for c in _comps) if _comps else ""}
      <div style="font-size:0.78rem;color:#8b949e;margin-top:1rem;">
        KARAKTERISTIK SKENARIO
      </div>
      <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:.5rem;margin-top:0.4rem;">
        <span style="background:#161b22;border:1px solid #30363d;border-radius:4px;padding:4px 14px;font-size:.82rem;color:#c9d1d9;">Line B: {int(_s(sel_orig,"B_Days",_s(sel_orig,"Days_Per_Week",7)))}D/{int(_s(sel_orig,"B_Hours",_s(sel_orig,"Working_Hours",24)))}H</span>
        <span style="background:#161b22;border:1px solid #30363d;border-radius:4px;padding:4px 14px;font-size:.82rem;color:#c9d1d9;">Line G: {int(_s(sel_orig,"G_Days",_s(sel_orig,"Days_Per_Week",7)))}D/{int(_s(sel_orig,"G_Hours",_s(sel_orig,"Working_Hours",24)))}H</span>
        <span style="background:#161b22;border:1px solid #30363d;border-radius:4px;padding:4px 14px;font-size:.82rem;color:#c9d1d9;">Line D: {int(_s(sel_orig,"D_Days",7))}D/{int(_s(sel_orig,"D_Hours",24))}H</span>
        <span style="background:#161b22;border:1px solid #30363d;border-radius:4px;padding:4px 14px;font-size:.82rem;color:#c9d1d9;">Batch Mode: {str(sel_orig.get("Batch_Mode",sel_orig.get("WO_Mode",""))).strip()}</span>
        <span style="background:#161b22;border:1px solid #30363d;border-radius:4px;padding:4px 14px;font-size:.82rem;color:#c9d1d9;">Growth: {str(sel_orig.get("Growth","0")).strip()}</span>
        {"".join([f'<span style="background:#0d1117;border:1px solid #388bfd;border-radius:4px;padding:4px 14px;font-size:.82rem;color:#58a6ff;">Lini Baru: {new_line_days}D/{new_line_hrs}H</span>']) if _involves_new_line else ""}
      </div>
    </div>''',unsafe_allow_html=True)

    # ── Export Kapasitas (paling bawah) ──────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    import io as _io_exp
    # Determine config: D is always multiline, B/G depend on option
    _cfg_b = "multiline" if sel_opt_id in ("multiline_B","multiline_BG","multiline_BG_new") else "single"
    _cfg_g = "multiline" if sel_opt_id in ("multiline_G","multiline_BG","multiline_BG_new") else "single"
    _post_data = {
        "Scenario": sel_id,
        # Per-line schedule (for Perencanaan Produksi input)
        "B_Days": int(_s(sel_orig,"B_Days",_s(sel_orig,"Days_Per_Week",7))),
        "B_Hours": int(_s(sel_orig,"B_Hours",_s(sel_orig,"Working_Hours",24))),
        "G_Days": int(_s(sel_orig,"G_Days",_s(sel_orig,"Days_Per_Week",7))),
        "G_Hours": int(_s(sel_orig,"G_Hours",_s(sel_orig,"Working_Hours",24))),
        "D_Days": int(_s(sel_orig,"D_Days",7)),
        "D_Hours": int(_s(sel_orig,"D_Hours",24)),
        "Batch_Mode": str(sel_orig.get("Batch_Mode",sel_orig.get("WO_Mode",""))).strip(),
        "Growth": str(sel_orig.get("Growth","0")).strip(),
        # Post-upgrade capacity per lini
        "Tons_B": upd["Tons_B_new"], "Util_B": upd["Util_Filling_B_new"],
        "Line_B_Type":"SSS+BIB",    "Line_B_Config": _cfg_b,
        "Tons_G": upd["Tons_G_new"], "Util_G": upd["Util_Filling_G_new"],
        "Line_G_Type":"SSS+BIB",    "Line_G_Config": _cfg_g,
        "Tons_D": upd["Tons_D_new"], "Util_D": upd["Util_Filling_D_new"],
        "Line_D_Type":"SSS",         "Line_D_Config": "multiline",
    }
    if "Tons_C_new" in upd or _involves_new_line:
        _post_data.update({
            "C_Days": new_line_days if _involves_new_line else 7,
            "C_Hours": new_line_hrs if _involves_new_line else 24,
            "Tons_C": upd.get("Tons_C_new",0),
            "Util_C": upd.get("Util_Filling_C_new",0),
            "Line_C_Type": "SSS+BIB",
            "Line_C_Config": "single"
        })
    _csv_buf = _io_exp.StringIO()
    pd.DataFrame([_post_data]).to_csv(_csv_buf, index=False)
    st.download_button(
        "⬇ Export Kapasitas",
        data=_csv_buf.getvalue(),
        file_name=f"kapasitas_{sel_id}_{sel_opt_id}.csv",
        mime="text/csv",
        help="Download data kapasitas post-rekomendasi untuk digunakan di Perencanaan Produksi."
    )