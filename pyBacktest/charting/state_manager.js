// state_manager.js

// --- Constants ---
const TF_LIST = ["M1", "M3", "M5", "M15", "H1", "H4", "D", "W", "M"];
const DEFAULT_SESSION_DAYS = 10;
const NBSP = "\u00A0";
const DATA_DIR_URL = "data/";
const PHASE_FILE_SCAN_INTERVAL_MS = 1000;
const STORAGE_KEY = "m1_mx_dynamic_viewer_state_v1";

const VIEW_MODE_SINGLE = "single";
const VIEW_MODE_SPLIT  = "split";

const HTF_BEHAVIOR_INDEPENDENT   = "independent_snapshots";
const HTF_BEHAVIOR_FOLLOW_SNAP   = "follow_ltf_snapshots";
const HTF_BEHAVIOR_FOLLOW_STRICT = "follow_ltf_strict";

// Plot Config
const PLOT_CONFIG = {
    displaylogo: false,
    scrollZoom: true,
    responsive: true,
    displayModeBar: false 
};

// Colors & Dimensions
const BACKGROUND_COLOR = "rgb(255,255,255)";
const FOREGROUND_COLOR = "rgb(0,0,0)";
const WICK_OUTLINE_COLOR = "rgb(19,23,34)";
const BULL_BODY_COLOR = "rgb(144,191,249)";
const BEAR_BODY_COLOR = "rgb(178,181,190)";
const CANDLE_BODY_HALF_WIDTH = 0.5;
const DEFAULT_VISIBLE_BARS = 400;
const BUFFER_FACTOR = 3.0;

// Session Definitions
const SESSION_CONFIG = [
    { id: "asia",      name: "Asia",      startOffsetDays: -1, startHour: 20, startMinute: 0,  endOffsetDays: 0, endHour: 1,  endMinute: 0,  fillColor: "rgba(77, 208, 225, 0.1)" },
    { id: "frankfurt", name: "Frankfurt", startOffsetDays: 0,  startHour: 1,  startMinute: 45, endOffsetDays: 0, endHour: 2,  endMinute: 45, fillColor: "rgba(255, 152, 0, 0.1)" },
    { id: "london",    name: "London",    startOffsetDays: 0,  startHour: 3,  startMinute: 0,  endOffsetDays: 0, endHour: 7,  endMinute: 0,  fillColor: "rgba(76, 175, 80, 0.1)" },
    { id: "newyork",   name: "New York",  startOffsetDays: 0,  startHour: 8,  startMinute: 0,  endOffsetDays: 0, endHour: 12, endMinute: 0,  fillColor: "rgba(171, 71, 188, 0.1)" }
];

// --- Global State Variables ---
let DATA = null; 
let currentTf = "M5";
let currentTfLeft = "H1";

let candleHoverOn = false;
let axisMode = "both";
let sessionDays = DEFAULT_SESSION_DAYS;
let SHOW_MISSES = true;
let SHOW_SIGNALS = true;
let VIEW_MODE = VIEW_MODE_SINGLE;
let HTF_BEHAVIOR = HTF_BEHAVIOR_INDEPENDENT;
let SPLIT_LEFT_FRACTION = 0.5;
let AUTO_SAVE_ENABLED = true;

// Splitter State
let isSplitterDragging = false;
let splitterStartX = 0;
let splitterStartLeftWidth = 0;
let splitterStartRightWidth = 0;
let splitterContainerWidth = 0;
let splitterWidthPx = 0;

// Files & Setup Data
let phase2Files = [];
let phase3Files = [];
let phase2File = null;
let phase3File = null;
let PHASE2_BOXES = [];
let PHASE3_TRADES = [];
let SETUPS = [];
let SETUP_BY_ID = {};
let SETUP_SORT_MODE = "time_asc";

// Detect Phase 2 Base TF
let PHASE2_SIGNAL_BASE_TF = null;
let PHASE2_SIGNAL_BASE_MINUTES = 5;
let PHASE2_BASE_TF = null;

// HTF Snapshot / Follow State
let HTF_SNAPSHOT_ACTIVE = false;
let HTF_SNAPSHOT_INFO = null;
let HTF_SNAPSHOT_TFDATA = null;
let HTF_SNAPSHOT_MAX_SIGNAL_TS = null;

let HTF_FOLLOW_ACTIVE = false;
let HTF_FOLLOW_TFDATA = null;
let HTF_FOLLOW_INFO   = null;

// File Scan State
let lastPhase2File = null;
let lastPhase2Text = null;
let lastPhase3File = null;
let lastPhase3Text = null;
let phaseScanTimer = null;

// View State Objects
const TF_STATE = {};
const TF_STATE_LEFT = {};

const REGIME_STATE = {
    minute: { initialized: false, timeRange: null, yRange: null, anchorTime: null, visibleBarsHint: null },
    hourly: { initialized: false, timeRange: null, yRange: null, anchorTime: null, visibleBarsHint: null },
    daily:  { initialized: false, timeRange: null, yRange: null, anchorTime: null, visibleBarsHint: null },
};

const REGIME_STATE_LEFT = {
    minute: { initialized: false, timeRange: null, yRange: null, anchorTime: null, visibleBarsHint: null },
    hourly: { initialized: false, timeRange: null, yRange: null, anchorTime: null, visibleBarsHint: null },
    daily:  { initialized: false, timeRange: null, yRange: null, anchorTime: null, visibleBarsHint: null },
};

let isRelayoutFromCode = false;
let plotlyEventsBoundRight = false;
let plotlyEventsBoundLeft = false;

// --- Persistence Logic ---

function savePersistentState() {
    if (!AUTO_SAVE_ENABLED || !window.localStorage || !DATA) return;
    const payload = {
        currentTf,
        currentTfLeft,
        axisMode,
        candleHoverOn,
        sessionDays,
        REGIME_STATE,
        REGIME_STATE_LEFT,
        TF_STATE,
        TF_STATE_LEFT,
        SHOW_MISSES,
        SHOW_SIGNALS,
        SETUP_SORT_MODE,
        VIEW_MODE,
        htfBehavior: HTF_BEHAVIOR,
        splitterLeftFraction: SPLIT_LEFT_FRACTION
    };
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch (e) {
        console.warn("Could not save viewer state:", e);
    }
}

function restorePersistentState() {
    if (!window.localStorage || !DATA) return false;

    let raw;
    try {
        raw = localStorage.getItem(STORAGE_KEY);
    } catch (e) {
        console.warn("Could not read viewer state:", e);
        return false;
    }
    if (!raw) return false;

    let saved;
    try {
        saved = JSON.parse(raw);
    } catch (e) {
        console.warn("Viewer state corrupt, ignoring:", e);
        return false;
    }

    if (saved.currentTf && saved.currentTf in (DATA.timeframes || {})) {
        currentTf = saved.currentTf;
    }
    if (saved.currentTfLeft && saved.currentTfLeft in (DATA.timeframes || {})) {
        currentTfLeft = saved.currentTfLeft;
    }
    if (typeof saved.candleHoverOn === "boolean") candleHoverOn = saved.candleHoverOn;
    axisMode = "both"; // Always reset to default on reload
    if (typeof saved.sessionDays === "number" && saved.sessionDays >= 0) sessionDays = saved.sessionDays;
    if (typeof saved.SHOW_MISSES === "boolean") SHOW_MISSES = saved.SHOW_MISSES;
    if (typeof saved.SHOW_SIGNALS === "boolean") SHOW_SIGNALS = saved.SHOW_SIGNALS;
    if (typeof saved.SETUP_SORT_MODE === "string") SETUP_SORT_MODE = saved.SETUP_SORT_MODE;
    
    if (typeof saved.VIEW_MODE === "string") {
        if (saved.VIEW_MODE === VIEW_MODE_SINGLE || saved.VIEW_MODE === VIEW_MODE_SPLIT) {
            VIEW_MODE = saved.VIEW_MODE;
        }
    }
    
    if (typeof saved.htfBehavior === "string") {
        if ([HTF_BEHAVIOR_INDEPENDENT, HTF_BEHAVIOR_FOLLOW_SNAP, HTF_BEHAVIOR_FOLLOW_STRICT].includes(saved.htfBehavior)) {
            HTF_BEHAVIOR = saved.htfBehavior;
        }
    }

    if (typeof saved.splitterLeftFraction === "number" && isFinite(saved.splitterLeftFraction)) {
        SPLIT_LEFT_FRACTION = Math.min(0.9, Math.max(0.1, saved.splitterLeftFraction));
    }

    if (saved.REGIME_STATE) {
        for (const [key, val] of Object.entries(saved.REGIME_STATE)) {
            if (REGIME_STATE[key]) Object.assign(REGIME_STATE[key], val);
        }
    }
    if (saved.REGIME_STATE_LEFT) {
        for (const [key, val] of Object.entries(saved.REGIME_STATE_LEFT)) {
            if (REGIME_STATE_LEFT[key]) Object.assign(REGIME_STATE_LEFT[key], val);
        }
    }
    if (saved.TF_STATE) {
        for (const [tf, tfState] of Object.entries(saved.TF_STATE)) {
            TF_STATE[tf] = { ...tfState };
        }
    }
    if (saved.TF_STATE_LEFT) {
        for (const [tf, tfState] of Object.entries(saved.TF_STATE_LEFT)) {
            TF_STATE_LEFT[tf] = { ...tfState };
        }
    }

    return true;
}