import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path
import plotly.graph_objects as go
from modules.session import get, set_


def render():
    from modules.financial_calc import (
        MACHINES as _DEFAULT_MACHINES, DEFAULT_PARAMS, OVERHEAD, OVERHEAD_TOTAL,
        ANNUAL_OPERATOR, ANNUAL_QC, ANNUAL_MAINTENANCE_FBMI, fmt_rp,
        compute_financial, _load_fp_machines, _load_fp_capex_general,
        _load_fp_opex_general, _load_fp_financial,
    )

    CATALOG_PATH = Path("data/machine_catalog.json")
    FP_PATH      = Path("data/Financial_Param.xlsx")

    def load_catalog():
        if CATALOG_PATH.exists():
            with open(CATALOG_PATH) as f:
                cat = json.load(f)
            # Pastikan key yang dibutuhkan ada
            cat.setdefault("machines",      {k: dict(v) for k, v in _DEFAULT_MACHINES.items()})
            cat.setdefault("packages",      _default_packages())
            cat.setdefault("global_params", {k: v for k, v in DEFAULT_PARAMS.items()})
            cat.setdefault("capex_overhead", OVERHEAD)
            cat.setdefault("opex_manpower",  {
                "operator_annual": ANNUAL_OPERATOR,
                "qc_annual":       ANNUAL_QC,
                "maintenance_annual": ANNUAL_MAINTENANCE_FBMI,
            })
            return cat
        return _build_default_catalog()

    def _default_packages():
        return {
            "multiline_upgrade": {
                "name": "Upgrade SSS/BIB → Multiline",
                "components": [],
                "overhead_pct": OVERHEAD_TOTAL,
                "maintenance_annual": ANNUAL_MAINTENANCE_FBMI,
                "note": "Konversi lini existing ke multiline (CAPEX target ~Rp 11.9B, Pak Ardi FBMI)",
            },
            "stickpack_new_line": {
                "name": "Penambahan Lini Stickpack",
                "components": [],
                "overhead_pct": OVERHEAD_TOTAL,
                "maintenance_annual": ANNUAL_MAINTENANCE_FBMI,
                "note": "Lini stickpack baru (format 15g)",
            },
        }

    def _build_default_catalog():
        return {
            "machines":       {k: dict(v) for k, v in _DEFAULT_MACHINES.items()},
            "packages":       _default_packages(),
            "global_params":  {k: v for k, v in DEFAULT_PARAMS.items()},
            "capex_overhead": OVERHEAD,
            "opex_manpower": {
                "operator_annual":    ANNUAL_OPERATOR,
                "qc_annual":          ANNUAL_QC,
                "maintenance_annual": ANNUAL_MAINTENANCE_FBMI,
            },
        }

    def save_catalog(cat):
        CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CATALOG_PATH, "w") as f:
            json.dump(cat, f, indent=2, ensure_ascii=False)

    # ── Halaman ────────────────────────────────────────────────────────────────
    st.markdown('<div class="page-title">PARAMETER INVESTASI</div>', unsafe_allow_html=True)
    st.caption("Kelola katalog mesin, paket investasi, dan parameter finansial. "
               "Semua perubahan langsung digunakan oleh menu Perencanaan Kapasitas dan Alokasi Produksi.")

    if FP_PATH.exists():
        st.success(f"✓ Data dimuat dari: `{FP_PATH}` — edit di sini untuk override default.", icon=None)
    else:
        st.warning("File `data/Financial_Param.xlsx` tidak ditemukan. Menggunakan nilai default.")

    cat      = load_catalog()
    machines = cat["machines"]

    tab_mesin, tab_paket, tab_capex, tab_opex, tab_param = st.tabs([
        "⚙ Katalog Mesin",
        "📦 Paket Investasi",
        "🏗 Overhead CAPEX",
        "💼 OPEX & Manpower",
        "📊 Parameter Finansial",
    ])

    # ─── TAB 1: KATALOG MESIN ────────────────────────────────────────────────
    with tab_mesin:
        st.markdown("#### Daftar Mesin")
        st.caption("Harga dan spesifikasi mesin. Perubahan langsung dipakai di kalkulasi CAPEX paket investasi.")

        # Filter per role
        all_roles = sorted({m.get("role", m.get("name","?")) for m in machines.values()})
        sel_role  = st.selectbox("Filter Komponen", ["Semua"] + all_roles, key="mesin_role")

        _to_delete = None
        for key, m in machines.items():
            role = m.get("role", m.get("name","?"))
            if sel_role != "Semua" and role != sel_role:
                continue
            with st.expander(f"**{m.get('full_name', key)}** — {fmt_rp(m.get('capex',0))} | {m.get('capacity_kg_hr',0):.0f} kg/hr", expanded=False):
                c1, c2, c3 = st.columns([3, 2, 1])
                with c1:
                    m["full_name"]   = st.text_input("Nama Mesin",      m.get("full_name",""),  key=f"mfn_{key}")
                    m["role"]        = st.text_input("Komponen/Fungsi", m.get("role",""),        key=f"mr_{key}")
                    fmts = st.text_input("Format (pisah |)",
                        "|".join(m.get("format_compat",[])), key=f"mfmt_{key}",
                        help="Contoh: SSS|BIB atau STICKPACK")
                    m["format_compat"] = [x.strip() for x in fmts.split("|") if x.strip()]
                with c2:
                    m["capex"]        = st.number_input("CAPEX (Rp)", 0, 50_000_000_000,
                        int(m.get("capex",0)), 10_000_000, format="%d", key=f"mc_{key}")
                    m["opex_per_ton"] = st.number_input("OPEX/Ton (Rp)", 0, 1_000_000,
                        int(m.get("opex_per_ton",0)), 5_000, format="%d", key=f"mot_{key}")
                    m["capacity_kg_hr"] = st.number_input("Kapasitas (kg/hr)", 0.0, 5000.0,
                        float(m.get("capacity_kg_hr",0)), 10.0, key=f"mkghr_{key}")
                with c3:
                    m["is_core"] = st.checkbox("Core", m.get("is_core", True), key=f"mic_{key}")
                    m["url"]     = st.text_input("URL Ref", m.get("url",""), key=f"mu_{key}")
                    if st.button("🗑 Hapus", key=f"del_{key}", type="secondary"):
                        _to_delete = key

        if _to_delete:
            del cat["machines"][_to_delete]
            save_catalog(cat); st.rerun()

        st.markdown("---")
        with st.expander("➕ Tambah Mesin Baru"):
            na1, na2 = st.columns(2)
            with na1:
                new_key   = st.text_input("ID (unik, lowercase_)", key="nk")
                new_full  = st.text_input("Nama Mesin", key="nfn")
                new_role  = st.text_input("Komponen/Fungsi", key="nr")
                new_fmt   = st.text_input("Format (SSS|BIB|STICKPACK)", key="nfmt")
            with na2:
                new_capex = st.number_input("CAPEX (Rp)", 0, 50_000_000_000, 500_000_000, 10_000_000, format="%d", key="ncpx")
                new_opex  = st.number_input("OPEX/Ton (Rp)", 0, 1_000_000, 100_000, 5_000, format="%d", key="nopt")
                new_kghr  = st.number_input("Kapasitas (kg/hr)", 0.0, 5000.0, 100.0, key="nkghr")
                new_core  = st.checkbox("Core", True, key="nic")
            if st.button("Tambah Mesin", type="primary", key="add_machine"):
                if new_key and new_full:
                    cat["machines"][new_key] = {
                        "full_name": new_full, "role": new_role, "capex": new_capex,
                        "opex_per_ton": new_opex, "capacity_kg_hr": new_kghr,
                        "format_compat": [x.strip() for x in new_fmt.split("|") if x.strip()],
                        "is_core": new_core, "opex_rate": 0.05, "url": "",
                    }
                    save_catalog(cat); st.success(f"Mesin '{new_full}' ditambahkan."); st.rerun()

        if st.button("💾 Simpan Katalog Mesin", type="primary", key="save_mesin"):
            save_catalog(cat); st.success("Katalog mesin disimpan.")

    # ─── TAB 2: PAKET INVESTASI ──────────────────────────────────────────────
    with tab_paket:
        st.markdown("#### Paket Investasi")
        st.caption("Setiap paket = kombinasi mesin + overhead. CAPEX total dihitung otomatis.")

        for pkg_key, pkg in cat["packages"].items():
            with st.expander(f"**{pkg.get('name', pkg_key)}**", expanded=True):
                pkg["name"] = st.text_input("Nama Paket", pkg.get("name",""), key=f"pn_{pkg_key}")
                pkg["note"] = st.text_input("Catatan", pkg.get("note",""), key=f"pnt_{pkg_key}")
                pkg["maintenance_annual"] = st.number_input(
                    "Maintenance/Tahun (Rp)", 0, 2_000_000_000,
                    int(pkg.get("maintenance_annual", ANNUAL_MAINTENANCE_FBMI)),
                    10_000_000, format="%d", key=f"pm_{pkg_key}",
                    help="Pak Ardi FBMI: Rp 20M/bulan = Rp 240M/tahun")

                st.markdown("**Komponen Mesin:**")
                comps     = pkg.get("components", [])
                new_comps = []
                total_machine = 0
                for ci, comp in enumerate(comps):
                    cc1, cc2, cc3 = st.columns([5, 1, 1])
                    with cc1:
                        ckey = st.selectbox(
                            "Mesin", list(machines.keys()),
                            index=list(machines.keys()).index(comp["key"]) if comp["key"] in machines else 0,
                            key=f"ck_{pkg_key}_{ci}",
                            format_func=lambda k: machines.get(k,{}).get("full_name", k))
                    with cc2:
                        qty = st.number_input("Qty", 1, 20, int(comp.get("qty",1)), key=f"cq_{pkg_key}_{ci}")
                    with cc3:
                        unit_capex = machines.get(ckey, {}).get("capex", 0)
                        st.caption(fmt_rp(unit_capex * qty))
                        total_machine += unit_capex * qty
                    new_comps.append({"key": ckey, "qty": qty})
                pkg["components"] = new_comps

                # Tambah komponen baru
                ac1, ac2, ac3 = st.columns([5, 1, 1])
                with ac1:
                    add_m = st.selectbox("+ Tambah", list(machines.keys()), key=f"add_{pkg_key}",
                        format_func=lambda k: machines.get(k,{}).get("full_name", k))
                with ac2:
                    add_q = st.number_input("Qty", 1, 20, 1, key=f"addq_{pkg_key}")
                with ac3:
                    if st.button("＋", key=f"addbtn_{pkg_key}"):
                        pkg["components"].append({"key": add_m, "qty": add_q})
                        save_catalog(cat); st.rerun()

                # CAPEX summary
                overhead_pct  = OVERHEAD_TOTAL
                overhead_amt  = int(total_machine * overhead_pct)
                from modules.financial_calc import COMMISSIONING_FIXED
                total_capex   = int(total_machine + overhead_amt + COMMISSIONING_FIXED)
                pkg["overhead_pct"] = overhead_pct

                st.markdown(f"""
**Estimasi CAPEX Total: {fmt_rp(total_capex)}**
- Mesin: {fmt_rp(total_machine)}
- Overhead ({overhead_pct*100:.0f}%): {fmt_rp(overhead_amt)}
- Komisioning & Training: {fmt_rp(COMMISSIONING_FIXED)}
""")
                st.caption(f"OPEX/tahun: Maintenance {fmt_rp(pkg['maintenance_annual'])} "
                           f"+ Operator {fmt_rp(ANNUAL_OPERATOR)} + QC {fmt_rp(ANNUAL_QC)} "
                           f"= {fmt_rp(pkg['maintenance_annual'] + ANNUAL_OPERATOR + ANNUAL_QC)}")

        # Tambah paket baru
        st.markdown("---")
        with st.expander("➕ Tambah Paket Baru"):
            np1, np2 = st.columns(2)
            with np1:
                npkg_key  = st.text_input("ID Paket (unik, lowercase_)", key="npk")
                npkg_name = st.text_input("Nama Paket", key="npn")
            with np2:
                npkg_note = st.text_input("Catatan", key="npnt")
            if st.button("Buat Paket", type="primary", key="create_pkg"):
                if npkg_key and npkg_name:
                    cat["packages"][npkg_key] = {
                        "name": npkg_name, "note": npkg_note,
                        "components": [], "overhead_pct": OVERHEAD_TOTAL,
                        "maintenance_annual": ANNUAL_MAINTENANCE_FBMI,
                    }
                    save_catalog(cat); st.success(f"Paket '{npkg_name}' dibuat."); st.rerun()

        if st.button("💾 Simpan Paket", type="primary", key="save_paket"):
            save_catalog(cat); st.success("Paket investasi disimpan.")

    # ─── TAB 3: OVERHEAD CAPEX ───────────────────────────────────────────────
    with tab_capex:
        st.markdown("#### Overhead CAPEX")
        st.caption("Persentase overhead diterapkan ke total harga mesin untuk menghitung CAPEX total.")

        overhead = cat.get("capex_overhead", OVERHEAD)
        st.markdown("**Overhead % dari total harga mesin:**")
        oh_cols   = st.columns(len(overhead))
        new_overhead = {}
        for i, (k, v) in enumerate(overhead.items()):
            with oh_cols[i]:
                new_overhead[k] = st.number_input(
                    k, 0.0, 50.0, float(v)*100, 0.5, key=f"oh_{k}") / 100
        cat["capex_overhead"] = new_overhead

        from modules.financial_calc import COMMISSIONING_FIXED as _cf
        st.markdown(f"**Biaya Tetap Tambahan:**")
        sc1, sc2 = st.columns(2)
        with sc1:
            st.metric("Komisioning", fmt_rp(_cf * 0.7))
        with sc2:
            st.metric("Training", fmt_rp(_cf * 0.3))
        st.caption(f"Total komisioning + training: {fmt_rp(_cf)} (dapat diubah di `financial_calc.py`)")

        new_total = sum(new_overhead.values()) * 100
        st.info(f"Total overhead: **{new_total:.1f}%** dari harga mesin")

        if st.button("💾 Simpan Overhead", type="primary", key="save_oh"):
            save_catalog(cat); st.success("Overhead CAPEX disimpan.")

    # ─── TAB 4: OPEX & MANPOWER ─────────────────────────────────────────────
    with tab_opex:
        st.markdown("#### OPEX & Manpower")
        st.caption("Biaya operasional tahunan untuk lini baru. Sumber: Pak Ardi FBMI & UMR Bekasi.")

        opex = cat.get("opex_manpower", {
            "operator_annual": ANNUAL_OPERATOR,
            "qc_annual": ANNUAL_QC,
            "maintenance_annual": ANNUAL_MAINTENANCE_FBMI,
        })

        oc1, oc2, oc3 = st.columns(3)
        with oc1:
            st.markdown("**Maintenance**")
            opex["maintenance_annual"] = st.number_input(
                "Biaya Maintenance/Tahun (Rp)", 0, 1_000_000_000,
                int(opex.get("maintenance_annual", ANNUAL_MAINTENANCE_FBMI)),
                5_000_000, format="%d", key="om_maint",
                help="Pak Ardi FBMI: Rp 20 juta/bulan = Rp 240M/tahun")
            st.caption(f"≈ {fmt_rp(opex['maintenance_annual']/12)}/bulan")

        with oc2:
            st.markdown("**Operator (per orang)**")
            umr      = st.number_input("UMR Bekasi/bulan (Rp)", 3_000_000, 15_000_000,
                5_126_897, 100_000, format="%d", key="om_umr",
                help="UMR Bekasi 2024: Rp 5.127M")
            thr_m    = st.number_input("THR (bulan gaji)", 1, 3, 1, key="om_thr")
            bpjs_pct = st.number_input("BPJS (%)", 10, 25, 15, 1, key="om_bpjs")
            op_annual = int(umr * (12 + thr_m) * (1 + bpjs_pct/100))
            opex["operator_annual"] = op_annual
            st.metric("Total/orang/tahun", fmt_rp(op_annual))

        with oc3:
            st.markdown("**QC (per orang)**")
            umr_qc   = st.number_input("UMR Bekasi/bulan (Rp)", 3_000_000, 15_000_000,
                5_126_897, 100_000, format="%d", key="om_umrqc")
            thr_qc   = st.number_input("THR (bulan gaji)", 1, 3, 1, key="om_thrqc")
            bpjs_qc  = st.number_input("BPJS (%)", 10, 25, 15, 1, key="om_bpjsqc")
            qc_annual = int(umr_qc * (12 + thr_qc) * (1 + bpjs_qc/100))
            opex["qc_annual"] = qc_annual
            st.metric("Total/orang/tahun", fmt_rp(qc_annual))

        total_opex = opex["maintenance_annual"] + opex["operator_annual"] + opex["qc_annual"]
        st.info(f"**Total OPEX/tahun (lini baru): {fmt_rp(total_opex)}**\n\n"
                f"Maintenance {fmt_rp(opex['maintenance_annual'])} + "
                f"Operator {fmt_rp(opex['operator_annual'])} + "
                f"QC {fmt_rp(opex['qc_annual'])}")
        cat["opex_manpower"] = opex

        if st.button("💾 Simpan OPEX", type="primary", key="save_opex"):
            save_catalog(cat); st.success("Parameter OPEX disimpan.")

    # ─── TAB 5: PARAMETER FINANSIAL ─────────────────────────────────────────
    with tab_param:
        st.markdown("#### Parameter Finansial Global")
        st.caption(
            "Parameter ini digunakan di seluruh perhitungan kelayakan finansial. "
            "Sumber referensi: model valuasi Fonterra/Lactalis Group.")

        gp = cat.get("global_params", {k: v for k, v in DEFAULT_PARAMS.items()})

        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            st.markdown("**Asumsi Dasar**")
            gp["discount_rate"]         = st.number_input(
                "Discount Rate / WACC (%)", 5.0, 30.0,
                float(gp.get("discount_rate", 0.12))*100, 0.5, key="gp_dr") / 100
            gp["project_lifetime_year"] = st.number_input(
                "Umur Proyek (tahun)", 3, 20,
                int(gp.get("project_lifetime_year", 5)), 1, key="gp_pl")
            gp["useful_life_year"]      = st.number_input(
                "Umur Ekonomis Aset (tahun, untuk depresiasi)", 3, 20,
                int(gp.get("useful_life_year", 5)), 1, key="gp_ul",
                help="Dasar perhitungan depresiasi straight-line (tax shield)")
            gp["tax_rate"]              = st.number_input(
                "Tarif Pajak Korporasi (%)", 0.0, 40.0,
                float(gp.get("tax_rate", 0.25))*100, 1.0, key="gp_tax") / 100

        with pc2:
            st.markdown("**Threshold Kelayakan**")
            gp["minimum_npv"]           = st.number_input(
                "NPV Minimum (Rp)", -1_000_000_000, 5_000_000_000,
                int(gp.get("minimum_npv", 0)), 100_000_000, format="%d", key="gp_npv")
            gp["minimum_irr"]           = st.number_input(
                "IRR Minimum (%)", 5.0, 50.0,
                float(gp.get("minimum_irr", 0.15))*100, 0.5, key="gp_irr") / 100
            gp["minimum_roi"]           = st.number_input(
                "ROI Minimum (%)", 5.0, 100.0,
                float(gp.get("minimum_roi", 0.25))*100, 1.0, key="gp_roi") / 100
            gp["payback_threshold_year"] = st.number_input(
                "Payback Maksimal (tahun)", 1, 10,
                int(gp.get("payback_threshold_year", 3)), 1, key="gp_pb")

        with pc3:
            st.markdown("**Nilai Benefit**")
            gp["internal_value_per_ton"] = st.number_input(
                "Nilai Internal/Ton (Rp)", 500_000, 10_000_000,
                int(gp.get("internal_value_per_ton", 2_100_000)), 100_000,
                format="%d", key="gp_ivt",
                help="Margin kontribusi per ton produksi internal")
            gp["maklon_cost_per_ton"]    = st.number_input(
                "Biaya Maklon/Ton (Rp)", 1_000_000, 20_000_000,
                int(gp.get("maklon_cost_per_ton", 6_500_000)), 100_000,
                format="%d", key="gp_mct",
                help="Biaya total CO-MAN per ton (harga beli dari pihak ketiga)")
            gp["internal_cost_per_ton"]  = st.number_input(
                "Biaya Produksi Internal/Ton (Rp)", 500_000, 15_000_000,
                int(gp.get("internal_cost_per_ton", 5_000_000)), 100_000,
                format="%d", key="gp_ict",
                help="Biaya produksi internal per ton")
            savings = gp["maklon_cost_per_ton"] - gp["internal_cost_per_ton"]
            st.metric("Savings per Ton (Maklon→Internal)", fmt_rp(savings))
            gp["realization_factor"]     = st.number_input(
                "Realization Factor", 0.50, 1.00,
                float(gp.get("realization_factor", 0.75)), 0.05, key="gp_rf",
                help="Faktor koreksi: berapa % dari demand forecast yang benar-benar terealisasi")

        # Preview kalkulasi
        st.markdown("---")
        st.markdown("**Preview Kalkulasi Cepat**")
        prev1, prev2 = st.columns(2)
        with prev1:
            test_capex = st.number_input("CAPEX Test (Rp)", 1_000_000_000, 20_000_000_000,
                11_900_000_000, 500_000_000, format="%d", key="prev_capex",
                help="Referensi: ~Rp 11.9B per data Pak Ardi FBMI")
            test_ton   = st.number_input("Volume Tambahan/Tahun (ton)", 100, 10000, 1200, 100, key="prev_ton")

        with prev2:
            opex_man = cat["opex_manpower"]
            test_opex = opex_man.get("maintenance_annual", ANNUAL_MAINTENANCE_FBMI) + \
                        opex_man.get("operator_annual", ANNUAL_OPERATOR) + \
                        opex_man.get("qc_annual", ANNUAL_QC)
            gp["maintenance_annual"] = opex_man.get("maintenance_annual", ANNUAL_MAINTENANCE_FBMI)

            from modules.financial_calc import compute_financial
            result = compute_financial(test_capex, test_ton, gp, test_opex)
            st.markdown(f"""
| Metrik | Nilai |
|--------|-------|
| NPV | {fmt_rp(result['npv'])} |
| IRR | {f"{result['irr_pct']:.1f}%" if result['irr_pct'] else "N/A"} |
| ROI/tahun | {result['roi_pct']:.1f}% |
| Payback | {f"{result['payback_year']:.1f} tahun" if result['payback_year'] else "N/A"} |
| FCF/tahun | {fmt_rp(result['annual_fcf'])} |
| LAYAK | {"✅ Ya" if result['feasible'] else "❌ Tidak"} |
""")
        cat["global_params"] = gp
        if st.button("💾 Simpan Parameter Finansial", type="primary", key="save_param"):
            save_catalog(cat); st.success("Parameter finansial disimpan.")

    # ── Simpan semua ──────────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("💾 SIMPAN SEMUA PERUBAHAN", type="primary", key="save_all"):
        save_catalog(cat)
        set_("investment_catalog", cat)
        st.success("Semua perubahan disimpan ke katalog investasi.")
        st.rerun()
