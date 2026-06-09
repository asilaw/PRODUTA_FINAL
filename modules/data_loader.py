"""
modules/data_loader.py
Central data loading & preprocessing. Auto-detects CSV separator.
"""

import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path
import io

DATA_DIR = Path(__file__).parent.parent / "data"

PACKAGING_MAP = {
    "SSS":       "SSS",
    "BIB":       "BIB",
    "PILLOW":    "BIB",
    "STICKPACK": "STICKPACK",
}

def _map_packaging(val: str) -> str:
    """Flexible packaging type mapping — handles partial matches and case variations.
    E.g. 'SSS Sachet', 'sss', 'BIB/Pillow', 'Stickpack 480' all map correctly.
    """
    v = str(val).upper().strip().replace("-","").replace("_","").replace(" ","")
    if "STICK" in v:           return "STICKPACK"
    if "BIB" in v or "PILLOW" in v or "BAGBOX" in v: return "BIB"
    if "SSS" in v or "SACHET" in v or "SMALLSINGLE" in v: return "SSS"
    # Try exact match on original PACKAGING_MAP
    for key, mapped in PACKAGING_MAP.items():
        if key in str(val).upper().strip():
            return mapped
    return "OTHER"



# ── Column normalization: all simulation format versions → internal names ──────
_SIM_COL_MAP = {
    # v3 (Asil final): space-separated column names with units
    "Scenario":            "Scenario_ID",
    "Line B Days":         "B_Days",
    "Line B Hours":        "B_Hours",
    "Line G Days":         "G_Days",
    "Line G Hours":        "G_Hours",
    "Line D Days":         "D_Days",
    "Line D Hours":        "D_Hours",
    "Batch Mode":          "Batch_Mode",
    "Target Demand Ton":   "Target_Demand_Ton",
    "Planned Ton":         "Planned_Ton",
    "Tons Finished":       "Tons_Finished",
    "Target Demand Ton":   "Target_Demand_Ton",
    "Planning Ratio (%)":  "Planning_Ratio",
    "Finished Ratio (%)":  "Finished_Ratio",
    "Unmet Demand Ton":    "Unmet_Demand",
    "Tons B":              "Tons_B",
    "Tons G":              "Tons_G",
    "Tons D":              "Tons_D",
    "Util Filling B (%)":  "Util_Filling_B",
    "Util Filling G (%)":  "Util_Filling_G",
    "Util Filling D (%)":  "Util_Filling_D",
    "Setup Minute B":      "Setup_Min_B",
    "Setup Minute G":      "Setup_Min_G",
    "Setup Minute D":      "Setup_Min_D",
    "Bottleneck Area":     "Bottleneck_Area",
    "Planner Status":      "Planner_Status",
    "Capacity Status":     "Capacity_Status",
    "Downtime B":          "Downtime_B",
    "Downtime G":          "Downtime_G",
    "Downtime D":          "Downtime_D",
    "Downtime_B":          "Downtime_B",
    "Downtime_G":          "Downtime_G",
    "Downtime_D":          "Downtime_D",
    "Growth Demand (%)": "Growth",
    "Availability B (%)": "Availability_B",
    "Availability G (%)": "Availability_G",
    "Availability D (%)": "Availability_D",
    "Availability_B":      "Availability_B",
    "Availability_G":      "Availability_G",
    "Availability_D":      "Availability_D",
    # CSV export dari Capacity Simulation (Asil)
    "Line B Availability (%)": "Availability_B",
    "Line G Availability (%)": "Availability_G",
    "Line D Availability (%)": "Availability_D",
    "Line B Downtime Days/Month": "Downtime_B",
    "Line G Downtime Days/Month": "Downtime_G",
    "Line D Downtime Days/Month": "Downtime_D",
    # v2 (Asil prev): underscore names
    "Scenario_Code":       "Scenario_ID",
    "Batch_Mode":          "Batch_Mode",
    "Target_Demand_Ton":   "Target_Demand_Ton",
    "Planned_Ton":         "Planned_Ton",
    "Tons_Finished":       "Tons_Finished",
    "Planning_Ratio":      "Planning_Ratio",
    "Finished_Ratio":      "Finished_Ratio",
    "Unmet_Demand":        "Unmet_Demand",
    "Tons_B":              "Tons_B",
    "Tons_G":              "Tons_G",
    "Tons_D":              "Tons_D",
    "Util_Filling_B":      "Util_Filling_B",
    "Util_Filling_G":      "Util_Filling_G",
    "Util_Filling_D":      "Util_Filling_D",
    "Setup_Min_B":         "Setup_Min_B",
    "Setup_Min_G":         "Setup_Min_G",
    "Setup_Min_D":         "Setup_Min_D",
    "Bottleneck_Area":     "Bottleneck_Area",
    "Planner_Status":      "Planner_Status",
    "Capacity_Status":     "Capacity_Status",
}

def _normalize_sim_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename any simulation format columns to internal standard names (all formats)."""
    rename = {}
    for col in df.columns:
        # Direct map
        if col in _SIM_COL_MAP:
            rename[col] = _SIM_COL_MAP[col]
            continue
        # Try stripped/title variants
        col_clean = col.strip()
        if col_clean in _SIM_COL_MAP:
            rename[col] = _SIM_COL_MAP[col_clean]
    if rename:
        df = df.rename(columns=rename)
    # Ensure Scenario_ID exists
    if "Scenario_ID" not in df.columns:
        for candidate in ["Scenario","Scenario_Code","scenario","SCENARIO"]:
            if candidate in df.columns:
                df = df.rename(columns={candidate: "Scenario_ID"}); break
    # Per-line schedule: add backward-compat columns derived from per-line if missing
    for col_new, col_old, col_space, default in [
        ("B_Days","B_Days","Line B Days",7),("B_Hours","B_Hours","Line B Hours",24),
        ("G_Days","G_Days","Line G Days",7),("G_Hours","G_Hours","Line G Hours",24),
        ("D_Days","D_Days","Line D Days",7),("D_Hours","D_Hours","Line D Hours",24),
    ]:
        if col_new not in df.columns:
            if col_space in df.columns:
                df[col_new] = df[col_space]
            else:
                df[col_new] = default
    # Batch Mode
    if "Batch_Mode" not in df.columns:
        for bc in ["Batch Mode","WO_Mode","batch_mode"]:
            if bc in df.columns:
                df["Batch_Mode"] = df[bc]; break
    return df

def _parse_sim_v3(text: str) -> pd.DataFrame:
    """Parse Asil v3 format: comma-separated, single header row, space-separated names."""
    import io
    for sep in [",", "\t", ";"]:
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep, skipinitialspace=True)
            if "Scenario" in df.columns or "Line B Days" in df.columns:
                return _normalize_sim_columns(df)
        except Exception:
            pass
    return pd.DataFrame()

def _detect_sep(text: str) -> str:
    """Auto-detect separator: tab, semicolon, or comma."""
    first_line = text.split("\n")[0]
    if "\t" in first_line:
        return "\t"
    if ";" in first_line:
        return ";"
    return ","


def _parse_sim_v4(text: str) -> pd.DataFrame:
    """
    Parse format CSV baru Asil (Jun 2026): tab-separated, tanpa header.
    Kolom (berdasarkan urutan):
    [0] row_num, [1] label, [2] B_days, [3] B_hrs, [4] G_days, [5] G_hrs,
    [6] D_days, [7] D_hrs, [8] batch_mode, [9] growth,
    [10] avail_b, [11] avail_g, [12] avail_d,
    [13] downtime_b, [14] downtime_g, [15] downtime_d,
    [16] target_demand, [17] planned_ton, [18] tons_finished,
    [19] planning_ratio, [20] finished_ratio, [21] unmet_demand,
    [22] tons_b, [23] tons_g, [24] tons_d,
    [25] util_b, [26] util_g, [27] util_d,
    ...optional...
    [-2] fis_score, [-1] decision
    """
    import io as _io
    lines = [l for l in text.strip().split("\n") if l.strip()]
    rows = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 10:
            continue
        def _g(i, d=0.0):
            try: return float(parts[i]) if i < len(parts) and parts[i].strip() else d
            except: return d
        def _s(i, d=""):
            return parts[i].strip() if i < len(parts) else d
        rows.append({
            "Scenario_ID":       _s(1),  # label as scenario ID
            "Scenario":          _s(1),
            "B_Days":            _g(2, 7), "B_Hours":  _g(3, 24),
            "G_Days":            _g(4, 7), "G_Hours":  _g(5, 24),
            "D_Days":            _g(6, 7), "D_Hours":  _g(7, 24),
            "Batch_Mode":        _s(8),
            "Growth":            _g(9, 0),
            "Availability_B":    _g(10, 100), "Availability_G": _g(11, 100),
            "Availability_D":    _g(12, 100),
            "Downtime_B":        _g(13, 0), "Downtime_G": _g(14, 0),
            "Downtime_D":        _g(15, 0),
            "Target_Demand_Ton": _g(16, 0),
            "Planned_Ton":       _g(17, 0),
            "Tons_Finished":     _g(18, 0),
            "Planning_Ratio":    _g(19, 100),
            "Finished_Ratio":    _g(20, 100),
            "Unmet_Demand":      _g(21, 0),
            "Tons_B":            _g(22, 0), "Tons_G": _g(23, 0), "Tons_D": _g(24, 0),
            "Util_Filling_B":    _g(25, 0), "Util_Filling_G": _g(26, 0),
            "Util_Filling_D":    _g(27, 0),
            "Capacity_Status":   "",
            "Planner_Status":    "",
            "Bottleneck_Area":   "",
            "_row_num":          _g(0, 0),
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Deduplicate: jika semua baris punya label yang sama, ini 1 skenario saja
    # Kembalikan 1 baris per skenario unik (unique by label)
    df["_label_key"] = df["Scenario_ID"].astype(str).str.strip()
    df = df.drop_duplicates(subset=["_label_key"]).drop(columns=["_label_key", "_row_num"])
    df = df.reset_index(drop=True)
    return df


def _read_flexible(source, encoding="utf-8") -> pd.DataFrame:
    """Read CSV/TSV from file path or uploaded file object, auto-detect sep."""
    if hasattr(source, "read"):
        raw = source.read()
        # handle bytes vs str
        if isinstance(raw, bytes):
            raw = raw.decode(encoding, errors="replace")
        source.seek(0)
    else:
        raw = Path(source).read_text(encoding=encoding, errors="replace")

    sep = _detect_sep(raw)
    df = pd.read_csv(io.StringIO(raw), sep=sep, encoding=encoding,
                     on_bad_lines="skip")
    df.columns = df.columns.str.strip()
    return df


# ── Master SKU ────────────────────────────────────────────────────────────────
def load_master_sku(uploaded_file=None) -> pd.DataFrame:
    if uploaded_file is not None:
        df = _read_flexible(uploaded_file)
    else:
        path = DATA_DIR / "master_sku.csv"
        if not path.exists():
            return pd.DataFrame()
        df = _read_flexible(path)

    # Find packaging column — multi-strategy detection
    # Strategy 1: explicit PORT TYPE column
    pkg_col = next((c for c in df.columns if "PORT" in c.upper() and "TYPE" in c.upper()), None)
    # Strategy 2: any column named PORT
    if pkg_col is None:
        pkg_col = next((c for c in df.columns if c.upper().strip() in ("PORT","PORT TYPE","PORT_TYPE","KEMASAN","PACKAGING","PACKAGING TYPE")), None)
    # Strategy 3: scan all object columns for SSS/BIB/STICKPACK values
    if pkg_col is None:
        for col in df.select_dtypes(include="object").columns:
            sample = df[col].dropna().astype(str).str.upper().str.strip()
            hits = sample.str.contains(r"SSS|BIB|PILLOW|STICKPACK", regex=True).sum()
            if hits > 0:
                pkg_col = col
                break
    # Strategy 4: PRODUCT TYPE as last resort (might have SSS/BIB in it)
    if pkg_col is None:
        pkg_col = next((c for c in df.columns if "PRODUCT" in c.upper() and "TYPE" in c.upper()), None)

    if pkg_col:
        df["PACKAGING_NORM"] = df[pkg_col].apply(_map_packaging)
        df["_pkg_col_used"] = pkg_col   # track which column was used (for debugging)
    else:
        df["PACKAGING_NORM"] = "UNKNOWN"
        df["_pkg_col_used"] = "—"

    # Normalise money columns — strip Rp, dots, commas
    for col in df.columns:
        if any(k in col.upper() for k in ["OPEX", "CAPEX", "MAKLON", "BIAYA"]):
            # Note: VOLUME excluded — uses dot as decimal separator (e.g., 4.04 ton)
            df[col] = (
                df[col].astype(str)
                .str.replace(r"[RpRp\s]", "", regex=True)
                .str.replace(r"\.", "", regex=True)   # thousands separator
                .str.replace(",", ".", regex=False)
                .str.replace("-", "0", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
                .fillna(0)
            )

    if "MACHINE HOURS/MT" in df.columns:
        # VOLUME columns: use dot as decimal (4.04 = 4.04 ton, NOT 404)
        for col in df.columns:
            if "VOLUME" in col.upper():
                df[col] = (df[col].astype(str)
                    .str.replace(r"[Rp\s]","",regex=True)
                    .str.replace("-","0",regex=False)
                    .pipe(pd.to_numeric, errors="coerce")
                    .fillna(0))
        df["MACHINE HOURS/MT"] = pd.to_numeric(df["MACHINE HOURS/MT"], errors="coerce").fillna(0)

    return df


# ── Forecast ──────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_forecast(uploaded_file=None) -> pd.DataFrame:
    if uploaded_file is not None:
        df = _read_flexible(uploaded_file)
    else:
        path = DATA_DIR / "forecast.csv"
        if not path.exists():
            return pd.DataFrame()
        df = _read_flexible(path)

    # Normalise column names to lowercase for robustness
    col_map = {c: c.strip().lower().replace(" ", "_") for c in df.columns}
    df = df.rename(columns=col_map)

    # Find date column
    date_col = next((c for c in df.columns if "date" in c or "tanggal" in c or "bulan" in c), None)
    if date_col and date_col != "date":
        df = df.rename(columns={date_col: "date"})

    # Find forecast column
    fc_col = next((c for c in df.columns if c in ("forecast", "value", "demand", "pred")), None)
    if fc_col and fc_col != "forecast":
        df = df.rename(columns={fc_col: "forecast"})

    if "date" not in df.columns:
        # last resort: first column that looks like a date
        for c in df.columns:
            sample = df[c].dropna().astype(str).iloc[0] if not df[c].dropna().empty else ""
            if "/" in sample or "-" in sample:
                df = df.rename(columns={c: "date"})
                break

    if "date" not in df.columns:
        st.error("Kolom tanggal tidak ditemukan. Pastikan ada kolom 'date' di file forecast.")
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for col in ["forecast", "forecast_lower", "forecast_upper"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").clip(lower=0)

    if "mape_backtest" in df.columns:
        df["mape_backtest"] = pd.to_numeric(df["mape_backtest"], errors="coerce")

    # SKU column
    sku_col = next((c for c in df.columns if c in ("sku", "sku_id", "kode", "item")), None)
    if sku_col and sku_col != "sku":
        df = df.rename(columns={sku_col: "sku"})

    return df.dropna(subset=["date"])


def merge_forecast_sku(forecast_df: pd.DataFrame, master_df: pd.DataFrame) -> pd.DataFrame:
    if forecast_df.empty or master_df.empty:
        return forecast_df

    # Find SKU column in master
    sku_col_master = next((c for c in master_df.columns if c.upper() == "SKU"), None)
    if sku_col_master is None:
        return forecast_df

    # Include PORT TYPE and common packaging column names so they survive the merge
    _port_cols = [c for c in master_df.columns
                  if ("PORT" in c.upper() and "TYPE" in c.upper())
                  or c.upper().strip() in ("PORT","KEMASAN","PACKAGING")]
    want = ["BRAND", "PRODUCT", "PACKAGING_NORM", "PRODUCTION STATUS", "LINE COMPATIBLE",
            "MACHINE HOURS/MT", "VOLUME (Bulan/Ton)", "VOLUME PRODUKSI"] + _port_cols
    keep = [sku_col_master] + [c for c in want if c in master_df.columns]

    merged = forecast_df.merge(master_df[keep], left_on="sku", right_on=sku_col_master, how="left")
    merged["sku_found"] = merged[sku_col_master].notna()

    # PACKAGING_NORM: compute fresh here (not dependent on @st.cache_data of load_master_sku)
    # Detect PORT TYPE column from master_df
    _pkg_col = None
    for _c in master_df.columns:
        _cu = _c.upper().strip()
        if "PORT" in _cu and "TYPE" in _cu:
            _pkg_col = _c
            break
    if _pkg_col is None:
        # Fallback: scan for column whose values contain SSS/BIB/STICKPACK
        for _c in master_df.columns:
            _vals = master_df[_c].dropna().astype(str).str.upper()
            if _vals.str.contains("SSS|BIB|STICKPACK|PILLOW", regex=True).any():
                _pkg_col = _c
                break
    # Find PORT TYPE column in the merged result (it came through because we added it to want)
    _port_col_in_merged = next(
        (c for c in merged.columns if "PORT" in c.upper() and "TYPE" in c.upper()), None)
    if _port_col_in_merged:
        # Direct: map from the PORT TYPE column that's already in merged
        merged["PACKAGING_NORM"] = merged[_port_col_in_merged].apply(_map_packaging)
    elif _pkg_col is not None:
        # Fallback: lookup from master_df
        _pkg_lut = {str(r[sku_col_master]): _map_packaging(str(r.get(_pkg_col, "")))
                    for _, r in master_df.iterrows()}
        merged["PACKAGING_NORM"] = merged["sku"].astype(str).map(_pkg_lut).fillna("OTHER")
    else:
        merged["PACKAGING_NORM"] = "OTHER"

    return merged


# ── Simulation ────────────────────────────────────────────────────────────────
def _parse_sim_new_format(content: str) -> pd.DataFrame:
    """Parse new simulation format (CSV or TSV).
    Skips leading blank/title rows (BOM, empty, 'Simulation Result').
    Auto-detects comma vs tab separator.
    Finds the row containing 'Scenario_Code' as the true column header row.
    """
    # Strip BOM, normalise line endings
    content = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    all_lines = content.split("\n")

    # Find the header row: the first row where a cell equals "Scenario_Code"
    header_line_idx = None
    sep = ","  # default; overridden below
    for i, line in enumerate(all_lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Auto-detect separator from this line
        detected_sep = "\t" if "\t" in stripped else ","
        cells = [c.strip() for c in stripped.split(detected_sep)]
        if "Scenario_Code" in cells:
            header_line_idx = i
            sep = detected_sep
            break

    if header_line_idx is None:
        return pd.DataFrame()

    col_names = [c.strip() for c in all_lines[header_line_idx].strip().split(sep)]

    # Parse data rows (all non-empty rows after header)
    data_rows = []
    for line in all_lines[header_line_idx + 1:]:
        stripped = line.strip()
        if not stripped:
            continue
        cells = stripped.split(sep)
        if len(cells) < len(col_names):
            cells += [""] * (len(col_names) - len(cells))
        data_rows.append(cells[:len(col_names)])

    if not data_rows:
        return pd.DataFrame(columns=col_names)
    return pd.DataFrame(data_rows, columns=col_names)


@st.cache_data(show_spinner=False)
def load_simulation(_uploaded_file=None) -> pd.DataFrame:
    """Load simulation — supports new per-line format (Scenario_Code, B_Days, ...)
    and old format (Scenario_ID, Days_Per_Week, ...).  Produces unified output."""
    # ── Read raw text first (most reliable for new format) ───────────────────
    raw_text = ""
    if _uploaded_file is not None:
        try:
            if hasattr(_uploaded_file, "read"):
                raw_bytes = _uploaded_file.read()
                raw_text  = raw_bytes.decode("utf-8", errors="replace")
                if hasattr(_uploaded_file, "seek"):
                    _uploaded_file.seek(0)
            elif isinstance(_uploaded_file, (str, Path)):
                with open(_uploaded_file, "rb") as fh:
                    raw_text = fh.read().decode("utf-8", errors="replace")
        except Exception:
            pass
    else:
        path = DATA_DIR / "simulation.csv"
        if not path.exists():
            return pd.DataFrame()
        try:
            with open(path, "rb") as fh:
                raw_text = fh.read().decode("utf-8", errors="replace")
        except Exception:
            return pd.DataFrame()

    if not raw_text.strip():
        return pd.DataFrame()

    # ── Format detection: v4 > v3 > v2 > v1 ────────────────────────────────────
    first_line = raw_text.split("\n")[0].lower()
    # v4: tab-separated, NO header, first column = row number (integer)
    # Format baru Asil: "1\tB:7D/24H · G:7D/24H · D:7D/24H\t7\t24\t..."
    _first_col = first_line.split("\t")[0].strip() if "\t" in first_line else ""
    is_v4 = (
        "\t" in first_line
        and _first_col.isdigit()
        and ("7d/24h" in first_line or "d/24h" in first_line or "7d/" in first_line)
        and "line b days" not in first_line
    )
    is_v3 = not is_v4 and ("line b days" in first_line or (
        "scenario" in first_line and "batch mode" in first_line
        and "scenario_code" not in first_line
    ))
    is_v2 = not is_v4 and "Scenario_Code" in raw_text and not is_v3

    if is_v4:
        # v4: tab-separated, no header, row-number first col (Asil new format Jun 2026)
        df = _parse_sim_v4(raw_text)
        new_fmt = not df.empty
    elif is_v3:
        # v3: comma-separated, new column names with spaces
        df = _parse_sim_v3(raw_text)      # returns normalized DataFrame
        new_fmt = not df.empty
    elif is_v2:
        df = _parse_sim_new_format(raw_text)
        new_fmt = "Scenario_Code" in df.columns
    else:
        # v1 old format
        new_fmt = False
        try:
            if _uploaded_file is not None and hasattr(_uploaded_file, "seek"):
                _uploaded_file.seek(0)
            df = _read_flexible(_uploaded_file or (DATA_DIR / "simulation.csv"))
        except Exception:
            df = pd.DataFrame()

    # Normalize ALL formats to internal column names
    if not df.empty:
        df = _normalize_sim_columns(df)
        new_fmt = "Scenario_ID" in df.columns or "B_Days" in df.columns

    if new_fmt and "Scenario_Code" in df.columns:
        # v2 legacy rename
        df.rename(columns={"Scenario_Code": "Scenario_ID"}, inplace=True)

        # Numeric columns
        per_line_num = ["B_Days","B_Hours","G_Days","G_Hours","D_Days","D_Hours",
                        "Growth","Target_Demand_Ton","Planned_Ton","Tons_Finished",
                        "Planning_Ratio","Finished_Ratio","Unmet_Demand",
                        "Tons_B","Tons_G","Tons_D",
                        "Util_Filling_B","Util_Filling_G","Util_Filling_D",
                        "Setup_Min_B","Setup_Min_G","Setup_Min_D"]
        for col in [c for c in per_line_num if c in df.columns]:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace("%",""), errors="coerce").fillna(0)

        # Per-line effective hours (days/7 × 349 effective days/year × hours/day)
        for line in ["B","G","D"]:
            dc, hc = f"{line}_Days", f"{line}_Hours"
            if dc in df.columns and hc in df.columns:
                df[f"{line}_Eff_Hrs"] = (df[dc]/7 * 349 * df[hc]).round(0)

        # Total system hours (sum across all 3 lines — used for ranking efficiency)
        eff_cols = [f"{l}_Eff_Hrs" for l in "BGD" if f"{l}_Eff_Hrs" in df.columns]
        df["Total_System_Hrs"] = df[eff_cols].sum(axis=1)

        # Backward-compat: global schedule columns (use max across lines)
        df["Days_Per_Week"]         = df[["B_Days","G_Days","D_Days"]].max(axis=1)
        df["Working_Hours"]         = df[["B_Hours","G_Hours","D_Hours"]].max(axis=1)
        df["Effective_Working_Days"]= (df["Days_Per_Week"]/7 * 349).round(0)

        # Batch_Mode → WO_Mode
        if "Batch_Mode" in df.columns:
            df["Batch_Mode"] = df["Batch_Mode"].astype(str).str.strip()
            df["WO_Mode"] = (df["Batch_Mode"]
                .str.replace("BLOSS","WO_LOSS",regex=False)
                .str.replace("B35","WO_35",regex=False))

        # Capacity_Status flag for FIS override
        if "Capacity_Status" in df.columns:
            df["Cap_Sufficient"] = ~df["Capacity_Status"].astype(str).str.upper().str.contains(
                "TIDAK MENCUKUPI", na=False)

    else:
        # Old format — compute per-line effective hours from global schedule
        for col in ["Days_Per_Week","Working_Hours","Effective_Working_Days",
                    "Target_Demand_Ton","Tons_Finished","Finished_Ratio","Unmet_Demand",
                    "Tons_B","Tons_G","Tons_D","Util_Filling_B","Util_Filling_G","Util_Filling_D"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace("%",""), errors="coerce").fillna(0)
        single_eff = df.get("Effective_Working_Days", pd.Series([349]*len(df))) *                      df.get("Working_Hours", pd.Series([24]*len(df)))
        df["Total_System_Hrs"] = single_eff * 3
        for line in "BGD":
            df[f"{line}_Eff_Hrs"] = single_eff

    # Unmet ratio
    if "Target_Demand_Ton" in df.columns and "Unmet_Demand" in df.columns:
        df["Unmet_Ratio"] = (df["Unmet_Demand"] / df["Target_Demand_Ton"].replace(0,np.nan)).fillna(0)

    # Strip string columns
    for col in ["Scenario_ID","WO_Mode","Batch_Mode","Bottleneck_Area","Planner_Status","Capacity_Status"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # Remove empty rows
    if "Scenario_ID" in df.columns:
        df = df[df["Scenario_ID"].astype(str).str.strip().str.len() > 0].reset_index(drop=True)

    return df


def classify_scenario(df: pd.DataFrame,
                       finished_ratio_threshold: float = 95.0,
                       unmet_ratio_threshold: float = 0.05) -> pd.DataFrame:
    df = df.copy()
    cond = (
        (df.get("Finished_Ratio", pd.Series(dtype=float)) >= finished_ratio_threshold) &
        (df.get("Unmet_Ratio",   pd.Series(dtype=float)) <= unmet_ratio_threshold)
    )
    df["DECISION_LEVEL"] = np.where(cond, "MAINTAIN", "MODIFY")
    return df


# ── Machine Components ────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_machine_components(uploaded_file=None) -> pd.DataFrame:
    if uploaded_file is not None:
        df = _read_flexible(uploaded_file)
    else:
        path = DATA_DIR / "machine_components.csv"
        if not path.exists():
            return pd.DataFrame()
        df = _read_flexible(path)

    for col in df.columns:
        if any(k in col.upper() for k in ["CAPEX", "OPEX"]):
            df[col] = (
                df[col].astype(str)
                .str.replace(r"[Rp\s\.]", "", regex=True)
                .str.replace(",", ".", regex=False)
                .pipe(pd.to_numeric, errors="coerce").fillna(0)
            )
    for col in ["CAPACITY IMPACT (%)", "CAPACITY (kg/hr)", "SIZE (mm)"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


# ── Co-Man Volume ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_coman_volume(uploaded_file=None) -> pd.DataFrame:
    if uploaded_file is not None:
        df = _read_flexible(uploaded_file)
    else:
        path = DATA_DIR / "coman_volume.csv"
        if not path.exists():
            return pd.DataFrame()
        df = _read_flexible(path)

    vol_col = next((c for c in df.columns if "VOLUME" in c.upper() or "TON" in c.upper()), None)
    if vol_col:
        df[vol_col] = pd.to_numeric(df[vol_col], errors="coerce").fillna(0)

    return df


# ── Financial Parameters ──────────────────────────────────────────────────────
DEFAULT_FINANCIAL_PARAMS = {
    "discount_rate":           0.18,
    "project_lifetime_year":   3,
    "payback_threshold_year":  2,
    "minimum_npv":             0,
    "minimum_irr":             0.15,
    "minimum_roi":             0.25,
    "realization_factor":      0.75,
    "internal_value_per_ton":  1_500_000,
    "coman_cost_per_ton":      6_500_000,
    "internal_cost_per_ton":   5_000_000,
    "saving_per_ton_pullback": 1_500_000,
}
