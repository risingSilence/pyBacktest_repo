// background.js (MV3 Service Worker)

// Restart-URL mit Marker bauen: __tabrestart=<oldTabId>
function buildRestartUrl(originalUrl, oldTabId) {
  const idStr = String(oldTabId);
  if (!originalUrl) return "";

  if (originalUrl.includes("#")) {
    return originalUrl + "&__tabrestart=" + idStr;
  }
  return originalUrl + "#__tabrestart=" + idStr;
}

// Klick auf das Extension-Icon -> neuen Tab im Hintergrund öffnen
chrome.action.onClicked.addListener((currentTab) => {
  if (!currentTab || !currentTab.id || !currentTab.url) {
    return;
  }

  const oldTabId = currentTab.id;
  const url = currentTab.url;
  const restartUrl = buildRestartUrl(url, oldTabId);

  chrome.tabs.create({ url: restartUrl, active: false }, () => {
    // neuer Tab meldet sich später per Message
  });
});

// Messages von Content Scripts
chrome.runtime.onMessage.addListener((message, sender) => {
  if (!message || !message.type) return;

  // Neuer Tab: "ich bin ready, schalte jetzt um"
  if (message.type === "restart-target-ready") {
    const tab = sender.tab;
    if (!tab || typeof tab.id !== "number") return;

    const newTabId = tab.id;
    const oldTabId = message.oldTabId;
    if (typeof oldTabId !== "number") return;

    // alten Tab schließen & neuen aktivieren
    chrome.tabs.update(newTabId, { active: true }, () => {
      chrome.tabs.remove(oldTabId);
    });

    return;
  }
});
