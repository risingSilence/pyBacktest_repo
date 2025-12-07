print("phase1_structure_bos.py - starting up...")

import pandas as pd
import os
from datetime import datetime

# ---------------------------------
# CONFIG
# ---------------------------------

# Liste der Symbole
SYMBOLS = ["EURUSD", "GBPUSD", "AUDUSD"] #"NZDUSD", "USDJPY", "USDCAD", "USDCHF", "GBPJPY", "EURGBP"]

DATA_DIR = "data"

PIP_SIZE = 0.0001

# ... (Rest der Config: LOOKBACK, MIN_SWING_PIPS usw. bleiben gleich)

LEFT_LOOKBACK = 1
RIGHT_LOOKFORWARD = 1

# Min. Swing-Amplitude für Pivots
# WICHTIG - EURUSD ist der "ANKER" für andere Paare!
# die anderen Multis sind von der durschnittlichen Volatilität zwischen 8am und 12pm NY abgeleitet.

MIN_SWING_PIPS = {
    "EURUSD": 3.0,
    "GBPUSD": 3.2,
    "AUDUSD": 2.6,
    "NZDUSD": 2.3,
    "USDJPY": 1.9,
    "USDCAD": 3.1,
    "USDCHF": 2.7,
    "GBPJPY": 4.3,
    "EURGBP": 1.5,
}

SINGLE_COUNTER_ENGULFING = {
    "EURUSD": 4.0,
    "GBPUSD": 4.3,
    "AUDUSD": 3.5,
    "NZDUSD": 3.0,
    "USDJPY": 2.6,
    "USDCAD": 4.2,
    "USDCHF": 3.6,
    "GBPJPY": 5.7,
    "EURGBP": 2.0,
}

# Pips für CHOCH-Erkennung
CHOCH_PIPS = {
    "EURUSD": 1.5,
    "GBPUSD": 1.6,
    "AUDUSD": 1.3,
    "NZDUSD": 1.1,
    "USDJPY": 1.0,
    "USDCAD": 1.6,
    "USDCHF": 1.4,
    "GBPJPY": 2.2,
    "EURGBP": 0.8,
}

# Min. lookahead/lookforward skip pips (Hintertür),
# separat definierbar (hier = CHOCH-Werte)
SKIP_PIPS = {
    "EURUSD": 1.5,
    "GBPUSD": 1.6,
    "AUDUSD": 1.3,
    "NZDUSD": 1.1,
    "USDJPY": 1.0,
    "USDCAD": 1.6,
    "USDCHF": 1.4,
    "GBPJPY": 2.2,
    "EURGBP": 0.8,
}

# ---------------------------------
# Helpers
# ---------------------------------

def get_single_counter_engulfing_price(symbol: str) -> float:
    base = get_base_pair(symbol)
    return SINGLE_COUNTER_ENGULFING[base] * PIP_SIZE


def get_base_pair(symbol: str) -> str:
    # Wenn das Symbol direkt in der Map ist (z.B. "US30"), nimm es direkt
    if symbol in MIN_SWING_PIPS:
        return symbol

    # Fallback für Forex-Paare (falls du z.B. EURUSD_micro handelst)
    for base in ["EURUSD", "GBPUSD", "AUDUSD"]:
        if symbol.startswith(base):
            return base

    raise ValueError(f"Unknown base pair or config missing for symbol '{symbol}'")


def get_min_swing_price(symbol: str) -> float:
    base = get_base_pair(symbol)
    return MIN_SWING_PIPS[base] * PIP_SIZE


def get_choch_price(symbol: str) -> float:
    base = get_base_pair(symbol)
    return CHOCH_PIPS[base] * PIP_SIZE


def get_skip_price(symbol: str) -> float:
    """
    Min lookahead/lookforward skip pips (Hintertür) in Price-Einheiten.
    """
    base = get_base_pair(symbol)
    return SKIP_PIPS[base] * PIP_SIZE


def merge_struct_points(*lists):
    """
    Punkte aus mehreren Listen mergen, Duplikate (idx, kind) entfernen.
    Bei Konflikten gewinnt der mit kleinerem pos.
    """
    merged = {}
    for lst in lists:
        for sp in lst:
            key = (sp["idx"], sp["kind"])
            if key not in merged or sp["pos"] < merged[key]["pos"]:
                merged[key] = sp
    return list(merged.values())


# ---------------------------------
# 1) Pivot-basierte Swings + Drop/Spike-Overrides ggü. Vor-Candle
# ---------------------------------

def detect_struct_points(df: pd.DataFrame, min_swing_price: float, skip_price: float):
    """
    Basis-Swings:
      - Pivot-Logik (LEFT_LOOKBACK/RIGHT_LOOKFORWARD) + MIN_SWING_PIPS
      - zusätzliche Drop/Spike-Overrides:

        Low-Override (Uptrend-Pullback):
          - low[i] <= low[i-1] - skip_price
          - min(low[i+1..i+R]) >= low[i]  (lokales Tief nach rechts)
          - i ist KEIN Pivot-L
          => L an i (source='override_prev_drop_L')

        High-Override (Downtrend-Pullback):
          - high[i] >= high[i-1] + skip_price
          - max(high[i+1..i+R]) <= high[i] (lokales Hoch nach rechts)
          - i ist KEIN Pivot-H
          => H an i (source='override_prev_spike_H')
    """
    print("Detecting base structural points from pivots + prev-candle overrides...")
    df = df.copy()
    n = len(df)
    highs = df["high"].values
    lows = df["low"].values
    index = df.index

    L = LEFT_LOOKBACK
    R = RIGHT_LOOKFORWARD

    points = []

    pivot_low_pos = set()
    pivot_high_pos = set()

    for i in range(L, n - R):
        low_val = lows[i]
        high_val = highs[i]

        # --- LOW PIVOT ---
        window_lows = lows[i-L:i+R+1]
        left_high = highs[i-L:i].max() if i - L < i else highs[i-1]
        right_high = highs[i+1:i+1+R].max() if i + 1 < i + 1 + R <= n else highs[min(i+1, n-1)]
        depth_min = min(left_high - low_val, right_high - low_val)

        is_low_min = (low_val == window_lows.min())
        if is_low_min and depth_min >= min_swing_price:
            points.append({
                "idx": index[i],
                "kind": "L",
                "price": float(low_val),
                "pos": i,
                "source": "pivot"
            })
            pivot_low_pos.add(i)

        # --- HIGH PIVOT ---
        window_highs = highs[i-L:i+R+1]
        left_low = lows[i-L:i].min() if i - L < i else lows[i-1]
        right_low = lows[i+1:i+1+R].min() if i + 1 < i + 1 + R <= n else lows[min(i+1, n-1)]
        height_min = min(high_val - left_low, high_val - right_low)

        is_high_max = (high_val == window_highs.max())
        if is_high_max and height_min >= min_swing_price:
            points.append({
                "idx": index[i],
                "kind": "H",
                "price": float(high_val),
                "pos": i,
                "source": "pivot"
            })
            pivot_high_pos.add(i)

    # --- Drop/Spike-Overrides relativ zur vorherigen Kerze ---
    override_lows = 0
    override_highs = 0

    for i in range(L, n - R):
        # Low-Override: starker Drop vs vorige Kerze + lokales Tief nach rechts
        if i not in pivot_low_pos:
            prev_low = lows[i-1]
            drop = prev_low - lows[i]  # positiv, wenn aktuelles Low tiefer ist
            if drop >= skip_price:
                right_window = lows[i+1:i+1+R]
                if len(right_window) > 0 and right_window.min() >= lows[i]:
                    points.append({
                        "idx": index[i],
                        "kind": "L",
                        "price": float(lows[i]),
                        "pos": i,
                        "source": "override_prev_drop_L"
                    })
                    override_lows += 1

        # High-Override: starker Spike vs vorige Kerze + lokales Hoch nach rechts
        if i not in pivot_high_pos:
            prev_high = highs[i-1]
            spike = highs[i] - prev_high  # positiv, wenn aktuelles High höher ist
            if spike >= skip_price:
                right_window_h = highs[i+1:i+1+R]
                if len(right_window_h) > 0 and right_window_h.max() <= highs[i]:
                    points.append({
                        "idx": index[i],
                        "kind": "H",
                        "price": float(highs[i]),
                        "pos": i,
                        "source": "override_prev_spike_H"
                    })
                    override_highs += 1

    points.sort(key=lambda x: x["pos"])
    print(f"Base pivot structural points: L={len(pivot_low_pos)}, H={len(pivot_high_pos)}")
    print(f"Prev-candle override points:  L={override_lows}, H={override_highs}")
    print(f"Total structural points from detect_struct_points: {len(points)}")
    return points


# ---------------------------------
# 2) Immer L zwischen HH, H zwischen LL (ohne die linke Extrem-Bar)
# ---------------------------------

def ensure_intermediate_swings(df: pd.DataFrame, struct_points: list):
    print("Ensuring intermediate swings between HH and LL...")
    if not struct_points:
        return []

    df_index = df.index
    pos_map = {idx: pos for pos, idx in enumerate(df_index)}

    sps = sorted(struct_points, key=lambda x: x["pos"])
    existing = {(sp["idx"], sp["kind"]) for sp in sps}
    additions = []

    for i in range(len(sps) - 1):
        a = sps[i]
        b = sps[i+1]

        # Bereich von a.pos (inkl.) bis b.pos (exkl.)
        start_pos = a["pos"]
        end_pos = b["pos"]

        if end_pos <= start_pos:
            continue

        sub = df.iloc[start_pos:end_pos]
        if sub.empty:
            continue

        # ------------------------------------------------------
        # L zwischen zwei H (a.kind == 'H' und b.kind == 'H')
        # Standard: linke H-Bar NICHT als Low-Kandidat.
        # Ausnahme: wenn linke H-Bar BEARISH (close < open),
        #           darf ihr Low als Kandidat mitgezählt werden.
        # ------------------------------------------------------
        if a["kind"] == "H" and b["kind"] == "H":
            sub_for_low = sub

            if sub_for_low.index[0] == a["idx"]:
                first_row = sub_for_low.iloc[0]
                # Bearish-Body-Check: nur wenn NICHT bearish, erste Zeile droppen
                if not (float(first_row["close"]) < float(first_row["open"])):
                    sub_for_low = sub_for_low.iloc[1:]

            if sub_for_low.empty:
                continue

            idx_min = sub_for_low["low"].idxmin()
            if (idx_min, "L") not in existing:
                additions.append({
                    "idx": idx_min,
                    "kind": "L",
                    "price": float(sub_for_low.loc[idx_min, "low"]),
                    "pos": pos_map[idx_min],
                    "source": "intermediate_L_between_HH"
                })
                existing.add((idx_min, "L"))

        # ------------------------------------------------------
        # H zwischen zwei L (a.kind == 'L' und b.kind == 'L')
        # Standard: linke L-Bar NICHT als High-Kandidat.
        # Ausnahme: wenn linke L-Bar BULLISH (close > open),
        #           darf ihr High als Kandidat mitgezählt werden.
        # ------------------------------------------------------
        if a["kind"] == "L" and b["kind"] == "L":
            sub_for_high = sub

            if sub_for_high.index[0] == a["idx"]:
                first_row = sub_for_high.iloc[0]
                # Bullish-Body-Check: nur wenn NICHT bullish, erste Zeile droppen
                if not (float(first_row["close"]) > float(first_row["open"])):
                    sub_for_high = sub_for_high.iloc[1:]

            if sub_for_high.empty:
                continue

            idx_max = sub_for_high["high"].idxmax()
            if (idx_max, "H") not in existing:
                additions.append({
                    "idx": idx_max,
                    "kind": "H",
                    "price": float(sub_for_high.loc[idx_max, "high"]),
                    "pos": pos_map[idx_max],
                    "source": "intermediate_H_between_LL"
                })
                existing.add((idx_max, "H"))

    print(f"Intermediate swings added: {len(additions)}")
    return additions



# ---------------------------------
# 2b) Body-Filter: Struktur nur mit „richtungs-passenden“ Bodies
# ---------------------------------

def apply_body_filter(df: pd.DataFrame, struct_points: list) -> list:
    """
    Filtert Strukturpunkte so, dass:
      - ein L (HL/LL) nur erlaubt ist, wenn seit dem letzten H davor
        mind. eine Candle mit close <= open (bear oder doji) vorkam.
      - ein H (HH/LH) nur erlaubt ist, wenn seit dem letzten L davor
        mind. eine Candle mit close >= open (bull oder doji) vorkam.

    Spezielle Ausnahmen:
      - Wenn auf derselben Candle sowohl ein L als auch ein H liegen,
        werden beide Strukturpunkte akzeptiert, ohne Body-Filter.
      - Alle Punkte mit source, die mit 'counter_engulf' beginnen,
        werden ebenfalls ohne Body-Filter akzeptiert.
    """
    if not struct_points:
        return []

    sps = sorted(struct_points, key=lambda x: x["pos"])
    opens  = df["open"].values
    closes = df["close"].values

    idx_has_L = {sp["idx"] for sp in sps if sp["kind"] == "L"}
    idx_has_H = {sp["idx"] for sp in sps if sp["kind"] == "H"}

    accepted = []

    last_H_pos = None
    prev_H_pos = None
    last_L_pos = None
    prev_L_pos = None

    for sp in sps:
        pos  = sp["pos"]
        idx  = sp["idx"]
        kind = sp["kind"]
        src  = (sp.get("source", "") or "")
        accept = True

        # --- NEU: alle counter_engulf*-Punkte immer durchlassen ---
        if src.startswith("counter_engulf"):
            accepted.append(sp)
            if kind == "L":
                prev_L_pos = last_L_pos
                last_L_pos = pos
            elif kind == "H":
                prev_H_pos = last_H_pos
                last_H_pos = pos
            continue

        if kind == "L":
            # Sonderfall: auf dieser Candle gibt es auch ein H -> Body-Filter überspringen
            if idx in idx_has_H:
                accepted.append(sp)
                prev_L_pos = last_L_pos
                last_L_pos = pos
                continue

            ref_H_pos = None
            if last_H_pos is not None:
                if last_H_pos < pos:
                    ref_H_pos = last_H_pos
                elif last_H_pos == pos and prev_H_pos is not None and prev_H_pos < pos:
                    ref_H_pos = prev_H_pos

            if ref_H_pos is not None and ref_H_pos < pos:
                segment_opens  = opens[ref_H_pos:pos+1]
                segment_closes = closes[ref_H_pos:pos+1]
                # bear oder doji: close <= open
                has_bear_or_doji = (segment_closes <= segment_opens).any()
                if not has_bear_or_doji:
                    accept = False

            if accept:
                accepted.append(sp)
                prev_L_pos = last_L_pos
                last_L_pos = pos

        elif kind == "H":
            # Sonderfall: auf dieser Candle gibt es auch ein L -> Body-Filter überspringen
            if idx in idx_has_L:
                accepted.append(sp)
                prev_H_pos = last_H_pos
                last_H_pos = pos
                continue

            ref_L_pos = None
            if last_L_pos is not None:
                if last_L_pos < pos:
                    ref_L_pos = last_L_pos
                elif last_L_pos == pos and prev_L_pos is not None and prev_L_pos < pos:
                    ref_L_pos = prev_L_pos

            if ref_L_pos is not None and ref_L_pos < pos:
                segment_opens  = opens[ref_L_pos:pos+1]
                segment_closes = closes[ref_L_pos:pos+1]
                # bull oder doji: close >= open
                has_bull_or_doji = (segment_closes >= segment_opens).any()
                if not has_bull_or_doji:
                    accept = False

            if accept:
                accepted.append(sp)
                prev_H_pos = last_H_pos
                last_H_pos = pos

        else:
            accepted.append(sp)

    print(
        f"Structural points after body filter: "
        f"{len(accepted)} (vorher: {len(struct_points)})"
    )
    return accepted






# ---------------------------------
# 2c) LH/HL-Verfeinerung mit Pivot-Kriterium
# ---------------------------------

def refine_LH_HL_with_pivot(df: pd.DataFrame,
                            struct_points: list,
                            df_swings: pd.DataFrame,
                            min_swing_price: float) -> list:
    """
    Regel:
      - Ein LH, das NICHT zu einem LL führt (bis zum nächsten High-Swing),
        muss Pivot-Kriterien erfüllen (Lookback/Lookforward + min_swing_price),
        sonst wird das High an dieser Stelle entfernt.
      - Ein HL, das NICHT zu einem HH führt (bis zum nächsten Low-Swing),
        muss Pivot-Kriterien erfüllen, sonst wird das Low entfernt.
    """
    if not struct_points:
        return []

    sps = sorted(struct_points, key=lambda x: x["pos"])

    idx_list = list(df.index)
    idx_to_pos = {idx: i for i, idx in enumerate(idx_list)}
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    swing_high_label = df_swings["swing_high_label"].to_dict()
    swing_low_label = df_swings["swing_low_label"].to_dict()

    to_remove_H = set()
    to_remove_L = set()

    L = LEFT_LOOKBACK
    R = RIGHT_LOOKFORWARD

    def is_pivot_high(pos: int) -> bool:
        if pos < L or pos > n - 1 - R:
            return False
        h = highs[pos]
        window_highs = highs[pos-L:pos+R+1]
        if h != window_highs.max():
            return False
        left_low = lows[pos-L:pos].min()
        right_low = lows[pos+1:pos+1+R].min()
        height_min = min(h - left_low, h - right_low)
        return height_min >= min_swing_price

    def is_pivot_low(pos: int) -> bool:
        if pos < L or pos > n - 1 - R:
            return False
        lo = lows[pos]
        window_lows = lows[pos-L:pos+R+1]
        if lo != window_lows.min():
            return False
        left_high = highs[pos-L:pos].max()
        right_high = highs[pos+1:pos+1+R].max()
        depth_min = min(left_high - lo, right_high - lo)
        return depth_min >= min_swing_price

    high_swing_positions = []
    low_swing_positions = []

    for idx in idx_list:
        lbl_h = swing_high_label.get(idx, "")
        lbl_l = swing_low_label.get(idx, "")
        pos = idx_to_pos[idx]
        if lbl_h != "":
            high_swing_positions.append((pos, idx, lbl_h))
        if lbl_l != "":
            low_swing_positions.append((pos, idx, lbl_l))

    # --- LH prüfen: hat kein LL danach -> Pivot nötig ---
    for pos, idx, lbl in high_swing_positions:
        if lbl != "LH":
            continue

        next_high_pos = None
        for p2, idx2, lbl2 in high_swing_positions:
            if p2 > pos:
                next_high_pos = p2
                break

        end_pos = next_high_pos if next_high_pos is not None else n

        has_LL = False
        for p_l, idx_l, lbl_l in low_swing_positions:
            if p_l > pos and p_l < end_pos and lbl_l == "LL":
                has_LL = True
                break

        if not has_LL:
            if not is_pivot_high(pos):
                to_remove_H.add(idx)

    # --- HL prüfen: hat kein HH danach -> Pivot nötig ---
    for pos, idx, lbl in low_swing_positions:
        if lbl != "HL":
            continue

        next_low_pos = None
        for p2, idx2, lbl2 in low_swing_positions:
            if p2 > pos:
                next_low_pos = p2
                break

        end_pos = next_low_pos if next_low_pos is not None else n

        has_HH = False
        for p_h, idx_h, lbl_h in high_swing_positions:
            if p_h > pos and p_h < end_pos and lbl_h == "HH":
                has_HH = True
                break

        if not has_HH:
            if not is_pivot_low(pos):
                to_remove_L.add(idx)

    refined = []
    for sp in sps:
        if sp["kind"] == "H" and sp["idx"] in to_remove_H:
            continue
        if sp["kind"] == "L" and sp["idx"] in to_remove_L:
            continue
        refined.append(sp)

    print(f"Refined structural points (LH/HL pivot filter): {len(refined)} (vorher: {len(sps)})")
    return refined


# ---------------------------------
# 2d) LL/HH-Merge: keine LL-LL und HH-HH ohne LH/HL dazwischen
# ---------------------------------

def merge_consecutive_extremes(df: pd.DataFrame,
                               struct_points: list,
                               df_swings: pd.DataFrame) -> list:
    """
    Regel:
      - Zwei aufeinanderfolgende LL (in der Sequence der L-Swings),
        zwischen denen KEIN LH liegt -> das frühere LL wird verworfen,
        das spätere LL bleibt.
      - Zwei aufeinanderfolgende HH (in der Sequence der H-Swings),
        zwischen denen KEIN HL liegt -> das frühere HH wird verworfen.

      Ausnahme:
        - Wenn das frühere HH auf derselben Candle gleichzeitig ein HL trägt,
          wird es NICHT verworfen (typischer Fall: HH+HL auf einer Candle
          im laufenden Uptrend).
        - Analog könnte man das später für LL+LH spiegeln, falls gewünscht.

    Dadurch gibt es keine LL-LL bzw. HH-HH-Folgen mehr ohne
    passende Gegenstruktur dazwischen, außer in dem bewusst
    erlaubten Spezialfall HH+HL auf derselben Kerze.
    """
    if not struct_points:
        return []

    sps = sorted(struct_points, key=lambda x: x["pos"])

    # Mapping Index -> pos für schnelle Suche
    idx_list = list(df.index)
    idx_to_pos = {idx: i for i, idx in enumerate(idx_list)}

    swing_low_label = df_swings["swing_low_label"].to_dict()
    swing_high_label = df_swings["swing_high_label"].to_dict()

    low_swings = []   # (pos, idx, lbl)
    high_swings = []  # (pos, idx, lbl)

    for sp in sps:
        idx = sp["idx"]
        pos = sp["pos"]
        if sp["kind"] == "L":
            lbl_l = swing_low_label.get(idx, "")
            if lbl_l != "":
                low_swings.append((pos, idx, lbl_l))
        elif sp["kind"] == "H":
            lbl_h = swing_high_label.get(idx, "")
            if lbl_h != "":
                high_swings.append((pos, idx, lbl_h))

    # --- LL-LL-Fälle bereinigen (ohne LH dazwischen) ---
    drop_L = set()

    high_swings_sorted = sorted(high_swings, key=lambda x: x[0])

    prev_LL = None  # (pos, idx, lbl)

    for pos, idx, lbl in sorted(low_swings, key=lambda x: x[0]):
        if lbl == "LL":
            if prev_LL is not None and prev_LL[2] == "LL":
                pos_prev, idx_prev, _ = prev_LL

                # Check: gibt es zwischen pos_prev und pos eine LH?
                has_LH_between = False
                for p_h, idx_h, lbl_h in high_swings_sorted:
                    if p_h > pos_prev and p_h < pos and lbl_h == "LH":
                        has_LH_between = True
                        break

                if not has_LH_between:
                    # Älteres LL verwerfen
                    drop_L.add(idx_prev)

            prev_LL = (pos, idx, lbl)
        else:
            # HL/L0/... unterbrechen die LL-Kette
            prev_LL = (pos, idx, lbl)

    # --- HH-HH-Fälle bereinigen (ohne HL dazwischen) ---
    drop_H = set()

    low_swings_sorted = sorted(low_swings, key=lambda x: x[0])

    prev_HH = None  # (pos, idx, lbl)

    for pos, idx, lbl in sorted(high_swings, key=lambda x: x[0]):
        if lbl == "HH":
            if prev_HH is not None and prev_HH[2] == "HH":
                pos_prev, idx_prev, _ = prev_HH

                # Check: gibt es zwischen pos_prev und pos ein HL?
                has_HL_between = False
                for p_l, idx_l, lbl_l in low_swings_sorted:
                    if p_l > pos_prev and p_l < pos and lbl_l == "HL":
                        has_HL_between = True
                        break

                if not has_HL_between:
                    # Ausnahme:
                    # Wenn auf derselben Kerze wie das frühere HH auch ein HL liegt,
                    # dann dieses HH NICHT verwerfen (typischer Fall: HH+HL zusammen).
                    low_lbl_prev = swing_low_label.get(idx_prev, "")
                    if low_lbl_prev != "HL":
                        # nur droppen, wenn das frühere HH NICHT gleichzeitig ein HL trägt
                        drop_H.add(idx_prev)

            prev_HH = (pos, idx, lbl)
        else:
            # LH/H0/... unterbrechen die HH-Kette
            prev_HH = (pos, idx, lbl)

    # --- Struct-Points nach Drop-Listen filtern ---
    refined = []
    for sp in sps:
        if sp["kind"] == "L" and sp["idx"] in drop_L:
            continue
        if sp["kind"] == "H" and sp["idx"] in drop_H:
            continue
        refined.append(sp)

    print(
        f"Merged consecutive extremes: "
        f"dropped L={len(drop_L)}, H={len(drop_H)}, remaining points={len(refined)}"
    )
    return refined



# ---------------------------------
# 3) Swings klassifizieren (HH/HL/LH/LL)
# ---------------------------------

def classify_swings(df: pd.DataFrame, struct_points: list) -> pd.DataFrame:
    df = df.copy()
    df["swing_low_price"] = pd.NA
    df["swing_low_label"] = ""
    df["swing_high_price"] = pd.NA
    df["swing_high_label"] = ""

    sps = sorted(struct_points, key=lambda x: x["pos"])
    last_low = None
    last_high = None

    for sp in sps:
        idx = sp["idx"]
        price = sp["price"]
        kind = sp["kind"]

        if kind == "L":
            if last_low is None:
                label = "L0"
            else:
                if price > last_low:
                    label = "HL"
                elif price < last_low:
                    label = "LL"
                else:
                    label = "L_eq"
            last_low = price
            df.loc[idx, "swing_low_price"] = price
            df.loc[idx, "swing_low_label"] = label

        elif kind == "H":
            if last_high is None:
                label = "H0"
            else:
                if price > last_high:
                    label = "HH"
                elif price < last_high:
                    label = "LH"
                else:
                    label = "H_eq"
            last_high = price
            df.loc[idx, "swing_high_price"] = price
            df.loc[idx, "swing_high_label"] = label

    return df


def relabel_inside_legs(df: pd.DataFrame, struct_points: list) -> pd.DataFrame:
    """
    Post-Processing:
      - Im Bärentrend:
          * Ein HH, das das Leg-High oder das letzte HH NICHT strikt überbietet,
            wird zu LH umgelabelt.
          * Ein LL, das das Leg-Low oder das letzte LL NICHT strikt unterbietet,
            wird zu HL umgelabelt.
      - Im Bullentrend entsprechend gespiegelt.

      - JEDES MAL, wenn:
          * ein echtes HH bestätigt wird, springt das LL-Kriterium
            (last_LL_price) auf das jüngste Swing-Low.
          * ein echtes LL bestätigt wird, springt das HH-Kriterium
            (last_HH_price) auf das jüngste Swing-High.

      - DAILY RESET:
          * Am FX-Rollover (17:00 NY) beginnt der nächste FX-Tag.
          * Beim ersten Strukturpunkt eines neuen FX-Tags werden alle
            Anker (Leg-High/Low, letzte HH/LL, letzte H/L) zurückgesetzt.
    """
    df = df.copy()

    swing_low_price  = df["swing_low_price"].to_dict()
    swing_low_label  = df["swing_low_label"].to_dict()
    swing_high_price = df["swing_high_price"].to_dict()
    swing_high_label = df["swing_high_label"].to_dict()

    sps = sorted(struct_points, key=lambda x: x["pos"])

    last_high_price = None
    last_low_price  = None

    # Leg-Anker
    bear_anchor_high = None  # Leg-High für Bärentrend
    bull_anchor_low  = None  # Leg-Low  für Bullentrend

    # Aktuelle „Kriterien“ für echte LL / HH
    last_LL_price = None     # aktuelles relevantes Leg-Low (für LL)
    last_HH_price = None     # aktuelles relevantes Leg-High (für HH)

    # FX-Day-Tracking (Rollover 17:00 NY)
    current_fx_day = None    # (Datum nach Shift um 17h)

    for sp in sps:
        idx  = sp["idx"]       # time_ny als Index
        kind = sp["kind"]

        # -------------------------------
        # FX-Day-Bestimmung (17:00 NY)
        # -------------------------------
        ts = pd.Timestamp(idx)
        fx_day = (ts - pd.Timedelta(hours=17)).date()

        if current_fx_day is None:
            current_fx_day = fx_day
        elif fx_day != current_fx_day:
            # Neuer FX-Tag -> alle Anker resetten
            current_fx_day = fx_day
            bear_anchor_high = None
            bull_anchor_low  = None
            last_LL_price    = None
            last_HH_price    = None
            last_high_price  = None
            last_low_price   = None

        if kind == "H":
            price = swing_high_price.get(idx, None)
            label = swing_high_label.get(idx, "")

            if price is None or pd.isna(price):
                continue

            # Bullischer Leg-Anker: bei HH den letzten Low davor merken
            if label == "HH" and last_low_price is not None:
                bull_anchor_low = last_low_price

            # Bärischer Leg: HH darf nur HH bleiben, wenn es das Leg-High STRICT bricht
            if bear_anchor_high is not None and label == "HH":
                if price <= bear_anchor_high:
                    # noch innerhalb oder exakt am alten Bear-Leg-High -> nur LH
                    df.at[idx, "swing_high_label"] = "LH"
                    label = "LH"
                else:
                    # echtes HH, Leg-High nachziehen
                    bear_anchor_high = price

            # Globale HH-Logik: must beat last_HH_price STRICT
            if label == "HH":
                if last_HH_price is not None and price <= last_HH_price:
                    # tiefer oder gleich letztem HH -> eigentlich LH
                    df.at[idx, "swing_high_label"] = "LH"
                    label = "LH"
                else:
                    # neues „echtes“ HH
                    last_HH_price = price

                    # sobald ein echtes HH bestätigt ist, springt
                    # das LL-Kriterium auf das jüngste Swing-Low
                    if last_low_price is not None:
                        last_LL_price = last_low_price

            # letztes High updaten
            last_high_price = price

        elif kind == "L":
            price = swing_low_price.get(idx, None)
            label = swing_low_label.get(idx, "")

            if price is None or pd.isna(price):
                continue

            # Bärischer Leg-Anker: bei LL das letzte High davor merken
            if label == "LL" and last_high_price is not None:
                bear_anchor_high = last_high_price

            # Bullischer Leg: LL darf nur LL bleiben, wenn es das Leg-Low STRICT bricht
            if bull_anchor_low is not None and label == "LL":
                if price >= bull_anchor_low:
                    # noch innerhalb oder exakt am alten Bull-Leg-Low -> nur HL
                    df.at[idx, "swing_low_label"] = "HL"
                    label = "HL"
                else:
                    # echtes LL im Kontext des Bull-Legs
                    bull_anchor_low = price

            # Globale LL-Logik: must beat last_LL_price STRICT
            if label == "LL":
                if last_LL_price is not None and price >= last_LL_price:
                    # oberhalb oder gleich dem aktuellen Leg-Low -> eigentlich HL
                    df.at[idx, "swing_low_label"] = "HL"
                    label = "HL"
                else:
                    # neues „echtes“ LL
                    last_LL_price = price

                    # sobald ein echtes LL bestätigt ist, springt
                    # das HH-Kriterium auf das jüngste Swing-High
                    if last_high_price is not None:
                        last_HH_price = last_high_price

            # letztes Low updaten
            last_low_price = price

    return df

def apply_counter_engulf_override(df: pd.DataFrame, struct_points: list) -> pd.DataFrame:
    """
    Sonderbehandlung für Single-Counter-Engulfing:

      - Für L mit source == 'counter_engulf_L':
          * Wenn es bereits ein vorheriges strukturelles Low gibt
            und dieses Low niedriger ist als das aktuelle,
            wird das Label zwangsweise auf 'HL' gesetzt.

      - Für H mit source == 'counter_engulf_H':
          * Wenn es bereits ein vorheriges strukturelles High gibt
            und dieses High höher ist als das aktuelle,
            wird das Label zwangsweise auf 'LH' gesetzt.

    Ziel:
      - In starken Single-Counter-Engulfing-Mustern soll ein HL/LH
        nicht durch frühere Filter/Heuristiken „verhindert“ werden,
        sondern explizit durchgesetzt werden.
    """
    df = df.copy()

    swing_low_price  = df["swing_low_price"].to_dict()
    swing_low_label  = df["swing_low_label"].to_dict()
    swing_high_price = df["swing_high_price"].to_dict()
    swing_high_label = df["swing_high_label"].to_dict()

    sps = sorted(struct_points, key=lambda x: x["pos"])

    # Wir tracken das letzte valide Low/High, so wie es final im df steht.
    last_low_price  = None
    last_high_price = None

    for sp in sps:
        idx  = sp["idx"]
        kind = sp["kind"]
        src  = sp.get("source", "")

        # ---------- LOW-SEITE: counter_engulf_L -> HL erzwingen ----------
        if kind == "L":
            price = swing_low_price.get(idx, None)
            if price is None or pd.isna(price):
                continue

            lbl = swing_low_label.get(idx, "")

            # Wenn dieser Punkt aus Single-Counter-Engulfing stammt:
            if src == "counter_engulf_L":
                # Es gibt bereits ein vorheriges strukturelles Low?
                if last_low_price is not None:
                    # Tiefer als das letzte Low -> normal LL/HL-Logik
                    # Höher als das letzte Low -> explizit HL setzen
                    if price > last_low_price:
                        df.at[idx, "swing_low_label"] = "HL"
                        swing_low_label[idx] = "HL"
                        # und dieses HL wird neues Referenz-Low
                        last_low_price = price
                        continue
                    # falls price <= last_low_price: lassen wir das bestehende Label,
                    # aber aktualisieren ggf. last_low_price.
                # falls kein last_low_price vorhanden war, verhalten wir uns neutral
                # (Label bleibt wie es ist, typischerweise L0 o.ä.)

            # normales Update des letzten gültigen Lows,
            # basierend auf dem finalen Label
            lbl_after = swing_low_label.get(idx, "")
            if lbl_after in ("L0", "HL", "LL", "L_eq"):
                last_low_price = price

        # ---------- HIGH-SEITE: counter_engulf_H -> LH erzwingen ----------
        elif kind == "H":
            price = swing_high_price.get(idx, None)
            if price is None or pd.isna(price):
                continue

            lbl = swing_high_label.get(idx, "")

            if src == "counter_engulf_H":
                if last_high_price is not None:
                    # Höher als letztes High -> normales HH-Szenario
                    # Niedriger als letztes High -> explizit LH setzen
                    if price < last_high_price:
                        df.at[idx, "swing_high_label"] = "LH"
                        swing_high_label[idx] = "LH"
                        last_high_price = price
                        continue
                # falls kein last_high_price: neutral, Label bleibt wie es ist

            lbl_after = swing_high_label.get(idx, "")
            if lbl_after in ("H0", "HH", "LH", "H_eq"):
                last_high_price = price

    return df



# ---------------------------------
# 4a) Bearish CHOCH – nur erstes LL nach HL-Bruch
# ---------------------------------

def scan_bearish_choch(df: pd.DataFrame, df_swings: pd.DataFrame, choch_price: float):
    """
    Für jedes HL (oder L0):
      - suche erste bearische Candle j mit Low <= HL_low - choch_price
      - suche von j aus die erste nicht-bearische Candle k (Base, close >= open)
      - bestimme minLow in [j..k]
      - erzeuge GENAU EIN LL an diesem minLow
    """
    print("Scanning bearish CHOCH (first LL after HL break)...")

    idx_list = list(df.index)
    n = len(idx_list)

    lows = df["low"].values
    opens = df["open"].values
    closes = df["close"].values

    swing_low_price = df_swings["swing_low_price"].to_dict()
    swing_low_label = df_swings["swing_low_label"].to_dict()

    synthetic = []

    # HL-/L0-Positionen sammeln
    hl_positions = []
    for pos, idx in enumerate(idx_list):
        lbl = swing_low_label.get(idx, "")
        if lbl in ("HL", "L0"):
            price = swing_low_price.get(idx, None)
            if price is not None and not pd.isna(price):
                hl_positions.append((pos, idx, float(price)))

    for pos_hl, idx_hl, hl_price in hl_positions:
        # 1) erste bearische Break-Candle j
        j = None
        for k in range(pos_hl + 1, n):
            if closes[k] < opens[k] and lows[k] <= hl_price - choch_price:
                j = k
                break
        if j is None:
            continue

        # 2) erste nicht-bearische Candle k >= j (Base)
        k_base = None
        for k in range(j, n):
            if closes[k] >= opens[k]:
                k_base = k
                break
        if k_base is None:
            continue

        # minLow in [j..k_base]
        segment_lows = lows[j:k_base+1]
        rel_min = segment_lows.argmin()
        i_min = j + rel_min
        idx_min = idx_list[i_min]
        base_ll_price = float(lows[i_min])

        # LL an idx_min (nur wenn dort nicht schon ein L aus CHOCH steht)
        exists = any(sp["idx"] == idx_min and sp["kind"] == "L" for sp in synthetic)
        if not exists:
            synthetic.append({
                "idx": idx_min,
                "kind": "L",
                "price": base_ll_price,
                "pos": i_min,
                "source": "bear_choch_LL"
            })

    print(f"Bearish CHOCH LL points: {len(synthetic)}")
    return synthetic


# ---------------------------------
# 4b) Bullish CHOCH – nur erstes HH nach LH-Bruch
# ---------------------------------

def scan_bullish_choch(df: pd.DataFrame, df_swings: pd.DataFrame, choch_price: float):
    """
    Für jedes LH (oder H0):
      - suche erste bullische Candle j mit High >= LH_high + choch_price
      - suche von j aus die erste nicht-bearische Candle k (Base, close <= open)
      - bestimme maxHigh in [j..k]
      - erzeuge GENAU EIN HH an diesem maxHigh
    """
    print("Scanning bullish CHOCH (first HH after LH break)...")

    idx_list = list(df.index)
    n = len(idx_list)

    highs = df["high"].values
    opens = df["open"].values
    closes = df["close"].values

    swing_high_price = df_swings["swing_high_price"].to_dict()
    swing_high_label = df_swings["swing_high_label"].to_dict()

    synthetic = []

    # LH-/H0-Positionen sammeln
    lh_positions = []
    for pos, idx in enumerate(idx_list):
        lbl = swing_high_label.get(idx, "")
        if lbl in ("LH", "H0"):
            price = swing_high_price.get(idx, None)
            if price is not None and not pd.isna(price):
                lh_positions.append((pos, idx, float(price)))

    for pos_lh, idx_lh, lh_price in lh_positions:
        # 1) erste bullische Break-Candle j
        j = None
        for k in range(pos_lh + 1, n):
            if closes[k] > opens[k] and highs[k] >= lh_price + choch_price:
                j = k
                break
        if j is None:
            continue

        # 2) erste nicht-bearische Candle k >= j (Base)
        k_base = None
        for k in range(j, n):
            if closes[k] <= opens[k]:
                k_base = k
                break
        if k_base is None:
            continue

        # maxHigh in [j..k_base]
        segment_highs = highs[j:k_base+1]
        rel_max = segment_highs.argmax()
        i_max = j + rel_max
        idx_max = idx_list[i_max]
        base_hh_price = float(highs[i_max])

        # HH an idx_max (nur wenn dort nicht schon ein H aus CHOCH steht)
        exists = any(sp["idx"] == idx_max and sp["kind"] == "H" for sp in synthetic)
        if not exists:
            synthetic.append({
                "idx": idx_max,
                "kind": "H",
                "price": base_hh_price,
                "pos": i_max,
                "source": "bull_choch_HH"
            })

    print(f"Bullish CHOCH HH points: {len(synthetic)}")
    return synthetic

def scan_single_counter_engulfing(df: pd.DataFrame, threshold_price: float):
    """
    Sucht nach Single-Counter-Engulfing-Pattern mit Kontext-Bedingung,
    wobei die Mindeststrecke auf der Impuls-Candle j wie folgt gemessen wird:

    - bullischer Sonderfall:   Strecke = high_j - open_j
    - bearischer Sonderfall:   Strecke = open_j - low_j

    Bullischer Sonderfall:
        - Candle i-1: bull (close > open)
        - Candle i  : bear (close < open)   -> "Problemkerze"
        - Candle j = i+1: bull (close > open)
        - High(j) strikt über High(i): high_j > high_i
        - (high_j - open_j) >= threshold_price
        -> wir erzwingen auf Candle i:
             * einen Low-Strukturpunkt (L)  -> später HL
             * einen High-Strukturpunkt (H) -> später HH/H

    Bearischer Sonderfall (gespiegelt):
        - Candle i-1: bear (close < open)
        - Candle i  : bull (close > open)
        - Candle j = i+1: bear (close < open)
        - Low(j) strikt unter Low(i): low_j < low_i
        - (open_j - low_j) >= threshold_price
        -> wir erzwingen auf Candle i:
             * einen High-Strukturpunkt (H) -> später LH
             * einen Low-Strukturpunkt (L)  -> später LL/L

    Die eigentliche Klassifikation in HL/LL/HH/LH macht danach
    weiterhin `classify_swings()`.
    """
    idx_list = list(df.index)
    n = len(idx_list)

    opens  = df["open"].values
    closes = df["close"].values
    highs  = df["high"].values
    lows   = df["low"].values

    points = []

    for i in range(n - 1):
        j = i + 1

        o_i, c_i = float(opens[i]),  float(closes[i])
        h_i, l_i = float(highs[i]),  float(lows[i])
        o_j, c_j = float(opens[j]),  float(closes[j])
        h_j, l_j = float(highs[j]),  float(lows[j])

        # Wir brauchen i-1 für den Kontext
        if i == 0:
            continue
        o_prev, c_prev = float(opens[i-1]), float(closes[i-1])

        idx_i = idx_list[i]

        # -----------------------------
        # Bullischer Sonderfall:
        # prev bull, i bear, j bull
        # high_j strikt > high_i
        # und Impulsstrecke (high_j - open_j) >= threshold_price
        # -----------------------------
        if (c_prev > o_prev and      # i-1 bull
            c_i < o_i and            # i bear
            c_j > o_j and            # j bull
            h_j > h_i):              # j bricht High von i

            bull_impulse = h_j - o_j
            if bull_impulse >= threshold_price:
                # erzwungenes Low (später HL)
                points.append({
                    "idx":   idx_i,
                    "kind":  "L",
                    "price": l_i,
                    "pos":   i,
                    "source": "counter_engulf_L"
                })
                # erzwungenes High (später HH/H)
                points.append({
                    "idx":   idx_i,
                    "kind":  "H",
                    "price": h_i,
                    "pos":   i,
                    "source": "counter_engulf_L_high"
                })

        # -----------------------------
        # Bearischer Sonderfall:
        # prev bear, i bull, j bear
        # low_j strikt < low_i
        # und Impulsstrecke (open_j - low_j) >= threshold_price
        # -----------------------------
        if (c_prev < o_prev and      # i-1 bear
            c_i > o_i and            # i bull
            c_j < o_j and            # j bear
            l_j < l_i):              # j bricht Low von i

            bear_impulse = o_j - l_j
            if bear_impulse >= threshold_price:
                # erzwungenes High (später LH)
                points.append({
                    "idx":   idx_i,
                    "kind":  "H",
                    "price": h_i,
                    "pos":   i,
                    "source": "counter_engulf_H"
                })
                # erzwungenes Low (später LL/L)
                points.append({
                    "idx":   idx_i,
                    "kind":  "L",
                    "price": l_i,
                    "pos":   i,
                    "source": "counter_engulf_H_low"
                })

    print(f"Single-counter engulfing points: {len(points)}")
    return points



# ---------------------------------
# 5) BOS
# ---------------------------------

def detect_bos(df: pd.DataFrame, struct_points: list) -> pd.DataFrame:
    print("Detecting BOS up/down...")
    df = df.copy()
    df["bos_up"] = False
    df["bos_down"] = False

    sp_map = {}
    for sp in struct_points:
        sp_map.setdefault(sp["idx"], []).append(sp)

    last_high = None
    last_low = None
    bos_up_list = []
    bos_down_list = []

    for idx, row in df.iterrows():
        close = float(row["close"])

        bos_up = False
        bos_down = False

        if last_high is not None and close > last_high:
            bos_up = True
        if last_low is not None and close < last_low:
            bos_down = True

        bos_up_list.append(bos_up)
        bos_down_list.append(bos_down)

        if idx in sp_map:
            for sp in sp_map[idx]:
                if sp["kind"] == "H":
                    last_high = sp["price"]
                elif sp["kind"] == "L":
                    last_low = sp["price"]

    df["bos_up"] = bos_up_list
    df["bos_down"] = bos_down_list
    return df

# ---------------------------------
# PIPELINE WRAPPER
# ---------------------------------

def run_phase1_for_symbol(symbol: str):
    print(f"--- Processing Phase 1 for {symbol} ---")

    # Dateinamen dynamisch
    input_filename = f"data_{symbol}_M5_phase0_enriched.csv"
    input_file = os.path.join(DATA_DIR, input_filename)

    # ALT:
    # output_filename = f"data_{symbol}_M5_phase1_structure.csv"
    
    # NEU (Vorschlag):
    output_filename = f"data_{symbol}_M5_phase1_structure_NY.csv"
    output_file = os.path.join(DATA_DIR, output_filename)

    if not os.path.exists(input_file):
        print(f"Skipping {symbol}: Input file not found ({input_file})")
        return

    print("Loading input file...", input_file)
    df_all = pd.read_csv(input_file)

    if "time_ny" not in df_all.columns:
        raise RuntimeError("Column 'time_ny' not found in input file.")

    # Set index
    df_all["time_ny"] = pd.to_datetime(df_all["time_ny"])
    df_all = df_all.set_index("time_ny").sort_index()

    # Filter auf Symbol
    df_sym = df_all[df_all["symbol"] == symbol].copy()
    if df_sym.empty:
        print(f"Warning: No data for {symbol} in dataset.")
        return

    print(f"Rows for {symbol}: {len(df_sym)}")

    # Parameter dynamisch für das aktuelle Symbol holen
    min_swing_price = get_min_swing_price(symbol)
    choch_price = get_choch_price(symbol)
    skip_price = get_skip_price(symbol)

    print(f"Min swing amplitude (pivot):                 {min_swing_price}")
    print(f"CHOCH price threshold (for BOS/CHOCH logic): {choch_price}")
    print(f"Min lookahead/lookforward skip pips (price): {skip_price}")

    # --- CORE LOGIC (Steps 1-13) ---

    # 1) Pivot-Swings + prev-candle-Overrides
    base_points = detect_struct_points(df_sym, min_swing_price, skip_price)

    # 2) Zwischen-Swings (erste Runde)
    interm1 = ensure_intermediate_swings(df_sym, base_points)
    base_plus_interm1 = merge_struct_points(base_points, interm1)

    # 3) Vorläufige Klassifikation (für HL/LH-Referenzen)
    df_pre = classify_swings(df_sym, base_plus_interm1)

    # 4a) Bearish CHOCH-LL
    choch_bear = scan_bearish_choch(df_sym, df_pre, choch_price)

    # 4b) Bullish CHOCH-HH
    choch_bull = scan_bullish_choch(df_sym, df_pre, choch_price)

    # 4c) Single-Counter-Engulfing (zusätzliche Struktur-L/H)
    sc_threshold = get_single_counter_engulfing_price(symbol)
    sc_points = scan_single_counter_engulfing(df_sym, sc_threshold)

    # 5) Merge
    points_with_choch_sc = merge_struct_points(base_plus_interm1, choch_bear, choch_bull, sc_points)
    interm2 = ensure_intermediate_swings(df_sym, points_with_choch_sc)
    all_points = merge_struct_points(points_with_choch_sc, interm2)
    all_points.sort(key=lambda x: x["pos"])

    print(f"Total structural points after CHOCH + SC + intermediates: {len(all_points)}")

    # 6) Body-Filter anwenden
    all_points = apply_body_filter(df_sym, all_points)

    # 7) Temporäre Klassifikation für LH/HL-Refinement
    df_tmp1 = classify_swings(df_sym, all_points)

    # 8) LH/HL mit Pivot-Regel verfeinern
    all_points = refine_LH_HL_with_pivot(df_sym, all_points, df_tmp1, min_swing_price)

    # 9) erneute Klassifikation nach LH/HL-Refinement
    df_tmp2 = classify_swings(df_sym, all_points)

    # 10) LL/HH-Merge: keine LL-LL / HH-HH ohne LH/HL dazwischen
    all_points = merge_consecutive_extremes(df_sym, all_points, df_tmp2)

    # 11) Finale Klassifikation
    df_final = classify_swings(df_sym, all_points)

    # 11b) HH/LL nur dann, wenn sie wirklich das Leg-High / Leg-Low brechen
    df_final = relabel_inside_legs(df_final, all_points)

    # 11c) Single-Counter-Engulfing-Overrides (HL/LH explizit freischalten)
    df_final = apply_counter_engulf_override(df_final, all_points)

    # 12) BOS
    df_final = detect_bos(df_final, all_points)

    # 13) Speichern
    print(f"Saving to {output_file} ...")
    df_final.to_csv(output_file, index=True)
    print(f"Done for {symbol}.\n")


# ---------------------------------
# MAIN
# ---------------------------------

def main():
    for sym in SYMBOLS:
        run_phase1_for_symbol(sym)


if __name__ == "__main__":
    print("Entering main() ...")
    try:
        main()
    except Exception:
        import traceback
        print("ERROR in phase1_structure_bos.py:")
        traceback.print_exc()