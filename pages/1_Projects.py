import streamlit as st

import app_state
from ai_wasteguard import registry
from ai_wasteguard.db import get_session

st.set_page_config(page_title="Projects — AI-WasteGuard", layout="centered")
st.title("Projects")

user_id = app_state.require_login()

with st.expander("Register a new project", expanded=False):
    with st.form("new_project_form"):
        title = st.text_input("Title")
        description = st.text_area("Description", height=100)
        disease_focus = st.text_input("Disease / AMR focus")
        amr_focus = st.checkbox("This project has an AMR surveillance focus")
        submitted = st.form_submit_button("Create project")
    if submitted:
        try:
            with get_session() as session:
                registry.create_project(
                    session,
                    owner_id=user_id,
                    title=title,
                    description=description,
                    disease_focus=disease_focus,
                    amr_focus=amr_focus,
                )
            st.success(f"Project '{title}' created.")
        except registry.ValidationError as exc:
            st.error(str(exc))

st.subheader("Your projects")
with get_session() as session:
    projects = registry.list_projects_for_owner(session, user_id)
    if not projects:
        st.info("No projects yet. Create one above.")
    for project in projects:
        with st.container(border=True):
            st.markdown(f"**{project.title}**  \n`{project.id}`")
            if project.description:
                st.write(project.description)
            meta = []
            if project.disease_focus:
                meta.append(f"Disease focus: {project.disease_focus}")
            if project.amr_focus:
                meta.append("AMR focus: yes")
            meta.append(f"Status: {project.status.value}")
            st.caption(" · ".join(meta))
