"""
Decision Support System — PT FBMI Lactalis
TIN IPB 2026
"""
import streamlit as st
import streamlit.components.v1 as _stc
from pathlib import Path
from modules.session import init_session, get_state, set_state
from modules.theme import inject_css, sidebar_brand

# ── Page config — always "Decision Support System" base ───────────────────────
LOGO = "assets/lactalis_logo.png" if Path("assets/lactalis_logo.png").exists() else "🧊"
st.set_page_config(
    page_title="Decision Support System",
    page_icon=LOGO,
    layout="wide",
    initial_sidebar_state="expanded",
)
init_session()
inject_css()

# ── Session persistence via token file ─────────────────────────────────────────
from modules.user_manager import verify_session, create_session, verify_login, register

def _auto_login():
    """Try to restore login from saved session token."""
    if get_state("logged_in"):
        return True
    token_file = Path("data/.session_token")
    if token_file.exists():
        token = token_file.read_text().strip()
        ok, username = verify_session(token)
        if ok:
            set_state("logged_in", True)
            set_state("user_name", username)
            set_state("_session_token", token)
            return True
    return False

# ── Login / Register page ──────────────────────────────────────────────────────
def auth_page():
    _stc.html("<script>document.title='Decision Support System — Log In'</script>", height=0)

    # Center container
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        if Path(LOGO).exists():
            st.image(LOGO, use_container_width=True)

        st.markdown("""
        <div style="text-align:center;padding:18px 0 8px;">
          <div style="font-size:1.75rem;font-weight:900;color:#f0f4ff;letter-spacing:.02em;">
            Decision Support System
          </div>
          <div style="color:#8b9ec7;font-size:.88rem;margin-top:4px;">PT FBMI – Lactalis Group</div>
          <div style="color:#4096FF;font-size:.78rem;margin-top:2px;">IPB University &nbsp;·&nbsp; 2026</div>
        </div>""", unsafe_allow_html=True)

        st.markdown("---")

        login_tab, reg_tab = st.tabs(["🔑 Masuk", "📝 Daftar Akun"])

        with login_tab:
            user = st.text_input("Username", key="l_user")
            pwd  = st.text_input("Password", type="password", key="l_pwd")
            if st.button("Login", type="primary", use_container_width=True):
                ok, udata = verify_login(user.strip(), pwd)
                if ok:
                    token = create_session(user.strip())
                    Path("data/.session_token").parent.mkdir(parents=True, exist_ok=True)
                    Path("data/.session_token").write_text(token)
                    set_state("logged_in", True)
                    set_state("user_name", udata.get("name", user))
                    set_state("_session_token", token)
                    st.rerun()
                else:
                    st.error("Username atau password salah.")

        with reg_tab:
            r_name  = st.text_input("Nama Lengkap", key="r_name")
            r_phone = st.text_input("Nomor HP", key="r_phone")
            r_user  = st.text_input("Username", key="r_user")
            r_pwd   = st.text_input("Password", type="password", key="r_pwd")
            r_pwd2  = st.text_input("Konfirmasi Password", type="password", key="r_pwd2")
            if st.button("Daftar", type="primary", use_container_width=True):
                if r_pwd != r_pwd2:
                    st.error("Password tidak cocok.")
                elif not r_name.strip():
                    st.error("Nama lengkap tidak boleh kosong.")
                else:
                    ok, msg = register(r_user.strip(), r_pwd, r_name.strip(), r_phone.strip())
                    if ok:
                        st.success(f"✓ {msg} Silakan login.")
                    else:
                        st.error(msg)

# ── Check session ─────────────────────────────────────────────────────────────
if not _auto_login():
    auth_page()
    st.stop()

# ── MAIN APP ───────────────────────────────────────────────────────────────────
sidebar_brand()

MENUS = [
    "Demand Overview",
    "Capacity Simulation",
    "Capacity Planning",
    "Production Allocation",
    "Investment Catalog",
]

with st.sidebar:
    st.markdown('<div class="section-title">Navigation</div>', unsafe_allow_html=True)
    page = st.radio("", MENUS, label_visibility="collapsed", key="main_nav")
    st.markdown("---")
    st.caption(f"👤 {get_state('user_name') or 'User'}")
    if st.button("Logout", use_container_width=True):
        Path("data/.session_token").unlink(missing_ok=True)
        set_state("logged_in", False)
        st.rerun()

# Dynamic browser title
_stc.html(f"<script>document.title='Decision Support System — {page}'</script>", height=0)

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
