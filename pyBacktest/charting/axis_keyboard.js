// assets/axis_keyboard_final.js
(function () {
  // Hilfsfunktion: Axis-Mode setzen, bevorzugt über onAxisModeChange
  function setAxisMode(mode) {
    if (typeof window.onAxisModeChange === "function") {
      // Hauptpfad: direkt deine globale Funktion nutzen
      window.onAxisModeChange(mode);
    } else {
      // Fallback: nur Radios updaten (falls onAxisModeChange noch nicht existiert)
      const container = document.getElementById("axis-mode");
      if (!container) return;
      const inputs = container.querySelectorAll('input[name="axis-mode"]');
      inputs.forEach((input) => {
        input.checked = (input.value === mode);
      });
    }
  }

  // Shift = nur X, Alt = nur Y, sonst wieder beide
  window.addEventListener("keydown", function (e) {
    // Wiederholte Events beim Gedrückthalten ignorieren
    if (e.repeat) return;

    if (e.key === "Shift") {
      setAxisMode("x");
    } else if (e.key === "Alt" || e.key === "AltGraph") {
      e.preventDefault();
      e.stopPropagation();
      setAxisMode("y");
    }
  });

  window.addEventListener("keyup", function (e) {
    if (e.key === "Shift" || e.key === "Alt" || e.key === "AltGraph") {
      e.preventDefault();
      e.stopPropagation();
      setAxisMode("both");
    }
  });
})();
