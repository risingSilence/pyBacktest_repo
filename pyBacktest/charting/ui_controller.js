// ui_controller.js

function renderSetupDropdown() {
    const select = document.getElementById("setup-select");
    if (!select) return;
    const prevValue = select.value;
    select.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = ""; placeholder.disabled = true; placeholder.selected = true; placeholder.hidden = true;
    select.appendChild(placeholder);

    if (!SETUPS || !SETUPS.length) return;
    const sorted = getSortedSetups();
    SETUP_BY_ID = {};
    for (const s of sorted) SETUP_BY_ID[String(s.id)] = s;

    sorted.forEach((setup) => {
        const opt = document.createElement("option");
        opt.value = String(setup.id); opt.textContent = setup.label;
        select.appendChild(opt);
    });
    if (prevValue && SETUP_BY_ID[prevValue]) select.value = prevValue;
    else select.value = "";
}

function buildTfSelects() {
    const tfSelect = document.getElementById("tf-select");
    const tfSelectLeft = document.getElementById("tf-select-left");
    if (!tfSelect || !tfSelectLeft) return;
    tfSelect.innerHTML = ""; tfSelectLeft.innerHTML = "";

    const invalidForLtf = ["W", "M"];
    const invalidForHtf = ["M1", "M3", "M5"];

    TF_LIST.forEach((tf) => {
        if (!invalidForLtf.includes(tf)) {
            const optMain = document.createElement("option");
            optMain.value = tf; optMain.textContent = tf;
            if (tf === currentTf) optMain.selected = true;
            tfSelect.appendChild(optMain);
        }
        if (!invalidForHtf.includes(tf)) {
            const optLeft = document.createElement("option");
            optLeft.value = tf; optLeft.textContent = tf;
            if (tf === currentTfLeft) optLeft.selected = true;
            tfSelectLeft.appendChild(optLeft);
        }
    });

    tfSelect.addEventListener("change", (e) => {
        const newTf = e.target.value;
        if (newTf && newTf !== currentTf) { onTfChange(newTf); savePersistentState(); }
    });
    tfSelectLeft.addEventListener("change", (e) => {
        const newTf = e.target.value;
        if (newTf && newTf !== currentTfLeft) { onTfChangeLeft(newTf); savePersistentState(); }
    });
}

function updatePhaseDropdowns(newPhase2Files, newPhase3Files) {
    const p2Select = document.getElementById("phase2-file-select");
    const p3Select = document.getElementById("phase3-file-select");
    if (!p2Select || !p3Select) return;

    phase2Files = newPhase2Files || [];
    phase3Files = newPhase3Files || [];
    const currentP2 = phase2File, currentP3 = phase3File;

    p2Select.innerHTML = "";
    if (!phase2Files.length) {
        const opt = document.createElement("option"); opt.value = ""; opt.textContent = "(no setups files found)"; p2Select.appendChild(opt); phase2File = null;
    } else {
        phase2Files.forEach(fn => { const opt = document.createElement("option"); opt.value = fn; opt.textContent = fn; p2Select.appendChild(opt); });
        if (currentP2 && phase2Files.includes(currentP2)) phase2File = currentP2;
        else phase2File = phase2Files[0];
        p2Select.value = phase2File || "";
    }

    p3Select.innerHTML = "";
    if (!phase3Files.length) {
        const opt = document.createElement("option"); opt.value = ""; opt.textContent = "(no trades files found)"; p3Select.appendChild(opt); phase3File = null;
    } else {
        phase3Files.forEach(fn => { const opt = document.createElement("option"); opt.value = fn; opt.textContent = fn; p3Select.appendChild(opt); });
        if (currentP3 && phase3Files.includes(currentP3)) phase3File = currentP3;
        else phase3File = phase3Files[0];
        p3Select.value = phase3File || "";
    }
}

function syncUiToState() {
    const tfSelect = document.getElementById("tf-select"); if (tfSelect) tfSelect.value = currentTf;
    const tfSelectLeft = document.getElementById("tf-select-left"); if (tfSelectLeft) tfSelectLeft.value = currentTfLeft;
    const hoverToggle = document.getElementById("candle-hover-toggle"); if (hoverToggle) hoverToggle.checked = !!candleHoverOn;
    const sessionInput = document.getElementById("session-days"); if (sessionInput) sessionInput.value = String(sessionDays);
    const showMissesToggle = document.getElementById("show-misses-toggle"); if (showMissesToggle) showMissesToggle.checked = !!SHOW_MISSES;
    const showSignalsToggle = document.getElementById("show-signals-toggle"); if (showSignalsToggle) showSignalsToggle.checked = !!SHOW_SIGNALS;
    const setupSortSelect = document.getElementById("setup-sort-select"); if (setupSortSelect) setupSortSelect.value = SETUP_SORT_MODE;
    const viewModeInputs = document.querySelectorAll('#view-mode input[name="view-mode"]');
    viewModeInputs.forEach((input) => { input.checked = (input.value === VIEW_MODE); });
    const htfBehaviorSelect = document.getElementById("htf-behavior-select"); if (htfBehaviorSelect) htfBehaviorSelect.value = HTF_BEHAVIOR;
}

function onCandleHoverToggle(checked) {
    candleHoverOn = checked;
    const hoverInfoValue = candleHoverOn ? "x+y" : "none";
    const gd = document.getElementById("m1-chart");
    if (gd && gd.data && gd.data.length) {
        const candleIndices = [];
        gd.data.forEach((tr, idx) => { if (tr && tr.type === "candlestick") candleIndices.push(idx); });
        if (candleIndices.length) Plotly.restyle("m1-chart", { hoverinfo: hoverInfoValue }, candleIndices);
    }
    savePersistentState();
}

function onHtfBehaviorChange(newBehavior) {
    if (newBehavior !== HTF_BEHAVIOR_INDEPENDENT && newBehavior !== HTF_BEHAVIOR_FOLLOW_SNAP && newBehavior !== HTF_BEHAVIOR_FOLLOW_STRICT) return;
    if (HTF_BEHAVIOR === newBehavior) { const sel = document.getElementById("htf-behavior-select"); if (sel) sel.value = HTF_BEHAVIOR; return; }

    HTF_BEHAVIOR = newBehavior;
    if (HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_STRICT) clearHtfSnapshot({ clearSetupSelect: false });

    if (HTF_BEHAVIOR === HTF_BEHAVIOR_INDEPENDENT) {
        HTF_FOLLOW_ACTIVE = false; HTF_FOLLOW_TFDATA = null; HTF_FOLLOW_INFO = null;
        if (VIEW_MODE === VIEW_MODE_SPLIT && DATA && DATA.timeframes[currentTfLeft]) {
            const tfDataL = DATA.timeframes[currentTfLeft];
            let stateL = TF_STATE_LEFT[currentTfLeft];
            if (!stateL) stateL = computeWindowForTfRightAnchored(tfDataL, DEFAULT_VISIBLE_BARS, tfDataL.maxIdx);
            const regimeL = getRegime(currentTfLeft, "left");
            const regStateL = REGIME_STATE_LEFT[regimeL] || {};
            applyStateAndRenderLeft(currentTfLeft, stateL, { autoY: false, yRangeOverride: regStateL.yRange });
        }
    } else {
        if (VIEW_MODE === VIEW_MODE_SPLIT && TF_STATE[currentTf]) updateHtfFollowFromLtf(TF_STATE[currentTf]);
    }
    savePersistentState();
}

function onViewModeChange(mode) {
    if (mode !== VIEW_MODE_SINGLE && mode !== VIEW_MODE_SPLIT) return;
    const oldMode = VIEW_MODE;
    if (oldMode === mode) {
        const inputsSame = document.querySelectorAll('#view-mode input[name="view-mode"]');
        inputsSame.forEach((input) => { input.checked = (input.value === mode); });
        return;
    }
    VIEW_MODE = mode;
    if (mode === VIEW_MODE_SINGLE) clearHtfSnapshot();

    const inputs = document.querySelectorAll('#view-mode input[name="view-mode"]');
    inputs.forEach((input) => { input.checked = (input.value === mode); });

    updateLayoutForViewMode();

    window.requestAnimationFrame(() => {
        let factor = 1;
        if (oldMode === VIEW_MODE_SINGLE && mode === VIEW_MODE_SPLIT) factor = 0.5;
        else if (oldMode === VIEW_MODE_SPLIT && mode === VIEW_MODE_SINGLE) factor = 2.0;
        
        reanchorRightChartToRightEdge(factor);

        if (VIEW_MODE === VIEW_MODE_SPLIT && (HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_SNAP || HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_STRICT) && TF_STATE[currentTf]) {
            updateHtfFollowFromLtf(TF_STATE[currentTf]);
        }
        try { Plotly.Plots.resize("m1-chart"); if (VIEW_MODE === VIEW_MODE_SPLIT) Plotly.Plots.resize("htf-chart"); } catch (e) {}
        savePersistentState();
    });
}

function onAxisModeChange(mode) {
    axisMode = mode;
    const update = {};
    if (mode === "both") { update["xaxis.fixedrange"] = false; update["yaxis.fixedrange"] = false; }
    else if (mode === "x") { update["xaxis.fixedrange"] = false; update["yaxis.fixedrange"] = true; }
    else if (mode === "y") { update["xaxis.fixedrange"] = true; update["yaxis.fixedrange"] = false; }

    try { Plotly.relayout("m1-chart", update); } catch (e) {}
    try { const htfEl = document.getElementById("htf-chart"); if (htfEl && VIEW_MODE === VIEW_MODE_SPLIT) Plotly.relayout("htf-chart", update); } catch (e) {}
    savePersistentState();
}

function onTfChange(newTf) {
    if (newTf === currentTf) return;
    const oldTf = currentTf;
    const oldRegime = getRegime(oldTf);
    const newRegime = getRegime(newTf);
    currentTf = newTf;

    const tfDataNew = DATA.timeframes[newTf];
    if (!tfDataNew) { console.warn("No data for TF", newTf); return; }
    if (!PHASE2_BASE_TF) getPhase2BaseTfData();

    const regStateOld = REGIME_STATE[oldRegime];
    const regStateNew = REGIME_STATE[newRegime];

    if (oldRegime === newRegime) {
        const timeRange = regStateOld.timeRange;
        const yRange = regStateOld.yRange;
        const state = computeWindowFromTimeRangeExact(tfDataNew, timeRange);
        const oldState = TF_STATE[oldTf];
        if (oldState && oldState.visibleEndIdx != null && oldState.visibleStartIdx != null) {
            const oldSpan = oldState.visibleEndIdx - oldState.visibleStartIdx;
            const newSpan = state.visibleEndIdx - state.visibleStartIdx;
            if (oldSpan > 0 && newSpan > 0) {
                if (oldState.viewEnd != null) {
                    const oldBarEdgeR = oldState.visibleEndIdx + 0.5;
                    const oldGapR = oldState.viewEnd - oldBarEdgeR;
                    state.viewEnd = (state.visibleEndIdx + 0.5) + (newSpan * (oldGapR / oldSpan));
                }
                if (oldState.viewStart != null) {
                    const oldBarEdgeL = oldState.visibleStartIdx - 0.5;
                    const oldGapL = oldBarEdgeL - oldState.viewStart;
                    state.viewStart = (state.visibleStartIdx - 0.5) - (newSpan * (oldGapL / oldSpan));
                }
            }
        }
        applyStateAndRender(newTf, state, { autoY: false, yRangeOverride: yRange });
        return;
    }

    const anchorTime = regStateOld.anchorTime;
    let anchorIdx = null;
    if (anchorTime && tfDataNew.bars && tfDataNew.bars.length) {
        const anchorTs = parseNyIsoToMs(anchorTime);
        const pos = findPosLEByTs(tfDataNew, anchorTs);
        if (pos !== null) anchorIdx = tfDataNew.bars[pos].i;
    }

    let visibleBars = regStateNew.visibleBarsHint && regStateNew.visibleBarsHint > 0 ? regStateNew.visibleBarsHint : DEFAULT_VISIBLE_BARS;
    const lastTf = regStateNew.lastTf;
    if (lastTf && lastTf !== newTf) {
        const minOld = tfToMinutes(lastTf), minNew = tfToMinutes(newTf);
        if (minOld && minNew) {
            const ratio = minOld / minNew;
            visibleBars = Math.round(visibleBars * ratio);
            if (visibleBars < 10) visibleBars = 10;
        }
    }

    const state = computeWindowForTfRightAnchored(tfDataNew, visibleBars, anchorIdx);
    if (!regStateNew.initialized) applyStateAndRender(newTf, state, { autoY: true });
    else applyStateAndRender(newTf, state, { autoY: false, yRangeOverride: regStateNew.yRange });
}

function onTfChangeLeft(newTf) {
    if (newTf === currentTfLeft) return;
    const wasSnapshotActive = HTF_SNAPSHOT_ACTIVE;
    const preservedSnapshotInfo = HTF_SNAPSHOT_INFO;
    const preservedMaxSignalTs = HTF_SNAPSHOT_MAX_SIGNAL_TS;
    clearHtfSnapshot();

    const oldTf = currentTfLeft;
    const oldRegime = getRegime(oldTf, "left");
    const newRegime = getRegime(newTf, "left");
    currentTfLeft = newTf;

    let tfDataNew = DATA.timeframes[newTf];
    if (!tfDataNew) { console.warn("No data for TF (left)", newTf); return; }
    const m1Data = DATA.timeframes["M1"];
    let snapshotRestored = false;

    if (wasSnapshotActive && preservedSnapshotInfo && preservedSnapshotInfo.snapshotTime && m1Data) {
        const snapshot = buildHtfSnapshotData(newTf, tfDataNew, m1Data, preservedSnapshotInfo.snapshotTime);
        if (snapshot) {
            HTF_SNAPSHOT_ACTIVE = true; HTF_SNAPSHOT_TFDATA = snapshot.htfSnapshotData;
            HTF_SNAPSHOT_INFO = { ...preservedSnapshotInfo, tf: newTf, htfBarIndex: snapshot.htfBarIndex };
            HTF_SNAPSHOT_MAX_SIGNAL_TS = preservedMaxSignalTs;
            if (preservedSnapshotInfo.setupId != null && SETUP_BY_ID) {
                const setup = SETUP_BY_ID[String(preservedSnapshotInfo.setupId)];
                if (setup && setup.boxRef) setup.boxRef.isSnapshotActive = true;
            }
            tfDataNew = HTF_SNAPSHOT_TFDATA;
            snapshotRestored = true;
        }
    }

    if (!snapshotRestored) {
        const isFollowMode = (VIEW_MODE === VIEW_MODE_SPLIT && (HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_SNAP || HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_STRICT));
        if (isFollowMode && TF_STATE[currentTf]) {
            const stateRight = TF_STATE[currentTf];
            const tfRight = currentTf;
            if (stateRight.visibleEndIdx != null) {
                const tfDataRight = DATA.timeframes[tfRight];
                if (tfDataRight && m1Data) {
                    let lastIdx = Math.round(stateRight.visibleEndIdx);
                    lastIdx = Math.max(tfDataRight.minIdx, Math.min(tfDataRight.maxIdx, lastIdx));
                    const posRight = lastIdx - tfDataRight.minIdx;
                    if (posRight >= 0 && posRight < tfDataRight.bars.length) {
                        const lastBarRight = tfDataRight.bars[posRight];
                        const ltfDurMs = timeframeToMs(tfRight);
                        if (lastBarRight && ltfDurMs) {
                            const snapshotTime = lastBarRight.ts + ltfDurMs;
                            const snapshot = buildHtfSnapshotData(newTf, DATA.timeframes[newTf], m1Data, snapshotTime);
                            if (snapshot) {
                                HTF_FOLLOW_ACTIVE = true; HTF_FOLLOW_TFDATA = snapshot.htfSnapshotData;
                                HTF_FOLLOW_INFO = { tf: newTf, snapshotTime: snapshotTime, htfBarIndex: snapshot.htfBarIndex };
                                tfDataNew = HTF_FOLLOW_TFDATA;
                            }
                        }
                    }
                }
            }
        } else {
            HTF_FOLLOW_ACTIVE = false; HTF_FOLLOW_TFDATA = null; HTF_FOLLOW_INFO = null;
        }
    }

    const regStateOld = REGIME_STATE_LEFT[oldRegime];
    const regStateNew = REGIME_STATE_LEFT[newRegime];

    if (oldRegime === newRegime) {
        const timeRange = regStateOld.timeRange;
        const yRange = regStateOld.yRange;
        const state = computeWindowFromTimeRangeExact(tfDataNew, timeRange);
        const oldState = TF_STATE_LEFT[oldTf];
        if (oldState && oldState.visibleEndIdx != null && oldState.visibleStartIdx != null) {
            const oldSpan = oldState.visibleEndIdx - oldState.visibleStartIdx;
            const newSpan = state.visibleEndIdx - state.visibleStartIdx;
            if (oldSpan > 0 && newSpan > 0) {
                if (oldState.viewEnd != null) {
                    const oldBarEdgeR = oldState.visibleEndIdx + 0.5;
                    const oldGapR = oldState.viewEnd - oldBarEdgeR;
                    state.viewEnd = (state.visibleEndIdx + 0.5) + (newSpan * (oldGapR / oldSpan));
                }
                if (oldState.viewStart != null) {
                    const oldBarEdgeL = oldState.visibleStartIdx - 0.5;
                    const oldGapL = oldBarEdgeL - oldState.viewStart;
                    state.viewStart = (state.visibleStartIdx - 0.5) - (newSpan * (oldGapL / oldSpan));
                }
            }
        }
        applyStateAndRenderLeft(newTf, state, { autoY: false, yRangeOverride: yRange });
        return;
    }

    const anchorTime = regStateOld.anchorTime;
    let anchorIdx = null;
    if (anchorTime && tfDataNew.bars && tfDataNew.bars.length) {
        const anchorTs = parseNyIsoToMs(anchorTime);
        const pos = findPosLEByTs(tfDataNew, anchorTs);
        if (pos !== null) anchorIdx = tfDataNew.bars[pos].i;
    }
    if (anchorIdx === null && tfDataNew.bars.length > 0) anchorIdx = tfDataNew.maxIdx;

    let visibleBars = regStateNew.visibleBarsHint && regStateNew.visibleBarsHint > 0 ? regStateNew.visibleBarsHint : DEFAULT_VISIBLE_BARS;
    const lastTf = regStateNew.lastTf;
    if (lastTf && lastTf !== newTf) {
        const minOld = tfToMinutes(lastTf), minNew = tfToMinutes(newTf);
        if (minOld && minNew) {
            const ratio = minOld / minNew;
            visibleBars = Math.round(visibleBars * ratio);
            if (visibleBars < 10) visibleBars = 10;
        }
    }

    const state = computeWindowForTfRightAnchored(tfDataNew, visibleBars, anchorIdx);
    if (!regStateNew.initialized) applyStateAndRenderLeft(newTf, state, { autoY: true });
    else applyStateAndRenderLeft(newTf, state, { autoY: false, yRangeOverride: regStateNew.yRange });
}

function updateLayoutForViewMode() {
    const container = document.getElementById("chart-container");
    const leftWrap  = document.getElementById("left-chart-wrapper");
    const rightWrap = document.getElementById("right-chart-wrapper");
    const splitter  = document.getElementById("chart-splitter");
    if (!rightWrap) return;

    if (VIEW_MODE === VIEW_MODE_SPLIT) {
        if (leftWrap) leftWrap.style.display = "block";
        if (splitter) splitter.style.display = "block";
        if (container && leftWrap && rightWrap) {
            const containerRect = container.getBoundingClientRect();
            const splitterRect  = splitter ? splitter.getBoundingClientRect() : null;
            const splitterWidth = splitterRect && splitterRect.width ? splitterRect.width : 3;
            const totalWidth    = containerRect.width || rightWrap.clientWidth + (leftWrap ? leftWrap.clientWidth : 0);
            const usableWidth = Math.max(100, totalWidth - splitterWidth);
            const leftPx  = usableWidth * SPLIT_LEFT_FRACTION;
            const rightPx = usableWidth - leftPx;
            leftWrap.style.flex  = `0 0 ${leftPx}px`;
            rightWrap.style.flex = `0 0 ${rightPx}px`;
        }
        if (DATA && DATA.timeframes) {
            if (!DATA.timeframes[currentTfLeft]) {
                const available = Object.keys(DATA.timeframes);
                if (available.length) currentTfLeft = available[0];
            }
            const tfDataL = DATA.timeframes[currentTfLeft];
            if (tfDataL) {
                let stateL = TF_STATE_LEFT[currentTfLeft];
                const regimeL   = getRegime(currentTfLeft, "left");
                const regStateL = REGIME_STATE_LEFT[regimeL] || {};
                if (!stateL) stateL = computeWindowForTfRightAnchored(tfDataL, DEFAULT_VISIBLE_BARS, tfDataL.maxIdx);
                applyStateAndRenderLeft(currentTfLeft, stateL, { autoY: !regStateL.initialized, yRangeOverride: regStateL.yRange });
            }
        }
    } else {
        if (leftWrap) leftWrap.style.display = "none";
        if (splitter) splitter.style.display = "none";
        rightWrap.style.flex = "1 1 100%";
    }

    bindPlotlyEventsOnce();

    if (container) {
        const oldOverflowX = container.style.overflowX;
        const oldOverflowY = container.style.overflowY;
        container.style.overflowX = "hidden";
        container.style.overflowY = "hidden";
        window.requestAnimationFrame(() => {
            try { Plotly.Plots.resize("m1-chart"); if (VIEW_MODE === VIEW_MODE_SPLIT) Plotly.Plots.resize("htf-chart"); } catch (e) { console.warn("Plotly resize after view mode change failed:", e); }
            finally { container.style.overflowX = oldOverflowX; container.style.overflowY = oldOverflowY; }
        });
    }
}

function initSplitterDrag() {
    const container = document.getElementById("chart-container");
    const leftWrap  = document.getElementById("left-chart-wrapper");
    const rightWrap = document.getElementById("right-chart-wrapper");
    const splitter  = document.getElementById("chart-splitter");
    if (!container || !leftWrap || !rightWrap || !splitter) return;

    const m1El  = document.getElementById("m1-chart");
    const htfEl = document.getElementById("htf-chart");
    if (m1El)  m1El.style.width  = "100%";
    if (htfEl) htfEl.style.width = "100%";

    let handle = document.getElementById("chart-splitter-handle");
    if (!handle) {
        handle = document.createElement("div"); handle.id = "chart-splitter-handle"; splitter.appendChild(handle);
    }
    Object.assign(handle.style, {
        position: "absolute", top: "0", left: "50%", transform: "translateX(-50%)", width: "14px", height: "100%",
        cursor: "col-resize", background: "transparent", pointerEvents: "auto", zIndex: 20
    });

    let dragBase = null, rafId = null, pendingWidths = null;

    function getEffectiveTfData(pane, tf) {
        if (pane === "left") {
            if (HTF_SNAPSHOT_ACTIVE && HTF_SNAPSHOT_TFDATA && HTF_SNAPSHOT_INFO && HTF_SNAPSHOT_INFO.tf === tf) return HTF_SNAPSHOT_TFDATA;
            if (HTF_FOLLOW_ACTIVE && HTF_FOLLOW_TFDATA && HTF_FOLLOW_INFO && HTF_FOLLOW_INFO.tf === tf) return HTF_FOLLOW_TFDATA;
        }
        return DATA.timeframes[tf];
    }

    function makePaneBase(paneId, tf) {
        const tfData = getEffectiveTfData(paneId, tf);
        if (!tfData) return null;
        let state = (paneId === "left") ? TF_STATE_LEFT[tf] : TF_STATE[tf];
        if (!state) state = computeWindowForTfRightAnchored(tfData, DEFAULT_VISIBLE_BARS, tfData.maxIdx);
        const baseVisibleBars = state.visibleBars || DEFAULT_VISIBLE_BARS;
        let anchorIdx = state.visibleEndIdx;
        if (anchorIdx == null || !isFinite(anchorIdx)) anchorIdx = tfData.maxIdx;
        
        let gapR = Math.max(1, Math.round(baseVisibleBars * 0.1));
        if (state.viewEnd != null && state.visibleEndIdx != null) { const raw = state.viewEnd - (state.visibleEndIdx + 0.5); if (isFinite(raw) && raw >= 0) gapR = raw; }
        
        let gapL = 0;
        if (state.viewStart != null && state.visibleStartIdx != null) { const raw = (state.visibleStartIdx - 0.5) - state.viewStart; if (isFinite(raw) && raw >= 0) gapL = raw; }
        return { paneId, tf, tfData, baseVisibleBars, anchorIdx, gapR, gapL };
    }

    function liveReanchor(paneBase, widthFactor) {
        if (!paneBase) return;
        const { paneId, tf, tfData, baseVisibleBars, anchorIdx, gapR, gapL } = paneBase;
        let visibleBars = Math.round(baseVisibleBars * widthFactor);
        if (visibleBars < 10) visibleBars = 10;
        const newState = computeWindowForTfRightAnchored(tfData, visibleBars, anchorIdx);
        newState.viewEnd = (newState.visibleEndIdx + 0.5) + gapR;
        newState.viewStart = (newState.visibleStartIdx - 0.5) - gapL;
        const regime = getRegime(tf, paneId);
        const regStateAll = (paneId === "left") ? REGIME_STATE_LEFT : REGIME_STATE;
        const regState = regStateAll[regime] || {};
        if (paneId === "left") applyStateAndRenderLeft(tf, newState, { autoY: false, yRangeOverride: regState.yRange });
        else applyStateAndRender(tf, newState, { autoY: false, yRangeOverride: regState.yRange });
    }

    function requestLiveUpdate() {
        if (rafId != null) return;
        rafId = requestAnimationFrame(() => {
            rafId = null;
            if (!dragBase || !pendingWidths) return;
            const { newLeftPx, newRightPx } = pendingWidths;
            pendingWidths = null;
            try { Plotly.Plots.resize("m1-chart"); } catch (e) {}
            if (VIEW_MODE === VIEW_MODE_SPLIT) { try { Plotly.Plots.resize("htf-chart"); } catch (e) {} }
            const factorLeft = newLeftPx / dragBase.leftWidth;
            const factorRight = newRightPx / dragBase.rightWidth;
            liveReanchor(dragBase.leftPane, factorLeft);
            liveReanchor(dragBase.rightPane, factorRight);
        });
    }

    handle.addEventListener("mousedown", (e) => {
        if (VIEW_MODE !== VIEW_MODE_SPLIT) return;
        e.preventDefault(); e.stopPropagation();
        const containerRect = container.getBoundingClientRect();
        const leftRect = leftWrap.getBoundingClientRect();
        const rightRect = rightWrap.getBoundingClientRect();
        const splitterRect = splitter.getBoundingClientRect();
        splitterContainerWidth = containerRect.width;
        splitterStartLeftWidth = leftRect.width;
        splitterStartRightWidth = rightRect.width;
        splitterWidthPx = splitterRect.width || 3;
        splitterStartX = e.clientX;
        isSplitterDragging = true;
        document.body.style.cursor = "col-resize";
        dragBase = {
            leftWidth: splitterStartLeftWidth, rightWidth: splitterStartRightWidth,
            leftPane: makePaneBase("left", currentTfLeft), rightPane: makePaneBase("right", currentTf),
        };
        pendingWidths = { newLeftPx: splitterStartLeftWidth, newRightPx: splitterStartRightWidth };
        requestLiveUpdate();
    });

    window.addEventListener("mousemove", (e) => {
        if (!isSplitterDragging || VIEW_MODE !== VIEW_MODE_SPLIT) return;
        const delta = e.clientX - splitterStartX;
        const minWidth = 80;
        let newLeft = splitterStartLeftWidth + delta;
        const maxLeft = splitterContainerWidth - splitterWidthPx - minWidth;
        if (newLeft < minWidth) newLeft = minWidth;
        if (newLeft > maxLeft) newLeft = maxLeft;
        const newRight = splitterContainerWidth - splitterWidthPx - newLeft;
        leftWrap.style.flex = `0 0 ${newLeft}px`;
        rightWrap.style.flex = `0 0 ${newRight}px`;
        pendingWidths = { newLeftPx: newLeft, newRightPx: newRight };
        requestLiveUpdate();
    });

    window.addEventListener("mouseup", () => {
        if (!isSplitterDragging) return;
        isSplitterDragging = false;
        document.body.style.cursor = "";
        if (!dragBase) return;
        const leftRect = leftWrap.getBoundingClientRect();
        const rightRect = rightWrap.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        const totalWidth = containerRect.width;
        const usableWidth = Math.max(1, totalWidth - splitterWidthPx);
        if (usableWidth > 0) {
            let frac = leftRect.width / usableWidth;
            frac = Math.min(0.9, Math.max(0.1, frac));
            SPLIT_LEFT_FRACTION = frac;
        }
        try { Plotly.Plots.resize("m1-chart"); if (VIEW_MODE === VIEW_MODE_SPLIT) Plotly.Plots.resize("htf-chart"); } catch (e) {}
        const factorLeft = leftRect.width / dragBase.leftWidth;
        const factorRight = rightRect.width / dragBase.rightWidth;
        liveReanchor(dragBase.leftPane, factorLeft);
        liveReanchor(dragBase.rightPane, factorRight);
        dragBase = null; pendingWidths = null;
        if (rafId != null) { cancelAnimationFrame(rafId); rafId = null; }
        savePersistentState();
    });
}

function reapplyStateFromStorage() {
    const ok = restorePersistentState();
    if (!ok) { console.warn("[restart] reapplyStateFromStorage: restorePersistentState() failed"); return; }
    if (!DATA || !DATA.timeframes || !DATA.timeframes[currentTf]) { console.warn("[restart] reapplyStateFromStorage: no data for currentTf"); return; }

    if (!DATA.timeframes[currentTf]) {
        const available = Object.keys(DATA.timeframes);
        if (available.length > 0) currentTf = available[0];
    }
    if (!DATA.timeframes[currentTfLeft]) {
        const available = Object.keys(DATA.timeframes);
        if (available.length > 0) currentTfLeft = available[0];
    }

    const tfDataR = DATA.timeframes[currentTf];
    let stateR = TF_STATE[currentTf];
    if (!stateR) stateR = computeWindowForTf(tfDataR, DEFAULT_VISIBLE_BARS, tfDataR.maxIdx);
    const regimeR = getRegime(currentTf);
    const regStateR = REGIME_STATE[regimeR] || {};
    applyStateAndRender(currentTf, stateR, { autoY: false, yRangeOverride: regStateR.yRange });

    if (VIEW_MODE === VIEW_MODE_SPLIT && DATA.timeframes[currentTfLeft]) {
        const tfDataL = DATA.timeframes[currentTfLeft];
        let stateL = TF_STATE_LEFT[currentTfLeft];
        if (!stateL) stateL = computeWindowForTf(tfDataL, DEFAULT_VISIBLE_BARS, tfDataL.maxIdx);
        const regimeL = getRegime(currentTfLeft, "left");
        const regStateL = REGIME_STATE_LEFT[regimeL] || {};
        applyStateAndRenderLeft(currentTfLeft, stateL, { autoY: false, yRangeOverride: regStateL.yRange });
    }

    syncUiToState();
    updateLayoutForViewMode();
}