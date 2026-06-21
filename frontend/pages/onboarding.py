"""
Onboarding page — two-card wizard that collects goal and learner info before routing to Skill Gap.

Flow:
    Card 0 (Goal):
        - User enters a free-text learning goal.
        - Optional: click "Refine" to get AI suggestions via render_goal_refinement().
        - "Next" advances to card 1.

    Card 1 (Information):
        - User picks occupation (preset list or free-text "Other").
        - Optional: upload a PDF resume or type learning preferences.
        - learner_information = occupation + text + pdf (concatenated).
        - "Previous" returns to card 0.
        - "Save & Continue" validates goal + occupation, then switches to pages/skill_gap.py.

State keys written: onboarding_card_index, to_add_goal, refined_learning_goal,
                    learner_occupation, learner_information_text, learner_information.
All mutations are persisted to user_data/data_store.json via save_persistent_state().
"""
import streamlit as st

import time
import asyncio
from components.goal_refinement import render_goal_refinement
from utils.pdf import extract_text_from_pdf
from utils.state import save_persistent_state
from components.topbar import render_topbar


def on_refine_click():
    """Set the refining flag so the goal text area becomes read-only while AI suggestions load.

    Called by the "Refine" button in render_goal_refinement(). Setting the flag to True
    disables the text_area on the next rerun, preventing edits while the AI processes
    the goal. The flag is cleared by render_goal_refinement() once suggestions are ready.
    """
    st.session_state["if_refining_learning_goal"] = True
    try:
        save_persistent_state()
    except Exception:
        pass


def _init_onboarding_state():
    """Ensure required session_state keys exist to avoid KeyErrors on first render.

    Uses setdefault so existing values (e.g. restored from data_store.json) are never
    overwritten. The to_add_goal dict is the in-progress goal object that will be passed
    downstream to skill gap analysis and the learning path; it is mutated in place by
    render_goal() and later enriched by backend modules.

    Keys initialized:
        onboarding_card_index (int): Which wizard card is shown (0 = Goal, 1 = Information).
        if_refining_learning_goal (bool): Locks the goal text area during AI refinement.
        learner_occupation (str): Selected or typed occupation string.
        learner_information_text (str): Free-text learning preferences entered by the user.
        learner_information (str): Concatenated string of occupation + text + pdf content.
        to_add_goal (dict): Skeleton goal object with keys: learning_goal, skill_gaps,
                            learner_profile, learning_path, is_completed, is_deleted.
    """
    st.session_state.setdefault("onboarding_card_index", 0)  # 0: goal, 1: info
    st.session_state.setdefault("if_refining_learning_goal", False)
    st.session_state.setdefault("learner_occupation", "")
    st.session_state.setdefault("learner_information_text", "")
    st.session_state.setdefault("learner_information", "")
    st.session_state.setdefault("to_add_goal", {
        "learning_goal": "",
        "skill_gaps": [],
        "learner_profile": {},
        "learning_path": [],
        "is_completed": False,
        "is_deleted": False
    })
    try:
        save_persistent_state()
    except Exception:
        pass


def _inject_card_css():
    """Inject lightweight CSS to style containers as cards and navigation buttons.

    Defines two CSS classes:
        .gm-card: white rounded card with subtle border and shadow, used for each wizard step.
        .gm-side / .gm-side-btn: sticky sidebar button style (currently unused in the wizard
                                  but available for future side-navigation).
    """
    st.markdown(
        """
        <style>
        .gm-card { 
            background: #ffffff; 
            border: 1px solid rgba(0,0,0,0.08);
            border-radius: 14px; 
            box-shadow: 0 8px 24px rgba(0,0,0,0.06);
            padding: 24px 22px; 
        }
        .gm-side { position: sticky; top: 160px; }
        .gm-side .gm-side-btn {
            border: 1px solid rgba(0,0,0,0.12);
            background: #ffffff;
            color: #111827;
            padding: 6px 10px; 
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_onboard():
    """Entry point for the onboarding page — initializes state, injects styles, and renders the card flow.

    Layout: a 1-5-1 column split centres all content in the middle column so the wizard
    feels narrow and focused rather than full-width.

    refined_learning_goal is lazily seeded from to_add_goal["learning_goal"] on the first
    render only; after that render_goal_refinement() owns it. This avoids overwriting an
    AI-refined goal if the user navigates away and returns.
    """
    _init_onboarding_state()
    _inject_card_css()
    left, center, right = st.columns([1, 5, 1])
    goal = st.session_state["to_add_goal"]
    if "refined_learning_goal" not in st.session_state:
        st.session_state["refined_learning_goal"] = goal["learning_goal"]
        try:
            save_persistent_state()
        except Exception:
            pass
    with center:
        render_topbar()
        st.title("Onboarding GenMentor")
        st.write("Start Your Goal-oriented and Personalized Learning Journey!")
        render_cards_with_nav(goal)
        

def render_goal(goal):
    """Render the first onboarding card: free-text goal entry with optional AI refinement and a Next button.

    Args:
        goal (dict): Reference to st.session_state["to_add_goal"]. Mutations to
                     goal["learning_goal"] inside this function update session_state
                     directly because dicts are passed by reference in Python.

    The text_area is disabled while if_refining_learning_goal is True (set by
    on_refine_click()) to prevent edits during the async AI call. The "Next" button
    is disabled when already on card 1 (idx == 1) to avoid re-triggering the transition.
    """
    idx = st.session_state.get("onboarding_card_index", 0)
    with st.container(border=True):
        st.subheader("Set Learning Goal")
        st.info("🚀 Please enter your role and specific learning goal. You can also refine it with AI suggestions.")
        learning_goal = st.text_area("* Enter your learning goal", value=goal["learning_goal"], label_visibility="visible", disabled=st.session_state["if_refining_learning_goal"])
        goal["learning_goal"] = learning_goal
        button_col, hint_col, next_col = st.columns([3, 10, 3])
        render_goal_refinement(goal, button_col, hint_col)
        save_persistent_state()
        with hint_col:
            if st.session_state["if_refining_learning_goal"]:
                st.write("**✨ Refining learning goal...**")
        with next_col:
            if st.button("Next", key="gm_nav_next", use_container_width=True, disabled=(idx == 1), type="primary"):
                st.session_state["onboarding_card_index"] = min(1, idx + 1)
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()
        



def render_information(goal):
    """Render the second onboarding card: occupation picker, optional free-text and PDF upload for learner context.

    Args:
        goal (dict): Reference to st.session_state["to_add_goal"] (not mutated here,
                     passed through to render_continue_button for validation).

    Occupation resolution logic:
        occupations.index() raises ValueError if the stored learner_occupation is not in
        the preset list (e.g. a custom "Other" value from a previous session). The except
        branch maps this to index=None, which renders the selectbox with no selection.
        Three cases are then handled:
            - "Other" selected: show a free-text input; only persist if non-empty.
            - None (no selection): clear learner_occupation to "".
            - Preset value: persist the selected string directly.

    learner_information is rebuilt on every render as:
        learner_occupation + learner_information_text + learner_information_pdf
    This is a plain string concatenation; the backend receives it as unstructured context
    for personalisation. The PDF text is local to this render call — it is not stored
    separately in session_state, only merged into learner_information.
    """
    idx = st.session_state.get("onboarding_card_index", 0)
    with st.container(border=True):
        st.subheader("Share Your Information")
        st.info("🧠 Please provide your information (Text or PDF) to enhance personalized experience")

        occupations = ["Software Engineer", "Data Scientist", "AI Researcher", "Product Manager", "UI/UX Designer", "Other"]
        try:
            occupation_selectbox_index = occupations.index(st.session_state["learner_occupation"]) 
        except ValueError:
            occupation_selectbox_index = None
        ocp_left, ocp_right = st.columns([1, 1])
        with ocp_left:
            selected_occupation = st.selectbox("Select your occupation", occupations, index=occupation_selectbox_index)
        if selected_occupation == "Other":
            with ocp_right:
                other_occupation = st.text_input("Please specify your occupation")
            if other_occupation:
                st.session_state["learner_occupation"] = other_occupation
                try:
                    save_persistent_state()
                except Exception:
                    pass
        if selected_occupation is None:
            st.session_state["learner_occupation"] = ""
            try:
                save_persistent_state()
            except Exception:
                pass
        else:
            st.session_state["learner_occupation"] = selected_occupation
            try:
                save_persistent_state()
            except Exception:
                pass
        upload_col, information_col = st.columns([1, 1])
        with upload_col:
            uploaded_file = st.file_uploader("[Optional] Upload a PDF with your information (e.g., resume)", type="pdf")
            if uploaded_file is not None:
                with st.spinner("Extracting text from PDF..."):
                    learner_information_pdf = extract_text_from_pdf(uploaded_file)
                    st.toast("✅ PDF uploaded successfully.")
            else:
                learner_information_pdf = ""
        with information_col:
            learner_information_text = st.text_area("[Optional] Enter your learning perferences and style", value=st.session_state["learner_information_text"], label_visibility="visible", height=77)
            st.session_state["learner_information"] = st.session_state["learner_occupation"] + learner_information_text + learner_information_pdf
            try:
                save_persistent_state()
            except Exception:
                pass
        # st.divider()
        arrow_left, space_col, continue_button_col = st.columns([3, 10, 3])
        save_persistent_state()
        with arrow_left:
            if st.button("Previous", key="gm_nav_prev", use_container_width=True, disabled=(idx == 0)):
                st.session_state["onboarding_card_index"] = max(0, idx - 1)
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()
        with continue_button_col:
            render_continue_button(goal)

def render_continue_button(goal):
    """Validate that goal and occupation are set, then navigate to the Skill Gap page.

    Args:
        goal (dict): Reference to st.session_state["to_add_goal"]; reads learning_goal
                     for validation but does not mutate it.

    Validation: both goal["learning_goal"] and learner_occupation must be non-empty strings.
    On success, sets selected_page = "Skill Gap" before switching so the sidebar nav
    highlights the correct page after the redirect.
    """
    if st.button("Save & Continue", type="primary"):
        if not goal["learning_goal"] or not st.session_state["learner_occupation"]:
            st.warning("Please provide both a learning goal and your occupation before continuing.")
        else:
            st.session_state["selected_page"] = "Skill Gap"
            try:
                save_persistent_state()
            except Exception:
                pass
            st.switch_page("pages/skill_gap.py")


def render_cards_with_nav(goal):
    """Route to the correct wizard card based on onboarding_card_index.

    Args:
        goal (dict): Reference to st.session_state["to_add_goal"], forwarded to
                     whichever card is currently active.

    Acts as a simple router: index 0 → render_goal(), index 1 → render_information().
    Navigation buttons (Next / Previous) live inside each card and update the index
    before calling st.rerun(), so the next render lands here with the updated index.
    """
    idx = st.session_state.get("onboarding_card_index", 0)

    if idx == 0:
        render_goal(goal)
    else:
        render_information(goal)

render_onboard()