#!/bin/bash

# Stop execution if any command fails
set -e

echo "[INFO] Installing dependencies..."
pip install -r requirements.txt

echo "[INFO] Running WebScraper.py..."
python Scripts/WebScraper.py

echo "[INFO] Running Sortino.py..."
python Scripts/Sortino.py

echo "[SUCCESS] All scripts completed."
