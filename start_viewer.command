#!/bin/bash

# 1. In den Charting-Ordner wechseln
cd "/Users/andre/Documents/pyBacktest_repo/pyBacktest/charting"

# 2. Kurze Info ausgeben
echo "------------------------------------------------"
echo "PROJECT: pyBacktest Charting"
echo "PATH:    $(pwd)"
echo "URL:     http://localhost:8000"
echo "------------------------------------------------"

# 3. Browser automatisch öffnen
open "http://localhost:8000"

# 4. Python File Server starten
python3 -m http.server 8000
