import threading
from pathlib import Path

import streamlit as st

from ai_wasteguard import jobs, permissions, registry
import app_state
from ai_wasteguard.db import get_session
from ai_wasteguard.models import JobStatus

st.set_page_config(page_title="Pipelines — AI-WasteGuard", layout="centered")
st.title("Pipelines")
st.caption(
    "Runs the synthetic demo pipeline (collect_data -> prepare_dataset -> "
    "train_model) as a real subprocess job against an isolated directory per "
    "run. This is the same synthetic, non-clinical data described on the "
    "Streamlit demo dashboard - not a real bioinformatics pipeline."
)

user_id = app_state.require_login()

with get_session() as session:
    projects = registry.list_projects_for_owner(session, user_id)
    project_options = {p.title: p.id for p in projects}

if not project_options:
    st.info("No projects yet. Create one on the **Projects** page first.")
    st.stop()

project_id = project_options[st.selectbox("Project", list(project_options.keys()))]


def _run_job_in_background(job_id: str) -> None:
    with get_session() as bg_session:
        jobs.execute_job(bg_session, job_id)


if app_state.current_user_role() not in permissions.CAN_RUN_PIPELINES:
    st.info("Your role does not permit submitting pipeline jobs. You can still view job history below.")
else:
    if st.button("Submit synthetic demo pipeline job"):
        if app_state.check_permission(permissions.CAN_RUN_PIPELINES, "submit a pipeline job"):
            with get_session() as session:
                job = jobs.create_job(session, project_id, user_id)
                job_id = job.id
            threading.Thread(target=_run_job_in_background, args=(job_id,), daemon=True).start()
            st.success(f"Job {job_id[:8]}… submitted. Refresh below to see status.")

st.subheader("Job history")
if st.button("Refresh"):
    st.rerun()

with get_session() as session:
    job_list = jobs.list_jobs_for_project(session, project_id)
    if not job_list:
        st.info("No jobs submitted yet for this project.")
    for job in job_list:
        with st.container(border=True):
            status_icon = {
                JobStatus.QUEUED: "⏳",
                JobStatus.RUNNING: "🔄",
                JobStatus.COMPLETED: "✅",
                JobStatus.FAILED: "❌",
            }[job.status]
            st.markdown(f"{status_icon} **{job.pipeline_name}** — `{job.status.value}`")
            st.caption(f"Submitted: {job.created_at.isoformat()}")
            if job.error_message:
                st.error(job.error_message)
            if job.log:
                with st.expander("Log"):
                    st.code(job.log, language="text")
            if job.status == JobStatus.COMPLETED and job.output_dir:
                metrics_path = Path(job.output_dir) / "results" / "evaluation_metrics.txt"
                if metrics_path.exists():
                    with st.expander("Evaluation metrics"):
                        st.text(metrics_path.read_text())
