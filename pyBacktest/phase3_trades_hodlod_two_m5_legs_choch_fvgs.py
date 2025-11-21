print("phase3_trades_hodlod_two_m5_legs_choch_fvgs.py - starting up...")

from dataclasses import dataclass
from typing import Optional, Any, Dict, List
import pandas as pd
import numpy as np
import os

# ---------------------------------
# CONFIG
# ---------------------------------

SYMBOL = "EURUSD"

# Muss exakt zum Setup-Namen aus Phase 2 passen!
SETUP_NAME = "hodlod_two_m5_legs_choch_fvgs"

# Verzeichnisse
CHART_DATA_DIR = "charting/data"

# Inputs (Kommen direkt aus Phase 2 Output im charting/data Ordner)
INPUT_BARS_FILENAME = f"data_{SYMBOL}_M5_signals_{SETUP_NAME}.csv"
INPUT_BARS_FILE = os.path.join(CHART_DATA_DIR, INPUT_BARS_FILENAME)

INPUT_SETUPS_FILENAME = f"data_{SYMBOL}_M5_setups_{SETUP_NAME}.csv"
INPUT_SETUPS_FILE = os.path.join(CHART_DATA_DIR, INPUT_SETUPS_FILENAME)

# Outputs (Trades & Stats)
# Wir hängen den Exit-Mode und ggf. ein R-Tag an
# Template für Trades: data_{SYMBOL}_M5_trades_{SETUP_NAME}_{exit_suffix}.csv
TRADES_FILE_TEMPLATE = os.path.join(CHART_DATA_DIR, f"data_{SYMBOL}_M5_trades_{SETUP_NAME}_{{exit_suffix}}.csv")

# Stats: data_{SYMBOL}_M5_stats_{SETUP_NAME}.csv
OUTPUT_STATS_FILE = os.path.join(CHART_DATA_DIR, f"data_{SYMBOL}_M5_stats_{SETUP_NAME}.csv")


PIP_SIZE_MAP: Dict[str, float] = {
    "AUDUSD": 0.0001,
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
}

SL_BUFFER: Dict[str, float] = { 
    "AUDUSD": 0.5, 
    "EURUSD": 0.8, 
    "GBPUSD": 1.0, 
}

MAX_SL_SIZE: Dict[str, float] = { 
    "AUDUSD": 18.0, 
    "EURUSD": 24.0, 
    "GBPUSD": 28.0, 
}

NY_ENTRY_CUTOFF_MINUTE = 12 * 60
NY_SESSION_CLOSE_MINUTE = 16 * 60
NY_2PM_MINUTE = 14 * 60


SCENARIO_ID = "limit_fvg2_london_2R"


# ---------------------------------
# DATA CLASSES
# ---------------------------------

@dataclass
class EntrySpec:
    symbol: str
    direction: str  # "buy" / "sell"
    date_ny: Any
    setup_index: int
    entry_price: float
    sl_price: float
    tp_price: float
    activation_idx: Any   # Index der ersten Kerze, in der Limit aktiv ist
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


# ---------------------------------
# HELPER: TIME COLUMNS
# ---------------------------------

def _ensure_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Stellt sicher, dass time_ny Index ist und hour/minute/minute_of_day/date_ny existieren.
    """
    if df.index.name is None or df.index.name != "time_ny":
        # Wenn eine time_ny-Spalte existiert, diese als Index setzen
        if "time_ny" in df.columns:
            df["time_ny"] = pd.to_datetime(df["time_ny"])
            df = df.set_index("time_ny")
            df.index.name = "time_ny"
        else:
            # Erster Index wird als Zeit interpretiert
            df.index = pd.to_datetime(df.index)
            df.index.name = "time_ny"
    else:
        df.index = pd.to_datetime(df.index)

    if "hour_ny" not in df.columns:
        df["hour_ny"] = df.index.hour
    if "minute_ny" not in df.columns:
        df["minute_ny"] = df.index.minute
    if "minute_of_day" not in df.columns:
        df["minute_of_day"] = df["hour_ny"] * 60 + df["minute_ny"]
    if "date_ny" not in df.columns:
        # Annahme: FX-Tag bereits in phase0 korrekt berechnet; 
        # falls nicht vorhanden, fallback auf Kalendertag:
        df["date_ny"] = df.index.date

    return df


# ---------------------------------
# HELPER: FVG-SCANS MIT BOUNDARIES
# ---------------------------------

def _scan_bear_fvgs_with_bounds(highs: np.ndarray,
                                lows: np.ndarray,
                                start_pos: int,
                                end_pos: int,
                                pip_size: float) -> List[Dict[str, Any]]:
    """
    Bear-FVGs (downtrend): high[i+1] < low[i-1].
    Wir liefern Dicts mit:
        mid_pos, upper, lower, size_pips
    upper = lows[left], lower = highs[right]
    """
    if end_pos - start_pos < 2:
        return []

    out: List[Dict[str, Any]] = []
    for i in range(start_pos + 1, end_pos):
        left = i - 1
        right = i + 1
        if left < 0 or right >= len(highs):
            continue
        if highs[right] < lows[left]:
            upper = lows[left]
            lower = highs[right]
            size_price = upper - lower
            if size_price > 0:
                out.append({
                    "mid_pos": i,
                    "upper": float(upper),
                    "lower": float(lower),
                    "size_pips": float(size_price / pip_size),
                })
    return out


def _scan_bull_fvgs_with_bounds(highs: np.ndarray,
                                lows: np.ndarray,
                                start_pos: int,
                                end_pos: int,
                                pip_size: float) -> List[Dict[str, Any]]:
    """
    Bull-FVGs (uptrend): low[i+1] > high[i-1].
    Wir liefern Dicts mit:
        mid_pos, upper, lower, size_pips
    upper = lows[right], lower = highs[left]
    """
    if end_pos - start_pos < 2:
        return []

    out: List[Dict[str, Any]] = []
    for i in range(start_pos + 1, end_pos):
        left = i - 1
        right = i + 1
        if left < 0 or right >= len(highs):
            continue
        if lows[right] > highs[left]:
            lower = highs[left]
            upper = lows[right]
            size_price = upper - lower
            if size_price > 0:
                out.append({
                    "mid_pos": i,
                    "upper": float(upper),
                    "lower": float(lower),
                    "size_pips": float(size_price / pip_size),
                })
    return out


# ---------------------------------
# ENTRY-SZENARIO 1
# ---------------------------------

def build_entry_for_setup_scenario1(setup_row: pd.Series,
                                    df_day: pd.DataFrame,
                                    setup_idx: int) -> Optional[EntrySpec]:
    """
    Short:
      - SL = HOD + Buffer
      - Limit an Bear-FVG im 2. Leg (LL1->LL2) mit der
        niedrigsten Untergrenze; Entry = Untergrenze.
      - MaxSL enforced, danach 2R vs London-Low-Logik.

    Long:
      - SL = LOD - Buffer
      - Limit an Bull-FVG im 2. Leg (LOD->HH2) mit der
        höchsten Obergrenze; Entry = Obergrenze.
      - MaxSL + 2R vs London-High.
    """
    direction = setup_row["direction"]
    symbol = setup_row["symbol"]
    date_ny = setup_row["date_ny"]

    pip_size = PIP_SIZE_MAP.get(symbol)
    if pip_size is None:
        print(f"[WARN] Unknown symbol {symbol}, skipping setup {setup_idx}")
        return None

    sl_buffer_pips = SL_BUFFER[symbol]
    max_sl_pips = MAX_SL_SIZE[symbol]

    # London-Level holen
    if direction == "sell":
        if "london_low" not in df_day.columns or df_day["london_low"].isna().all():
            print(f"[INFO] No london_low for date {date_ny}, skipping SELL setup {setup_idx}")
            return None
        london_level = float(df_day["london_low"].iloc[0])
        hod_price = float(setup_row["hod_price"])
        sl_price = hod_price + sl_buffer_pips * pip_size

        # FVG im 2. Leg LL1 -> LL2
        ll1_ts = pd.to_datetime(setup_row["ll1_idx"])
        ll2_ts = pd.to_datetime(setup_row["ll2_idx"])
        try:
            pos_ll1 = df_day.index.get_loc(ll1_ts)
            pos_ll2 = df_day.index.get_loc(ll2_ts)
        except KeyError:
            print(f"[WARN] LL1/LL2 index not found in df_day for setup {setup_idx}, skipping.")
            return None

        highs = df_day["high"].values
        lows = df_day["low"].values
        fvgs = _scan_bear_fvgs_with_bounds(highs, lows, pos_ll1, pos_ll2, pip_size)
        if not fvgs:
            print(f"[INFO] No bear FVGs in leg2 for setup {setup_idx}, skipping.")
            return None

        # FVG mit niedrigster Untergrenze (lower) wählen, Entry = lower
        best = min(fvgs, key=lambda d: d["lower"])
        entry_price = best["lower"]

        # Max-SL prüfen: SL bleibt am HOD+Buffer, Entry wird ggf. näher gezogen
        sl_size_price = sl_price - entry_price
        sl_size_pips = sl_size_price / pip_size
        if sl_size_pips > max_sl_pips:
            sl_size_pips = max_sl_pips
            sl_size_price = sl_size_pips * pip_size
            entry_price = sl_price - sl_size_price

        # 2R-Logik vs London-Low
        tp_2r = entry_price - 2.0 * sl_size_pips * pip_size

        if tp_2r >= london_level:
            # 2R liegt "vor" London-Low (nicht weiter weg) -> TP = 2R
            tp_price = tp_2r
        else:
            # 2R wäre unter London-Low -> Entry so anpassen, dass London-Low = 2R
            # Range (SL -> London-Low) inkl. Buffer / 3 = finale SL-Distanz
            sl_to_london_price = sl_price - london_level
            if sl_to_london_price <= 0:
                print(f"[WARN] SL <= London-Low for setup {setup_idx}, skipping.")
                return None
            sl_size_price = sl_to_london_price / 3.0
            sl_size_pips = sl_size_price / pip_size
            if sl_size_pips > max_sl_pips:
                print(f"[INFO] Required SL size ({sl_size_pips:.2f}) > max ({max_sl_pips}) for setup {setup_idx}, skipping.")
                return None
            entry_price = sl_price - sl_size_price
            tp_price = london_level  # sollte jetzt exakt 2R sein

        # Aktivierung ab der Kerze nach LL2
        activation_ts = ll2_ts
        try:
            activation_pos = df_day.index.get_loc(activation_ts) + 1
        except KeyError:
            print(f"[WARN] LL2 index not found in df_day for setup {setup_idx}, skipping.")
            return None
        if activation_pos >= len(df_day):
            print(f"[INFO] No bars after LL2 for setup {setup_idx}, skipping.")
            return None
        activation_idx = df_day.index[activation_pos]

    elif direction == "buy":
        if "london_high" not in df_day.columns or df_day["london_high"].isna().all():
            print(f"[INFO] No london_high for date {date_ny}, skipping BUY setup {setup_idx}")
            return None
        london_level = float(df_day["london_high"].iloc[0])
        lod_price = float(setup_row["lod_price"])
        sl_price = lod_price - sl_buffer_pips * pip_size

        # FVG im 2. Leg LOD -> HH2
        lod_ts = pd.to_datetime(setup_row["lod_idx"])
        hh2_ts = pd.to_datetime(setup_row["hh2_idx"])
        try:
            pos_lod = df_day.index.get_loc(lod_ts)
            pos_hh2 = df_day.index.get_loc(hh2_ts)
        except KeyError:
            print(f"[WARN] LOD/HH2 index not found in df_day for setup {setup_idx}, skipping.")
            return None

        highs = df_day["high"].values
        lows = df_day["low"].values
        fvgs = _scan_bull_fvgs_with_bounds(highs, lows, pos_lod, pos_hh2, pip_size)
        if not fvgs:
            print(f"[INFO] No bull FVGs in leg2 for setup {setup_idx}, skipping.")
            return None

        # FVG mit höchster Obergrenze (upper) wählen, Entry = upper
        best = max(fvgs, key=lambda d: d["upper"])
        entry_price = best["upper"]

        # Max-SL prüfen
        sl_size_price = entry_price - sl_price
        sl_size_pips = sl_size_price / pip_size
        if sl_size_pips > max_sl_pips:
            sl_size_pips = max_sl_pips
            sl_size_price = sl_size_pips * pip_size
            entry_price = sl_price + sl_size_price

        # 2R vs London-High
        tp_2r = entry_price + 2.0 * sl_size_pips * pip_size

        if tp_2r <= london_level:
            tp_price = tp_2r
        else:
            # Entry so anpassen, dass London-High = 2R
            sl_to_london_price = london_level - sl_price
            if sl_to_london_price <= 0:
                print(f"[WARN] SL >= London-High for setup {setup_idx}, skipping.")
                return None
            sl_size_price = sl_to_london_price / 3.0
            sl_size_pips = sl_size_price / pip_size
            if sl_size_pips > max_sl_pips:
                print(f"[INFO] Required SL size ({sl_size_pips:.2f}) > max ({max_sl_pips}) for setup {setup_idx}, skipping.")
                return None
            entry_price = sl_price + sl_size_price
            tp_price = london_level

        # Aktivierung ab der Kerze nach HH2
        activation_ts = hh2_ts
        try:
            activation_pos = df_day.index.get_loc(activation_ts) + 1
        except KeyError:
            print(f"[WARN] HH2 index not found in df_day for setup {setup_idx}, skipping.")
            return None
        if activation_pos >= len(df_day):
            print(f"[INFO] No bars after HH2 for setup {setup_idx}, skipping.")
            return None
        activation_idx = df_day.index[activation_pos]

    else:
        print(f"[WARN] Unknown direction {direction} for setup {setup_idx}")
        return None

    return EntrySpec(
        symbol=symbol,
        direction=direction,
        date_ny=date_ny,
        setup_index=setup_idx,
        entry_price=float(entry_price),
        sl_price=float(sl_price),
        tp_price=float(tp_price),
        activation_idx=activation_idx,
    )

def _simulate_exit_phase(entry: EntrySpec,
                         df_day: pd.DataFrame,
                         entry_idx: Any,
                         session_close_minute: Optional[int],
                         bos_target_number: Optional[int]) -> ExitResult:
    """
    Exit-Phase nach Fill, generisch für verschiedene Exit-Strategien.

    - session_close_minute:
        * 16*60 für exit_4pm und die post-2pm-BOS-Varianten
        * 14*60 für exit_2pm
        * None für exit_unmanaged (kein zeitbasierter Close)
    - bos_target_number:
        * None oder 0 -> kein BOS-basiertes Trailing
        * 1  -> ab 14:00 SL auf erstes BOS-Low/-High gegen die Position
        * 2  -> ab 14:00 SL auf zweites BOS-Low/-High gegen die Position

    Near-TP-Trailing (für alle Exit-Modi):
      - Sobald eine Kerze > 1.75R im Profit ist:
          * Long: SL auf Low dieser Kerze
          * Short: SL auf High dieser Kerze
      - Danach wird mit jeder Kerze der SL nachgezogen (höheres Low / tieferes High).
      - WICHTIG: Es gilt deine Regel:
          * Erst prüfen, ob SL/TP hit, DANN SL anpassen.
          * D.h. die erste >1.75R-Kerze armt nur das Trailing,
            aber stoppt nicht in derselben Kerze aus.

    Exit-Reasons:
      - "SL"                        : normaler SL (ohne Trailing)
      - "TRAILING_STOP"             : BOS-Trailing
      - "TRAILING_STOP_NEAR_TP"     : 1.75R-Near-TP-Trailing
      - "TP"                        : Take Profit
      - "SESSION_CLOSE"             : Exit um 14/16 NY
      - "MANUAL_CLOSE"              : letztes Bar bei unmanaged

    1R wird immer aus dem initialen SL-Abstand berechnet.
    """
    direction = entry.direction
    symbol = entry.symbol
    pip_size = PIP_SIZE_MAP[symbol]

    # Sicherstellen, dass Zeitspalten existieren
    if "minute_of_day" not in df_day.columns:
        df_day = _ensure_time_columns(df_day)

    try:
        entry_pos = df_day.index.get_loc(entry_idx)
    except KeyError:
        return ExitResult(
            filled=False,
            miss_reason="entry_idx_not_in_day",
            entry_idx=None,
            exit_idx=None,
            exit_price=None,
            exit_reason=None,
            result_R=None,
            sl_size_pips=None,
            holding_minutes=None,
        )

    # --- initiales Risiko für 1R ---
    initial_sl = entry.sl_price
    if direction == "sell":
        risk_sl_size_price = initial_sl - entry.entry_price
    else:
        risk_sl_size_price = entry.entry_price - initial_sl

    risk_sl_size_pips = abs(risk_sl_size_price / pip_size) if pip_size else None

    # Struktur-SL (BOS), Near-TP-SL kommt als Overlay dazu
    effective_sl = initial_sl
    tp_price = entry.tp_price

    exit_idx = None
    exit_price = None
    exit_reason = None

    last_idx_before_close = None

    # BOS-Trailing-Status
    ref_price = None
    bos_count = 0
    use_bos_trailing = bos_target_number is not None and bos_target_number > 0
    bos_trailing_active = False

    has_swing_low_label = "swing_low_label" in df_day.columns
    has_swing_high_label = "swing_high_label" in df_day.columns

    # Near-TP-Trailing (ab 1.75R), greift ab der NÄCHSTEN Kerze
    near_tp_trailing_active = False
    near_tp_sl: Optional[float] = None

    # 1.75R-Schwelle in Preis
    threshold_long = None
    threshold_short = None
    if risk_sl_size_pips and risk_sl_size_pips > 0:
        threshold_pips = 1.75 * risk_sl_size_pips
        threshold_long = entry.entry_price + threshold_pips * pip_size
        threshold_short = entry.entry_price - threshold_pips * pip_size

    for pos in range(entry_pos, len(df_day)):
        row = df_day.iloc[pos]
        minute_of_day = row["minute_of_day"]
        idx = df_day.index[pos]

        # Zeitlimit (für unmanaged ist session_close_minute=None -> kein Zeitbreak)
        if session_close_minute is not None and minute_of_day > session_close_minute:
            break

        last_idx_before_close = idx

        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        # -------------------------------------------------
        # 1) BOS-Trailing ab 14:00 (wie bisher)
        #    -> passt effective_sl an, bevor wir SL/TP prüfen
        # -------------------------------------------------
        if use_bos_trailing and minute_of_day >= NY_2PM_MINUTE:
            if ref_price is None:
                # Referenz = Close der ersten Kerze ab 14:00
                ref_price = close

            bos_trigger = False

            if direction == "buy":
                # BOS gegen Long: erstes/zweites Low unter dem 14:00-Preis
                if low < ref_price:
                    if has_swing_low_label:
                        lab = row["swing_low_label"]
                        if isinstance(lab, str) and lab != "":
                            bos_trigger = True
                    else:
                        bos_trigger = True
            else:
                # BOS gegen Short: erstes/zweites High über dem 14:00-Preis
                if high > ref_price:
                    if has_swing_high_label:
                        lab = row["swing_high_label"]
                        if isinstance(lab, str) and lab != "":
                            bos_trigger = True
                    else:
                        bos_trigger = True

            if bos_trigger:
                bos_count += 1
                if bos_count == bos_target_number:
                    if direction == "buy":
                        effective_sl = low
                    else:
                        effective_sl = high
                    bos_trailing_active = True

        # -------------------------------------------------
        # 2) Effektiven SL für diese Kerze berechnen
        #    (BOS-SL + ggf. Near-TP-SL aus VORHERIGEN Kerzen)
        # -------------------------------------------------
        sl_for_hit = effective_sl
        if near_tp_trailing_active and near_tp_sl is not None:
            if direction == "buy":
                sl_for_hit = max(sl_for_hit, near_tp_sl)
            else:
                sl_for_hit = min(sl_for_hit, near_tp_sl)

        # -------------------------------------------------
        # 3) SL / TP Check mit sl_for_hit
        # -------------------------------------------------
        if direction == "sell":
            hit_sl = high >= sl_for_hit
            hit_tp = low <= tp_price
        else:
            hit_sl = low <= sl_for_hit
            hit_tp = high >= tp_price

        if hit_sl or hit_tp:
            # konservativ: SL gewinnt, wenn beides möglich
            if hit_sl:
                exit_idx = idx
                exit_price = sl_for_hit
                if near_tp_trailing_active and near_tp_sl is not None:
                    exit_reason = "TRAILING_STOP_NEAR_TP"
                elif bos_trailing_active and effective_sl != initial_sl:
                    exit_reason = "TRAILING_STOP"
                else:
                    exit_reason = "SL"
            elif hit_tp:
                exit_idx = idx
                exit_price = tp_price
                exit_reason = "TP"
            break

        # -------------------------------------------------
        # 4) Nur wenn KEIN Exit:
        #    Near-TP-Trailing ARMEN / NACHZIEHEN
        #    -> wirkt erst ab nächster Kerze (deine gewünschte Reihenfolge)
        # -------------------------------------------------
        # Zuerst: Falls schon aktiv, mit dieser Kerze SL nachziehen
        if near_tp_trailing_active and near_tp_sl is not None:
            if direction == "buy":
                near_tp_sl = max(near_tp_sl, low)
            else:
                near_tp_sl = min(near_tp_sl, high)

        # Dann: falls noch nicht aktiv, prüfen ob diese Kerze erstmals >1.75R kommt
        if (not near_tp_trailing_active) and risk_sl_size_pips and risk_sl_size_pips > 0:
            if direction == "buy" and threshold_long is not None:
                if high >= threshold_long:
                    near_tp_trailing_active = True
                    near_tp_sl = low  # wird ab nächster Kerze benutzt
            elif direction == "sell" and threshold_short is not None:
                if low <= threshold_short:
                    near_tp_trailing_active = True
                    near_tp_sl = high  # wird ab nächster Kerze benutzt

    # -------------------------------------------------
    # 5) Falls weder SL/TP getroffen wurden
    # -------------------------------------------------
    if exit_idx is None:
        if session_close_minute is None:
            # unmanaged: Ende des übergebenen Datensatzes -> MANUAL_CLOSE
            last_idx = df_day.index[-1]
            row = df_day.loc[last_idx]
            exit_idx = last_idx
            exit_price = float(row["close"])
            exit_reason = "MANUAL_CLOSE"
        else:
            # zeitbasierter Close (2pm/4pm)
            if last_idx_before_close is None:
                last_idx_before_close = df_day.index[-1]
            row = df_day.loc[last_idx_before_close]
            exit_idx = last_idx_before_close
            exit_price = float(row["close"])
            exit_reason = "SESSION_CLOSE"

    # -------------------------------------------------
    # 6) Ergebnis in R
    # -------------------------------------------------
    if direction == "sell":
        result_pips = (entry.entry_price - exit_price) / pip_size
    else:
        result_pips = (exit_price - entry.entry_price) / pip_size

    if risk_sl_size_pips and risk_sl_size_pips != 0:
        result_R = result_pips / risk_sl_size_pips
    else:
        result_R = None

    # Holding-Zeit
    holding_minutes = None
    if entry_idx is not None and exit_idx is not None:
        delta = exit_idx - entry_idx
        holding_minutes = delta.total_seconds() / 60.0

    return ExitResult(
        filled=True,
        miss_reason=None,
        entry_idx=entry_idx,
        exit_idx=exit_idx,
        exit_price=float(exit_price) if exit_price is not None else None,
        exit_reason=exit_reason,
        result_R=float(result_R) if result_R is not None else None,
        sl_size_pips=float(risk_sl_size_pips) if risk_sl_size_pips is not None else None,
        holding_minutes=holding_minutes,
    )




def simulate_trade_for_exit_mode(entry: EntrySpec,
                                 df_day: pd.DataFrame,
                                 exit_mode: str) -> ExitResult:
    """
    Simuliert einen Trade mit identischer Entry-Logik, aber verschiedenen Exit-Modi:

    exit_4pm:
        - SL/TP, sonst Close um 16:00 NY
    exit_2pm:
        - SL/TP, sonst Close um 14:00 NY
    exit_post_2pm_1st_bos:
        - wie unmanaged (kein harter Session-Close), aber ab 14:00 NY
          BOS-basiertes Trailing auf das erste BOS-Low/-High gegen die Position
    exit_post_2pm_2nd_bos:
        - wie unmanaged, aber ab 14:00 NY BOS-basiertes Trailing auf das zweite
          BOS-Low/-High gegen die Position
    exit_unmanaged:
        - kein zeitbasierter Exit; Trade läuft bis TP/SL oder letzter Bar
          (MANUAL_CLOSE am letzten Close)

    Rückgabe:
        ExitResult mit allen Infos (filled, entry_idx, exit_idx, exit_price, result_R, etc.)
    """
    direction = entry.direction

    # sicherstellen, dass Zeitspalten vorhanden sind
    if "minute_of_day" not in df_day.columns:
        df_day = _ensure_time_columns(df_day)

    # 1) Limit-Fill suchen (identisch für alle Exit-Modi)
    try:
        start_pos = df_day.index.get_loc(entry.activation_idx)
    except KeyError:
        return ExitResult(
            filled=False,
            miss_reason="activation_idx_not_in_day",
            entry_idx=None,
            exit_idx=None,
            exit_price=None,
            exit_reason=None,
            result_R=None,
            sl_size_pips=None,
            holding_minutes=None,
        )

    filled = False
    entry_idx = None

    for pos in range(start_pos, len(df_day)):
        row = df_day.iloc[pos]
        if row["minute_of_day"] > NY_ENTRY_CUTOFF_MINUTE:
            break

        high = float(row["high"])
        low = float(row["low"])

        if direction == "sell":
            if high >= entry.entry_price:
                filled = True
                entry_idx = df_day.index[pos]
                break
        else:
            if low <= entry.entry_price:
                filled = True
                entry_idx = df_day.index[pos]
                break

    if not filled:
        return ExitResult(
            filled=False,
            miss_reason="no_fill_until_noon",
            entry_idx=None,
            exit_idx=None,
            exit_price=None,
            exit_reason=None,
            result_R=None,
            sl_size_pips=None,
            holding_minutes=None,
        )

    # 2) Exit-Variante bestimmen
    if exit_mode == "exit_4pm":
        session_close_minute = NY_SESSION_CLOSE_MINUTE     # 16:00
        bos_target = None

    elif exit_mode == "exit_2pm":
        session_close_minute = NY_2PM_MINUTE               # 14:00
        bos_target = None

    elif exit_mode == "exit_post_2pm_1st_bos":
        # darf wie unmanaged über mehrere Tage laufen -> kein Session-Close
        session_close_minute = None
        bos_target = 1

    elif exit_mode == "exit_post_2pm_2nd_bos":
        # darf wie unmanaged über mehrere Tage laufen -> kein Session-Close
        session_close_minute = None
        bos_target = 2

    elif exit_mode == "exit_unmanaged":
        session_close_minute = None                        # kein Zeitlimit
        bos_target = None

    else:
        # Fallback: wie exit_4pm
        session_close_minute = NY_SESSION_CLOSE_MINUTE
        bos_target = None

    return _simulate_exit_phase(
        entry=entry,
        df_day=df_day,
        entry_idx=entry_idx,
        session_close_minute=session_close_minute,
        bos_target_number=bos_target,
    )





# ---------------------------------
# STATS
# ---------------------------------

def _format_minutes_to_hhmm(minutes: Optional[float]) -> str:
    if minutes is None or np.isnan(minutes):
        return ""
    total = int(round(minutes))
    h = total // 60
    m = total % 60
    return f"{h:02d}:{m:02d}"

def _get_price_decimals_for_symbol(symbol: str) -> int:
    """
    Bestimmt die Anzahl der Nachkommastellen für Preise.
    Heuristik:
      - n = Anzahl Nachkommastellen der Pip-Size
      - Preis bekommt n+1 Nachkommastellen
    Beispiel: pip_size = 0.0001 -> 4 Nachkommastellen -> Preis = 5 Nachkommastellen
    """
    pip_size = PIP_SIZE_MAP.get(symbol)
    if pip_size is None:
        # Fallback: 5 Nachkommastellen für FX
        return 5

    s = f"{pip_size:.10f}".rstrip("0")
    if "." in s:
        decimals_pip = len(s.split(".")[1])
    else:
        decimals_pip = 0

    # Annahme: Preis hat eine Stelle mehr als die Pip-Size
    return decimals_pip + 1


def _round_trades_for_output(df_trades: pd.DataFrame) -> pd.DataFrame:
    """
    - Preise (entry/sl/tp/exit) auf symbol-spezifische Dezimalstellen runden
    - sonstige numerische Größen (R, SL in Pips, Holding-Zeit in Minuten) auf 2 Nachkommastellen runden
    """
    if df_trades.empty:
        return df_trades

    price_cols = ["entry_price", "sl_price", "tp_price", "exit_price"]

    # Preise pro Zeile/Symbol runden
    for idx, row in df_trades.iterrows():
        symbol = row.get("symbol")
        if pd.isna(symbol):
            continue
        decimals = _get_price_decimals_for_symbol(symbol)

        for col in price_cols:
            if col in df_trades.columns:
                val = row.get(col)
                if pd.notna(val):
                    df_trades.at[idx, col] = round(float(val), decimals)

    # Andere numerische Spalten auf 2 Nachkommastellen runden
    numeric_cols_2dec = ["result_R", "sl_size_pips", "holding_minutes"]
    for col in numeric_cols_2dec:
        if col in df_trades.columns:
            df_trades[col] = pd.to_numeric(df_trades[col], errors="coerce").round(2)

    return df_trades


def _round_stats_for_output(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Alle float-Werte im Stats-Dict auf 2 Nachkommastellen runden.
    Strings (z.B. hh:mm) und ints bleiben unverändert.
    """
    rounded: Dict[str, Any] = {}
    for k, v in stats.items():
        if isinstance(v, (float, np.floating)):
            if np.isnan(v):
                rounded[k] = v
            else:
                rounded[k] = float(round(v, 2))
        else:
            rounded[k] = v
    return rounded



def compute_stats(df_trades: pd.DataFrame) -> Dict[str, Any]:
    """
    df_trades enthält pro Setup eine Zeile, unabhängig davon ob filled oder miss.
    Gefillte Trades haben filled=True und result_R != None.
    """
    stats: Dict[str, Any] = {}

    n_setups = len(df_trades)
    n_filled = int(df_trades["filled"].sum()) if "filled" in df_trades.columns else 0
    stats["n_setups"] = n_setups
    stats["n_filled"] = n_filled
    stats["tag_rate"] = n_filled / n_setups if n_setups > 0 else np.nan

    df_filled = df_trades[df_trades["filled"]] if "filled" in df_trades.columns else pd.DataFrame()

    n_trades = len(df_filled)
    stats["n_trades"] = n_trades

    if n_trades == 0:
        return stats

    # Basic R-Metriken
    res_R = df_filled["result_R"].astype(float)
    stats["win_rate"] = float((res_R > 0).mean()) if len(res_R) > 0 else np.nan
    stats["avg_R"] = float(res_R.mean()) if len(res_R) > 0 else np.nan

    winners = df_filled[res_R > 0]
    losers = df_filled[res_R < 0]

    stats["avg_winner_R"] = float(winners["result_R"].mean()) if not winners.empty else np.nan
    stats["avg_loser_R"] = float(losers["result_R"].mean()) if not losers.empty else np.nan

    stats["cumulative_R"] = float(res_R.sum())

    # SL size
    if "sl_size_pips" in df_filled.columns:
        stats["avg_sl_size_pips"] = float(df_filled["sl_size_pips"].astype(float).mean())
    else:
        stats["avg_sl_size_pips"] = np.nan

    # Holding times
    hold_all = df_filled["holding_minutes"].astype(float)
    stats["avg_holding_minutes"] = float(hold_all.mean()) if len(hold_all) > 0 else np.nan

    hold_w = winners["holding_minutes"].astype(float) if not winners.empty else pd.Series(dtype=float)
    hold_l = losers["holding_minutes"].astype(float) if not losers.empty else pd.Series(dtype=float)

    stats["avg_holding_minutes_winners"] = float(hold_w.mean()) if len(hold_w) > 0 else np.nan
    stats["avg_holding_minutes_losers"] = float(hold_l.mean()) if len(hold_l) > 0 else np.nan

    # SL- und TP-Zeiten
    # SL schließt hier auch Trailing-Stops ein (inkl. Near-TP-Trailing)
    sl_trades = df_filled[df_filled["exit_reason"].isin(
        ["SL", "TRAILING_STOP", "TRAILING_STOP_NEAR_TP"]
    )]
    tp_trades = df_filled[df_filled["exit_reason"] == "TP"]

    stats["avg_sl_minutes"] = float(sl_trades["holding_minutes"].astype(float).mean()) if not sl_trades.empty else np.nan
    stats["avg_tp_minutes"] = float(tp_trades["holding_minutes"].astype(float).mean()) if not tp_trades.empty else np.nan

    # Streaks
    # Wir sortieren nach entry_idx
    df_sorted = df_filled.sort_values("entry_idx")
    res_sorted = df_sorted["result_R"].astype(float)

    max_win_streak = 0
    max_loss_streak = 0
    cur_win = 0
    cur_loss = 0

    for r in res_sorted:
        if r > 0:
            cur_win += 1
            cur_loss = 0
        elif r < 0:
            cur_loss += 1
            cur_win = 0
        else:
            # R == 0 -> streaks resetten
            cur_win = 0
            cur_loss = 0
        max_win_streak = max(max_win_streak, cur_win)
        max_loss_streak = max(max_loss_streak, cur_loss)

    stats["max_win_streak"] = int(max_win_streak)
    stats["max_loss_streak"] = int(max_loss_streak)

    # Equity-Kurve und Drawdown (Start bei 0 für korrekten Max-DD)
    equity = res_sorted.cumsum()
    equity_with_zero = pd.concat([pd.Series([0.0]), equity], ignore_index=True)
    running_max = equity_with_zero.cummax()
    drawdowns = running_max - equity_with_zero

    stats["max_drawdown_R"] = float(drawdowns.max())
    stats["avg_drawdown_R"] = float(drawdowns.mean())

    # Formattierte Zeiten (hh:mm) zusätzlich speichern
    stats["avg_holding_hhmm"] = _format_minutes_to_hhmm(stats["avg_holding_minutes"])
    stats["avg_holding_hhmm_winners"] = _format_minutes_to_hhmm(stats["avg_holding_minutes_winners"])
    stats["avg_holding_hhmm_losers"] = _format_minutes_to_hhmm(stats["avg_holding_minutes_losers"])
    stats["avg_sl_time_hhmm"] = _format_minutes_to_hhmm(stats["avg_sl_minutes"])
    stats["avg_tp_time_hhmm"] = _format_minutes_to_hhmm(stats["avg_tp_minutes"])

    return stats





# ---------------------------------
# MAIN
# ---------------------------------

def main():
    print(f"Running phase3 backtest for {SYMBOL} / scenario {SCENARIO_ID} ...")

    # Bars laden (ALLE Tage)
    print(f"Loading bars from {INPUT_BARS_FILE} ...")
    df_bars = pd.read_csv(INPUT_BARS_FILE)
    df_bars = _ensure_time_columns(df_bars)

    # Setups laden
    print(f"Loading setups from {INPUT_SETUPS_FILE} ...")
    df_setups = pd.read_csv(INPUT_SETUPS_FILE)

    exit_variants = [
        "exit_4pm",
        "exit_2pm",
        "exit_post_2pm_1st_bos",
        "exit_post_2pm_2nd_bos",
        "exit_unmanaged",
    ]

    stats_per_exit: Dict[str, Dict[str, Any]] = {}

    for exit_mode in exit_variants:
        print(f"\n=== Running exit mode: {exit_mode} ===")

        trades_rows: List[Dict[str, Any]] = []

        for i, setup in df_setups.iterrows():
            direction = setup["direction"]
            date_ny = setup["date_ny"]

            # Tages-Bars für Entry-Logik (London-Range etc.)
            df_day = df_bars[df_bars["date_ny"] == date_ny].copy()
            if df_day.empty:
                print(f"[INFO] No bars for date {date_ny}, skipping setup {i}.")
                continue

            # Entry wird auf Basis des Tages gebaut
            entry_spec = build_entry_for_setup_scenario1(setup, df_day, setup_idx=i)
            if entry_spec is None:
                # Kein Entry in diesem Szenario -> echte "no_entry_for_scenario"-Miss,
                # hier gibt es auch keine sinnvollen Preise für SL/TP/Entry
                trades_rows.append({
                    "symbol": setup["symbol"],
                    "date_ny": date_ny,
                    "direction": direction,
                    "scenario_id": SCENARIO_ID,
                    "exit_mode": exit_mode,
                    "setup_index": i,
                    "filled": False,
                    "miss_reason": "no_entry_for_scenario",
                    "entry_idx": None,
                    "exit_idx": None,
                    "entry_price": None,
                    "sl_price": None,
                    "tp_price": None,
                    "exit_price": None,
                    "exit_reason": None,
                    "result_R": None,
                    "sl_size_pips": None,
                    "holding_minutes": None,
                })
                continue

            # Für Exit-Modi, die über den Tag hinauslaufen dürfen,
            # verwenden wir den GESAMTEN Datensatz (df_bars),
            # sonst nur den Tagesdatensatz (df_day).
            if exit_mode in ("exit_unmanaged",
                             "exit_post_2pm_1st_bos",
                             "exit_post_2pm_2nd_bos"):
                df_for_exit = df_bars
            else:
                df_for_exit = df_day

            exit_res = simulate_trade_for_exit_mode(entry_spec, df_for_exit, exit_mode=exit_mode)

            # WICHTIG: Entry/SL/TP IMMER schreiben, sobald entry_spec existiert,
            # auch wenn filled == False (z.B. no_fill_until_noon)
            trades_rows.append({
                "symbol": entry_spec.symbol,
                "date_ny": entry_spec.date_ny,
                "direction": entry_spec.direction,
                "scenario_id": entry_spec.scenario_id,
                "exit_mode": exit_mode,
                "setup_index": entry_spec.setup_index,
                "filled": exit_res.filled,
                "miss_reason": exit_res.miss_reason,
                "entry_idx": exit_res.entry_idx,
                "exit_idx": exit_res.exit_idx,
                "entry_price": entry_spec.entry_price,
                "sl_price": entry_spec.sl_price,
                "tp_price": entry_spec.tp_price,
                "exit_price": exit_res.exit_price,
                "exit_reason": exit_res.exit_reason,
                "result_R": exit_res.result_R,
                "sl_size_pips": exit_res.sl_size_pips,
                "holding_minutes": exit_res.holding_minutes,
            })

        df_trades = pd.DataFrame(trades_rows)
        print(f"Exit mode {exit_mode}: setups processed: {len(df_setups)}, trades rows: {len(df_trades)}")

        # Trades für diesen Exit-Mode runden und speichern
        df_trades_out = _round_trades_for_output(df_trades.copy())
        trades_file = TRADES_FILE_TEMPLATE.format(exit_suffix=exit_mode)
        print(f"Saving trades ({exit_mode}) to {trades_file} ...")
        df_trades_out.to_csv(trades_file, index=False)
        print("Trades file saved.")

        # Stats für diesen Exit-Modus berechnen (nur gefillte Trades zählen)
        if not df_trades.empty:
            stats = compute_stats(df_trades)
            stats = _round_stats_for_output(stats)
            stats_per_exit[exit_mode] = stats
        else:
            stats_per_exit[exit_mode] = {}

    # -------------------------------------------------
    # Stats-Matrix: metric, exit_4pm, exit_2pm, ...
    # -------------------------------------------------
    if stats_per_exit:
        all_metrics = set()
        for s in stats_per_exit.values():
            all_metrics.update(s.keys())
        all_metrics = sorted(all_metrics)

        rows = []
        for metric in all_metrics:
            row = {"metric": metric}
            for exit_mode in exit_variants:
                val = stats_per_exit.get(exit_mode, {}).get(metric, np.nan)
                row[exit_mode] = val
            rows.append(row)

        df_stats = pd.DataFrame(rows)
        print(f"\nSaving multi-exit stats to {OUTPUT_STATS_FILE} ...")
        df_stats.to_csv(OUTPUT_STATS_FILE, index=False)
        print("Stats file saved.")
    else:
        print("No stats to write.")



if __name__ == "__main__":
    main()
