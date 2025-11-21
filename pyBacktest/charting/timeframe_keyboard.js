// timeframe_keyboard.js
(function () {
    // -----------------------------------------------------------
    // CONFIG & STATE
    // -----------------------------------------------------------
    let inputBuffer = "";
    let isPopupVisible = false;
    let activeChartId = "m1-chart"; // Default: Right/Main Chart
    
    // UI Elements
    let popup = null;
    let valEl = null;
    let descEl = null;

    // VALID LISTS
    // LTF: Alles außer W/M
    const VALID_TFS_LTF = ["M1", "M3", "M5", "M15", "H1", "H4", "D"];
    // HTF: Nur >= 15min
    const VALID_TFS_HTF = ["M15", "H1", "H4", "D", "W", "M"];

    const TIME_UNIT_LABELS = {
        "m": "Month",
        "w": "Week",
        "d": "Day",
        "h": "Hour",
        "min": "Minute"
    };

    console.log("[TF Keyboard] Script loaded.");

    // -----------------------------------------------------------
    // LOGIC
    // -----------------------------------------------------------

    function resolveTimeframe(input) {
        const lower = input.toLowerCase();
        const numMatch = lower.match(/^(\d+)/);
        if (!numMatch) return null;
        
        const val = parseInt(numMatch[1], 10);
        let unit = "min"; 
        let tfString = "";
        
        const isHtf = (activeChartId === "htf-chart");

        if (lower.includes("d")) {
            unit = "d";
            tfString = "D"; 
        } else if (lower.includes("w")) {
            unit = "w";
            tfString = "W";
        } else if (lower.includes("m") && !lower.includes("min")) { 
            // "1m" -> Month
            unit = "m";
            tfString = "M";
        } else if (lower.includes("h")) {
            unit = "h";
            tfString = "H" + val; 
        } else {
            // Default: Minutes
            unit = "min";
            tfString = "M" + val; 
            
            // Special Mappings
            if (val === 60) tfString = "H1";
            if (val === 240) tfString = "H4";

            // Global Exception: "4" -> H4
            if (val === 4) {
                unit = "h";
                tfString = "H4";
            }

            // HTF Exception: "1" -> H1 (statt M1)
            // (Nur wenn wir im HTF Chart sind)
            if (isHtf && val === 1) {
                unit = "h";
                tfString = "H1";
            }
        }

        const desc = val + " " + TIME_UNIT_LABELS[unit];
        return { tfString, desc, valid: isValidTf(tfString) };
    }

    function isValidTf(tf) {
        const isHtf = (activeChartId === "htf-chart");
        const list = isHtf ? VALID_TFS_HTF : VALID_TFS_LTF;
        return list.includes(tf);
    }

    function setActiveChart(chartId) {
        if (chartId && chartId !== activeChartId) {
            activeChartId = chartId;
        }
    }

    // -----------------------------------------------------------
    // UI HANDLING
    // -----------------------------------------------------------

    function createUI() {
        if (document.getElementById("tf-popup-overlay-unique")) return;

        // 1. CSS
        const style = document.createElement('style');
        style.innerHTML = `
            .tf-popup-overlay {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: #fff;
                border: 1px solid #ccc;
                border-radius: 6px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                padding: 15px 20px;
                z-index: 10000;
                font-family: Arial, sans-serif;
                min-width: 140px;
                text-align: center;
                display: none;
                pointer-events: none;
            }
            .tf-popup-input {
                font-size: 24px;
                font-weight: bold;
                color: #000;
                margin-bottom: 4px;
            }
            .tf-popup-desc {
                font-size: 13px;
                color: #666;
                margin-bottom: 0;
                font-weight: 500;
            }
            .tf-popup-desc.error {
                color: #d32f2f; /* Red */
            }
            .tf-popup-overlay.visible {
                display: block;
                animation: tfFadeIn 0.1s ease-out;
            }
            @keyframes tfFadeIn {
                from { opacity: 0; transform: translate(-50%, -45%); }
                to { opacity: 1; transform: translate(-50%, -50%); }
            }
        `;
        document.head.appendChild(style);

        // 2. HTML
        popup = document.createElement("div");
        popup.id = "tf-popup-overlay-unique";
        popup.className = "tf-popup-overlay";
        popup.innerHTML = `
            <div class="tf-popup-input" id="tf-popup-value"></div>
            <div class="tf-popup-desc" id="tf-popup-desc"></div>
        `;
        document.body.appendChild(popup);

        valEl = document.getElementById("tf-popup-value");
        descEl = document.getElementById("tf-popup-desc");
    }

    function updatePopup() {
        if (!popup) return;

        valEl.textContent = inputBuffer;
        
        const res = resolveTimeframe(inputBuffer);
        
        // Default State
        descEl.className = "tf-popup-desc";
        descEl.textContent = "...";

        if (res) {
            if (res.valid) {
                descEl.textContent = "Change to " + res.desc;
                descEl.style.color = "#666";
            } else {
                descEl.textContent = "Invalid Timeframe";
                descEl.style.color = "red";
                descEl.className = "tf-popup-desc error";
            }
        }

        // Positionierung: BUGFIX -> Kein VIEW_MODE Check, nur activeChartId
        let containerId = "right-chart-wrapper"; 
        if (activeChartId === "htf-chart") {
            containerId = "left-chart-wrapper";
        }
        
        const container = document.getElementById(containerId);
        if (container) {
            const style = window.getComputedStyle(container);
            if (style.position === "static") {
                container.style.position = "relative";
            }
            if (popup.parentElement !== container) {
                container.appendChild(popup);
            }
        }

        if (!isPopupVisible) {
            popup.classList.add("visible");
            isPopupVisible = true;
        }
    }

    function closePopup() {
        if (!popup) return;
        inputBuffer = "";
        popup.classList.remove("visible");
        isPopupVisible = false;
    }

    function commitChange() {
        const res = resolveTimeframe(inputBuffer);
        
        if (res && res.valid) {
            console.log("[TF Keyboard] Switching", activeChartId, "to", res.tfString);
            
            if (activeChartId === "htf-chart") {
                // LINKER CHART (HTF)
                if (typeof window.onTfChangeLeft === "function") {
                    window.onTfChangeLeft(res.tfString);
                }
                const sel = document.getElementById("tf-select-left");
                if (sel) sel.value = res.tfString;

            } else {
                // RECHTER CHART (LTF)
                if (typeof window.onTfChange === "function") {
                    window.onTfChange(res.tfString);
                }
                const sel = document.getElementById("tf-select");
                if (sel) sel.value = res.tfString;
            }
            
            closePopup();
        } else {
            console.log("[TF Keyboard] Invalid input ignored:", inputBuffer);
        }
    }

    // -----------------------------------------------------------
    // EVENTS
    // -----------------------------------------------------------

    function onKeyDown(e) {
        const tag = e.target.tagName.toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select") return;

        const key = e.key;

        // 1. Start: Zahlen 1-9
        if (!isPopupVisible) {
            if (/^[1-9]$/.test(key)) {
                inputBuffer = key;
                updatePopup();
                e.stopPropagation(); 
            }
            return;
        }

        // 2. Popup offen
        e.preventDefault();
        e.stopPropagation();

        if (key === "Enter") {
            commitChange();
        } else if (key === "Escape") {
            closePopup();
        } else if (key === "Backspace") {
            inputBuffer = inputBuffer.slice(0, -1);
            if (inputBuffer.length === 0) {
                closePopup();
            } else {
                updatePopup();
            }
        } else if (/^[0-9dwmhs]$/i.test(key)) {
            inputBuffer += key;
            updatePopup();
        }
    }

    function init() {
        createUI();

        const rightWrap = document.getElementById("right-chart-wrapper");
        const leftWrap = document.getElementById("left-chart-wrapper");

        if (rightWrap) {
            rightWrap.addEventListener("mouseenter", () => setActiveChart("m1-chart"));
            rightWrap.addEventListener("mousedown", () => setActiveChart("m1-chart"));
        }
        if (leftWrap) {
            leftWrap.addEventListener("mouseenter", () => setActiveChart("htf-chart"));
            leftWrap.addEventListener("mousedown", () => setActiveChart("htf-chart"));
        }
        
        window.removeEventListener("keydown", onKeyDown, true); 
        window.addEventListener("keydown", onKeyDown, true);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

})();