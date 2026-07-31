import streamlit as st

import app_state
from ai_wasteguard import jobs, model_registry, permissions, registry
from ai_wasteguard.db import get_session
from ai_wasteguard.models import JobStatus, ModelApprovalStatus

st.set_page_config(page_title="Models — AI-WasteGuard", layout="centered")
st.title("Models")

user_id = app_state.require_login()
user_role = app_state.current_user_role()

with get_session() as session:
    projects = registry.list_projects_for_owner(session, user_id)
    project_options = {p.title: p.id for p in projects}

if not project_options:
    st.info("No projects yet. Create one on the **Projects** page first.")
    st.stop()

project_id = project_options[st.selectbox("Project", list(project_options.keys()))]

st.subheader("Register a model from a completed job")
if user_role not in permissions.CAN_REGISTER_MODELS:
    st.info("Your role does not permit registering models.")
else:
    with get_session() as session:
        completed_jobs = [
            j for j in jobs.list_jobs_for_project(session, project_id) if j.status == JobStatus.COMPLETED
        ]
        job_options = {f"{j.pipeline_name} — {j.created_at.isoformat()}": j.id for j in completed_jobs}

    if not job_options:
        st.info("No completed jobs yet for this project. Submit one on the **Pipelines** page.")
    else:
        job_id = job_options[st.selectbox("Completed job", list(job_options.keys()))]
        model_name = st.text_input("Model name (optional)")
        if st.button("Register model"):
            if app_state.check_permission(permissions.CAN_REGISTER_MODELS, "register a model"):
                try:
                    with get_session() as session:
                        model_registry.register_model_from_job(session, job_id, user_id, name=model_name or None)
                    st.success("Model registered.")
                except model_registry.ModelRegistrationError as exc:
                    st.error(str(exc))

st.subheader("Registered models")
with get_session() as session:
    model_list = model_registry.list_models_for_project(session, project_id)
    if not model_list:
        st.info("No models registered yet.")
    for model in model_list:
        with st.container(border=True):
            badge = {
                ModelApprovalStatus.DRAFT: "🟡 draft",
                ModelApprovalStatus.APPROVED: "🟢 approved",
                ModelApprovalStatus.DEPRECATED: "⚫ deprecated",
            }[model.approval_status]
            st.markdown(f"**{model.name}** — {badge}")
            st.caption(f"Algorithm: {model.algorithm} · Target: {model.target_variable}")
            if model.metrics:
                with st.expander("Metrics"):
                    st.text(model.metrics)
            with st.expander("Intended use / prohibited use"):
                st.write(f"**Intended use:** {model.intended_use}")
                st.write(f"**Prohibited use:** {model.prohibited_use}")

            if model.approval_status == ModelApprovalStatus.DRAFT:
                if user_role not in permissions.CAN_APPROVE_MODELS:
                    st.caption("Approval requires the Administrator role.")
                else:
                    if st.button("Approve", key=f"approve_{model.id}"):
                        if app_state.check_permission(permissions.CAN_APPROVE_MODELS, "approve a model"):
                            with get_session() as approval_session:
                                model_registry.approve_model(approval_session, model.id, user_id)
                            # The badge above was already rendered from data
                            # fetched before this click was handled (same
                            # loop iteration) - rerun so it reflects the new
                            # status instead of showing stale "draft".
                            st.rerun()
