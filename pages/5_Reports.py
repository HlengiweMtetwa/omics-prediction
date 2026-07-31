from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import app_state
from ai_wasteguard import registry, reports
from ai_wasteguard.db import get_session

st.set_page_config(page_title="Reports — AI-WasteGuard", layout="centered")
st.title("Reports")

user_id = app_state.require_login()

with get_session() as session:
    projects = registry.list_projects_for_owner(session, user_id)
    project_options = {p.title: p.id for p in projects}

if not project_options:
    st.info("No projects yet. Create one on the **Projects** page first.")
    st.stop()

project_id = project_options[st.selectbox("Project", list(project_options.keys()))]

if st.button("Generate project summary report"):
    with get_session() as session:
        report = reports.generate_project_summary_report(session, project_id, user_id)
        report_id = report.id
    st.success(f"Report generated ({report_id[:8]}…).")

st.subheader("Generated reports")
with get_session() as session:
    report_list = reports.list_reports_for_project(session, project_id)
    if not report_list:
        st.info("No reports generated yet.")
    for report in report_list:
        content = Path(report.file_path).read_bytes()
        with st.container(border=True):
            st.markdown(f"**{report.report_type}** — {report.created_at.isoformat()}")
            st.caption(f"SHA-256: {report.content_hash[:16]}…")
            st.download_button(
                "Download HTML",
                data=content,
                file_name=f"{report.report_type}_{report.id[:8]}.html",
                mime="text/html",
                key=f"download_{report.id}",
            )
            with st.expander("Preview"):
                components.html(content.decode("utf-8"), height=500, scrolling=True)
