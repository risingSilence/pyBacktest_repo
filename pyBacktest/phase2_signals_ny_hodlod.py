print("phase2_signals_ny_hodlod.py - starting up...")

import pandas as pd
import os
import json
import numpy as np

try:
    from config import START_DATE, END_DATE, PIP_SIZE_MAP
    START_DATE_NY = START_DATE
    END_DATE_NY = END_DATE
except ImportError:
    # Fallback, if config.py is not found or testing standalone
    from datetime import datetime
    print("WARN: config.py dates not found, using default dates.")
    START_DATE_NY = datetime(2023, 1, 1) # Fallback
    END_DATE_NY   = datetime(2025, 11, 21) # Fallback

# ---------------------------------
# CONFIG
# ---------------------------------

# Liste der Symbole
SYMBOLS = ["GBPUSD"] #"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY", "GBPJPY", "EURGBP", "DXY", "US30", "NAS100", "US500", "XAUUSD"]

# Setup-Name für Dateinamen (VEREINFACHT)
SETUP_NAME = "ny_hodlod"

# Suffix der VORHERIGEN Phase (Input), um die richtigen Struktur-Daten zu finden
PHASE1_INPUT_SUFFIX = "_NY" 

# TIME FRAME KONFIGURATION
SETUP_TF = "M5"              # Der Timeframe, auf dem wir suchen
SETUP_TF_MINUTES = 5         # Dauer einer Kerze in Minuten (für End-Zeit-Berechnung)

# Pfade definieren
BASE_DATA_DIR = "data"             # Hier liegt der Phase 1 Output
CHART_DATA_DIR = "charting/data"   # Hierhin schreiben wir für die HTML

# ---------------------------------
# BASE CONFIG (EURUSD BASELINE)
# ---------------------------------
# Base Values for EURUSD (Ratio 1.0)

BASE_MIN_RANGE = 7.0        # Pips Range (HOD -> Breakdown Low)
BASE_MIN_SINGLE_FVG = 0.5   # Pips FVG Size

# NY-Zeitfenster in Minuten seit 00:00
NY_START_HOD_LOD = 8 * 60 + 30      # 08:30
NY_END_HOD_LOD   = 11 * 60          # 11:00 (Anker muss in diesem Fenster liegen)
NY_SIGNAL_CUTOFF = 11 * 60 + 30     # 11:30 (Signal/CHOCH muss davor passieren)

# ---------------------------------
# Hilfsfunktionen (Zeit & Index)
# ---------------------------------

def _ensure_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "time_ny" in df.columns:
        df["time_ny"] = pd.to_datetime(df["time_ny"])
        df = df.set_index("time_ny")
        df.index.name = "time_ny"
    else:
        df.index = pd.to_datetime(df.index)
        df.index.name = "time_ny"

    if "hour_ny" not in df.columns or "minute_ny" not in df.columns:
        idx = df.index
        df["hour_ny"] = idx.hour
        df["minute_ny"] = idx.minute

    df["hour_ny"] = df["hour_ny"].astype(int)
    df["minute_ny"] = df["minute_ny"].astype(int)
    df["minute_of_day"] = df["hour_ny"] * 60 + df["minute_ny"]

    if "date_ny" not in df.columns:
        df["date_ny"] = df.index.date

    return df


def _build_index_maps(df: pd.DataFrame):
    idx_list = list(df.index)
    idx_to_pos = {idx: i for i, idx in enumerate(idx_list)}
    return idx_list, idx_to_pos


# ---------------------------------
# FVG-Scan
# ---------------------------------

def _scan_bear_fvgs_for_leg(highs, lows, start_pos: int, end_pos: int, pip_size: float):
    """
    Bear-FVGs (downtrend): high[i+1] < low[i-1].
    """
    if end_pos - start_pos < 2:
        return []

    sizes = []
    for i in range(start_pos + 1, end_pos):
        left = i - 1
        right = i + 1
        if left < 0 or right >= len(highs):
            continue
        if highs[right] < lows[left]:
            size_price = lows[left] - highs[right]
            if size_price > 0:
                sizes.append(size_price / pip_size)
    return sizes


def _scan_bull_fvgs_for_leg(highs, lows, start_pos: int, end_pos: int, pip_size: float):
    """
    Bull-FVGs (uptrend): low[i+1] > high[i-1].
    """
    if end_pos - start_pos < 2:
        return []

    sizes = []
    for i in range(start_pos + 1, end_pos):
        left = i - 1
        right = i + 1
        if left < 0 or right >= len(highs):
            continue
        if lows[right] > highs[left]:
            size_price = lows[right] - highs[left]
            if size_price > 0:
                sizes.append(size_price / pip_size)
    return sizes

# ---------------------------------
# LOAD VOLA RATIO
# ---------------------------------

def load_vola_ratio(symbol: str) -> float:
    # Explizit das NY Ratio File laden
    ratio_file = os.path.join(BASE_DATA_DIR, "volatility_ratios_NY.json") # BASE_DATA_DIR ist "data"
    
    if not os.path.exists(ratio_file):
        return 1.0
    try:
        with open(ratio_file, "r") as f:
            data = json.load(f)
        return data.get(symbol, 1.0)
    except:
        return 1.0


# ---------------------------------
# SELL-Setup: HOD (HH) -> Break of prev HL (Close)
# ---------------------------------

def find_sell_setup_for_day(df_sym: pd.DataFrame,
                            df_day: pd.DataFrame,
                            symbol: str,
                            idx_to_pos,
                            highs,
                            lows,
                            pip_size: float,
                            min_range_pips: float,
                            min_single_fvg: float):
    """
    SELL-Setup (HOD-Seite, One Leg - Direct Break).
    """
    min_range = min_range_pips
    min_single = min_single_fvg

    df_day = df_day.sort_index()

    anchor_hh_idx = None
    anchor_hh_row = None
    anchor_hh_high = None
    
    # Das Level, das gebrochen werden muss (letztes HL vor dem HOD)
    break_level = None

    for idx, row in df_day.iterrows():
        minute = int(row["minute_of_day"])

        # 1) Anker-HH (HOD) im Fenster
        if (
            row.get("swing_high_label") == "HH"
            and bool(row.get("is_day_high_bar", False))
            and NY_START_HOD_LOD <= minute <= NY_END_HOD_LOD
        ):
            # Neuer potenzieller Anker gefunden
            pos_hod = idx_to_pos.get(idx)
            if pos_hod is None: continue
            
            # Suche rückwärts ab pos_hod - 1 nach einem Swing Low
            found_hl_price = None
            start_search = max(0, pos_hod - 500)
            
            for k in range(pos_hod - 1, start_search - 1, -1):
                val = df_sym.iat[k, df_sym.columns.get_loc("swing_low_label")]
                if val and isinstance(val, str) and val in ["HL", "LL", "L0", "L_eq"]:
                    found_hl_price = df_sym.iat[k, df_sym.columns.get_loc("swing_low_price")]
                    break
            
            if found_hl_price is not None:
                anchor_hh_idx = idx
                anchor_hh_row = row
                anchor_hh_high = float(row["high"])
                break_level = float(found_hl_price)
            else:
                anchor_hh_idx = None
                break_level = None
            
            continue

        if anchor_hh_idx is None or break_level is None:
            continue

        # 2) TRIGGER: Close unter break_level
        if minute >= NY_SIGNAL_CUTOFF:
            anchor_hh_idx = None
            break_level = None
            continue

        close_price = float(row["close"])
        
        if close_price < break_level:
            # --- SIGNAL: CHOCH ---
            
            if "has_broken_london_low" in df_day.columns:
                val = row.get("has_broken_london_low")
                if pd.notna(val) and bool(val):
                    anchor_hh_idx = None
                    break_level = None
                    continue

            current_low = float(row["low"])
            range_price = anchor_hh_high - current_low
            range_pips = range_price / pip_size
            
            if range_pips < min_range:
                anchor_hh_idx = None
                continue

            signal_idx = idx
            pos_hod = idx_to_pos[anchor_hh_idx]
            pos_signal = idx_to_pos[signal_idx]
            
            sizes_leg1 = _scan_bear_fvgs_for_leg(highs, lows, pos_hod, pos_signal, pip_size)
            
            if not sizes_leg1 or max(sizes_leg1) < min_single:
                anchor_hh_idx = None
                continue
            
            signal_end_ts = pd.Timestamp(signal_idx) + pd.Timedelta(minutes=SETUP_TF_MINUTES)

            return {
                "direction": "sell",
                "symbol": symbol,
                "date_ny": df_day["date_ny"].iloc[0],
                "signal_tf": SETUP_TF,
                "signal_start_time": anchor_hh_idx,
                "signal_end_time": signal_end_ts,

                "hod_idx": anchor_hh_idx,
                "ll1_idx": signal_idx, 
                "choch_idx": signal_idx,
                
                "hod_price": anchor_hh_high,
                "ll1_price": current_low, 
                "choch_close_price": close_price,
                
                "break_level_price": break_level,
                "range_pips": range_pips,
                "fvg_max_leg1": max(sizes_leg1) if sizes_leg1 else 0.0,
                "fvg_max_leg2": 0.0 
            }

    return None


# ---------------------------------
# BUY-Setup: LOD (LL) -> Break of prev LH (Close)
# ---------------------------------

def find_buy_setup_for_day(df_sym: pd.DataFrame,
                           df_day: pd.DataFrame,
                           symbol: str,
                           idx_to_pos,
                           highs,
                           lows,
                           pip_size: float,
                           min_range_pips: float,
                           min_single_fvg: float):
    
    min_range = min_range_pips
    min_single = min_single_fvg

    df_day = df_day.sort_index()

    anchor_ll_idx = None
    anchor_ll_row = None
    anchor_ll_low = None
    
    break_level = None

    for idx, row in df_day.iterrows():
        minute = int(row["minute_of_day"])

        # 1) Anker-LL (LOD) im Fenster
        if (
            row.get("swing_low_label") == "LL"
            and bool(row.get("is_day_low_bar", False))
            and NY_START_HOD_LOD <= minute <= NY_END_HOD_LOD
        ):
            pos_lod = idx_to_pos.get(idx)
            if pos_lod is None: continue
            
            found_lh_price = None
            start_search = max(0, pos_lod - 500)
            
            for k in range(pos_lod - 1, start_search - 1, -1):
                val = df_sym.iat[k, df_sym.columns.get_loc("swing_high_label")]
                if val and isinstance(val, str) and val in ["LH", "HH", "H0", "H_eq"]:
                    found_lh_price = df_sym.iat[k, df_sym.columns.get_loc("swing_high_price")]
                    break
            
            if found_lh_price is not None:
                anchor_ll_idx = idx
                anchor_ll_row = row
                anchor_ll_low = float(row["low"])
                break_level = float(found_lh_price)
            else:
                anchor_ll_idx = None
                break_level = None
            
            continue

        if anchor_ll_idx is None or break_level is None:
            continue

        # 2) TRIGGER: Close über break_level
        if minute >= NY_SIGNAL_CUTOFF:
            anchor_ll_idx = None
            break_level = None
            continue
            
        close_price = float(row["close"])
        
        if close_price > break_level:
            # --- SIGNAL ---
            
            if "has_broken_london_high" in df_day.columns:
                val = row.get("has_broken_london_high")
                if pd.notna(val) and bool(val):
                    anchor_ll_idx = None
                    break_level = None
                    continue
            
            current_high = float(row["high"])
            range_price = current_high - anchor_ll_low
            range_pips = range_price / pip_size
            
            if range_pips < min_range:
                anchor_ll_idx = None 
                continue
            
            signal_idx = idx
            pos_lod = idx_to_pos[anchor_ll_idx]
            pos_signal = idx_to_pos[signal_idx]
            
            sizes_leg1 = _scan_bull_fvgs_for_leg(highs, lows, pos_lod, pos_signal, pip_size)
            
            if not sizes_leg1 or max(sizes_leg1) < min_single:
                anchor_ll_idx = None
                continue
            
            signal_end_ts = pd.Timestamp(signal_idx) + pd.Timedelta(minutes=SETUP_TF_MINUTES)

            return {
                "direction": "buy",
                "symbol": symbol,
                "date_ny": df_day["date_ny"].iloc[0],
                "signal_tf": SETUP_TF,
                "signal_start_time": anchor_ll_idx,
                "signal_end_time": signal_end_ts,

                "lod_idx": anchor_ll_idx,
                "hh1_idx": signal_idx,
                "choch_idx": signal_idx,
                
                "lod_price": anchor_ll_low,
                "hh1_price": current_high,
                "choch_close_price": close_price,
                "break_level_price": break_level,
                
                "range_pips": range_pips,
                "fvg_max_leg1": max(sizes_leg1) if sizes_leg1 else 0.0,
                "fvg_max_leg2": 0.0
            }
    
    return None

# ---------------------------------
# MAIN-LOGIK
# ---------------------------------

def run_phase2_one_leg_for_symbol(symbol: str):
    print(f"--- Processing Phase 2 (One Leg) for {symbol} ---")

    if not os.path.exists(CHART_DATA_DIR):
        os.makedirs(CHART_DATA_DIR)

    # Dateinamen dynamisch: INPUT kommt von Phase 1 (behält _NY suffix)
    input_filename = f"data_{symbol}_M5_phase1_structure{PHASE1_INPUT_SUFFIX}.csv"
    input_file = os.path.join(BASE_DATA_DIR, input_filename)

    # Dateinamen dynamisch: OUTPUT ist vereinfacht!
    output_bars_filename = f"data_{symbol}_M5_signals_{SETUP_NAME}.csv"
    output_bars_file = os.path.join(CHART_DATA_DIR, output_bars_filename)

    output_setups_filename = f"data_{symbol}_M5_setups_{SETUP_NAME}.csv"
    output_setups_file = os.path.join(CHART_DATA_DIR, output_setups_filename)

    if not os.path.exists(input_file):
        print(f"Skipping {symbol}: Input file not found ({input_file})")
        return

    if symbol not in PIP_SIZE_MAP:
        print(f"Skipping {symbol}: No PIP_SIZE_MAP entry.")
        return
    pip_size = PIP_SIZE_MAP[symbol]

    print(f"Loading input file {input_file} ...")
    df = pd.read_csv(input_file)

    if "time_ny" not in df.columns:
        raise RuntimeError("Column 'time_ny' not found in input file.")

    df = _ensure_time_columns(df)

    # --- DATE FILTER (from config.py) ---
    print(f"Filtering data to range: {START_DATE_NY} -> {END_DATE_NY}")
    mask = (df.index >= START_DATE_NY) & (df.index < END_DATE_NY)
    df = df.loc[mask]

    if df.empty:
        print(f"No data left after filtering for {START_DATE_NY} to {END_DATE_NY}")
        return
    # ------------------------------------

    df_sym = df[df["symbol"] == symbol].copy()
    if df_sym.empty:
        print(f"No data for {symbol} in {input_file}")
        return

    df_sym = df_sym.sort_index()

    idx_list, idx_to_pos = _build_index_maps(df_sym)
    highs = df_sym["high"].astype(float).values
    lows = df_sym["low"].astype(float).values

    df_sym["sell_signal_top"] = False
    df_sym["sell_signal_bottom"] = False
    df_sym["buy_signal_bottom"] = False
    df_sym["buy_signal_top"] = False

    setups = []

    # --- DYNAMIC PARAMS ---
    vola_ratio = load_vola_ratio(symbol)
    
    # Berechne die effektiven Werte für dieses Symbol
    effective_min_range = BASE_MIN_RANGE * vola_ratio
    effective_min_fvg   = BASE_MIN_SINGLE_FVG * vola_ratio
    
    print(f"Volatility Ratio: {vola_ratio:.4f}")
    print(f"Effective Min Range: {effective_min_range:.2f} pips")
    print(f"Effective Min FVG:   {effective_min_fvg:.2f} pips")

    print(f"Scanning for {SETUP_NAME} setups...")
    
    for day, df_day in df_sym.groupby("date_ny"):
        df_day = df_day.sort_index()

        sell_setup = find_sell_setup_for_day(
            df_sym=df_sym,
            df_day=df_day,
            symbol=symbol,
            idx_to_pos=idx_to_pos,
            highs=highs,
            lows=lows,
            pip_size=pip_size,
            min_range_pips=effective_min_range,  # <--- Pass dynamic value
            min_single_fvg=effective_min_fvg     # <--- Pass dynamic value
        )
        if sell_setup is not None:
            hod_idx = sell_setup["hod_idx"]
            choch_idx = sell_setup["choch_idx"] 
            
            if hod_idx in df_sym.index:
                df_sym.loc[hod_idx, "sell_signal_top"] = True
            if choch_idx in df_sym.index:
                df_sym.loc[choch_idx, "sell_signal_bottom"] = True
            setups.append(sell_setup)

        buy_setup = find_buy_setup_for_day(
            df_sym=df_sym,
            df_day=df_day,
            symbol=symbol,
            idx_to_pos=idx_to_pos,
            highs=highs,
            lows=lows,
            pip_size=pip_size,
            min_range_pips=effective_min_range,  # <--- Pass dynamic value
            min_single_fvg=effective_min_fvg     # <--- Pass dynamic value
        )
        if buy_setup is not None:
            lod_idx = buy_setup["lod_idx"]
            choch_idx = buy_setup["choch_idx"] 
            
            if lod_idx in df_sym.index:
                df_sym.loc[lod_idx, "buy_signal_bottom"] = True
            if choch_idx in df_sym.index:
                df_sym.loc[choch_idx, "buy_signal_top"] = True
            setups.append(buy_setup)

    print(f"Total setups found: {len(setups)}")

    print(f"Saving bars with signals to {output_bars_file} ...")
    df_sym.to_csv(output_bars_file, index=True)
    
    if setups:
        df_setups = pd.DataFrame(setups)
        for col in [c for c in df_setups.columns if c.endswith("_time") or c.endswith("_idx")]:
            try:
                df_setups[col] = pd.to_datetime(df_setups[col]).dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass
        print(f"Saving setups summary to {output_setups_file} ...")
        df_setups.to_csv(output_setups_file, index=False)
    else:
        print("No setups found, no setups CSV written.")
    
    print(f"Done for {symbol}.\n")


def main():
    for sym in SYMBOLS:
        run_phase2_one_leg_for_symbol(sym)


if __name__ == "__main__":
    print("Entering main() ...")
    try:
        main()
    except Exception:
        import traceback
        print("ERROR in phase2_signals_ny_hodlod.py:")
        traceback.print_exc()