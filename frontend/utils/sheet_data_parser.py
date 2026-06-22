"""
Utility functions for parsing Univer sheet data into usable formats.
"""
import re


def a1_to_rowcol(a1: str) -> tuple:
    """Convert A1 address (e.g. 'B3') to 0-based (row_idx, col_idx) for Univer cellData."""
    m = re.match(r'^([A-Z]+)([0-9]+)$', a1.strip().upper())
    if not m:
        raise ValueError(f"Invalid A1 address: {a1!r}")
    col_str, row_str = m.group(1), m.group(2)
    col = 0
    for ch in col_str:
        col = col * 26 + (ord(ch) - ord('A') + 1)
    col -= 1  # 0-based
    row = int(row_str) - 1  # 0-based
    return (row, col)


def _col_idx_to_letter(idx: int) -> str:
    """Convert 0-based column index to column letter(s). 0='A', 25='Z', 26='AA'."""
    result = ""
    n = idx + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(ord('A') + rem) + result
    return result


def _coerce_cell_value(value):
    """
    Normalize values before writing them into Univer cellData.
    """
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _build_cell_entry(value):
    """
    Build a Univer cell object from a Python value.

    Formula strings (starting with '=') are stored as {f: "=..."} so Univer
    evaluates them. This lets rebuilt snapshots preserve student formulas across
    iframe reloads, and allows tutor demo formulas to compute on mount.
    """
    normalized = _coerce_cell_value(value)
    if normalized is None:
        return None

    # Formula strings → {f: ...} so Univer evaluates them on load
    if isinstance(normalized, str) and normalized.startswith("="):
        return {"f": normalized}

    cell = {"v": normalized}
    if isinstance(normalized, (int, float)) and not isinstance(normalized, bool):
        # Univer uses t=2 for numbers in snapshots.
        cell["t"] = 2
    return cell


def build_univer_workbook_from_grid(
    grid,
    sheet_name="Generated Data",
    workbook_name="GenMentor Sheet",
):
    """
    Build a minimal Univer workbook snapshot from a 2D array.

    Args:
        grid: list[list[Any]] where each nested list is a row
        sheet_name: Name of the first sheet
        workbook_name: Name of the workbook

    Returns:
        dict: Univer workbook snapshot compatible with createWorkbook()
    """
    if not isinstance(grid, list):
        raise ValueError("Grid payload must be a list of rows.")
    if any(not isinstance(row, list) for row in grid):
        raise ValueError("Each grid row must be a list.")

    sheet_id = "sheet1"
    cell_data = {}
    max_col_count = 0

    for row_idx, row in enumerate(grid):
        if not isinstance(row, list):
            continue
        max_col_count = max(max_col_count, len(row))
        row_cells = {}
        for col_idx, value in enumerate(row):
            cell = _build_cell_entry(value)
            if cell is not None:
                row_cells[str(col_idx)] = cell
        if row_cells:
            cell_data[str(row_idx)] = row_cells

    row_count = max(1000, len(grid) + 20)
    column_count = max(20, max_col_count + 5)

    return {
        "id": "workbook1",
        "name": workbook_name,
        "sheetOrder": [sheet_id],
        "sheets": {
            sheet_id: {
                "id": sheet_id,
                "name": sheet_name,
                "cellData": cell_data,
                "rowCount": row_count,
                "columnCount": column_count,
            }
        },
    }


def build_univer_workbook_from_records(
    records,
    sheet_name="Generated Data",
    workbook_name="GenMentor Sheet",
):
    """
    Build a Univer workbook from list[dict] records.

    The first row is generated from the union of record keys (in first-seen order).
    """
    if not isinstance(records, list):
        raise ValueError("Records payload must be a list.")
    if any(not isinstance(row, dict) for row in records):
        raise ValueError("Each record must be an object/dict.")

    headers = []
    seen = set()
    for record in records:
        for key in record.keys():
            if key not in seen:
                seen.add(key)
                headers.append(key)

    grid = [headers]
    for record in records:
        grid.append([record.get(header) for header in headers])

    return build_univer_workbook_from_grid(
        grid=grid,
        sheet_name=sheet_name,
        workbook_name=workbook_name,
    )


def build_univer_workbook_from_payload(
    payload,
    sheet_name="Generated Data",
    workbook_name="GenMentor Sheet",
):
    """
    Convert a generic LLM payload into a Univer workbook.

    Supported payload formats:
    - list[dict] -> header row + records
    - list[list] -> used as-is
    - {"headers": [...], "rows": [[...], ...]}
    """
    if isinstance(payload, list):
        if not payload:
            return build_univer_workbook_from_grid(
                [[]], sheet_name=sheet_name, workbook_name=workbook_name
            )

        first_item = payload[0]
        if isinstance(first_item, dict):
            return build_univer_workbook_from_records(
                payload, sheet_name=sheet_name, workbook_name=workbook_name
            )
        if isinstance(first_item, list):
            return build_univer_workbook_from_grid(
                payload, sheet_name=sheet_name, workbook_name=workbook_name
            )
        raise ValueError(
            "List payload must contain only objects (records) or arrays (rows)."
        )

    if isinstance(payload, dict):
        headers = payload.get("headers")
        rows = payload.get("rows")
        if isinstance(headers, list) and isinstance(rows, list):
            grid = [headers] + rows
            return build_univer_workbook_from_grid(
                grid, sheet_name=sheet_name, workbook_name=workbook_name
            )

    raise ValueError(
        "Unsupported payload format. Use list[dict], list[list], or {headers, rows}."
    )


def build_univer_multi_sheet_workbook(sheets_list, workbook_name="GenMentor Sheet"):
    """
    Build a Univer workbook with multiple sheets.

    Args:
        sheets_list: list of dicts, each with keys "name" and "cells" (A1 cell-map)
        workbook_name: Name of the workbook

    Returns:
        dict: Univer workbook snapshot compatible with createWorkbook()
    """
    if not sheets_list:
        return build_univer_workbook_from_grid([[]], workbook_name=workbook_name)

    sheet_order = []
    sheets_dict = {}

    for i, sheet_info in enumerate(sheets_list):
        sheet_id = f"sheet{i + 1}"
        sheet_name = sheet_info.get("name", f"Sheet{i + 1}")
        cells_map: dict = sheet_info.get("cells", {})

        cell_data: dict = {}
        max_row_idx = 0
        max_col_idx = 0

        for a1_key, value in cells_map.items():
            try:
                row_idx, col_idx = a1_to_rowcol(a1_key)
            except ValueError:
                continue
            cell_entry = _build_cell_entry(value)
            if cell_entry is None:
                continue
            cell_data.setdefault(str(row_idx), {})[str(col_idx)] = cell_entry
            max_row_idx = max(max_row_idx, row_idx)
            max_col_idx = max(max_col_idx, col_idx)

        row_count = max(1000, max_row_idx + 20)
        column_count = max(20, max_col_idx + 5)

        sheet_order.append(sheet_id)
        sheets_dict[sheet_id] = {
            "id": sheet_id,
            "name": sheet_name,
            "cellData": cell_data,
            "rowCount": row_count,
            "columnCount": column_count,
        }

    return {
        "id": "workbook1",
        "name": workbook_name,
        "sheetOrder": sheet_order,
        "sheets": sheets_dict,
    }


def rebuild_sheets_from_snapshot(raw_snapshot):
    """Rebuild the durable [{name, cells}] list from a live workbook.save() snapshot.

    Prefers the formula string (f) over the cached display value (v) for formula cells,
    so that formulas survive iframe reloads and are re-evaluated by Univer on mount.
    _build_cell_entry already handles formula strings starting with '=' correctly.

    Args:
        raw_snapshot: dict returned by workbook.save() (the Univer snapshot format).

    Returns:
        list of {name, cells} dicts (cells is an A1 cell-map), or None if the snapshot is invalid.
    """
    if not raw_snapshot or not isinstance(raw_snapshot, dict):
        return None

    snapshot_sheets = raw_snapshot.get("sheets", {})
    if not isinstance(snapshot_sheets, dict) or not snapshot_sheets:
        return None

    sheet_order = raw_snapshot.get("sheetOrder", list(snapshot_sheets.keys()))
    result = []

    for sheet_id in sheet_order:
        sheet_info = snapshot_sheets.get(sheet_id)
        if not isinstance(sheet_info, dict):
            continue

        sheet_name = sheet_info.get("name", sheet_id)
        cell_data = sheet_info.get("cellData", {})
        if not isinstance(cell_data, dict) or not cell_data:
            continue

        # Find grid dimensions
        max_row = -1
        max_col = -1
        for row_str, row_data in cell_data.items():
            try:
                row_idx = int(row_str)
                max_row = max(max_row, row_idx)
                if isinstance(row_data, dict):
                    for col_str in row_data.keys():
                        try:
                            max_col = max(max_col, int(col_str))
                        except (ValueError, TypeError):
                            pass
            except (ValueError, TypeError):
                pass

        if max_row < 0:
            continue

        # Build A1 cell-map from the Univer snapshot, preferring formula (f) over cached value (v)
        cells: dict = {}
        for r in range(max_row + 1):
            for c in range(max_col + 1):
                cell = cell_data.get(str(r), {}).get(str(c))
                if isinstance(cell, dict):
                    val = cell.get("f") if cell.get("f") is not None else cell.get("v")
                else:
                    val = None
                if val is not None:
                    a1 = _col_idx_to_letter(c) + str(r + 1)
                    cells[a1] = val

        if cells:
            result.append({"name": sheet_name, "cells": cells})

    return result if result else None


def extract_cell_values(sheet_data):
    """
    Extract cell values from Univer sheet snapshot into a 2D array.
    
    Args:
        sheet_data: The sheet data object returned from Univer (via postMessage)
    
    Returns:
        dict: A dictionary with sheet IDs as keys and 2D arrays of cell values as values.
              Format: { sheet_id: [[row0_col0, row0_col1, ...], [row1_col0, row1_col1, ...], ...] }
    """
    result = {}
    
    try:
        if not sheet_data or not isinstance(sheet_data, dict):
            return result
        
        sheets = sheet_data.get('sheets', {})
        if not isinstance(sheets, dict):
            return result
        
        for sheet_id, sheet_info in sheets.items():
            if not isinstance(sheet_info, dict):
                continue
            
            # Get cell data
            cell_data = sheet_info.get('cellData', {})
            if not isinstance(cell_data, dict):
                continue
            
            # Find max row and column to create the 2D array
            max_row = -1
            max_col = -1
            
            for row_str, row_data in cell_data.items():
                try:
                    row_idx = int(row_str)
                    max_row = max(max_row, row_idx)
                    
                    if isinstance(row_data, dict):
                        for col_str in row_data.keys():
                            try:
                                col_idx = int(col_str)
                                max_col = max(max_col, col_idx)
                            except (ValueError, TypeError):
                                pass
                except (ValueError, TypeError):
                    pass
            
            # Create 2D array
            if max_row >= 0 and max_col >= 0:
                grid = [[None for _ in range(max_col + 1)] for _ in range(max_row + 1)]
                
                # Fill in the cell values
                for row_str, row_data in cell_data.items():
                    try:
                        row_idx = int(row_str)
                        if isinstance(row_data, dict):
                            for col_str, cell_info in row_data.items():
                                try:
                                    col_idx = int(col_str)
                                    if isinstance(cell_info, dict):
                                        # Extract the display value (v) or formula result (f)
                                        value = cell_info.get('v')
                                        if value is None:
                                            value = cell_info.get('f')
                                        grid[row_idx][col_idx] = value
                                except (ValueError, TypeError):
                                    pass
                    except (ValueError, TypeError):
                        pass
                
                result[sheet_id] = grid
    
    except Exception as e:
        print(f"Error extracting cell values: {e}")
    
    return result


def sheet_to_dataframe(sheet_data, sheet_id=None, has_headers=True):
    """
    Convert Univer sheet data to a pandas DataFrame.
    
    Args:
        sheet_data: The sheet data object returned from Univer
        sheet_id: Optional specific sheet ID. If None, uses the first sheet.
        has_headers: If True, treats the first row as column headers.
    
    Returns:
        pandas.DataFrame or None if pandas is not available or data is invalid
    """
    try:
        import pandas as pd
    except ImportError:
        print("pandas is not installed. Cannot convert to DataFrame.")
        return None
    
    cell_values = extract_cell_values(sheet_data)
    if not cell_values:
        return None
    
    # Get the target sheet
    if sheet_id and sheet_id in cell_values:
        grid = cell_values[sheet_id]
    else:
        # Use first sheet
        grid = next(iter(cell_values.values()), None)
    
    if not grid:
        return None
    
    # Convert to DataFrame
    if has_headers and len(grid) > 0:
        headers = grid[0]
        data = grid[1:]
        df = pd.DataFrame(data, columns=headers)
    else:
        df = pd.DataFrame(grid)
    
    return df


def get_sheet_summary(sheet_data):
    """
    Get a summary of the sheet data.
    
    Args:
        sheet_data: The sheet data object returned from Univer
    
    Returns:
        dict: Summary information about the sheets
    """
    summary = {
        'workbook_name': None,
        'num_sheets': 0,
        'sheets': []
    }
    
    try:
        if not sheet_data or not isinstance(sheet_data, dict):
            return summary
        
        summary['workbook_name'] = sheet_data.get('name')
        
        sheets = sheet_data.get('sheets', {})
        if isinstance(sheets, dict):
            summary['num_sheets'] = len(sheets)
            
            for sheet_id, sheet_info in sheets.items():
                if isinstance(sheet_info, dict):
                    cell_data = sheet_info.get('cellData', {})
                    num_rows = len(cell_data) if isinstance(cell_data, dict) else 0
                    
                    # Count non-empty cells
                    num_cells = 0
                    for row_data in cell_data.values():
                        if isinstance(row_data, dict):
                            num_cells += len(row_data)
                    
                    summary['sheets'].append({
                        'id': sheet_id,
                        'name': sheet_info.get('name', f'Sheet {sheet_id}'),
                        'num_rows': num_rows,
                        'num_cells': num_cells
                    })
    
    except Exception as e:
        print(f"Error generating summary: {e}")
    
    return summary
