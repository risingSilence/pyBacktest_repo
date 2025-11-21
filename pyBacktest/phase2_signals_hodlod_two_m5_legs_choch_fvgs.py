print("phase2_signals_hodlod_two_m5_legs_choch_fvgs.py - starting up...")

import pandas as pd
import os

# ---------------------------------
# CONFIG
# ---------------------------------

SYMBOL = "EURUSD"

# Setup-Name für Dateinamen (damit man im Frontend weiß, was es ist)
SETUP_NAME = "hodlod_two_m5_legs_choch_fvgs"

# Pfade definieren
BASE_DATA_DIR = "data"             # Hier liegt der Phase 1 Output
CHART_DATA_DIR = "charting/data"   # Hierhin schreiben wir für die HTML

# Input: Struktur-Daten aus Phase 1
INPUT_FILENAME = f"data_{SYMBOL}_M5_phase1_structure.csv"
INPUT_FILE = os.path.join(BASE_DATA_DIR, INPUT_FILENAME)

# Output 1: Die Bars mit den Signalen (für Phase 3 und Visualisierung)
# Format: data_{SYMBOL}_{TF}_signals_{SETUP_NAME}.csv
OUTPUT_BARS_FILENAME = f"data_{SYMBOL}_M5_signals_{SETUP_NAME}.csv"
OUTPUT_BARS_FILE = os.path.join(CHART_DATA_DIR, OUTPUT_BARS_FILENAME)

# Output 2: Die Setups/Boxen (für Phase 3 und Visualisierung)
# Format: data_{SYMBOL}_{TF}_setups_{SETUP_NAME}.csv
OUTPUT_SETUPS_FILENAME = f"data_{SYMBOL}_M5_setups_{SETUP_NAME}.csv"
OUTPUT_SETUPS_FILE = os.path.join(CHART_DATA_DIR, OUTPUT_SETUPS_FILENAME)

# Parameter
PIP_SIZE_MAP = {
    "AUDUSD": 0.0001,
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
}
# ... (Rest der Config Parameter bleiben gleich)

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
    SELL-Setup (HOD-Seite):

    - Anker-HH:
        Laufendes Day-High + HH im Zeitfenster 08:30–11:00 NY
        (swing_high_label == "HH" und is_day_high_bar == True).
        Jeder neue gültige HH im Fenster ersetzt den Anker.

    - 1st Leg: HH -> LL1
        LL1 = erstes Swing-LL (swing_low_label == "LL") nach dem Anker-HH.

    - CHOCH:
        Sobald nach LL1 eine Kerze mit
            close <= LL1_low - CHOCH_PIPS[symbol] * pip_size
        schließt (vor 11:30 NY), gilt CHOCH als passiert.

    - 2nd Leg: LL1 -> (Signal-Bar)
        Nach CHOCH wird bei JEDER weiteren Candle bis max. zum
        ersten strukturellen 2. LL geprüft:

        * Range(HH_high -> current_low) >= MIN_RANGE[symbol]
        * Bear-FVGs in Leg1 (HH->LL1) und Leg2 (LL1->current):
              Summe >= MIN_FVG_SUM[symbol]
              pro Leg max(FVG) >= MIN_SINGLE_FVG[symbol]
        * London-Low an current-Bar noch NICHT gebrochen.

        Die erste Candle, bei der alle Bedingungen erfüllt sind,
        wird als ll2_idx/ll2_row genommen (auch ohne LL-Label).

        Wenn bis zum ersten Swing-LL nach CHOCH kein gültiger
        Kandidat gefunden wird, gibt es KEIN Setup.
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

    return {
        "direction": "sell",
        "symbol": symbol,
        "date_ny": df_day["date_ny"].iloc[0],
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
    BUY-Setup (LOD-Seite, gespiegelt):

    - Anker-LL:
        Laufendes Day-Low + LL im Zeitfenster 08:30–11:00 NY
        (swing_low_label == "LL" und is_day_low_bar == True).
        Jeder neue gültige LL im Fenster ersetzt den Anker.

    - 1st Leg: LL -> HH1
        HH1 = erstes Swing-HH (swing_high_label == "HH") nach dem Anker-LL.

    - CHOCH:
        Sobald nach HH1 eine Kerze mit
            close >= HH1_high + CHOCH_PIPS[symbol] * pip_size
        schließt (vor 11:30 NY), gilt CHOCH als passiert.

    - 2nd Leg: HH1 -> (Signal-Bar)
        Nach CHOCH wird bei JEDER weiteren Candle bis max. zum
        ersten strukturellen 2. HH geprüft:

        * Range(LL_low -> current_high) >= MIN_RANGE[symbol]
        * Bull-FVGs in Leg1 (LL->HH1) und Leg2 (HH1->current):
              Summe >= MIN_FVG_SUM[symbol]
              pro Leg max(FVG) >= MIN_SINGLE_FVG[symbol]
        * London-High an current-Bar noch NICHT gebrochen.

        Die erste Candle, bei der alle Bedingungen erfüllt sind,
        wird als hh2_idx/hh2_row genommen (auch ohne HH-Label).

        Wenn bis zum ersten Swing-HH nach CHOCH kein gültiger
        Kandidat gefunden wird, gibt es KEIN Setup.
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

    return {
        "direction": "buy",
        "symbol": symbol,
        "date_ny": df_day["date_ny"].iloc[0],
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

def main():
    # Sicherstellen, dass charting/data existiert
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

    df_sym = df[df["symbol"] == symbol].copy()
    if df_sym.empty:
        raise RuntimeError(f"No data for {symbol} in {INPUT_FILE}")

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
    print(f"Saving bars with signals to {OUTPUT_BARS_FILE} ...")
    df_sym.to_csv(OUTPUT_BARS_FILE, index=True)
    print("Bars file saved.")

    # Setup-Übersicht speichern
    if setups:
        df_setups = pd.DataFrame(setups)
        # Zeitspalten lesbar machen
        for col in [c for c in df_setups.columns if c.endswith("_time")]:
            df_setups[col] = pd.to_datetime(df_setups[col]).dt.strftime("%Y-%m-%d %H:%M:%S")
        print(f"Saving setups summary to {OUTPUT_SETUPS_FILE} ...")
        df_setups.to_csv(OUTPUT_SETUPS_FILE, index=False)
        print("Setups file saved.")
    else:
        print("No setups found, no setups CSV written.")


if __name__ == "__main__":
    print("Entering main() ...")
    try:
        main()
    except Exception:
        import traceback
        print("ERROR in phase2_legs_fvg_signals.py:")
        traceback.print_exc()
