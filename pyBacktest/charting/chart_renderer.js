// chart_renderer.js

// --- Window Calculation Logic ---

function calculateVerticalCorrection(tfData, visibleStartIdx, visibleEndIdx, currentYRange) {
    if (!tfData || !tfData.bars || visibleStartIdx == null || visibleEndIdx == null || !currentYRange) return null;
    const yMin = currentYRange[0], yMax = currentYRange[1];
    if (!Number.isFinite(yMin) || !Number.isFinite(yMax) || yMax <= yMin) return null;

    const start = Math.max(tfData.minIdx, Math.round(visibleStartIdx));
    const end   = Math.min(tfData.maxIdx, Math.round(visibleEndIdx));
    const visibleBars = sliceBarsForRange(tfData, start, end);

    if (!visibleBars || !visibleBars.length) return null;

    let globalHigh = Number.NEGATIVE_INFINITY;
    let globalLow  = Number.POSITIVE_INFINITY;
    for (const bar of visibleBars) {
        if (bar.h > globalHigh) globalHigh = bar.h;
        if (bar.l < globalLow)  globalLow  = bar.l;
    }
    if (!Number.isFinite(globalHigh) || !Number.isFinite(globalLow)) return null;

    const height = yMax - yMin;
    const padding = height * 0.10;

    if (globalLow > yMax) {
        const newYMin = globalLow - padding;
        const newYMax = newYMin + height;
        console.log("[AutoPan] Candles above view -> Correction Up applied.");
        return [newYMin, newYMax];
    }
    if (globalHigh < yMin) {
        const newYMax = globalHigh + padding;
        const newYMin = newYMax - height;
        console.log("[AutoPan] Candles below view -> Correction Down applied.");
        return [newYMin, newYMax];
    }
    return null;
}

function computeWindowForTf(tfData, visibleBars, centerIdx) {
    const bars = tfData.bars || [];
    if (!bars.length) {
        return { windowStart: 0, windowEnd: -1, visibleStartIdx: 0, visibleEndIdx: -1, visibleBars: 0, minIdx: 0, maxIdx: -1, viewStart: 0, viewEnd: -1 };
    }
    const minIdx = tfData.minIdx, maxIdx = tfData.maxIdx;
    if (!visibleBars || visibleBars <= 0) visibleBars = DEFAULT_VISIBLE_BARS;
    if (centerIdx === null || centerIdx === undefined || !isFinite(centerIdx)) centerIdx = maxIdx;

    let halfVisible = Math.floor(visibleBars / 2);
    let visibleStartIdx = Math.round(centerIdx - halfVisible);
    let visibleEndIdx = visibleStartIdx + visibleBars - 1;

    if (visibleStartIdx < minIdx) {
        visibleStartIdx = minIdx; visibleEndIdx = visibleStartIdx + visibleBars - 1;
    }
    if (visibleEndIdx > maxIdx) {
        visibleEndIdx = maxIdx; visibleStartIdx = visibleEndIdx - visibleBars + 1;
        if (visibleStartIdx < minIdx) visibleStartIdx = minIdx;
    }
    visibleBars = Math.max(1, visibleEndIdx - visibleStartIdx + 1);

    let totalBars = Math.floor(visibleBars * BUFFER_FACTOR);
    if (totalBars < visibleBars) totalBars = visibleBars;

    const visibleCenter = 0.5 * (visibleStartIdx + visibleEndIdx);
    let halfTotal = Math.floor(totalBars / 2);
    let windowStart = Math.round(visibleCenter - halfTotal);
    let windowEnd = windowStart + totalBars - 1;

    if (windowStart < minIdx) { windowStart = minIdx; windowEnd = windowStart + totalBars - 1; }
    if (windowEnd > maxIdx) { windowEnd = maxIdx; windowStart = windowEnd - totalBars + 1; if (windowStart < minIdx) windowStart = minIdx; }

    const viewStart = visibleStartIdx - 0.5;
    const viewEnd   = visibleEndIdx + 0.5;

    return { windowStart, windowEnd, visibleStartIdx, visibleEndIdx, visibleBars, minIdx, maxIdx, viewStart, viewEnd };
}

function computeWindowForTfRightAnchored(tfData, visibleBars, anchorIdx) {
    const bars = tfData.bars || [];
    if (!bars.length) return computeWindowForTf(tfData, visibleBars, null);
    const minIdx = tfData.minIdx, maxIdx = tfData.maxIdx;
    if (!visibleBars || visibleBars <= 0) visibleBars = DEFAULT_VISIBLE_BARS;
    if (anchorIdx === null || anchorIdx === undefined || !isFinite(anchorIdx)) return computeWindowForTf(tfData, visibleBars, null);

    let visibleEndIdx = Math.round(anchorIdx);
    let visibleStartIdx = visibleEndIdx - (visibleBars - 1);

    if (visibleEndIdx > maxIdx) { visibleEndIdx = maxIdx; visibleStartIdx = visibleEndIdx - (visibleBars - 1); }
    if (visibleStartIdx < minIdx) {
        visibleStartIdx = minIdx; visibleEndIdx = visibleStartIdx + (visibleBars - 1);
        if (visibleEndIdx > maxIdx) visibleEndIdx = maxIdx;
    }
    visibleBars = Math.max(1, visibleEndIdx - visibleStartIdx + 1);

    let totalBars = Math.floor(visibleBars * BUFFER_FACTOR);
    if (totalBars < visibleBars) totalBars = visibleBars;

    const visibleCenter = 0.5 * (visibleStartIdx + visibleEndIdx);
    let halfTotal = Math.floor(totalBars / 2);
    let windowStart = Math.round(visibleCenter - halfTotal);
    let windowEnd = windowStart + totalBars - 1;

    if (windowStart < minIdx) { windowStart = minIdx; windowEnd = windowStart + totalBars - 1; }
    if (windowEnd > maxIdx) { windowEnd = maxIdx; windowStart = windowEnd - totalBars + 1; if (windowStart < minIdx) windowStart = minIdx; }

    const viewStart = visibleStartIdx - 0.5;
    const viewEnd   = visibleEndIdx + 0.5;

    return { windowStart, windowEnd, visibleStartIdx, visibleEndIdx, visibleBars, minIdx, maxIdx, viewStart, viewEnd };
}

function computeWindowFromTimeRangeExact(tfData, timeRange) {
    const bars = tfData.bars || [];
    if (!bars.length || !timeRange || timeRange.length !== 2) return computeWindowForTf(tfData, DEFAULT_VISIBLE_BARS, null);
    const [t0, t1] = timeRange;
    const ts0 = parseNyIsoToMs(t0), ts1 = parseNyIsoToMs(t1);
    let posL = findPosGEByTs(tfData, ts0), posR = findPosLEByTs(tfData, ts1);

    if (posL === null && posR === null) return computeWindowForTf(tfData, DEFAULT_VISIBLE_BARS, null);
    if (posL === null) posL = 0;
    if (posR === null) posR = bars.length - 1;
    if (posR < posL) { const tmp = posL; posL = posR; posR = tmp; }

    const leftIdx = bars[posL].i, rightIdx = bars[posR].i;
    const visibleBars = Math.max(1, rightIdx - leftIdx + 1);
    const centerIdx = 0.5 * (leftIdx + rightIdx);
    return computeWindowForTf(tfData, visibleBars, centerIdx);
}

// --- Ticks & Grid Logic ---

function generateIntradayTicks(start, end, stepMin) {
    const ticks = [];
    if (!start || !end) return ticks;
    const stepMs = stepMin * 60 * 1000;
    const base = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate()));
    base.setUTCDate(base.getUTCDate() - 1);
    let t = base.getTime();
    const endExt = end.getTime() + stepMs;
    while (t <= endExt) { ticks.push(new Date(t)); t += stepMs; }
    return ticks;
}

function generateCalendarTicks(start, end, intervalCode) {
    const ticks = [];
    if (!start || !end) return ticks;
    let s = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate()));
    let e = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate()));

    function addDays(d, n) { const nd = new Date(d.getTime()); nd.setUTCDate(nd.getUTCDate() + n); return nd; }
    function addMonths(d, n) { const nd = new Date(d.getTime()); nd.setUTCMonth(nd.getUTCMonth() + n); nd.setUTCDate(1); return nd; }

    let dt;
    if (intervalCode === "year") {
        let year = s.getUTCFullYear() - 1; dt = new Date(Date.UTC(year, 0, 1)); const endExt = addMonths(e, 12);
        while (dt.getTime() <= endExt.getTime()) { ticks.push(new Date(dt.getTime())); dt = addMonths(dt, 12); }
    } else if (intervalCode === "quarter") {
        let year = s.getUTCFullYear(), month = s.getUTCMonth(); let qMonth = 3 * Math.floor(month / 3) + 1;
        dt = new Date(Date.UTC(year, qMonth - 1, 1)); dt = addMonths(dt, -3); const endExt = addMonths(e, 3);
        while (dt.getTime() <= endExt.getTime()) { ticks.push(new Date(dt.getTime())); dt = addMonths(dt, 3); }
    } else if (intervalCode === "month") {
        dt = new Date(Date.UTC(s.getUTCFullYear(), s.getUTCMonth(), 1)); dt = addMonths(dt, -1); const endExt = addMonths(e, 1);
        while (dt.getTime() <= endExt.getTime()) { ticks.push(new Date(dt.getTime())); dt = addMonths(dt, 1); }
    } else if (intervalCode === "week_mon") {
        dt = new Date(s.getTime()); const wd = dt.getUTCDay(); const shift = (wd + 6) % 7;
        dt.setUTCDate(dt.getUTCDate() - shift); dt = addDays(dt, -7); const endExt = addDays(e, 7);
        while (dt.getTime() <= endExt.getTime()) { if (dt.getUTCDay() === 1) ticks.push(new Date(dt.getTime())); dt = addDays(dt, 7); }
    } else if (intervalCode === "day_mwf") {
        dt = addDays(s, -1); const endExt = addDays(e, 1);
        while (dt.getTime() <= endExt.getTime()) { const wd = dt.getUTCDay(); if (wd === 1 || wd === 3 || wd === 5) ticks.push(new Date(dt.getTime())); dt = addDays(dt, 1); }
    } else {
        dt = addDays(s, -1); const endExt = addDays(e, 1);
        while (dt.getTime() <= endExt.getTime()) { ticks.push(new Date(dt.getTime())); dt = addDays(dt, 1); }
    }

    const uniqueSorted = Array.from(new Set(ticks.map(t => t.getTime()))).sort((a, b) => a - b);
    const out = [];
    const minAllowed = addDays(s, -2).getTime();
    const maxAllowed = addDays(e, 2).getTime();
    for (const ms of uniqueSorted) { if (ms >= minAllowed && ms <= maxAllowed) out.push(new Date(ms)); }
    return out;
}

function formatTickLabels(ticks, intervalCode, anchorInfo, tickIndices, state, chartPixelWidth) {
    if (!ticks || !ticks.length) return { labels: [], hiddenTickvals: [] };
    anchorInfo = anchorInfo || {};
    const yearFirstTradingDate = anchorInfo.yearFirstTradingDate || {};
    const monthFirstTradingDate = anchorInfo.monthFirstTradingDate || {};
    const monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    function pad2(x) { return String(x).padStart(2, "0"); }
    const levelOrder = { time: 0, day: 1, month: 2, year: 3 };

    let baseUnit;
    if (intervalCode === "year") baseUnit = "year";
    else if (intervalCode === "quarter" || intervalCode === "month") baseUnit = "month";
    else if (intervalCode === "week_mon" || intervalCode === "day_mwf" || intervalCode === "day" || intervalCode === "day_all") baseUnit = "day";
    else baseUnit = "time";
    const isIntraday = baseUnit === "time";

    function highlight(text, unit) {
        if (levelOrder[unit] > levelOrder[baseUnit]) return "<span style='font-size:110%'><b>" + text + "</b></span>";
        return text;
    }

    const units = [], texts = [], labeledDates = new Set();
    for (const dt of ticks) {
        const y = dt.getUTCFullYear(), m = dt.getUTCMonth() + 1, d = dt.getUTCDate(), hh = dt.getUTCHours(), mm = dt.getUTCMinutes(), wd = dt.getUTCDay();
        const yearStr = String(y), monthStr = monthNames[m - 1], dayStr = String(d), timeStr = pad2(hh) + ":" + pad2(mm);
        let unit, text;

        if (isIntraday) {
            const dateKey = `${y}-${pad2(m)}-${pad2(d)}`;
            const ymKey = `${y}-${pad2(m)}`;
            const anchorYearDate = yearFirstTradingDate[y];
            const anchorMonthDate = monthFirstTradingDate[ymKey];
            const isMidnight = (hh === 0 && mm === 0);
            const isDayOpen = (hh === 17 && mm === 0);
            const isSunday = (wd === 0);

            unit = "time"; text = timeStr;
            if ((isMidnight && !isSunday) || (isDayOpen && isSunday)) {
                if (!labeledDates.has(dateKey)) {
                    if (anchorYearDate && dateKey === anchorYearDate) { unit = "year"; text = yearStr; }
                    else if (anchorMonthDate && dateKey === anchorMonthDate) { unit = "month"; text = monthStr; }
                    else { unit = "day"; text = dayStr; }
                    labeledDates.add(dateKey);
                }
            }
        } else {
            if (intervalCode === "year") { unit = "year"; text = yearStr; }
            else if (intervalCode === "quarter") { unit = "month"; text = "Q" + (Math.floor((m - 1) / 3) + 1); }
            else if (intervalCode === "month") { unit = "month"; text = monthStr; }
            else {
                const month2 = pad2(m), dateKey = `${y}-${month2}-${pad2(d)}`, ymKey = `${y}-${month2}`;
                const anchorYearDate = yearFirstTradingDate[y], anchorMonthDate = monthFirstTradingDate[ymKey];
                if (anchorYearDate && dateKey === anchorYearDate) { unit = "year"; text = yearStr; }
                else if (anchorMonthDate && dateKey === anchorMonthDate) { unit = "month"; text = monthStr; }
                else if (d === 1 && m === 1) { unit = "year"; text = yearStr; }
                else if (d === 1) { unit = "month"; text = monthStr; }
                else { unit = "day"; text = dayStr; }
            }
        }
        units.push(unit); texts.push(text);
    }

    const hiddenTickvals = [];
    const n = texts.length;
    if (n > 0 && tickIndices && tickIndices.length === n) {
        const SAFE_PIXEL_RADIUS = 40;
        let safeIndexRadius = 0.5;
        try {
            const width = chartPixelWidth;
            let visSpan = null;
            if (state && state.visibleStartIdx != null && state.visibleEndIdx != null) {
                visSpan = Math.max(1, state.visibleEndIdx - state.visibleStartIdx);
            } else {
                let minIdx = tickIndices[0], maxIdx = tickIndices[0];
                for (let i = 1; i < tickIndices.length; i++) {
                    if (tickIndices[i] < minIdx) minIdx = tickIndices[i];
                    if (tickIndices[i] > maxIdx) maxIdx = tickIndices[i];
                }
                visSpan = Math.max(1, maxIdx - minIdx);
            }
            if (width && visSpan) { const pixelsPerIndex = width / visSpan; safeIndexRadius = SAFE_PIXEL_RADIUS / pixelsPerIndex; }
        } catch (e) {}

        for (let j = 0; j < n; j++) {
            const uj = units[j]; if (!uj) continue;
            if (levelOrder[uj] > levelOrder[baseUnit]) {
                const idxBig = tickIndices[j];
                for (let i = 0; i < n; i++) {
                    if (i === j) continue; if (!texts[i]) continue;
                    const ui = units[i]; if (!ui) continue;
                    if (levelOrder[ui] < levelOrder[uj]) {
                        const idxSmall = tickIndices[i];
                        if (Math.abs(idxSmall - idxBig) <= safeIndexRadius) { texts[i] = ""; hiddenTickvals.push(idxSmall); }
                    }
                }
            }
        }
    }

    const labels = [];
    for (let i = 0; i < texts.length; i++) {
        if (!texts[i]) labels.push("");
        else labels.push(highlight(texts[i], units[i]));
    }
    return { labels, hiddenTickvals };
}

function computeTimeTicks(tfName, tfData, state, chartPixelWidth) {
    const barsAll = tfData.bars || [];
    if (!barsAll.length) return { tickvals: [], ticktext: [] };

    const ts_all = [], idx_all = [];
    const wStart = (state && state.windowStart != null) ? state.windowStart : tfData.minIdx;
    const wEnd   = (state && state.windowEnd   != null) ? state.windowEnd   : tfData.maxIdx;

    for (const bar of barsAll) {
        if (bar.i < wStart || bar.i > wEnd) continue;
        const ts = bar.ts;
        if (!Number.isNaN(ts)) { ts_all.push(ts); idx_all.push(bar.i); }
    }
    if (!ts_all.length) {
        for (const bar of barsAll) { const ts = bar.ts; if (!Number.isNaN(ts)) { ts_all.push(ts); idx_all.push(bar.i); } }
    }
    if (!ts_all.length) return { tickvals: [], ticktext: [] };

    const anchorInfo = { yearFirstTradingDate: tfData.yearFirstTradingDate || {}, monthFirstTradingDate: tfData.monthFirstTradingDate || {} };
    const visibleStartIdx = state.visibleStartIdx;
    const visibleEndIdx   = state.visibleEndIdx;

    let visTimes = [];
    if (visibleStartIdx != null && visibleEndIdx != null) {
        for (let i = 0; i < idx_all.length; i++) {
            const idx = idx_all[i];
            if (idx >= visibleStartIdx && idx <= visibleEndIdx) visTimes.push(new Date(ts_all[i]));
        }
    }
    if (!visTimes.length) visTimes = ts_all.map(ms => new Date(ms));
    if (!visTimes.length) return { tickvals: [], ticktext: [] };

    const startTime = visTimes[0], endTime = visTimes[visTimes.length - 1];
    const realSpanMinutes = Math.max(1, Math.round((endTime.getTime() - startTime.getTime()) / 60000.0));
    
    const diffs = [];
    for (let i = 1; i < visTimes.length; i++) {
        const dtMin = (visTimes[i].getTime() - visTimes[i - 1].getTime()) / 60000.0;
        if (dtMin > 0) diffs.push(dtMin);
    }
    let medianStepMin;
    if (diffs.length) {
        const sorted = diffs.slice().sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        medianStepMin = (sorted.length % 2 === 0) ? 0.5 * (sorted[mid - 1] + sorted[mid]) : sorted[mid];
    } else { medianStepMin = realSpanMinutes; }

    const dayMinutes = 24 * 60;
    let data_is_intraday = medianStepMin < 20 * 60;
    let data_is_daily_base = !data_is_intraday && medianStepMin >= 0.5 * dayMinutes && medianStepMin <= 1.5 * dayMinutes;
    if (tfName === "H4") { data_is_intraday = false; data_is_daily_base = true; }
    const logicalSpanMinutes = medianStepMin * (visTimes.length - 1);
    const preferCalendarForIntraday = data_is_intraday && (logicalSpanMinutes / dayMinutes) >= 20;

    let max_ticks = 32;
    if (chartPixelWidth && chartPixelWidth > 0) {
        let effWidth = chartPixelWidth;
        if (state && state.viewStart != null && state.viewEnd != null && state.visibleStartIdx != null && state.visibleEndIdx != null) {
            const viewSpan = Math.abs(state.viewEnd - state.viewStart);
            const dataSpan = Math.max(0, state.visibleEndIdx - state.visibleStartIdx);
            if (viewSpan > 0 && dataSpan >= 0) {
                const frac = Math.max(0.05, Math.min(1, dataSpan / viewSpan));
                effWidth = chartPixelWidth * frac;
            }
        }
        max_ticks = Math.max(2, Math.floor(effWidth / 72));
    }

    function searchsortedLeft(arr, value) {
        let lo = 0, hi = arr.length;
        while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] < value) lo = mid + 1; else hi = mid; }
        return lo;
    }

    function projectTicks(candTicks, useMappedDatetime) {
        const vals = [], dts = [];
        for (const dt of candTicks) {
            const ts = dt.getTime();
            const pos = searchsortedLeft(ts_all, ts);
            if (pos >= ts_all.length) continue;
            const barIdx = idx_all[pos];
            if (visibleStartIdx != null && barIdx < (visibleStartIdx - 1)) continue;
            if (visibleEndIdx   != null && barIdx > (visibleEndIdx   + 1)) continue;
            if (vals.length && barIdx === vals[vals.length - 1]) continue;
            vals.push(barIdx);
            dts.push(useMappedDatetime ? new Date(ts_all[pos]) : dt);
        }
        return { vals, dts };
    }

    let useIntradayGrid = false, intervalCode = null, tickDtList = null;
    if (data_is_intraday && !preferCalendarForIntraday) {
        const intradaySteps = [["15min", 15], ["30min", 30], ["1h", 60], ["2h", 120], ["4h", 240], ["8h", 480], ["12h", 720]];
        let best = null;
        for (const [code, step] of intradaySteps) {
            const candTicks = generateIntradayTicks(startTime, endTime, step);
            if (!candTicks.length) continue;
            const proj = projectTicks(candTicks, false);
            if (proj.vals.length > 0 && proj.vals.length <= max_ticks) {
                if (!best || proj.vals.length > best.nVis) best = { code, candTicks, nVis: proj.vals.length };
            }
        }
        if (best) { useIntradayGrid = true; intervalCode = best.code; tickDtList = best.candTicks; }
    }

    if (!tickDtList || !tickDtList.length) {
        const calendarCandidates = data_is_daily_base ? ["day_all", "day_mwf", "week_mon", "month", "quarter", "year"] : ["day", "day_mwf", "week_mon", "month", "quarter", "year"];
        let best = null, fallback = null;
        for (const code of calendarCandidates) {
            const candTicks = generateCalendarTicks(startTime, endTime, code);
            if (!candTicks.length) continue;
            const proj = projectTicks(candTicks, false);
            const nVis = proj.vals.length;
            if (!nVis) continue;
            fallback = { code, candTicks, nVis };
            if (nVis <= max_ticks) {
                if (!best || nVis > best.nVis) best = { code, candTicks, nVis };
            }
        }
        const chosen = best || fallback;
        if (chosen) { intervalCode = chosen.code; tickDtList = chosen.candTicks; }
    }

    if (!tickDtList || !tickDtList.length) return { tickvals: [], ticktext: [] };

    const useMappedDatetime = data_is_intraday && useIntradayGrid;
    let projected = projectTicks(tickDtList, useMappedDatetime);
    let tickvals = projected.vals;
    let tickDatetimes = projected.dts;

    if (!tickvals.length) return { tickvals: [], ticktext: [] };

    if (["day", "day_all", "day_mwf", "week_mon"].includes(intervalCode)) {
        const mft = tfData.monthFirstTradingDate || {};
        const extra = [];
        const visStartCheck = (visibleStartIdx != null) ? visibleStartIdx - 1 : null;
        const visEndCheck   = (visibleEndIdx   != null) ? visibleEndIdx   + 1 : null;

        for (const [ymKey, dateStr] of Object.entries(mft)) {
            const parts = dateStr.split("-");
            if (parts.length !== 3) continue;
            const yy = Number(parts[0]), mm = Number(parts[1]), dd = Number(parts[2]);
            if (!yy || !mm || !dd) continue;
            const anchorMs = Date.UTC(yy, mm - 1, dd);
            if (anchorMs < startTime.getTime() - 2 * 86400000 || anchorMs > endTime.getTime() + 2 * 86400000) continue;
            const pos = searchsortedLeft(ts_all, anchorMs);
            if (pos >= ts_all.length) continue;
            const barIdx = idx_all[pos];
            if (visStartCheck != null && barIdx < visStartCheck) continue;
            if (visEndCheck   != null && barIdx > visEndCheck)   continue;
            if (tickvals.includes(barIdx)) continue;
            
            let duplicateDate = false;
            for (const dtExisting of tickDatetimes) {
                if (dtExisting.getUTCFullYear() === yy && dtExisting.getUTCMonth() === (mm - 1) && dtExisting.getUTCDate() === dd) { duplicateDate = true; break; }
            }
            if (duplicateDate) continue;
            extra.push({ idx: barIdx, dt: new Date(anchorMs) });
        }
        if (extra.length) {
            const combined = [];
            for (let i = 0; i < tickvals.length; i++) combined.push({ idx: tickvals[i], dt: tickDatetimes[i] });
            for (const e of extra) combined.push(e);
            combined.sort((a, b) => a.idx - b.idx);
            const newVals = [], newDts = [];
            for (const item of combined) {
                if (newVals.length && item.idx === newVals[newVals.length - 1]) continue;
                newVals.push(item.idx); newDts.push(item.dt);
            }
            tickvals = newVals; tickDatetimes = newDts;
        }
    }

    const labelInfo = formatTickLabels(tickDatetimes, intervalCode, anchorInfo, tickvals, state, chartPixelWidth);
    console.log("[ticks]", tfName, "width=", chartPixelWidth, "mode=", intervalCode, "nTicks=", tickvals.length);

    return { tickvals, ticktext: labelInfo.labels, hiddenTickvals: labelInfo.hiddenTickvals || [] };
}

// --- Traces Builders ---

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
            logicalCloseTs = box.signalTs + (PHASE2_SIGNAL_BASE_MINUTES || 5) * 60 * 1000;
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
        if (pane === "left" && maxAllowedTs != null) {
            let checkTs = (tr.entryTs != null && Number.isFinite(tr.entryTs)) ? tr.entryTs : tr.entryWindowEndTs;
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
        if (tr.entryWindowEndTs != null && Number.isFinite(tr.entryWindowEndTs)) {
            let posFirstAfter = findPosGEByTs(tfData, tr.entryWindowEndTs);
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

// --- Chart Construction ---

function buildFigureForState(tf, tfData, state, yRange, autoY, chartPixelWidth, pane) {
    const { windowStart, windowEnd, visibleStartIdx, visibleEndIdx } = state;
    if (windowEnd < windowStart) {
        return {
            fig: { data: [], layout: { title: `${tf} – no data`, plot_bgcolor: BACKGROUND_COLOR, paper_bgcolor: BACKGROUND_COLOR }, config: PLOT_CONFIG },
            visibleTimeRange: null, usedYRange: yRange
        };
    }

    const windowBars = sliceBarsForRange(tfData, windowStart, windowEnd);
    const visibleBarsArr = sliceBarsForRange(tfData, visibleStartIdx, visibleEndIdx);
    const x = [], open = [], high = [], low = [], close = [], customdata = [];
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

    const tickInfo = computeTimeTicks(tf, tfData, state, chartPixelWidth);
    const shapes = [];
    if (tickInfo.ticktext && tickInfo.tickvals && tickInfo.ticktext.length === tickInfo.tickvals.length) {
        for (let i = 0; i < tickInfo.tickvals.length; i++) {
            if (tickInfo.ticktext[i]) {
                shapes.push({ type: "line", xref: "x", yref: "paper", x0: tickInfo.tickvals[i], x1: tickInfo.tickvals[i], y0: 0, y1: -0.006, line: { color: FOREGROUND_COLOR, width: 1 }, layer: "above" });
            }
        }
    }

    const priceTrace = {
        type: "candlestick", x, open, high, low, close, customdata, name: "Price",
        increasing: { line: { color: WICK_OUTLINE_COLOR }, fillcolor: BULL_BODY_COLOR },
        decreasing: { line: { color: WICK_OUTLINE_COLOR }, fillcolor: BEAR_BODY_COLOR },
        line: { width: 1 }, hoverinfo: candleHoverOn ? "x+y" : "none", showlegend: false
    };

    const allTraces = []
        .concat(buildSessionTraces(tf, tfData, state, windowBars, visibleBarsArr))
        .concat(buildPhase2Traces(tf, tfData, windowBars, windowStart, windowEnd, pane))
        .concat(buildPhase3Traces(tf, tfData, windowBars, windowStart, windowEnd, pane))
        .concat([priceTrace]);

    let yAxisSide = (pane === "left") ? "left" : "right";
    let margin = (pane === "left") ? { l: 60, r: 10, t: 20, b: 40 } : { l: 10, r: 60, t: 20, b: 40 };

    const layout = {
        title: `${DATA.symbol} – ${tf} (NY)`,
        xaxis: {
            title: "", rangeslider: { visible: false }, showgrid: false, showline: true, linewidth: 1, linecolor: "black", mirror: true,
            ticks: "outside", ticklen: 5, tickcolor: BACKGROUND_COLOR, tickpadding: 5, fixedrange: axisMode === "y", range: xRange,
            tickmode: (tickInfo.tickvals && tickInfo.tickvals.length) ? "array" : "auto",
            tickvals: (tickInfo.tickvals && tickInfo.tickvals.length) ? tickInfo.tickvals : undefined,
            ticktext: (tickInfo.ticktext && tickInfo.ticktext.length) ? tickInfo.ticktext : undefined,
        },
        yaxis: { side: yAxisSide, tickformat: ".5f", showgrid: false, showline: true, linewidth: 1, linecolor: "black", mirror: true, ticks: "outside", fixedrange: axisMode === "x", range: finalYRange },
        hovermode: "x", dragmode: "pan", plot_bgcolor: BACKGROUND_COLOR, paper_bgcolor: BACKGROUND_COLOR, font: { color: FOREGROUND_COLOR, size: 11 },
        shapes: shapes, margin: margin, showlegend: false
    };

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

function handleRelayoutingForPane(pane, ev) {
    if (isRelayoutFromCode || !DATA) return;
    const isLeft = (pane === "left");
    const tf = isLeft ? currentTfLeft : currentTf;
    const tfData = DATA.timeframes[tf];
    if (!tfData) return;

    let hasX = false, v0 = null, v1 = null;
    if (ev["xaxis.range[0]"] !== undefined && ev["xaxis.range[1]"] !== undefined) {
        v0 = parseFloat(ev["xaxis.range[0]"]); v1 = parseFloat(ev["xaxis.range[1]"]);
        if (isFinite(v0) && isFinite(v1)) hasX = true;
    }

    let state = isLeft ? TF_STATE_LEFT[tf] : TF_STATE[tf];
    if (!state) state = computeWindowForTf(tfData, DEFAULT_VISIBLE_BARS, null);

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

        if (right >= left) {
            let visibleStartIdx = left + 0.5, visibleEndIdx = right - 0.5;
            if (visibleEndIdx < visibleStartIdx) { const tmp = visibleStartIdx; visibleStartIdx = visibleEndIdx; visibleEndIdx = tmp; }
            const approxVisibleBars = Math.max(1, Math.round(visibleEndIdx - visibleStartIdx + 1));
            const centerIdx = 0.5 * (visibleStartIdx + visibleEndIdx);
            let baseState = computeWindowForTf(tfData, approxVisibleBars, centerIdx);
            baseState.visibleStartIdx = visibleStartIdx; baseState.visibleEndIdx = visibleEndIdx;
            baseState.visibleBars = Math.max(1, visibleEndIdx - visibleStartIdx + 1);
            baseState.viewStart = viewStart; baseState.viewEnd = viewEnd;
            state = baseState;
        } else { state.viewStart = viewStart; state.viewEnd = viewEnd; }
    }

    if (isLeft) TF_STATE_LEFT[tf] = state; else TF_STATE[tf] = state;

    if (state.visibleStartIdx != null && state.visibleEndIdx != null) {
        const bars = tfData.bars || [];
        const minIdx = tfData.minIdx;
        const posL = Math.max(0, state.visibleStartIdx - minIdx);
        const posR = Math.min(bars.length - 1, state.visibleEndIdx - minIdx);
        const regState = isLeft ? REGIME_STATE_LEFT[getRegime(tf, "left")] : REGIME_STATE[getRegime(tf)];
        if (regState && bars[posL] && bars[posR]) {
            regState.timeRange = [bars[posL].t, bars[posR].t];
            regState.anchorTime = bars[posR].t;
            regState.visibleBarsHint = state.visibleBars;
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