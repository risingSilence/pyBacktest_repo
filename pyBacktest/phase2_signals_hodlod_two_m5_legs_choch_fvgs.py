print("phase2_signals_hodlod_two_m5_legs_choch_fvgs.py - starting up...")

import pandas as pd
import os
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

# Liste der Symbole
SYMBOLS = ["EURUSD", "GBPUSD"]

# Setup-Name für Dateinamen (damit man im Frontend weiß, was es ist)
SETUP_NAME = "hodlod_two_m5_legs_choch_fvgs"

# TIME FRAME KONFIGURATION (NEU)
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

CHOCH_PIPS = {
    "AUDUSD": 1.0,
    "EURUSD": 1.5,
    "GBPUSD": 2.0,
}

MIN_RANGE = {
    "AUDUSD": 8.0,
    "EURUSD": 12.0,
    "GBPUSD": 16.0,
}

MIN_FVG_SUM = {
    "AUDUSD": 2.0,
    "EURUSD": 3.0,
    "GBPUSD": 4.0,
}

MIN_SINGLE_FVG = {
    "AUDUSD": 0.2,
    "EURUSD": 0.3,
    "GBPUSD": 0.4,
}

# NY-Zeitfenster in Minuten seit 00:00
NY_START_HOD_LOD = 8 * 60 + 30      # 08:30
NY_END_HOD_LOD   = 11 * 60          # 11:00 (HOD/LOD-Fenster)
NY_LAST_LL_HH    = 11 * 60 + 30     # 11:30 (2. LL/2. HH muss strictly davor liegen)


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
    Wir scannen i von start_pos+1 bis end_pos-1 (i ist die Mittelkerze).
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
# SELL-Setup: HOD (HH) -> LL1 -> LL2
# ---------------------------------

def find_sell_setup_for_day(df_sym: pd.DataFrame,
                            df_day: pd.DataFrame,
                            symbol: str,
                            idx_to_pos,
                            highs,
                            lows,
                            pip_size: float):
    """
    SELL-Setup (HOD-Seite) mit expliziter Signal-Start/End-Berechnung.
    """

    choch_pips = CHOCH_PIPS[symbol]
    min_range = MIN_RANGE[symbol]
    min_fvg_sum = MIN_FVG_SUM[symbol]
    min_single = MIN_SINGLE_FVG[symbol]

    df_day = df_day.sort_index()

    anchor_hh_idx = None
    anchor_hh_row = None

    ll1_idx = None
    ll1_row = None
    ll1_low = None

    choch_seen = False

    ll2_idx = None
    ll2_row = None

    for idx, row in df_day.iterrows():
        minute = int(row["minute_of_day"])

        # 1) möglicher neuer Anker-HH (HH + DayHigh im Fenster)
        if (
            row.get("swing_high_label") == "HH"
            and bool(row.get("is_day_high_bar", False))
            and NY_START_HOD_LOD <= minute <= NY_END_HOD_LOD
        ):
            anchor_hh_idx = idx
            anchor_hh_row = row

            # alles nach neuem Anker zurücksetzen
            ll1_idx = ll1_row = None
            ll1_low = None
            choch_seen = False
            ll2_idx = ll2_row = None

        if anchor_hh_idx is None:
            continue

        # 2) LL1: erstes Swing-LL nach dem Anker
        if ll1_idx is None and row.get("swing_low_label") == "LL" and idx > anchor_hh_idx:
            ll1_idx = idx
            ll1_row = row
            ll1_low = float(row["low"])
            continue

        # Ab hier nur weiter, wenn LL1 schon existiert
        if ll1_idx is None:
            continue

        # alles nach LL1 muss vor 11:30 passieren
        if minute >= NY_LAST_LL_HH:
            break

        close_price = float(row["close"])

        # 3) CHOCH: erster Close unterhalb Threshold nach LL1
        if not choch_seen and idx > ll1_idx:
            threshold_price = ll1_low - choch_pips * pip_size
            if close_price <= threshold_price:
                choch_seen = True

        # Solange CHOCH noch nicht gesehen wurde, kann es kein fertiges Setup geben
        if not choch_seen:
            continue

        # 4) Kandidat: aktuelle Candle als mögliches "LL2" prüfen

        # Range-Bedingung HH -> aktuelle Candle
        range_price = float(anchor_hh_row["high"]) - float(row["low"])
        range_pips = range_price / pip_size
        if range_pips >= min_range:
            pos_hod = idx_to_pos[anchor_hh_idx]
            pos_ll1 = idx_to_pos[ll1_idx]
            pos_cur = idx_to_pos[idx]

            sizes_leg1 = _scan_bear_fvgs_for_leg(highs, lows, pos_hod, pos_ll1, pip_size)
            sizes_leg2 = _scan_bear_fvgs_for_leg(highs, lows, pos_ll1, pos_cur, pip_size)

            sum_fvg = sum(sizes_leg1) + sum(sizes_leg2)

            if (
                sum_fvg >= min_fvg_sum
                and sizes_leg1
                and max(sizes_leg1) >= min_single
                and sizes_leg2
                and max(sizes_leg2) >= min_single
            ):
                # London-Low-Break-Filter
                if "has_broken_london_low" in df_day.columns:
                    val = row.get("has_broken_london_low")
                    if pd.notna(val) and bool(val):
                        # London Low bereits gebrochen -> dieser Kandidat ungültig
                        pass
                    else:
                        ll2_idx = idx
                        ll2_row = row
                        break
                else:
                    ll2_idx = idx
                    ll2_row = row
                    break

        # 5) Wenn CHOCH gesehen wurde und wir jetzt das erste
        #    Swing-LL nach LL1 sehen, aber BIS HIERHER keinen
        #    gültigen FVG-Kandidaten gefunden haben -> abbrechen.
        if row.get("swing_low_label") == "LL" and idx > ll1_idx:
            # Das ist das strukturelle 2. LL -> nicht weiter als bis hier suchen
            break

    # Wenn eine der Schlüsselstellen fehlt -> kein Setup
    if anchor_hh_idx is None or ll1_idx is None or ll2_idx is None:
        return None

    # Range & FVG für das Setup-Dict nochmal berechnen
    range_price = float(anchor_hh_row["high"]) - float(ll2_row["low"])
    range_pips = range_price / pip_size

    pos_hod = idx_to_pos[anchor_hh_idx]
    pos_ll1 = idx_to_pos[ll1_idx]
    pos_ll2 = idx_to_pos[ll2_idx]

    sizes_leg1 = _scan_bear_fvgs_for_leg(highs, lows, pos_hod, pos_ll1, pip_size)
    sizes_leg2 = _scan_bear_fvgs_for_leg(highs, lows, pos_ll1, pos_ll2, pip_size)
    sum_fvg = sum(sizes_leg1) + sum(sizes_leg2)

    # --- NEU: End-Time berechnen ---
    # ll2_idx ist die Open-Time der Signal-Kerze.
    # Wir addieren die Timeframe-Dauer, um die Close-Time (Signal-Manifestierung) zu erhalten.
    signal_end_ts = pd.Timestamp(ll2_idx) + pd.Timedelta(minutes=SETUP_TF_MINUTES)

    return {
        "direction": "sell",
        "symbol": symbol,
        "date_ny": df_day["date_ny"].iloc[0],
        
        # --- GENERISCHE SPALTEN ---
        "signal_tf": SETUP_TF,
        "signal_start_time": anchor_hh_idx,  # Start (HOD Open Time)
        "signal_end_time": signal_end_ts,    # End (LL2 Close Time)

        # --- ALTE SPALTEN ---
        "hod_idx": anchor_hh_idx,
        "ll1_idx": ll1_idx,
        "ll2_idx": ll2_idx,
        "hod_time": anchor_hh_idx,
        "ll1_time": ll1_idx,
        "ll2_time": ll2_idx,
        "hod_price": float(anchor_hh_row["high"]),
        "ll1_price": float(ll1_row["low"]),
        "ll2_price": float(ll2_row["low"]),
        "range_pips": range_pips,
        "fvg_sum_pips": sum_fvg,
        "fvg_max_leg1": max(sizes_leg1) if sizes_leg1 else 0.0,
        "fvg_max_leg2": max(sizes_leg2) if sizes_leg2 else 0.0,
    }


# ---------------------------------
# BUY-Setup: LOD (LL) -> HH1 -> HH2
# ---------------------------------

def find_buy_setup_for_day(df_sym: pd.DataFrame,
                           df_day: pd.DataFrame,
                           symbol: str,
                           idx_to_pos,
                           highs,
                           lows,
                           pip_size: float):
    """
    BUY-Setup (LOD-Seite, gespiegelt).
    """

    choch_pips = CHOCH_PIPS[symbol]
    min_range = MIN_RANGE[symbol]
    min_fvg_sum = MIN_FVG_SUM[symbol]
    min_single = MIN_SINGLE_FVG[symbol]

    df_day = df_day.sort_index()

    anchor_ll_idx = None
    anchor_ll_row = None

    hh1_idx = None
    hh1_row = None
    hh1_high = None

    choch_seen = False

    hh2_idx = None
    hh2_row = None

    for idx, row in df_day.iterrows():
        minute = int(row["minute_of_day"])

        # 1) möglicher neuer Anker-LL (LL + DayLow im Fenster)
        if (
            row.get("swing_low_label") == "LL"
            and bool(row.get("is_day_low_bar", False))
            and NY_START_HOD_LOD <= minute <= NY_END_HOD_LOD
        ):
            anchor_ll_idx = idx
            anchor_ll_row = row

            # alles nach neuem Anker zurücksetzen
            hh1_idx = hh1_row = None
            hh1_high = None
            choch_seen = False
            hh2_idx = hh2_row = None

        if anchor_ll_idx is None:
            continue

        # 2) HH1: erstes Swing-HH nach dem Anker
        if hh1_idx is None and row.get("swing_high_label") == "HH" and idx > anchor_ll_idx:
            hh1_idx = idx
            hh1_row = row
            hh1_high = float(row["high"])
            continue

        # Ab hier nur weiter, wenn HH1 schon existiert
        if hh1_idx is None:
            continue

        # alles nach HH1 muss vor 11:30 passieren
        if minute >= NY_LAST_LL_HH:
            break

        close_price = float(row["close"])

        # 3) CHOCH: erster Close oberhalb Threshold nach HH1
        if not choch_seen and idx > hh1_idx:
            threshold_price = hh1_high + choch_pips * pip_size
            if close_price >= threshold_price:
                choch_seen = True

        if not choch_seen:
            continue

        # 4) Kandidat: aktuelle Candle als mögliches "HH2" prüfen

        # Range-Bedingung LL -> aktuelle Candle
        range_price = float(row["high"]) - float(anchor_ll_row["low"])
        range_pips = range_price / pip_size
        if range_pips >= min_range:
            pos_lod = idx_to_pos[anchor_ll_idx]
            pos_hh1 = idx_to_pos[hh1_idx]
            pos_cur = idx_to_pos[idx]

            sizes_leg1 = _scan_bull_fvgs_for_leg(highs, lows, pos_lod, pos_hh1, pip_size)
            sizes_leg2 = _scan_bull_fvgs_for_leg(highs, lows, pos_hh1, pos_cur, pip_size)

            sum_fvg = sum(sizes_leg1) + sum(sizes_leg2)

            if (
                sum_fvg >= min_fvg_sum
                and sizes_leg1
                and max(sizes_leg1) >= min_single
                and sizes_leg2
                and max(sizes_leg2) >= min_single
            ):
                # London-High-Break-Filter
                if "has_broken_london_high" in df_day.columns:
                    val = row.get("has_broken_london_high")
                    if pd.notna(val) and bool(val):
                        pass
                    else:
                        hh2_idx = idx
                        hh2_row = row
                        break
                else:
                    hh2_idx = idx
                    hh2_row = row
                    break

        # 5) Wenn CHOCH gesehen wurde und wir jetzt das erste
        #    Swing-HH nach HH1 sehen, aber BIS HIERHER keinen
        #    gültigen FVG-Kandidaten gefunden haben -> abbrechen.
        if row.get("swing_high_label") == "HH" and idx > hh1_idx:
            # Das ist das strukturelle 2. HH -> nicht weiter als bis hier suchen
            break

    if anchor_ll_idx is None or hh1_idx is None or hh2_idx is None:
        return None

    range_price = float(hh2_row["high"]) - float(anchor_ll_row["low"])
    range_pips = range_price / pip_size

    pos_lod = idx_to_pos[anchor_ll_idx]
    pos_hh1 = idx_to_pos[hh1_idx]
    pos_hh2 = idx_to_pos[hh2_idx]

    sizes_leg1 = _scan_bull_fvgs_for_leg(highs, lows, pos_lod, pos_hh1, pip_size)
    sizes_leg2 = _scan_bull_fvgs_for_leg(highs, lows, pos_hh1, pos_hh2, pip_size)
    sum_fvg = sum(sizes_leg1) + sum(sizes_leg2)

    # --- NEU: End-Time berechnen ---
    # hh2_idx ist die Open-Time der Signal-Kerze.
    # Wir addieren die Timeframe-Dauer, um die Close-Time (Signal-Manifestierung) zu erhalten.
    signal_end_ts = pd.Timestamp(hh2_idx) + pd.Timedelta(minutes=SETUP_TF_MINUTES)

    return {
        "direction": "buy",
        "symbol": symbol,
        "date_ny": df_day["date_ny"].iloc[0],
        
        # --- GENERISCHE SPALTEN ---
        "signal_tf": SETUP_TF,
        "signal_start_time": anchor_ll_idx, # Start (LOD Open Time)
        "signal_end_time": signal_end_ts,   # End (HH2 Close Time)

        # --- ALTE SPALTEN ---
        "lod_idx": anchor_ll_idx,
        "hh1_idx": hh1_idx,
        "hh2_idx": hh2_idx,
        "lod_time": anchor_ll_idx,
        "hh1_time": hh1_idx,
        "hh2_time": hh2_idx,
        "lod_price": float(anchor_ll_row["low"]),
        "hh1_price": float(hh1_row["high"]),
        "hh2_price": float(hh2_row["high"]),
        "range_pips": range_pips,
        "fvg_sum_pips": sum_fvg,
        "fvg_max_leg1": max(sizes_leg1) if sizes_leg1 else 0.0,
        "fvg_max_leg2": max(sizes_leg2) if sizes_leg2 else 0.0,
    }

# ---------------------------------
# MAIN-LOGIK
# ---------------------------------

def run_phase2_two_legs_for_symbol(symbol: str):
    print(f"--- Processing Phase 2 (Two Legs) for {symbol} ---")

    # Sicherstellen, dass charting/data existiert
    if not os.path.exists(CHART_DATA_DIR):
        os.makedirs(CHART_DATA_DIR)

    if symbol not in PIP_SIZE_MAP:
        print(f"Skipping {symbol}: No PIP_SIZE_MAP entry.")
        return
    pip_size = PIP_SIZE_MAP[symbol]

    # Dateinamen dynamisch
    input_filename = f"data_{symbol}_M5_phase1_structure.csv"
    input_file = os.path.join(BASE_DATA_DIR, input_filename)

    output_bars_filename = f"data_{symbol}_M5_signals_{SETUP_NAME}.csv"
    output_bars_file = os.path.join(CHART_DATA_DIR, output_bars_filename)

    output_setups_filename = f"data_{symbol}_M5_setups_{SETUP_NAME}.csv"
    output_setups_file = os.path.join(CHART_DATA_DIR, output_setups_filename)

    if not os.path.exists(input_file):
        print(f"Skipping {symbol}: Input file not found ({input_file})")
        return

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

    # Index-Maps + Price-Arrays für FVG-Scan
    idx_list, idx_to_pos = _build_index_maps(df_sym)
    highs = df_sym["high"].astype(float).values
    lows = df_sym["low"].astype(float).values

    # Signalspalten initialisieren
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
            ll2_idx = sell_setup["ll2_idx"]
            if hod_idx in df_sym.index:
                df_sym.loc[hod_idx, "sell_signal_top"] = True
            if ll2_idx in df_sym.index:
                df_sym.loc[ll2_idx, "sell_signal_bottom"] = True
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
            hh2_idx = buy_setup["hh2_idx"]
            if lod_idx in df_sym.index:
                df_sym.loc[lod_idx, "buy_signal_bottom"] = True
            if hh2_idx in df_sym.index:
                df_sym.loc[hh2_idx, "buy_signal_top"] = True
            setups.append(buy_setup)

    print(f"Total setups found: {len(setups)}")

    # Bars-CSV mit Signal-Spalten speichern
    print(f"Saving bars with signals to {output_bars_file} ...")
    df_sym.to_csv(output_bars_file, index=True)
    
    # Setup-Übersicht speichern
    if setups:
        df_setups = pd.DataFrame(setups)
        # Zeitspalten lesbar machen
        for col in [c for c in df_setups.columns if c.endswith("_time")]:
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
        run_phase2_two_legs_for_symbol(sym)


if __name__ == "__main__":
    print("Entering main() ...")
    try:
        main()
    except Exception:
        import traceback
        print("ERROR in phase2_signals_hodlod_two_m5_legs_choch_fvgs.py:")
        traceback.print_exc()