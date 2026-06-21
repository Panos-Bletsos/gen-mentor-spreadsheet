  Role

  You are a frontend engineer working on a Streamlit + Python web application.

  Context

  This is a Streamlit multi-page app (frontend/) for an undergraduate thesis: an
  interactive spreadsheet learning environment with an AI tutor. The app already has
  a working Univer.js spreadsheet PoC (referenced in pages/sheets.py — a React
  component loaded via CDN in an <iframe>, communicating via postMessage). do not use the existing floating chatbot component in components/chatbot.py.

  Key files to understand before starting:
  - main.py — registers pages via st.navigation() and st.Page(); this is where you
  add the new menu item
  - components/chatbot.py — existing chat UI pattern to reuse
  - pages/sheets.py — existing Univer.js integration to reuse
  - config.py — contains use_mock_data flag

  Task

  Add a new Exercise page to the app. Specifically:

  1. Add a new sidebar menu item — register a new st.Page("pages/exercise.py", ...)    in main.py, adding it to the st.navigation() call for authenticated users (i.e.
  inside the if st.session_state["if_complete_onboarding"] branch). Use an
  appropriate Material icon (e.g. :material/edit_note:).
  2. Create pages/exercise.py with a two-column layout:
    - Left/main column (~70% width): exercise title, exercise description text, and
  the Univer.js spreadsheet iframe (reuse the pattern from pages/sheets.py)
    - Right column (~30% width): a chat interface for the AI tutor to guide the
  student through the exercise (reuse the chat UI pattern from components/chatbot.py
  but rendered inline, not as a floating button)
  3. Mock all backend calls. There is no backend endpoint yet. Hardcode a sample
  exercise object (title, description, initial spreadsheet data) directly in the
  page. For the chat, simulate a tutor response (e.g. a hardcoded reply or a simple
  echo) so the UI is functional end-to-end.

  Constraints

  - This is a thesis prototype — keep it simple and functional, not polished
  - Do not add new dependencies; use only what is already in requirements.txt
  - Follow existing patterns (session state, CSS imports, page structure) used in
  other pages like knowledge_document.py
  - The chat state (message history) should live in st.session_state following the
  existing pattern in chatbot.py