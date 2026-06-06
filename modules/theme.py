"""
Theme module — dark theme matching student's DSS, with Lactalis branding.
Adapted from Asil's theme.py to work with dark color scheme.
"""
import streamlit as st
from pathlib import Path

LOGO_PATH = Path("assets/lactalis_logo.png")

DARK_CSS = """
<style>
:root {
  --bg:#0d1117; --bg2:#161b22; --border:#30363d;
  --primary:#58a6ff; --text:#f0f6fc; --muted:#8b949e;
  --success:#3fb950; --warning:#d29922; --danger:#f85149;
}
.page-title{font-size:1.55rem;font-weight:700;color:var(--text);
  border-left:4px solid var(--primary);padding:6px 14px;margin-bottom:1rem;}
.section-title{font-size:.95rem;font-weight:600;color:var(--primary);
  text-transform:uppercase;letter-spacing:.08em;margin:1.2rem 0 .4rem;}
.kpi-box{background:var(--bg2);border:1px solid var(--border);border-radius:8px;
  padding:14px 18px;border-left:4px solid var(--primary);margin-bottom:8px;}
.kpi-label{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;}
.kpi-value{font-size:1.35rem;font-weight:700;color:var(--text);margin-top:2px;}
.dss-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
  padding:1.2rem;margin-bottom:12px;}
.hero{background:var(--bg2);border:1px solid var(--border);border-radius:12px;
  padding:1.4rem 1.8rem;margin-bottom:1.2rem;}
.hero h2{color:var(--primary);margin:0 0 .3rem;}
.hero p{color:var(--muted);margin:0;}
.note-box{background:#1c2128;border-left:4px solid var(--primary);
  padding:10px 14px;border-radius:4px;color:var(--muted);font-size:.88rem;margin:.6rem 0;}
.warn-box{background:#272115;border-left:4px solid var(--warning);
  padding:10px 14px;border-radius:4px;color:#e3b341;font-size:.88rem;margin:.6rem 0;}
.badge-feasible{background:#238636;color:#fff;padding:4px 14px;border-radius:6px;font-weight:700;}
.badge-infeasible{background:#da3633;color:#fff;padding:4px 14px;border-radius:6px;font-weight:700;}
.badge-maintain{background:#238636;color:#fff;padding:3px 10px;border-radius:4px;font-weight:600;font-size:.82rem;}
.badge-modify{background:#d29922;color:#fff;padding:3px 10px;border-radius:4px;font-weight:600;font-size:.82rem;}
</style>
"""

def inject_css():
    st.markdown(DARK_CSS, unsafe_allow_html=True)

def sidebar_brand():
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), use_container_width=True)
        st.markdown("""
        <div style="text-align:center;padding:8px 0 12px;">
          <div style="font-size:.8rem;font-weight:700;color:#58a6ff;letter-spacing:.12em;">
            DECISION SUPPORT SYSTEM
          </div>
          <div style="font-size:.7rem;color:#8b949e;">PT FBMI · Lactalis · IPB TIN</div>
        </div>""", unsafe_allow_html=True)

def hero(title, subtitle=""):
    st.markdown(f"""
    <div class="hero">
      <h2>{title}</h2>
      {"<p>" + subtitle + "</p>" if subtitle else ""}
    </div>""", unsafe_allow_html=True)

def note(text):
    st.markdown(f'<div class="note-box">ℹ {text}</div>', unsafe_allow_html=True)

def warning(text):
    st.markdown(f'<div class="warn-box">⚠ {text}</div>', unsafe_allow_html=True)
