// assets/crosshair_labels.js
(function () {
  // Beide Charts: rechts (LTF) und links (HTF)
  var GRAPH_IDS = ["m1-chart", "htf-chart"];
  var RETRY_MS = 250;

  // pro Chart etwas State
  var charts = {}; // key = outerId (m1-chart / htf-chart)
  var isDragging = false;

  function getPlotDiv(outerId) {
    var outer = document.getElementById(outerId);
    if (!outer) return null;
    var list = outer.getElementsByClassName("js-plotly-plot");
    if (list && list.length > 0) return list[0];
    return outer;
  }

  function createLabel(className, transform) {
    var div = document.createElement("div");
    div.className = className;
    div.style.position = "absolute";
    div.style.pointerEvents = "none";
    div.style.background = "black";
    div.style.color = "white";
    div.style.padding = "4px 8px";
    div.style.fontSize = "14px";
    div.style.fontFamily = "Arial, sans-serif";
    div.style.borderRadius = "3px";
    div.style.zIndex = 11;
    div.style.whiteSpace = "nowrap";
    div.style.display = "none";
    div.style.transform = transform;
    return div;
  }

  function createVLine() {
    var div = document.createElement("div");
    div.className = "crosshair-vline-overlay";
    div.style.position = "absolute";
    div.style.pointerEvents = "none";
    div.style.borderLeft = "1px dashed rgba(128,128,128,0.7)";
    div.style.height = "0px";
    div.style.display = "none";
    div.style.zIndex = 10;
    return div;
  }

  function createHLine() {
    var div = document.createElement("div");
    div.className = "crosshair-hline-overlay";
    div.style.position = "absolute";
    div.style.pointerEvents = "none";
    div.style.borderTop = "1px dashed rgba(128,128,128,0.7)";
    div.style.width = "0px";
    div.style.display = "none";
    div.style.zIndex = 10;
    return div;
  }

  function hideChart(state) {
    if (!state) return;
    if (state.xLabel) state.xLabel.style.display = "none";
    if (state.yLabel) state.yLabel.style.display = "none";
    if (state.vLine) state.vLine.style.display = "none";
    if (state.hLine) state.hLine.style.display = "none";
  }

  function hideAllCharts() {
    for (var id in charts) {
      if (Object.prototype.hasOwnProperty.call(charts, id)) {
        hideChart(charts[id]);
      }
    }
  }

  function resetHoverState(state) {
    if (!state) return;
    state.hoverState.xa = null;
    state.hoverState.ya = null;
    state.hoverState.xArray = null;
    state.hoverState.tsArray = null;
    state.hoverState.labelsArray = null;
    state.barDurationMinutes = null;
    hideChart(state);
  }

  function ensureAxes(state) {
    var gd = state.gd;
    if (!gd || !gd._fullLayout) return false;
    var fl = gd._fullLayout;
    if (!fl.xaxis || !fl.yaxis) return false;
    state.hoverState.xa = fl.xaxis;
    state.hoverState.ya = fl.yaxis;
    return true;
  }

  function computeBarDurationMinutes(tsArray) {
    var diffs = [];
    for (var i = 1; i < tsArray.length; i++) {
      var a = tsArray[i - 1];
      var b = tsArray[i];
      if (a == null || b == null) continue;
      var diffMin = (b - a) / 60000;
      if (diffMin > 0) diffs.push(diffMin);
    }
    if (!diffs.length) return null;
    diffs.sort(function (a, b) { return a - b; });
    var mid = Math.floor(diffs.length / 2);
    if (diffs.length % 2 === 1) {
      return diffs[mid];
    } else {
      return 0.5 * (diffs[mid - 1] + diffs[mid]);
    }
  }

  function ensureCandlestickCache(state) {
    var hs = state.hoverState;

    var gd = state.gd;
    if (!gd || !gd.data) return false;

    // Aktuellen Candlestick-Trace suchen
    var trace = null;
    for (var i = 0; i < gd.data.length; i++) {
      var tr = gd.data[i];
      if (tr && tr.type === "candlestick") {
        trace = tr;
        break;
      }
    }
    if (!trace) return false;

    var xArrCurrent = trace.x || [];

    // Wenn bereits ein Cache existiert, prüfen, ob er noch zum aktuellen Trace passt.
    // Plotly.react() erzeugt in der Regel neue Array-Instanzen -> Referenzänderung.
    if (hs.xArray && hs.tsArray && hs.labelsArray) {
      // Wenn Referenz und Länge identisch sind, gehen wir davon aus, dass der Cache noch gültig ist.
      if (hs.xArray === xArrCurrent && hs.xArray.length === xArrCurrent.length) {
        return true;
      }
      // ansonsten Cache verwerfen und komplett neu aufbauen
      hs.xArray = null;
      hs.tsArray = null;
      hs.labelsArray = null;
    }

    var xArr = xArrCurrent;
    var cdArr = trace.customdata || [];
    var n = xArr.length;

    var tsArr = new Array(n);
    var labels = new Array(n);

    for (var j = 0; j < n; j++) {
      var cd = cdArr[j];
      if (cd && typeof cd === "object" && cd !== null) {
        if (typeof cd.ts !== "undefined" && cd.ts !== null) {
          tsArr[j] = Number(cd.ts);
        } else {
          tsArr[j] = null;
        }
        if (typeof cd.label !== "undefined" && cd.label !== null) {
          labels[j] = String(cd.label);
        } else {
          labels[j] = "";
        }
      } else {
        // Rückwärtskompatibilität: altes customdata = Label-String
        tsArr[j] = null;
        labels[j] = cd != null ? String(cd) : "";
      }
    }

    hs.xArray = xArr;
    hs.tsArray = tsArr;
    hs.labelsArray = labels;

    var dur = computeBarDurationMinutes(tsArr);
    if (dur != null) {
      state.barDurationMinutes = dur;
    }

    return true;
  }


  function findIndexFloor(tsArray, ts) {
    if (!tsArray || !tsArray.length) return -1;
    var idx = -1;
    for (var i = 0; i < tsArray.length; i++) {
      var v = tsArray[i];
      if (v == null) continue;
      if (v <= ts) idx = i;
      else break;
    }
    return idx;
  }

  function mapTsBetweenCharts(sourceState, targetState, ts) {
    var targetTs = targetState.hoverState.tsArray;
    if (!targetTs || !targetTs.length) return -1;

    var durSource = sourceState.barDurationMinutes;
    var durTarget = targetState.barDurationMinutes;

    var idx = -1;

    // Wenn source deutlich höherer TF als target: nimm die letzte Candle im Intervall
    if (durSource && durTarget && durSource > durTarget * 1.5) {
      var spanMs = durSource * 60 * 1000;
      var endTs = ts + spanMs - 1;
      idx = findIndexFloor(targetTs, endTs);
      if (idx !== -1 && targetTs[idx] < ts) {
        // keine Candle im Intervall [ts, endTs]
        idx = -1;
      }
    } else {
      // LTF -> HTF oder ähnlich: nimm Candle mit ts <= ts_source (Floor)
      idx = findIndexFloor(targetTs, ts);
    }

    return idx;
  }

  function drawCrosshairAtIndex(state, idx, yVal) {
    var hs = state.hoverState;
    var xArr = hs.xArray || [];
    var labels = hs.labelsArray || [];
    var xa = hs.xa;
    var ya = hs.ya;
    var gd = state.gd;

    if (!xa || !ya || !gd || !xArr.length) {
      hideChart(state);
      return;
    }

    if (idx < 0 || idx >= xArr.length) {
      // Nichts zu zeigen
      hideChart(state);
      return;
    }

    if (typeof xa.l2p !== "function" || typeof ya.l2p !== "function") {
      hideChart(state);
      return;
    }

    var rect = gd.getBoundingClientRect();
    var snappedX = xArr[idx];
    var label = labels[idx] || "";

    // X-Pixel
    var xPxInAxis = xa.l2p(snappedX);
    var xPx = xa._offset + xPxInAxis;

    // Y-Pixel aus yVal, falls vorhanden
    var yPx = null;
    if (typeof yVal === "number" && isFinite(yVal)) {
      var yPxInAxis = ya.l2p(yVal);
      yPx = ya._offset + yPxInAxis;
    }

    // Y-Label + horizontale Linie
    if (
      yPx != null &&
      yPx >= ya._offset &&
      yPx <= ya._offset + ya._length
    ) {
      var priceLabel = yVal.toFixed(5);

      // linker Chart = htf-chart -> Label an linker Y-Achse
      var isLeftChart = (state.id === "htf-chart");

      var left, plotLeft, plotWidth;
      if (typeof xa._offset === "number" && typeof xa._length === "number") {
        // Plotbereich
        plotLeft = xa._offset;
        plotWidth = xa._length;

        if (isLeftChart) {
          left = xa._offset;               // linke Y-Achse
        } else {
          left = xa._offset + xa._length;  // rechte Y-Achse
        }
      } else {
        // Fallback ohne Achsen-Metadaten
        plotLeft = 0;
        plotWidth = rect.width;
        left = isLeftChart ? 0 : rect.width;
      }

      state.yLabel.textContent = priceLabel;

      state.yLabel.style.left = left + "px";
      state.yLabel.style.top = yPx + "px";
      state.yLabel.style.display = "block";

      state.hLine.style.left = plotLeft + "px";
      state.hLine.style.top = yPx + "px";
      state.hLine.style.width = plotWidth + "px";
      state.hLine.style.display = "block";
    } else {
      state.yLabel.style.display = "none";
      state.hLine.style.display = "none";
    }

    // X-Label + vertikale Linie
    if (
      xPx >= xa._offset &&
      xPx <= xa._offset + xa._length
    ) {
      if (label) {
        state.xLabel.textContent = label;
        state.xLabel.style.left = xPx + "px";
        state.xLabel.style.top = (ya._offset + ya._length) + "px";
        state.xLabel.style.display = "block";
      } else {
        state.xLabel.style.display = "none";
      }

      state.vLine.style.left = xPx + "px";
      state.vLine.style.top = ya._offset + "px";
      state.vLine.style.height = ya._length + "px";
      state.vLine.style.display = "block";
    } else {
      state.xLabel.style.display = "none";
      state.vLine.style.display = "none";
    }
  }

  function mirrorCrosshair(sourceState, ts, yVal) {
    if (ts == null) {
      // ohne Zeit kein Mirror
      return;
    }

    for (var id in charts) {
      if (!Object.prototype.hasOwnProperty.call(charts, id)) continue;
      var target = charts[id];
      if (target === sourceState) continue;

      if (!ensureAxes(target) || !ensureCandlestickCache(target)) {
        hideChart(target);
        continue;
      }

      var idx = mapTsBetweenCharts(sourceState, target, ts);
      if (idx === -1) {
        hideChart(target);
      } else {
        drawCrosshairAtIndex(target, idx, yVal);
      }
    }
  }

  function updateCrosshairFromMouse(state, ev) {
    // während Drag: alles aus
    if (isDragging) {
      hideAllCharts();
      return;
    }

    if (!ensureAxes(state)) {
      hideChart(state);
      return;
    }

    // Candlestick-Infos (xArray, tsArray, Labels) sicherstellen
    ensureCandlestickCache(state);

    var hs = state.hoverState;
    var xa = hs.xa;
    var ya = hs.ya;
    var gd = state.gd;

    if (
      !xa ||
      !ya ||
      typeof xa.p2l !== "function" ||
      typeof xa.l2p !== "function" ||
      typeof ya.p2l !== "function"
    ) {
      hideChart(state);
      return;
    }

    var rect = gd.getBoundingClientRect();
    var mouseX = ev.clientX - rect.left;
    var mouseY = ev.clientY - rect.top;

    var xArr = hs.xArray || [];
    var tsArr = hs.tsArray || [];
    var labels = hs.labelsArray || [];

    // ---------------- Y-TEIL (wie vorher, nur lokal) ----------------
    var yVal = null;
    if (mouseY < ya._offset || mouseY > ya._offset + ya._length) {
      state.yLabel.style.display = "none";
      state.hLine.style.display = "none";
    } else {
      var yPxInAxis = mouseY - ya._offset;
      var tmpYVal = ya.p2l(yPxInAxis);
      if (typeof tmpYVal === "number" && isFinite(tmpYVal)) {
        yVal = tmpYVal;

        var priceLabel = yVal.toFixed(5);

        // linker Chart = htf-chart -> Label an linker Y-Achse
        var isLeftChart = (state.id === "htf-chart");

        var left, plotLeft, plotWidth;
        if (typeof xa._offset === "number" && typeof xa._length === "number") {
          // Plotbereich
          plotLeft = xa._offset;
          plotWidth = xa._length;

          if (isLeftChart) {
            left = xa._offset;               // linke Y-Achse
          } else {
            left = xa._offset + xa._length;  // rechte Y-Achse
          }
        } else {
          // Fallback ohne Achsen-Metadaten
          plotLeft = 0;
          plotWidth = rect.width;
          left = isLeftChart ? 0 : rect.width;
        }

        state.yLabel.textContent = priceLabel;

        state.yLabel.style.left = left + "px";
        state.yLabel.style.top = mouseY + "px";
        state.yLabel.style.display = "block";

        state.hLine.style.left = plotLeft + "px";
        state.hLine.style.top = mouseY + "px";
        state.hLine.style.width = plotWidth + "px";
        state.hLine.style.display = "block";
      } else {
        state.yLabel.style.display = "none";
        state.hLine.style.display = "none";
      }
    }

    // ---------------- X-TEIL (inkl. Mirror) ----------------

    if (!xArr.length) {
      // keine Candles -> nur Y-Crosshair möglich
      state.xLabel.style.display = "none";
      state.vLine.style.display = "none";
      return;
    }

    if (mouseX < xa._offset || mouseX > xa._offset + xa._length) {
      // außerhalb X → lokales X-Crosshair aus, Mirror auch aus
      state.xLabel.style.display = "none";
      state.vLine.style.display = "none";
      // Mirror ausblenden
      for (var id in charts) {
        if (Object.prototype.hasOwnProperty.call(charts, id)) {
          if (charts[id] !== state) {
            charts[id].xLabel.style.display = "none";
            charts[id].vLine.style.display = "none";
          }
        }
      }
      return;
    }

    var xPxInAxis = mouseX - xa._offset;
    var xValContinuous = xa.p2l(xPxInAxis);
    if (typeof xValContinuous !== "number" || !isFinite(xValContinuous)) {
      state.xLabel.style.display = "none";
      state.vLine.style.display = "none";
      return;
    }

    var firstX = xArr[0];
    var lastX = xArr[xArr.length - 1];

    var snappedX = Math.round(xValContinuous);
    if (snappedX < firstX) snappedX = firstX;
    if (snappedX > lastX) snappedX = lastX;

    var pointIdx = snappedX - firstX;
    if (pointIdx < 0 || pointIdx >= xArr.length) {
      state.xLabel.style.display = "none";
      state.vLine.style.display = "none";
      return;
    }

    var timeLabel = labels[pointIdx] || "";
    var ts = tsArr[pointIdx] != null ? tsArr[pointIdx] : null;
    var xPx = xa.l2p(snappedX) + xa._offset;

    // eigenes X-Label
    if (timeLabel) {
      state.xLabel.textContent = timeLabel;
      state.xLabel.style.left = xPx + "px";
      state.xLabel.style.top = (ya._offset + ya._length) + "px";
      state.xLabel.style.display = "block";
    } else {
      state.xLabel.style.display = "none";
    }

    // eigene vertikale Linie
    state.vLine.style.left = xPx + "px";
    state.vLine.style.top = ya._offset + "px";
    state.vLine.style.height = ya._length + "px";
    state.vLine.style.display = "block";

    // Jetzt: Mirror ins andere Chart
    mirrorCrosshair(state, ts, yVal);
  }

  function initChart(outerId) {
    if (typeof window.Plotly === "undefined") {
      setTimeout(function () { initChart(outerId); }, RETRY_MS);
      return;
    }

    var gd = getPlotDiv(outerId);
    if (!gd || typeof gd.on !== "function") {
      setTimeout(function () { initChart(outerId); }, RETRY_MS);
      return;
    }

    if (gd.__crosshairOverlayInitialized) {
      return;
    }
    gd.__crosshairOverlayInitialized = true;

    console.log("[crosshair-overlay] init chart:", outerId, "gd.id:", gd.id);

    var container = gd;
    if (!container.style.position) {
      container.style.position = "relative";
    }

    var xLabel = createLabel("crosshair-x-label-overlay", "translate(-50%, 0)");
    var yLabel = createLabel("crosshair-y-label-overlay", "translate(0, -50%)");
    var vLine = createVLine();
    var hLine = createHLine();

    container.appendChild(xLabel);
    container.appendChild(yLabel);
    container.appendChild(vLine);
    container.appendChild(hLine);

    var state = {
      id: outerId,
      gd: gd,
      xLabel: xLabel,
      yLabel: yLabel,
      vLine: vLine,
      hLine: hLine,
      hoverState: {
        xa: null,
        ya: null,
        xArray: null,
        tsArray: null,
        labelsArray: null
      },
      barDurationMinutes: null
    };

    charts[outerId] = state;

    gd.__crosshairChartId = outerId;

    // Plotly-Events (für Daten/Relayout)
    gd.on("plotly_hover", function (eventData) {
      // Candlestick-Trace cachen, falls noch nicht passiert
      if (!eventData || !eventData.points || !eventData.points.length) return;

      if (!ensureAxes(state)) return;
      ensureCandlestickCache(state);
    });

    gd.on("plotly_unhover", function () {
      // bewusst nichts: Crosshair bleibt stehen
    });

    // Layout- oder Datenänderung -> Cache resetten
    gd.on("plotly_relayout", function () {
      resetHoverState(state);
    });
    gd.on("plotly_restyle", function () {
      resetHoverState(state);
    });
    gd.on("plotly_redraw", function () {
      resetHoverState(state);
    });
    gd.on("plotly_update", function () {
      resetHoverState(state);
    });

    // Mausbewegung → Crosshair für dieses Chart + Mirror
    gd.addEventListener("mousemove", function (ev) {
      updateCrosshairFromMouse(state, ev);
    });

    gd.addEventListener("mousedown", function (ev) {
      if (ev.button === 0) {
        isDragging = true;
        hideAllCharts();
      }
    });
  }

  function initAll() {
    for (var i = 0; i < GRAPH_IDS.length; i++) {
      initChart(GRAPH_IDS[i]);
    }
  }

  // Mouseup global → drag-Ende
  window.addEventListener("mouseup", function () {
    if (isDragging) {
      isDragging = false;
      // Crosshair kommt erst bei nächster Mausbewegung wieder
    }
  });

  // Window-Resize → Achsen & Cache resetten
  window.addEventListener("resize", function () {
    for (var id in charts) {
      if (!Object.prototype.hasOwnProperty.call(charts, id)) continue;
      var st = charts[id];
      st.hoverState.xa = null;
      st.hoverState.ya = null;
      st.hoverState.xArray = null;
      st.hoverState.tsArray = null;
      st.hoverState.labelsArray = null;
      st.barDurationMinutes = null;
      hideChart(st);
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
