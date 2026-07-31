from datetime import datetime

import streamlit as st
from sqlalchemy.exc import IntegrityError

import app_state
from ai_wasteguard import registry
from ai_wasteguard.db import get_session

st.set_page_config(page_title="Sites & Sampling — AI-WasteGuard", layout="centered")
st.title("Sites & Sampling")

user_id = app_state.require_login()

with get_session() as session:
    projects = registry.list_projects_for_owner(session, user_id)
    project_options = {p.title: p.id for p in projects}

if not project_options:
    st.info("No projects yet. Create one on the **Projects** page first.")
    st.stop()

selected_project_title = st.selectbox("Project", list(project_options.keys()))
project_id = project_options[selected_project_title]

st.subheader("Sites")
with st.expander("Register a new site", expanded=False):
    with st.form("new_site_form"):
        name = st.text_input("Site name")
        country = st.text_input("Country")
        region = st.text_input("Region / province")
        site_type = st.selectbox("Site type", ["", "wastewater treatment plant", "pumping station", "manhole", "other"])
        col1, col2 = st.columns(2)
        latitude = col1.number_input("Latitude", value=0.0, format="%.6f")
        longitude = col2.number_input("Longitude", value=0.0, format="%.6f")
        submitted = st.form_submit_button("Create site")
    if submitted:
        try:
            with get_session() as session:
                registry.create_site(
                    session,
                    project_id=project_id,
                    name=name,
                    country=country or None,
                    region=region or None,
                    latitude=latitude or None,
                    longitude=longitude or None,
                    site_type=site_type or None,
                )
            st.success(f"Site '{name}' created.")
        except registry.ValidationError as exc:
            st.error(str(exc))

with get_session() as session:
    sites = registry.list_sites_for_project(session, project_id)
    site_options = {s.name: s.id for s in sites}

if not site_options:
    st.info("No sites yet for this project. Create one above.")
    st.stop()

selected_site_name = st.selectbox("Site", list(site_options.keys()))
site_id = site_options[selected_site_name]

st.subheader("Sampling events")
with st.expander("Register a new sampling event", expanded=False):
    with st.form("new_event_form"):
        collected_date = st.date_input("Collection date")
        collected_time = st.time_input("Collection time")
        sample_matrix = st.selectbox("Sample matrix", ["", "influent", "effluent", "sludge", "surface water"])
        collector = st.text_input("Collector")
        notes = st.text_area("Field notes", height=80)
        submitted_event = st.form_submit_button("Create sampling event")
    if submitted_event:
        try:
            collected_at = datetime.combine(collected_date, collected_time)
            with get_session() as session:
                registry.create_sampling_event(
                    session,
                    site_id=site_id,
                    collected_at=collected_at,
                    sample_matrix=sample_matrix or None,
                    collector=collector or None,
                    notes=notes or None,
                )
            st.success("Sampling event created.")
        except registry.ValidationError as exc:
            st.error(str(exc))

with get_session() as session:
    events = registry.list_sampling_events_for_site(session, site_id)
    event_options = {f"{e.collected_at.isoformat()} ({e.sample_matrix or 'unspecified matrix'})": e.id for e in events}

if not event_options:
    st.info("No sampling events yet for this site. Create one above.")
    st.stop()

selected_event_label = st.selectbox("Sampling event", list(event_options.keys()))
event_id = event_options[selected_event_label]

st.subheader("Samples")
with st.expander("Register a new sample", expanded=False):
    with st.form("new_sample_form"):
        sample_type = st.selectbox("Sample type", ["", "composite", "grab"])
        replicate = st.number_input("Replicate", min_value=1, step=1, value=1)
        lab_identifier = st.text_input("Laboratory identifier")
        submitted_sample = st.form_submit_button("Create sample")
    if submitted_sample:
        try:
            with get_session() as session:
                registry.create_sample(
                    session,
                    sampling_event_id=event_id,
                    sample_type=sample_type or None,
                    replicate=int(replicate),
                    lab_identifier=lab_identifier or None,
                )
            st.success("Sample created.")
        except IntegrityError:
            st.error(f"Replicate {int(replicate)} already exists for this sampling event.")

with get_session() as session:
    samples = registry.list_samples_for_event(session, event_id)
    if not samples:
        st.info("No samples yet for this sampling event. Create one above.")
    for sample in samples:
        with st.container(border=True):
            st.markdown(f"**Replicate {sample.replicate}** — {sample.sample_type or 'unspecified type'}")
            if sample.lab_identifier:
                st.caption(f"Lab ID: {sample.lab_identifier}")
            st.caption(f"Status: {sample.analysis_status.value}")
