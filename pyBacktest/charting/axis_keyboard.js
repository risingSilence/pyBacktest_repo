// assets/axis_keyboard.js
(function () {
  // ---------------------------------------------------------
  // 1. OS DETECTION & CONFIG
  // ---------------------------------------------------------
  const platform = navigator.platform ? navigator.platform.toUpperCase() : "";
  const isMac = platform.indexOf("MAC") >= 0;

  console.log("[AxisKeyboard] Initialized. Detected OS:", isMac ? "macOS" : "Windows/Linux");

  let currentMode = "both";

  function setAxisMode(mode) {
    if (currentMode === mode) return;
    currentMode = mode;

    if (typeof window.onAxisModeChange === "function") {
      window.onAxisModeChange(mode);
    } else {
      const container = document.getElementById("axis-mode");
      if (!container) return;
      const inputs = container.querySelectorAll('input[name="axis-mode"]');
      inputs.forEach((input) => {
        input.checked = (input.value === mode);
      });
    }
  }

  // ---------------------------------------------------------
  // 2. KEYBOARD HANDLING (Capture Phase)
  // ---------------------------------------------------------
  window.addEventListener("keydown", function (e) {
    if (e.repeat) return;

    // --- X-ACHSE: SHIFT (Universal) ---
    if (e.key === "Shift") {
      e.stopImmediatePropagation(); 
      setAxisMode("x");
      return;
    }

    // --- Y-ACHSE: OS-ABHÄNGIG ---
    const isYTrigger = isMac 
      ? (e.key === "Meta") 
      : (e.key === "Alt" || e.key === "AltGraph");

    if (isYTrigger) {
      e.preventDefault();
      e.stopImmediatePropagation();
      setAxisMode("y");
      return;
    }
  }, true);

  window.addEventListener("keyup", function (e) {
    const isShift = (e.key === "Shift");
    const isYTrigger = isMac 
      ? (e.key === "Meta") 
      : (e.key === "Alt" || e.key === "AltGraph");

    if (isShift || isYTrigger) {
      e.preventDefault();
      e.stopImmediatePropagation();
      setAxisMode("both");
    }
  }, true);

  // ---------------------------------------------------------
  // 3. WHEEL EVENT TRANSLATION (Universal)
  // ---------------------------------------------------------
  window.addEventListener("wheel", function (e) {
    if (currentMode === "x" && e.isTrusted) {
      // Horizontal Scroll (z.B. Mac Trackpad + Shift) in vertikalen Zoom umwandeln
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        e.stopImmediatePropagation();
        e.preventDefault();

        const syntheticEvent = new WheelEvent("wheel", {
          bubbles: true,
          cancelable: true,
          view: window,
          detail: e.detail,
          deltaX: 0,
          deltaY: e.deltaX, // X auf Y mappen für Zoom
          deltaZ: 0,
          deltaMode: e.deltaMode,
          clientX: e.clientX,
          clientY: e.clientY,
          screenX: e.screenX,
          screenY: e.screenY,
          ctrlKey: false,
          altKey: false,
          shiftKey: false,
          metaKey: false
        });

        e.target.dispatchEvent(syntheticEvent);
      }
    }
  }, true);

  // ---------------------------------------------------------
  // 4. MOUSE EVENT FIX (Prevent ZoomBox on Shift+Drag)
  // ---------------------------------------------------------
  // FIX: Wenn Shift gehalten wird (X-Mode), interpretiert Plotly 
  // einen Drag normalerweise als "ZoomBox Selection".
  // Wir fangen den Klick ab und senden ihn OHNE Shift-Flag neu.
  // Plotly denkt dann, es ist ein normaler Klick -> Pan (locked auf X).
  
  window.addEventListener("mousedown", function (e) {
    // Bedingung: X-Modus an (Shift) UND echtes User-Event UND Shift-Flag gesetzt
    if (currentMode === "x" && e.isTrusted && e.shiftKey) {
      
      // Originales Event stoppen
      e.stopImmediatePropagation();
      e.preventDefault();
      e.stopPropagation();

      // Kopie des Events erstellen, aber shiftKey auf FALSE zwingen
      const syntheticEvent = new MouseEvent("mousedown", {
        bubbles: true,
        cancelable: true,
        view: window,
        detail: e.detail,
        screenX: e.screenX,
        screenY: e.screenY,
        clientX: e.clientX,
        clientY: e.clientY,
        ctrlKey: e.ctrlKey,
        altKey: e.altKey,
        shiftKey: false, // <--- Das verhindert die ZoomBox!
        metaKey: e.metaKey,
        button: e.button,
        buttons: e.buttons,
        relatedTarget: e.relatedTarget
      });

      // Neu dispatchen
      e.target.dispatchEvent(syntheticEvent);
    }
  }, true); // Capture Phase, um vor Plotly dran zu sein

})();