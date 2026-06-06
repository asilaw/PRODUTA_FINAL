"""
modules/fis_engine.py
Fuzzy Inference System untuk scoring skenario simulasi.
Mamdani-style FIS menggunakan scikit-fuzzy.

Inputs:
  util_max      — utilisasi tertinggi dari Line B, G, D (%)
  unmet_ratio   — rasio demand tidak terpenuhi (%)
  finished_ratio — rasio demand selesai diproduksi (%)

Output:
  decision_score — 0.0–4.0
    < 1.6  → MAINTAIN
    ≥ 1.6  → MODIFY
"""

import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import warnings
warnings.filterwarnings("ignore")

# ── Build FIS system (cached after first call) ─────────────────────────────
_fis_sim = None

def _build_fis():
    global _fis_sim
    if _fis_sim is not None:
        return _fis_sim

    # ── Antecedents ──────────────────────────────────────────────────────────
    util_max       = ctrl.Antecedent(np.arange(0, 101, 0.5), 'util_max')
    unmet_ratio    = ctrl.Antecedent(np.arange(0, 101, 0.5), 'unmet_ratio')
    finished_ratio = ctrl.Antecedent(np.arange(0, 101, 0.5), 'finished_ratio')

    # ── Consequent ───────────────────────────────────────────────────────────
    decision_score = ctrl.Consequent(np.arange(0, 4.05, 0.05), 'decision_score')

    # ── Membership functions: util_max ────────────────────────────────────
    util_max['low']      = fuzz.trapmf(util_max.universe, [0,  0,  45, 62])
    util_max['medium']   = fuzz.trimf( util_max.universe, [55, 68, 78])
    util_max['high']     = fuzz.trimf( util_max.universe, [70, 80, 92])
    util_max['critical'] = fuzz.trapmf(util_max.universe, [85, 92, 100, 100])

    # ── Membership functions: unmet_ratio ────────────────────────────────
    unmet_ratio['low']      = fuzz.trapmf(unmet_ratio.universe, [0,  0,  3,  8])
    unmet_ratio['moderate'] = fuzz.trimf( unmet_ratio.universe, [5,  12, 20])
    unmet_ratio['high']     = fuzz.trimf( unmet_ratio.universe, [15, 22, 35])
    unmet_ratio['critical'] = fuzz.trapmf(unmet_ratio.universe, [28, 40, 100, 100])

    # ── Membership functions: finished_ratio ────────────────────────────
    finished_ratio['poor']      = fuzz.trapmf(finished_ratio.universe, [0,  0,  68, 78])
    finished_ratio['fair']      = fuzz.trimf( finished_ratio.universe, [72, 82, 91])
    finished_ratio['good']      = fuzz.trimf( finished_ratio.universe, [87, 92, 97])
    finished_ratio['excellent'] = fuzz.trapmf(finished_ratio.universe, [94, 97, 100, 100])

    # ── Membership functions: decision_score ─────────────────────────────
    decision_score['maintain'] = fuzz.trapmf(decision_score.universe, [0,   0,   0.8, 1.6])
    decision_score['modify']   = fuzz.trapmf(decision_score.universe, [1.2, 2.2, 4.0, 4.0])

    # ── Rules ────────────────────────────────────────────────────────────────
    rules = [
        # MAINTAIN conditions
        ctrl.Rule(util_max['low']    & unmet_ratio['low']      & finished_ratio['excellent'], decision_score['maintain']),
        ctrl.Rule(util_max['low']    & unmet_ratio['low']      & finished_ratio['good'],      decision_score['maintain']),
        ctrl.Rule(util_max['medium'] & unmet_ratio['low']      & finished_ratio['excellent'], decision_score['maintain']),
        ctrl.Rule(util_max['medium'] & unmet_ratio['low']      & finished_ratio['good'],      decision_score['maintain']),
        ctrl.Rule(util_max['medium'] & unmet_ratio['moderate'] & finished_ratio['good'],      decision_score['maintain']),

        # MODIFY conditions
        ctrl.Rule(util_max['high']     & unmet_ratio['moderate'],                             decision_score['modify']),
        ctrl.Rule(util_max['high']     & unmet_ratio['high'],                                 decision_score['modify']),
        ctrl.Rule(util_max['high']     & finished_ratio['fair'],                              decision_score['modify']),
        ctrl.Rule(util_max['critical'],                                                        decision_score['modify']),
        ctrl.Rule(unmet_ratio['high'],                                                         decision_score['modify']),
        ctrl.Rule(unmet_ratio['critical'],                                                     decision_score['modify']),
        ctrl.Rule(finished_ratio['poor'],                                                      decision_score['modify']),
        ctrl.Rule(finished_ratio['fair'] & unmet_ratio['moderate'],                           decision_score['modify']),
        ctrl.Rule(finished_ratio['fair'] & util_max['high'],                                  decision_score['modify']),
        ctrl.Rule(util_max['medium']     & unmet_ratio['high'],                               decision_score['modify']),
    ]

    system = ctrl.ControlSystem(rules)
    _fis_sim = ctrl.ControlSystemSimulation(system)
    return _fis_sim


def compute_fis(util_max_val: float,
                unmet_ratio_val: float,
                finished_ratio_val: float) -> dict:
    """
    Run FIS for a single scenario.
    Returns dict with score, level, and input membership info.
    """
    try:
        sim = _build_fis()
        sim.input['util_max']       = float(np.clip(util_max_val,    0, 100))
        sim.input['unmet_ratio']    = float(np.clip(unmet_ratio_val, 0, 100))
        sim.input['finished_ratio'] = float(np.clip(finished_ratio_val, 0, 100))
        sim.compute()
        score = float(sim.output['decision_score'])
    except Exception:
        # Fallback: weighted crisp scoring if FIS fails
        score = _fallback_score(util_max_val, unmet_ratio_val, finished_ratio_val)

    level = "MAINTAIN" if score < 1.6 else "MODIFY"

    # Membership tags for display
    u_tag = _tag(util_max_val,       [45,62,70,80,85,92],  ["LOW","LOW","MEDIUM","HIGH","HIGH","CRITICAL"])
    r_tag = _tag(unmet_ratio_val,    [3,8,12,20,28,40],    ["LOW","LOW","MODERATE","HIGH","HIGH","CRITICAL"])
    f_tag = _tag(finished_ratio_val, [68,78,87,92,94,97],  ["POOR","POOR","FAIR","GOOD","GOOD","EXCELLENT"])

    return {
        "score":          round(score, 3),
        "level":          level,
        "util_tag":       u_tag,
        "unmet_tag":      r_tag,
        "finished_tag":   f_tag,
    }


def _fallback_score(u, r, f):
    u_norm = u / 100
    r_norm = r / 100
    f_norm = 1 - f / 100
    return (0.45 * u_norm + 0.30 * r_norm + 0.25 * f_norm) * 4


def _tag(val, breaks, labels):
    for i, b in enumerate(breaks):
        if val <= b:
            return labels[i]
    return labels[-1]
