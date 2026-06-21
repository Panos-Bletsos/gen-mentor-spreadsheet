"""
Learning Path page for the GenMentor frontend.

User flow
---------
1. Guard: redirect to onboarding if the user hasn't completed it, or if the
   selected goal has no skill gaps yet (skill_gap page must run first).
2. Auto-schedule: if the goal has no learning path yet, call the backend to
   generate one (default 8 sessions) and persist the result.
3. Display: once a path exists, show two sections:
   - Overall information (current goal text, completion progress bar, skill
     details expander).
   - Session grid (2-column card layout, one card per session).
4. Per-session actions:
   - "Learning" button (incomplete sessions):
       Treatment cohort  (config.interactive_exercises=True):
           → derive_knowledge_points → session_to_exercise_topic
           → exercise.py (interactive spreadsheet exercise)
       Control cohort:
           → knowledge_document.py (read-only content)
   - "Completed" button (completed sessions): always goes to
     knowledge_document.py for review.
   - Completion toggle (currently disabled / read-only).
5. Re-schedule expander: lets the user pick a new session count and trigger a
   backend re-schedule while showing a spinner.
"""

import time
import math
import streamlit as st
import config
from components.skill_info import render_skill_info
from utils.request_api import schedule_learning_path, reschedule_learning_path, derive_knowledge_points
from utils.exercise_routing import session_to_exercise_topic
from components.navigation import render_navigation
from utils.state import save_persistent_state

def render_learning_path():
    """
    Entry point for the Learning Path page.

    Guards against accessing the page out of order, then either auto-schedules
    a learning path if one doesn't exist yet, or delegates to the two sub-render
    functions that build the UI.
    """
    if not st.session_state.get("if_complete_onboarding"):
        st.switch_page("pages/onboarding.py")

    goal = st.session_state["goals"][st.session_state["selected_goal_id"]]
    save_persistent_state()
    if not goal["learning_goal"] or not st.session_state["learner_information"]:
        st.switch_page("pages/onboarding.py")
    else:
        if not goal["skill_gaps"]:
            st.switch_page("pages/skill_gap.py")

    st.title("Learning Path")
    st.write("Track your learning progress through the sessions below.")

    st.markdown("""
        <style>
        .card-header {
            color: #333;
            font-weight: bold;
            margin-bottom: 10px;
        }
        </style>
    """, unsafe_allow_html=True)
    if not goal["learning_path"]:
        with st.spinner('Scheduling Learning Path ...'):
            goal["learning_path"] = schedule_learning_path(goal["learner_profile"], session_count=8)
            save_persistent_state()
            if goal["learning_path"]:
                st.toast("🎉 Successfully scheduled learning path!")
                st.rerun()
            else:
                st.error("Failed to schedule learning path. Please try again.")
    else:
        render_overall_information(goal)
        render_learning_sessions(goal)


def render_overall_information(goal):
    """
    Render the top summary card: goal text, progress bar, and skill details.

    Args:
        goal: The currently selected goal dict from session state.  Expected
              keys: ``learning_goal``, ``learning_path`` (list of session
              dicts with an ``if_learned`` bool), ``learner_profile``.
    """
    with st.container(border=True):
        st.write("#### 🎯 Current Goal")
        st.text_area("In-progress Goal", value=goal["learning_goal"], disabled=True, help="Change this in the Goal Management section.")
        learned_sessions = sum(1 for s in goal["learning_path"] if s["if_learned"])
        total_sessions = len(goal["learning_path"])
        if total_sessions == 0:
            st.warning("No learning sessions found.")
            progress = 0
        else:
            progress = int((learned_sessions / total_sessions) * 100)
        st.write("#### 📊 Overall Progress")
        with st.container():
            st.progress(progress)
            st.write(f"{learned_sessions}/{total_sessions} sessions completed ({progress}%)")

            if learned_sessions == total_sessions:
                st.success("🎉 Congratulations! All sessions are complete.")
                st.balloons()
            else:
                st.info("🚀 Keep going! You’re making great progress.")
        with st.expander("View Skill Details", expanded=False):
            render_skill_info(goal["learner_profile"])

def render_learning_sessions(goal):
    """
    Render the interactive session grid and re-schedule controls.

    Builds a 2-column card grid where each card represents one learning session.
    Each card shows the session title, an expandable abstract, a completion
    toggle (read-only), and an action button.

    Action button behaviour depends on two dimensions:
    - Session completion state  (``session["if_learned"]``).
    - A/B cohort flag           (``config.interactive_exercises``).

    For incomplete sessions in the *treatment* cohort the button calls
    ``derive_knowledge_points`` on the backend, constructs the exercise topic
    via ``session_to_exercise_topic``, seeds exercise-related session-state
    keys, and navigates to ``exercise.py``.  Backend errors are stored in a
    per-session error key and surfaced inline on the next rerun rather than
    blocking the spinner.

    For the *control* cohort (or completed sessions) the button navigates to
    ``knowledge_document.py``.

    The re-schedule expander uses a two-rerun pattern to display a spinner:
    the first click sets ``if_rescheduling_learning_path=True`` and calls
    ``st.rerun()``, and on the following rerun the spinner is shown while the
    actual API call runs.

    Args:
        goal: The currently selected goal dict from session state.  Expected
              keys: ``learning_path`` (list of session dicts), ``learner_profile``.
    """
    st.write("#### 📖 Learning Sessions")
    total_sessions = len(goal["learning_path"])
    with st.expander("Re-schedule Learning Path", expanded=False):
        st.info("Customize your learning path by re-scheduling sessions or marking them as complete.")
        expected_session_count = st.number_input("Expected Sessions", min_value=0, max_value=10, value=total_sessions)
        st.session_state["expected_session_count"] = expected_session_count
        try:
            save_persistent_state()
        except Exception:
            pass
        if st.button("Re-schedule Learning Path", type="primary"):
            st.session_state["if_rescheduling_learning_path"] = True
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()
        if st.session_state.get("if_rescheduling_learning_path"):
            with st.spinner('Re-scheduling Learning Path ...'):
                goal["learning_path"] = reschedule_learning_path(goal["learning_path"], goal["learner_profile"], expected_session_count)
                st.session_state["if_rescheduling_learning_path"] = False
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.toast("🎉 Successfully re-schedule learning path!")
                st.rerun()
    save_persistent_state()
    # Build the full grid upfront so Streamlit registers all column contexts
    # before any card content is written.  Each element of columns_list is a
    # tuple of `columns_spec` st.delta_generator objects (one per column).
    columns_spec = 2
    num_columns = math.ceil(len(goal["learning_path"]) / columns_spec)
    columns_list = [st.columns(columns_spec, gap="large") for _ in range(num_columns)]
    for sid, session in enumerate(goal["learning_path"]):
        # Row index = sid // columns_spec; column index within that row = sid % columns_spec
        session_column = columns_list[sid // columns_spec]
        with session_column[sid % columns_spec]:
            with st.container(border=True):
                text_color = "#5ecc6b" if session["if_learned"] else "#fc7474"

                st.markdown(f"<div class='card'><div class='card-header' style='color: {text_color};'>{sid+1}: {session['title']}</div>", unsafe_allow_html=True)

                with st.expander("View Session Details", expanded=False):
                    st.info(session["abstract"])
                    st.write("**Associated Skills & Desired Proficiency:**")
                    for skill_outcome in session.get("desired_outcome_when_completed", []):
                        st.write(f"- {skill_outcome['name']} (`{skill_outcome['level']}`)")

                col1, col2 = st.columns([5, 3])
                with col1:
                    if_learned_key = f"if_learned_{session['id']}"
                    old_if_learned = session["if_learned"]
                    session_status_hint = "Keep Learning" if not session["if_learned"] else "Completed"
                    session_if_learned = st.toggle(session_status_hint, value=session["if_learned"], key=if_learned_key, disabled=True)
                    goal["learning_path"][sid]["if_learned"] = session_if_learned
                    save_persistent_state()
                    if session_if_learned != old_if_learned:
                        st.rerun()

                with col2:
                    if not session["if_learned"]:
                        start_key = f"start_{session['id']}_{session['if_learned']}"
                        if st.button("Learning", key=start_key, use_container_width=True, type="primary", icon=":material/local_library:"):
                            if config.interactive_exercises:
                                # Treatment cohort (A/B test): derive knowledge points from the
                                # backend and route to the interactive spreadsheet exercise page.
                                error_key = f"exercise_error_{session['id']}"
                                with st.spinner("Preparing exercise..."):
                                    kps = derive_knowledge_points(
                                        goal["learner_profile"],
                                        goal["learning_path"],
                                        session,
                                    )
                                if kps is None:
                                    st.session_state[error_key] = "Failed to contact the backend. Please try again."
                                    st.rerun()
                                else:
                                    topic_dict, extra_context_str = session_to_exercise_topic(
                                        session,
                                        goal["learner_profile"],
                                        kps,
                                    )
                                    st.session_state["exercise_topic"] = topic_dict
                                    st.session_state["exercise_phase"] = "loading"
                                    st.session_state["exercise_origin_session_id"] = session["id"]
                                    st.session_state["exercise_messages"] = []
                                    st.session_state["exercise_extra_context"] = extra_context_str
                                    st.session_state["exercise_skill_gaps"] = goal.get("skill_gaps", [])
                                    save_persistent_state()
                                    st.switch_page("pages/exercise.py")
                            else:
                                # Control cohort: navigate to read-only knowledge document.
                                st.session_state["selected_session_id"] = sid
                                st.session_state["selected_point_id"] = 0
                                st.session_state["selected_page"] = "Knowledge Document"
                                save_persistent_state()
                                st.switch_page("pages/knowledge_document.py")
                        # Show inline error for /derive-knowledge-points failures
                        error_key = f"exercise_error_{session['id']}"
                        if st.session_state.get(error_key):
                            st.error(st.session_state.pop(error_key))
                    else:
                        start_key = f"start_{session['id']}_{session['if_learned']}"
                        if st.button("Completed", key=start_key, use_container_width=True, type="secondary", icon=":material/done_outline:"):
                            st.session_state["selected_session_id"] = sid
                            st.session_state["selected_point_id"] = 0
                            st.session_state["selected_page"] = "Knowledge Document"
                            save_persistent_state()
                            st.switch_page("pages/knowledge_document.py")


render_learning_path()