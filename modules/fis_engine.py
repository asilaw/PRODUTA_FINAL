"""
FIS Engine — Fuzzy Inference System untuk evaluasi risiko kapasitas.
Mamdani type, pure NumPy.

Input:
    util_max_pct      : utilisasi tertinggi dari semua lini (%)
    unmet_ratio_pct   : unmet demand / total demand (%)
    finished_ratio_pct: ton selesai / target demand (%)

Output: severity score [0, 4]
    0.0 – 1.4  → MAINTAIN Aman
    1.4 – 2.0  → MAINTAIN Monitor (utilisasi mulai mendekati batas)
    2.0 – 2.8  → MODIFY Borderline (utilisasi sedikit melewati batas / unmet kecil)
    2.8 – 4.0  → MODIFY Signifikan (utilisasi tinggi / unmet demand besar)

Perbaikan v2 (Jun 2026):
- Fix bug MF degenerate (a=b atau c=d tidak lagi return 0 yang salah)
- Aturan fuzzy didesain ulang agar gradasi skor mencerminkan kondisi aktual
- Severity label menggantikan keputusan biner tunggal
"""
import numpy as np


def _tri(x, a, b, c):
    """Triangular MF. Handles degenerate a=b (left-ramp) and b=c (right-ramp)."""
    x = float(x)
    if x < a or x > c:
        return 0.0
    if x == b:
        return 1.0
    eps = 1e-10
    if x < b:
        return float(np.clip((x - a) / (b - a + eps), 0.0, 1.0))
    return float(np.clip((c - x) / (c - b + eps), 0.0, 1.0))


def _trap(x, a, b, c, d):
    """Trapezoidal MF. Handles degenerate a=b (left plateau) and c=d (right plateau)."""
    x = float(x)
    eps = 1e-10
    if x < a or x > d:
        return 0.0
    if b <= x <= c:
        return 1.0
    if x < b:
        return float(np.clip((x - a) / (b - a + eps), 0.0, 1.0))
    return float(np.clip((d - x) / (d - c + eps), 0.0, 1.0))


def compute_fis(util_max_pct: float,
                unmet_ratio_pct: float,
                finished_ratio_pct: float) -> float:
    """
    Hitung skor risiko kapasitas FIS Mamdani.

    Perancangan MF berdasarkan threshold industri filling powder (Lactalis FBMI):
        Utilisasi aman    : < 75%  (operational target)
        Utilisasi monitor : 75–85% (approaching capacity limit)
        Utilisasi tinggi  : > 82%  (potential bottleneck)
        Utilisasi kritis  : > 90%  (must intervene)
    """
    u = float(np.clip(util_max_pct, 0.0, 100.0))
    r = float(np.clip(unmet_ratio_pct, 0.0, 100.0))
    f = float(np.clip(finished_ratio_pct, 0.0, 100.0))

    # ── Input MF: Utilisasi (%) ────────────────────────────────────────────────
    u_rendah  = _trap(u,  0.0,  0.0, 65.0, 78.0)   # Aman: penuh di 0-65%, turun ke 78%
    u_sedang  = _tri( u, 65.0, 78.0, 92.0)          # Menengah: puncak di 78%
    u_tinggi  = _trap(u, 82.0, 90.0,100.0,100.0)    # Tinggi: naik mulai 82%, penuh di 90%

    # ── Input MF: Unmet ratio (%) ──────────────────────────────────────────────
    r_kecil   = _trap(r,  0.0,  0.0,  2.0,  8.0)   # Sangat kecil (< 2% aman)
    r_sedang  = _tri( r,  2.0, 15.0, 40.0)          # Menengah: 2-40%
    r_besar   = _trap(r, 25.0, 50.0,100.0,100.0)    # Besar: > 25% → kritis

    # ── Input MF: Finished ratio (%) ──────────────────────────────────────────
    f_tinggi  = _trap(f, 95.0,100.0,100.0,100.0)    # Hampir/selesai penuh
    f_sedang  = _tri( f, 80.0, 90.0, 99.0)          # Cukup terselesaikan
    f_rendah  = _tri( f,  0.0, 60.0, 88.0)          # Banyak tidak selesai

    # ── Output domain [0, 4] ───────────────────────────────────────────────────
    x = np.linspace(0.0, 4.0, 600)
    eps = 1e-10

    def _omf(center, half_width):
        """Triangular output MF with given center and half-width."""
        return np.clip(1.0 - np.abs(x - center) / (half_width + eps), 0.0, 1.0)

    out_aman       = _omf(0.8,  0.9)   # centroid 0.8  → MAINTAIN Aman
    out_monitor    = _omf(1.7,  0.8)   # centroid 1.7  → MAINTAIN Monitor
    out_borderline = _omf(2.4,  0.7)   # centroid 2.4  → MODIFY Borderline
    out_significant= _omf(3.2,  0.8)   # centroid 3.2  → MODIFY Signifikan
    out_kritis     = _omf(3.8,  0.5)   # centroid 3.8  → MODIFY Kritis

    agg = np.zeros(600)

    # ── Rules ──────────────────────────────────────────────────────────────────
    # R1: Util rendah + Unmet kecil → Aman
    agg = np.maximum(agg, min(u_rendah, r_kecil) * out_aman)

    # R2: Util rendah + Finished tinggi → Aman
    agg = np.maximum(agg, min(u_rendah, f_tinggi) * out_aman)

    # R3: Util sedang + Unmet kecil + Finished tinggi → Monitor
    agg = np.maximum(agg, min(u_sedang, r_kecil, f_tinggi) * out_monitor)

    # R4: Util sedang + Finished sedang → Monitor
    agg = np.maximum(agg, min(u_sedang, f_sedang) * out_monitor)

    # R5: Util tinggi + Unmet kecil + Finished tinggi → Borderline MODIFY
    #     (utilisasi > batas tapi demand terpenuhi penuh → tidak terlalu kritis)
    agg = np.maximum(agg, min(u_tinggi, r_kecil, f_tinggi) * out_borderline)

    # R6: Util tinggi + Finished sedang → MODIFY Signifikan
    agg = np.maximum(agg, min(u_tinggi, f_sedang) * out_significant)

    # R7: Unmet sedang → MODIFY Signifikan
    agg = np.maximum(agg, r_sedang * out_significant)

    # R8: Unmet besar → Kritis
    agg = np.maximum(agg, r_besar * out_kritis)

    # R9: Finished rendah → Kritis (produksi tidak selesai)
    agg = np.maximum(agg, f_rendah * out_kritis)

    # R10: Util tinggi + Unmet sedang → Kritis
    agg = np.maximum(agg, min(u_tinggi, r_sedang) * out_kritis)

    # ── Defuzzifikasi: centroid ────────────────────────────────────────────────
    denom = float(np.sum(agg))
    if denom < 1e-10:
        # Fallback: kondisi ambiguous → monitor ringan
        return 1.2
    score = float(np.sum(agg * x) / denom)
    return round(float(np.clip(score, 0.0, 4.0)), 3)


def fis_severity_label(score: float) -> str:
    """Label tingkat keparahan berdasarkan skor FIS."""
    if score < 1.4:   return "Aman"
    if score < 2.0:   return "Monitor"
    if score < 2.8:   return "Borderline"
    if score < 3.5:   return "Signifikan"
    return "Kritis"


def fis_severity_color(score: float) -> str:
    """Warna untuk label tingkat keparahan."""
    if score < 1.4:   return "#1a7f4b"   # hijau
    if score < 2.0:   return "#088395"   # teal
    if score < 2.8:   return "#d29922"   # oranye
    if score < 3.5:   return "#e05c4b"   # merah-oranye
    return "#f85149"                      # merah kritis
