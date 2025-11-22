// trace_builder.js

// --- Traces Builders ---

// Erstellt die Hintergrund-Boxen für Trading Sessions
function buildSessionTraces(tf, tfData, state, windowBars, visibleBarsArr) {
    const traces = [];
    if (!windowBars || !windowBars.length || !visibleBarsArr || !visibleBarsArr.length || !sessionDays || sessionDays <= 0) return traces;
    if (tf === "H4" || tf === "D" || tf === "W" || tf === "M") return traces;
    if (getRegime(tf) === "daily") return traces;

    const visibleStartIdx = state.visibleStartIdx;
    const visibleEndIdx = state.visibleEndIdx;
    if (visibleStartIdx == null || visibleEndIdx == null) return traces;

    const dayInfo = {};
    for (const bar of windowBars) {
        const dt = new Date(bar.ts);
        const key = tradingDateKeyFromDate(dt);
        if (!dayInfo[key]) { dayInfo[key] = { firstIdx: bar.i, lastIdx: bar.i }; }
        else {
            if (bar.i < dayInfo[key].firstIdx) dayInfo[key].firstIdx = bar.i;
            if (bar.i > dayInfo[key].lastIdx)  dayInfo[key].lastIdx = bar.i;
        }
    }
    let allWindowDays = Object.keys(dayInfo).sort();
    if (!allWindowDays.length) return traces;

    const visibleDays = [], fullVisibleDays = [];
    let leftPartialDay = null, rightPartialDay = null;

    for (const dayKey of allWindowDays) {
        const info = dayInfo[dayKey];
        const intersects = (info.lastIdx >= visibleStartIdx) && (info.firstIdx <= visibleEndIdx);
        if (!intersects) continue;
        visibleDays.push(dayKey);
        const isFull = (info.firstIdx >= visibleStartIdx) && (info.lastIdx <= visibleEndIdx);
        if (isFull) fullVisibleDays.push(dayKey);
        else {
            if ((info.firstIdx < visibleStartIdx) && (info.lastIdx >= visibleStartIdx)) leftPartialDay = dayKey;
            if ((info.lastIdx > visibleEndIdx) && (info.firstIdx <= visibleEndIdx)) rightPartialDay = dayKey;
        }
    }

    const rawMax = (typeof sessionDays === "number" ? sessionDays : DEFAULT_SESSION_DAYS);
    const maxDays = Math.max(3, Math.min(rawMax, 60));
    let selectedDayKeys = [];

    if (!visibleDays.length) {
        if (allWindowDays.length <= maxDays) selectedDayKeys = allWindowDays.slice();
        else selectedDayKeys = allWindowDays.slice(allWindowDays.length - maxDays);
    } else if (visibleDays.length >= maxDays) {
        let selected = fullVisibleDays.slice();
        if (rightPartialDay && !selected.includes(rightPartialDay)) selected.push(rightPartialDay);
        if (leftPartialDay && !selected.includes(leftPartialDay)) selected.push(leftPartialDay);
        while (selected.length > maxDays) {
            let removed = false;
            for (let i = 0; i < selected.length; i++) {
                if (rightPartialDay && selected[i] === rightPartialDay) continue;
                selected.splice(i, 1); removed = true; break;
            }
            if (!removed) break;
        }
        selectedDayKeys = selected.slice();
    } else {
        selectedDayKeys = visibleDays.slice();
        const selectedSet = new Set(selectedDayKeys);
        let remaining = maxDays - selectedDayKeys.length;
        if (remaining > 0 && allWindowDays.length > selectedDayKeys.length) {
            const idxFirstVis = allWindowDays.indexOf(visibleDays[0]);
            const idxLastVis  = allWindowDays.indexOf(visibleDays[visibleDays.length - 1]);
            let leftIdx = idxFirstVis - 1, rightIdx = idxLastVis + 1;
            while (remaining > 0 && (leftIdx >= 0 || rightIdx < allWindowDays.length)) {
                if (remaining === 1) {
                    if (rightIdx < allWindowDays.length && !selectedSet.has(allWindowDays[rightIdx])) { selectedDayKeys.push(allWindowDays[rightIdx]); remaining--; rightIdx++; }
                    else if (leftIdx >= 0 && !selectedSet.has(allWindowDays[leftIdx])) { selectedDayKeys.unshift(allWindowDays[leftIdx]); remaining--; leftIdx--; }
                    else break;
                } else {
                    let added = false;
                    if (leftIdx >= 0 && !selectedSet.has(allWindowDays[leftIdx])) { selectedDayKeys.unshift(allWindowDays[leftIdx]); selectedSet.add(allWindowDays[leftIdx]); remaining--; added = true; leftIdx--; }
                    if (remaining > 0 && rightIdx < allWindowDays.length && !selectedSet.has(allWindowDays[rightIdx])) { selectedDayKeys.push(allWindowDays[rightIdx]); selectedSet.add(allWindowDays[rightIdx]); remaining--; added = true; rightIdx++; }
                    if (!added) break;
                }
            }
        }
    }

    selectedDayKeys = selectedDayKeys.filter(dk => dayInfo[dk]).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));

    for (const dayKey of selectedDayKeys) {
        const baseDate = dateFromKey(dayKey);
        if (!baseDate) continue;
        for (const s of SESSION_CONFIG) {
            const startBase = addDaysUtc(baseDate, s.startOffsetDays || 0);
            const endBase   = addDaysUtc(baseDate, s.endOffsetDays   || 0);
            const startMs = Date.UTC(startBase.getUTCFullYear(), startBase.getUTCMonth(), startBase.getUTCDate(), s.startHour, s.startMinute, 0);
            const endMs   = Date.UTC(endBase.getUTCFullYear(), endBase.getUTCMonth(), endBase.getUTCDate(), s.endHour,   s.endMinute,   0);

            const barsInSession = [];
            for (const bar of windowBars) { if (bar.ts >= startMs && bar.ts < endMs) barsInSession.push(bar); }
            if (!barsInSession.length) continue;

            let runningHigh = barsInSession[0].h, runningLow = barsInSession[0].l;
            const xTop = [], yTop = [], xBottom = [], yBottom = [];

            for (const bar of barsInSession) {
                if (bar.h > runningHigh) runningHigh = bar.h;
                if (bar.l < runningLow)  runningLow  = bar.l;
                xTop.push(bar.i); yTop.push(runningHigh);
                xBottom.push(bar.i); yBottom.push(runningLow);
            }
            const lastBarInSession = barsInSession[barsInSession.length - 1];
            if (lastBarInSession) {
                const maxWindowIdx = windowBars[windowBars.length - 1].i;
                let extendIdx = lastBarInSession.i + 1;
                if (extendIdx > maxWindowIdx) extendIdx = maxWindowIdx;
                if (extendIdx > lastBarInSession.i) {
                    xTop.push(extendIdx); yTop.push(runningHigh);
                    xBottom.push(extendIdx); yBottom.push(runningLow);
                }
            }
            traces.push({
                type: "scatter", x: xTop.concat(xBottom.slice().reverse()), y: yTop.concat(yBottom.slice().reverse()),
                mode: "lines", line: { width: 0 }, fill: "toself", fillcolor: s.fillColor, hoverinfo: "skip",
                name: s.name, legendgroup: "sessions", showlegend: false
            });
        }
    }
    return traces;
}

// Erstellt die Setup-Boxen (Phase 2)
function buildPhase2Traces(tf, tfData, windowBars, windowStartIdx, windowEndIdx, pane) {
    const traces = [];
    if (!PHASE2_BOXES || !PHASE2_BOXES.length || !SHOW_SIGNALS) return traces;

    const minIdx = windowStartIdx, maxIdx = windowEndIdx;
    const baseTfData = getPhase2BaseTfData();
    
    let maxBoxCloseTs = null;
    if (pane === "left") {
        if (HTF_SNAPSHOT_MAX_SIGNAL_TS != null && isFinite(HTF_SNAPSHOT_MAX_SIGNAL_TS)) maxBoxCloseTs = HTF_SNAPSHOT_MAX_SIGNAL_TS;
        else if (HTF_FOLLOW_ACTIVE && HTF_FOLLOW_INFO && HTF_FOLLOW_INFO.snapshotTime != null && isFinite(HTF_FOLLOW_INFO.snapshotTime)) maxBoxCloseTs = HTF_FOLLOW_INFO.snapshotTime;
    }

    for (const box of PHASE2_BOXES) {
        const t1 = box.topTs, t2 = box.bottomTs;
        if (!Number.isFinite(t1) || !Number.isFinite(t2)) continue;
        const startTs = Math.min(t1, t2);
        let searchRightTs = null, logicalCloseTs = null;

        if (box.signalTs != null && Number.isFinite(box.signalTs)) {
            // FIX: Prüfen, ob PHASE2_SIGNAL_BASE_MINUTES eine Zahl ist (auch 0 ist erlaubt!).
            // Vorher: (PHASE2_SIGNAL_BASE_MINUTES || 5) -> bei 0 griff der Fallback 5.
            let addMinutes = (typeof PHASE2_SIGNAL_BASE_MINUTES === "number") ? PHASE2_SIGNAL_BASE_MINUTES : 5;
            
            logicalCloseTs = box.signalTs + addMinutes * 60 * 1000;
            searchRightTs = logicalCloseTs - 1;
        } else {
            logicalCloseTs = Math.max(t1, t2);
            searchRightTs = logicalCloseTs;
        }

        if (pane === "left" && maxBoxCloseTs != null && logicalCloseTs != null && logicalCloseTs > maxBoxCloseTs) continue;

        let posL = findPosLEByTs(tfData, startTs);
        let posR = findPosLEByTs(tfData, searchRightTs);
        if (posL === null) posL = 0;
        if (posR === null) posR = tfData.bars.length - 1;
        if (posR < posL) { const tmp = posL; posL = posR; posR = tmp; }

        const idxL = tfData.bars[posL].i, idxR = tfData.bars[posR].i;
        let leftIdx = Math.max(minIdx, Math.min(idxL, idxR)), rightIdx = Math.min(maxIdx, Math.max(idxL, idxR));
        if (rightIdx < minIdx || leftIdx > maxIdx || rightIdx < leftIdx) continue;

        let hiBox = box.priceHi, loBox = box.priceLo;
        if (!Number.isFinite(hiBox) || !Number.isFinite(loBox)) {
            if (baseTfData && baseTfData.bars && baseTfData.bars.length) {
                let posBaseL = findPosLEByTs(baseTfData, startTs);
                let posBaseR = findPosLEByTs(baseTfData, searchRightTs);
                if (posBaseL === null) posBaseL = 0;
                if (posBaseR === null) posBaseR = baseTfData.bars.length - 1;
                if (posBaseR < posBaseL) { const tmp = posBaseL; posBaseL = posBaseR; posBaseR = tmp; }
                
                const baseBarsInBox = sliceBarsForRange(baseTfData, baseTfData.bars[posBaseL].i, baseTfData.bars[posBaseR].i);
                if (baseBarsInBox.length) {
                    let hi = Number.NEGATIVE_INFINITY, lo = Number.POSITIVE_INFINITY;
                    for (const b of baseBarsInBox) { if (b.h > hi) hi = b.h; if (b.l < lo) lo = b.l; }
                    if (Number.isFinite(hi) && Number.isFinite(lo)) { hiBox = hi; loBox = lo; box.priceHi = hi; box.priceLo = lo; }
                }
            }
            if (!Number.isFinite(hiBox) || !Number.isFinite(loBox)) {
                const barsInBox = sliceBarsForRange(tfData, leftIdx, rightIdx);
                if (!barsInBox.length) continue;
                let hi = Number.NEGATIVE_INFINITY, lo = Number.POSITIVE_INFINITY;
                for (const bar of barsInBox) { if (bar.h > hi) hi = bar.h; if (bar.l < lo) lo = bar.l; }
                if (!Number.isFinite(hi) || !Number.isFinite(lo)) continue;
                hiBox = hi; loBox = lo; box.priceHi = hi; box.priceLo = lo;
            }
        }

        const x0 = leftIdx - CANDLE_BODY_HALF_WIDTH, x1 = rightIdx + CANDLE_BODY_HALF_WIDTH;
        const xPoly = [x0, x1, x1, x0, x0];
        const yPoly = [hiBox, hiBox, loBox, loBox, hiBox];
        const isBuy = box.direction === "buy";
        const isSnapshotBox = (pane === "left" && box.isSnapshotActive === true);

        traces.push({
            type: "scatter", x: xPoly, y: yPoly, mode: "lines",
            line: { width: 1, color: isBuy ? "rgba(0,0,255,0.9)" : "rgba(255,0,0,0.9)", dash: isSnapshotBox ? "solid" : "dot" },
            fill: "none", hoverinfo: "skip", name: isBuy ? "Phase2 BUY" : "Phase2 SELL", legendgroup: "phase2", showlegend: false
        });
    }
    return traces;
}

// Erstellt die Trade-Visualisierungen (Phase 3)
function buildPhase3Traces(tf, tfData, windowBars, windowStartIdx, windowEndIdx, pane) {
    const traces = [];
    if (!PHASE3_TRADES || !PHASE3_TRADES.length) return traces;
    const minIdx = windowStartIdx, maxIdx = windowEndIdx;

    let maxAllowedTs = null;
    if (pane === "left") {
        if (HTF_SNAPSHOT_MAX_SIGNAL_TS != null && isFinite(HTF_SNAPSHOT_MAX_SIGNAL_TS)) maxAllowedTs = HTF_SNAPSHOT_MAX_SIGNAL_TS;
        else if (HTF_FOLLOW_ACTIVE && HTF_FOLLOW_INFO && HTF_FOLLOW_INFO.snapshotTime != null && isFinite(HTF_FOLLOW_INFO.snapshotTime)) maxAllowedTs = HTF_FOLLOW_INFO.snapshotTime;
    }

    for (const tr of PHASE3_TRADES) {
        // Prüfen auf Zeitgrenze (Snapshot)
        if (pane === "left" && maxAllowedTs != null) {
            let checkTs = (tr.entryTs != null && Number.isFinite(tr.entryTs)) ? tr.entryTs : tr.expirationTs;
            if (checkTs != null && checkTs > maxAllowedTs) continue;
        }

        const isBuy = tr.direction === "buy";
        const hasEntryTs = tr.entryTs != null && Number.isFinite(tr.entryTs);
        const hasExitTs = tr.exitTs != null && Number.isFinite(tr.exitTs);
        const isFilled = tr.filled && hasEntryTs && hasExitTs;
        const isMissed = !tr.filled;

        if (!SHOW_MISSES && isMissed) continue;

        if (isFilled) {
            let posEntry = findPosGEByTs(tfData, tr.entryTs);
            let posExit  = findPosGEByTs(tfData, tr.exitTs);
            if (posEntry === null) posEntry = findPosLEByTs(tfData, tr.entryTs);
            if (posExit === null) posExit = findPosLEByTs(tfData, tr.exitTs);
            if (posEntry === null || posExit === null) continue;

            const idxEntry = tfData.bars[posEntry].i;
            const idxExit  = tfData.bars[posExit].i;
            if (Math.max(idxEntry, idxExit) < minIdx || Math.min(idxEntry, idxExit) > maxIdx) continue;

            let entryPrice = Number.isFinite(tr.entryPrice) ? tr.entryPrice : tfData.bars[posEntry].c;
            let exitPrice = Number.isFinite(tr.exitPrice) ? tr.exitPrice : tfData.bars[posExit].c;
            const slPrice = Number.isFinite(tr.slPrice) ? tr.slPrice : NaN;
            const tpPrice = Number.isFinite(tr.tpPrice) ? tr.tpPrice : NaN;

            const isSingleCandle = (idxEntry === idxExit);
            let boxXLeft, boxXRight, lineXStart, lineXEnd;

            if (isSingleCandle) {
                boxXLeft = idxEntry - 0.5; boxXRight = idxEntry + 0.5;
                lineXStart = idxEntry - 0.5; lineXEnd = idxEntry + 0.5;
            } else {
                boxXLeft = Math.min(idxEntry, idxExit); boxXRight = Math.max(idxEntry, idxExit);
                lineXStart = idxEntry; lineXEnd = idxExit;
            }

            if (!Number.isNaN(slPrice)) {
                traces.push({
                    type: "scatter", x: [boxXLeft, boxXRight, boxXRight, boxXLeft, boxXLeft],
                    y: [Math.max(entryPrice, slPrice), Math.max(entryPrice, slPrice), Math.min(entryPrice, slPrice), Math.min(entryPrice, slPrice), Math.max(entryPrice, slPrice)],
                    mode: "lines", line: { width: 0 }, fill: "toself", fillcolor: "rgba(8,153,129,0.15)", hoverinfo: "skip", showlegend: false
                });
            }
            if (!Number.isNaN(tpPrice)) {
                traces.push({
                    type: "scatter", x: [boxXLeft, boxXRight, boxXRight, boxXLeft, boxXLeft],
                    y: [Math.max(entryPrice, tpPrice), Math.max(entryPrice, tpPrice), Math.min(entryPrice, tpPrice), Math.min(entryPrice, tpPrice), Math.max(entryPrice, tpPrice)],
                    mode: "lines", line: { width: 0 }, fill: "toself", fillcolor: "rgba(67,70,81,0.15)", hoverinfo: "skip", showlegend: false
                });
            }
            if (entryPrice !== exitPrice) {
                const isProfit = isBuy ? (exitPrice > entryPrice) : (exitPrice < entryPrice);
                traces.push({
                    type: "scatter", x: [boxXLeft, boxXRight, boxXRight, boxXLeft, boxXLeft],
                    y: [Math.max(entryPrice, exitPrice), Math.max(entryPrice, exitPrice), Math.min(entryPrice, exitPrice), Math.min(entryPrice, exitPrice), Math.max(entryPrice, exitPrice)],
                    mode: "lines", line: { width: 0 }, fill: "toself", fillcolor: isProfit ? "rgba(67,70,81,0.15)" : "rgba(8,153,129,0.15)", hoverinfo: "skip", showlegend: false
                });
            }
            traces.push({
                type: "scatter", x: [lineXStart, lineXEnd], y: [entryPrice, exitPrice],
                mode: "lines", line: { width: 1, color: "rgba(49,27,146,1.0)", dash: "dash" }, hoverinfo: "skip", showlegend: false
            });
            continue;
        }

        // Missed Trade
        if (!Number.isFinite(tr.entryPrice)) continue;
        const box = findPhase2BoxForTrade(tr);
        if (!box || !Number.isFinite(box.signalTs)) continue;
        let posSignal = findPosGEByTs(tfData, box.signalTs);
        if (posSignal === null) posSignal = findPosLEByTs(tfData, box.signalTs);
        if (posSignal === null) continue;

        const signalBarIdx = tfData.bars[posSignal].i;
        let startIdx = signalBarIdx + 1;
        let endIdx = null;

        // FIX: Wir nutzen jetzt expirationTs statt entryWindowEndTs
        if (tr.expirationTs != null && Number.isFinite(tr.expirationTs)) {
            let posFirstAfter = findPosGEByTs(tfData, tr.expirationTs);
            if (posFirstAfter !== null) { let posEnd = posFirstAfter - 1; if (posEnd < 0) posEnd = 0; endIdx = tfData.bars[posEnd].i; }
        }
        
        if (endIdx === null) endIdx = maxIdx;
        if (endIdx < startIdx) { const tmp = startIdx; startIdx = endIdx; endIdx = tmp; }

        const leftIdx = Math.max(minIdx, startIdx), rightIdx = Math.min(maxIdx, endIdx);
        if (rightIdx < minIdx || leftIdx > maxIdx || rightIdx < leftIdx) continue;

        let boxXLeft = leftIdx, boxXRight = rightIdx;
        if (leftIdx === rightIdx) { boxXLeft = leftIdx - 0.5; boxXRight = rightIdx + 0.5; }

        const entryPrice = tr.entryPrice;
        if (!Number.isNaN(tr.slPrice)) {
            traces.push({
                type: "scatter", x: [boxXLeft, boxXRight, boxXRight, boxXLeft, boxXLeft],
                y: [Math.max(entryPrice, tr.slPrice), Math.max(entryPrice, tr.slPrice), Math.min(entryPrice, tr.slPrice), Math.min(entryPrice, tr.slPrice), Math.max(entryPrice, tr.slPrice)],
                mode: "lines", line: { width: 0 }, fill: "toself", fillcolor: "rgba(8,153,129,0.15)", hoverinfo: "skip", showlegend: false
            });
        }
        if (!Number.isNaN(tr.tpPrice)) {
            traces.push({
                type: "scatter", x: [boxXLeft, boxXRight, boxXRight, boxXLeft, boxXLeft],
                y: [Math.max(entryPrice, tr.tpPrice), Math.max(entryPrice, tr.tpPrice), Math.min(entryPrice, tr.tpPrice), Math.min(entryPrice, tr.tpPrice), Math.max(entryPrice, tr.tpPrice)],
                mode: "lines", line: { width: 0 }, fill: "toself", fillcolor: "rgba(67,70,81,0.15)", hoverinfo: "skip", showlegend: false
            });
        }
    }
    return traces;
}

// Hilfsfunktion: Erstellt den Haupt-Candlestick-Trace (Preis)
function buildPriceTrace(x, open, high, low, close, customdata) {
    // Hinweis: candleHoverOn, WICK_OUTLINE_COLOR, etc. kommen aus state_manager.js (global)
    return {
        type: "candlestick", x, open, high, low, close, customdata, name: "Price",
        increasing: { line: { color: WICK_OUTLINE_COLOR }, fillcolor: BULL_BODY_COLOR },
        decreasing: { line: { color: WICK_OUTLINE_COLOR }, fillcolor: BEAR_BODY_COLOR },
        line: { width: 1 }, hoverinfo: candleHoverOn ? "x+y" : "none", showlegend: false
    };
}

// Hilfsfunktion: Erstellt Shapes für die Zeitleiste (Tick-Linien unten)
function buildTickShapes(tickInfo) {
    const shapes = [];
    if (tickInfo.ticktext && tickInfo.tickvals && tickInfo.ticktext.length === tickInfo.tickvals.length) {
        for (let i = 0; i < tickInfo.tickvals.length; i++) {
            if (tickInfo.ticktext[i]) {
                // Hinweis: FOREGROUND_COLOR kommt aus state_manager.js
                shapes.push({ type: "line", xref: "x", yref: "paper", x0: tickInfo.tickvals[i], x1: tickInfo.tickvals[i], y0: 0, y1: -0.006, line: { color: FOREGROUND_COLOR, width: 1 }, layer: "above" });
            }
        }
    }
    return shapes;
}

// Hilfsfunktion: Baut das Layout-Objekt für Plotly (Standardisiert)
function buildChartLayout(title, xRange, yRange, tickInfo, shapes, pane, axisMode) {
    let yAxisSide = (pane === "left") ? "left" : "right";
    let margin = (pane === "left") ? { l: 60, r: 10, t: 20, b: 40 } : { l: 10, r: 60, t: 20, b: 40 };

    return {
        title: title,
        xaxis: {
            title: "", rangeslider: { visible: false }, showgrid: false, showline: true, linewidth: 1, linecolor: "black", mirror: true,
            ticks: "outside", ticklen: 5, tickcolor: BACKGROUND_COLOR, tickpadding: 5, fixedrange: axisMode === "y", range: xRange,
            tickmode: (tickInfo.tickvals && tickInfo.tickvals.length) ? "array" : "auto",
            tickvals: (tickInfo.tickvals && tickInfo.tickvals.length) ? tickInfo.tickvals : undefined,
            ticktext: (tickInfo.ticktext && tickInfo.ticktext.length) ? tickInfo.ticktext : undefined,
        },
        yaxis: { side: yAxisSide, tickformat: ".5f", showgrid: false, showline: true, linewidth: 1, linecolor: "black", mirror: true, ticks: "outside", fixedrange: axisMode === "x", range: yRange },
        hovermode: "x", dragmode: "pan", plot_bgcolor: BACKGROUND_COLOR, paper_bgcolor: BACKGROUND_COLOR, font: { color: FOREGROUND_COLOR, size: 11 },
        shapes: shapes, margin: margin, showlegend: false
    };
}