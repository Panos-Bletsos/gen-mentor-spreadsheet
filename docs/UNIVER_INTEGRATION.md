# Univer Sheets Integration with Streamlit

This document explains how the Univer spreadsheet framework is integrated with Streamlit and how to access sheet data.

## Overview

Univer is a powerful React-based spreadsheet framework that has been integrated into the GenMentor Streamlit app. Since Streamlit is Python-based and Univer is React-based, we use a hybrid approach:

1. **Univer runs via CDN** - Loaded through `<script>` tags (UMD builds) including React, ReactDOM, RxJS, and Univer packages
2. **Embedded in iframe** - Rendered using `streamlit.components.v1.html()` which creates an isolated iframe
3. **Bidirectional communication** - Uses `postMessage` API to send data from Univer (inside iframe) to Streamlit (parent window)

## Architecture

```
┌─────────────────────────────────────────┐
│   Streamlit (Python)                    │
│   ├── pages/sheets.py                   │
│   ├── components.html()                 │
│   │   └── iframe                        │
│   │       └── Univer (React via CDN)    │
│   └── Receives data via postMessage     │
└─────────────────────────────────────────┘
```

## Files

### `frontend/assets/js/univer_sheets.py`
Contains the `get_univer_sheets_html()` function that generates the complete HTML document for Univer:
- Loads React, ReactDOM, RxJS via CDN
- Loads Univer preset packages and locales
- Initializes Univer with the `createUniver()` API
- Sets up bidirectional communication via `postMessage`

**Key features:**
- `enable_sync=True` - Automatically sends sheet data to Streamlit when cells change (debounced to 1 second)
- Hooks into Univer's command system to detect data modifications
- Listens for `getUniverData` message from Streamlit to trigger manual sync

### `frontend/pages/sheets.py`
The Streamlit page that embeds Univer and displays/processes the data:
- Embeds Univer using `components.html()`
- Receives data returned by the component
- Displays data in multiple formats (summary, cell values, DataFrame, raw JSON)
- Provides export functionality (JSON, CSV)

### `frontend/utils/sheet_data_parser.py`
Utility functions for parsing Univer's data format:

#### `extract_cell_values(sheet_data)`
Extracts cell values from Univer snapshot into a 2D array.

**Returns:**
```python
{
    'sheet_id_1': [
        [cell_0_0, cell_0_1, cell_0_2, ...],
        [cell_1_0, cell_1_1, cell_1_2, ...],
        ...
    ],
    'sheet_id_2': [...],
}
```

#### `sheet_to_dataframe(sheet_data, sheet_id=None, has_headers=True)`
Converts Univer sheet data to a pandas DataFrame.

**Parameters:**
- `sheet_data`: The Univer data object
- `sheet_id`: Optional specific sheet ID (uses first sheet if None)
- `has_headers`: If True, treats first row as column headers

**Returns:** `pandas.DataFrame` or `None`

#### `get_sheet_summary(sheet_data)`
Gets summary information about all sheets.

**Returns:**
```python
{
    'workbook_name': 'GenMentor Sheet',
    'num_sheets': 2,
    'sheets': [
        {
            'id': 'sheet_id_1',
            'name': 'Sheet1',
            'num_rows': 10,
            'num_cells': 45
        },
        ...
    ]
}
```

## Data Flow

### 1. Univer → Streamlit (Automatic Sync)

When cells are edited in Univer:

1. Univer's command system detects the change
2. After 1 second debounce, `sendDataToStreamlit()` is called
3. `univerAPI.getActiveWorkbook().save()` captures the current state
4. Data is sent via `window.parent.postMessage({ type: 'univerData', data: snapshot }, '*')`
5. Streamlit's `components.html()` receives the data and returns it
6. The returned data is stored in `st.session_state.sheet_data`

### 2. Streamlit → Univer (Manual Trigger)

To manually request data from Univer (future enhancement):
```python
# Send message to iframe to trigger data sync
components.html("""
<script>
    const iframe = window.parent.document.querySelector('iframe');
    iframe.contentWindow.postMessage({ type: 'getUniverData' }, '*');
</script>
""", height=0)
```

### 3. Data Persistence

Currently, data is stored in `st.session_state.sheet_data` which persists during the Streamlit session. To persist across sessions, you can:

```python
# Save to file
import json
with open('sheet_data.json', 'w') as f:
    json.dump(st.session_state.sheet_data, f)

# Load from file
with open('sheet_data.json', 'r') as f:
    st.session_state.sheet_data = json.load(f)

# Pass to Univer on next render
workbook_data = json.dumps(st.session_state.sheet_data)
univer_html = get_univer_sheets_html(workbook_data=workbook_data)
```

## Usage Examples

### Example 1: Process sheet data in your backend

```python
import streamlit as st
from utils.sheet_data_parser import extract_cell_values
from utils.request_api import send_to_backend

if st.session_state.sheet_data:
    cell_values = extract_cell_values(st.session_state.sheet_data)
    
    # Send to your backend API
    response = send_to_backend('/api/process-sheet', {
        'sheet_data': cell_values
    })
    
    st.success(f"Data processed: {response}")
```

### Example 2: Convert to DataFrame and analyze

```python
from utils.sheet_data_parser import sheet_to_dataframe

df = sheet_to_dataframe(st.session_state.sheet_data, has_headers=True)

if df is not None:
    # Perform analysis
    st.write("Column means:", df.mean())
    
    # Plot with plotly
    import plotly.express as px
    fig = px.line(df, x='Date', y='Revenue')
    st.plotly_chart(fig)
```

### Example 3: Validate user input

```python
from utils.sheet_data_parser import extract_cell_values

if st.button("Validate Data"):
    cells = extract_cell_values(st.session_state.sheet_data)
    first_sheet = next(iter(cells.values()))
    
    # Check if all cells in column 0 are numbers
    errors = []
    for i, row in enumerate(first_sheet[1:], start=1):  # Skip header
        if row[0] is not None and not isinstance(row[0], (int, float)):
            errors.append(f"Row {i}: Expected number, got {type(row[0])}")
    
    if errors:
        st.error("\n".join(errors))
    else:
        st.success("All data is valid!")
```

## Univer Data Format

The data returned by `univerAPI.getActiveWorkbook().save()` has this structure:

```json
{
    "id": "workbook_id",
    "name": "GenMentor Sheet",
    "sheetOrder": ["sheet1", "sheet2"],
    "sheets": {
        "sheet1": {
            "id": "sheet1",
            "name": "Sheet1",
            "cellData": {
                "0": {  // Row index
                    "0": {  // Column index
                        "v": "Header1",  // Value
                        "s": "style_id"  // Style reference
                    },
                    "1": { "v": "Header2" }
                },
                "1": {
                    "0": { "v": 42, "t": 2 },  // t=2 means number
                    "1": { "v": "Text" }
                }
            },
            "rowCount": 1000,
            "columnCount": 20,
            "rowData": {...},  // Row heights
            "columnData": {...}  // Column widths
        }
    }
}
```

## Limitations

1. **Refresh required for data sync** - Streamlit's `components.html()` only returns data on component mount/remount. For real-time sync, the page needs to rerun. Consider using `st.rerun()` on a timer if needed.

2. **Iframe isolation** - The Univer component runs in a sandboxed iframe, so it can't directly access Streamlit's Python backend or session state.

3. **Data size** - Very large spreadsheets (10,000+ cells) may impact performance when syncing via postMessage.

4. **Formulas** - Complex formulas are evaluated by Univer, but the snapshot contains computed values, not the original formulas.

## Future Enhancements

1. **Custom Streamlit component** - Build a proper Streamlit component package for better integration
2. **WebSocket sync** - Use WebSocket for real-time bidirectional communication instead of postMessage
3. **Backend storage** - Automatically save sheet data to database or file system
4. **Collaborative editing** - Multiple users editing the same sheet via WebSocket

## Troubleshooting

### Data not updating
- Make sure `enable_sync=True` in `get_univer_sheets_html()`
- Wait 1-2 seconds after editing (debounce delay)
- Check browser console for JavaScript errors

### Empty data received
- Check if the sheet has any cell data
- Verify the postMessage is working (browser DevTools → Console)
- Make sure the iframe is fully loaded before editing

### Performance issues
- Reduce the size of the sheet (fewer rows/columns)
- Increase the debounce delay in `univer_sheets.py`
- Disable auto-sync and use manual export buttons instead

## References

- [Univer Documentation](https://docs.univer.ai/)
- [Streamlit Components API](https://docs.streamlit.io/library/components)
- [postMessage API](https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage)
