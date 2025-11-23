print("phase3_trades_hodlod_two_m5_legs_choch_fvgs.py - starting up...")

from dataclasses import dataclass
from typing import Optional, Any, Dict, List
import pandas as pd
import numpy as np
import os

# ==============================================================================
# 1. CONFIGURATION & PARAMETERS
# ==============================================================================

SYMBOL = "EURUSD"
SETUP_NAME = "hodlod_two_m5_legs_choch_fvgs" # Muss exakt zum Phase 2 Output passen

# --- PATHS ---
CHART_DATA_DIR = "charting/data"
INPUT_BARS_FILENAME = f"data_{SYMBOL}_M5_signals_{SETUP_NAME}.csv"
INPUT_BARS_FILE = os.path.join(CHART_DATA_DIR, INPUT_BARS_FILENAME)
INPUT_SETUPS_FILENAME = f"data_{SYMBOL}_M5_setups_{SETUP_NAME}.csv"
INPUT_SETUPS_FILE = os.path.join(CHART_DATA_DIR, INPUT_SETUPS_FILENAME)
TRADES_FILE_TEMPLATE = os.path.join(CHART_DATA_DIR, f"data_{SYMBOL}_M5_trades_{SETUP_NAME}_{{exit_suffix}}.csv")
OUTPUT_STATS_FILE = os.path.join(CHART_DATA_DIR, f"data_{SYMBOL}_M5_stats_{SETUP_NAME}.csv")

# --- RISK & TRADE PARAMETERS ---
SCENARIO_ID = "limit_fvg2_london_2R"

# Stats Output Config
OVERWRITE_STATS_FILE = False  # True = überschreiben, False = neue Datei (_1, _2...) erstellen

# Target Risk-Reward Ratio (Standard)
TARGET_RR = 2.8

# Near-TP Trailing:
NEAR_TP_TRAILING_ENABLED = False
NEAR_TP_TRIGGER_R = 1.75

# SL Buffer (in Pips) - Halbiert vs. altes Setup
SL_BUFFER = { 
    "AUDUSD": 0.3, 
    "EURUSD": 0.4, # 0.4 default 
    "GBPUSD": 0.5, 
}

# Max SL Size (in Pips) - Verschärft
MAX_SL_SIZE = { 
    "AUDUSD": 9.0, 
    "EURUSD": 12.0, # 12.0 default 
    "GBPUSD": 15.0, 
}

PIP_SIZE_MAP = {
    "AUDUSD": 0.0001,
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
}

# --- TIME SETTINGS (NEW YORK TIME) ---

# Späteste Uhrzeit für einen ENTRY (Limit Fill oder Market)
ENTRY_CUTOFF_HOUR = 12
ENTRY_CUTOFF_MINUTE = 0

# Exit Zeit für den "exit_2pm" Modus
EXIT_2PM_HOUR = 14
EXIT_2PM_MINUTE = 0

# Exit Zeit für den "exit_4pm" Modus (Session Close)
EXIT_SESSION_CLOSE_HOUR = 16
EXIT_SESSION_CLOSE_MINUTE = 0

# Ab wann startet das BOS-Trailing (für exit_post_2pm_... Modi)
BOS_TRAILING_START_HOUR = 14
BOS_TRAILING_START_MINUTE = 0

# --- INTERNAL CONSTANTS ---
SQUEEZE_RISK_DIVISOR = TARGET_RR + 1 # NICHT ANFASSEN!!


# ==============================================================================
# 2. DERIVED CONFIG (DO NOT EDIT MANUALLY)
# ==============================================================================
NY_ENTRY_CUTOFF_MOD = ENTRY_CUTOFF_HOUR * 60 + ENTRY_CUTOFF_MINUTE
NY_2PM_MOD = EXIT_2PM_HOUR * 60 + EXIT_2PM_MINUTE
NY_SESSION_CLOSE_MOD = EXIT_SESSION_CLOSE_HOUR * 60 + EXIT_SESSION_CLOSE_MINUTE
NY_BOS_START_MOD = BOS_TRAILING_START_HOUR * 60 + BOS_TRAILING_START_MINUTE


# ==============================================================================
# 3. DATA CLASSES
# ==============================================================================

@dataclass
class EntrySpec:
    symbol: str
    direction: str
    date_ny: Any
    setup_index: int
    entry_price: float
    sl_price: float
    tp_price: float
    activation_idx: Any
    scenario_id: str = SCENARIO_ID

@dataclass
class ExitResult:
    filled: bool
    miss_reason: Optional[str]
    entry_idx: Optional[Any]
    exit_idx: Optional[Any]
    exit_price: Optional[float]
    exit_reason: Optional[str]
    result_R: Optional[float]
    sl_size_pips: Optional[float]
    holding_minutes: Optional[float]


# ==============================================================================
# 4. HELPER FUNCTIONS
# ==============================================================================

def _ensure_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.index.name != "time_ny":
        if "time_ny" in df.columns:
            df["time_ny"] = pd.to_datetime(df["time_ny"])
            df = df.set_index("time_ny")
        else:
            df.index = pd.to_datetime(df.index)
        df.index.name = "time_ny"

    if "minute_of_day" not in df.columns:
        idx = df.index
        df["hour_ny"] = idx.hour
        df["minute_ny"] = idx.minute
        df["minute_of_day"] = df["hour_ny"] * 60 + df["minute_ny"]
    
    if "date_ny" not in df.columns:
        df["date_ny"] = df.index.date

    return df

def _get_unique_filepath(path: str) -> str:
    if not os.path.exists(path): return path
    base, ext = os.path.splitext(path)
    counter = 1
    while True:
        new_path = f"{base}_{counter}{ext}"
        if not os.path.exists(new_path): return new_path
        counter += 1

def _scan_bear_fvgs_with_bounds(highs: np.ndarray, lows: np.ndarray, start_pos: int, end_pos: int, pip_size: float) -> List[Dict[str, Any]]:
    if end_pos - start_pos < 2: return []
    out = []
    for i in range(start_pos + 1, end_pos):
        left, right = i - 1, i + 1
        if left < 0 or right >= len(highs): continue
        if highs[right] < lows[left]:
            upper, lower = lows[left], highs[right]
            size_price = upper - lower
            if size_price > 0:
                out.append({"mid_pos": i, "upper": float(upper), "lower": float(lower), "size_pips": float(size_price / pip_size)})
    return out

def _scan_bull_fvgs_with_bounds(highs: np.ndarray, lows: np.ndarray, start_pos: int, end_pos: int, pip_size: float) -> List[Dict[str, Any]]:
    if end_pos - start_pos < 2: return []
    out = []
    for i in range(start_pos + 1, end_pos):
        left, right = i - 1, i + 1
        if left < 0 or right >= len(highs): continue
        if lows[right] > highs[left]:
            lower, upper = highs[left], lows[right]
            size_price = upper - lower
            if size_price > 0:
                out.append({"mid_pos": i, "upper": float(upper), "lower": float(lower), "size_pips": float(size_price / pip_size)})
    return out


# ==============================================================================
# 5. ENTRY LOGIC (Original Two-Leg Logic with Config Vars)
# ==============================================================================

def build_entry_for_setup_scenario1(setup_row: pd.Series,
                                    df_day: pd.DataFrame,
                                    setup_idx: int) -> Optional[EntrySpec]:
    direction = setup_row["direction"]
    symbol = setup_row["symbol"]
    date_ny = setup_row["date_ny"]

    pip_size = PIP_SIZE_MAP.get(symbol)
    if pip_size is None: return None

    # Config-Werte laden
    sl_buffer_pips = SL_BUFFER[symbol]
    max_sl_pips = MAX_SL_SIZE[symbol]
    max_sl_price = max_sl_pips * pip_size

    # --- SELL LOGIC (Short) ---
    if direction == "sell":
        if "london_low" not in df_day.columns or df_day["london_low"].isna().all(): return None
        london_level = float(df_day["london_low"].iloc[0])
        
        hod_price = float(setup_row["hod_price"])
        sl_price = hod_price + sl_buffer_pips * pip_size

        # FVG im 2. Leg: LL1 -> LL2
        try:
            ll1_ts = pd.to_datetime(setup_row["ll1_idx"])
            ll2_ts = pd.to_datetime(setup_row["ll2_idx"])
            pos_ll1 = df_day.index.get_loc(ll1_ts)
            pos_ll2 = df_day.index.get_loc(ll2_ts)
        except KeyError: return None

        highs, lows = df_day["high"].values, df_day["low"].values
        fvgs = _scan_bear_fvgs_with_bounds(highs, lows, pos_ll1, pos_ll2, pip_size)
        if not fvgs: return None

        # Best FVG = niedrigste Untergrenze (aggressivstes Limit)
        best = min(fvgs, key=lambda d: d["lower"])
        entry_price = best["lower"]

        # Max-SL Cap
        if (sl_price - entry_price) > max_sl_price:
            entry_price = sl_price - max_sl_price

        # London Squeeze / 2R Target
        risk = sl_price - entry_price
        tp_2r = entry_price - TARGET_RR * risk

        if tp_2r >= london_level:
            tp_price = tp_2r
        else:
            # Squeeze: London Low ist Target
            dist = sl_price - london_level
            if dist <= 0: return None
            new_risk = dist / SQUEEZE_RISK_DIVISOR
            if (new_risk / pip_size) > max_sl_pips: return None # Squeeze erzwingt zu großen SL -> Skip
            entry_price = sl_price - new_risk
            tp_price = london_level

        # Aktivierung: Kerze NACH LL2
        try:
            activation_pos = df_day.index.get_loc(ll2_ts) + 1
            if activation_pos >= len(df_day): return None
            activation_idx = df_day.index[activation_pos]
        except KeyError: return None

    # --- BUY LOGIC (Long) ---
    elif direction == "buy":
        if "london_high" not in df_day.columns or df_day["london_high"].isna().all(): return None
        london_level = float(df_day["london_high"].iloc[0])
        
        lod_price = float(setup_row["lod_price"])
        sl_price = lod_price - sl_buffer_pips * pip_size

        # FVG im Bereich LOD -> HH2 (Original Logic preserved)
        try:
            lod_ts = pd.to_datetime(setup_row["lod_idx"])
            hh2_ts = pd.to_datetime(setup_row["hh2_idx"])
            pos_lod = df_day.index.get_loc(lod_ts)
            pos_hh2 = df_day.index.get_loc(hh2_ts)
        except KeyError: return None

        highs, lows = df_day["high"].values, df_day["low"].values
        fvgs = _scan_bull_fvgs_with_bounds(highs, lows, pos_lod, pos_hh2, pip_size)
        if not fvgs: return None

        # Best FVG = höchste Obergrenze (aggressivstes Limit)
        best = max(fvgs, key=lambda d: d["upper"])
        entry_price = best["upper"]

        # Max-SL Cap
        if (entry_price - sl_price) > max_sl_price:
            entry_price = sl_price + max_sl_price

        # London Squeeze / 2R Target
        risk = entry_price - sl_price
        tp_2r = entry_price + TARGET_RR * risk

        if tp_2r <= london_level:
            tp_price = tp_2r
        else:
            dist = london_level - sl_price
            if dist <= 0: return None
            new_risk = dist / SQUEEZE_RISK_DIVISOR
            if (new_risk / pip_size) > max_sl_pips: return None
            entry_price = sl_price + new_risk
            tp_price = london_level

        # Aktivierung: Kerze NACH HH2
        try:
            activation_pos = df_day.index.get_loc(hh2_ts) + 1
            if activation_pos >= len(df_day): return None
            activation_idx = df_day.index[activation_pos]
        except KeyError: return None

    else:
        return None

    return EntrySpec(symbol, direction, date_ny, setup_idx, float(entry_price), float(sl_price), float(tp_price), activation_idx)


# ==============================================================================
# 6. TRADE SIMULATION & EXIT (Standardized)
# ==============================================================================

def _simulate_exit_phase(entry: EntrySpec, df_day: pd.DataFrame, entry_idx: Any, session_close_minute_mod: Optional[int], bos_target_number: Optional[int]) -> ExitResult:
    direction = entry.direction
    pip_size = PIP_SIZE_MAP[entry.symbol]

    if "minute_of_day" not in df_day.columns: df_day = _ensure_time_columns(df_day)
    try: entry_pos = df_day.index.get_loc(entry_idx)
    except KeyError: return ExitResult(False, "entry_idx_not_in_day", None, None, None, None, None, None, None)

    initial_sl = entry.sl_price
    risk_sl_size_price = abs(entry.entry_price - initial_sl)
    risk_sl_size_pips = risk_sl_size_price / pip_size if pip_size else 0

    effective_sl = initial_sl
    tp_price = entry.tp_price
    exit_idx, exit_price, exit_reason = None, None, None
    last_idx_before_close = None

    # Trailing State
    ref_price = None
    bos_count = 0
    use_bos_trailing = (bos_target_number is not None and bos_target_number > 0)
    bos_trailing_active = False
    
    near_tp_trailing_active = False
    near_tp_sl = None
    
    threshold_long, threshold_short = None, None
    if NEAR_TP_TRAILING_ENABLED and risk_sl_size_pips > 0:
        d = NEAR_TP_TRIGGER_R * risk_sl_size_price
        threshold_long, threshold_short = entry.entry_price + d, entry.entry_price - d

    has_sl_label = "swing_low_label" in df_day.columns
    has_sh_label = "swing_high_label" in df_day.columns

    for pos in range(entry_pos, len(df_day)):
        row = df_day.iloc[pos]
        minute = row["minute_of_day"]
        idx = df_day.index[pos]

        if session_close_minute_mod is not None and minute > session_close_minute_mod:
            break
        last_idx_before_close = idx

        h, l, c = float(row["high"]), float(row["low"]), float(row["close"])

        # --- 1. BOS TRAILING ---
        if use_bos_trailing and minute >= NY_BOS_START_MOD:
            if ref_price is None: ref_price = c
            bos_trigger = False
            if direction == "buy":
                if l < ref_price:
                    if not has_sl_label or (isinstance(row["swing_low_label"], str) and row["swing_low_label"] != ""): 
                        bos_trigger = True
            else:
                if h > ref_price:
                    if not has_sh_label or (isinstance(row["swing_high_label"], str) and row["swing_high_label"] != ""): 
                        bos_trigger = True
            if bos_trigger:
                bos_count += 1
                if bos_count == bos_target_number:
                    effective_sl = l if direction == "buy" else h
                    bos_trailing_active = True

        # --- 2. EFFECTIVE SL (BOS vs NearTP) ---
        sl_curr = effective_sl
        if near_tp_trailing_active and near_tp_sl is not None:
            sl_curr = max(sl_curr, near_tp_sl) if direction == "buy" else min(sl_curr, near_tp_sl)

        # --- 3. HIT CHECK ---
        if direction == "sell":
            hit_sl, hit_tp = (h >= sl_curr), (l <= tp_price)
        else:
            hit_sl, hit_tp = (l <= sl_curr), (h >= tp_price)

        if hit_sl or hit_tp:
            if hit_sl:
                exit_idx, exit_price = idx, sl_curr
                if near_tp_trailing_active: exit_reason = "TRAILING_STOP_NEAR_TP"
                elif bos_trailing_active and effective_sl != initial_sl: exit_reason = "TRAILING_STOP"
                else: exit_reason = "SL"
            else:
                exit_idx, exit_price, exit_reason = idx, tp_price, "TP"
            break

        # --- 4. UPDATE TRAILING ---
        if near_tp_trailing_active and near_tp_sl is not None:
            if direction == "buy": near_tp_sl = max(near_tp_sl, l)
            else: near_tp_sl = min(near_tp_sl, h)
        
        if NEAR_TP_TRAILING_ENABLED and not near_tp_trailing_active and risk_sl_size_pips > 0:
            if direction == "buy" and threshold_long and h >= threshold_long:
                near_tp_trailing_active = True; near_tp_sl = l
            elif direction == "sell" and threshold_short and l <= threshold_short:
                near_tp_trailing_active = True; near_tp_sl = h

    # --- 5. UNFILLED EXIT ---
    if exit_idx is None:
        if session_close_minute_mod is None:
            exit_idx = df_day.index[-1]
            exit_price = float(df_day.iloc[-1]["close"])
            exit_reason = "MANUAL_CLOSE"
        else:
            if last_idx_before_close:
                exit_idx = last_idx_before_close
                exit_price = float(df_day.loc[last_idx_before_close]["close"])
                exit_reason = "SESSION_CLOSE"
            else:
                return ExitResult(True, "no_data_for_exit", entry_idx, None, None, None, None, None, None)

    pips = (entry.entry_price - exit_price) if direction == "sell" else (exit_price - entry.entry_price)
    res_r = (pips / pip_size) / risk_sl_size_pips if (pip_size and risk_sl_size_pips > 0) else 0.0
    hold_min = (exit_idx - entry_idx).total_seconds() / 60.0 if (entry_idx and exit_idx) else 0.0

    return ExitResult(True, None, entry_idx, exit_idx, float(exit_price), exit_reason, float(res_r), float(risk_sl_size_pips), hold_min)


def simulate_trade_for_exit_mode(entry: EntrySpec, df_day: pd.DataFrame, exit_mode: str) -> ExitResult:
    direction = entry.direction
    if "minute_of_day" not in df_day.columns: df_day = _ensure_time_columns(df_day)

    try: start_pos = df_day.index.get_loc(entry.activation_idx)
    except KeyError: return ExitResult(False, "activation_idx_not_in_day", None, None, None, None, None, None, None)

    filled, entry_idx = False, None
    for pos in range(start_pos, len(df_day)):
        row = df_day.iloc[pos]
        if row["minute_of_day"] > NY_ENTRY_CUTOFF_MOD: break
        h, l = float(row["high"]), float(row["low"])
        if direction == "sell":
            if h >= entry.entry_price:
                filled, entry_idx = True, df_day.index[pos]; break
        else:
            if l <= entry.entry_price:
                filled, entry_idx = True, df_day.index[pos]; break

    if not filled: return ExitResult(False, "no_fill_until_noon", None, None, None, None, None, None, None)

    session_close_mod, bos_target = NY_SESSION_CLOSE_MOD, None
    if exit_mode == "exit_2pm": session_close_mod = NY_2PM_MOD
    elif exit_mode == "exit_unmanaged": session_close_mod = None
    elif exit_mode == "exit_post_2pm_1st_bos": session_close_mod = None; bos_target = 1
    elif exit_mode == "exit_post_2pm_2nd_bos": session_close_mod = None; bos_target = 2
    
    return _simulate_exit_phase(entry, df_day, entry_idx, session_close_mod, bos_target)


# ==============================================================================
# 7. STATS CALCULATION
# ==============================================================================

def _format_minutes_to_hhmm(minutes: Optional[float]) -> str:
    if minutes is None or np.isnan(minutes): return ""
    total = int(round(minutes))
    h, m = total // 60, total % 60
    return f"{h:02d}:{m:02d}"

def _round_trades(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    for c in ["entry_price", "sl_price", "tp_price", "exit_price"]:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce").round(5)
    for c in ["result_R", "sl_size_pips", "holding_minutes"]:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce").round(2)
    return df

def _round_stats_for_output(stats: Dict[str, Any]) -> Dict[str, Any]:
    rounded = {}
    for k, v in stats.items():
        if isinstance(v, (float, np.floating)):
            rounded[k] = v if np.isnan(v) else float(round(v, 2))
        else:
            rounded[k] = v
    return rounded

def compute_stats_comprehensive(df_trades: pd.DataFrame) -> Dict[str, Any]:
    stats = {}
    n_setups = len(df_trades)
    n_filled = int(df_trades["filled"].sum()) if "filled" in df_trades.columns else 0
    stats["n_setups"] = n_setups
    stats["n_filled"] = n_filled
    stats["tag_rate"] = n_filled / n_setups if n_setups > 0 else np.nan

    df_filled = df_trades[df_trades["filled"] == True].copy() if "filled" in df_trades.columns else pd.DataFrame()
    n_trades = len(df_filled)
    stats["n_trades"] = n_trades

    if n_trades == 0: return stats

    res_R = df_filled["result_R"].astype(float)
    stats["win_rate"] = float((res_R > 0).mean()) if len(res_R) > 0 else np.nan
    stats["avg_R"] = float(res_R.mean()) if len(res_R) > 0 else np.nan

    winners = df_filled[res_R > 0]
    losers = df_filled[res_R < 0]

    stats["avg_winner_R"] = float(winners["result_R"].mean()) if not winners.empty else np.nan
    stats["avg_loser_R"] = float(losers["result_R"].mean()) if not losers.empty else np.nan
    stats["cumulative_R"] = float(res_R.sum())

    if "sl_size_pips" in df_filled.columns:
        stats["avg_sl_size_pips"] = float(df_filled["sl_size_pips"].astype(float).mean())
    else:
        stats["avg_sl_size_pips"] = np.nan

    hold_all = df_filled["holding_minutes"].astype(float)
    stats["avg_holding_minutes"] = float(hold_all.mean()) if len(hold_all) > 0 else np.nan

    hold_w = winners["holding_minutes"].astype(float) if not winners.empty else pd.Series(dtype=float)
    hold_l = losers["holding_minutes"].astype(float) if not losers.empty else pd.Series(dtype=float)

    stats["avg_holding_minutes_winners"] = float(hold_w.mean()) if len(hold_w) > 0 else np.nan
    stats["avg_holding_minutes_losers"] = float(hold_l.mean()) if len(hold_l) > 0 else np.nan

    sl_trades = df_filled[df_filled["exit_reason"].isin(["SL", "TRAILING_STOP", "TRAILING_STOP_NEAR_TP"])]
    tp_trades = df_filled[df_filled["exit_reason"] == "TP"]

    stats["avg_sl_minutes"] = float(sl_trades["holding_minutes"].astype(float).mean()) if not sl_trades.empty else np.nan
    stats["avg_tp_minutes"] = float(tp_trades["holding_minutes"].astype(float).mean()) if not tp_trades.empty else np.nan

    sort_col = "entry_time" if "entry_time" in df_filled.columns else None
    if sort_col:
        df_sorted = df_filled.sort_values(sort_col)
        res_sorted = df_sorted["result_R"].astype(float)
        max_win_streak, max_loss_streak, cur_win, cur_loss = 0, 0, 0, 0
        for r in res_sorted:
            if r > 0: cur_win += 1; cur_loss = 0
            elif r < 0: cur_loss += 1; cur_win = 0
            else: cur_win = 0; cur_loss = 0
            max_win_streak = max(max_win_streak, cur_win)
            max_loss_streak = max(max_loss_streak, cur_loss)
        
        stats["max_win_streak"] = int(max_win_streak)
        stats["max_loss_streak"] = int(max_loss_streak)
        
        equity = res_sorted.cumsum()
        eq_series = pd.concat([pd.Series([0.0]), equity], ignore_index=True)
        running_max = eq_series.cummax()
        drawdowns = running_max - eq_series
        stats["max_drawdown_R"] = float(drawdowns.max())
        stats["avg_drawdown_R"] = float(drawdowns.mean())

    stats["avg_holding_hhmm"] = _format_minutes_to_hhmm(stats.get("avg_holding_minutes"))
    stats["avg_holding_hhmm_winners"] = _format_minutes_to_hhmm(stats.get("avg_holding_minutes_winners"))
    stats["avg_holding_hhmm_losers"] = _format_minutes_to_hhmm(stats.get("avg_holding_minutes_losers"))
    stats["avg_sl_time_hhmm"] = _format_minutes_to_hhmm(stats.get("avg_sl_minutes"))
    stats["avg_tp_time_hhmm"] = _format_minutes_to_hhmm(stats.get("avg_tp_minutes"))

    return stats


# ==============================================================================
# 8. MAIN EXECUTION
# ==============================================================================

def main():
    print(f"Running Phase 3 Backtest: {SETUP_NAME}")
    if not os.path.exists(INPUT_BARS_FILE) or not os.path.exists(INPUT_SETUPS_FILE):
        print("Input files not found. Run Phase 2 first.")
        return

    df_bars = pd.read_csv(INPUT_BARS_FILE)
    df_bars = _ensure_time_columns(df_bars)
    df_setups = pd.read_csv(INPUT_SETUPS_FILE)
    
    exit_variants = ["exit_4pm", "exit_2pm", "exit_post_2pm_1st_bos", "exit_post_2pm_2nd_bos", "exit_unmanaged"]
    stats_per_exit = {}

    for exit_mode in exit_variants:
        print(f"Processing {exit_mode}...")
        results = []
        
        for i, row in df_setups.iterrows():
            date_ny = row["date_ny"]
            df_day = df_bars[df_bars["date_ny"].astype(str) == str(date_ny)].copy()
            if df_day.empty: continue
            
            expiration_str = f"{date_ny} {ENTRY_CUTOFF_HOUR:02d}:{ENTRY_CUTOFF_MINUTE:02d}:00"

            spec = build_entry_for_setup_scenario1(row, df_day, i)
            if spec is None:
                results.append({"symbol": row["symbol"], "date_ny": date_ny, "setup_index": i, "direction": row["direction"], "exit_mode": exit_mode, "filled": False, "miss_reason": "calc_error", "expiration_time": expiration_str})
                continue
            
            df_sim = df_bars if "unmanaged" in exit_mode or "post_2pm" in exit_mode else df_day
            res = simulate_trade_for_exit_mode(spec, df_sim, exit_mode)
            
            results.append({
                "symbol": spec.symbol, "date_ny": spec.date_ny, "direction": spec.direction, "scenario_id": spec.scenario_id,
                "exit_mode": exit_mode, "setup_index": spec.setup_index, "filled": res.filled, "miss_reason": res.miss_reason,
                "entry_time": res.entry_idx, "exit_time": res.exit_idx, "expiration_time": expiration_str,
                "entry_price": spec.entry_price, "sl_price": spec.sl_price, "tp_price": spec.tp_price,
                "exit_price": res.exit_price, "exit_reason": res.exit_reason, "result_R": res.result_R,
                "sl_size_pips": res.sl_size_pips, "holding_minutes": res.holding_minutes
            })
            
        df_res = pd.DataFrame(results)
        df_res = _round_trades(df_res)
        out_file = TRADES_FILE_TEMPLATE.format(exit_suffix=exit_mode)
        df_res.to_csv(out_file, index=False)
        
        if not df_res.empty:
            stats = compute_stats_comprehensive(df_res)
            stats = _round_stats_for_output(stats)
            stats_per_exit[exit_mode] = stats
        else:
            stats_per_exit[exit_mode] = {}

    if stats_per_exit:
        all_metrics = set()
        for s in stats_per_exit.values(): all_metrics.update(s.keys())
        all_metrics = sorted(all_metrics)
        
        rows = []
        # 1. Metrics
        for metric in all_metrics:
            row = {"metric": metric}
            for exit_mode in exit_variants:
                row[exit_mode] = stats_per_exit.get(exit_mode, {}).get(metric, np.nan)
            rows.append(row)

        # 2. Config Meta
        def _fmt_time(h, m): return f"{h:02d}:{m:02d}"
        config_meta = [
            ("cfg_symbol", SYMBOL),
            ("cfg_target_rr", TARGET_RR),
            ("cfg_squeeze_divisor", SQUEEZE_RISK_DIVISOR),
            ("cfg_near_tp_enabled", NEAR_TP_TRAILING_ENABLED),
            ("cfg_near_tp_trigger_r", NEAR_TP_TRIGGER_R),
            ("cfg_sl_buffer_pips", SL_BUFFER.get(SYMBOL, np.nan)),
            ("cfg_max_sl_pips", MAX_SL_SIZE.get(SYMBOL, np.nan)),
            ("cfg_entry_cutoff_time", _fmt_time(ENTRY_CUTOFF_HOUR, ENTRY_CUTOFF_MINUTE)),
            ("cfg_exit_2pm_time", _fmt_time(EXIT_2PM_HOUR, EXIT_2PM_MINUTE)),
            ("cfg_session_close_time", _fmt_time(EXIT_SESSION_CLOSE_HOUR, EXIT_SESSION_CLOSE_MINUTE)),
            ("cfg_bos_trailing_start", _fmt_time(BOS_TRAILING_START_HOUR, BOS_TRAILING_START_MINUTE)),
        ]
        for name, val in config_meta:
            row = {"metric": name}
            for exit_mode in exit_variants: row[exit_mode] = val 
            rows.append(row)
            
        df_stats = pd.DataFrame(rows)
        
        final_output_file = OUTPUT_STATS_FILE
        if not OVERWRITE_STATS_FILE and os.path.exists(final_output_file):
            final_output_file = _get_unique_filepath(final_output_file)
            
        df_stats.to_csv(final_output_file, index=False)
        print(f"Stats saved to {final_output_file}")

if __name__ == "__main__":
    main()