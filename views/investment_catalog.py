import streamlit as st
import pandas as pd
import numpy as np
import io
import json
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
from modules.session import get, set_
from modules.financial_calc import MACHINES

def render():
    import streamlit as st
    import pandas as pd
    import json
    from pathlib import Path

    CATALOG_PATH = Path("data/machine_catalog.json")

    # ── Default catalog from financial_calc ────────────────────────────────────────
    def _default_catalog():
        from modules.financial_calc import MACHINES
        return {
            "machines": {k: dict(v) for k,v in MACHINES.items()},
            "packages": {
                "multiline_upgrade": {
                    "name": "Konversi Lini SSS+BIB → Multiline",
                    "components": [
                        {"key": "micro_auger", "qty": 6},
                        {"key": "shiputec",    "qty": 1},
                        {"key": "inclined_z",  "qty": 6},
                        {"key": "multi_strand","qty": 1},
                        {"key": "checkweigher","qty": 1},
                        {"key": "xray",        "qty": 1},
                    ],
                    "overhead_pct": 0.18,
                    "maintenance_annual": 240_000_000,
                    "note": "CAPEX target ~Rp 11.9B (per data Pak Ardi FBMI, Juni 2026)",
                },
                "stickpack_new_line": {
                    "name": "Penambahan Lini Stickpack Baru",
                    "components": [
                        {"key": "stickpack_filler", "qty": 1},
                        {"key": "checkweigher",      "qty": 1},
                        {"key": "xray",              "qty": 1},
                        {"key": "flat_belt",         "qty": 2},
                    ],
                    "overhead_pct": 0.18,
                    "maintenance_annual": 240_000_000,
                    "note": "Lini stickpack baru (format stick pack 15g)",
                },
            },
        }

    def load_catalog():
        if CATALOG_PATH.exists():
            with open(CATALOG_PATH) as f:
                return json.load(f)
        return _default_catalog()

    def save_catalog(cat):
        CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CATALOG_PATH, "w") as f:
            json.dump(cat, f, indent=2, ensure_ascii=False)

    def fmt_rp(v):
        try: return f"Rp {float(v):,.0f}"
        except: return str(v)

    # ── Page ───────────────────────────────────────────────────────────────────────
    st.markdown('<p class="page-title">Konfigurasi Investasi</p>',unsafe_allow_html=True)
    st.caption("Kelola katalog mesin, paket investasi, dan parameter finansial yang digunakan oleh seluruh menu DSS.")

    cat = load_catalog()
    _changed = False

    tab_mesin, tab_paket, tab_param = st.tabs(["🔧 Katalog Mesin", "📦 Paket Investasi", "📊 Parameter Finansial"])

    # ─────────────────────────────────────────────────────────────────────────────
    with tab_mesin:
        st.markdown("### Daftar Mesin")
        st.caption("Harga CAPEX dan tarif OPEX per mesin. Perubahan otomatis dipakai oleh menu Capacity Planning dan Production Allocation.")

        machines = cat["machines"]
        _to_delete = None

        for key, m in machines.items():
            with st.expander(f"**{m.get('name', key)}** — {fmt_rp(m.get('capex',0))}", expanded=False):
                c1,c2,c3 = st.columns([3,2,1])
                with c1:
                    m["name"]      = st.text_input("Nama Singkat", m.get("name",""), key=f"mn_{key}")
                    m["full_name"] = st.text_input("Nama Lengkap", m.get("full_name",""), key=f"mfn_{key}")
                    m["role"]      = st.text_input("Fungsi", m.get("role",""), key=f"mr_{key}")
                with c2:
                    m["capex"]     = st.number_input("CAPEX (Rp)", 0, 50_000_000_000,
                        int(m.get("capex",0)), 100_000_000, format="%d", key=f"mc_{key}")
                    m["opex_rate"] = st.number_input("OPEX Rate (%/thn)", 0.0, 30.0,
                        float(m.get("opex_rate",0.05))*100, 0.5, key=f"mo_{key}") / 100
                with c3:
                    m["url"] = st.text_input("URL Referensi", m.get("url",""), key=f"mu_{key}")
                    if st.button("🗑 Hapus", key=f"del_{key}", type="secondary"):
                        _to_delete = key
            _changed = True

        if _to_delete:
            del cat["machines"][_to_delete]
            save_catalog(cat)
            st.rerun()

        st.markdown("---")
        with st.expander("➕ Tambah Mesin Baru"):
            nc1,nc2 = st.columns(2)
            with nc1:
                new_key   = st.text_input("ID Mesin (unik, huruf kecil_)", key="new_mk")
                new_name  = st.text_input("Nama Singkat", key="new_mn")
                new_full  = st.text_input("Nama Lengkap", key="new_mfn")
            with nc2:
                new_capex = st.number_input("CAPEX (Rp)", 0, 50_000_000_000, 1_000_000_000, 100_000_000, format="%d", key="new_mc")
                new_opex  = st.number_input("OPEX Rate (%/thn)", 0.0, 30.0, 5.0, 0.5, key="new_mo")
                new_role  = st.text_input("Fungsi", key="new_mr")
            if st.button("Tambah Mesin", type="primary"):
                if new_key and new_name:
                    cat["machines"][new_key] = {
                        "name": new_name, "full_name": new_full, "capex": new_capex,
                        "opex_rate": new_opex/100, "role": new_role, "url": ""
                    }
                    save_catalog(cat)
                    st.success(f"Mesin '{new_name}' ditambahkan."); st.rerun()

        if st.button("💾 Simpan Perubahan Mesin", type="primary"):
            save_catalog(cat)
            st.success("Katalog mesin disimpan.")

    # ─────────────────────────────────────────────────────────────────────────────
    with tab_paket:
        st.markdown("### Paket Investasi")
        st.caption("Setiap paket adalah kombinasi mesin + biaya overhead. CAPEX total dihitung otomatis.")

        machines = cat["machines"]
        for pkg_key, pkg in cat["packages"].items():
            with st.expander(f"**{pkg.get('name', pkg_key)}**", expanded=True):
                pkg["name"]          = st.text_input("Nama Paket", pkg.get("name",""), key=f"pn_{pkg_key}")
                pkg["note"]          = st.text_input("Catatan/Sumber", pkg.get("note",""), key=f"pnt_{pkg_key}")
                pkg["maintenance_annual"] = st.number_input(
                    "Biaya Maintenance/Tahun (Rp)", 0, 2_000_000_000,
                    int(pkg.get("maintenance_annual", 240_000_000)), 10_000_000,
                    format="%d", key=f"pm_{pkg_key}",
                    help="Pak Ardi FBMI: Rp 20M/bulan = Rp 240M/tahun")
                pkg["overhead_pct"]  = st.slider("Overhead % (install+elektrikal+utilitas+komisioning)",
                    0.0, 0.40, float(pkg.get("overhead_pct",0.18)), 0.01, key=f"poh_{pkg_key}")

                # Components
                st.markdown("**Komponen:**")
                comps = pkg.get("components", [])
                _new_comps = []
                for ci, comp in enumerate(comps):
                    cc1,cc2,cc3 = st.columns([4,1,1])
                    with cc1:
                        ckey = st.selectbox("Mesin", list(machines.keys()),
                            index=list(machines.keys()).index(comp["key"]) if comp["key"] in machines else 0,
                            key=f"ck_{pkg_key}_{ci}", format_func=lambda k: machines.get(k,{}).get("name",k))
                    with cc2:
                        qty = st.number_input("Qty", 1, 20, int(comp.get("qty",1)), key=f"cq_{pkg_key}_{ci}")
                    with cc3:
                        st.caption(fmt_rp(machines.get(ckey,{}).get("capex",0) * qty))
                    _new_comps.append({"key": ckey, "qty": qty})
                pkg["components"] = _new_comps

                # Add component
                nc1x, nc2x = st.columns([4,1])
                with nc1x:
                    add_m = st.selectbox("+ Tambah komponen", list(machines.keys()),
                        key=f"add_{pkg_key}", format_func=lambda k: machines.get(k,{}).get("name",k))
                with nc2x:
                    add_q = st.number_input("Qty", 1, 20, 1, key=f"addq_{pkg_key}")
                if st.button(f"＋ Tambah ke {pkg['name']}", key=f"addbtn_{pkg_key}"):
                    pkg["components"].append({"key": add_m, "qty": add_q})
                    save_catalog(cat); st.rerun()

                # CAPEX summary
                machines_total = sum(machines.get(c["key"],{}).get("capex",0)*c["qty"] for c in pkg["components"])
                total_capex = int(machines_total * (1 + pkg["overhead_pct"]))
                st.markdown(f"**Total CAPEX estimasi: {fmt_rp(total_capex)}** "
                            f"(mesin {fmt_rp(machines_total)} + overhead {pkg['overhead_pct']*100:.0f}%)")
                st.caption(f"OPEX/thn: maintenance {fmt_rp(pkg['maintenance_annual'])} "
                           f"+ operator Rp 76.6M + QC Rp 76.6M = {fmt_rp(pkg['maintenance_annual']+153_294_220)}/thn")

        if st.button("💾 Simpan Paket", type="primary"):
            save_catalog(cat)
            st.success("Paket investasi disimpan.")

    # ─────────────────────────────────────────────────────────────────────────────
    with tab_param:
        st.markdown("### Parameter Finansial Global")
        st.caption("Parameter ini menjadi default di semua menu analisis kelayakan.")

        fp1,fp2,fp3 = st.columns(3)
        with fp1:
            st.markdown("**Basis Nilai**")
            st.info("**CO-MAN Savings:** Rp 1.500.000/ton\n\n"
                    "(Harga maklon Rp 6.5M − Biaya internal Rp 5M = Rp 1.5M selisih)")
            val_int = st.number_input("Nilai Internal/Ton (Rp)", 500_000, 10_000_000,
                2_100_000, 100_000, format="%d",
                help="Margin kontribusi per ton produksi internal (bukan CO-MAN)")
        with fp2:
            st.markdown("**Asumsi Finansial**")
            wacc_g = st.number_input("WACC/Discount Rate (%)",5,30,13,1,format="%d")
            tax_g  = st.number_input("Tarif Pajak (%)",0,40,25,1,format="%d")
            life_g = st.number_input("Umur Proyek (tahun)",3,20,10,1)
            life_a = st.number_input("Umur Ekonomis Aset (tahun)",3,30,10,1)
        with fp3:
            st.markdown("**Biaya Tenaga Kerja (per orang)**")
            umr = st.number_input("UMR Bekasi/bulan (Rp)",3_000_000,15_000_000,
                5_126_897,100_000,format="%d",help="UMR Bekasi 2024: Rp 5.127M")
            thr_m = st.number_input("Bulan THR",1,3,1)
            bpjs_pct = st.number_input("Faktor BPJS (%)",10,25,15,1,format="%d")
            annual_staff = int(umr * (12+thr_m) * (1+bpjs_pct/100))
            st.metric("Total/orang/tahun", fmt_rp(annual_staff))

        if st.button("💾 Simpan Parameter", type="primary"):
            cat["global_params"] = {
                "wacc": wacc_g/100, "tax_rate": tax_g/100,
                "project_life": life_g, "asset_life": life_a,
                "internal_value_per_ton": val_int,
                "umr_bekasi": umr, "annual_staff_cost": annual_staff,
            }
            save_catalog(cat); st.success("Parameter finansial disimpan.")

