// view_engine.js

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