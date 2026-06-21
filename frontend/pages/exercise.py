import json
import streamlit as st
import streamlit.components.v1 as components
from assets.js.univer_sheets import get_univer_sheets_html
from streamlit_js_eval import streamlit_js_eval
from utils.sheet_data_parser import build_univer_multi_sheet_workbook, extract_cell_values
from utils.request_api import start_exercise, chat_with_tutor_exercise, update_learner_profile
from utils.state import initialize_session_state, save_persistent_state

initialize_session_state()

st.markdown(
    "<style>" + open("./assets/css/main.css").read() + "</style>",
    unsafe_allow_html=True,
)


def _find_tool_call(tool_calls, tool_name):
    """Find a tool call by name in the tool_calls list. Returns args dict or None."""
    for tc in (tool_calls or []):
        if tc.get("name") == tool_name:
            return tc.get("args", {})
    return None


def _capture_sheet_snapshot(nonce):
    """Reach into the Univer iframe and grab the current workbook snapshot.

    The nonce determines the streamlit_js_eval component key — a new nonce forces the
    browser to re-run the JS and return a fresh value. The return value on the *same*
    render where the nonce first appears is always None (one-render lag); the actual
    snapshot arrives on the next render.

    Returns:
        (snapshot_dict, is_live) where is_live=True means the value came from the
        iframe and reflects the student's current edits. is_live=False means we fell
        back to the session-state initial data.
    """
    js_code = """
    (function() {
        var iframes = window.parent.document.querySelectorAll('iframe');
        for (var i = 0; i < iframes.length; i++) {
            try {
                var win = iframes[i].contentWindow;
                if (win && typeof win.getWorkbookSnapshot === 'function') {
                    var snapshot = win.getWorkbookSnapshot();
                    if (snapshot) return JSON.stringify(snapshot);
                }
            } catch(e) {}
        }
        return null;
    })()
    """
    try:
        raw = streamlit_js_eval(
            js_expressions=js_code,
            key=f"sheet_snapshot_{nonce}",
        )
        if raw and isinstance(raw, str):
            snapshot = json.loads(raw)
            cell_values = extract_cell_values(snapshot)
            if cell_values:
                return {"cell_values": cell_values, "raw_snapshot": snapshot}, True
    except Exception:
        pass

    # Fallback: reconstruct from session state spreadsheet data (reflects initial state
    # only — no student edits — but is better than nothing if the iframe is unavailable)
    result = st.session_state.get("exercise_plan", {})
    spreadsheet_data = result.get("spreadsheet_data", {})
    sheets = spreadsheet_data.get("sheets", [])
    if sheets:
        fallback = {}
        for sheet in sheets:
            name = sheet.get("name", "Sheet1")
            headers = sheet.get("headers", [])
            rows = sheet.get("rows", [])
            fallback[name] = [headers] + rows
        return {"cell_values": fallback, "source": "session_state"}, False
    return {}, False


def _mark_lesson_learned():
    """Mark the originating learning-path session as completed, if applicable.

    Only runs when the exercise was launched from a specific learning-path lesson
    (exercise_origin_session_id is set). Brainstorming-started exercises skip this.
    """
    origin_session_id = st.session_state.get("exercise_origin_session_id")
    if origin_session_id is None:
        return
    goals = st.session_state.get("goals", [])
    selected_goal_id = st.session_state.get("selected_goal_id", 0)
    if not goals or selected_goal_id >= len(goals):
        return
    learning_path = goals[selected_goal_id].get("learning_path", [])
    for session in learning_path:
        if session.get("id") == origin_session_id:
            session["if_learned"] = True
            break
    try:
        save_persistent_state()
    except Exception:
        pass


def _execute_pending_action(pending, plan, result):
    """Run the queued tutor action using the freshest available sheet snapshot.

    Called once a fresh snapshot has arrived (or after the fallback timeout).
    The caller wraps this in a spinner and calls st.rerun() afterward.
    """
    action_type = pending.get("type")
    fresh_snapshot = st.session_state.get("_last_sheet_snapshot", {})
    exercise_context = {"plan": plan, "sheet_snapshot": fresh_snapshot}
    learner_profile = st.session_state.get("learner_profile", "")

    exercise_id = st.session_state.get("exercise_id")

    if action_type == "chat":
        reply = chat_with_tutor_exercise(
            st.session_state["exercise_messages"],
            learner_profile,
            mode="exercise",
            exercise_context=exercise_context,
            exercise_id=exercise_id,
        )
        if reply:
            display_text = reply.get("response", "")
            sheet_update = _find_tool_call(reply.get("tool_calls", []), "SheetUpdate")
            st.session_state["exercise_messages"].append({"role": "assistant", "content": display_text})
            if sheet_update:
                st.session_state["exercise_plan"]["spreadsheet_data"] = sheet_update
                st.session_state["_sheet_data_version"] = (
                    st.session_state.get("_sheet_data_version", 0) + 1
                )
        else:
            st.session_state["exercise_messages"].append({
                "role": "assistant",
                "content": "I'm having trouble connecting. Please try again.",
            })

    elif action_type == "finish":
        # Build a transient instruction message — sent to the backend but never
        # persisted into exercise_messages (so no "[SYSTEM]" bubble in the chat).
        finish_instruction = {
            "role": "user",
            "content": (
                "[SYSTEM] The student has finished the exercise. "
                "Please summarize their performance: what they did well, "
                "what they struggled with, and what to practice next."
            ),
        }
        transient_msgs = st.session_state["exercise_messages"] + [finish_instruction]

        reply = chat_with_tutor_exercise(
            transient_msgs,
            learner_profile,
            mode="exercise",
            exercise_context=exercise_context,
            exercise_id=exercise_id,
            lifecycle="exercise_completed",
        )
        if reply:
            feedback = reply.get("response", "")
            if feedback:
                st.session_state["exercise_messages"].append(
                    {"role": "assistant", "content": feedback}
                )

        # Mark the originating lesson as learned (no-op for brainstorming exercises)
        _mark_lesson_learned()

        # Update learner profile — pass the conversation directly; no brittle
        # "extract JSON from LLM" round-trip.
        try:
            session_info = {
                "type": "exercise",
                "topic": str(st.session_state.get("exercise_topic", "")),
                "scenario": plan.get("scenario", ""),
            }
            update_learner_profile(
                learner_profile,
                str(st.session_state.get("exercise_messages", [])),
                session_information=str(session_info),
            )
        except Exception:
            pass


def _reset_exercise():
    st.session_state["exercise_phase"] = None
    st.session_state["exercise_topic"] = None
    st.session_state["exercise_messages"] = []
    st.session_state["exercise_plan"] = None
    st.session_state["exercise_id"] = None
    st.session_state["_snapshot_nonce"] = 0
    st.session_state["_last_snapshot_nonce"] = -1
    st.session_state["_last_sheet_snapshot"] = {}
    st.session_state["_pending_tutor_action"] = None
    st.session_state["_snapshot_wait_count"] = 0


def get_exercise_phase():
    phase = st.session_state.get("exercise_phase")
    if phase:
        return phase
    params = st.query_params
    topic = params.get("topic")
    if topic:
        st.session_state["exercise_topic"] = topic
        return "loading"
    return "brainstorming"


def render_toolbar():
    if st.button("Start New Exercise", key="start_new_exercise"):
        _reset_exercise()
        st.rerun()


# ---------------------------------------------------------------------------
# Phase: Brainstorming
# ---------------------------------------------------------------------------

def render_brainstorming():
    left_col, right_col = st.columns([1.5, 1], gap="large")

    with left_col:
        st.header("Practice Mode")
        st.info("Chat with the AI tutor to decide what you'd like to practice. The spreadsheet will load once we've picked an exercise.")

    with right_col:
        st.subheader("AI Tutor")

        if not st.session_state["exercise_messages"]:
            st.session_state["exercise_messages"].append({
                "role": "assistant",
                "content": "Hi! What would you like to practice today? You can tell me a specific skill or your a goal you'd like to achieve.",
            })

        chat_container = st.container()
        with chat_container:
            for msg in st.session_state["exercise_messages"]:
                st.chat_message(msg["role"]).write(msg["content"])

        st.empty()
        if prompt := st.chat_input("Tell me what you want to practice..."):
            st.session_state["exercise_messages"].append({"role": "user", "content": prompt})

            with st.spinner("Thinking..."):
                reply = chat_with_tutor_exercise(
                    st.session_state["exercise_messages"],
                    st.session_state.get("learner_profile", ""),
                    mode="brainstorming",
                )

            if reply:
                display_text = reply.get("response", "")
                exercise_topic = _find_tool_call(reply.get("tool_calls", []), "BrainstormingDone")
                st.session_state["exercise_messages"].append({"role": "assistant", "content": display_text})

                if exercise_topic:
                    st.session_state["exercise_topic"] = exercise_topic
                    st.session_state["exercise_phase"] = "loading"
                    st.rerun()
            else:
                st.session_state["exercise_messages"].append({
                    "role": "assistant",
                    "content": "I'm having trouble connecting right now. Could you try again?",
                })

            st.rerun()

        student_msg_count = sum(1 for m in st.session_state["exercise_messages"] if m["role"] == "user")
        if student_msg_count >= 6:
            if st.button("Ready to start the exercise"):
                st.session_state["exercise_messages"].append({
                    "role": "user",
                    "content": "Let's start the exercise based on what we discussed.",
                })
                with st.spinner("Finalizing exercise topic..."):
                    reply = chat_with_tutor_exercise(
                        st.session_state["exercise_messages"],
                        st.session_state.get("learner_profile", ""),
                        mode="brainstorming",
                    )
                if reply:
                    display_text = reply.get("response", "")
                    exercise_topic = _find_tool_call(reply.get("tool_calls", []), "BrainstormingDone")
                    st.session_state["exercise_messages"].append({"role": "assistant", "content": display_text})
                    if exercise_topic:
                        st.session_state["exercise_topic"] = exercise_topic
                        st.session_state["exercise_phase"] = "loading"
                        st.rerun()
                st.rerun()


# ---------------------------------------------------------------------------
# Phase: Loading
# ---------------------------------------------------------------------------

def render_loading():
    st.header("Generating your exercise...")
    with st.spinner("The AI is creating a personalized exercise for you. This may take 20-40 seconds..."):
        topic = st.session_state.get("exercise_topic") or "general spreadsheet practice"
        result = start_exercise(
            topic=topic,
            learner_profile=st.session_state.get("learner_profile", ""),
            brainstorming_history=st.session_state.get("exercise_messages", []),
            extra_context=st.session_state.get("exercise_extra_context", ""),
            skill_gaps=st.session_state.get("exercise_skill_gaps", []),
        )

    if result and "exercise_plan" in result:
        st.session_state["exercise_plan"] = result
        st.session_state["exercise_id"] = result.get("exercise_id")
        st.session_state["_sheet_data_version"] = 0
        st.session_state["exercise_messages"].append({
            "role": "assistant",
            "content": result["tutor_message"],
        })
        st.session_state["exercise_phase"] = "exercising"
        st.rerun()
    else:
        st.error("Could not generate exercise. Please try again.")
        if st.button("Go back to brainstorming"):
            st.session_state["exercise_phase"] = "brainstorming"
            st.rerun()


# ---------------------------------------------------------------------------
# Phase: Exercising
# ---------------------------------------------------------------------------

def render_exercising():
    result = st.session_state.get("exercise_plan", {})
    plan = result.get("exercise_plan", {})
    spreadsheet_data = result.get("spreadsheet_data", {})

    # --- Snapshot capture ---
    # Must be called on EVERY render so the streamlit_js_eval component stays mounted.
    # When the nonce is new, the browser re-runs the JS; the value arrives one render
    # later. Until then (is_live=False) we keep the last known good snapshot.
    nonce = st.session_state.get("_snapshot_nonce", 0)
    snapshot, is_live = _capture_sheet_snapshot(nonce)

    if is_live:
        # Fresh live value from the iframe — store it and mark the nonce as satisfied.
        st.session_state["_last_sheet_snapshot"] = snapshot
        st.session_state["_last_snapshot_nonce"] = nonce
        st.session_state["_snapshot_wait_count"] = 0
    elif snapshot and not st.session_state.get("_last_sheet_snapshot"):
        # Fallback only used when we have no prior snapshot at all.
        st.session_state["_last_sheet_snapshot"] = snapshot

    # --- Layout ---
    left_col, right_col = st.columns([1.5, 1], gap="large")

    with left_col:
        title = plan.get("scenario", "Exercise")[:80]
        st.header(title)

        sheets = spreadsheet_data.get("sheets", [])
        if sheets:
            workbook = build_univer_multi_sheet_workbook(sheets, workbook_name="Exercise")
            workbook_json = json.dumps(workbook)
            univer_html = get_univer_sheets_html(height="100%", workbook_data=workbook_json)
            # Add a nonce to force iframe reload when sheet_data_version changes
            sheet_version = st.session_state.get("_sheet_data_version", 0)
            univer_html += f"<!-- sheet_v{sheet_version} -->"
            components.html(univer_html, height=600, scrolling=False)
        else:
            st.warning("No spreadsheet data available.")

    with right_col:
        st.subheader("AI Tutor")

        chat_container = st.container(height=500)
        with chat_container:
            for msg in st.session_state["exercise_messages"]:
                st.chat_message(msg["role"]).write(msg["content"])

        pending = st.session_state.get("_pending_tutor_action")

        if pending is not None:
            # A user action is queued. Check whether a fresh snapshot for the current
            # nonce has arrived (is_live + nonce matches). If so, run the action now.
            # If not, wait — streamlit_js_eval will trigger another rerun when the
            # browser responds. After 3 waits with no live value, fall back to the last
            # known snapshot to avoid an infinite wait if the iframe is unavailable.
            fresh_nonce_ready = (
                st.session_state.get("_last_snapshot_nonce") == nonce and is_live
            )
            wait_count = st.session_state.get("_snapshot_wait_count", 0)

            if fresh_nonce_ready or wait_count >= 3:
                with st.spinner("Thinking..."):
                    _execute_pending_action(pending, plan, result)
                st.session_state["_pending_tutor_action"] = None
                st.session_state["_snapshot_wait_count"] = 0
                st.rerun()
            else:
                st.session_state["_snapshot_wait_count"] = wait_count + 1
                st.info("Capturing spreadsheet state...")
        else:
            if prompt := st.chat_input("Ask about this exercise..."):
                st.session_state["exercise_messages"].append({"role": "user", "content": prompt})
                # Queue the action and bump the nonce so a fresh snapshot is captured
                # before the tutor call goes out.
                st.session_state["_pending_tutor_action"] = {"type": "chat", "prompt": prompt}
                st.session_state["_snapshot_nonce"] = nonce + 1
                st.session_state["_snapshot_wait_count"] = 0
                st.rerun()

        # Finish exercise — stays live and idempotent so the student can re-finish
        # after further edits. Feedback appears as a normal assistant message.
        st.divider()
        if st.button("Finish Exercise", type="primary", disabled=(pending is not None)):
            st.session_state["_pending_tutor_action"] = {"type": "finish"}
            st.session_state["_snapshot_nonce"] = nonce + 1
            st.session_state["_snapshot_wait_count"] = 0
            st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def render_exercise():
    save_persistent_state()
    render_toolbar()
    phase = get_exercise_phase()
    if phase == "loading":
        render_loading()
    elif phase == "exercising":
        render_exercising()
    else:
        render_brainstorming()


render_exercise()
