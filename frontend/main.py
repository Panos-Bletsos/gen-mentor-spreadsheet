"""App shell for the GenMentor Streamlit frontend.

This module re-executes on every user interaction (Streamlit's execution model),
so anything placed here runs passively on each render — page registration,
autosave, mastery tracking, and the floating chatbot all live here for that reason.

Execution order matters: initialize_session_state() and the initial autosave run
before set_page_config() so that state is warm before any UI command is issued.
set_page_config() must itself be the first true Streamlit UI command in the script.
"""
import streamlit as st
import time
from utils.state import initialize_session_state, change_selected_goal_id, save_persistent_state, load_persistent_state, _get_data_store_path

# Must run before any st.* UI call so all keys exist when pages render.
initialize_session_state()

# Persist state eagerly on load; failures are silent to avoid blocking the UI.
st.session_state.setdefault("_autosave_enabled", True)
try:
    save_persistent_state()
except Exception:
    pass

from components.chatbot import render_chatbot

st.set_page_config(page_title="GenMentor", page_icon="🧠", layout="wide")
st.logo("./assets/avatar.png")
st.markdown('<style>' + open('./assets/css/main.css').read() + '</style>', unsafe_allow_html=True)

try:
    # One-shot redirect: send the user to Learning Path immediately after onboarding
    # completes. The _navigated_lp_once flag prevents an infinite redirect loop
    # because switch_page() triggers a full re-render of this script.
    if st.session_state.get("if_complete_onboarding", False) and not st.session_state.get("_navigated_lp_once", False):
        st.session_state["_navigated_lp_once"] = True
        try:
            st.switch_page("pages/learning_path.py")
        except Exception:
            pass
except Exception:
    pass

@st.dialog("Confirm Reset")
def show_reset_dialog():
    """Modal dialog for resetting all learner data.

    On confirm: backs up data_store.json with a timestamp suffix, deletes the
    original, disables autosave to prevent a concurrent write racing the delete,
    clears all session state, then navigates to onboarding.
    On cancel: reruns to close the dialog without changes.
    """
    st.warning("All history will be cleared. Do you want to reset?")
    st.divider()
    col_confirm, _space, col_cancel = st.columns([1, 2, 0.7])
    with col_confirm:
        if st.button("Confirm", type="primary"):
            from pathlib import Path
            from datetime import datetime
            import shutil
            try:
                st.session_state["_autosave_enabled"] = False
            except Exception:
                pass
            try:
                data_path = _get_data_store_path()
            except Exception:
                data_path = Path(__file__).resolve().parent / "user_data" / "data_store.json"
            try:
                data_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            if data_path.exists():
                try:
                    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                    backup_path = data_path.parent / f"data_storage-{ts}.json"
                    shutil.copy2(str(data_path), str(backup_path))
                except Exception:
                    pass
                try:
                    data_path.unlink()
                except Exception:
                    pass
            try:
                st.session_state.clear()
            except Exception:
                pass
            try:
                # After clearing state, navigate to onboarding page explicitly
                try:
                    st.switch_page("pages/onboarding.py")
                except Exception:
                    st.rerun()
            except Exception:
                try:
                    st.rerun()
                except Exception:
                    pass
    with col_cancel:
        if st.button("Cancel"):
            # simply rerun to close the dialog without changes
            try:
                st.rerun()
            except Exception:
                try:
                    st.rerun()
                except Exception:
                    pass

if st.session_state["show_chatbot"]:
    render_chatbot()

# Page objects must be created before st.navigation(); the default=True page is
# the one Streamlit lands on at the root URL, so it flips between onboarding and
# learning_path depending on whether the user has completed onboarding.
if st.session_state["if_complete_onboarding"]:
    onboarding = st.Page("pages/onboarding.py", title="Onboarding", icon=":material/how_to_reg:", default=False, url_path="onboarding")
    learning_path = st.Page("pages/learning_path.py", title="Learning Path", icon=":material/route:", default=True, url_path="learning_path")
else:
    onboarding = st.Page("pages/onboarding.py", title="Onboarding", icon=":material/how_to_reg:", default=True, url_path="onboarding")
    learning_path = st.Page("pages/learning_path.py", title="Learning Path", icon=":material/route:", default=False, url_path="learning_path")
skill_gaps = st.Page("pages/skill_gap.py", title="Skill Gap", icon=":material/insights:", default=False, url_path="skill_gap")
knowledge_document = st.Page("pages/knowledge_document.py", title="Resume Learning", icon=":material/menu_book:", default=False, url_path="knowledge_document")
learner_profile = st.Page("pages/learner_profile.py", title="My Profile", icon=":material/person:", default=False, url_path="learner_profile")
goal_management = st.Page("pages/goal_management.py", title="Goal Management", icon=":material/flag:", default=False, url_path="goal_management")
dashboard = st.Page("pages/dashboard.py", title="Analytics Dashboard", icon=":material/browse:", default=False, url_path="dashboard")
sheets = st.Page("pages/sheets.py", title="Sheets", icon=":material/grid_on:", default=False, url_path="sheets")
exercise = st.Page("pages/exercise.py", title="Exercise", icon=":material/edit_note:", default=False, url_path="exercise")

# Learning Analytics Dashboard
if not st.session_state["if_complete_onboarding"]:
    nav_position = "sidebar"
    pg = st.navigation({"GenMentor": [onboarding, skill_gaps, learning_path]}, position="hidden", expanded=True)
else:
    nav_position = "sidebar"
    pg = st.navigation({"GenMentor": [goal_management, learning_path, knowledge_document, exercise, learner_profile, dashboard, sheets]}, position=nav_position, expanded=True)
    with st.sidebar:
        _left, _center, _right = st.columns([2, 2, 2])
        with _center:
            if st.button("Reset", help="Clear local history (keeps timestamped backups)"):
                show_reset_dialog()
    goal = st.session_state["goals"][st.session_state["selected_goal_id"]]
    goal['start_time'] = time.time()
    try:
        save_persistent_state()
    except Exception:
        pass
    unlearned_skill = len(goal['learner_profile']['cognitive_status']['in_progress_skills'])
    learned_skill = len(goal['learner_profile']['cognitive_status']['mastered_skills'])
    all_skill = learned_skill + unlearned_skill

    if goal['id'] not in st.session_state['learned_skills_history']:
        st.session_state['learned_skills_history'][goal['id']] = []
        try:
            save_persistent_state()
        except Exception:
            pass

    # Mastery rate is sampled at most once every 10 minutes (600 s) and kept as
    # a rolling window of the last 10 readings — used by the analytics dashboard
    # to draw a progress-over-time chart without storing a full timestamped log.
    mastery_rate = learned_skill / all_skill if all_skill != 0 else 0
    if all_skill != 0:
        if st.session_state['learned_skills_history'][goal['id']] == []:
            st.session_state['learned_skills_history'][goal['id']].append(mastery_rate)
            try:
                save_persistent_state()
            except Exception:
                pass
    if(time.time()-goal['start_time']>600):
        goal['start_time'] = time.time()
        try:
            save_persistent_state()
        except Exception:
            pass
        st.session_state['learned_skills_history'][goal['id']].append(mastery_rate)
        try:
            save_persistent_state()
        except Exception:
            pass

    if len(st.session_state['learned_skills_history'][goal['id']]) > 10:
        st.session_state['learned_skills_history'][goal['id']].pop(0)
        try:
            save_persistent_state()
        except Exception:
            pass

    try:
        save_persistent_state()
    except Exception:
        pass

try:
    if st.session_state.get("_autosave_enabled", True):
        save_persistent_state()
except Exception:
    pass

if len(st.session_state["goals"]) != 0:
    change_selected_goal_id(st.session_state["selected_goal_id"])
    try:
        save_persistent_state()
    except Exception:
        pass

pg.run()

