"""
Theme — modern navy blue, fresh, professional.
"""
import streamlit as st
from pathlib import Path

LOGO_PATH = Path("assets/lactalis_logo.png")

CSS = """
<style>
/* ── Palette: modern navy blue ───────────────────────────────────────────── */
:root {
  --bg:       #0f1729;
  --bg2:      #192342;
  --bg3:      #1f2d55;
  --border:   #2e4082;
  --primary:  #4096FF;
  --primary2: #1677ff;
  --text:     #f0f4ff;
  --muted:    #8b9ec7;
  --success:  #52c41a;
  --warning:  #faad14;
  --danger:   #ff4d4f;
  --grad:     linear-gradient(135deg, #1677ff22, #4096ff11);
}

/* ── Global ───────────────────────────────────────────────────────────────── */
.stApp { background: var(--bg); }

/* ── Cards / boxes ─────────────────────────────────────────────────────────── */
.page-title {
  font-size:1.6rem; font-weight:800; color:var(--text);
  padding:10px 18px; border-left:5px solid var(--primary);
  background:var(--grad); border-radius:0 8px 8px 0; margin-bottom:1.2rem;
}
.section-title {
  font-size:.82rem; font-weight:700; color:var(--primary);
  text-transform:uppercase; letter-spacing:.1em; margin:1.2rem 0 .45rem;
}
.kpi-box {
  background:var(--bg2); border:1px solid var(--border); border-radius:10px;
  padding:16px 20px; border-top:3px solid var(--primary); margin-bottom:8px;
  transition:.2s;
}
.kpi-box:hover { border-color:var(--primary); background:var(--bg3); }
.kpi-label { font-size:.7rem; color:var(--muted); text-transform:uppercase; letter-spacing:.08em; }
.kpi-value { font-size:1.4rem; font-weight:800; color:var(--text); margin-top:4px; }
.dss-card {
  background:var(--bg2); border:1px solid var(--border); border-radius:12px;
  padding:1.3rem; margin-bottom:12px;
}
.hero {
  background:var(--grad); border:1px solid var(--border); border-radius:14px;
  padding:1.6rem 2rem; margin-bottom:1.4rem;
}
.hero h2 { color:var(--primary); font-size:1.5rem; font-weight:800; margin:0 0 .3rem; }
.hero p  { color:var(--muted); margin:0; font-size:.9rem; }

/* ── Badges ─────────────────────────────────────────────────────────────────── */
.badge-feasible   { background:#135200; color:#95de64; padding:4px 14px; border-radius:6px; font-weight:700; border:1px solid #52c41a; }
.badge-infeasible { background:#5c0011; color:#ff7875; padding:4px 14px; border-radius:6px; font-weight:700; border:1px solid #ff4d4f; }
.badge-maintain   { background:#135200; color:#95de64; padding:3px 10px; border-radius:4px; font-weight:600; font-size:.82rem; }
.badge-modify     { background:#614700; color:#ffd666; padding:3px 10px; border-radius:4px; font-weight:600; font-size:.82rem; }

/* ── Sidebar: nav only, clean ───────────────────────────────────────────────── */
[data-testid="stSidebar"] {
  background: #111c38 !important;
  border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] .stRadio > label > div {
  color: var(--muted); font-size:.82rem; font-weight:600; letter-spacing:.06em;
}
[data-testid="stSidebar"] .stRadio > div > label {
  padding:8px 12px; border-radius:8px; cursor:pointer;
  transition:.15s; display:block; margin:2px 0;
}
[data-testid="stSidebar"] .stRadio > div > label:hover {
  background:var(--bg3); color:var(--primary);
}
[data-testid="stSidebar"] [data-checked="true"] > label {
  background:var(--bg3); border-left:3px solid var(--primary); color:var(--text);
}

/* ── Right panel ─────────────────────────────────────────────────────────────── */
.right-panel {
  background:var(--bg2); border:1px solid var(--border); border-radius:12px;
  padding:1rem 1.1rem; height:100%;
}
.right-panel .section-title { margin-top:.3rem; }

/* ── Streamlit overrides ────────────────────────────────────────────────────── */
div[data-testid="stDataFrame"] { border-radius:10px; overflow:hidden; }
</style>
"""

def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)

def sidebar_brand():
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), use_container_width=True)
        st.markdown("""
        <div style="text-align:center;padding:6px 0 14px;">
          <div style="font-size:.75rem;font-weight:700;color:#4096FF;letter-spacing:.1em;">
            DECISION SUPPORT SYSTEM
          </div>
          <div style="font-size:.68rem;color:#8b9ec7;">PT FBMI · Lactalis · IPB</div>
        </div>""", unsafe_allow_html=True)

def hero(title, subtitle=""):
    st.markdown(f"""
    <div class="hero">
      <h2>{title}</h2>
      {"<p>" + subtitle + "</p>" if subtitle else ""}
    </div>""", unsafe_allow_html=True)

def note(text):
    st.markdown(f'<div style="background:#192342;border-left:4px solid #4096FF;padding:10px 14px;border-radius:4px;color:#8b9ec7;font-size:.88rem;margin:.6rem 0;">ℹ {text}</div>', unsafe_allow_html=True)

def warning(text):
    st.markdown(f'<div style="background:#2d2100;border-left:4px solid #faad14;padding:10px 14px;border-radius:4px;color:#ffd666;font-size:.88rem;margin:.6rem 0;">⚠ {text}</div>', unsafe_allow_html=True)

def right_panel_start():
    """Returns a context column for right settings panel."""
    return st.container()
