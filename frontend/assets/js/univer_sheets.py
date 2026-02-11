from pathlib import Path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def get_univer_sheets_html(height="100%", workbook_data=None):
    """
    Build the Univer iframe HTML by composing separate template, CSS, and JS files.

    Args:
        height: CSS height for the page root (default "100%").
        workbook_data: Optional JSON string of workbook data to initialize the sheet with.
                       If None, creates an empty workbook.
    """
    asset_dir = Path(__file__).resolve().parents[1] / "univer"

    html_template = _read_text(asset_dir / "index.html")
    css_content = _read_text(asset_dir / "univer.css")
    js_content = _read_text(asset_dir / "univer.js")

    workbook_json = workbook_data if workbook_data else "null"

    html = html_template.replace("__ROOT_HEIGHT__", height)
    html = html.replace("/*__UNIVER_CSS__*/", css_content)
    html = html.replace("/*__WORKBOOK_INIT__*/null", workbook_json)
    html = html.replace("/*__UNIVER_JS__*/", js_content)

    return html
