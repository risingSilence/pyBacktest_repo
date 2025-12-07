#!/bin/bash

# 1. In den Projektordner wechseln
cd "/Users/andre/Documents/pyBacktest_repo/pyBacktest"

# 2. Virtuelles Environment aktivieren
source venv/bin/activate

# 3. Kurze Info ausgeben
echo "------------------------------------------------"
echo "PROJECT: pyBacktest"
echo "VENV:    Aktiviert"
echo "PATH:    $(pwd)"
echo "------------------------------------------------"

# 4. Neue Shell starten, damit das Fenster offen bleibt
exec "$SHELL"
