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
})();

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
