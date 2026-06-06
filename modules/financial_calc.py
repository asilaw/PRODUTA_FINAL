"""
modules/financial_calc.py
Kalkulasi kelayakan finansial investasi kapasitas filling line.
Semua angka biaya bersifat estimasi — perlu konfirmasi ke supplier/manajemen.
"""
import numpy as np
import numpy_financial as npf

# ── Rupiah formatter ──────────────────────────────────────────────────────────
def fmt_rp(amount: float) -> str:
    """Format Rupiah dengan titik sebagai pemisah ribuan (format Indonesia)."""
    # Round to nearest 1000 to avoid floating point noise
    amount = round(amount)
    # Indonesian format: dots as thousands separator
    return "Rp " + f"{amount:,}".replace(",", ".")


# ── Machine catalog ───────────────────────────────────────────────────────────
# CAPEX per unit (Rp)
# ── Machine Catalog — Prices per Pak Ardi FBMI (June 2026) ──────────────────
# CAPEX target multiline upgrade: ~Rp 11.9B total (incl. install/electrical/utilities)
# Maintenance: Rp 240M/year (Rp 20M/month per Pak Ardi)
# Operator: UMR Bekasi 2024 Rp 5.127M/bln × 13 bln × 1.15 BPJS ≈ Rp 76.6M/orang/thn
MACHINES = {
    "micro_auger": {
        "name":      "MICRO AUGER",
        "full_name": "MICRO AUGER DOSING UNIT",
        "capex":     600_000_000,   # updated: Rp 600M per unit (×6 = 3.6B)
        "opex_rate": 0.05,
        "url":       "https://www.dahepowderpacking.com/auger-filler/auger-powder-fillers.html",
        "role":      "Dosing",
        "img":       "micro_auger.jpg",
    },
    "shiputec": {
        "name":      "MULTILINE FILLER",
        "full_name": "MULTILINE POWDER PACKAGING MACHINE",
        "capex":     3_500_000_000,   # Pak Ardi: Rp 3.5B (China), Rp 5-7B (Europe)
        "opex_rate": 0.09,
        "url":       "http://www.shiputec.com/multi-lane-powder-sachet-packaging-machine-product/",
        "role":      "Filling",
        "img":       "shiputec.jpg",
    },
    "inclined_z": {
        "name":      "INCLINED CONVEYOR",
        "full_name": "INCLINED Z-CONVEYOR",
        "capex":     200_000_000,   # updated: Rp 200M per unit (×6 = 1.2B)
        "opex_rate": 0.03,
        "url":       "http://www.alibaba.com/product-detail/Z-Structure-Lifting-Belt-Conveyer-Factory_60279635436.html",
        "role":      "Transfer",
        "img":       "inclined_z.jpg",
    },
    "multi_strand": {
        "name":      "MULTI-STRAND CONVEYOR",
        "full_name": "MULTI-STRAND CONVEYOR",
        "capex":     1_000_000_000,  # updated: Rp 1B
        "opex_rate": 0.03,
        "url":       "https://www.packworld.com/leaders-new/machinery/conveying-accumulation/product/13365302/glideline-multistrand-pallet-handling-conveyor-system",
        "role":      "Transfer",
        "img":       "multi_strand.jpg",
    },
    "feeder_ams": {
        "name":      "SCREW FEEDER",
        "full_name": "FLEXIBLE SCREW FEEDER",
        "capex":     235_000_000,
        "opex_rate": 0.04,
        "url":       "https://www.amsfilling.com/infeed-systems/",
        "role":      "Feeding",
        "img":       "feeder_ams.jpg",
    },
    "auger_bgl": {
        "name":      "AUGER DOSING",
        "full_name": "AUGER DOSING MACHINE",
        "capex":     270_000_000,
        "opex_rate": 0.05,
        "url":       "https://www.made-in-china.com/showroom/ericli1/product-detailRMeEbxKlaopY/China-Auger-Filling-dosing-Machine-BGL-3AL-.html",
        "role":      "Dosing",
        "img":       "auger_bgl.jpg",
    },
    "wolf_vpc250": {
        "name":      "VERTICAL FILLER",
        "full_name": "VERTICAL PACKAGING MACHINE",
        "capex":     1_150_000_000,
        "opex_rate": 0.09,
        "url":       "https://wolf-packaging.com/machine-overview/2",
        "role":      "Filling",
        "img":       "wolf_vpc250.jpg",
    },
    "flat_belt": {
        "name":      "BELT CONVEYOR",
        "full_name": "FLAT BELT CONVEYOR",
        "capex":     40_000_000,
        "opex_rate": 0.03,
        "url":       "https://shopee.co.id/Conveyor-Belt-150x25x75cm-With-Bracket-and-Sensor-Speed-adjustable.-i.17565655.5649091461",
        "role":      "Transfer",
        "img":       "flat_belt.jpg",
    },
    "checkweigher": {
        "name":      "CHECKWEIGHER",
        "full_name": "INLINE CHECKWEIGHER WITH AIR REJECTOR",
        "capex":     500_000_000,   # updated: Rp 500M
        "opex_rate": 0.06,
        "url":       "https://hengtianxia.en.made-in-china.com/product/zQUpGrkoqsYV/China-High-Precision-Speed-Inline-Packaging-Bag-Box-Sachet-Bottle-Conveyor-Checkweigher-with-Air-Blast-Rejector.html",
        "role":      "Inspeksi",
        "img":       "checkweigher.jpg",
    },
    "xray": {
        "name":      "X-RAY DETECTOR",
        "full_name": "X-RAY FOREIGN BODY DETECTION SYSTEM",
        "capex":     750_000_000,   # updated: Rp 750M
        "opex_rate": 0.06,
        "url":       "https://www.foodmanvision.com/product/x-ray-inspection-system-for-packaged-products-fxr-3017/#overview",
        "role":      "Inspeksi",
        "img":       "xray.jpg",
    },
    # ── Stickpack line ───────────────────────────────────────────────────────────
    "stickpack_filler": {
        "name":      "STICKPACK FILLER",
        "full_name": "Filler Stickpack",
        "capex":     3_500_000_000,  # updated: same China filler range Rp 3.5B
        "opex_rate": 0.09,
        "url":       "http://www.shiputec.com/stick-bag-packaging-machine-product/",
        "role":      "Filling",
        "img":       "stickpack_filler.jpg",
    },
}

# ── General overhead (applied to total machine cost) ──────────────────────────
OVERHEAD = {
    "Instalasi":          0.08,
    "Elektrikal":         0.05,
    "Utilitas":           0.03,
    "Sparepart Awal":     0.02,
}
OVERHEAD_TOTAL = sum(OVERHEAD.values())  # 18%

# ── Fixed costs ───────────────────────────────────────────────────────────────
COMMISSIONING_MODIFY  = 20_000_000   # modifikasi lini existing
COMMISSIONING_NEWLINE = 35_000_000   # lini baru (setup lebih lengkap)
TRAINING_NEWLINE      = 15_000_000   # lini baru dengan mesin tipe baru (Shiputec/Wolf)

# ── Manpower OPEX (annual, for new line only) ─────────────────────────────────
ANNUAL_OPERATOR = 83_200_000   # 1 operator/tahun
ANNUAL_QC       = 83_200_000   # 1 QC/tahun


def _machine_capex(machines_qty: list) -> dict:
    """machines_qty: list of (machine_key, qty)"""
    total_machine = 0
    breakdown = {}
    annual_opex = 0
    for key, qty in machines_qty:
        m = MACHINES[key]
        cost = m["capex"] * qty
        total_machine += cost
        opex = m["capex"] * m["opex_rate"] * qty
        annual_opex += opex
        label = m["full_name"] + (f" ×{qty}" if qty > 1 else "")
        breakdown[label] = cost
    overhead = total_machine * OVERHEAD_TOTAL
    for k, v in OVERHEAD.items():
        breakdown[k] = total_machine * v
    return {"machine": total_machine, "overhead": overhead,
            "breakdown": breakdown, "annual_maintenance": annual_opex}


def capex_multiline(qty_lines: int = 1) -> dict:
    """CAPEX untuk konversi single → multiline per lini."""
    # Per lini: 6× micro auger + 1× Shiputec + 6× Z-conveyor + 1× Multi-strand
    machines = [
        ("micro_auger",  6 * qty_lines),
        ("shiputec",     1 * qty_lines),
        ("inclined_z",   6 * qty_lines),
        ("multi_strand", 1 * qty_lines),
    ]
    r = _machine_capex(machines)
    r["commissioning"] = COMMISSIONING_MODIFY * qty_lines
    r["training"]      = 0   # no training for modification
    r["annual_manpower"] = 0  # no additional staff for modification
    r["total"] = r["machine"] + r["overhead"] + r["commissioning"]
    r["breakdown"]["Commissioning"] = r["commissioning"]
    # Pak Ardi: maintenance = Rp 20M/bulan = Rp 240M/tahun (FIXED for filling line)
    r["annual_opex_maintenance"]  = 240_000_000  # Rp 240M/thn (Pak Ardi: Rp 20M/bln)
    r["annual_opex_total"]        = r["annual_opex_maintenance"]
    r["annual_operator_salary"]   = 0   # modifikasi lini — tidak ada operator baru
    r["annual_qc_salary"]         = 0   # modifikasi lini — tidak ada QC baru
    r["machine_list"] = [(k, q) for k, q in machines]
    return r


def capex_new_line() -> dict:
    """CAPEX untuk penambahan 1 lini baru single-lane SSS+BIB."""
    machines = [
        ("feeder_ams",  1),
        ("auger_bgl",   1),
        ("wolf_vpc250", 1),
        ("inclined_z",  1),
        ("flat_belt",   1),
        ("checkweigher",1),
        ("xray",        1),
    ]
    r = _machine_capex(machines)
    r["commissioning"] = COMMISSIONING_NEWLINE
    r["training"]      = TRAINING_NEWLINE
    r["annual_manpower"] = ANNUAL_OPERATOR + ANNUAL_QC
    r["total"] = r["machine"] + r["overhead"] + r["commissioning"] + r["training"]
    r["breakdown"]["Commissioning"] = r["commissioning"]
    r["breakdown"]["Training"]      = r["training"]
    r["annual_opex_total"] = r["annual_maintenance"] + r["annual_manpower"]
    r["machine_list"] = [(k, q) for k, q in machines]
    return r


def capex_stickpack_line() -> dict:
    """CAPEX untuk lini stickpack baru (Shiputec SPMP-480)."""
    machines = [
        ("feeder_ams",      1),
        ("micro_auger",     1),   # 1 unit auger untuk single-lane stickpack
        ("stickpack_filler",1),
        ("inclined_z",      1),
        ("flat_belt",       1),
        ("checkweigher",    1),
        ("xray",            1),
    ]
    r = _machine_capex(machines)
    r["commissioning"]   = COMMISSIONING_NEWLINE
    r["training"]        = TRAINING_NEWLINE
    r["annual_manpower"] = ANNUAL_OPERATOR + ANNUAL_QC
    r["total"]           = r["machine"] + r["overhead"] + r["commissioning"] + r["training"]
    r["breakdown"]["Commissioning"] = r["commissioning"]
    r["breakdown"]["Training"]      = r["training"]
    r["annual_opex_total"] = r["annual_maintenance"] + r["annual_manpower"]
    r["machine_list"]    = machines
    return r


CAPEX_FN = {
    "multiline_G":       lambda: capex_multiline(1),
    "multiline_B":       lambda: capex_multiline(1),
    "multiline_BG":      lambda: capex_multiline(2),
    "new_line":          capex_new_line,
    "multiline_BG_new":  lambda: {
        "total": capex_multiline(2)["total"] + capex_new_line()["total"],
        "annual_opex_total": capex_multiline(2)["annual_opex_total"] + capex_new_line()["annual_opex_total"],
        "breakdown": {**capex_multiline(2)["breakdown"],
                      **{f"[Lini Baru] {k}": v for k,v in capex_new_line()["breakdown"].items()}},
        "machine_list": capex_multiline(2)["machine_list"] + capex_new_line()["machine_list"],
    },
    "stickpack_line": capex_stickpack_line,
}

# ── Default financial parameters ──────────────────────────────────────────────
# ── Default parameters — aligned with Fonterra/FBMI Group Valuation Model ────
# Source: IRR_RainWaterHarvesting — Assumptions tab (Indonesia: WACC 13%, Tax 25%)
DEFAULT_PARAMS = {
    "discount_rate":            0.13,    # WACC Indonesia (Assumptions tab)
    "project_lifetime_year":    10,      # Minimum 10 years per Group Principles
    "payback_threshold_year":   3,
    "realization_factor":       0.75,    # Only applies to INTERNAL products
    "internal_value_per_ton":   2_100_000,
    "tax_rate":                 0.25,    # Indonesia corporate tax rate
    "useful_life_year":         10,      # Asset useful life for straight-line depreciation
    "maintenance_capex_pct":    0.020,   # ~2% of initial capex/yr (Pak Ardi: Rp 240M/thn on ~11.9B)
    "minimum_irr":              0.13,    # Must exceed WACC
    "minimum_roi":              0.10,
    "minimum_npv":             0,
}


def compute_financial(total_capex: float,
                      annual_additional_ton: float,
                      params: dict,
                      annual_opex_extra: float = 0.0) -> dict:
    """DCF valuation aligned with Fonterra Group Valuation Model (GVM).

    FCF = EBIT + Depreciation - Cash Tax - Maintenance Capex - ΔWC
        = annual_benefit - annual_opex - Cash Tax - Maintenance Capex

    where:
        EBIT      = annual_benefit - annual_opex - depreciation
        Cash Tax  = max(EBIT, 0) × tax_rate   (tax shield via depreciation)
        dep       = total_capex / useful_life_year  (straight-line)
    """
    r        = float(params.get("discount_rate",          DEFAULT_PARAMS["discount_rate"]))
    N        = int(params.get("project_lifetime_year",    DEFAULT_PARAMS["project_lifetime_year"]))
    rf       = float(params.get("realization_factor",     DEFAULT_PARAMS["realization_factor"]))
    vpt      = float(params.get("internal_value_per_ton", DEFAULT_PARAMS["internal_value_per_ton"]))
    tax_rate = float(params.get("tax_rate",               DEFAULT_PARAMS["tax_rate"]))
    ul       = max(int(params.get("useful_life_year",     DEFAULT_PARAMS["useful_life_year"])), 1)
    maint_pct= float(params.get("maintenance_capex_pct",  DEFAULT_PARAMS["maintenance_capex_pct"]))

    # --- Benefit (already pre-computed if _benefit_override set) ---
    if params.get("_benefit_override", 0) > 0:
        annual_benefit = float(params["_benefit_override"])
    else:
        annual_benefit = annual_additional_ton * vpt * rf

    # --- Straight-line depreciation (tax shield) ---
    depreciation = total_capex / ul if ul > 0 else 0

    # --- Annual maintenance capex (operating capex, expensed in FCF) ---
    annual_maint = total_capex * maint_pct

    # --- Income statement ---
    ebit      = annual_benefit - annual_opex_extra - depreciation
    cash_tax  = max(ebit, 0.0) * tax_rate   # no negative tax credit

    # --- Free Cash Flow per year (FCF) ---
    # = EBIT + dep (add back non-cash) - cash_tax - maintenance_capex
    # = annual_benefit - annual_opex_extra - cash_tax - annual_maint
    annual_fcf = annual_benefit - annual_opex_extra - cash_tax - annual_maint

    cash_flows = [-total_capex] + [annual_fcf] * N

    npv = float(npf.npv(r, cash_flows))
    try:
        irr = npf.irr(cash_flows)
        irr_pct = float(irr * 100) if not np.isnan(irr) else None
    except Exception:
        irr_pct = None

    # ROI = annual FCF / initial CAPEX (annual return on invested capital)
    roi_pct  = (annual_fcf / total_capex * 100) if total_capex > 0 else 0
    payback  = (total_capex / annual_fcf) if annual_fcf > 0 else None

    min_irr = params.get("minimum_irr", DEFAULT_PARAMS["minimum_irr"])
    min_roi = params.get("minimum_roi", DEFAULT_PARAMS["minimum_roi"])
    pb_thr  = params.get("payback_threshold_year", DEFAULT_PARAMS["payback_threshold_year"])

    flags = {
        "NPV > 0":                    npv > 0,
        f"IRR ≥ {min_irr*100:.0f}%":  (irr_pct/100 >= min_irr) if irr_pct else False,
        f"ROI ≥ {min_roi*100:.0f}%":  roi_pct/100 >= min_roi,
        f"Payback ≤ {pb_thr} thn":    (payback <= pb_thr) if payback else False,
    }
    feasible = flags["NPV > 0"] and flags[f"ROI ≥ {min_roi*100:.0f}%"]

    return {
        "npv": npv, "irr_pct": irr_pct, "roi_pct": roi_pct,
        "payback_year": payback,
        "annual_benefit": annual_benefit, "annual_fcf": annual_fcf,
        "annual_opex_extra": annual_opex_extra,
        "depreciation": depreciation, "ebit": ebit,
        "cash_tax": cash_tax, "annual_maint_capex": annual_maint,
        "cash_flows": cash_flows, "flags": flags, "feasible": feasible,
        "annual_additional_ton": annual_additional_ton,
    }


def monte_carlo_npv(total_capex, monthly_mean, monthly_std, params, n_sim=5000):
    np.random.seed(42)
    r   = float(params.get("discount_rate",          DEFAULT_PARAMS["discount_rate"]))
    N   = int(params.get("project_lifetime_year",    DEFAULT_PARAMS["project_lifetime_year"]))
    rf  = float(params.get("realization_factor",     DEFAULT_PARAMS["realization_factor"]))
    vpt = float(params.get("internal_value_per_ton", DEFAULT_PARAMS["internal_value_per_ton"]))
    samples = np.clip(np.random.normal(monthly_mean, max(monthly_std, 0.1), n_sim), 0, None)
    npvs = np.array([npf.npv(r, [-total_capex] + [s*12*vpt*rf]*N) for s in samples])
    return {
        "npv_mean": npvs.mean(), "npv_p5": np.percentile(npvs,5),
        "npv_p25": np.percentile(npvs,25), "npv_p75": np.percentile(npvs,75),
        "npv_p95": np.percentile(npvs,95),
        "prob_positive": (npvs > 0).mean() * 100, "samples": npvs,
    }
