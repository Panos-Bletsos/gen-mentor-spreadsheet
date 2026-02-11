"""
Utility functions for parsing Univer sheet data into usable formats.
"""


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
    """
    normalized = _coerce_cell_value(value)
    if normalized is None:
        return None

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
