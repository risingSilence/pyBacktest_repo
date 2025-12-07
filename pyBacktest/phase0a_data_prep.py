import os
from datetime import datetime, timedelta

import pandas as pd

# ---------------------------------
# CONFIGURATION
# ---------------------------------

# Ordner, in dem deine M1-CSV-Dateien liegen
# Beispiel: r"D:\Dukascopy\M1"
CSV_DIR = r"./dukascopy_m1"

# Dateinamen-Template:
# Pro Jahr und Symbol eine Datei, z.B.:
#   EURUSD_2025_M1.csv  -> "{symbol}_{year}_M1.csv"
# oder EURUSD_M1_2025.csv -> "{symbol}_M1_{year}.csv"
# >> HIER auf dein echtes Pattern anpassen!
CSV_FILENAME_TEMPLATE = "{symbol}_{year}_M1.csv"

# Symbole
SYMBOLS = ["AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY", "GBPJPY", "EURGBP", "DXY", "US30", "NAS100", "US500", "XAUUSD"] #"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY", "GBPJPY", "EURGBP", "DXY", "US30", "NAS100", "US500", "XAUUSD"]

# Time period in NEW YORK TIME
try:
    from config import START_DATE, END_DATE
    START_DATE_NY = START_DATE
    END_DATE_NY = END_DATE
except ImportError:
    # Fallback, falls config.py nicht gefunden wird
    print("WARN: Dates from config.py not found, using default dates.")
    START_DATE_NY = datetime(2021, 1, 1)
    END_DATE_NY   = datetime(2025, 11, 21)

# Local time (GMT+1) -> NY (GMT-5) = -6 Stunden
LOCAL_TO_NY_OFFSET_HOURS = 6

# ---------------------------------
# LOAD M1 CSV & CONVERT TO NY TIME
# ---------------------------------

def load_m1_data_for_symbol(symbol: str,
                            start_ny: datetime,
                            end_ny: datetime) -> pd.DataFrame:
    """
    Lädt M1-CSV-Dateien für ein Symbol über mehrere Jahre,
    parst 'Local time' (z.B. '31.12.2024 23:00:00.000 GMT+0100' oder
    '15.07.2025 10:15:00.000 GMT+0200'),
    konvertiert diese lokalzeitbasierten Timestamps zuerst nach UTC und
    danach nach New York Zeit (America/New_York, inkl. korrekter DST-Übergänge),
    und filtert auf [start_ny, end_ny).

    Erwartetes CSV-Format pro Datei:
        Local time,Open,High,Low,Close,Volume
        31.12.2024 23:00:00.000 GMT+0100,1.03526,1.03526,1.03526,1.03526,0
    """
    print(f"Loading M1 CSV data for {symbol} from {start_ny.date()} to {end_ny.date()} (NY time)...")

    years = range(start_ny.year, end_ny.year + 1)
    dfs = []

    for year in years:
        filename = CSV_FILENAME_TEMPLATE.format(symbol=symbol, year=year)
        filepath = os.path.join(CSV_DIR, filename)

        if not os.path.exists(filepath):
            print(f"  [WARN] File not found for {symbol}, year {year}: {filepath}")
            continue

        print(f"  Reading {filepath} ...")
        df_year = pd.read_csv(filepath)

        if "Local time" not in df_year.columns:
            raise ValueError(f"'Local time' column not found in {filepath}")

        # Beispiel-Formate:
        # 31.12.2024 23:00:00.000 GMT+0100
        # 15.07.2025 10:15:00.000 GMT+0200
        #
        # Wir schneiden " GMT+0100"/" GMT+0200" nicht einfach weg,
        # sondern wandeln es in ein Standard-%z-Format um:
        # "31.12.2024 23:00:00.000 GMT+0100" -> "31.12.2024 23:00:00.000 +0100"
        raw = df_year["Local time"].astype(str)
        ts = raw.str.replace(" GMT", " ", regex=False)

        # Direkt nach UTC parsen:
        # - dayfirst=True, weil Format dd.mm.yyyy ...
        # - utc=True: pandas interpretiert +0100/+0200 korrekt und rechnet nach UTC
        df_year["time_utc"] = pd.to_datetime(ts, dayfirst=True, utc=True, errors="coerce")

        # ungültige Zeiten droppen
        df_year = df_year.dropna(subset=["time_utc"])

        # UTC -> New York (inkl. aller DST-Übergänge)
        time_ny_aware = df_year["time_utc"].dt.tz_convert("America/New_York")

        # Zeitzone droppen, damit wir im Rest der Pipeline mit naiven NY-Zeiten arbeiten
        df_year["time_ny"] = time_ny_aware.dt.tz_localize(None)

        # Auf gewünschten Zeitraum [start_ny, end_ny) filtern
        mask = (df_year["time_ny"] >= start_ny) & (df_year["time_ny"] < end_ny)
        df_year = df_year.loc[mask]

        if df_year.empty:
            continue

        # Spalten-Namen ins gewohnte Schema mappen
        rename_map = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "tick_volume",
        }
        for col in rename_map.keys():
            if col not in df_year.columns:
                raise ValueError(f"Column '{col}' not found in {filepath}")

        df_year = df_year.rename(columns=rename_map)

        # Index = NY-Zeit
        df_year = df_year.set_index("time_ny").sort_index()
        df_year.index.name = "time_ny"

        # Nur relevante Spalten behalten
        df_year = df_year[["open", "high", "low", "close", "tick_volume"]]

        dfs.append(df_year)

    if not dfs:
        raise RuntimeError(f"No M1 CSV data found for {symbol} in years {list(years)}")

    df_m1 = pd.concat(dfs).sort_index()

    # Doppelte Time-Indexe raus (falls sich Jahre überlappen)
    df_m1 = df_m1[~df_m1.index.duplicated(keep="first")]

    print(f"  Loaded {len(df_m1)} M1 bars for {symbol} after time filtering.")
    return df_m1



# ---------------------------------
# M1 -> M5 AGGREGATION
# ---------------------------------

def aggregate_m1_to_m5(df_m1: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregiert M1-Bars zu M5-Bars:
      - open: first
      - high: max
      - low: min
      - close: last
      - tick_volume: sum

    Zeitachse:
      - Index = time_ny (NY-Zeit, naiv)
      - KEINE separate time_server-Spalte mehr.

    spread und real_volume werden auf 0 gesetzt, um das alte Schema grob
    beizubehalten.
    """
    if df_m1.empty:
        raise ValueError("df_m1 is empty in aggregate_m1_to_m5")

    agg_dict = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "tick_volume": "sum",
    }

    # M1 -> M5 resample
    df_m5 = df_m1.resample("5T").agg(agg_dict)

    # Zeilen ohne vollständige OHLC droppen
    df_m5 = df_m5.dropna(subset=["open", "high", "low", "close"])

    # spread / real_volume anlegen für Konsistenz
    df_m5["spread"] = 0
    df_m5["real_volume"] = 0

    # Index ist bereits time_ny (kommt aus df_m1.index)
    df_m5.index.name = "time_ny"

    # Spalten-Reihenfolge ohne time_server
    df_m5 = df_m5[["open", "high", "low", "close",
                   "tick_volume", "spread", "real_volume"]]

    return df_m5



# ---------------------------------
# SESSION & LEVEL LOGIC (PHASE 0)
# ---------------------------------

def add_session_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add NY-based session information and daily levels to the DataFrame.
    Assumes index is NY time (time_ny, naiv).
    """
    df = df.copy()

    df["hour_ny"] = df.index.hour
    df["minute_ny"] = df.index.minute

    # Trading-Tag: 17:00 NY des Vortags bis 16:59 des aktuellen Tages
    df["date_ny"] = df.index.date

    mask = df["hour_ny"] >= 17
    if mask.any():
        df.loc[mask, "date_ny"] = (df.index[mask] + pd.Timedelta(days=1)).date

    # London Session: 03:00–07:00 NY
    df["is_london_session"] = (
        (df["hour_ny"] >= 3) & (df["hour_ny"] < 7)
    )

    # NY Entry Window: 09:30–11:00 NY
    df["is_ny_entry_window"] = (
        ((df["hour_ny"] == 9) & (df["minute_ny"] >= 30)) |
        ((df["hour_ny"] > 9) & (df["hour_ny"] < 11))
    )

    # Day High/Low pro NY-Kalendertag
    df["day_high"] = df.groupby("date_ny")["high"].transform("max")
    df["day_low"] = df.groupby("date_ny")["low"].transform("min")

    # London High/Low zuerst nur auf London-Bars berechnen
    df["london_high_raw"] = pd.NA
    df["london_low_raw"] = pd.NA

    london_mask = df["is_london_session"]

    if london_mask.any():
        df.loc[london_mask, "london_high_raw"] = (
            df.loc[london_mask]
            .groupby("date_ny")["high"]
            .transform("max")
        )
        df.loc[london_mask, "london_low_raw"] = (
            df.loc[london_mask]
            .groupby("date_ny")["low"]
            .transform("min")
        )

    # London-Werte innerhalb des Tages ausrollen (ffill/bfill pro Tag)
    df["london_high"] = df.groupby("date_ny")["london_high_raw"].ffill().bfill()
    df["london_low"] = df.groupby("date_ny")["london_low_raw"].ffill().bfill()

    # Flag, ob an dem Tag überhaupt eine London-Range existiert
    df["has_london_range"] = df["london_high"].notna() & df["london_low"].notna()

    return df


# ---------------------------------
# PIPELINE PRO SYMBOL
# ---------------------------------

def build_symbol_dataset(symbol: str,
                         start_ny: datetime,
                         end_ny: datetime) -> pd.DataFrame:
    """
    Full pipeline for a single symbol:
    - M1-CSV-Daten laden
    - auf NY-Zeit bringen und Zeitraum filtern
    - zu M5 aggregieren
    - Session & Level Columns hinzufügen
    """
    print(f"\n=== Building dataset for {symbol} ===")
    df_m1 = load_m1_data_for_symbol(symbol, start_ny, end_ny)
    df_m5 = aggregate_m1_to_m5(df_m1)
    df_feat = add_session_columns(df_m5)
    df_feat["symbol"] = symbol
    return df_feat


# ---------------------------------
# MAIN
# ---------------------------------

def main():
    # Output-Ordner definieren
    # 1. DATA_DIR für die Phase-Pipeline (bleibt wie besprochen für Phase 0b/1)
    DATA_DIR = "data"
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    # 2. CHARTING_DIR für den direkten JSON-Input
    CHARTING_DIR = "charting"
    if not os.path.exists(CHARTING_DIR):
        os.makedirs(CHARTING_DIR)

    for symbol in SYMBOLS:
        print(f"\n=== Phase 0 for {symbol} ===")

        # 1) M1-Rohdaten laden und in NY-Zeit bringen
        df_m1 = load_m1_data_for_symbol(symbol, START_DATE_NY, END_DATE_NY)
        if df_m1.empty:
            print(f"  [WARN] No M1 data for {symbol} in range, skipping.")
            continue

        # 2) M1 -> M5 aggregieren und Session-Columns hinzufügen (für Pipeline)
        df_m5 = aggregate_m1_to_m5(df_m1)
        df_feat = add_session_columns(df_m5)
        df_feat["symbol"] = symbol

        # 2a) M5-Phase0-Output speichern -> IN DATA ORDNER (Pipeline-Basis)
        filename_m5 = f"data_{symbol}_M5_phase0.csv"
        out_m5 = os.path.join(DATA_DIR, filename_m5)
        
        df_feat.to_csv(out_m5, index=True)
        print(f"  Saved M5 phase0 file: {out_m5}")

        # 3) M1-Rohdaten als Chart-Feed speichern -> DIREKT NACH CHARTING (Neuer Name)
        df_m1_chart = df_m1.copy()

        df_m1_chart = df_m1_chart.rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "tick_volume": "Volume",
            }
        )

        # Zeit als String formatieren für CSV
        local_time_str = df_m1_chart.index.strftime("%d.%m.%Y %H:%M:%S.%f").str[:-3]
        df_m1_chart.insert(0, "Local time", local_time_str)

        # NEUER NAME: (symbol)_M1_raw_for_json.csv
        filename_m1 = f"{symbol}_M1_raw_for_json.csv"
        out_m1 = os.path.join(CHARTING_DIR, filename_m1)
        
        df_m1_chart.to_csv(out_m1, index=False)
        print(f"  Saved M1 Raw for JSON: {out_m1}")

if __name__ == "__main__":
    main()