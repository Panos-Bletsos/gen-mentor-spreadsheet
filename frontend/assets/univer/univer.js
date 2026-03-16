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

        return {
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
