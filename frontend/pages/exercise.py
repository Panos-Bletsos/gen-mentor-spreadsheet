import json
import time
import streamlit as st
import streamlit.components.v1 as components
from assets.js.univer_sheets import get_univer_sheets_html
from utils.sheet_data_parser import build_univer_workbook_from_payload


st.markdown('<style>' + open('./assets/css/main.css').read() + '</style>', unsafe_allow_html=True)

MOCK_EXERCISE = {
    "title": "SUM and AVERAGE Practice",
    "description": (
        "Calculate the **total** and **average** quarterly sales for each region.\n\n"
        "- In the **Total** column, use the `SUM` function to add Q1 through Q4.\n"
        "- In the **Average** column, use the `AVERAGE` function over the same range.\n\n"
        "Try typing formulas directly in the spreadsheet cells below."
    ),
    "spreadsheet_data": {
        "headers": ["Region", "Q1", "Q2", "Q3", "Q4", "Total", "Average"],
        "rows": [
            ["North", 1200, 1500, 1800, 1600, "", ""],
            ["South", 900, 1100, 1300, 1000, "", ""],
            ["East", 1400, 1600, 1900, 1700, "", ""],
            ["West", 800, 950, 1100, 1050, "", ""],
        ],
    },
}

MOCK_TUTOR_REPLIES = [
    "Great question! For the Total column, try using `=SUM(B2:E2)` in cell F2, then drag down to fill the other rows.",
    "The AVERAGE function works similarly: `=AVERAGE(B2:E2)` in cell G2. You can also select the range with your mouse!",
    "You're doing well! Remember that SUM adds all values in a range, while AVERAGE divides the sum by the count.",
    "If you see an error, double-check that your cell references match the data range. The numbers are in columns B through E.",
]


def render_exercise():
    left_col, right_col = st.columns([1.5, 1], gap="large")

    with left_col:
        st.header(MOCK_EXERCISE["title"])
        st.markdown(MOCK_EXERCISE["description"])

        workbook = build_univer_workbook_from_payload(
            MOCK_EXERCISE["spreadsheet_data"],
            sheet_name="Sales Data",
            workbook_name="Exercise Sheet",
        )
        workbook_json = json.dumps(workbook)
        univer_html = get_univer_sheets_html(height="100%", workbook_data=workbook_json)
        # Strip UI down to formula bar + cells only
        strip_css = """<style>
            #toolbar { display: none !important; }
            #cell-info { display: none !important; }
            #app { height: 100% !important; }
            /* Hide Univer toolbar/ribbon/header elements */
            [role="toolbar"] { display: none !important; }
            [role="menubar"] { display: none !important; }
            [role="menu"] { display: none !important; }
            /* Hide elements that are likely the formatting toolbar */
            div[style*="flex"][style*="row"] > button,
            div[style*="flex"][style*="row"] > [role="button"] { display: none !important; }
            /* Generic: hide button collections that are top-aligned (toolbar pattern) */
            div:has(> button):has(> button + button) { display: none !important; }
        </style>"""
        strip_js = """<script>
        (function hideUniversToolbar() {
            var timer = setInterval(function() {
                var app = document.getElementById('app');
                if (!app) return;
                var allDivs = app.querySelectorAll('div');
                allDivs.forEach(function(el) {
                    // If div has many button/icon children (toolbar pattern), hide it
                    var btnCount = el.querySelectorAll(':scope > button, :scope > [role="button"], :scope > svg').length;
                    if (btnCount >= 3 && el.offsetHeight < 100) {
                        el.style.display = 'none';
                    }
                });
                clearInterval(timer);
            }, 200);
        })();
        </script>"""
        univer_html = univer_html.replace("</head>", strip_css + "</head>")
        univer_html = univer_html.replace("</body>", strip_js + "</body>")
        nonce = str(time.time())
        univer_html += f"<!-- nonce:{nonce} -->"
        components.html(univer_html, height=600, scrolling=False)

    with right_col:
        st.subheader("AI Tutor")

        chat_container = st.container(height=500)
        with chat_container:
            for msg in st.session_state["exercise_messages"]:
                st.chat_message(msg["role"]).write(msg["content"])

        if prompt := st.chat_input("Ask about this exercise..."):
            st.session_state["exercise_messages"].append({"role": "user", "content": prompt})

            reply_idx = len(st.session_state["exercise_messages"]) // 2
            reply = MOCK_TUTOR_REPLIES[reply_idx % len(MOCK_TUTOR_REPLIES)]
            st.session_state["exercise_messages"].append({"role": "assistant", "content": reply})

            st.rerun()


render_exercise()
