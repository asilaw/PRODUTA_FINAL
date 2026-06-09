"""
modules/decision_model.py
Model evaluasi kapasitas berbasis Machine Learning (Random Forest Classifier).

Menggantikan pendekatan rule-based / FIS murni dengan model yang:
  1. Dilatih dari data sintetis yang merepresentasikan kondisi operasional DES
  2. Mempelajari pola keputusan MAINTAIN/MODIFY dari kombinasi fitur
  3. Menghasilkan confidence score + kontribusi tiap lini
  4. Dapat di-retrain jika data DES baru tersedia

File model disimpan di: models/capacity_classifier.pkl
Fitur input:
  [util_b, util_g, util_d, util_max, unmet_ratio, finished_ratio,
   util_variance, lines_above_80, lines_above_90]
"""
import numpy as np
import pickle
import time
from pathlib import Path

MODEL_PATH = Path("models/capacity_classifier.pkl")
FEATURE_NAMES = [
    "Util Line B (%)", "Util Line G (%)", "Util Line D (%)",
    "Util Maks (%)", "Unmet Ratio (%)", "Finished Ratio (%)",
    "Variansi Utilisasi", "Lini > 80%", "Lini > 90%",
]


def _extract_features(util_b, util_g, util_d, unmet_ratio, finished_ratio):
    """Extract feature vector dari parameter skenario DES."""
    util_max = max(util_b, util_g, util_d)
    util_variance = float(np.var([util_b, util_g, util_d]))
    lines_above_80 = sum(1 for u in [util_b, util_g, util_d] if u > 80)
    lines_above_90 = sum(1 for u in [util_b, util_g, util_d] if u > 90)
    return np.array([
        util_b, util_g, util_d, util_max, unmet_ratio, finished_ratio,
        util_variance, lines_above_80, lines_above_90,
    ])


def _generate_training_data(n_samples=8000):
    """
    Generate data latih sintetis yang merepresentasikan output simulasi DES.

    Label didasarkan pada kombinasi FIS score + aturan bisnis:
    - Unmet demand > threshold → MODIFY (hard rule, tidak bisa ditawar)
    - Utilisasi sangat tinggi (>93%) → MODIFY
    - Kombinasi util menengah + unmet kecil → keputusan FIS-based
    """
    from modules.fis_engine import compute_fis
    np.random.seed(42)

    # Distribusi realistis: mayoritas skenario aman (matching DES output)
    n_safe    = int(n_samples * 0.55)   # kondisi normal/aman
    n_medium  = int(n_samples * 0.30)   # menengah (gray zone)
    n_stressed = n_samples - n_safe - n_medium  # kondisi stres

    def _gen_block(n, util_range, unmet_range):
        util_b  = np.random.uniform(*util_range, n)
        util_g  = np.random.uniform(*util_range, n)
        util_d  = np.random.uniform(util_range[0]*0.8, util_range[1]*0.9, n)
        # Tambahkan korelasi: lini yg sama kondisinya
        util_g  = util_g * 0.85 + util_b * 0.15 + np.random.normal(0, 2, n)
        util_g  = np.clip(util_g, 40, 100)
        unmet   = np.random.uniform(*unmet_range, n)
        unmet   = np.clip(unmet, 0, 100)
        finished = np.clip(100 - unmet + np.random.normal(0, 1.5, n), 0, 100)
        return util_b, util_g, util_d, unmet, finished

    blocks = [
        _gen_block(n_safe,    (40, 82), (0, 1.5)),
        _gen_block(n_medium,  (75, 92), (0, 8)),
        _gen_block(n_stressed,(82, 100),(0, 30)),
    ]

    features, labels = [], []
    for util_b, util_g, util_d, unmet, finished in blocks:
        for i in range(len(util_b)):
            ub, ug, ud = util_b[i], util_g[i], util_d[i]
            um, fi = unmet[i], finished[i]
            umax = max(ub, ug, ud)
            score = compute_fis(umax, um, fi)
            feat = _extract_features(ub, ug, ud, um, fi)
            features.append(feat)

            # Labeling logic (expert-calibrated):
            if um > 5.0:
                lbl = "MODIFY"   # unmet signifikan → hard rule
            elif umax > 93:
                lbl = "MODIFY"   # utilisasi sangat tinggi → hard rule
            elif score >= 2.0:
                lbl = "MODIFY"   # FIS score menunjukkan risiko
            else:
                lbl = "MAINTAIN"
            labels.append(lbl)

    return np.array(features), np.array(labels)


def train_model(progress_fn=None):
    """
    Latih model Random Forest dari data sintetis.
    progress_fn: callable(float, str) untuk update progress bar Streamlit.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import cross_val_score

    if progress_fn: progress_fn(0.05, "Menyiapkan data latih...")
    time.sleep(0.3)

    X, y = _generate_training_data(8000)
    if progress_fn: progress_fn(0.35, "Data latih siap — melatih model...")
    time.sleep(0.3)

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", RandomForestClassifier(
            n_estimators=150,
            max_depth=10,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )),
    ])
    model.fit(X, y)
    if progress_fn: progress_fn(0.75, "Validasi model (cross-validation)...")
    time.sleep(0.2)

    scores = cross_val_score(model, X, y, cv=5, scoring="f1_weighted")
    cv_mean = float(scores.mean())
    if progress_fn: progress_fn(0.90, "Menyimpan model...")
    time.sleep(0.2)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    meta = {"cv_f1": round(cv_mean, 4), "n_samples": len(X), "trained_at": time.strftime("%Y-%m-%d %H:%M")}
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "meta": meta}, f)

    if progress_fn: progress_fn(1.0, "Model siap.")
    return model, meta


def load_model():
    """Load model dari file pkl. Return (model, meta) atau (None, None)."""
    if not MODEL_PATH.exists():
        return None, None
    try:
        with open(MODEL_PATH, "rb") as f:
            data = pickle.load(f)
        return data["model"], data.get("meta", {})
    except Exception:
        return None, None


def evaluate_scenarios(scenarios: list, model=None) -> list:
    """
    Evaluasi daftar skenario dengan model ML.

    scenarios: list of dict dengan keys:
        util_b, util_g, util_d, unmet_ratio, finished_ratio

    Returns list of dict:
        decision, confidence, level, feature_contributions
    """
    if model is None:
        return None

    results = []
    for s in scenarios:
        feat = _extract_features(
            s.get("util_b", 0), s.get("util_g", 0), s.get("util_d", 0),
            s.get("unmet_ratio", 0), s.get("finished_ratio", 100),
        )
        proba = model.predict_proba([feat])[0]
        classes = model.classes_
        pred = model.predict([feat])[0]
        pred_idx = list(classes).index(pred)
        confidence = float(proba[pred_idx])

        # Feature contributions via RF feature importances
        clf = model.named_steps.get("clf", model)
        if hasattr(clf, "feature_importances_"):
            importances = clf.feature_importances_
            # Ambil top-3 contributing features
            top_idx = np.argsort(importances)[::-1][:3]
            contrib = [(FEATURE_NAMES[i], round(importances[i]*100, 1)) for i in top_idx]
        else:
            contrib = []

        results.append({
            "decision":               pred,
            "confidence":             round(confidence * 100, 1),
            "feature_contributions":  contrib,
        })
    return results
