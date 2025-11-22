// utils.js

// --- Helper: Timeframe to Minutes ---
function tfToMinutes(tf) {
    switch (tf) {
        case "M1":  return 1;
        case "M3":  return 3;
        case "M5":  return 5;
        case "M15": return 15;
        case "H1":  return 60;
        case "H4":  return 240;
        case "D":   return 1440;
        case "W":   return 10080;
        case "M":   return 43200; // approx 30 days
        default:    return null;
    }
}

// --- Helper: Timeframe to Milliseconds ---
function timeframeToMs(tf) {
    if (!tf) return null;
    switch (tf) {
        case "M1":  return 1 * 60 * 1000;
        case "M3":  return 3 * 60 * 1000;
        case "M5":  return 5 * 60 * 1000;
        case "M15": return 15 * 60 * 1000;
        case "H1":  return 60 * 60 * 1000;
        case "H4":  return 4 * 60 * 60 * 1000;
        case "D":   return 24 * 60 * 60 * 1000;
        case "W":   return 7 * 24 * 60 * 60 * 1000;
        case "M":   return 30 * 24 * 60 * 60 * 1000;
        default:    return null;
    }
}

// --- Helper: Regime Logic ---
function getRegime(tf, pane = "right") {
    // Exception: M15 on HTF (left) -> Hourly Regime
    if (tf === "M15" && pane === "left") {
        return "hourly";
    }
    const mapping = {
        M1: "minute", M3: "minute", M5: "minute", M15: "minute",
        H1: "hourly", H4: "hourly",
        D: "daily", W: "daily", M: "daily",
    };
    return mapping[tf] || "minute";
}

// --- Date Helpers ---
function pad2(n) {
    return String(n).padStart(2, "0");
}

function dateKeyFromDate(dt) {
    const y = dt.getUTCFullYear();
    const m = pad2(dt.getUTCMonth() + 1);
    const d = pad2(dt.getUTCDate());
    return `${y}-${m}-${d}`;
}

function dateFromKey(key) {
    const parts = key.split("-");
    if (parts.length !== 3) return null;
    const y = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    const d = parseInt(parts[2], 10);
    if (!y || !m || !d) return null;
    return new Date(Date.UTC(y, m - 1, d));
}

function addDaysUtc(date, days) {
    const d = new Date(date.getTime());
    d.setUTCDate(d.getUTCDate() + days);
    return d;
}

function tradingDateKeyFromDate(dt) {
    const h = dt.getUTCHours();
    const base = (h >= 17) ? addDaysUtc(dt, 1) : dt;
    return dateKeyFromDate(base);
}

// --- Parsing Helpers ---
function parseNyIsoToMs(isoStr) {
    if (!isoStr) return NaN;
    if (!isoStr.endsWith("Z")) {
        isoStr += "Z";
    }
    return Date.parse(isoStr);
}

function parseNyStringToMs(str) {
    if (!str) return NaN;
    let iso = String(str).trim();
    if (!iso) return NaN;
    if (iso.indexOf("T") === -1 && iso.indexOf(" ") !== -1) {
        iso = iso.replace(" ", "T");
    }
    if (!iso.endsWith("Z")) {
        iso += "Z";
    }
    const ts = Date.parse(iso);
    return Number.isNaN(ts) ? NaN : ts;
}

function pickNumberField(row, candidates) {
    for (const name of candidates) {
        if (name in row && row[name] !== "") {
            const v = parseFloat(String(row[name]).replace(",", "."));
            if (!Number.isNaN(v)) return v;
        }
    }
    return NaN;
}

// --- Array Search Helpers ---
function findPosGEByTs(tfData, targetTs) {
    const bars = tfData.bars;
    let lo = 0, hi = bars.length - 1, res = null;
    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const ts = bars[mid].ts;
        if (ts >= targetTs) {
            res = mid;
            hi = mid - 1;
        } else {
            lo = mid + 1;
        }
    }
    return res;
}

function findPosLEByTs(tfData, targetTs) {
    const bars = tfData.bars;
    let lo = 0, hi = bars.length - 1, res = null;
    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const ts = bars[mid].ts;
        if (ts <= targetTs) {
            res = mid;
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }
    return res;
}

function sliceBarsForRange(tfData, startIdx, endIdx) {
    const bars = tfData.bars;
    const minIdx = tfData.minIdx;
    if (endIdx < startIdx) return [];
    const startPos = Math.max(startIdx - minIdx, 0);
    const endPos = Math.min(endIdx - minIdx, bars.length - 1);
    if (endPos < startPos) return [];
    return bars.slice(startPos, endPos + 1);
}