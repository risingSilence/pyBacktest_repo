from datetime import datetime

# ----------------------------------------------------------------
# ZENTRALE KONFIGURATION FÜR ZEITRAUM-FILTER
# ----------------------------------------------------------------

# Zeitraum für die Rohdaten-Verarbeitung (Phase 0a/0b/1)
# Sollte den vollen Umfang der M1-Daten abdecken.
START_DATE_PHASE01 = datetime(2021, 1, 1)
END_DATE_PHASE01   = datetime(2025, 11, 21)

# Zeitraum für die Backtesting-Logik (Phase 2/3)
# Definiert den Zeitraum, auf dem die Setup-Erkennung laufen soll.
START_DATE_PHASE23 = datetime(2023, 1, 1)
END_DATE_PHASE23   = datetime(2025, 11, 21)


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