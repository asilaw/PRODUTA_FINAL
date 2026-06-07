"""
FIS Engine — pure NumPy implementation, no skfuzzy or networkx dependency.
Input : util_max (%), unmet_ratio (%), finished_ratio (%)
Output: severity score float in [0, 4]
"""
import numpy as np


def _tri(x, a, b, c):
    eps = 1e-10
    return float(np.clip(np.minimum((x-a)/(b-a+eps), (c-x)/(c-b+eps)), 0, 1))


def _trap(x, a, b, c, d):
    eps = 1e-10
    return float(np.clip(np.minimum(np.minimum((x-a)/(b-a+eps), 1.0), (d-x)/(d-c+eps)), 0, 1))


def compute_fis(util_max_pct: float,
                unmet_ratio_pct: float,
                finished_ratio_pct: float) -> float:
    u = float(np.clip(util_max_pct,      0, 100))
    r = float(np.clip(unmet_ratio_pct,   0, 100))
    f = float(np.clip(finished_ratio_pct, 0, 100))

    u_low  = _tri(u, 0, 0, 70)
    u_med  = _tri(u, 55, 80, 100)
    u_high = _trap(u, 85, 95, 100, 100)

    r_low  = _trap(r, 0, 0, 5, 15)
    r_high = _tri(r, 5, 50, 100)

    f_low  = _tri(f, 0, 70, 90)
    f_med  = _tri(f, 85, 95, 100)
    f_high = _trap(f, 95, 100, 100, 100)

    x = np.linspace(0, 4, 500)
    eps = 1e-10
    out_low  = np.clip(np.minimum((x-0)/(1.5+eps), (1.5-x)/(1.5+eps)), 0, 1)
    out_med  = np.clip(np.minimum((x-1.0)/(1.0+eps), (3.0-x)/(1.0+eps)), 0, 1)
    out_high = np.where(x >= 2.5, np.clip((x-2.5)/(1.5+eps), 0, 1), 0.0)

    agg = np.zeros_like(x)
    agg = np.maximum(agg, min(u_low,  f_high) * out_low)
    agg = np.maximum(agg, max(u_med,  min(u_high, f_med)) * out_med)
    agg = np.maximum(agg, max(r_high, min(u_high, f_low)) * out_high)

    denom = float(np.sum(agg))
    score = float(np.sum(agg * x) / denom) if denom > 0 else 2.0
    return round(float(np.clip(score, 0, 4)), 4)
