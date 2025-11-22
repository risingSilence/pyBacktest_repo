// chart_renderer.js

// --- Chart Construction ---

function buildFigureForState(tf, tfData, state, yRange, autoY, chartPixelWidth, pane) {
    const { windowStart, windowEnd, visibleStartIdx, visibleEndIdx } = state;
    if (windowEnd < windowStart) {
        return {
            fig: { data: [], layout: { title: `${tf} – no data`, plot_bgcolor: BACKGROUND_COLOR, paper_bgcolor: BACKGROUND_COLOR }, config: PLOT_CONFIG },
            visibleTimeRange: null, usedYRange: yRange
        };
    }

    // 1. Daten Slicing
    const windowBars = sliceBarsForRange(tfData, windowStart, windowEnd);
    const visibleBarsArr = sliceBarsForRange(tfData, visibleStartIdx, visibleEndIdx);
    const x = [], open = [], high = [], low = [], close = [], customdata = [];
    
    // 2. Y-Range Berechnung
    let yMin = (yRange && !autoY) ? yRange[0] : Number.POSITIVE_INFINITY;
    let yMax = (yRange && !autoY) ? yRange[1] : Number.NEGATIVE_INFINITY;

    for (const bar of windowBars) {
        x.push(bar.i); open.push(bar.o); high.push(bar.h); low.push(bar.l); close.push(bar.c);
        const ts = new Date(bar.ts);
        const wdIdx = ts.getUTCDay();
        const wdNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
        const monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
        const label = `${wdNames[wdIdx]} ${String(ts.getUTCDate()).padStart(2,"0")} ${monthNames[ts.getUTCMonth()]} '${String(ts.getUTCFullYear()).slice(-2)} ${String(ts.getUTCHours()).padStart(2,"0")}:${String(ts.getUTCMinutes()).padStart(2,"0")}`;
        customdata.push({ label: label, ts: bar.ts });
    }

    if (autoY || !yRange) {
        for (const bar of visibleBarsArr) { if (bar.l < yMin) yMin = bar.l; if (bar.h > yMax) yMax = bar.h; }
        if (!Number.isFinite(yMin) || !Number.isFinite(yMax)) { yMin = Number.POSITIVE_INFINITY; yMax = Number.NEGATIVE_INFINITY; for (const bar of windowBars) { if (bar.l < yMin) yMin = bar.l; if (bar.h > yMax) yMax = bar.h; } }
    }

    const viewStart = (state.viewStart != null) ? state.viewStart : (visibleStartIdx - 0.5);
    const viewEnd = (state.viewEnd != null) ? state.viewEnd : (visibleEndIdx + 0.5);
    const xRange = [viewStart, viewEnd];
    const finalYRange = [yMin, yMax];

    let visibleTimeRange = null;
    if (visibleBarsArr.length > 0) visibleTimeRange = [visibleBarsArr[0].t, visibleBarsArr[visibleBarsArr.length - 1].t];

    // 3. Ticks berechnen (via view_engine.js)
    const tickInfo = computeTimeTicks(tf, tfData, state, chartPixelWidth);
    // 4. Tick Shapes bauen (via trace_builder.js)
    const shapes = buildTickShapes(tickInfo);

    // 5. Haupt-Price Trace bauen (via trace_builder.js)
    const priceTrace = buildPriceTrace(x, open, high, low, close, customdata);

    // 6. Alle Traces zusammenfügen
    const allTraces = []
        .concat(buildSessionTraces(tf, tfData, state, windowBars, visibleBarsArr))
        .concat(buildPhase2Traces(tf, tfData, windowBars, windowStart, windowEnd, pane))
        .concat(buildPhase3Traces(tf, tfData, windowBars, windowStart, windowEnd, pane))
        .concat([priceTrace]);

    // 7. Layout zusammenbauen (via trace_builder.js)
    const title = `${DATA.symbol} – ${tf} (NY)`;
    const layout = buildChartLayout(title, xRange, finalYRange, tickInfo, shapes, pane, axisMode);

    return { fig: { data: allTraces, layout, config: PLOT_CONFIG }, visibleTimeRange, usedYRange: finalYRange };
}

function applyStateAndRenderForPane(pane, tf, state, options) {
    let tfData;
    if (pane === "left") {
        if (HTF_SNAPSHOT_ACTIVE && HTF_SNAPSHOT_TFDATA && HTF_SNAPSHOT_INFO && HTF_SNAPSHOT_INFO.tf === tf) tfData = HTF_SNAPSHOT_TFDATA;
        else if (HTF_FOLLOW_ACTIVE && HTF_FOLLOW_TFDATA && HTF_FOLLOW_INFO && HTF_FOLLOW_INFO.tf === tf) tfData = HTF_FOLLOW_TFDATA;
        else tfData = DATA.timeframes[tf];
    } else {
        tfData = DATA.timeframes[tf];
    }
    if (!tfData) return;

    const regime = getRegime(tf);
    const regStateAll = (pane === "left") ? REGIME_STATE_LEFT : REGIME_STATE;
    const regState = regStateAll[regime];
    const autoY = !!options.autoY;
    let yRange = null;
    if (options.yRangeOverride) yRange = options.yRangeOverride.slice();
    else if (regState.yRange && !autoY) yRange = regState.yRange.slice();

    const chartId = (pane === "left") ? "htf-chart" : "m1-chart";
    let chartPixelWidth = null;
    const chartEl = document.getElementById(chartId);
    if (chartEl) {
        const rect = chartEl.getBoundingClientRect();
        chartPixelWidth = (rect && rect.width) ? rect.width : (chartEl.clientWidth || chartEl.offsetWidth || null);
    }

    const { fig, visibleTimeRange, usedYRange } = buildFigureForState(tf, tfData, state, yRange, autoY, chartPixelWidth, pane);

    if (pane === "left") TF_STATE_LEFT[tf] = { ...state };
    else TF_STATE[tf] = { ...state };

    if (visibleTimeRange) { regState.timeRange = visibleTimeRange; regState.anchorTime = visibleTimeRange[1]; }
    if (usedYRange) regState.yRange = usedYRange.slice();
    regState.visibleBarsHint = state.visibleBars;
    regState.lastTf = tf;
    if (autoY && !regState.initialized) regState.initialized = true;

    isRelayoutFromCode = true;
    Plotly.react(chartId, fig.data, fig.layout, fig.config).then(() => { isRelayoutFromCode = false; savePersistentState(); }).catch((e) => { isRelayoutFromCode = false; console.warn("Plotly.react error:", e); });
}

function applyStateAndRender(tf, state, options) { applyStateAndRenderForPane("right", tf, state, options); }
function applyStateAndRenderLeft(tf, state, options) { applyStateAndRenderForPane("left", tf, state, options); }

function initDefaultViewRight() {
    const tfData = DATA.timeframes[currentTf];
    if (!tfData) return;
    const state = computeWindowForTfRightAnchored(tfData, DEFAULT_VISIBLE_BARS, tfData.maxIdx);
    applyStateAndRender(currentTf, state, { autoY: true });
}

function initDefaultViewLeft() {
    if (!DATA || !DATA.timeframes) return;
    if (!DATA.timeframes[currentTfLeft]) {
        const available = Object.keys(DATA.timeframes);
        if (!available.length) return;
        currentTfLeft = available[0];
    }
    const tfData = DATA.timeframes[currentTfLeft];
    const state = computeWindowForTfRightAnchored(tfData, DEFAULT_VISIBLE_BARS, tfData.maxIdx);
    applyStateAndRenderLeft(currentTfLeft, state, { autoY: true });
}

function reanchorChartToRightEdgeForPane(pane, widthFactor) {
    if (!DATA || !DATA.timeframes) return;
    const tf = pane === "left" ? currentTfLeft : currentTf;
    const tfData = DATA.timeframes[tf];
    if (!tfData) return;

    let state = pane === "left" ? TF_STATE_LEFT[tf] : TF_STATE[tf];
    let preserveGap = 0;
    if (state && state.viewEnd != null && state.visibleEndIdx != null) {
        preserveGap = state.viewEnd - (state.visibleEndIdx + 0.5);
    }

    if (!state) state = computeWindowForTfRightAnchored(tfData, DEFAULT_VISIBLE_BARS, tfData.maxIdx);
    
    let anchorIdx = state.visibleEndIdx;
    if (anchorIdx == null || !isFinite(anchorIdx)) anchorIdx = state.visibleStartIdx;
    if (anchorIdx == null || !isFinite(anchorIdx)) anchorIdx = tfData.maxIdx;

    let visibleBars = state.visibleBars || DEFAULT_VISIBLE_BARS;
    if (widthFactor && isFinite(widthFactor) && widthFactor > 0) {
        const oldBars = visibleBars;
        visibleBars = Math.round(visibleBars * widthFactor);
        if (visibleBars < 10) visibleBars = 10;
        console.log(`[Reanchor] ${pane}: Width x${widthFactor.toFixed(2)} -> Bars ${oldBars} to ${visibleBars}`);
    }

    const newState = computeWindowForTfRightAnchored(tfData, visibleBars, anchorIdx);
    if (isFinite(preserveGap)) {
        newState.viewEnd = (newState.visibleEndIdx + 0.5) + preserveGap;
        if (newState.viewEnd <= newState.viewStart) {
            const range = Math.max(1, newState.visibleEndIdx - newState.visibleStartIdx);
            newState.viewEnd = (newState.visibleEndIdx + 0.5) + (range * 0.1);
        }
    }

    const regime = getRegime(tf);
    const regStateAll = pane === "left" ? REGIME_STATE_LEFT : REGIME_STATE;
    const regState = regStateAll[regime] || {};

    if (pane === "left") applyStateAndRenderLeft(tf, newState, { autoY: false, yRangeOverride: regState.yRange });
    else applyStateAndRender(tf, newState, { autoY: false, yRangeOverride: regState.yRange });
}

function reanchorRightChartToRightEdge(widthFactor) { reanchorChartToRightEdgeForPane("right", widthFactor); }

function rerenderCurrentViewWithPhases() {
    if (!DATA || !DATA.timeframes) return;
    if (DATA.timeframes[currentTf]) {
        const tfDataR = DATA.timeframes[currentTf];
        let stateR = TF_STATE[currentTf];
        if (!stateR) stateR = computeWindowForTf(tfDataR, DEFAULT_VISIBLE_BARS, tfDataR.maxIdx);
        const regimeR = getRegime(currentTf);
        const regStateR = REGIME_STATE[regimeR] || {};
        applyStateAndRender(currentTf, stateR, { autoY: false, yRangeOverride: regStateR.yRange });
    }
    if (VIEW_MODE === VIEW_MODE_SPLIT && DATA.timeframes[currentTfLeft]) {
        const tfDataL = DATA.timeframes[currentTfLeft];
        let stateL = TF_STATE_LEFT[currentTfLeft];
        if (!stateL) stateL = computeWindowForTf(tfDataL, DEFAULT_VISIBLE_BARS, tfDataL.maxIdx);
        const regimeL = getRegime(currentTfLeft, "left");
        const regStateL = REGIME_STATE_LEFT[regimeL] || {};
        applyStateAndRenderLeft(currentTfLeft, stateL, { autoY: false, yRangeOverride: regStateL.yRange });
    }
}

// --- HTF Snapshot & Follow Logic ---

function buildHtfSnapshotData(tfName, tfDataOriginal, m1Data, snapshotTimeMs) {
    if (!tfDataOriginal || !tfDataOriginal.bars || !tfDataOriginal.bars.length) return null;
    if (!m1Data || !m1Data.bars || !m1Data.bars.length) return null;
    if (!isFinite(snapshotTimeMs)) return null;

    let pos = findPosLEByTs(tfDataOriginal, snapshotTimeMs);
    if (pos === null) return null;

    const barsOrig = tfDataOriginal.bars;
    const htfBar = barsOrig[pos];
    const htfOpenTs = htfBar.ts;
    const m1BarsAll = m1Data.bars;
    const startTs = htfOpenTs;
    const endTs = snapshotTimeMs;

    let posStart = findPosGEByTs(m1Data, startTs);
    let posEnd = findPosLEByTs(m1Data, endTs - 1);

    if (posStart === null || posEnd === null || posEnd < posStart) {
        const snapshotBarsFallback = barsOrig.slice(0, pos + 1).map(b => ({ ...b }));
        const lastFallback = snapshotBarsFallback[snapshotBarsFallback.length - 1];
        return { htfSnapshotData: { ...tfDataOriginal, bars: snapshotBarsFallback, maxIdx: lastFallback.i }, htfBarIndex: lastFallback.i };
    }

    let o = m1BarsAll[posStart].o, h = m1BarsAll[posStart].h, l = m1BarsAll[posStart].l, c = m1BarsAll[posEnd].c;
    for (let i = posStart; i <= posEnd; i++) {
        const b = m1BarsAll[i];
        if (b.h > h) h = b.h;
        if (b.l < l) l = b.l;
    }

    const snapshotBars = barsOrig.slice(0, pos + 1).map(b => ({ ...b }));
    const last = snapshotBars[snapshotBars.length - 1];
    last.o = o; last.h = h; last.l = l; last.c = c;

    return { htfSnapshotData: { ...tfDataOriginal, bars: snapshotBars, maxIdx: last.i }, htfBarIndex: last.i };
}

function updateHtfFollowFromLtf(stateRight) {
    if (!DATA || !DATA.timeframes || VIEW_MODE !== VIEW_MODE_SPLIT || HTF_BEHAVIOR === HTF_BEHAVIOR_INDEPENDENT || !stateRight) return;
    const tfRight = currentTf, tfLeft = currentTfLeft;
    const tfDataRight = DATA.timeframes[tfRight], tfDataLeftOriginal = DATA.timeframes[tfLeft], m1Data = DATA.timeframes["M1"];
    if (!tfDataRight || !tfDataLeftOriginal || !m1Data || stateRight.visibleEndIdx == null) return;

    let lastIdx = Math.round(stateRight.visibleEndIdx);
    lastIdx = Math.max(tfDataRight.minIdx, Math.min(tfDataRight.maxIdx, lastIdx));
    const posRight = lastIdx - tfDataRight.minIdx;
    if (posRight < 0 || posRight >= tfDataRight.bars.length) return;

    const lastBarRight = tfDataRight.bars[posRight];
    if (!lastBarRight) return;
    const ltfDurMs = timeframeToMs(tfRight);
    if (!ltfDurMs) return;

    const snapshotTime = lastBarRight.ts + ltfDurMs;
    const snapshot = buildHtfSnapshotData(tfLeft, tfDataLeftOriginal, m1Data, snapshotTime);
    if (!snapshot) return;

    const { htfSnapshotData, htfBarIndex } = snapshot;
    const minIdx = htfSnapshotData.minIdx, maxIdx = htfSnapshotData.maxIdx;
    const prevState = TF_STATE_LEFT[tfLeft];

    let visibleBars = (prevState && prevState.visibleBars > 0) ? prevState.visibleBars : (stateRight.visibleBars > 0 ? stateRight.visibleBars : DEFAULT_VISIBLE_BARS);
    visibleBars = Math.max(1, Math.round(visibleBars));
    const targetGapBars = Math.max(1, Math.round(visibleBars * 0.1));
    let currentGapBars = (prevState && prevState.viewEnd != null) ? (prevState.viewEnd - (htfBarIndex + 0.5)) : 0;
    if (!isFinite(currentGapBars) || currentGapBars < 0) currentGapBars = 0;

    const regimeLeft = getRegime(tfLeft, "left");
    const regStateLeft = REGIME_STATE_LEFT[regimeLeft] || {};

    function renderWith(newState) {
        HTF_FOLLOW_ACTIVE = true; HTF_FOLLOW_TFDATA = htfSnapshotData; HTF_FOLLOW_INFO = { tf: tfLeft, snapshotTime, htfBarIndex };
        applyStateAndRenderLeft(tfLeft, newState, { autoY: false, yRangeOverride: regStateLeft.yRange });
    }

    if (prevState && currentGapBars >= targetGapBars) {
        let visStart = (prevState.visibleStartIdx != null) ? prevState.visibleStartIdx : (htfBarIndex - (visibleBars - 1));
        let visEnd = (prevState.visibleEndIdx != null) ? prevState.visibleEndIdx : htfBarIndex;
        visStart = Math.max(minIdx, Math.min(visStart, maxIdx));
        visEnd = Math.max(minIdx, Math.min(visEnd, maxIdx));
        if (visEnd < visStart) { visStart = Math.max(minIdx, htfBarIndex - (visibleBars - 1)); visEnd = Math.min(maxIdx, htfBarIndex); }
        
        visibleBars = Math.max(1, Math.round(visEnd - visStart + 1));
        let newState = computeWindowForTf(htfSnapshotData, visibleBars, 0.5 * (visStart + visEnd));
        newState.visibleStartIdx = visStart; newState.visibleEndIdx = visEnd; newState.visibleBars = visibleBars;
        newState.viewStart = (prevState.viewStart != null) ? prevState.viewStart : (visStart - 0.5);
        newState.viewEnd = (prevState.viewEnd != null) ? prevState.viewEnd : (visEnd + 0.5 + targetGapBars);
        renderWith(newState);
        return;
    }

    let visibleEndIdx = htfBarIndex;
    let visibleStartIdx = visibleEndIdx - (visibleBars - 1);
    if (visibleStartIdx < minIdx) { visibleStartIdx = minIdx; visibleEndIdx = visibleStartIdx + (visibleBars - 1); if (visibleEndIdx > maxIdx) visibleEndIdx = maxIdx; }
    if (visibleEndIdx > maxIdx) { visibleEndIdx = maxIdx; visibleStartIdx = visibleEndIdx - (visibleBars - 1); if (visibleStartIdx < minIdx) visibleStartIdx = minIdx; }
    
    visibleBars = Math.max(1, visibleEndIdx - visibleStartIdx + 1);
    let newState = computeWindowForTf(htfSnapshotData, visibleBars, 0.5 * (visibleStartIdx + visibleEndIdx));
    newState.visibleStartIdx = visibleStartIdx; newState.visibleEndIdx = visibleEndIdx; newState.visibleBars = visibleBars;
    
    let prevGapBars = 0;
    if (prevState && prevState.viewEnd != null && prevState.visibleEndIdx != null) {
        const raw = prevState.viewEnd - (prevState.visibleEndIdx + 0.5);
        if (isFinite(raw) && raw > 0) prevGapBars = raw;
    }
    const gapBars = Math.max(targetGapBars, prevGapBars);
    newState.viewStart = visibleStartIdx - 0.5; newState.viewEnd = visibleEndIdx + 0.5 + gapBars;
    renderWith(newState);
}

function applyHtfSnapshotForSetup(setup, options) {
    const opts = options || {};
    let shouldPreserveView = !!opts.preserveView;
    const isAutoPan = !!opts.isAutoPan;

    if (HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_STRICT) return;
    if (!DATA || !DATA.timeframes || !setup) { clearHtfSnapshot(); return; }

    if (PHASE2_BOXES && PHASE2_BOXES.length) PHASE2_BOXES.forEach(b => b.isSnapshotActive = false);
    if (setup.boxRef) setup.boxRef.isSnapshotActive = true;

    if (VIEW_MODE !== VIEW_MODE_SPLIT) { clearHtfSnapshot(); return; }

    const tfLeft = currentTfLeft;
    const tfDataLeft = DATA.timeframes[tfLeft], m1Data = DATA.timeframes["M1"], tfDataLtf = DATA.timeframes[currentTf];
    if (!tfDataLeft || !m1Data || !tfDataLtf) { clearHtfSnapshot(); return; }

    const ltfDurationMs = timeframeToMs(currentTf);
    if (!ltfDurationMs || !isFinite(setup.signalTs)) { clearHtfSnapshot(); return; }

    const snapshotTime = setup.signalTs + ltfDurationMs;
    const snapshot = buildHtfSnapshotData(tfLeft, tfDataLeft, m1Data, snapshotTime);
    if (!snapshot) { clearHtfSnapshot(); return; }

    const { htfSnapshotData, htfBarIndex } = snapshot;
    let ltfSignalIdx = null;
    const ltfPos = findPosLEByTs(tfDataLtf, setup.signalTs);
    if (ltfPos !== null) ltfSignalIdx = tfDataLtf.bars[ltfPos].i;

    HTF_SNAPSHOT_ACTIVE = true;
    HTF_SNAPSHOT_TFDATA = htfSnapshotData;
    HTF_SNAPSHOT_INFO = { tf: tfLeft, setupId: setup.id, signalTs: setup.signalTs, snapshotTime, htfBarIndex, ltfSignalIdx };

    const regimeLeft = getRegime(tfLeft, "left");
    const regStateLeft = REGIME_STATE_LEFT[regimeLeft] || {};

    if (!shouldPreserveView && isAutoPan) {
        const stateLeft = TF_STATE_LEFT[tfLeft];
        if (stateLeft && stateLeft.viewEnd != null && stateLeft.visibleStartIdx != null && stateLeft.visibleEndIdx != null) {
            const currentGap = stateLeft.viewEnd - (htfBarIndex + 0.5);
            const currentWidth = stateLeft.visibleEndIdx - stateLeft.visibleStartIdx;
            const minRequiredGap = Math.max(1, currentWidth * 0.1);
            if (currentGap >= minRequiredGap) shouldPreserveView = true;
        }
    }

    if (shouldPreserveView) {
        let stateLeft = TF_STATE_LEFT[tfLeft];
        if (stateLeft) {
            stateLeft = { ...stateLeft };
            const minIdx = htfSnapshotData.minIdx, maxIdx = htfSnapshotData.maxIdx;
            if (typeof minIdx === "number" && typeof maxIdx === "number") {
                if (stateLeft.visibleStartIdx < minIdx) stateLeft.visibleStartIdx = minIdx;
                if (stateLeft.visibleEndIdx > maxIdx) stateLeft.visibleEndIdx = maxIdx;
                if (stateLeft.visibleEndIdx < stateLeft.visibleStartIdx) {
                    stateLeft.visibleStartIdx = Math.max(minIdx, maxIdx - DEFAULT_VISIBLE_BARS);
                    stateLeft.visibleEndIdx = maxIdx;
                }
                stateLeft.windowStart = Math.max(minIdx, stateLeft.visibleStartIdx - 100);
                stateLeft.windowEnd = Math.min(maxIdx, stateLeft.visibleEndIdx + 100);
            }
            applyStateAndRenderLeft(tfLeft, stateLeft, { autoY: false, yRangeOverride: regStateLeft.yRange });
            return;
        }
    }

    let stateLeft = TF_STATE_LEFT[tfLeft];
    let visibleBars = (stateLeft && isFinite(stateLeft.visibleBars) && stateLeft.visibleBars > 0) ? stateLeft.visibleBars : DEFAULT_VISIBLE_BARS;
    const newState = computeWindowForTfRightAnchored(htfSnapshotData, visibleBars, htfBarIndex);
    
    const span = Math.max(1, newState.visibleEndIdx - newState.visibleStartIdx + 1);
    const gapBars = Math.max(1, Math.round(span * 0.1));
    newState.viewStart = newState.visibleStartIdx - 0.5;
    newState.viewEnd = newState.visibleEndIdx + 0.5 + gapBars;

    let baseYRange = regStateLeft.yRange, newYRange = null;
    if (baseYRange && baseYRange.length === 2) {
        const height = baseYRange[1] - baseYRange[0];
        const lastBar = htfSnapshotData.bars.find(b => b.i === htfBarIndex) || htfSnapshotData.bars[htfSnapshotData.bars.length - 1];
        if (lastBar && height && height > 0) {
            const center = 0.5 * (lastBar.h + lastBar.l);
            if (isFinite(center)) newYRange = [center - height / 2, center + height / 2];
        }
    }
    applyStateAndRenderLeft(tfLeft, newState, { autoY: !newYRange, yRangeOverride: newYRange || baseYRange || null });
}

function clearHtfSnapshot(options) {
    const opts = options || {};
    const clearSetupSelect = !!opts.clearSetupSelect;
    if (PHASE2_BOXES && PHASE2_BOXES.length) PHASE2_BOXES.forEach(b => b.isSnapshotActive = false);
    HTF_SNAPSHOT_ACTIVE = false;
    HTF_SNAPSHOT_MAX_SIGNAL_TS = null;
    HTF_SNAPSHOT_TFDATA = null;
    HTF_SNAPSHOT_INFO = null;
    if (clearSetupSelect) {
        const setupSelectEl = document.getElementById("setup-select");
        if (setupSelectEl) setupSelectEl.value = "";
    }
}

// --- Relayout Logic ---

function autoSelectSetupForCurrentView(tfData, state, excludedSetupId) {
    if (!SETUPS || !SETUPS.length || !tfData || !tfData.bars || !tfData.bars.length || !state || state.visibleStartIdx == null || state.visibleEndIdx == null) return null;
    const vs = state.visibleStartIdx, ve = state.visibleEndIdx, viewCenter = 0.5 * (vs + ve);
    let bestSetup = null, bestCenter = null, bestScore = null;

    for (const setup of SETUPS) {
        if (excludedSetupId != null && setup.id === excludedSetupId) continue;
        const box = setup.boxRef; if (!box) continue;
        const info = getBoxVisibleCenterIndexInTf(tfData, box, vs, ve);
        if (!info) continue;
        const center = info.center;
        const score = Math.abs(center - viewCenter);
        if (bestSetup === null) { bestSetup = setup; bestCenter = center; bestScore = score; }
        else {
            if (score < bestScore - 1e-6) { bestSetup = setup; bestCenter = center; bestScore = score; }
            else if (Math.abs(score - bestScore) <= 1e-6) { if (center > bestCenter) { bestSetup = setup; bestCenter = center; bestScore = score; } }
        }
    }
    return bestSetup;
}

function getBoxVisibleCenterIndexInTf(tfData, box, visibleStartIdx, visibleEndIdx) {
    if (!tfData || !tfData.bars || !tfData.bars.length || !box) return null;
    const t1 = box.topTs, t2 = box.bottomTs;
    if (!Number.isFinite(t1) || !Number.isFinite(t2)) return null;
    const startTs = Math.min(t1, t2), endTs = Math.max(t1, t2);
    let effectiveEndTs = endTs;
    if (Number.isFinite(endTs) && PHASE2_SIGNAL_BASE_MINUTES > 1) effectiveEndTs = endTs + (PHASE2_SIGNAL_BASE_MINUTES - 1) * 60 * 1000;

    let posL = findPosLEByTs(tfData, startTs), posR = findPosLEByTs(tfData, effectiveEndTs);
    if (posL === null) posL = 0;
    if (posR === null) posR = tfData.bars.length - 1;
    if (posR < posL) { const tmp = posL; posL = posR; posR = tmp; }

    const idxL = tfData.bars[posL].i, idxR = tfData.bars[posR].i;
    const left = Math.max(idxL, visibleStartIdx), right = Math.min(idxR, visibleEndIdx);
    if (right < left) return null;
    return { idxL, idxR, left, right, center: 0.5 * (left + right) };
}

function focusOnSetup(setup) {
    if (!setup || !DATA || !DATA.timeframes || !DATA.timeframes[currentTf]) return;

    if (HTF_BEHAVIOR === HTF_BEHAVIOR_INDEPENDENT || HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_SNAP) {
        if (setup.signalTs != null && Number.isFinite(setup.signalTs)) {
            HTF_SNAPSHOT_MAX_SIGNAL_TS = setup.signalTs + PHASE2_SIGNAL_BASE_MINUTES * 60 * 1000;
        } else HTF_SNAPSHOT_MAX_SIGNAL_TS = null;
    } else HTF_SNAPSHOT_MAX_SIGNAL_TS = null;

    const tfData = DATA.timeframes[currentTf];
    const regime = getRegime(currentTf);
    const regState = REGIME_STATE[regime] || {};

    let anchorTs = null;
    if (setup.dateNy) anchorTs = parseNyStringToMs(`${setup.dateNy} 10:00:00`);
    else if (setup.signalTs != null && Number.isFinite(setup.signalTs)) anchorTs = setup.signalTs;

    let anchorPos = null;
    if (anchorTs != null && Number.isFinite(anchorTs)) {
        anchorPos = findPosLEByTs(tfData, anchorTs);
        if (anchorPos === null) anchorPos = findPosGEByTs(tfData, anchorTs);
    }
    if (anchorPos === null) anchorPos = tfData.bars.length - 1;
    const anchorIdx = tfData.bars[anchorPos].i;

    let state = TF_STATE[currentTf];
    if (!state) state = computeWindowForTf(tfData, DEFAULT_VISIBLE_BARS, tfData.maxIdx);
    const visibleBars = state.visibleBars || DEFAULT_VISIBLE_BARS;
    const newState = computeWindowForTf(tfData, visibleBars, anchorIdx);

    let yRange = regState.yRange;
    if (!yRange) {
        const tmp = buildFigureForState(currentTf, tfData, newState, null, true, "right");
        yRange = tmp.usedYRange;
    }
    if (!yRange || yRange.length !== 2) { applyStateAndRender(currentTf, newState, { autoY: true }); return; }

    let yMin = yRange[0], yMax = yRange[1], h = yMax - yMin;
    if (!(h > 0)) { applyStateAndRender(currentTf, newState, { autoY: true }); return; }

    const chartEl = document.getElementById("m1-chart");
    const rect = chartEl ? chartEl.getBoundingClientRect() : null;
    const plotHeight = (rect && rect.height) ? rect.height : 600;
    const pxOffset = 100;
    const pricePerPx = h / plotHeight;
    const delta = pricePerPx * pxOffset;

    let lod = Number.POSITIVE_INFINITY, hod = Number.NEGATIVE_INFINITY;
    const box = setup.boxRef;
    if (box && Number.isFinite(box.topTs) && Number.isFinite(box.bottomTs)) {
        const tMin = Math.min(box.topTs, box.bottomTs), tMax = Math.max(box.topTs, box.bottomTs);
        for (const bar of tfData.bars) {
            if (bar.ts < tMin) continue;
            if (bar.ts > tMax) break;
            if (bar.l < lod) lod = bar.l;
            if (bar.h > hod) hod = bar.h;
        }
    }
    if (!Number.isFinite(lod) || !Number.isFinite(hod)) {
        const targetKey = setup.dateNy;
        lod = Number.POSITIVE_INFINITY; hod = Number.NEGATIVE_INFINITY;
        if (targetKey) {
            for (const bar of tfData.bars) {
                const key = tradingDateKeyFromDate(new Date(bar.ts));
                if (key !== targetKey) continue;
                if (bar.l < lod) lod = bar.l;
                if (bar.h > hod) hod = bar.h;
            }
        }
    }

    let newYMin = yMin, newYMax = yMax;
    if (setup.direction === "buy" && lod < Number.POSITIVE_INFINITY) { newYMin = lod - delta; newYMax = newYMin + h; }
    else if (setup.direction === "sell" && hod > Number.NEGATIVE_INFINITY) { newYMax = hod + delta; newYMin = newYMax - h; }

    applyStateAndRender(currentTf, newState, { autoY: false, yRangeOverride: [newYMin, newYMax] });

    if (VIEW_MODE === VIEW_MODE_SPLIT && (HTF_BEHAVIOR === HTF_BEHAVIOR_INDEPENDENT || HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_SNAP)) {
        applyHtfSnapshotForSetup(setup);
    } else {
        clearHtfSnapshot();
    }
}

function handleRelayoutForPane(pane, ev) {
    if (isRelayoutFromCode || !DATA) return;
    const isLeft = (pane === "left");
    const tf = isLeft ? currentTfLeft : currentTf;
    let tfData = DATA.timeframes[tf];

    if (isLeft) {
        if (HTF_SNAPSHOT_ACTIVE && HTF_SNAPSHOT_TFDATA && HTF_SNAPSHOT_INFO && HTF_SNAPSHOT_INFO.tf === tf) tfData = HTF_SNAPSHOT_TFDATA;
        else if (HTF_FOLLOW_ACTIVE && HTF_FOLLOW_TFDATA && HTF_FOLLOW_INFO && HTF_FOLLOW_INFO.tf === tf) tfData = HTF_FOLLOW_TFDATA;
    }
    if (!tfData) return;

    const regime = getRegime(tf);
    const regStateAll = isLeft ? REGIME_STATE_LEFT : REGIME_STATE;
    const regState = regStateAll[regime];

    let hasX = false, hasY = false;
    let v0 = null, v1 = null, y0 = null, y1 = null;

    if (ev["xaxis.range[0]"] !== undefined && ev["xaxis.range[1]"] !== undefined) {
        v0 = parseFloat(ev["xaxis.range[0]"]); v1 = parseFloat(ev["xaxis.range[1]"]);
        if (isFinite(v0) && isFinite(v1)) hasX = true;
    }
    if (ev["yaxis.range[0]"] !== undefined && ev["yaxis.range[1]"] !== undefined) {
        y0 = parseFloat(ev["yaxis.range[0]"]); y1 = parseFloat(ev["yaxis.range[1]"]);
        if (isFinite(y0) && isFinite(y1)) hasY = true;
    }

    let state = isLeft ? TF_STATE_LEFT[tf] : TF_STATE[tf];
    if (!state) state = computeWindowForTf(tfData, DEFAULT_VISIBLE_BARS, null);
    let excludedSetupId = null;

    if (hasX) {
        const minIdx = tfData.minIdx, maxIdx = tfData.maxIdx;
        let viewStart = v0, viewEnd = v1;
        if (!isFinite(viewStart) || !isFinite(viewEnd)) { viewStart = state.viewStart != null ? state.viewStart : (minIdx - 0.5); viewEnd = state.viewEnd != null ? state.viewEnd : (maxIdx + 0.5); }

        const dataBandStart = minIdx - 0.5, dataBandEnd = maxIdx + 0.5;
        let span = Math.abs(viewEnd - viewStart); if (span < 1e-6) span = 1;

        if (viewStart > dataBandEnd) { viewEnd = dataBandEnd; viewStart = viewEnd - span; }
        else if (viewEnd < dataBandStart) { viewStart = dataBandStart; viewEnd = viewStart + span; }
        if (viewStart === viewEnd) viewEnd = viewStart + 1;

        const vLeft = Math.min(viewStart, viewEnd), vRight = Math.max(viewStart, viewEnd);
        let left = Math.max(vLeft, dataBandStart), right = Math.min(vRight, dataBandEnd);

        if (right < left) { state.viewStart = viewStart; state.viewEnd = viewEnd; }
        else {
            let visibleStartIdx = left + 0.5, visibleEndIdx = right - 0.5;
            if (visibleEndIdx < visibleStartIdx) { const tmp = visibleStartIdx; visibleStartIdx = visibleEndIdx; visibleEndIdx = tmp; }
            const approxVisibleBars = Math.max(1, Math.round(visibleEndIdx - visibleStartIdx + 1));
            const centerIdx = 0.5 * (visibleStartIdx + visibleEndIdx);
            let baseState = computeWindowForTf(tfData, approxVisibleBars, centerIdx);
            baseState.visibleStartIdx = visibleStartIdx; baseState.visibleEndIdx = visibleEndIdx;
            baseState.visibleBars = Math.max(1, visibleEndIdx - visibleStartIdx + 1);
            baseState.viewStart = viewStart; baseState.viewEnd = viewEnd;
            state = baseState;
        }
    }

    let yRange = regState.yRange;
    if (hasY) { yRange = [y0, y1]; regState.yRange = yRange.slice(); }

    if (yRange && state.visibleStartIdx != null && state.visibleEndIdx != null) {
        const correctedY = calculateVerticalCorrection(tfData, state.visibleStartIdx, state.visibleEndIdx, yRange);
        if (correctedY) { yRange = correctedY; regState.yRange = correctedY.slice(); }
    }

    if (isLeft) applyStateAndRenderLeft(tf, state, { autoY: false, yRangeOverride: yRange });
    else applyStateAndRender(tf, state, { autoY: false, yRangeOverride: yRange });

    // Snapshot Check
    if (!isLeft && HTF_SNAPSHOT_ACTIVE && HTF_SNAPSHOT_INFO && HTF_SNAPSHOT_INFO.signalTs != null && (HTF_BEHAVIOR === HTF_BEHAVIOR_INDEPENDENT || HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_SNAP)) {
        const vs = state.visibleStartIdx, ve = state.visibleEndIdx;
        let signalIdx = null;
        if (Number.isFinite(HTF_SNAPSHOT_INFO.signalTs)) {
            const posSignal = findPosLEByTs(tfData, HTF_SNAPSHOT_INFO.signalTs);
            if (posSignal !== null) signalIdx = tfData.bars[posSignal].i;
        }
        if (signalIdx != null && vs != null && ve != null && (signalIdx < vs || signalIdx > ve)) {
            excludedSetupId = HTF_SNAPSHOT_INFO.setupId;
            clearHtfSnapshot({ clearSetupSelect: true });
            if (DATA && DATA.timeframes && DATA.timeframes[currentTfLeft]) {
                const tfDataLeft = DATA.timeframes[currentTfLeft];
                let stateLeft = TF_STATE_LEFT[currentTfLeft];
                if (!stateLeft) stateLeft = computeWindowForTfRightAnchored(tfDataLeft, DEFAULT_VISIBLE_BARS, tfDataLeft.maxIdx);
                else {
                    const { visibleStartIdx, visibleEndIdx, viewStart, viewEnd } = stateLeft;
                    if (visibleStartIdx != null && visibleEndIdx != null) {
                        const visibleBars = Math.max(1, Math.round(visibleEndIdx - visibleStartIdx + 1));
                        const recomputed = computeWindowForTf(tfDataLeft, visibleBars, 0.5 * (visibleStartIdx + visibleEndIdx));
                        if (viewStart != null && viewEnd != null) { recomputed.viewStart = viewStart; recomputed.viewEnd = viewEnd; }
                        stateLeft = recomputed;
                    } else stateLeft = computeWindowForTfRightAnchored(tfDataLeft, DEFAULT_VISIBLE_BARS, tfDataLeft.maxIdx);
                }
                const regimeLeft = getRegime(currentTfLeft, "left");
                const regStateLeft = REGIME_STATE_LEFT[regimeLeft] || {};
                applyStateAndRenderLeft(currentTfLeft, stateLeft, { autoY: false, yRangeOverride: regStateLeft.yRange });
            }
        }
    }

    if (!isLeft && VIEW_MODE === VIEW_MODE_SPLIT && (HTF_BEHAVIOR === HTF_BEHAVIOR_INDEPENDENT || HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_SNAP)) {
        const setupSelectEl = document.getElementById("setup-select");
        if (setupSelectEl && !HTF_SNAPSHOT_ACTIVE && !setupSelectEl.value) {
            const bestSetup = autoSelectSetupForCurrentView(tfData, state, excludedSetupId);
            if (bestSetup) {
                setupSelectEl.value = String(bestSetup.id);
                if (bestSetup.signalTs != null && Number.isFinite(bestSetup.signalTs)) {
                    HTF_SNAPSHOT_MAX_SIGNAL_TS = bestSetup.signalTs + PHASE2_SIGNAL_BASE_MINUTES * 60 * 1000;
                } else HTF_SNAPSHOT_MAX_SIGNAL_TS = null;
                applyHtfSnapshotForSetup(bestSetup, { preserveView: false, isAutoPan: true });
            }
        }
    }

    if (!isLeft && VIEW_MODE === VIEW_MODE_SPLIT && !HTF_SNAPSHOT_ACTIVE) {
        if (HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_SNAP || HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_STRICT) {
            updateHtfFollowFromLtf(state);
        }
    }
}

function bindPlotlyEventsOnce() {
    const rightEl = document.getElementById("m1-chart");
    if (rightEl && typeof rightEl.on === "function" && !plotlyEventsBoundRight) {
        rightEl.on("plotly_relayout", (ev) => handleRelayoutForPane("right", ev));
        plotlyEventsBoundRight = true;
    }
    const leftEl = document.getElementById("htf-chart");
    if (leftEl && typeof leftEl.on === "function" && !plotlyEventsBoundLeft) {
        leftEl.on("plotly_relayout", (ev) => handleRelayoutForPane("left", ev));
        plotlyEventsBoundLeft = true;
    }
}