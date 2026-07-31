import streamlit as st

import app_state
from ai_wasteguard import auth, dashboard, permissions
from ai_wasteguard.db import get_session

st.set_page_config(page_title="AI-WasteGuard", layout="centered")

st.title("AI-WasteGuard")
st.caption("Environmental surveillance registry — projects, sites, sampling events, samples")

if not app_state.db_is_ready():
    st.error(
        "Database is not migrated yet. Run `alembic upgrade head` from the "
        "project root before using this app."
    )
    st.stop()

if app_state.is_logged_in():
    st.success(f"Logged in as **{st.session_state['user_full_name']}** ({st.session_state['user_email']})")
    st.write(f"Role: `{st.session_state['user_role']}`")
    if st.button("Log out"):
        app_state.logout()
        st.rerun()

    user_id = app_state.current_user_id()
    with get_session() as session:
        summary = dashboard.get_dashboard_summary(session, user_id)

    st.subheader("Overview")
    col1, col2, col3 = st.columns(3)
    col1.metric("Active projects", summary.active_projects)
    col2.metric("Sites", summary.sites)
    col3.metric("Samples", summary.samples)

    st.subheader("Pipeline jobs")
    jcol1, jcol2, jcol3, jcol4 = st.columns(4)
    jcol1.metric("Queued", summary.jobs_queued)
    jcol2.metric("Running", summary.jobs_running)
    jcol3.metric("Completed", summary.jobs_completed)
    jcol4.metric("Failed", summary.jobs_failed)

    st.subheader(f"Approved models ({len(summary.approved_models)})")
    if not summary.approved_models:
        st.caption("None yet.")
    for model in summary.approved_models:
        st.write(f"✅ **{model.name}** — {model.algorithm}")

    st.subheader("Recent activity")
    if not summary.recent_activity:
        st.caption("No activity yet.")
    for event in summary.recent_activity:
        st.caption(f"{event.created_at.isoformat()} — {event.action}" + (f" ({event.details})" if event.details else ""))

    st.write("Use the sidebar to open **Projects**, **Sites and Sampling**, **Uploads**, **Pipelines**, **Reports**, or **Models**.")
else:
    login_tab, register_tab = st.tabs(["Log in", "Register"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in")
        if submitted:
            try:
                app_state.login(email, password)
                st.rerun()
            except auth.AccountLocked as exc:
                st.error(str(exc))
            except auth.AccountDisabled as exc:
                st.error(str(exc))
            except auth.InvalidCredentials as exc:
                st.error(str(exc))

    with register_tab:
        with st.form("register_form"):
            full_name = st.text_input("Full name")
            reg_email = st.text_input("Email", key="reg_email")
            institution = st.text_input("Institution (optional)")
            role = st.selectbox(
                "Role",
                [r.value for r in permissions.SELF_REGISTERABLE_ROLES],
                help="Determines what you can create/edit. Administrator accounts are not self-service.",
            )
            reg_password = st.text_input("Password", type="password", key="reg_password")
            reg_password_confirm = st.text_input("Confirm password", type="password")
            reg_submitted = st.form_submit_button("Register")
        if reg_submitted:
            if not full_name or not reg_email or not reg_password:
                st.error("Full name, email and password are required.")
            elif reg_password != reg_password_confirm:
                st.error("Passwords do not match.")
            elif len(reg_password) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                try:
                    app_state.register(full_name, reg_email, reg_password, institution or None, role)
                    st.success("Account created. You can now log in on the **Log in** tab.")
                except auth.EmailAlreadyRegistered as exc:
                    st.error(str(exc))
