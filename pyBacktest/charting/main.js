// main.js

document.addEventListener("DOMContentLoaded", async () => {
    initSplitterDrag();
    buildTfSelects();

    const hoverToggle = document.getElementById("candle-hover-toggle");
    hoverToggle.addEventListener("change", (e) => { onCandleHoverToggle(e.target.checked); });

    const showMissesToggle = document.getElementById("show-misses-toggle");
    if (showMissesToggle) {
        showMissesToggle.checked = SHOW_MISSES;
        showMissesToggle.addEventListener("change", (e) => {
            SHOW_MISSES = !!e.target.checked;
            rebuildSetupsList();
            if (typeof rerenderCurrentViewWithPhases === "function") rerenderCurrentViewWithPhases();
            savePersistentState();
        });
    }

    const showSignalsToggle = document.getElementById("show-signals-toggle");
    if (showSignalsToggle) {
        showSignalsToggle.checked = SHOW_SIGNALS;
        showSignalsToggle.addEventListener("change", (e) => {
            SHOW_SIGNALS = !!e.target.checked;
            if (typeof rerenderCurrentViewWithPhases === "function") rerenderCurrentViewWithPhases();
            savePersistentState();
        });
    }

    const viewModeContainer = document.getElementById("view-mode");
    if (viewModeContainer) {
        viewModeContainer.addEventListener("change", (e) => {
            if (e.target && e.target.name === "view-mode") onViewModeChange(e.target.value);
        });
    }

    const htfBehaviorSelect = document.getElementById("htf-behavior-select");
    if (htfBehaviorSelect) {
        htfBehaviorSelect.value = HTF_BEHAVIOR;
        htfBehaviorSelect.addEventListener("change", (e) => { onHtfBehaviorChange(e.target.value); });
    }

    const sessionDaysInput = document.getElementById("session-days");
    if (sessionDaysInput) {
        sessionDaysInput.value = String(sessionDays);
        sessionDaysInput.addEventListener("change", (e) => {
            let val = parseInt(e.target.value, 10);
            if (!Number.isFinite(val) || val < 3) val = 3;
            if (val > 60) val = 60;
            sessionDays = val;
            e.target.value = String(sessionDays);

            if (!DATA) { savePersistentState(); return; }
            const tfData = DATA.timeframes[currentTf];
            if (!tfData) { savePersistentState(); return; }

            let state = TF_STATE[currentTf];
            if (!state) state = computeWindowForTf(tfData, DEFAULT_VISIBLE_BARS, null);
            const regime = getRegime(currentTf);
            const regState = REGIME_STATE[regime] || {};
            applyStateAndRender(currentTf, state, { autoY: false, yRangeOverride: regState.yRange });
            savePersistentState();
        });
    }

    const phase2Select = document.getElementById("phase2-file-select");
    const phase3Select = document.getElementById("phase3-file-select");
    const setupSelect  = document.getElementById("setup-select");
    const setupSortSelect = document.getElementById("setup-sort-select");

    if (phase2Select) {
        phase2Select.addEventListener("change", async (e) => {
            phase2File = e.target.value || null;
            await loadPhase2File(phase2File);
            if (typeof rerenderCurrentViewWithPhases === "function") rerenderCurrentViewWithPhases();
            rebuildSetupsList();
        });
    }

    if (phase3Select) {
        phase3Select.addEventListener("change", async (e) => {
            phase3File = e.target.value || null;
            await loadPhase3File(phase3File);
            if (typeof rerenderCurrentViewWithPhases === "function") rerenderCurrentViewWithPhases();
            rebuildSetupsList();
        });
    }

    if (setupSelect) {
        setupSelect.addEventListener("change", (e) => {
            const id = e.target.value;
            if (!id) return;
            const setup = SETUP_BY_ID[id];
            if (!setup) return;
            focusOnSetup(setup);
        });
    }

    if (setupSortSelect) {
        setupSortSelect.value = SETUP_SORT_MODE;
        setupSortSelect.addEventListener("change", (e) => {
            SETUP_SORT_MODE = e.target.value || "time_asc";
            renderSetupDropdown();
            savePersistentState();
        });
    }

    try {
        DATA = await loadData();
        const restored = restorePersistentState();

        if (!DATA.timeframes[currentTf]) {
            const available = Object.keys(DATA.timeframes);
            if (available.length > 0) currentTf = available[0];
        }
        if (!DATA.timeframes[currentTfLeft]) {
            const available = Object.keys(DATA.timeframes);
            if (available.length > 0) currentTfLeft = available[0];
        }

        syncUiToState();

        if (restored && TF_STATE[currentTf]) {
            const regimeR = getRegime(currentTf);
            const regStateR = REGIME_STATE[regimeR] || {};
            const tfStateR = TF_STATE[currentTf];
            applyStateAndRender(currentTf, tfStateR, { autoY: false, yRangeOverride: regStateR.yRange });
        } else {
            initDefaultViewRight();
        }

        updateLayoutForViewMode();
        bindPlotlyEventsOnce();

        if (VIEW_MODE === VIEW_MODE_SPLIT) {
            window.requestAnimationFrame(() => {
                try { Plotly.Plots.resize("m1-chart"); Plotly.Plots.resize("htf-chart"); } catch (e) { console.warn("Initial Plotly resize im Split-Mode fehlgeschlagen:", e); }
            });
        }

        rebuildSetupsList();
        startPhaseScanLoop();

        if (VIEW_MODE === VIEW_MODE_SPLIT && (HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_SNAP || HTF_BEHAVIOR === HTF_BEHAVIOR_FOLLOW_STRICT) && TF_STATE[currentTf]) {
            updateHtfFollowFromLtf(TF_STATE[currentTf]);
        }

        document.addEventListener("keydown", (e) => {
            const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : "";
            if (tag === "input" || tag === "textarea") return;
            const key = (e.key || "").toLowerCase();
            const nextKeys = ["arrowdown", "pagedown", "arrowright"];
            const prevKeys = ["arrowup", "pageup", "arrowleft"];
            if (!nextKeys.includes(key) && !prevKeys.includes(key)) return;

            const setups = getSortedSetups();
            if (!setups.length) return;
            const setupSelectEl = document.getElementById("setup-select");
            if (!setupSelectEl) return;

            const currentId = setupSelectEl.value;
            let idx = setups.findIndex((s) => String(s.id) === currentId);
            if (idx === -1) { idx = 0; }
            else if (nextKeys.includes(key)) { if (idx < setups.length - 1) idx++; }
            else if (prevKeys.includes(key)) { if (idx > 0) idx--; }

            const setup = setups[idx];
            if (!setup) return;
            setupSelectEl.value = String(setup.id);
            focusOnSetup(setup);
            e.preventDefault();
        });

        let resizeRerenderTimer = null;
        window.addEventListener("resize", () => {
            if (!DATA) return;
            if (resizeRerenderTimer) clearTimeout(resizeRerenderTimer);
            resizeRerenderTimer = setTimeout(() => {
                try { if (typeof rerenderCurrentViewWithPhases === "function") rerenderCurrentViewWithPhases(); } catch (e) { console.warn("Error re-rendering after resize:", e); }
            }, 150);
        });

        window.addEventListener("storage", (ev) => {
            try {
                if (ev.key === STORAGE_KEY && DATA) {
                    reapplyStateFromStorage();
                }
            } catch (e) {
                console.warn("[restart] storage-listener error:", e);
            }
        });

    } catch (err) {
        console.error(err);
        alert("Error loading data.json. Check console.");
    }
});