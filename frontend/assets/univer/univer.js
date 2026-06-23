var univerAPI;

(function () {
    var createUniver = UniverPresets.createUniver;
    var LocaleType = UniverCore.LocaleType;
    var mergeLocales = UniverCore.mergeLocales;
    var UniverSheetsCorePreset = UniverPresetSheetsCore.UniverSheetsCorePreset;

    var result = createUniver({
        locale: LocaleType.EN_US,
        locales: {
            [LocaleType.EN_US]: mergeLocales(UniverPresetSheetsCoreEnUS),
        },
        presets: [UniverSheetsCorePreset()],
    });

    univerAPI = result.univerAPI;
    univerAPI.createWorkbook(window.__WORKBOOK_DATA__ || { name: "GenMentor Sheet" });

    // --- Selection / focus tracking ---
    setupSelectionTracking();

    // --- Tutor highlights (re-applied on every iframe mount) ---
    applyHighlights(window.__HIGHLIGHTS__);
})();

/**
 * Convert a 0-based column index to a spreadsheet column letter (0 → A, 25 → Z, 26 → AA, …)
 */
function columnIndexToLetter(index) {
    var letter = "";
    var n = index;
    while (n >= 0) {
        letter = String.fromCharCode((n % 26) + 65) + letter;
        n = Math.floor(n / 26) - 1;
    }
    return letter;
}

/**
 * Get the current active cell position.
 * Returns { row, col, rowDisplay, colLetter, cellRef } or null.
 */
function getActiveCellPosition() {
    try {
        var workbook = univerAPI.getActiveWorkbook();
        if (!workbook) return null;
        var sheet = workbook.getActiveSheet();
        if (!sheet) return null;
        var selection = sheet.getSelection();
        if (!selection) return null;
        var range = selection.getActiveRange();
        if (!range) return null;

        var row = range.getRow();        // 0-based
        var col = range.getColumn();     // 0-based
        var colLetter = columnIndexToLetter(col);
        var cellRef = colLetter + (row + 1); // e.g. "B3"
        var sheetName = sheet.getSheetName ? sheet.getSheetName()
                      : (sheet.getName ? sheet.getName() : null);

        return {
            sheetName: sheetName,        // active tab name — used by tutor for targeting
            row: row,
            col: col,
            rowDisplay: row + 1,         // 1-based for display
            colLetter: colLetter,
            cellRef: cellRef,
        };
    } catch (e) {
        console.warn("Could not read active cell:", e);
        return null;
    }
}

/**
 * Wire up a listener that fires whenever the selection changes
 * and updates the cell-info display.
 */
function setupSelectionTracking() {
    var cellInfoEl = document.getElementById("cell-info");

    function updateCellInfo() {
        var pos = getActiveCellPosition();
        if (!cellInfoEl) return;
        
        if (!pos) {
            cellInfoEl.innerHTML = '<span style="color: #999;">Click on a cell to see its position</span>';
            return;
        }

        // Update the cell info display
        cellInfoEl.innerHTML = 
            '<span style="font-weight: 600; color: #1e40af;">Active Cell:</span> ' +
            '<code style="background: white; padding: 2px 8px; border: 1px solid #3b82f6; border-radius: 3px; font-weight: 700; color: #1e40af;">' + 
            pos.cellRef + 
            '</code> ' +
            '<span style="color: #6b7280;">|</span> ' +
            '<span style="color: #374151;">Row <strong>' + pos.rowDisplay + '</strong>, Column <strong>' + pos.colLetter + '</strong></span>';
    }

    try {
        var workbook = univerAPI.getActiveWorkbook();
        if (workbook) {
            workbook.onSelectionChange(function (_selection) {
                updateCellInfo();
            });
        }
        // Initial update
        updateCellInfo();
    } catch (e) {
        console.warn("Could not register selection listener:", e);
    }
}

/**
 * Parse an A1-notation range string into {r1, c1, r2, c2} (0-based).
 * Handles single cells ("C2") and ranges ("C2:C11").
 */
function _parseA1Range(a1) {
    var m = a1.match(/^([A-Za-z]+)(\d+)(?::([A-Za-z]+)(\d+))?$/);
    if (!m) return null;
    function colToIdx(s) {
        s = s.toUpperCase();
        var n = 0;
        for (var i = 0; i < s.length; i++) n = n * 26 + s.charCodeAt(i) - 64;
        return n - 1; // 0-based
    }
    var r1 = parseInt(m[2], 10) - 1;
    var c1 = colToIdx(m[1]);
    var r2 = m[3] ? parseInt(m[4], 10) - 1 : r1;
    var c2 = m[3] ? colToIdx(m[3]) : c1;
    return { r1: r1, c1: c1, r2: r2, c2: c2 };
}

/**
 * Find a sheet by tab name. Returns null (never falls back to active sheet)
 * so callers can skip painting rather than silently target the wrong tab.
 */
function _findSheetByName(workbook, name) {
    try {
        var sheets = workbook.getSheets ? workbook.getSheets() : [];
        for (var i = 0; i < sheets.length; i++) {
            var s = sheets[i];
            var sName = s.getSheetName ? s.getSheetName() : (s.getName ? s.getName() : null);
            if (sName === name) return s;
        }
        // Strict: no match — warn with available names so bugs are visible
        var available = sheets.map(function(s) {
            return s.getSheetName ? s.getSheetName() : (s.getName ? s.getName() : "?");
        });
        console.warn("_findSheetByName: no sheet named '" + name + "'. Available: [" + available.join(", ") + "]");
    } catch (e) {}
    return null;
}

/**
 * Apply tutor highlight groups to the spreadsheet.
 * payload: array of {sheet, ranges, color} — same format as window.__HIGHLIGHTS__.
 * Safe to call with null/undefined (no-op).
 */
function applyHighlights(payload) {
    if (!payload || !Array.isArray(payload) || payload.length === 0) return;
    try {
        var workbook = univerAPI.getActiveWorkbook();
        if (!workbook) return;
        var _switchedTab = false;
        payload.forEach(function (g) {
            var sheet = _findSheetByName(workbook, g.sheet);
            if (!sheet) return;
            // Bring the first highlighted tab into view so the student sees it
            if (!_switchedTab) {
                try {
                    if (workbook.setActiveSheet) workbook.setActiveSheet(sheet);
                    else if (sheet.activate) sheet.activate();
                } catch (e) {
                    console.warn("applyHighlights: could not switch tab", e);
                }
                _switchedTab = true;
            }
            var color = g.color || "#fff3cd";
            (g.ranges || []).forEach(function (a1) {
                try {
                    var range = null;
                    // Try A1-string overload first
                    if (sheet.getRange) {
                        try { range = sheet.getRange(a1); } catch (e1) {}
                    }
                    // Fallback: parse A1 and call numeric overload
                    if (!range) {
                        var coords = _parseA1Range(a1);
                        if (coords && sheet.getRange) {
                            range = sheet.getRange(
                                coords.r1, coords.c1,
                                coords.r2 - coords.r1 + 1,
                                coords.c2 - coords.c1 + 1
                            );
                        }
                    }
                    if (range) {
                        if (range.setBackgroundColor) range.setBackgroundColor(color);
                        else if (range.setBackground) range.setBackground(color);
                    }
                } catch (e) {
                    console.warn("applyHighlights: could not apply range", a1, e);
                }
            });
        });
    } catch (e) {
        console.warn("applyHighlights failed:", e);
    }
}

function getWorkbookSnapshot() {
    try {
        var workbook = univerAPI.getActiveWorkbook();
        if (workbook) {
            return workbook.save();
        }
    } catch (error) {
        console.error("Error getting workbook data:", error);
    }
    return null;
}

function downloadFile(content, filename, mimeType) {
    var blob = new Blob([content], { type: mimeType });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

function setStatus(text) {
    var status = document.getElementById("status");
    if (!status) {
        return;
    }
    status.textContent = text;
}

function clearStatusAfter(delayMs) {
    setTimeout(function () {
        setStatus("");
    }, delayMs);
}

function exportJSON() {
    var snapshot = getWorkbookSnapshot();
    if (!snapshot) {
        setStatus("No data to export.");
        return;
    }

    var jsonStr = JSON.stringify(snapshot, null, 2);
    downloadFile(jsonStr, "sheet_data.json", "application/json");
    setStatus("JSON exported!");
    clearStatusAfter(3000);
}

function exportCSV() {
    var snapshot = getWorkbookSnapshot();
    if (!snapshot || !snapshot.sheets) {
        setStatus("No data to export.");
        return;
    }

    var sheetId = Object.keys(snapshot.sheets)[0];
    var sheet = snapshot.sheets[sheetId];
    var cellData = sheet.cellData || {};

    var maxRow = -1;
    var maxCol = -1;

    for (var r in cellData) {
        var rowIdx = parseInt(r, 10);
        if (rowIdx > maxRow) {
            maxRow = rowIdx;
        }
        for (var c in cellData[r]) {
            var colIdx = parseInt(c, 10);
            if (colIdx > maxCol) {
                maxCol = colIdx;
            }
        }
    }

    if (maxRow < 0 || maxCol < 0) {
        setStatus("Sheet is empty.");
        return;
    }

    var rows = [];
    for (var i = 0; i <= maxRow; i++) {
        var cols = [];
        for (var j = 0; j <= maxCol; j++) {
            var cell = cellData[i] && cellData[i][j] ? cellData[i][j] : {};
            var val = cell.v !== undefined && cell.v !== null ? String(cell.v) : "";
            if (val.indexOf(",") !== -1 || val.indexOf('"') !== -1 || val.indexOf("\n") !== -1) {
                val = '"' + val.replace(/"/g, '""') + '"';
            }
            cols.push(val);
        }
        rows.push(cols.join(","));
    }

    downloadFile(rows.join("\n"), "sheet_data.csv", "text/csv");
    setStatus("CSV exported!");
    clearStatusAfter(3000);
}
