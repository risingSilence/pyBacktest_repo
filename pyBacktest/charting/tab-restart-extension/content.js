// content.js
// Neuer Tab (Restart-Target):
//   - erkennt __tabrestart im Hash
//   - wartet auf #m1-chart.js-plotly-plot (+ kleiner Buffer)
//   - meldet "restart-target-ready" an Background
//
// Alter Tab:
//   - macht nichts Besonderes (kein perform-final-save, kein final-save-done)

(function () {
  const TARGET_ID = "m1-chart";
  const READY_DELAY_MS = 200; // kleiner Puffer

  function log(...args) {
    console.log("[TabRestart content]", ...args);
  }

  function getOldTabIdFromHash() {
    const hash = window.location.hash || "";
    const match = hash.match(/__tabrestart=(\d+)/);
    if (!match) return null;
    const id = parseInt(match[1], 10);
    return Number.isFinite(id) ? id : null;
  }

  const oldTabIdFromHash = getOldTabIdFromHash();
  const isRestartTarget = oldTabIdFromHash !== null;

  if (!isRestartTarget) {
    // alter Tab: gar nichts machen
    return;
  }

  log("Restart-Target-Tab erkannt, oldTabId =", oldTabIdFromHash);

  let alreadyNotified = false;
  let observer = null;
  let pollTimer = null;
  let readyTimeout = null;

  function cleanHash() {
    try {
      const hash = window.location.hash || "";
      const cleanedHash = hash
        .replace(/(&)?__tabrestart=\d+/, "")
        .replace(/^#&/, "#");
      const base = window.location.origin + window.location.pathname + window.location.search;
      const finalUrl = cleanedHash && cleanedHash !== "#" ? base + cleanedHash : base;
      if (finalUrl !== window.location.href) {
        history.replaceState(null, "", finalUrl);
      }
    } catch (e) {
      // egal
    }
  }

  function sendRestartTargetReadyOnce(reason) {
    if (alreadyNotified) return;
    alreadyNotified = true;

    log("Sende restart-target-ready (Grund:", reason + ")", "oldTabId =", oldTabIdFromHash);

    try {
      if (observer) observer.disconnect();
      if (pollTimer) clearInterval(pollTimer);
      if (readyTimeout) clearTimeout(readyTimeout);
    } catch (e) {}

    cleanHash();

    try {
      chrome.runtime.sendMessage(
        { type: "restart-target-ready", oldTabId: oldTabIdFromHash, reason },
        () => {
          if (chrome.runtime.lastError) {
            log("runtime.sendMessage error:", chrome.runtime.lastError.message);
          }
        }
      );
    } catch (e) {
      log("runtime.sendMessage exception:", e);
    }
  }

function triggerReadyWithDelay(source) {
  if (alreadyNotified || readyTimeout) return;

  log(
    "Restart-Target-Ready in",
    source,
    "- #m1-chart hat Klasse js-plotly-plot. Warte",
    READY_DELAY_MS,
    "ms ..."
  );

  try {
    if (observer) observer.disconnect();
    if (pollTimer) clearInterval(pollTimer);
  } catch (e) {}

  readyTimeout = setTimeout(() => {
    // 1) Direkt im Page-Kontext reapplyStateFromStorage() feuern
    try {
      const script = document.createElement("script");
      script.textContent = `
        try {
          if (typeof reapplyStateFromStorage === "function") {
            reapplyStateFromStorage();
          }
        } catch (e) {
          console && console.warn && console.warn(
            "[TabRestart injected] reapplyStateFromStorage error:",
            e
          );
        }
      `;
      (document.documentElement || document.head || document.body).appendChild(script);
      script.remove();
    } catch (e) {
      log("Fehler beim Injizieren von reapplyStateFromStorage vor ready:", e);
    }

    // 2) Danach dem Background sagen: Restart-Target ist ready
    sendRestartTargetReadyOnce(source);
  }, READY_DELAY_MS);
}


  function checkTargetReady(source) {
    const el = document.getElementById(TARGET_ID);
    if (!el) return false;
    if (el.classList && el.classList.contains("js-plotly-plot")) {
      triggerReadyWithDelay(source);
      return true;
    }
    return false;
  }

  function startWatchingRestartTarget() {
    // 1) evtl. schon fertig?
    if (checkTargetReady("initial-check")) {
      return;
    }

    // 2) MutationObserver
    try {
      observer = new MutationObserver(() => {
        checkTargetReady("mutation");
      });

      observer.observe(document.documentElement || document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["class", "id"]
      });

      log("MutationObserver (Restart-Target) installiert.");
    } catch (e) {
      log("MutationObserver Fehler (Restart-Target):", e);
    }

    // 3) Fallback-Polling
    pollTimer = setInterval(() => {
      checkTargetReady("poll");
    }, 300);

    log("Polling (Restart-Target) gestartet (300ms).");
  }

  if (document.readyState === "complete" || document.readyState === "interactive") {
    log("DOM bereit (Restart-Target), starte Watching.");
    startWatchingRestartTarget();
  } else {
    window.addEventListener("DOMContentLoaded", () => {
      log("DOMContentLoaded (Restart-Target), starte Watching.");
      startWatchingRestartTarget();
    });
  }
})();
