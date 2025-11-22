// data_loader.js

// --- Base Data Loading ---
async function loadData() {
    const response = await fetch("data.json");
    if (!response.ok) {
        throw new Error("Could not load data.json: " + response.statusText);
    }
    const payload = await response.json();

    if (!payload.timeframes) {
        throw new Error("Invalid JSON: no 'timeframes' key");
    }

    for (const [tf, tfData] of Object.entries(payload.timeframes)) {
        const bars = tfData.bars || [];
        if (!bars.length) continue;

        for (const bar of bars) {
            bar.ts = parseNyIsoToMs(bar.t);
        }
        tfData.minIdx = bars[0].i;
        tfData.maxIdx = bars[bars.length - 1].i;

        const yearFirstTradingDate = {};
        const monthFirstTradingDate = {};
        for (const bar of bars) {
            const dt = new Date(bar.ts);
            const y = dt.getUTCFullYear();
            const m = dt.getUTCMonth() + 1;
            const d = dt.getUTCDate();
            const wd = dt.getUTCDay();
            if (wd === 6) continue;
            const mStr = String(m).padStart(2, "0");
            const dStr = String(d).padStart(2, "0");
            const dateKey = `${y}-${mStr}-${dStr}`;
            const ymKey = `${y}-${mStr}`;
            if (yearFirstTradingDate[y] === undefined) {
                yearFirstTradingDate[y] = dateKey;
            }
            if (monthFirstTradingDate[ymKey] === undefined) {
                monthFirstTradingDate[ymKey] = dateKey;
            }
        }
        tfData.yearFirstTradingDate = yearFirstTradingDate;
        tfData.monthFirstTradingDate = monthFirstTradingDate;
    }
    return payload;
}

// --- CSV Parsing & Processing ---

function parseCsvToObjects(text) {
    const lines = text.split(/\r?\n/).filter(line => line.trim() !== "");
    if (!lines.length) return [];
    const header = lines[0].split(",").map(h => h.trim());
    const rows = [];
    for (let i = 1; i < lines.length; i++) {
        const parts = lines[i].split(",");
        if (!parts.length) continue;
        const obj = {};
        header.forEach((h, idx) => {
            obj[h] = (parts[idx] !== undefined) ? parts[idx].trim() : "";
        });
        rows.push(obj);
    }
    return rows;
}

function updatePhase2SignalBaseFromFilename(filename) {
    PHASE2_SIGNAL_BASE_TF = null;
    PHASE2_SIGNAL_BASE_MINUTES = 5;
    PHASE2_BASE_TF = null;

    if (!filename) return;
    const lower = filename.toUpperCase();
    let detectedTf = null;

    for (const tf of TF_LIST) {
        const token = "_" + tf.toUpperCase() + "_";
        if (lower.includes(token)) {
            detectedTf = tf;
            break;
        }
    }

    if (!detectedTf) {
        console.warn("[Phase2] Could not derive TF from filename:", filename);
        return;
    }

    PHASE2_SIGNAL_BASE_TF = detectedTf;
    const mins = tfToMinutes(detectedTf);
    if (mins != null) {
        PHASE2_SIGNAL_BASE_MINUTES = mins;
    }
    console.log("[Phase2] Signal-Base-TF:", PHASE2_SIGNAL_BASE_TF, "(", mins, "min)");
}

function getPhase2BaseTfData() {
    if (!DATA || !DATA.timeframes) return null;
    if (PHASE2_BASE_TF && DATA.timeframes[PHASE2_BASE_TF]) {
        return DATA.timeframes[PHASE2_BASE_TF];
    }

    const tried = new Set();
    const order = [];
    if (PHASE2_SIGNAL_BASE_TF) order.push(PHASE2_SIGNAL_BASE_TF);
    order.push("M5", "M1", "M3", "M15", "H1");

    for (const tf of order) {
        if (tried.has(tf)) continue;
        tried.add(tf);
        const tfData = DATA.timeframes[tf];
        if (tfData && tfData.bars && tfData.bars.length) {
            PHASE2_BASE_TF = tf;
            return tfData;
        }
    }
    const keys = Object.keys(DATA.timeframes);
    for (const tf of keys) {
        if (tried.has(tf)) continue;
        const tfData = DATA.timeframes[tf];
        if (tfData && tfData.bars && tfData.bars.length) {
            PHASE2_BASE_TF = tf;
            return tfData;
        }
    }
    return null;
}

function buildPhase2BoxesFromRows(rows) {
    const boxes = [];
    rows.forEach((row, rowIndex) => {
        const direction = (row["direction"] || "").toLowerCase();
        const dateNy = row["date_ny"] || row["date"] || "";
        const hod_time = parseNyStringToMs(row["hod_time"]);
        const ll2_time = parseNyStringToMs(row["ll2_time"]);
        const lod_time = parseNyStringToMs(row["lod_time"]);
        const hh2_time = parseNyStringToMs(row["hh2_time"]);

        let topTs = NaN, bottomTs = NaN, signalTs = NaN;

        if (direction === "sell" && !Number.isNaN(hod_time) && !Number.isNaN(ll2_time)) {
            topTs = hod_time; bottomTs = ll2_time; signalTs = ll2_time;
        } else if (direction === "buy" && !Number.isNaN(lod_time) && !Number.isNaN(hh2_time)) {
            topTs = hh2_time; bottomTs = lod_time; signalTs = hh2_time;
        } else {
            return;
        }

        boxes.push({
            direction, topTs, bottomTs, signalTs, dateNy, setupIndex: rowIndex
        });
    });
    boxes.sort((a, b) => a.topTs - b.topTs);
    return boxes;
}

function buildPhase3TradesFromRows(rows) {
    const trades = [];
    for (const row of rows) {
        const direction = (row["direction"] || "").toLowerCase();
        const dateNy = row["date_ny"] || row["date"] || "";
        const symbol = row["symbol"] || "";
        const scenarioId = row["scenario_id"] || "";
        const exitMode = row["exit_mode"] || "";
        const missReason = row["miss_reason"] || "";
        const filledRaw = (row["filled"] || "").toLowerCase();
        const filled = (filledRaw === "true" || filledRaw === "1" || filledRaw === "yes");

        let setupIndex = NaN;
        if (row["setup_index"] !== undefined && row["setup_index"] !== "") {
            const tmp = parseInt(row["setup_index"], 10);
            if (!Number.isNaN(tmp)) setupIndex = tmp;
        }

        const entryTsRaw = parseNyStringToMs(row["entry_idx"]);
        const exitTsRaw = parseNyStringToMs(row["exit_idx"]);
        const hasEntryTs = !Number.isNaN(entryTsRaw);
        const hasExitTs = !Number.isNaN(exitTsRaw);

        const entryPrice = pickNumberField(row, ["entry_price", "entry", "entry_px", "entry_close"]);
        const slPrice = pickNumberField(row, ["sl_price", "sl", "stop_price", "stop"]);
        const tpPrice = pickNumberField(row, ["tp_price", "tp", "target_price", "target"]);
        const exitPrice = pickNumberField(row, ["exit_price", "exit", "exit_px", "exit_close"]);

        let resultR = NaN;
        if (row["result_R"] !== undefined && row["result_R"] !== "") {
            const tmpR = parseFloat(String(row["result_R"]).replace(",", "."));
            if (!Number.isNaN(tmpR)) resultR = tmpR;
        }

        if (filled && (!hasEntryTs || !hasExitTs)) continue;

        let entryWindowEndTs = null;
        if (dateNy) {
            const ts = parseNyStringToMs(`${dateNy} 12:00:00`);
            if (!Number.isNaN(ts)) entryWindowEndTs = ts;
        }

        trades.push({
            direction, symbol, dateNy, scenarioId, exitMode, missReason,
            setupIndex: Number.isNaN(setupIndex) ? null : setupIndex,
            filled,
            entryTs: hasEntryTs ? entryTsRaw : null,
            exitTs: hasExitTs ? exitTsRaw : null,
            entryWindowEndTs,
            entryPrice: Number.isNaN(entryPrice) ? NaN : entryPrice,
            slPrice: Number.isNaN(slPrice) ? NaN : slPrice,
            tpPrice: Number.isNaN(tpPrice) ? NaN : tpPrice,
            exitPrice: Number.isNaN(exitPrice) ? NaN : exitPrice,
            resultR: Number.isNaN(resultR) ? null : resultR
        });
    }
    trades.sort((a, b) => {
        const ta = (a.entryTs != null ? a.entryTs : a.entryWindowEndTs) ?? 0;
        const tb = (b.entryTs != null ? b.entryTs : b.entryWindowEndTs) ?? 0;
        return ta - tb;
    });
    return trades;
}

function findPhase2BoxForTrade(trade) {
    if (!PHASE2_BOXES || !PHASE2_BOXES.length) return null;
    if (trade.setupIndex != null) {
        const byIdx = PHASE2_BOXES.find(b => b.setupIndex === trade.setupIndex);
        if (byIdx) return byIdx;
    }
    if (trade.dateNy) {
        const matches = PHASE2_BOXES.filter(b => b.dateNy === trade.dateNy && b.direction === trade.direction);
        if (matches.length >= 1) return matches[0];
    }
    return null;
}

// --- Setup List Construction ---

function buildSetupLabel(direction, signalTs, dateNy, achievedR, isMissed, isBreakeven) {
    const dirBase = (direction === "buy") ? "BUY" : "SELL";
    const dirCol = (dirBase + NBSP.repeat(4)).slice(0, 4);

    let datePart = "??.??.?? ??:??";
    if (signalTs != null && Number.isFinite(signalTs)) {
        const dt = new Date(signalTs);
        const dd = String(dt.getUTCDate()).padStart(2, "0");
        const mm = String(dt.getUTCMonth() + 1).padStart(2, "0");
        const yy = String(dt.getUTCFullYear()).slice(-2);
        const hh = String(dt.getUTCHours()).padStart(2, "0");
        const mi = String(dt.getUTCMinutes()).padStart(2, "0");
        datePart = `${dd}.${mm}.${yy} ${hh}:${mi}`;
    } else if (dateNy) {
        const parts = dateNy.split("-");
        if (parts.length === 3) {
            const yy = parts[0].slice(-2);
            const mm = parts[1];
            const dd = parts[2];
            datePart = `${dd}.${mm}.${yy} 00:00`;
        }
    }

    let rStr;
    if (isMissed) {
        rStr = NBSP + NBSP + "miss";
    } else {
        let rVal = achievedR;
        if (!Number.isFinite(rVal)) rVal = 0;
        const sign = (rVal >= 0 ? "+" : "");
        rStr = `${sign}${rVal.toFixed(2)}R`;
    }

    if (rStr.length < 6) {
        rStr = NBSP.repeat(6 - rStr.length) + rStr;
    }

    const gapDirDate = NBSP.repeat(3);
    const gapDateR   = NBSP.repeat(4);
    return `${dirCol}${gapDirDate}${datePart}${gapDateR}${rStr}`;
}

function rebuildSetupsList() {
    SETUPS = [];
    SETUP_BY_ID = {};

    if (!PHASE3_TRADES || !PHASE3_TRADES.length || !PHASE2_BOXES || !PHASE2_BOXES.length) {
        if (typeof renderSetupDropdown === "function") renderSetupDropdown();
        return;
    }

    let idCounter = 0;
    for (const tr of PHASE3_TRADES) {
        const box = findPhase2BoxForTrade(tr);
        if (!box || !Number.isFinite(box.signalTs)) continue;

        const direction = tr.direction || box.direction || "buy";
        const signalTs = box.signalTs;
        const dateNy = tr.dateNy || box.dateNy || "";
        const rawR = (typeof tr.resultR === "number" && !Number.isNaN(tr.resultR)) ? tr.resultR : 0;
        const isMissed = !tr.filled;
        const isBreakeven = tr.filled && Math.abs(rawR) < 1e-6;

        if (isMissed && !SHOW_MISSES) continue;

        const achievedR = rawR;
        const label = buildSetupLabel(direction, signalTs, dateNy, achievedR, isMissed, isBreakeven);

        SETUPS.push({
            id: idCounter++,
            direction, signalTs, dateNy, achievedR, isMissed, isBreakeven,
            boxRef: box, tradeRef: tr, label
        });
    }

    if (typeof renderSetupDropdown === "function") renderSetupDropdown();
}

function getSortedSetups() {
    const list = SETUPS.slice();
    list.sort(function (a, b) {
        if (SETUP_SORT_MODE === "time_asc") return (a.signalTs || 0) - (b.signalTs || 0);
        if (SETUP_SORT_MODE === "time_desc") return (b.signalTs || 0) - (a.signalTs || 0);
        if (SETUP_SORT_MODE === "dir_long_short") {
            if (a.direction !== b.direction) return (a.direction === "buy") ? -1 : 1;
            return (b.signalTs || 0) - (a.signalTs || 0);
        }
        if (SETUP_SORT_MODE === "dir_short_long") {
            if (a.direction !== b.direction) return (a.direction === "sell") ? -1 : 1;
            return (b.signalTs || 0) - (a.signalTs || 0);
        }
        if (SETUP_SORT_MODE === "r_desc") {
            const am = !!a.isMissed, bm = !!b.isMissed;
            if (am !== bm) return am ? 1 : -1;
            const ra = Number.isFinite(a.achievedR) ? a.achievedR : 0;
            const rb = Number.isFinite(b.achievedR) ? b.achievedR : 0;
            if (rb !== ra) return rb - ra;
            return (a.signalTs || 0) - (b.signalTs || 0);
        }
        if (SETUP_SORT_MODE === "r_asc") {
            const am = !!a.isMissed, bm = !!b.isMissed;
            if (am !== bm) return am ? 1 : -1;
            const ra = Number.isFinite(a.achievedR) ? a.achievedR : 0;
            const rb = Number.isFinite(b.achievedR) ? b.achievedR : 0;
            if (ra !== rb) return ra - rb;
            return (a.signalTs || 0) - (b.signalTs || 0);
        }
        return (a.signalTs || 0) - (b.signalTs || 0);
    });
    return list;
}

// --- Async File Loaders ---

async function scanPhaseFiles() {
    try {
        const res = await fetch(DATA_DIR_URL, { cache: "no-store" });
        if (!res.ok) {
            console.warn("Phase file scan failed:", res.status);
            return;
        }
        const html = await res.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, "text/html");
        const links = Array.from(doc.querySelectorAll("a[href]"));
        const files = links.map(a => a.getAttribute("href")).filter(href => href && !href.endsWith("/"));

        const phase2 = files.filter(name => /_setups_.*\.csv$/i.test(name) || name.endsWith("_setups.csv")).sort();
        const phase3 = files.filter(name => /_trades_.*\.csv$/i.test(name)).sort();

        if (typeof updatePhaseDropdowns === "function") updatePhaseDropdowns(phase2, phase3);
    } catch (e) {
        console.warn("Phase file scan error:", e);
    }
}

async function loadPhase2File(filename) {
    let changed = false;
    if (!filename) {
        if (PHASE2_BOXES.length || lastPhase2File !== null || lastPhase2Text !== null) {
            PHASE2_BOXES = []; lastPhase2File = null; lastPhase2Text = null; changed = true;
        }
        updatePhase2SignalBaseFromFilename(null);
        return changed;
    }
    updatePhase2SignalBaseFromFilename(filename);
    const url = DATA_DIR_URL + filename;
    try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) {
            console.warn("[Phase2] Could not load file:", url, res.status);
            if (PHASE2_BOXES.length || lastPhase2File !== filename || lastPhase2Text !== null) {
                PHASE2_BOXES = []; lastPhase2File = filename; lastPhase2Text = null; changed = true;
            }
            return changed;
        }
        const text = await res.text();
        if (lastPhase2File === filename && lastPhase2Text === text) return false;
        const rows = parseCsvToObjects(text);
        PHASE2_BOXES = buildPhase2BoxesFromRows(rows);
        lastPhase2File = filename; lastPhase2Text = text; changed = true;
    } catch (e) {
        console.warn("[Phase2] Error loading:", url, e);
        if (PHASE2_BOXES.length || lastPhase2File !== filename || lastPhase2Text !== null) {
            PHASE2_BOXES = []; lastPhase2File = filename; lastPhase2Text = null; changed = true;
        }
    }
    return changed;
}

async function loadPhase3File(filename) {
    let changed = false;
    if (!filename) {
        if (PHASE3_TRADES.length || lastPhase3File !== null || lastPhase3Text !== null) {
            PHASE3_TRADES = []; lastPhase3File = null; lastPhase3Text = null; changed = true;
        }
        return changed;
    }
    const url = DATA_DIR_URL + filename;
    try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) {
            console.warn("[Phase3] Could not load file:", url, res.status);
            if (PHASE3_TRADES.length || lastPhase3File !== filename || lastPhase3Text !== null) {
                PHASE3_TRADES = []; lastPhase3File = filename; lastPhase3Text = null; changed = true;
            }
            return changed;
        }
        const text = await res.text();
        if (lastPhase3File === filename && lastPhase3Text === text) return false;
        const rows = parseCsvToObjects(text);
        PHASE3_TRADES = buildPhase3TradesFromRows(rows);
        lastPhase3File = filename; lastPhase3Text = text; changed = true;
    } catch (e) {
        console.warn("[Phase3] Error loading:", url, e);
        if (PHASE3_TRADES.length || lastPhase3File !== filename || lastPhase3Text !== null) {
            PHASE3_TRADES = []; lastPhase3File = filename; lastPhase3Text = null; changed = true;
        }
    }
    return changed;
}

function startPhaseScanLoop() {
    if (phaseScanTimer) {
        clearInterval(phaseScanTimer);
        phaseScanTimer = null;
    }
    (async () => {
        await scanPhaseFiles();
        const p2Changed = await loadPhase2File(phase2File);
        const p3Changed = await loadPhase3File(phase3File);
        if (p2Changed || p3Changed) {
            if (typeof rerenderCurrentViewWithPhases === "function") rerenderCurrentViewWithPhases();
            rebuildSetupsList();
        }
    })();
    phaseScanTimer = setInterval(async () => {
        await scanPhaseFiles();
        const p2Changed = await loadPhase2File(phase2File);
        const p3Changed = await loadPhase3File(phase3File);
        if (p2Changed || p3Changed) {
            if (typeof rerenderCurrentViewWithPhases === "function") rerenderCurrentViewWithPhases();
            rebuildSetupsList();
        }
    }, PHASE_FILE_SCAN_INTERVAL_MS);
}