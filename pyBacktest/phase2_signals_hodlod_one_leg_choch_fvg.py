print("phase2_signals_hodlod_one_leg_choch_fvg.py - starting up...")

import pandas as pd
import os
import numpy as np
try:
    from config import START_DATE_NY, END_DATE_NY
except ImportError:
    # Fallback, falls config.py nicht gefunden wird oder man es standalone testet
    from datetime import datetime
    print("WARN: config.py not found, using default dates.")
    START_DATE_NY = datetime(2025, 11, 1) # NUR FALLBACK!!!
    END_DATE_NY   = datetime(2025, 11, 8) # NUR FALLBACK!!!

# ---------------------------------
# CONFIG
# ---------------------------------

# Liste der Symbole
SYMBOLS = ["EURUSD", "GBPUSD", "AUDUSD"]

# Setup-Name für Dateinamen
SETUP_NAME = "hodlod_one_leg_choch_fvg"

# Oben in der Config ergänzen:
PHASE1_SUFFIX = "_NY"  # oder "_LONDON" für das andere File

# TIME FRAME KONFIGURATION
SETUP_TF = "M5"              # Der Timeframe, auf dem wir suchen
SETUP_TF_MINUTES = 5         # Dauer einer Kerze in Minuten (für End-Zeit-Berechnung)

# Pfade definieren
BASE_DATA_DIR = "data"             # Hier liegt der Phase 1 Output
CHART_DATA_DIR = "charting/data"   # Hierhin schreiben wir für die HTML

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
# SELL-Setup: HOD (HH) -> Break of prev HL (Close)
# ---------------------------------

def find_sell_setup_for_day(df_sym: pd.DataFrame,
                            df_day: pd.DataFrame,
                            symbol: str,
                            idx_to_pos,
                            highs,
                            lows,
                            pip_size: float):
    """
    SELL-Setup (HOD-Seite, One Leg - Direct Break).
    Struktur: HOD gefunden -> Suche letztes Swing Low davor (HL).
    Trigger: Close < prev_HL.
    Validierung: Range & FVG im Drop.
    """

    min_range = MIN_RANGE[symbol]
    min_single = MIN_SINGLE_FVG[symbol]

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
            
            # --- RÜCKWÄRTSSUCHE NACH DEM VORIGEN HL ---
            # Wir nutzen df_sym und idx_to_pos, um effizient zurückzuschauen
            pos_hod = idx_to_pos.get(idx)
            if pos_hod is None: continue
            
            # Suche rückwärts ab pos_hod - 1 nach einem Swing Low
            found_hl_price = None
            
            # Limitieren wir den Lookback auf z.B. 500 Bars, um nicht ewig zu suchen
            # (In M5 sind 500 Bars ca 2 Tage, das sollte reichen für Struktur)
            start_search = max(0, pos_hod - 500)
            
            # Slice holen (wir brauchen Swing Labels)
            # Achtung: df_sym ist groß, wir iterieren lieber über Indizes rückwärts
            # Wir greifen direkt auf die Spalte zu, um Speed zu haben
            # Da df_sym index=timestamp ist, nutzen wir iloc via pos
            
            # Wir iterieren manuell rückwärts:
            for k in range(pos_hod - 1, start_search - 1, -1):
                # Check label
                # Wir holen das Label aus dem DataFrame an Position k
                # Das ist performanter als .loc wenn wir den Integer Index k kennen
                # (df_sym.iloc[k] ist Series)
                
                # Optimierung: Wir schauen nur, ob swing_low_label != "" ist.
                # Wir akzeptieren HL, LL, L0 als "Struktur-Tief"
                val = df_sym.iat[k, df_sym.columns.get_loc("swing_low_label")]
                if val and isinstance(val, str) and val in ["HL", "LL", "L0", "L_eq"]:
                    # Gefunden!
                    found_hl_price = df_sym.iat[k, df_sym.columns.get_loc("swing_low_price")]
                    break
            
            if found_hl_price is not None:
                anchor_hh_idx = idx
                anchor_hh_row = row
                anchor_hh_high = float(row["high"])
                break_level = float(found_hl_price)
            else:
                # Kein Struktur-Tief davor gefunden -> HOD ignorieren
                anchor_hh_idx = None
                break_level = None
            
            continue

        if anchor_hh_idx is None or break_level is None:
            continue

        # 2) TRIGGER: Close unter break_level
        # Wir sind zeitlich NACH dem HOD (durch Loop-Struktur garantiert)
        
        if minute >= NY_SIGNAL_CUTOFF:
            # Zu spät -> Setup verwerfen
            anchor_hh_idx = None
            break_level = None
            continue

        close_price = float(row["close"])
        
        if close_price < break_level:
            # --- SIGNAL: CHOCH ---
            
            # London Low Check (Hard Filter)
            if "has_broken_london_low" in df_day.columns:
                val = row.get("has_broken_london_low")
                if pd.notna(val) and bool(val):
                    anchor_hh_idx = None
                    break_level = None
                    continue

            # Validierung: Range & FVG checken
            # Range: HOD bis Low der Signal-Kerze (oder Break-Level?)
            # Wir nehmen HOD bis aktuelles Low, da das der Move ist.
            current_low = float(row["low"])
            range_price = anchor_hh_high - current_low
            range_pips = range_price / pip_size
            
            if range_pips < min_range:
                # Range zu klein -> weitersuchen (vllt kommt später noch ein Break tiefer?)
                # Aber hier ist es ein "Event": Der erste Close drunter zählt.
                # Wenn der zu klein ist, ist das Setup meist invalid.
                anchor_hh_idx = None
                continue

            # FVG Check (HOD bis Current Candle)
            signal_idx = idx
            pos_hod = idx_to_pos[anchor_hh_idx]
            pos_signal = idx_to_pos[signal_idx]
            
            sizes_leg1 = _scan_bear_fvgs_for_leg(highs, lows, pos_hod, pos_signal, pip_size)
            
            if not sizes_leg1 or max(sizes_leg1) < min_single:
                anchor_hh_idx = None
                continue
            
            # Alles valide -> Setup erstellen
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
                
                # Wir mappen den "ll1_idx" auf die Signal-Kerze (Breakdown).
                # Phase 3 scannt dann FVG von HOD bis hierher -> korrekt.
                "ll1_idx": signal_idx, 
                "choch_idx": signal_idx,
                
                "hod_price": anchor_hh_high,
                # ll1_price ist hier das Low der Breakdown-Kerze
                "ll1_price": current_low, 
                "choch_close_price": close_price,
                
                # Meta für Debugging (welches HL wurde gebrochen?)
                # Speichern wir optional, stört Phase 3 nicht
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
                           pip_size: float):
    """
    BUY-Setup (LOD-Seite, One Leg - Direct Break).
    Struktur: LOD gefunden -> Suche letztes Swing High davor (LH).
    Trigger: Close > prev_LH.
    """

    min_range = MIN_RANGE[symbol]
    min_single = MIN_SINGLE_FVG[symbol]

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
            # Rückwärtssuche nach LH
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
                # Mapping hh1_idx auf Signal-Kerze
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

    # Dateinamen dynamisch
    input_filename = f"data_{symbol}_M5_phase1_structure{PHASE1_SUFFIX}.csv"
    input_file = os.path.join(BASE_DATA_DIR, input_filename)

    output_bars_filename = f"data_{symbol}_M5_signals_{SETUP_NAME}{PHASE1_SUFFIX}.csv"
    output_bars_file = os.path.join(CHART_DATA_DIR, output_bars_filename)

    output_setups_filename = f"data_{symbol}_M5_setups_{SETUP_NAME}{PHASE1_SUFFIX}.csv"
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
        print("ERROR in phase2_signals_hodlod_one_leg_choch_fvg.py:")
        traceback.print_exc()