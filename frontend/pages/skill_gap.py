"""
Skill Gap page — step 2 of the goal-setup flow.

User flow
---------
1. User arrives here after completing onboarding (a learning goal and learner
   information must already exist in session state).  If either is missing the
   page immediately redirects back to onboarding.

2. **Cold visit (no skill gaps yet):** ``render_identifying_skill_gap`` fires
   automatically on render — it calls the backend, shows a spinner, and on
   success writes the result back into ``goal["skill_gaps"]`` then re-runs the
   page.  No explicit "start" button is required.

3. **Warm visit (skill gaps present):** The page renders one card per skill via
   ``render_identified_skill_gap``.  The student can adjust required/current
   proficiency levels and toggle whether each skill counts as a gap.  A summary
   banner shows the total skill count and the number of identified gaps.

4. **"Schedule Learning Path":** Enabled as soon as skill gaps exist.  On click
   it lazily creates a learner profile (if one hasn't been created yet) and then
   commits the goal to persistent state before navigating to the Learning Path
   page.
"""
import time
import json
import httpx
import streamlit as st

from components.topbar import render_topbar
from config import backend_endpoint, use_mock_data
from components.gap_identification import render_identifying_skill_gap, render_identified_skill_gap
from utils.state import add_new_goal, reset_to_add_goal, save_persistent_state
from utils.request_api import identify_skill_gap, create_learner_profile


def render_skill_gap():
    """Render the Skill Gap review page for the goal currently being added.

    Reads ``st.session_state["to_add_goal"]`` (populated during onboarding) and
    drives the following states:

    * **Redirect:** if the goal has no learning goal text or the session has no
      learner information, the user is sent back to onboarding so no other state
      is assumed present.

    * **Identifying:** ``goal["skill_gaps"]`` is falsy — delegates to
      ``render_identifying_skill_gap`` which blocks with a spinner, calls the
      backend, and triggers a rerun once results are stored.

    * **Review:** ``goal["skill_gaps"]`` is populated — renders the card list
      and the "Schedule Learning Path" action button.

    The "Schedule Learning Path" button is intentionally disabled while skill
    gaps are empty so the student cannot proceed without analysis results.
    Learner-profile creation is deferred to this button's handler rather than
    happening at identification time, keeping each network call tied to an
    explicit user action.
    """
    goal = st.session_state["to_add_goal"]

    # Guard: both prerequisites must exist before any analysis can proceed.
    if not goal["learning_goal"] or not st.session_state["learner_information"]:
        st.switch_page("pages/onboarding.py")

    left, center, right = st.columns([1, 5, 1])
    with center:
        # render_topbar()
        st.title("Skill Gap")
        st.write("Review and confirm your skill gaps.")

        if not goal["skill_gaps"]:
            # No cached results — trigger analysis immediately on page load.
            render_identifying_skill_gap(goal)
        else:
            num_skills = len(goal["skill_gaps"])
            num_gaps = sum(1 for skill in goal["skill_gaps"] if skill["is_gap"])
            st.info(f"There are {num_skills} skills in total, with {num_gaps} skill gaps identified.")
            render_identified_skill_gap(goal)

            # The button is only enabled once skill gaps exist (truthy list).
            if_schedule_learning_path_ready = goal["skill_gaps"]
            space_col, continue_button_col = st.columns([1, 0.27])
            with continue_button_col:
                if st.button("Schedule Learning Path", type="primary", disabled=not if_schedule_learning_path_ready):
                    # Lazily create the learner profile on first continue press.
                    # It is created here rather than at identification time so
                    # the student can still adjust gap levels before committing.
                    if goal["skill_gaps"] and not goal["learner_profile"]:
                        with st.spinner('Creating your profile ...'):
                            learner_profile = create_learner_profile(
                                goal["learning_goal"],
                                st.session_state["learner_information"],
                                goal["skill_gaps"],
                            )
                            if learner_profile is None:
                                # Backend call failed — rerun to surface the
                                # error from the API layer rather than proceeding.
                                st.rerun()
                            goal["learner_profile"] = learner_profile
                            st.toast("🎉 Your profile has been created!")

                    # Commit the goal and navigate; add_new_goal returns the
                    # new goal's ID so the learning path page knows which goal
                    # to display.
                    new_goal_id = add_new_goal(**goal)
                    st.session_state["selected_goal_id"] = new_goal_id
                    st.session_state["if_complete_onboarding"] = True
                    st.session_state["selected_page"] = "Learning Path"
                    save_persistent_state()
                    st.switch_page("pages/learning_path.py")

render_skill_gap()
