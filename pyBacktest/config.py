from datetime import datetime

# ----------------------------------------------------------------
# ZENTRALE KONFIGURATION FUER ZEITRAUM-FILTER
# ----------------------------------------------------------------

# Einheitlicher Zeitraum fuer alle Phasen (0 bis 3).
# Dies definiert sowohl den Download/Prep-Zeitraum als auch den Backtest-Zeitraum.
START_DATE = datetime(2021, 1, 1)
END_DATE   = datetime(2025, 11, 21)


# ----------------------------------------------------------------
# ZENTRALE PIP SIZE MAP
# ----------------------------------------------------------------

PIP_SIZE_MAP = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "AUDUSD": 0.0001,
    "NZDUSD": 0.0001,
    "USDCAD": 0.0001,
    "USDCHF": 0.0001,
    "USDJPY": 0.01,
    "GBPJPY": 0.01,
    "EURGBP": 0.0001,
    "DXY": 0.01,
    "US30": 1.0,
    "NAS100": 1.0,
    "US500": 1.0,
    "XAUUSD": 0.01,
}