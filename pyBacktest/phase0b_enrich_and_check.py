import os
import pandas as pd

# ---------------------------------
# CONFIG
# ---------------------------------

# Liste der Symbole
SYMBOLS = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"] #"NZDUSD", "USDJPY", "USDCAD", "USDCHF", "GBPJPY", "EURGBP"]

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
    for sym in SYMBOLS:
        run_phase0b_for_symbol(sym)


if __name__ == "__main__":
    main()