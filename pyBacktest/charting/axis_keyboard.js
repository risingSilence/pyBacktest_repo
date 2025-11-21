// assets/axis_keyboard.js
(function () {
  // ---------------------------------------------------------
  // 1. OS DETECTION & CONFIG
  // ---------------------------------------------------------
  const platform = navigator.platform ? navigator.platform.toUpperCase() : "";
  // Einfache Heuristik: Wenn "MAC" im Plattform-String vorkommt, ist es macOS.
  const isMac = platform.indexOf("MAC") >= 0;

  console.log("[AxisKeyboard] Initialized. Detected OS:", isMac ? "macOS" : "Windows/Linux");

  // Aktuellen Modus lokal tracken
  let currentMode = "both";

  // Hilfsfunktion: Modus setzen und UI/Global Listener updaten
  function setAxisMode(mode) {
    if (currentMode === mode) return; // Keine unnötigen Updates
    currentMode = mode;

    if (typeof window.onAxisModeChange === "function") {
      window.onAxisModeChange(mode);
    } else {
      // Fallback: Nur Radios updaten
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
  // Wir nutzen { capture: true }, um die Events abzufangen, BEVOR Plotly sie sieht.
  // Das verhindert, dass Plotly natives Verhalten (z.B. Box-Zoom bei Shift) auslöst.

  window.addEventListener("keydown", function (e) {
    if (e.repeat) return;

    // --- X-ACHSE: SHIFT (Universal) ---
    if (e.key === "Shift") {
      // WICHTIG: StopPropagation verhindert, dass Plotly in den "Select Mode" springt.
      // Wir wollen Pan/Zoom via Achsen-Lock, keine Auswahl-Box.
      e.stopImmediatePropagation(); 
      setAxisMode("x");
      return;
    }

    // --- Y-ACHSE: OS-ABHÄNGIG ---
    // Mac: Meta (Command) | Windows: Alt
    const isYTrigger = isMac 
      ? (e.key === "Meta") 
      : (e.key === "Alt" || e.key === "AltGraph");

    if (isYTrigger) {
      e.preventDefault(); // Verhindert Browser-Menüs bei Alt
      e.stopImmediatePropagation();
      setAxisMode("y");
      return;
    }
  }, true); // <--- Capture Phase!

  window.addEventListener("keyup", function (e) {
    // Reset Logic
    const isShift = (e.key === "Shift");
    const isYTrigger = isMac 
      ? (e.key === "Meta") 
      : (e.key === "Alt" || e.key === "AltGraph");

    if (isShift || isYTrigger) {
      e.preventDefault();
      e.stopImmediatePropagation();
      // Wenn eine Taste losgelassen wird, gehen wir zurück auf "both".
      // (Kleine Einschränkung: Wenn man beide drückt und eine loslässt, resettet es auch.
      // Für diesen Use-Case aber völlig ausreichend.)
      setAxisMode("both");
    }
  }, true);

  // ---------------------------------------------------------
  // 3. WHEEL EVENT TRANSLATION (Universal)
  // ---------------------------------------------------------
  // macOS sendet bei Shift+Scroll ein horizontales Scroll-Event (deltaX).
  // Windows sendet meist vertikales (deltaY), aber manche Mäuse auch horizontal.
  // Wir normalisieren das hier: Wenn X-Mode aktiv ist, wird JEDE Bewegung 
  // in einen vertikalen Zoom für Plotly umgewandelt.

  window.addEventListener("wheel", function (e) {
    // Nur eingreifen, wenn wir im X-Modus sind (Shift gehalten)
    // UND das Event "vertrauenswürdig" ist (vom User kommt).
    if (currentMode === "x" && e.isTrusted) {
      
      // Logik: Wenn die horizontale Bewegung stärker ist als die vertikale
      // (typisch für Mac Shift+Scroll oder Windows Side-Scroll-Wheel),
      // dann schreiben wir das Event um.
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        
        // Originales Event stoppen
        e.stopImmediatePropagation();
        e.preventDefault();

        // Neues Event faken: Horizontal -> Vertikal
        // Plotly zoomt bei vertikalem Scrollen. Da die Y-Achse gelockt ist,
        // zoomt er dann nur die X-Achse. Perfekt.
        const syntheticEvent = new WheelEvent("wheel", {
          bubbles: true,
          cancelable: true,
          view: window,
          detail: e.detail,
          deltaX: 0,          // Horizontal eliminieren
          deltaY: e.deltaX,   // Horizontalbewegung als Zoom-Input nutzen
          deltaZ: 0,
          deltaMode: e.deltaMode,
          clientX: e.clientX,
          clientY: e.clientY,
          screenX: e.screenX,
          screenY: e.screenY,
          ctrlKey: false,     // Keine Modifier mitsenden!
          altKey: false,
          shiftKey: false,
          metaKey: false
        });

        e.target.dispatchEvent(syntheticEvent);
      }
      // Falls es schon deltaY ist (normales Windows Scrollrad + Shift),
      // lassen wir es durch. Da wir oben Shift via keydown versteckt haben,
      // denkt Plotly, es sei ein normaler Scroll -> Zoom X (wegen Axis Lock).
    }
  }, true); // Capture Phase

})();