import os
import pandas as pd
import json  # <--- NEU
from config import PIP_SIZE_MAP # <--- NEU (wird für Pips-Berechnung benötigt)

# ---------------------------------
# CONFIG
# ---------------------------------

# Liste der Symbole
SYMBOLS = ["EURGBP"] #"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY", "GBPJPY", "EURGBP", "DXY", "US30", "NAS100", "US500", "XAUUSD"]

# Pfade
DATA_DIR = "data"


# ---------------------------------
# LOAD & ENRICH
# ---------------------------------

def load_data(path: str) -> pd.DataFrame:
    print(f"Loading {path} ...")

    # Einfach normal laden
    df = pd.read_csv(path)

    # time_ny wieder zum Index machen (so hieß der Index im Original)
    if "time_ny" in df.columns:
        df["time_ny"] = pd.to_datetime(df["time_ny"])
        df = df.set_index("time_ny")
    else:
        # Fallback: time_utc benutzen
        if "time_utc" in df.columns:
            df["time_utc"] = pd.to_datetime(df["time_utc"])
            df = df.set_index("time_utc")
        else:
            # Wenn weder noch existiert, lassen wir den Index wie er ist
            print("Warning: no time_ny/time_utc column found, leaving index as-is.")

    return df


def add_hod_lod_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ergänzt:
    - Laufende Day-High/Day-Low-Flags (is_day_high_bar / is_day_low_bar)
    - London-High/Low-Bar-Flags (is_london_high_bar / is_london_low_bar)
    - Session-Break-Flags (has_broken_london_high / has_broken_london_low)

    Logik Day-High/Low:
    - Für jedes Symbol und jeden NY-Kalendertag (date_ny) wird ein
      laufendes Maximum der Highs (cummax) und ein laufendes Minimum
      der Lows (cummin) gebildet.
    - Jede Kerze, deren High == aktuellem Tages-Max-High entspricht,
      bekommt is_day_high_bar = True.
    - Jede Kerze, deren Low == aktuellem Tages-Min-Low entspricht,
      bekommt is_day_low_bar = True.

    Logik London-Break:
    - Pro Symbol & date_ny:
      - Von Daily-Open 17:00 NY bis vor 07:00 NY:
        has_broken_london_high = False
        has_broken_london_low  = False
      - Ab 07:00 NY bis 16:59 NY:
        - Sobald high >= london_high das erste Mal passiert:
            has_broken_london_high = True für diese und alle folgenden Kerzen
        - Sobald low <= london_low das erste Mal passiert:
            has_broken_london_low = True für diese und alle folgenden Kerzen
      - Tage ohne London-Range (has_london_range == False): überall False.
    """

    df = df.copy()

    # Sicherstellen, dass time_ny der Index ist
    if "time_ny" in df.columns:
        df["time_ny"] = pd.to_datetime(df["time_ny"])
        df = df.set_index("time_ny").sort_index()
    else:
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df.index.name = "time_ny"

    # NY-Kalendertag, falls noch nicht vorhanden
    if "date_ny" not in df.columns:
        df["date_ny"] = df.index.date

    # Gruppierung: pro Symbol und Tag
    group_cols = ["symbol", "date_ny"] if "symbol" in df.columns else ["date_ny"]

    # -----------------------------
    # Day-High/Day-Low-Flags
    # -----------------------------
    df["day_high_running"] = df.groupby(group_cols)["high"].cummax()
    df["day_low_running"] = df.groupby(group_cols)["low"].cummin()

    df["is_day_high_bar"] = df["high"] == df["day_high_running"]
    df["is_day_low_bar"] = df["low"] == df["day_low_running"]

    # Hilfsspalten wieder entfernen
    df = df.drop(columns=["day_high_running", "day_low_running"])

    # -----------------------------
    # London-High/Low-Bar-Flags (optional)
    # -----------------------------
    if {"london_high", "london_low", "is_london_session"}.issubset(df.columns):
        df["is_london_high_bar"] = (
            df["is_london_session"] & (df["high"] == df["london_high"])
        )
        df["is_london_low_bar"] = (
            df["is_london_session"] & (df["low"] == df["london_low"])
        )

    # -----------------------------
    # London-Break-Flags
    # -----------------------------
    # hour_ny/minute_ny ggf. aus Index ableiten
    if "hour_ny" not in df.columns:
        df["hour_ny"] = df.index.hour
    if "minute_ny" not in df.columns:
        df["minute_ny"] = df.index.minute

    # Default: alles False, falls wir keine London-Infos haben
    df["has_broken_london_high"] = False
    df["has_broken_london_low"] = False

    if {"london_high", "london_low", "has_london_range"}.issubset(df.columns):

        def _compute_london_breaks(g: pd.DataFrame) -> pd.DataFrame:
            """
            Wird pro (symbol, date_ny) aufgerufen.
            Setzt has_broken_london_high / has_broken_london_low entsprechend.
            """

            # Absicherung: hat dieser Tag überhaupt eine London-Range?
            has_range = g["has_london_range"].fillna(False)
            if not has_range.any():
                # Kein London-Range an diesem Tag -> alles False lassen
                g["has_broken_london_high"] = False
                g["has_broken_london_low"] = False
                return g

            hour = g["hour_ny"]

            # Nur zwischen 07:00 und vor 17:00 NY dürfen Breaks auftreten
            # (Daily Open 17:00 NY des Vortags bis < 07:00 NY = immer False)
            in_eval_window = (hour >= 7) & (hour < 17)

            # Bedingung: Kerze bricht London High / Low
            # (>= / <=, damit ein genaues Antippen auch als "gebrochen" gilt)
            cond_break_high = (
                has_range
                & in_eval_window
                & (g["high"] >= g["london_high"])
            )
            cond_break_low = (
                has_range
                & in_eval_window
                & (g["low"] <= g["london_low"])
            )

            # Running OR via cumsum:
            # False False False True True True ...
            g["has_broken_london_high"] = cond_break_high.cumsum().astype(bool)
            g["has_broken_london_low"] = cond_break_low.cumsum().astype(bool)

            return g

        df = df.groupby(group_cols, group_keys=False).apply(_compute_london_breaks)
    else:
        print("Warning: no london_high/london_low/has_london_range columns found. "
              "has_broken_london_high/low stay False.")

    return df


def save_data(df: pd.DataFrame, path: str) -> None:
    print(f"Saving enriched data to {path} ...")
    df.to_csv(path, index=True)
    print("Done.")

# ---------------------------------
# VOLATILITY RATIO CALCULATION (NY AM SESSION)
# ---------------------------------

def calculate_and_save_volatility_ratios():
    """
    Berechnet die durchschnittliche Range (High - Low) in Pips
    zwischen 08:00 und 12:00 NY Time für alle Symbole in SYMBOLS.
    Normalisiert die Werte relativ zu EURUSD (EURUSD = 1.0).
    Speichert das Ergebnis als JSON.
    """
    print("\n--- Calculating Volatility Ratios (8am - 12pm NY) ---")
    
    avg_ranges_pips = {}
    
    # 1. Durchschnittliche Ranges berechnen
    for symbol in SYMBOLS:
        # Wir nutzen die enriched files oder die phase0 files.
        # Phase0 files reichen, da wir nur High/Low/Time brauchen.
        input_filename = f"data_{symbol}_M5_phase0.csv"
        input_file = os.path.join(DATA_DIR, input_filename)
        
        if not os.path.exists(input_file):
            print(f"Skipping {symbol} for vola calc: File not found.")
            continue
            
        pip_size = PIP_SIZE_MAP.get(symbol, 0.0001)
        
        # Load data (nur notwendige Spalten für Speed)
        try:
            df = pd.read_csv(input_file, usecols=["time_ny", "high", "low"])
        except ValueError:
            # Falls time_ny nicht gefunden wird (altes Format?), komplett laden
            df = pd.read_csv(input_file)
            
        if "time_ny" not in df.columns:
            print(f"Skipping {symbol}: No 'time_ny' column.")
            continue
            
        df["time_ny"] = pd.to_datetime(df["time_ny"])
        
        # Filter: Nur 08:00 bis 11:55 (Kerzen die im 8-12 Fenster liegen)
        # Hour 8, 9, 10, 11. (12:00 ist meist die erste Kerze NACH dem Fenster)
        mask_ny_am = df["time_ny"].dt.hour.isin([8, 9, 10, 11])
        df_session = df.loc[mask_ny_am].copy()
        
        if df_session.empty:
            print(f"Warning: No NY AM data for {symbol}.")
            continue
            
        # Range in Pips
        ranges = (df_session["high"] - df_session["low"]) / pip_size
        avg_range = ranges.mean()
        
        avg_ranges_pips[symbol] = avg_range
        print(f"  {symbol}: Avg Range = {avg_range:.2f} pips")

    # 2. Ratios berechnen (Relativ zu EURUSD)
    if "EURUSD" not in avg_ranges_pips:
        print("CRITICAL: EURUSD not found in data. Cannot calculate ratios.")
        return
        
    base_vola = avg_ranges_pips["EURUSD"]
    ratios = {}
    
    for symbol, val in avg_ranges_pips.items():
        if base_vola > 0:
            r = val / base_vola
            ratios[symbol] = round(r, 4)
        else:
            ratios[symbol] = 1.0
            
    # 3. Speichern
    out_path = os.path.join(DATA_DIR, "volatility_ratios.json")
    with open(out_path, "w") as f:
        json.dump(ratios, f, indent=4)
        
    print(f"Saved volatility ratios to {out_path}")
    print(f"EURUSD Base Vola: {base_vola:.2f} pips")
    print("-" * 30)


# ---------------------------------
# LOGIC WRAPPER
# ---------------------------------

def run_phase0b_for_symbol(symbol: str):
    print(f"--- Processing Phase 0b for {symbol} ---")

    # Dateinamen dynamisch generieren
    input_filename = f"data_{symbol}_M5_phase0.csv"
    input_file = os.path.join(DATA_DIR, input_filename)

    output_filename = f"data_{symbol}_M5_phase0_enriched.csv"
    output_file = os.path.join(DATA_DIR, output_filename)

    # Check ob Input existiert
    if not os.path.exists(input_file):
        print(f"Skipping {symbol}: Input file not found ({input_file})")
        return

    # Pipeline ausführen
    df = load_data(input_file)
    df_enriched = add_hod_lod_flags(df)
    save_data(df_enriched, output_file)
    
    print(f"Done for {symbol}.\n")


# ---------------------------------
# MAIN
# ---------------------------------

def main():
    # 1. Anreichern (wie bisher)
    for sym in SYMBOLS:
        run_phase0b_for_symbol(sym)
        
    # 2. Volatilitäts-Analyse & Ratio-File erstellen
    calculate_and_save_volatility_ratios()


if __name__ == "__main__":
    main()