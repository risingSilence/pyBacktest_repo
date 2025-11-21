from __future__ import annotations
import json
import re
from pathlib import Path
from typing import List, Tuple, Dict

import pandas as pd
from pandas.api.types import is_datetime64tz_dtype

# ------------------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------------------
SYMBOL = "EURUSD"

# Wir ermitteln den Pfad, in dem dieses Skript liegt (D:\pyBacktest\charting)
SCRIPT_DIR = Path(__file__).resolve().parent

# Input: Die CSV liegt im selben Ordner wie das Skript
DATA_DIR = SCRIPT_DIR

# Output: data.json soll ebenfalls in diesen Ordner
OUT_PATH = SCRIPT_DIR / "data.json"

# Patterns (nicht mehr zwingend nötig für den Single File Load, aber stört nicht)
FILENAME_PATTERN = re.compile(r"^(?P<symbol>[A-Z0-9]+)_(?P<year>\d{4})_M1\.csv$")

# ------------------------------------------------------------------------------
# PART 1: DATA LOADING (Logic merged from chart_data.py & app_dynamic.py)
# ------------------------------------------------------------------------------

def parse_m1_filename(path: Path) -> Tuple[str, int]:
    """Parses filename like EURUSD_2021_M1.csv."""
    name = path.name
    m = FILENAME_PATTERN.match(name)
    if not m:
        raise ValueError(f"Filename does not match pattern 'SYMBOL_YYYY_M1.csv': {name}")
    symbol = m.group("symbol")
    year = int(m.group("year"))
    return symbol, year

def load_single_m1_csv(path: Path) -> pd.DataFrame:
    """
    Loads a single M1 CSV file.
    Expected format: Local time,Open,High,Low,Close,Volume
    """
    print(f"Loading M1 file: {path.resolve()}")
    df = pd.read_csv(path)

    # Normalize columns
    col_map = {
        "Local time": "time_ny",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    df = df.rename(columns=col_map)

    if "time_ny" not in df.columns:
        raise ValueError(f"Column 'Local time' or 'time_ny' missing in {path}")

    # Parse DateTime (Day-First usually for MT5 exports: 01.02.2023)
    # Using 'coerce' to handle potential bad lines, but mostly expecting valid data
    df["time_ny"] = pd.to_datetime(df["time_ny"], dayfirst=True, errors="coerce")
    
    # Ensure timezone-naive (NY time is treated as naive here)
    if is_datetime64tz_dtype(df["time_ny"]):
        df["time_ny"] = df["time_ny"].dt.tz_localize(None)

    df = df.dropna(subset=["time_ny"])
    
    # Ensure standard OHLCV columns exist
    for col in ["open", "high", "low", "close"]:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' missing in {path}")
            
    return df

def load_m1_data(data_dir: Path, symbol: str) -> pd.DataFrame:
    """
    Smart Loader:
    Lädt die dedizierte Raw-Datei: {symbol}_M1_raw_for_json.csv aus dem Charting-Ordner.
    """
    # Dateiname wie in Phase 0a definiert
    filename = f"{symbol}_M1_raw_for_json.csv"
    
    # Versuche Pfad direkt (falls wir im Root sind und data_dir="charting" ist)
    target_file = data_dir / filename
    
    # Fallback: Falls wir das Script IM charting ordner ausführen, ist data_dir="charting" 
    # evtl. falsch relativ gesehen (charting/charting/...), daher Check auf Current Dir.
    if not target_file.exists():
        # Check ob Datei im aktuellen Verzeichnis liegt
        if Path(filename).exists():
            target_file = Path(filename)
    
    if target_file.exists():
        print(f"Loading Raw M1 file: {target_file.resolve()}")
        # Format ist Local time,Open,High,Low,Close,Volume
        # load_single_m1_csv erwartet dieses Format
        df = load_single_m1_csv(target_file)
        df = df.sort_values("time_ny").reset_index(drop=True)
        print(f"Loaded single file: {len(df)} rows.")
        return df

    raise FileNotFoundError(f"Raw M1 file not found: {target_file} (checked CWD too)")

# ------------------------------------------------------------------------------
# PART 2: TIMEFRAME RESAMPLING (Logic from app_dynamic.py)
# ------------------------------------------------------------------------------

def make_tf_df(df_m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """
    Resamples M1 data into higher timeframes (M5, H1, H4, D, W, M).
    Handles FX specific logic (17:00 NY rollover).
    """
    # Prepare DataFrame for resampling
    df = df_m1.copy()
    df = df.set_index("time_ny").sort_index()

    # Aggregation rules
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in df.columns:
        agg["volume"] = "sum"

    # --- Resampling Logic ---
    # Standard Intraday
    intraday_rules = {
        "M1": "1min",
        "M3": "3min",
        "M5": "5min",
        "M15": "15min",
        "H1": "1H",
    }

    if tf in intraday_rules:
        rule = intraday_rules[tf]
        df_res = (
            df.resample(rule)
              .agg(agg)
              .dropna(subset=["open", "high", "low", "close"])
              .reset_index()
        )

    # Special Cases: 17:00 NY Rollover
    elif tf == "H4":
        # 4H candles starting at 17:00, 21:00, 01:00...
        shift = pd.Timedelta(hours=17)
        df_shift = df.copy()
        df_shift.index = df_shift.index - shift # Shift back to align 17:00 to 00:00
        
        df_res = (
            df_shift.resample("4H")
                    .agg(agg)
                    .dropna(subset=["open", "high", "low", "close"])
                    .reset_index()
        )
        df_res["time_ny"] = df_res["time_ny"] + shift # Shift forward for label

    elif tf == "D":
        # Daily: 17:00 -> 16:59 next day
        shift = pd.Timedelta(hours=17)
        df_shift = df.copy()
        df_shift.index = df_shift.index - shift

        df_res = (
            df_shift.resample("1D")
                    .agg(agg)
                    .dropna(subset=["open", "high", "low", "close"])
                    .reset_index()
        )
        df_res["time_ny"] = df_res["time_ny"] + shift

    elif tf == "W":
        # Weekly: Sunday 17:00 -> Friday 16:59
        shift = pd.Timedelta(hours=17)
        df_shift = df.copy()
        df_shift.index = df_shift.index - shift

        df_res = (
            df_shift.resample("W-FRI") # Pandas week ending Friday
                    .agg(agg)
                    .dropna(subset=["open", "high", "low", "close"])
                    .reset_index()
        )
        df_res["time_ny"] = df_res["time_ny"] + shift

    elif tf == "M":
        # Monthly: Shift +7h to include Sunday 17:00 of previous month into current month
        shift = pd.Timedelta(hours=7)
        df_shift = df.copy()
        df_shift.index = df_shift.index + shift

        df_res = (
            df_shift.resample("MS") # Month Start
                    .agg(agg)
                    .dropna(subset=["open", "high", "low", "close"])
                    .reset_index()
        )
        df_res["time_ny"] = df_res["time_ny"] - shift

    else:
        raise ValueError(f"Unknown Timeframe: {tf}")

    # Add Integer Index for Viewer (x-axis)
    df_res["bar_index"] = range(len(df_res))
    
    return df_res

# ------------------------------------------------------------------------------
# PART 3: JSON BUILDING (Logic from build_data_json.py)
# ------------------------------------------------------------------------------

def generate_json_payload(dfs_by_tf: Dict[str, pd.DataFrame]) -> dict:
    """Converts DataFrames to the specific JSON structure required by index.html."""
    payload = {
        "symbol": SYMBOL,
        "timeframes": {},
    }

    for tf, df_tf in dfs_by_tf.items():
        if df_tf is None or df_tf.empty:
            print(f"{tf}: Skipped (no data)")
            continue

        total_rows = len(df_tf)
        print(f"{tf}: Exporting {total_rows} bars...")

        bars = []
        # Using itertuples for performance
        for row in df_tf.itertuples(index=False):
            # Safe volume retrieval
            vol = getattr(row, "volume", 0.0)
            if pd.isna(vol): vol = 0.0

            bars.append({
                "i": int(row.bar_index),
                "t": row.time_ny.isoformat(), # ISO string for JS parsing
                "o": float(row.open),
                "h": float(row.high),
                "l": float(row.low),
                "c": float(row.close),
                "v": float(vol),
            })

        payload["timeframes"][tf] = {"bars": bars}
        print(f"{tf}: Done.")
    
    return payload

def main():
    print("--- Starting Data Generation ---")
    
    # 1. Load Base Data (M1)
    try:
        df_m1 = load_m1_data(DATA_DIR, SYMBOL)
    except Exception as e:
        print(f"CRITICAL ERROR: Could not load M1 data. {e}")
        return

    if df_m1.empty:
        print("M1 DataFrame is empty. Exiting.")
        return

    # 2. Generate Timeframes
    # List of TFs to generate
    tf_list = ["M1", "M3", "M5", "M15", "H1", "H4", "D", "W", "M"]
    dfs_by_tf = {}

    print("--- Resampling Timeframes ---")
    for tf in tf_list:
        try:
            print(f"Processing {tf}...", end=" ", flush=True)
            dfs_by_tf[tf] = make_tf_df(df_m1, tf)
            print(f"OK ({len(dfs_by_tf[tf])} bars)")
        except Exception as e:
            print(f"Error: {e}")

    # 3. Build and Write JSON
    print("--- Building JSON ---")
    payload = generate_json_payload(dfs_by_tf)

    print(f"Writing to {OUT_PATH.resolve()}...")
    OUT_PATH.write_text(json.dumps(payload), encoding="utf-8")

    size_bytes = OUT_PATH.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    print(f"Success! Wrote {size_bytes:,} bytes (~{size_mb:,.2f} MB)")
    print("Timeframes included:", ", ".join(sorted(payload["timeframes"].keys())))

if __name__ == "__main__":
    main()