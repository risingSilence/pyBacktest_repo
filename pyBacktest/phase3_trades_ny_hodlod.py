print("phase3_trades_ny_hodlod.py - starting up...")

from dataclasses import dataclass
from typing import Optional, Any, Dict, List
import pandas as pd
import numpy as np
import os
import json
from config import PIP_SIZE_MAP

# ==============================================================================
# 1. CONFIGURATION & PARAMETERS
# ==============================================================================

# Liste der Symbole
SYMBOLS = ["GBPUSD"] #"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY", "GBPJPY", "EURGBP", "DXY", "US30", "NAS100", "US500", "XAUUSD"]

# WICHTIG: Muss exakt so heißen wie in der Phase 2 Datei!
SETUP_NAME = "ny_hodlod"

# --- PATHS ---
CHART_DATA_DIR = "charting/data"

# --- RISK & TRADE PARAMETERS ---
SCENARIO_ID = "london_target_min_max_rr"

# Stats Output Config
OVERWRITE_STATS_FILE = True  # True = überschreiben, False = neue Datei (_1, _2...) erstellen

# --- MINIMUM RR CONFIG ---
# Wenn Market-Entry dieses RR zum London-Target nicht erreicht, wird gesqueezed (Limit Entry).
USE_GLOBAL_MIN_RR = False
GLOBAL_MIN_RR = 3.0
MIN_RR_MAP = {
    "EURUSD": 3.0,
    "GBPUSD": 4.0,
    "AUDUSD": 2.5,
    "NZDUSD": 3.0,
    "USDCAD": 3.0,
    "USDCHF": 3.0,
    "USDJPY": 3.0,
    "GBPJPY": 3.0,
    "EURGBP": 3.0,
    "DXY":    3.0,
    "US30":   2.5, 
    "NAS100": 2.5,
    "US500":  2.5,
    "XAUUSD": 3.0,
}

# --- MAXIMUM RR CONFIG ---
# Wenn Market-Entry möglich ist, aber das RR zum London-Target > MaxRR wäre,
# wird der TP verkürzt (Entry bleibt Market), um genau MaxRR zu erzielen.
USE_GLOBAL_MAX_RR = False
GLOBAL_MAX_RR = 10.0
MAX_RR_MAP = {
    "EURUSD": 10.0,
    "GBPUSD": 10.0,
    "AUDUSD": 10.0,
    "NZDUSD": 10.0,
    "USDCAD": 10.0,
    "USDCHF": 10.0,
    "USDJPY": 10.0,
    "GBPJPY": 10.0,
    "EURGBP": 10.0,
    "DXY": 10.0,
    "US30": 10.0,
    "NAS100": 10.0,
    "US500": 10.0,
    "XAUUSD": 10.0,
}
# --- NEAR-TP TRAILING CONFIG ---
NEAR_TP_TRAILING_ENABLED = False
NEAR_TP_TRAILING_OFFSET_PCT = 0.10  # 10%

# --- SL BUFFER CONFIG (EURUSD BASE) ---
# Dynamic calculation: Base * Ratio
BASE_SL_BUFFER = 0.0

# --- TIME SETTINGS (NEW YORK TIME) ---

# Späteste Uhrzeit für einen ENTRY (Limit Fill oder Market)
ENTRY_CUTOFF_HOUR = 12
ENTRY_CUTOFF_MINUTE = 15

# Exit Zeit für den "exit_2pm" Modus
EXIT_2PM_HOUR = 14
EXIT_2PM_MINUTE = 0

# Exit Zeit für den "exit_4pm" Modus (Session Close)
EXIT_SESSION_CLOSE_HOUR = 16
EXIT_SESSION_CLOSE_MINUTE = 0

# Ab wann startet das BOS-Trailing (für exit_post_2pm_... Modi)
BOS_TRAILING_START_HOUR = 14
BOS_TRAILING_START_MINUTE = 0

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
    order_type: str
    entry_reason: str
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

# Hilfsvariable für Pfad zu Ratios (liegt im Haupt 'data' Ordner, nicht 'charting/data')
ROOT_DATA_DIR = "data"

def load_vola_ratio(symbol: str) -> float:
    # Explizit das NY Ratio File laden
    ratio_file = os.path.join(ROOT_DATA_DIR, "volatility_ratios_NY.json")
    
    if not os.path.exists(ratio_file):
        return 1.0
    try:
        with open(ratio_file, "r") as f:
            data = json.load(f)
        return data.get(symbol, 1.0)
    except:
        return 1.0

def _get_unique_filepath(path: str) -> str:
    if not os.path.exists(path): 
        return path
    base, ext = os.path.splitext(path)
    counter = 1
    while True:
        new_path = f"{base}_{counter}{ext}"
        if not os.path.exists(new_path): 
            return new_path
        counter += 1

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


# ==============================================================================
# 5. ENTRY LOGIC (London Target, Min RR Squeeze, Max RR Cap)
# ==============================================================================

def build_entry_for_setup_london_min_max_rr(setup_row: pd.Series,
                                            df_day: pd.DataFrame,
                                            setup_idx: int,
                                            sl_buffer_pips: float) -> Optional[EntrySpec]: # <--- PASS ARG
    direction = setup_row["direction"]
    symbol = setup_row["symbol"]
    date_ny = setup_row["date_ny"]
    pip_size = PIP_SIZE_MAP.get(symbol)
    if pip_size is None: return None

    
    if USE_GLOBAL_MIN_RR:
        min_rr = GLOBAL_MIN_RR
    else:
        min_rr = MIN_RR_MAP.get(symbol, GLOBAL_MIN_RR)

    if USE_GLOBAL_MAX_RR:
        max_rr = GLOBAL_MAX_RR
    else:
        max_rr = MAX_RR_MAP.get(symbol, GLOBAL_MAX_RR)

    choch_idx = setup_row["choch_idx"]
    if pd.isna(choch_idx): return None
    signal_close = float(setup_row["choch_close_price"])
    
    try:
        choch_ts = pd.to_datetime(choch_idx)
        signal_pos = df_day.index.get_loc(choch_ts)
        # Limit/Market active ab der NÄCHSTEN Kerze nach dem Signal
        activation_idx = df_day.index[signal_pos + 1] if signal_pos + 1 < len(df_day) else None
    except (KeyError, IndexError):
        return None

    if activation_idx is None: return None

    # --- DATEN FÜR LONDON LEVELS HOLEN ---
    if "london_high" not in df_day.columns or "london_low" not in df_day.columns:
        return None
    
    if pd.isna(df_day["london_high"].iloc[0]) or pd.isna(df_day["london_low"].iloc[0]):
        return None

    london_high = float(df_day["london_high"].iloc[0])
    london_low  = float(df_day["london_low"].iloc[0])

    # --- ENTRY BERECHNUNG ---
    entry_price = None
    sl_price = None
    tp_price = None
    order_type = "limit"
    entry_reason = "unknown"

    if direction == "sell":
        # Short: Target Base ist London LOW
        tp_price = london_low
        hod_price = float(setup_row["hod_price"])
        sl_price = hod_price + sl_buffer_pips * pip_size
        
        # 1. Check Market Entry (Signal Close)
        risk_market = sl_price - signal_close
        reward_market = signal_close - tp_price
        
        # Validierung: Target muss unter Entry liegen
        if reward_market <= 0: return None 
        
        rr_market = reward_market / risk_market if risk_market > 0 else 0
        
        if rr_market >= min_rr:
            # Market Entry möglich (MinRR erfüllt)
            entry_price = signal_close
            order_type = "market"
            
            # --- NEU: MaxRR Check (Upside Capping) ---
            if rr_market > max_rr:
                # Wir kürzen den TP, um exakt MaxRR zu erreichen
                # Reward = Risk * MaxRR -> (Entry - TP) = (SL - Entry) * MaxRR
                # TP = Entry - (SL - Entry) * MaxRR
                new_reward = risk_market * max_rr
                tp_price = entry_price - new_reward
                entry_reason = "Market (TP shortened to MaxRR)"
            else:
                # TP bleibt London Low
                entry_reason = "Market (RR >= Min)"
                
        else:
            # Squeeze nötig: Entry Limit höher setzen
            # Formel: (Entry - TP) / (SL - Entry) = MinRR
            # -> Entry = (MinRR * SL + TP) / (1 + MinRR)
            # Hier zielen wir IMMER auf MinRR zum London Target (kein MaxRR check nötig)
            entry_price = (min_rr * sl_price + tp_price) / (1 + min_rr)
            order_type = "limit"
            entry_reason = "Limit (Squeeze to MinRR)"
            
            # Sanity Check: Limit darf nicht über SL liegen
            if entry_price >= sl_price: return None

    else: # direction == "buy"
        # Long: Target Base ist London HIGH
        tp_price = london_high
        lod_price = float(setup_row["lod_price"])
        sl_price = lod_price - sl_buffer_pips * pip_size
        
        # 1. Check Market Entry
        risk_market = signal_close - sl_price
        reward_market = tp_price - signal_close
        
        if reward_market <= 0: return None
        
        rr_market = reward_market / risk_market if risk_market > 0 else 0
        
        if rr_market >= min_rr:
            entry_price = signal_close
            order_type = "market"
            
            # --- NEU: MaxRR Check (Upside Capping) ---
            if rr_market > max_rr:
                # TP verkürzen
                # Reward = Risk * MaxRR -> (TP - Entry) = (Entry - SL) * MaxRR
                # TP = Entry + (Entry - SL) * MaxRR
                new_reward = risk_market * max_rr
                tp_price = entry_price + new_reward
                entry_reason = "Market (TP shortened to MaxRR)"
            else:
                entry_reason = "Market (RR >= Min)"
                
        else:
            # Squeeze: Entry Limit tiefer setzen
            # Formel: (TP - Entry) / (Entry - SL) = MinRR
            # -> Entry = (TP + MinRR * SL) / (1 + MinRR)
            entry_price = (tp_price + min_rr * sl_price) / (1 + min_rr)
            order_type = "limit"
            entry_reason = "Limit (Squeeze to MinRR)"
            
            if entry_price <= sl_price: return None

    return EntrySpec(symbol, direction, date_ny, setup_idx, float(entry_price), float(sl_price), float(tp_price), activation_idx, order_type, entry_reason)


# ==============================================================================
# 6. TRADE SIMULATION & EXIT
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
        # 1. Distanz zum TP berechnen (Reward-Strecke)
        dist_to_tp = abs(entry.tp_price - entry.entry_price)
        
        # 2. Trigger-Distanz berechnen (z.B. 90% der Strecke bei 10% Offset)
        # Formel: Strecke * (1.0 - Offset)
        trigger_dist = dist_to_tp * (1.0 - NEAR_TP_TRAILING_OFFSET_PCT)
        
        # 3. Thresholds setzen
        if direction == "buy":
            threshold_long = entry.entry_price + trigger_dist
        else:
            threshold_short = entry.entry_price - trigger_dist

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

        # --- 2. EFFECTIVE SL ---
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
        
        if not near_tp_trailing_active and risk_sl_size_pips > 0:
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

    # --- INVALIDATION CHECK: WURDE TARGET VOR ENTRY GEHOLT? ---
    # Wir scannen VOR dem Fill-Check, ob das Target (oder der verkürzte TP) verletzt wurde.
    
    invalidation_price = entry.tp_price # Target ist die Invalidation Line für Entry
    
    filled = False
    entry_idx = None
    
    # Market Order -> sofort Fill an activation_idx (Signal Close)
    if entry.order_type == "market":
        filled = True
        entry_idx = df_day.index[start_pos]
        
    else:
        # Limit Order -> Wir müssen warten bis Preis zurückkommt
        for pos in range(start_pos, len(df_day)):
            row = df_day.iloc[pos]
            minute = row["minute_of_day"]
            
            if minute > NY_ENTRY_CUTOFF_MOD: break
            
            h, l = float(row["high"]), float(row["low"])
            
            # 1. Check Invalidation (Target Hit BEFORE Entry)
            is_invalid = False
            if direction == "sell":
                if l <= invalidation_price: is_invalid = True
            else:
                if h >= invalidation_price: is_invalid = True
                
            if is_invalid:
                return ExitResult(False, "target_hit_before_entry", None, None, None, None, None, None, None)

            # 2. Check Fill
            if direction == "sell":
                if h >= entry.entry_price:
                    filled = True; entry_idx = df_day.index[pos]; break
            else:
                if l <= entry.entry_price:
                    filled = True; entry_idx = df_day.index[pos]; break

    if not filled: return ExitResult(False, "no_fill_until_noon", None, None, None, None, None, None, None)

    # Determine Session Close Time
    session_close_mod, bos_target = NY_SESSION_CLOSE_MOD, None
    if exit_mode == "exit_2pm": session_close_mod = NY_2PM_MOD
    elif exit_mode == "exit_unmanaged": session_close_mod = None
    
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

# ---------------------------------
# MAIN EXECUTION
# ---------------------------------

def run_phase3_one_leg_for_symbol(symbol: str):
    print(f"--- Processing Phase 3 (One Leg) for {symbol} ---")

    # Dateinamen dynamisch bauen (Input: Phase 2 Output, simplified)
    input_bars_filename = f"data_{symbol}_M5_signals_{SETUP_NAME}.csv"
    input_bars_file = os.path.join(CHART_DATA_DIR, input_bars_filename)

    input_setups_filename = f"data_{symbol}_M5_setups_{SETUP_NAME}.csv"
    input_setups_file = os.path.join(CHART_DATA_DIR, input_setups_filename)

    # Templates für Output (Vereinfacht)
    # Output: data_EURGBP_M5_trades_ny_hodlod_exit_4pm.csv
    trades_file_template = os.path.join(CHART_DATA_DIR, f"data_{symbol}_M5_trades_{SETUP_NAME}_{{exit_suffix}}.csv")
    
    # NEU: Stats Ordner erstellen und Pfad anpassen (Vereinfacht)
    stats_dir = os.path.join(CHART_DATA_DIR, "stats")
    os.makedirs(stats_dir, exist_ok=True)
    # Stats: data_EURGBP_M5_stats_ny_hodlod.csv
    output_stats_file = os.path.join(stats_dir, f"data_{symbol}_M5_stats_{SETUP_NAME}.csv")

    if not os.path.exists(input_bars_file) or not os.path.exists(input_setups_file):
        print(f"Skipping {symbol}: Input files not found. Run Phase 2 first.")
        print(f"Expected: {input_bars_file}")
        return

    df_bars = pd.read_csv(input_bars_file)
    df_bars = _ensure_time_columns(df_bars)
    df_setups = pd.read_csv(input_setups_file)

    # --- DYNAMIC PARAMS ---
    vola_ratio = load_vola_ratio(symbol)
    effective_sl_buffer = BASE_SL_BUFFER * vola_ratio
    print(f"Volatility Ratio: {vola_ratio:.4f}, SL Buffer: {effective_sl_buffer:.2f} pips")
    
    exit_variants = ["exit_4pm", "exit_2pm", "exit_unmanaged"]
    stats_per_exit = {}

    for exit_mode in exit_variants:
        results = []
        
        for i, row in df_setups.iterrows():
            date_ny = row["date_ny"]
            df_day = df_bars[df_bars["date_ny"].astype(str) == str(date_ny)].copy()
            if df_day.empty: continue
            
            expiration_str = f"{date_ny} {ENTRY_CUTOFF_HOUR:02d}:{ENTRY_CUTOFF_MINUTE:02d}:00"

            spec = build_entry_for_setup_london_min_max_rr(row, df_day, i, effective_sl_buffer) # <--- PASS ARG
            if spec is None:
                # Entry nicht möglich
                results.append({"symbol": row["symbol"], "date_ny": date_ny, "setup_index": i, "direction": row["direction"], "exit_mode": exit_mode, "filled": False, "miss_reason": "calc_error_or_invalid", "expiration_time": expiration_str})
                continue
            
            df_sim = df_bars if "unmanaged" in exit_mode or "post_2pm" in exit_mode else df_day
            res = simulate_trade_for_exit_mode(spec, df_sim, exit_mode)
            
            results.append({
                "symbol": spec.symbol, "date_ny": spec.date_ny, "direction": spec.direction, "scenario_id": spec.scenario_id,
                "exit_mode": exit_mode, "setup_index": spec.setup_index, "filled": res.filled, "miss_reason": res.miss_reason,
                "entry_time": res.entry_idx, "exit_time": res.exit_idx, "expiration_time": expiration_str,
                "entry_price": spec.entry_price, "sl_price": spec.sl_price, "tp_price": spec.tp_price,
                "exit_price": res.exit_price, "exit_reason": res.exit_reason, "result_R": res.result_R,
                "sl_size_pips": res.sl_size_pips, "holding_minutes": res.holding_minutes,
                "entry_reason": spec.entry_reason
            })
            
        df_res = pd.DataFrame(results)
        df_res = _round_trades(df_res)
        out_file = trades_file_template.format(exit_suffix=exit_mode)
        df_res.to_csv(out_file, index=False)
        
        if not df_res.empty:
            stats = compute_stats_comprehensive(df_res)
            stats = _round_stats_for_output(stats)
            stats_per_exit[exit_mode] = stats
        else:
            stats_per_exit[exit_mode] = {}

    # Save Stats
    if stats_per_exit:
        all_metrics = set()
        for s in stats_per_exit.values(): all_metrics.update(s.keys())
        all_metrics = sorted(all_metrics)
        
        rows = []
        
        # 1. Performance Metrics
        for metric in all_metrics:
            row = {"metric": metric}
            for exit_mode in exit_variants:
                row[exit_mode] = stats_per_exit.get(exit_mode, {}).get(metric, np.nan)
            rows.append(row)

        # 2. Configuration Metadata
        def _fmt_time(h, m): return f"{h:02d}:{m:02d}"
        
        eff_min_rr = GLOBAL_MIN_RR if USE_GLOBAL_MIN_RR else MIN_RR_MAP.get(symbol, GLOBAL_MIN_RR)
        eff_max_rr = GLOBAL_MAX_RR if USE_GLOBAL_MAX_RR else MAX_RR_MAP.get(symbol, GLOBAL_MAX_RR)

        config_meta = [
            ("cfg_symbol", symbol),
            ("cfg_min_rr", eff_min_rr),
            ("cfg_max_rr", eff_max_rr),
            ("cfg_target", "London High/Low"),
            ("cfg_entry_logic", "Market or Squeeze Limit"),
            ("cfg_near_tp_enabled", NEAR_TP_TRAILING_ENABLED),
            ("cfg_sl_buffer_pips", effective_sl_buffer), # <--- USE DYNAMIC VAR
            ("cfg_vola_ratio", vola_ratio),              # <--- Ratio loggen
            ("cfg_entry_cutoff_time", _fmt_time(ENTRY_CUTOFF_HOUR, ENTRY_CUTOFF_MINUTE)),
            ("cfg_exit_2pm_time", _fmt_time(EXIT_2PM_HOUR, EXIT_2PM_MINUTE)),
            ("cfg_session_close_time", _fmt_time(EXIT_SESSION_CLOSE_HOUR, EXIT_SESSION_CLOSE_MINUTE)),
        ]

        for name, val in config_meta:
            row = {"metric": name}
            for exit_mode in exit_variants:
                row[exit_mode] = val 
            rows.append(row)
            
        df_stats = pd.DataFrame(rows)
        
        final_output_file = output_stats_file
        if not OVERWRITE_STATS_FILE and os.path.exists(final_output_file):
            final_output_file = _get_unique_filepath(final_output_file)
            
        df_stats.to_csv(final_output_file, index=False)
        print(f"Stats saved to {final_output_file}")
    
    print(f"Done for {symbol}.\n")


def main():
    for sym in SYMBOLS:
        run_phase3_one_leg_for_symbol(sym)


if __name__ == "__main__":
    main()