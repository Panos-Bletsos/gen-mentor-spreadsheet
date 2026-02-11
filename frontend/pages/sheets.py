import json
import time
import streamlit as st
import streamlit.components.v1 as components
from assets.js.univer_sheets import get_univer_sheets_html
from utils.request_api import generate_synthetic_sheet_data
from utils.sheet_data_parser import (
    build_univer_workbook_from_payload,
    extract_cell_values,
    get_sheet_summary,
    sheet_to_dataframe,
)


st.markdown('<style>' + open('./assets/css/main.css').read() + '</style>', unsafe_allow_html=True)


def render_sheets():
    st.title("Sheets")

    # Initialize session state
    if 'sheet_data' not in st.session_state:
        st.session_state.sheet_data = None
    if "llm_seed_json" not in st.session_state:
        st.session_state.llm_seed_json = (
            "Generate a mentoring cohort dataset with learner names, countries, "
            "experience level, and weekly availability."
        )
    if "sheet_row_count" not in st.session_state:
        st.session_state.sheet_row_count = 20
    if "sheet_columns" not in st.session_state:
        st.session_state.sheet_columns = ""
    if "sheet_constraints" not in st.session_state:
        st.session_state.sheet_constraints = (
            "Use fictional data only. Keep values realistic and diverse."
        )
    if "load_example_json_requested" not in st.session_state:
        st.session_state.load_example_json_requested = False
    if "llm_populator_expanded" not in st.session_state:
        st.session_state.llm_populator_expanded = True

    if st.session_state.load_example_json_requested:
        st.session_state.llm_seed_json = (
            "Generate a mentorship spreadsheet with learner profile data."
        )
        st.session_state.sheet_row_count = 12
        st.session_state.sheet_columns = (
            "Name, Country, Primary Skill, Level, Weekly Availability (hrs)"
        )
        st.session_state.sheet_constraints = (
            "Use fictional data only. Keep names globally diverse."
        )
        st.session_state.load_example_json_requested = False
        st.session_state.llm_populator_expanded = True
        st.success("Example prompt loaded into the input box.")

    with st.expander(
        "Populate sheet from LLM JSON",
        expanded=st.session_state.llm_populator_expanded,
    ):
        st.caption(
            "Enter generation instructions and click **Populate Sheet**. "
            "Optional: provide columns and constraints. "
            "You can still paste JSON directly (legacy behavior)."
        )
        st.text_area(
            "Data generation prompt (or JSON payload)",
            key="llm_seed_json",
            height=200,
            label_visibility="collapsed",
        )
        st.number_input(
            "Row count",
            key="sheet_row_count",
            min_value=1,
            max_value=500,
            step=1,
        )
        st.text_input(
            "Columns (comma-separated, optional)",
            key="sheet_columns",
            placeholder="Name, Country, Role, Skill, Availability",
        )
        st.text_area(
            "Constraints (optional)",
            key="sheet_constraints",
            height=80,
        )
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Populate Sheet", type="primary", use_container_width=True):
                input_text = (st.session_state.llm_seed_json or "").strip()
                try:
                    payload = json.loads(input_text)
                    st.session_state.sheet_data = build_univer_workbook_from_payload(
                        payload,
                        sheet_name="Generated Data",
                        workbook_name="GenMentor Sheet",
                    )
                    st.success("Sheet populated from JSON.")
                    st.rerun()
                except json.JSONDecodeError:
                    # Not JSON: treat input as generation instructions for backend.
                    try:
                        parsed_columns = [
                            col.strip()
                            for col in (st.session_state.sheet_columns or "").split(",")
                            if col.strip()
                        ]
                        generated = generate_synthetic_sheet_data(
                            user_request=input_text,
                            row_count=st.session_state.sheet_row_count,
                            columns=parsed_columns or None,
                            constraints=st.session_state.sheet_constraints or "",
                            llm_type=st.session_state.get("llm_type", "openai/gpt-4o"),
                        )
                        if not generated:
                            st.error("No response from backend data generator.")
                        else:
                            st.session_state.sheet_data = build_univer_workbook_from_payload(
                                generated,
                                sheet_name="Generated Data",
                                workbook_name="GenMentor Sheet",
                            )
                            st.success("Sheet populated from synthetic backend data.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Could not generate data from backend: {e}")
                except ValueError as e:
                    st.error(f"Unsupported payload format: {e}")
                except Exception as e:
                    st.error(f"Could not populate sheet: {e}")
        with col2:
            if st.button("Load Example JSON", use_container_width=True):
                st.session_state.load_example_json_requested = True
                st.session_state.llm_populator_expanded = True
                st.rerun()

    # If we already have data, use it to initialize the workbook so edits persist across reruns
    workbook_data = None
    if st.session_state.sheet_data and isinstance(st.session_state.sheet_data, dict):
        try:
            workbook_data = json.dumps(st.session_state.sheet_data)
        except Exception:
            pass

    # Render the Univer spreadsheet inside an iframe via components.html().
    # The iframe has built-in "Export JSON" and "Export CSV" buttons.
    # Embed a nonce so that the HTML content is guaranteed to differ across
    # reruns, forcing the browser to fully reload the iframe (and re-execute
    # the Univer init script with the latest workbook data).
    univer_html = get_univer_sheets_html(height="100%", workbook_data=workbook_data)
    nonce = str(time.time())
    univer_html = univer_html.replace("</body>", f"<!-- nonce:{nonce} --></body>")

    sheet_container = st.empty()
    with sheet_container.container():
        components.html(univer_html, height=800, scrolling=False)

    # --- Import data back into Streamlit ---
    st.divider()
    st.subheader("Import Sheet Data")
    st.caption(
        'To bring data into Streamlit: click **"Export JSON"** in the toolbar above, '
        "then upload the downloaded file here."
    )

    uploaded = st.file_uploader(
        "Upload exported JSON",
        type=["json"],
        key="sheet_json_upload",
        label_visibility="collapsed",
    )

    if uploaded is not None:
        try:
            data = json.load(uploaded)
            st.session_state.sheet_data = data
            st.success("Sheet data imported successfully!")
        except json.JSONDecodeError:
            st.error("Invalid JSON file. Please upload the file exported from the sheet above.")

    # --- Display imported data ---
    if st.session_state.sheet_data and isinstance(st.session_state.sheet_data, dict):
        st.divider()
        tab1, tab2, tab3, tab4 = st.tabs(
            ["📊 Summary", "🔢 Cell Values", "📋 DataFrame", "🔍 Raw JSON"]
        )

        with tab1:
            st.subheader("Sheet Summary")
            summary = get_sheet_summary(st.session_state.sheet_data)

            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Workbook Name", summary["workbook_name"] or "Unnamed")
                st.metric("Number of Sheets", summary["num_sheets"])
            with col_b:
                total_cells = sum(s["num_cells"] for s in summary["sheets"])
                st.metric("Total Cells with Data", total_cells)

            if summary["sheets"]:
                st.write("**Sheets:**")
                for sheet in summary["sheets"]:
                    with st.expander(f"Sheet: {sheet['name']}", expanded=True):
                        st.write(f"- **Sheet ID:** {sheet['id']}")
                        st.write(f"- **Rows with data:** {sheet['num_rows']}")
                        st.write(f"- **Non-empty cells:** {sheet['num_cells']}")

        with tab2:
            st.subheader("Cell Values (2D Array)")
            cell_values = extract_cell_values(st.session_state.sheet_data)

            if cell_values:
                for sheet_id, grid in cell_values.items():
                    st.write(f"**Sheet: {sheet_id}**")
                    display_grid = grid[:50]
                    if len(grid) > 50:
                        st.caption(f"Showing first 50 of {len(grid)} rows")

                    display_data = []
                    for i, row in enumerate(display_grid):
                        row_dict = {"Row": i}
                        for j, val in enumerate(row):
                                row_dict[f"Col {j}"] = str(val) if val is not None else ""
                        display_data.append(row_dict)

                    if display_data:
                        st.dataframe(display_data, use_container_width=True)
            else:
                st.caption("No cell data found.")

        with tab3:
            st.subheader("As pandas DataFrame")
            try:
                df = sheet_to_dataframe(st.session_state.sheet_data, has_headers=True)
                if df is not None and not df.empty:
                    st.dataframe(df, use_container_width=True)
                    st.write("**Shape:**", df.shape)
                    numeric_cols = df.select_dtypes(include=["number"]).columns
                    if len(numeric_cols) > 0:
                        st.write("**Numeric Column Statistics:**")
                        st.dataframe(
                            df[numeric_cols].describe(), use_container_width=True
                        )
                else:
                    st.caption("Could not convert to DataFrame or it is empty.")
            except Exception as e:
                st.error(f"Error converting to DataFrame: {e}")

        with tab4:
            st.subheader("Raw JSON Data")
            try:
                st.json(st.session_state.sheet_data, expanded=False)
            except Exception:
                # Fallback: display as formatted text
                st.code(json.dumps(st.session_state.sheet_data, indent=2), language="json")

        # Clear button
        st.divider()
        if st.button("🗑️ Clear Imported Data"):
            st.session_state.sheet_data = None
            st.rerun()


render_sheets()
