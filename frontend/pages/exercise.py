import json
import time
import streamlit as st
import streamlit.components.v1 as components
from assets.js.univer_sheets import get_univer_sheets_html
from streamlit_js_eval import streamlit_js_eval
from utils.sheet_data_parser import build_univer_workbook_from_payload, extract_cell_values
from utils.request_api import start_exercise, chat_with_tutor_exercise, update_learner_profile
from utils.state import initialize_session_state

initialize_session_state()

st.markdown(
    "<style>" + open("./assets/css/main.css").read() + "</style>",
    unsafe_allow_html=True,
)


def parse_brainstorming_done(text):
    """Check if tutor response contains brainstorming_done JSON signal.
    Uses brace-counting to extract nested JSON with exercise_topic object.
    """
    marker = '"brainstorming_done"'
    idx = text.find(marker)
    if idx == -1:
        return text, None
    start = text.rfind("{", 0, idx)
    if start == -1:
        return text, None
    depth = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if depth != 0:
        return text, None
    try:
        signal = json.loads(text[start:end])
        if signal.get("brainstorming_done"):
            display_text = text[:start].strip()
            return display_text, signal.get("exercise_topic", {})
    except json.JSONDecodeError:
        pass
    return text, None


def _extract_json(text):
    """Extract a JSON object from LLM output, handling code fences and surrounding text."""
    import re
    # Strip markdown code fences
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Brace-counting: find first { and its matching }
    start = text.find("{")
    if start == -1:
        return {}
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return {}
    return {}


def _capture_sheet_snapshot():
    """Reach into the Univer iframe and grab the current workbook snapshot.

    Returns a dict suitable for passing as sheet_snapshot to the tutor,
    or {} if the snapshot cannot be captured.
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
            key=f"sheet_snapshot_m{len(st.session_state.get('exercise_messages', []))}",
        )
        if raw and isinstance(raw, str):
            snapshot = json.loads(raw)
            cell_values = extract_cell_values(snapshot)
            if cell_values:
                return {"cell_values": cell_values, "raw_snapshot": snapshot}
    except Exception:
        pass
    return {}


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
                "content": "Hi! What would you like to practice today? You can tell me a specific skill (like VLOOKUP or pivot tables) or a domain you're interested in (like sales analysis or financial modeling).",
            })

        chat_container = st.container(height=500)
        with chat_container:
            for msg in st.session_state["exercise_messages"]:
                st.chat_message(msg["role"]).write(msg["content"])

        if prompt := st.chat_input("Tell me what you want to practice..."):
            st.session_state["exercise_messages"].append({"role": "user", "content": prompt})

            with st.spinner("Thinking..."):
                reply = chat_with_tutor_exercise(
                    st.session_state["exercise_messages"],
                    st.session_state.get("learner_profile", ""),
                    mode="brainstorming",
                )

            if reply:
                display_text, exercise_topic = parse_brainstorming_done(reply)
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
                    display_text, exercise_topic = parse_brainstorming_done(reply)
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
        )

    if result and "exercise_plan" in result:
        st.session_state["exercise_plan"] = result
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

    left_col, right_col = st.columns([1.5, 1], gap="large")

    with left_col:
        title = plan.get("scenario", "Exercise")[:80]
        st.header(title)

        # Load first sheet into Univer (multi-sheet support is a follow-up)
        sheets = spreadsheet_data.get("sheets", [])
        if sheets:
            first_sheet = sheets[0]
            payload = {"headers": first_sheet.get("headers", []), "rows": first_sheet.get("rows", [])}
            workbook = build_univer_workbook_from_payload(
                payload,
                sheet_name=first_sheet.get("name", "Sheet1"),
                workbook_name="Exercise",
            )
            workbook_json = json.dumps(workbook)
            univer_html = get_univer_sheets_html(height="100%", workbook_data=workbook_json)
            nonce = str(time.time())
            univer_html += f"<!-- nonce:{nonce} -->"
            components.html(univer_html, height=600, scrolling=False)
        else:
            st.warning("No spreadsheet data available.")

    # Capture the sheet snapshot on every render (outside chat input block)
    # so streamlit_js_eval doesn't trigger a rerun inside the conditional.
    sheet_snapshot = _capture_sheet_snapshot()
    if sheet_snapshot:
        st.session_state["_last_sheet_snapshot"] = sheet_snapshot

    with right_col:
        st.subheader("AI Tutor")

        chat_container = st.container(height=500)
        with chat_container:
            for msg in st.session_state["exercise_messages"]:
                st.chat_message(msg["role"]).write(msg["content"])

        if prompt := st.chat_input("Ask about this exercise..."):
            st.session_state["exercise_messages"].append({"role": "user", "content": prompt})

            exercise_context = {
                "plan": plan,
                "sheet_snapshot": st.session_state.get("_last_sheet_snapshot", {}),
            }

            with st.spinner("Thinking..."):
                reply = chat_with_tutor_exercise(
                    st.session_state["exercise_messages"],
                    st.session_state.get("learner_profile", ""),
                    mode="exercise",
                    exercise_context=exercise_context,
                )

            if reply:
                st.session_state["exercise_messages"].append({"role": "assistant", "content": reply})
            else:
                st.session_state["exercise_messages"].append({
                    "role": "assistant",
                    "content": "I'm having trouble connecting. Please try again.",
                })

            st.rerun()

        # Finish exercise button
        st.divider()
        if st.button("Finish Exercise", type="primary"):
            st.session_state["exercise_messages"].append({
                "role": "user",
                "content": "[SYSTEM] The student has finished the exercise. Please summarize their performance: what they did well, what they struggled with, and what to practice next.",
            })
            with st.spinner("Generating feedback..."):
                exercise_context = {
                    "plan": plan,
                    "sheet_snapshot": st.session_state.get("_last_sheet_snapshot", {}),
                }
                reply = chat_with_tutor_exercise(
                    st.session_state["exercise_messages"],
                    st.session_state.get("learner_profile", ""),
                    mode="exercise",
                    exercise_context=exercise_context,
                )

            if reply:
                st.session_state["exercise_messages"].append({"role": "assistant", "content": reply})

            # Update learner profile with performance data
            with st.spinner("Updating your learner profile..."):
                perf_reply = chat_with_tutor_exercise(
                    st.session_state["exercise_messages"] + [
                        {"role": "user", "content": '[SYSTEM] Output a JSON performance summary: {"skills_practiced": [...], "completed_steps": N, "total_steps": N, "struggled_with": [...], "hints_requested": N}'}
                    ],
                    st.session_state.get("learner_profile", ""),
                    mode="exercise",
                    exercise_context=exercise_context,
                )
                if perf_reply:
                    perf_data = _extract_json(perf_reply)
                    if perf_data:
                        session_info = {
                            "type": "exercise",
                            "topic": str(st.session_state.get("exercise_topic", "")),
                            "scenario": plan.get("scenario", ""),
                            "performance": perf_data,
                        }
                        update_learner_profile(
                            st.session_state.get("learner_profile", ""),
                            str(st.session_state.get("exercise_messages", [])),
                            session_information=str(session_info),
                        )

            st.session_state["exercise_phase"] = "completed"
            st.rerun()


# ---------------------------------------------------------------------------
# Phase: Completed
# ---------------------------------------------------------------------------

def render_completed():
    st.header("Exercise Complete!")

    chat_container = st.container(height=500)
    with chat_container:
        for msg in st.session_state["exercise_messages"]:
            st.chat_message(msg["role"]).write(msg["content"])

    if st.button("Start a New Exercise"):
        st.session_state["exercise_phase"] = "brainstorming"
        st.session_state["exercise_messages"] = []
        st.session_state["exercise_plan"] = None
        st.session_state["exercise_topic"] = None
        st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def render_exercise():
    phase = get_exercise_phase()
    if phase == "loading":
        render_loading()
    elif phase == "exercising":
        render_exercising()
    elif phase == "completed":
        render_completed()
    else:
        render_brainstorming()


render_exercise()
