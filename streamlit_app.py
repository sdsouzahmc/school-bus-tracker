"""School Bus Tracker — demo of the one-page specification (crew app, office portal, parent portal; English / Arabic)."""
import os
import random

import streamlit as st

import db
from i18n import rtl_css, t

st.set_page_config(page_title="School Bus Tracker", page_icon="🚌", layout="wide", initial_sidebar_state="auto")

DATASET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "School_Bus_Trip_Dataset.xlsx")


@st.cache_resource
def _boot():
    """First run: load the supplied dataset workbook (or generate the full-size demo if it is missing)."""
    fresh = not os.path.exists(db.DB_PATH)
    db.init_db(seed_data=False)
    if fresh or not db.q1("SELECT id FROM buses LIMIT 1"):
        if os.path.exists(DATASET):
            from dataset_import import import_workbook
            import_workbook(DATASET, os.path.basename(DATASET))
        else:
            db.init_db(reset=True)
    return True


_boot()

st.markdown("""<style>
  .block-container {padding-top: 1.2rem;}
  .ok   {background:#e6f6ea;border-left:6px solid #1e8e3e;padding:10px 14px;border-radius:8px;font-size:1.05rem;margin:6px 0}
  .warn {background:#fff4e0;border-left:6px solid #e8a200;padding:10px 14px;border-radius:8px;font-size:1.05rem;margin:6px 0}
  .error{background:#fde8e8;border-left:6px solid #d93025;padding:10px 14px;border-radius:8px;font-size:1.05rem;margin:6px 0}
  .card {background:#f6f8fb;border:1px solid #e3e8ef;border-radius:10px;padding:10px 14px;margin:6px 0}
  .muted{color:#667085;font-size:.85rem}
  .pill {display:inline-block;padding:2px 10px;border-radius:12px;font-size:.8rem;font-weight:600;background:#eef2f7}
</style>""" + rtl_css(), unsafe_allow_html=True)


def login():
    st.title("🚌 " + t("School Bus Tracker"))
    st.caption(db.setting("school_name", db.SCHOOL_NAME) + " · " + db.setting("data_source", ""))
    c1, c2 = st.columns([1, 1])
    with c1:
        lang = st.radio(t("Language"), ["English", "العربية"], horizontal=True, index=1 if st.session_state.get("lang") == "ar" else 0)
        if (lang == "العربية") != (st.session_state.get("lang") == "ar"):
            st.session_state.lang = "ar" if lang == "العربية" else "en"
            st.rerun()
        pend = st.session_state.get("mfa_pending")
        if pend:
            st.info(f"Two-step verification for **{pend['display_name']}**. In production the code comes from an authenticator app "
                    f"or SMS. Demo code: **{st.session_state.mfa_code}**")
            with st.form("mfa"):
                code = st.text_input(t("Verification code"), max_chars=6)
                ok = st.form_submit_button(t("Verify"), type="primary")
            if ok:
                if code.strip() == st.session_state.mfa_code:
                    st.session_state.user = pend
                    st.session_state.pop("mfa_pending")
                    db.audit(pend["username"], pend["role"], "LOGIN", "user", pend["username"], "password + MFA")
                    st.rerun()
                else:
                    db.audit(pend["username"], pend["role"], "MFA_FAILED", "user", pend["username"])
                    st.error(t("Wrong code."))
            if st.button("Cancel"):
                st.session_state.pop("mfa_pending")
                st.rerun()
            return
        with st.form("login"):
            u = st.text_input(t("Username"))
            p = st.text_input(t("PIN / password"), type="password")
            ok = st.form_submit_button(t("Sign in"), type="primary")
        if ok:
            user = db.get_user(u, p)
            if not user:
                db.audit(u, "", "LOGIN_FAILED", "user", u)
                st.error(t("Wrong username or PIN."))
            elif user["role"] in db.MFA_ROLES:
                st.session_state.mfa_pending = user
                st.session_state.mfa_code = f"{random.randint(0, 999999):06d}"
                st.rerun()
            else:
                st.session_state.user = user
                db.audit(user["username"], user["role"], "LOGIN", "user", user["username"])
                st.rerun()
    with c2:
        st.markdown("**Demo logins**")
        st.markdown("""
| Role | Login | PIN |
|---|---|---|
| Administrator (MFA) | `admin` | `admin123` |
| Transport manager (MFA) | `manager` | `manager123` |
| Dispatcher | `dispatcher` | `1234` |
| Bus supervisor / care-taker | `sup01` / `care01` | `1234` |
| Driver (view only) | `drv01` | `1234` |
| School receiving staff | `recv1` | `1234` |
| Parent / guardian | `g001` … | `1234` |
""")


if "user" not in st.session_state:
    login()
    st.stop()

user = st.session_state.user
role = user["role"]

with st.sidebar:
    st.markdown(f"**{user['display_name']}**  \n<span class='muted'>{role.title()} · {user['username']}</span>", unsafe_allow_html=True)
    lang = st.radio(t("Language"), ["English", "العربية"], horizontal=True, index=1 if st.session_state.get("lang") == "ar" else 0)
    if (lang == "العربية") != (st.session_state.get("lang") == "ar"):
        st.session_state.lang = "ar" if lang == "العربية" else "en"
        st.rerun()
    if st.button(t("Sign out"), width="stretch"):
        db.audit(user["username"], role, "LOGOUT", "user", user["username"])
        for k in list(st.session_state):
            if k != "lang":
                del st.session_state[k]
        st.rerun()
    st.caption(db.setting("data_source", ""))

P = {
    "crew": st.Page("page_crew.py", title=t("Crew app"), icon="📷"),
    "receipt": st.Page("page_receipt.py", title=t("School receipt"), icon="🏫"),
    "parent": st.Page("page_parent.py", title=t("My children"), icon="👪"),
    "live": st.Page("page_live.py", title="Live trips", icon="🗺️"),
    "lists": st.Page("page_lists.py", title="Daily bus lists", icon="📋"),
    "exceptions": st.Page("page_exceptions.py", title="Exceptions & approvals", icon="🚨"),
    "notices": st.Page("page_notices.py", title="Parent notices", icon="✉️"),
    "reports": st.Page("page_reports.py", title="Reports", icon="📊"),
    "setup": st.Page("page_setup.py", title="Setup & data", icon="⚙️"),
}
MENU = {
    "supervisor": ["crew"], "caretaker": ["crew"], "driver": ["crew"],
    "receiving": ["receipt"],
    "guardian": ["parent"],
    "dispatcher": ["live", "lists", "exceptions", "notices", "reports", "crew", "receipt"],
    "manager": ["live", "lists", "exceptions", "notices", "reports", "setup", "crew", "receipt"],
    "admin": ["live", "lists", "exceptions", "notices", "reports", "setup", "crew", "receipt", "parent"],
}
st.navigation([P[k] for k in MENU.get(role, [])]).run()
