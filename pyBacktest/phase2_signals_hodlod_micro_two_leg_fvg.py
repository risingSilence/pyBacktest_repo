print("phase2_signals_hodlod_micro_two_leg_fvg.py - starting up...")

import pandas as pd
import os
import numpy as np
try:
    from config import START_DATE_NY, END_DATE_NY
except ImportError:
    from datetime import datetime
    print("WARN: config.py not found, using default dates.")
    START_DATE_NY = datetime(2025, 11, 1) # NUR FALLBACK!!!
    END_DATE_NY   = datetime(2025, 11, 8) # NUR FALLBACK!!!

# ---------------------------------
# CONFIG
# ---------------------------------

SYMBOL = "EURUSD"

# Setup-Name für Dateinamen
SETUP_NAME = "hodlod_micro_two_leg_fvg"

# TIME FRAME KONFIGURATION
SETUP_TF = "M5"              # Der Timeframe, auf dem wir suchen
SETUP_TF_MINUTES = 5         # Dauer einer Kerze in Minuten (für End-Zeit-Berechnung)

# Pfade definieren
BASE_DATA_DIR = "data"             # Hier liegt der Phase 1 Output
CHART_DATA_DIR = "charting/data"   # Hierhin schreiben wir für die HTML

# Input: Struktur-Daten aus Phase 1
INPUT_FILENAME = f"data_{SYMBOL}_M5_phase1_structure.csv"
INPUT_FILE = os.path.join(BASE_DATA_DIR, INPUT_FILENAME)

# Output 1: Die Bars mit den Signalen (für Phase 3 und Visualisierung)
OUTPUT_BARS_FILENAME = f"data_{SYMBOL}_M5_signals_{SETUP_NAME}.csv"
OUTPUT_BARS_FILE = os.path.join(CHART_DATA_DIR, OUTPUT_BARS_FILENAME)

# Output 2: Die Setups/Boxen (für Phase 3 und Visualisierung)
OUTPUT_SETUPS_FILENAME = f"data_{SYMBOL}_M5_setups_{SETUP_NAME}.csv"
OUTPUT_SETUPS_FILE = os.path.join(CHART_DATA_DIR, OUTPUT_SETUPS_FILENAME)

# Parameter
PIP_SIZE_MAP = {
    "AUDUSD": 0.0001,
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
}

# NEU: Reduzierte Range-Vorgaben (One Leg)
MIN_RANGE = {
    "AUDUSD": 5.0,
    "EURUSD": 7.0,
    "GBPUSD": 9.0,
}

# NEU: FVG Mindestgröße für das einzelne Leg
MIN_SINGLE_FVG = {
    "AUDUSD": 0.3,
    "EURUSD": 0.5,
    "GBPUSD": 0.8,
}

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
# FVG-Scan (identisch zu Phase 2 alt, aber wir nutzen nur das Resultat für Leg 1)
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
# SELL-Setup: HOD (HH) -> LL1 -> CHOCH (Close < LL1)
# ---------------------------------

def find_sell_setup_for_day(df_sym: pd.DataFrame,
                            df_day: pd.DataFrame,
                            symbol: str,
                            idx_to_pos,
                            highs,
                            lows,
                            pip_size: float):
    """
    SELL-Setup (HOD-Seite, One Leg).
    Struktur: HOD -> LL1. 
    Trigger: Close < LL1 Low (Strict).
    Validierung: Range HOD-LL1 & FVG in Leg 1.
    """

    min_range = MIN_RANGE[symbol]
    min_single = MIN_SINGLE_FVG[symbol]

    df_day = df_day.sort_index()

    anchor_hh_idx = None
    anchor_hh_row = None
    anchor_hh_high = None

    ll1_idx = None
    ll1_row = None
    ll1_low = None

    for idx, row in df_day.iterrows():
        minute = int(row["minute_of_day"])

        # 1) Anker-HH (HOD) im Fenster
        if (
            row.get("swing_high_label") == "HH"
            and bool(row.get("is_day_high_bar", False))
            and NY_START_HOD_LOD <= minute <= NY_END_HOD_LOD
        ):
            anchor_hh_idx = idx
            anchor_hh_row = row
            anchor_hh_high = float(row["high"])
            
            # Reset bei neuem Anker
            ll1_idx = ll1_row = None
            ll1_low = None

        if anchor_hh_idx is None:
            continue

        # 2) LL1: Erstes Swing Low nach dem Anker
        if ll1_idx is None and row.get("swing_low_label") == "LL" and idx > anchor_hh_idx:
            # Validierung des Beins (HOD -> LL1) BEVOR wir auf CHOCH warten
            # Das spart Rechenzeit und filtert "schlechte" Legs früh raus.
            
            # A) Range Check
            range_price = anchor_hh_high - float(row["low"])
            range_pips = range_price / pip_size
            
            if range_pips < min_range:
                # Leg zu klein -> Setup verwerfen (warten auf neuen Anker)
                # (Streng genommen könnte man warten ob noch ein tieferes LL kommt,
                # aber im "First Swing"-Ansatz ist das LL1 fix).
                # Wir resetten hier den Anker NICHT zwingend, vllt kommt noch ein besseres LL?
                # Aber per Definition "First Swing Low" ist das hier LL1.
                # Wenn das zu klein ist, ist das Setup tot für diesen HOD.
                anchor_hh_idx = None # Reset, da Struktur kaputt (zu klein)
                continue

            # B) FVG Check
            pos_hod = idx_to_pos[anchor_hh_idx]
            pos_ll1 = idx_to_pos[idx]
            sizes_leg1 = _scan_bear_fvgs_for_leg(highs, lows, pos_hod, pos_ll1, pip_size)
            
            if not sizes_leg1 or max(sizes_leg1) < min_single:
                # Kein ausreichendes FVG -> Setup tot für diesen HOD
                anchor_hh_idx = None
                continue
            
            # Leg ist valide -> Speichern
            ll1_idx = idx
            ll1_row = row
            ll1_low = float(row["low"])
            continue

        # 3) CHOCH Trigger: Close STRIKT unter LL1
        if ll1_idx is not None and idx > ll1_idx:
            # Cutoff Zeit prüfen
            if minute >= NY_SIGNAL_CUTOFF:
                # Zu spät -> Setup verwerfen
                anchor_hh_idx = None
                ll1_idx = None
                continue

            close_price = float(row["close"])
            
            if close_price < ll1_low:
                # CHOCH! Setup validiert.
                
                # London Low Check (Hard Filter)
                if "has_broken_london_low" in df_day.columns:
                    val = row.get("has_broken_london_low")
                    if pd.notna(val) and bool(val):
                        # London Low schon weg -> Invalid
                        anchor_hh_idx = None # Reset
                        ll1_idx = None
                        continue

                # Setup gefunden!
                signal_idx = idx
                
                # Werte für Output berechnen
                range_price = anchor_hh_high - ll1_low
                range_pips = range_price / pip_size
                
                # FVG Infos nochmal holen (waren ja schon validiert, aber für Output)
                pos_hod = idx_to_pos[anchor_hh_idx]
                pos_ll1 = idx_to_pos[ll1_idx]
                sizes_leg1 = _scan_bear_fvgs_for_leg(highs, lows, pos_hod, pos_ll1, pip_size)
                
                signal_end_ts = pd.Timestamp(signal_idx) + pd.Timedelta(minutes=SETUP_TF_MINUTES)

                return {
                    "direction": "sell",
                    "symbol": symbol,
                    "date_ny": df_day["date_ny"].iloc[0],
                    "signal_tf": SETUP_TF,
                    "signal_start_time": anchor_hh_idx,
                    "signal_end_time": signal_end_ts,

                    # Wichtige Punkte
                    "hod_idx": anchor_hh_idx,
                    "ll1_idx": ll1_idx,
                    "choch_idx": signal_idx, # Signal Kerze
                    
                    "hod_price": anchor_hh_high,
                    "ll1_price": ll1_low,
                    "choch_close_price": close_price,
                    
                    "range_pips": range_pips,
                    "fvg_max_leg1": max(sizes_leg1) if sizes_leg1 else 0.0,
                    # Leg 2 gibt es nicht, setzen wir auf 0 oder leer
                    "fvg_max_leg2": 0.0 
                }

    return None


# ---------------------------------
# BUY-Setup: LOD (LL) -> HH1 -> CHOCH (Close > HH1)
# ---------------------------------

def find_buy_setup_for_day(df_sym: pd.DataFrame,
                           df_day: pd.DataFrame,
                           symbol: str,
                           idx_to_pos,
                           highs,
                           lows,
                           pip_size: float):
    """
    BUY-Setup (LOD-Seite, One Leg).
    Struktur: LOD -> HH1.
    Trigger: Close > HH1 High (Strict).
    """

    min_range = MIN_RANGE[symbol]
    min_single = MIN_SINGLE_FVG[symbol]

    df_day = df_day.sort_index()

    anchor_ll_idx = None
    anchor_ll_row = None
    anchor_ll_low = None

    hh1_idx = None
    hh1_row = None
    hh1_high = None

    for idx, row in df_day.iterrows():
        minute = int(row["minute_of_day"])

        # 1) Anker-LL (LOD) im Fenster
        if (
            row.get("swing_low_label") == "LL"
            and bool(row.get("is_day_low_bar", False))
            and NY_START_HOD_LOD <= minute <= NY_END_HOD_LOD
        ):
            anchor_ll_idx = idx
            anchor_ll_row = row
            anchor_ll_low = float(row["low"])
            
            hh1_idx = hh1_row = None
            hh1_high = None

        if anchor_ll_idx is None:
            continue

        # 2) HH1: Erstes Swing High nach dem Anker
        if hh1_idx is None and row.get("swing_high_label") == "HH" and idx > anchor_ll_idx:
            # Validierung Leg 1
            
            # A) Range
            range_price = float(row["high"]) - anchor_ll_low
            range_pips = range_price / pip_size
            
            if range_pips < min_range:
                anchor_ll_idx = None 
                continue
            
            # B) FVG
            pos_lod = idx_to_pos[anchor_ll_idx]
            pos_hh1 = idx_to_pos[idx]
            sizes_leg1 = _scan_bull_fvgs_for_leg(highs, lows, pos_lod, pos_hh1, pip_size)
            
            if not sizes_leg1 or max(sizes_leg1) < min_single:
                anchor_ll_idx = None
                continue
            
            hh1_idx = idx
            hh1_row = row
            hh1_high = float(row["high"])
            continue

        # 3) CHOCH Trigger: Close STRIKT über HH1
        if hh1_idx is not None and idx > hh1_idx:
            if minute >= NY_SIGNAL_CUTOFF:
                anchor_ll_idx = None
                hh1_idx = None
                continue
                
            close_price = float(row["close"])
            
            if close_price > hh1_high:
                # CHOCH!
                
                # London High Filter
                if "has_broken_london_high" in df_day.columns:
                    val = row.get("has_broken_london_high")
                    if pd.notna(val) and bool(val):
                        anchor_ll_idx = None
                        hh1_idx = None
                        continue
                
                signal_idx = idx
                
                range_price = hh1_high - anchor_ll_low
                range_pips = range_price / pip_size
                
                pos_lod = idx_to_pos[anchor_ll_idx]
                pos_hh1 = idx_to_pos[hh1_idx]
                sizes_leg1 = _scan_bull_fvgs_for_leg(highs, lows, pos_lod, pos_hh1, pip_size)
                
                signal_end_ts = pd.Timestamp(signal_idx) + pd.Timedelta(minutes=SETUP_TF_MINUTES)

                return {
                    "direction": "buy",
                    "symbol": symbol,
                    "date_ny": df_day["date_ny"].iloc[0],
                    "signal_tf": SETUP_TF,
                    "signal_start_time": anchor_ll_idx,
                    "signal_end_time": signal_end_ts,

                    "lod_idx": anchor_ll_idx,
                    "hh1_idx": hh1_idx,
                    "choch_idx": signal_idx,
                    
                    "lod_price": anchor_ll_low,
                    "hh1_price": hh1_high,
                    "choch_close_price": close_price,
                    
                    "range_pips": range_pips,
                    "fvg_max_leg1": max(sizes_leg1) if sizes_leg1 else 0.0,
                    "fvg_max_leg2": 0.0
                }
    
    return None


# ---------------------------------
# MAIN-LOGIK
# ---------------------------------

def main():
    if not os.path.exists(CHART_DATA_DIR):
        os.makedirs(CHART_DATA_DIR)

    symbol = SYMBOL
    if symbol not in PIP_SIZE_MAP:
        raise RuntimeError(f"No PIP_SIZE_MAP entry for symbol {symbol}")
    pip_size = PIP_SIZE_MAP[symbol]

    print(f"Loading input file {INPUT_FILE} ...")
    df = pd.read_csv(INPUT_FILE)

    if "time_ny" not in df.columns:
        raise RuntimeError("Column 'time_ny' not found in input file.")

    df = _ensure_time_columns(df)

    # --- DATE FILTER (from config.py) ---
    print(f"Filtering data to range: {START_DATE_NY} -> {END_DATE_NY}")
    mask = (df.index >= START_DATE_NY) & (df.index < END_DATE_NY)
    df = df.loc[mask]

    if df.empty:
        raise RuntimeError(f"No data left after filtering for {START_DATE_NY} to {END_DATE_NY}")
    # ------------------------------------

    df_sym = df[df["symbol"] == symbol].copy()
    if df_sym.empty:
        raise RuntimeError(f"No data for {symbol} in {INPUT_FILE}")

    df_sym = df_sym.sort_index()

    idx_list, idx_to_pos = _build_index_maps(df_sym)
    highs = df_sym["high"].astype(float).values
    lows = df_sym["low"].astype(float).values

    df_sym["sell_signal_top"] = False
    df_sym["sell_signal_bottom"] = False
    df_sym["buy_signal_bottom"] = False
    df_sym["buy_signal_top"] = False

    setups = []

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
        )
        if sell_setup is not None:
            hod_idx = sell_setup["hod_idx"]
            choch_idx = sell_setup["choch_idx"] # Signal Kerze
            
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
        )
        if buy_setup is not None:
            lod_idx = buy_setup["lod_idx"]
            choch_idx = buy_setup["choch_idx"] # Signal Kerze
            
            if lod_idx in df_sym.index:
                df_sym.loc[lod_idx, "buy_signal_bottom"] = True
            if choch_idx in df_sym.index:
                df_sym.loc[choch_idx, "buy_signal_top"] = True
            setups.append(buy_setup)

    print(f"Total setups found: {len(setups)}")

    print(f"Saving bars with signals to {OUTPUT_BARS_FILE} ...")
    df_sym.to_csv(OUTPUT_BARS_FILE, index=True)
    
    if setups:
        df_setups = pd.DataFrame(setups)
        for col in [c for c in df_setups.columns if c.endswith("_time") or c.endswith("_idx")]:
            # Versuche, Zeitspalten lesbar zu machen, falls es Timestamps sind
            try:
                df_setups[col] = pd.to_datetime(df_setups[col]).dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass
        print(f"Saving setups summary to {OUTPUT_SETUPS_FILE} ...")
        df_setups.to_csv(OUTPUT_SETUPS_FILE, index=False)
    else:
        print("No setups found, no setups CSV written.")


if __name__ == "__main__":
    print("Entering main() ...")
    try:
        main()
    except Exception:
        import traceback
        print("ERROR in phase2_signals_hodlod_micro_two_leg_fvg.py:")
        traceback.print_exc()