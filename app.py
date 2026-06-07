"""
Decision Support System — PT FBMI Lactalis, TIN IPB 2026
"""
import streamlit as st
import streamlit.components.v1 as _stc
from pathlib import Path
from modules.session import init_session, get_state, set_state

LOGO        = "assets/lactalis_logo.png"
LOGO_SQUARE = "assets/lactalis_logo_square.png"
FAVICON     = LOGO_SQUARE if Path(LOGO_SQUARE).exists() else (LOGO if Path(LOGO).exists() else None)

st.set_page_config(
    page_title="Decision Support System",
    page_icon=FAVICON or ":material/factory:",
    layout="wide",
    initial_sidebar_state="expanded",
)
init_session()

from modules.theme import inject_css, sidebar_brand
inject_css()

from modules.user_manager import (verify_session, create_session,
                                   verify_login, register, load_users, save_users)
import hashlib, re as _re

def _hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def _pw_valid(pw):
    if len(pw) < 8:                        return False, "Minimal 8 karakter."
    if not _re.search(r'[0-9]', pw):       return False, "Harus mengandung angka."
    if not _re.search(r'[^a-zA-Z0-9]',pw): return False, "Harus mengandung simbol."
    return True, ""

def _auto_login():
    if get_state("logged_in"): return True
    p = Path("data/.session_token")
    if p.exists():
        try:
            ok, uname = verify_session(p.read_text().strip())
            if ok:
                users = load_users()
                udata = users.get(uname, {})
                set_state("logged_in", True)
                set_state("user_name", udata.get("name", ""))
                set_state("_username", uname)
                return True
        except Exception:
            pass
    return False

# ── LOGIN PAGE ──────────────────────────────────────────────────────────────
def auth_page():
    _stc.html("<script>document.title='Decision Support System — Masuk'</script>", height=0)

    # Inject login-specific CSS override
    st.markdown("""
    <style>
    /* Hide streamlit header & footer on login */
    [data-testid="stHeader"] { display: none !important; }
    [data-testid="stSidebar"] { display: none !important; }
    footer { display: none !important; }
    section.main > div { padding: 0 !important; }
    [data-testid="stAppViewContainer"] { padding: 0 !important; }

    /* Login split layout */
    .login-wrap {
        display: flex; min-height: 100vh; width: 100%;
    }
    .login-left {
        flex: 1; background: linear-gradient(135deg, #071952 0%, #088395 60%, #37B7C3 100%);
        display: flex; flex-direction: column; justify-content: center;
        padding: 60px 56px; position: relative; overflow: hidden;
    }
    .login-left::before {
        content: '';
        position: absolute; top: -120px; right: -120px;
        width: 420px; height: 420px; border-radius: 50%;
        border: 80px solid rgba(255,255,255,0.06);
    }
    .login-left::after {
        content: '';
        position: absolute; bottom: -80px; left: -60px;
        width: 300px; height: 300px; border-radius: 50%;
        border: 60px solid rgba(255,255,255,0.04);
    }
    .login-left h1 {
        color: #ffffff !important; font-size: 2.8rem; font-weight: 900;
        line-height: 1.18; margin: 24px 0 18px; position: relative; z-index: 1;
    }
    .login-left p {
        color: rgba(255,255,255,0.75); font-size: 1.05rem;
        line-height: 1.6; max-width: 360px; position: relative; z-index: 1;
    }
    .login-left .brand-tag {
        color: rgba(255,255,255,0.5); font-size: .8rem;
        position: absolute; bottom: 32px; left: 56px; z-index: 1;
    }
    .login-right {
        flex: 1; background: #ffffff;
        display: flex; flex-direction: column; justify-content: center;
        padding: 60px 64px;
    }
    .login-right h2 {
        font-size: 1.9rem; font-weight: 800; color: #071952 !important; margin: 0 0 6px;
    }
    .login-right .sub { color: #088395; font-size: .94rem; margin-bottom: 36px; }
    </style>
    """, unsafe_allow_html=True)

    # Split layout via columns
    left, right = st.columns([1, 1])

    with left:
        logo_path = LOGO if Path(LOGO).exists() else None
        st.markdown(f"""
        <div class="login-left">
            {'<img src="data:image/png;base64,' + __import__('base64').b64encode(open(logo_path,'rb').read()).decode() + '" style="width:160px;position:relative;z-index:1;" />' if logo_path else ''}
            <h1>Sistem Pengambilan<br>Keputusan<br>Kapasitas Produksi</h1>
            <p>Perencanaan kapasitas berbasis data — dari forecast permintaan hingga rekomendasi investasi mesin, dalam satu platform terintegrasi.</p>
            <div class="brand-tag">PT FBMI &middot; Lactalis Group &middot; IPB University &middot; 2026</div>
        </div>
        """, unsafe_allow_html=True)

    with right:
        st.markdown("""
        <div class="login-right">
            <h2>Selamat Datang</h2>
            <div class="sub">Masuk untuk mengakses sistem atau daftar akun baru.</div>
        </div>
        """, unsafe_allow_html=True)

        login_tab, reg_tab = st.tabs(["Masuk", "Daftar Akun"])

        with login_tab:
            user = st.text_input("Username", key="l_user", placeholder="Masukkan username")
            pwd  = st.text_input("Password", type="password", key="l_pwd", placeholder="Masukkan password")
            if st.button("Masuk", type="primary", use_container_width=True, key="btn_login"):
                if not user.strip() or not pwd:
                    st.error("Isi username dan password.")
                else:
                    ok, udata = verify_login(user.strip(), pwd)
                    if ok:
                        token = create_session(user.strip())
                        Path("data").mkdir(exist_ok=True)
                        Path("data/.session_token").write_text(token)
                        set_state("logged_in", True)
                        set_state("user_name", udata.get("name", ""))
                        set_state("_username", user.strip())
                        st.rerun()
                    else:
                        st.error("Username atau password salah.")

        with reg_tab:
            st.caption("Password: min. 8 karakter, mengandung angka dan simbol.")
            r_name = st.text_input("Nama Lengkap", key="r_name", placeholder="Nama lengkap Anda")
            r_user = st.text_input("Username",     key="r_user", placeholder="Pilih username unik")
            r_pwd  = st.text_input("Password",     type="password", key="r_pwd")
            r_pwd2 = st.text_input("Konfirmasi Password", type="password", key="r_pwd2")
            if st.button("Daftar Akun", type="primary", use_container_width=True, key="btn_reg"):
                if not r_name.strip():   st.error("Nama tidak boleh kosong.")
                elif not r_user.strip(): st.error("Username tidak boleh kosong.")
                elif r_pwd != r_pwd2:    st.error("Konfirmasi password tidak cocok.")
                else:
                    valid_pw, pw_msg = _pw_valid(r_pwd)
                    if not valid_pw:
                        st.error(f"Password tidak valid: {pw_msg}")
                    else:
                        ok, msg = register(r_user.strip(), r_pwd, r_name.strip())
                        if ok: st.success("Akun berhasil dibuat. Silakan masuk.")
                        else:  st.error(msg)

# ── MAIN APP ────────────────────────────────────────────────────────────────
if not _auto_login():
    auth_page()
    st.stop()

# Greeting
_uname   = get_state("_username") or ""
_uname_d = get_state("user_name") or ""
_first   = _uname_d.split()[0].title() if _uname_d else _uname
_greeting = "Hi, Admin!" if _uname.lower() == "admin" else f"Hi, {_first}!"

# Left sidebar: navigation only
sidebar_brand()
MENUS = ["Analisis Demand", "Capacity Simulation", "Capacity Planning",
         "Production Allocation", "Investment Catalog"]
with st.sidebar:
    st.markdown(
        f'<div style="color:#37B7C3;font-size:.86rem;font-weight:600;padding:0 0 10px 2px;">'
        f'{_greeting}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:.68rem;color:#EBF4F6;text-transform:uppercase;'
        'letter-spacing:.08em;opacity:.55;margin-bottom:4px;">Menu</div>',
        unsafe_allow_html=True)
    page = st.radio("", MENUS, label_visibility="collapsed", key="main_nav")

# Dynamic title
_stc.html(f"<script>document.title='Decision Support System — {page}'</script>", height=0)

# Top-right: Profile + Logout
_, _tr = st.columns([7, 1])
with _tr:
    _c1, _c2 = st.columns(2)
    with _c1:
        with st.popover("Profil", use_container_width=True):
            st.markdown(f"**{_uname_d or _uname}**")
            st.caption(f"Username: {_uname}")
            st.markdown("---")
            st.markdown("**Ubah Nama**")
            new_name = st.text_input("", value=_uname_d, key="pf_name",
                                      label_visibility="collapsed")
            if st.button("Simpan", key="btn_nm", type="primary"):
                users = load_users()
                if _uname in users:
                    users[_uname]["name"] = new_name.strip()
                    save_users(users)
                    set_state("user_name", new_name.strip())
                    st.success("Nama diperbarui.")
            st.markdown("**Ubah Password**")
            old_pw = st.text_input("Password lama", type="password", key="pf_old")
            new_pw = st.text_input("Password baru", type="password", key="pf_new",
                                    help="Min 8 karakter, angka, dan simbol.")
            if st.button("Simpan password", key="btn_pw"):
                v_ok, v_msg = _pw_valid(new_pw)
                if not v_ok:
                    st.error(v_msg)
                else:
                    lok, _ = verify_login(_uname, old_pw)
                    if not lok: st.error("Password lama salah.")
                    else:
                        users = load_users()
                        users[_uname]["password"] = _hash_pw(new_pw)
                        save_users(users); st.success("Password diperbarui.")
    with _c2:
        if st.button("Keluar", use_container_width=True, key="btn_logout"):
            Path("data/.session_token").unlink(missing_ok=True)
            set_state("logged_in", False); st.rerun()

st.markdown("---")

# Route
if page == "Analisis Demand":
    from views.demand_overview import render; render()
elif page == "Capacity Simulation":
    from views.capacity_simulation import render; render()
elif page == "Capacity Planning":
    from views.capacity_planning import render; render()
elif page == "Production Allocation":
    from views.production_allocation import render; render()
else:
    from views.investment_catalog import render; render()
