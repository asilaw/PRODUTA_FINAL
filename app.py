"""
PRODUTA DSS — Integrated
PT FBMI (Lactalis) · TIN IPB 2026

Forecast (Ubay) → Capacity Simulation (Asil) → FIS + Financial (Gibran)
"""
import streamlit as st
from modules.session import init_session, get_state, set_state
from modules.theme import inject_css, sidebar_brand

st.set_page_config(
    page_title="PRODUTA DSS — FBMI Lactalis",
    page_icon="🥛",
    layout="wide",
    initial_sidebar_state="expanded",
)
init_session()
inject_css()


def login_page():
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        from pathlib import Path
        if Path("assets/lactalis_logo.png").exists():
            st.image("assets/lactalis_logo.png", use_container_width=True)
        st.markdown("""
        <div style="text-align:center;padding:16px 0;">
          <div style="font-size:1.9rem;font-weight:800;color:#f0f6fc;">PRODUTA DSS</div>
          <div style="color:#8b949e;font-size:.9rem;">Production Capacity Decision Support System</div>
          <div style="color:#58a6ff;font-size:.8rem;margin-top:4px;">PT FBMI · Lactalis Group · TIN IPB 2026</div>
        </div>""", unsafe_allow_html=True)
        st.markdown("---")
        user = st.text_input("Username", value="admin", key="l_user")
        pwd  = st.text_input("Password", type="password", value="fbmi2026", key="l_pwd")
        if st.button("Login", type="primary", use_container_width=True):
            if user.strip() and pwd.strip():
                set_state("logged_in", True)
                set_state("user_name", user.strip())
                st.rerun()
            else:
                st.error("Username dan password tidak boleh kosong.")
        st.caption("Demo: admin / fbmi2026")

if not get_state("logged_in"):
    login_page()
    st.stop()

sidebar_brand()

with st.sidebar:
    st.markdown('<div class="section-title">Navigation</div>', unsafe_allow_html=True)
    page = st.radio("", [
        "Demand Overview",
        "Capacity Simulation",
        "Capacity Planning",
        "Production Allocation",
        "Investment Catalog",
    ], label_visibility="collapsed")

    st.markdown("---")
    st.markdown('<div class="section-title">Data</div>', unsafe_allow_html=True)
    if st.button("⬆ Upload", use_container_width=True, key="sidebar_upload"):
        set_state("goto_upload", True)

    st.markdown("---")
    st.caption(f"Logged in as: **{get_state('user_name') or 'user'}**")
    if st.button("Logout", use_container_width=True):
        set_state("logged_in", False)
        st.rerun()

# Route
if page == "Demand Overview":
    from views.demand_overview import render; render()
elif page == "Capacity Simulation":
    from views.capacity_simulation import render; render()
elif page == "Capacity Planning":
    from views.capacity_planning import render; render()
elif page == "Production Allocation":
    from views.production_allocation import render; render()
else:
    from views.investment_catalog import render; render()
