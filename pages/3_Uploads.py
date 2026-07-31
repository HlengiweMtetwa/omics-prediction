import streamlit as st

import app_state
from ai_wasteguard import permissions, registry, uploads
from ai_wasteguard.db import get_session

st.set_page_config(page_title="Uploads — AI-WasteGuard", layout="centered")
st.title("Uploads")
st.caption("Supported formats: " + ", ".join(uploads.SUPPORTED_EXTENSIONS))

user_id = app_state.require_login()

with get_session() as session:
    projects = registry.list_projects_for_owner(session, user_id)
    project_options = {p.title: p.id for p in projects}

if not project_options:
    st.info("No projects yet. Create one on the **Projects** page first.")
    st.stop()

project_id = project_options[st.selectbox("Project", list(project_options.keys()))]

with get_session() as session:
    sites = registry.list_sites_for_project(session, project_id)
    site_options = {s.name: s.id for s in sites}

if not site_options:
    st.info("No sites yet for this project. Register one on the **Sites and Sampling** page.")
    st.stop()

site_id = site_options[st.selectbox("Site", list(site_options.keys()))]

with get_session() as session:
    events = registry.list_sampling_events_for_site(session, site_id)
    event_options = {f"{e.collected_at.isoformat()} ({e.sample_matrix or 'unspecified matrix'})": e.id for e in events}

if not event_options:
    st.info("No sampling events yet for this site.")
    st.stop()

event_id = event_options[st.selectbox("Sampling event", list(event_options.keys()))]

with get_session() as session:
    samples = registry.list_samples_for_event(session, event_id)
    sample_options = {f"Replicate {s.replicate} ({s.sample_type or 'unspecified type'})": s.id for s in samples}

if not sample_options:
    st.info("No samples yet for this sampling event.")
    st.stop()

sample_id = sample_options[st.selectbox("Sample", list(sample_options.keys()))]

st.subheader("Upload a file")
if app_state.current_user_role() not in permissions.CAN_UPLOAD:
    st.info("Your role does not permit uploading files. You can still view files below.")
else:
    omics_type = st.selectbox(
        "Omics / data type", ["", "genomic", "metagenomic", "transcriptomic", "proteomic", "metabolomic", "environmental metadata"]
    )
    uploaded_file = st.file_uploader("File")
    if uploaded_file is not None and st.button("Upload"):
        if app_state.check_permission(permissions.CAN_UPLOAD, "upload a file"):
            try:
                with get_session() as session:
                    record = uploads.save_upload(
                        session,
                        sample_id=sample_id,
                        uploader_id=user_id,
                        original_filename=uploaded_file.name,
                        file_obj=uploaded_file,
                        omics_type=omics_type or None,
                    )
                st.success(f"'{record.original_filename}' uploaded ({record.size_bytes} bytes).")
            except uploads.UploadValidationError as exc:
                st.error(str(exc))

st.subheader("Files for this sample")
with get_session() as session:
    files = uploads.list_uploads_for_sample(session, sample_id)
    if not files:
        st.info("No files uploaded yet for this sample.")
    for f in files:
        with st.container(border=True):
            st.markdown(f"**{f.original_filename}**")
            st.caption(
                f"Type: {f.file_type}"
                + (f" · Omics: {f.omics_type}" if f.omics_type else "")
                + f" · {f.size_bytes} bytes · SHA-256: {f.checksum_sha256[:12]}…"
            )
            st.caption(f"Status: {f.validation_status.value}")
