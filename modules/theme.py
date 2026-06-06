"""
Theme — light/white base, palette: #071952 #088395 #37B7C3 #EBF4F6 #FFFFFF
"""
import streamlit as st
from pathlib import Path

LOGO_PATH = Path("assets/lactalis_logo.png")

CSS = """
<style>
/* ── Palette ─────────────────────────────────────────────────────────────────
   #071952  deep navy     → primary text, headings, sidebar bg
   #088395  teal          → primary action, buttons, accents
   #37B7C3  light teal    → hover, highlights, borders
   #EBF4F6  pale blue     → card backgrounds, sidebar content
   #FFFFFF  white         → main page background
──────────────────────────────────────────────────────────────────────────── */

/* ── Global reset ──────────────────────────────────────────────────────────── */
.stApp { background: #FFFFFF !important; }
section[data-testid="stMain"] { background: #FFFFFF; }

/* ── Typography ────────────────────────────────────────────────────────────── */
body, .stMarkdown, p, label { color: #071952 !important; }
h1, h2, h3, h4 { color: #071952 !important; font-weight: 800; }

/* ── Page title ────────────────────────────────────────────────────────────── */
.page-title {
  font-size: 1.55rem; font-weight: 800; color: #071952;
  padding: 10px 18px;
  border-left: 5px solid #088395;
  background: linear-gradient(90deg, #EBF4F6, #FFFFFF);
  border-radius: 0 8px 8px 0;
  margin-bottom: 1.2rem;
}

/* ── Section title ─────────────────────────────────────────────────────────── */
.section-title {
  font-size: .78rem; font-weight: 700; color: #088395;
  text-transform: uppercase; letter-spacing: .1em;
  margin: 1.2rem 0 .45rem;
  border-bottom: 1px solid #EBF4F6;
  padding-bottom: 4px;
}

/* ── KPI box ───────────────────────────────────────────────────────────────── */
.kpi-box {
  background: #EBF4F6;
  border: 1px solid #37B7C3;
  border-top: 3px solid #088395;
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 8px;
  transition: .2s;
}
.kpi-box:hover { background: #d6eef2; }
.kpi-label { font-size: .68rem; color: #088395; text-transform: uppercase; letter-spacing: .09em; font-weight: 600; }
.kpi-value { font-size: 1.4rem; font-weight: 800; color: #071952; margin-top: 4px; }

/* ── DSS card ──────────────────────────────────────────────────────────────── */
.dss-card {
  background: #EBF4F6;
  border: 1px solid #37B7C3;
  border-radius: 12px;
  padding: 1.3rem;
  margin-bottom: 12px;
}

/* ── Hero box ──────────────────────────────────────────────────────────────── */
.hero {
  background: linear-gradient(135deg, #EBF4F6, #FFFFFF);
  border: 1px solid #37B7C3;
  border-left: 5px solid #088395;
  border-radius: 12px;
  padding: 1.5rem 2rem;
  margin-bottom: 1.4rem;
}
.hero h2 { color: #071952 !important; font-size: 1.4rem; font-weight: 800; margin: 0 0 .3rem; }
.hero p  { color: #088395 !important; margin: 0; font-size: .88rem; }

/* ── Badges ────────────────────────────────────────────────────────────────── */
.badge-feasible   { background: #d6f5e0; color: #0a5c2e; padding: 4px 14px; border-radius: 6px; font-weight: 700; border: 1px solid #52c41a; }
.badge-infeasible { background: #fde8e8; color: #8b0000; padding: 4px 14px; border-radius: 6px; font-weight: 700; border: 1px solid #ff4d4f; }
.badge-maintain   { background: #d6f5e0; color: #0a5c2e; padding: 3px 10px; border-radius: 4px; font-weight: 600; font-size: .82rem; }
.badge-modify     { background: #fff3cd; color: #614700; padding: 3px 10px; border-radius: 4px; font-weight: 600; font-size: .82rem; }

/* ── Sidebar ───────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
  background: #071952 !important;
  border-right: 1px solid #088395;
}
[data-testid="stSidebar"] .stRadio > div > label {
  color: #EBF4F6 !important;
  padding: 8px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: .15s;
  display: block;
  margin: 2px 0;
  font-size: .88rem;
}
[data-testid="stSidebar"] .stRadio > div > label:hover {
  background: #088395;
  color: #FFFFFF !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] small,
[data-testid="stSidebar"] div { color: #EBF4F6 !important; }

/* ── Streamlit widget tweaks ───────────────────────────────────────────────── */
.stButton button[kind="primary"] {
  background: #088395 !important;
  border-color: #088395 !important;
  color: white !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
}
.stButton button[kind="primary"]:hover {
  background: #37B7C3 !important;
  border-color: #37B7C3 !important;
}
div[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; border: 1px solid #EBF4F6; }
.stTabs [data-baseweb="tab"] { color: #088395 !important; font-weight: 600; }
.stTabs [aria-selected="true"] { border-bottom: 2px solid #088395 !important; }
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
          <div style="font-size:.72rem;font-weight:700;color:#37B7C3;letter-spacing:.12em;">
            DECISION SUPPORT SYSTEM
          </div>
          <div style="font-size:.68rem;color:#EBF4F6;opacity:.7;">PT FBMI · Lactalis · IPB</div>
        </div>""", unsafe_allow_html=True)

def hero(title, subtitle=""):
    st.markdown(f"""
    <div class="hero">
      <h2>{title}</h2>
      {"<p>" + subtitle + "</p>" if subtitle else ""}
    </div>""", unsafe_allow_html=True)

def note(text):
    st.markdown(
        f'<div style="background:#EBF4F6;border-left:4px solid #088395;padding:10px 14px;'
        f'border-radius:4px;color:#071952;font-size:.88rem;margin:.6rem 0;">ℹ {text}</div>',
        unsafe_allow_html=True)

def warning(text):
    st.markdown(
        f'<div style="background:#fff8e6;border-left:4px solid #faad14;padding:10px 14px;'
        f'border-radius:4px;color:#614700;font-size:.88rem;margin:.6rem 0;">⚠ {text}</div>',
        unsafe_allow_html=True)
