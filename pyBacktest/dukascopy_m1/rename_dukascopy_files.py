import os
import re

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

# Directory where the downloaded CSV files are located.
# "./" means the script searches in the same folder it is running in.
SOURCE_DIR = "./"

# Mapping: Dukascopy Name -> Target Name
# If an asset is not in this list, it will be ignored (safety).
ASSET_MAP = {
    "NZDUSD": "NZDUSD",
    "USDCAD": "USDCAD",
    "USDCHF": "USDCHF",
    "USDJPY": "USDJPY",
    "GBPJPY": "GBPJPY",
    "EURGBP": "EURGBP",
    "DOLLAR.IDXUSD": "DXY",
    "USA30.IDXUSD":  "US30",
    "USATECH.IDXUSD": "NAS100",
    "USA500.IDXUSD": "US500",
    "XAUUSD": "XAUUSD"
}

# Regex pattern to parse the Dukascopy filename format.
# Example: NZDUSD_Candlestick_1_M_BID_01.01.2021-31.12.2021.csv
# Capturing Groups:
# 1: Raw Asset Name (e.g. "NZDUSD" or "DOLLAR.IDXUSD")
# 2: Start Date Full
# 3: Start Year (We use this for the target filename)
# 4: End Date Full (Ignored, handles variable dates in 2025)
FILENAME_PATTERN = re.compile(r"^([A-Z0-9\.]+)_Candlestick_1_M_BID_(\d{2}\.\d{2}\.(\d{4}))-(\d{2}\.\d{2}\.\d{4})\.csv$")

# ---------------------------------------------------------
# EXECUTION
# ---------------------------------------------------------

def main():
    print(f"--- Starting Rename Script in '{os.path.abspath(SOURCE_DIR)}' ---")
    
    count_renamed = 0
    count_skipped = 0

    # Iterate over all files in the directory
    for filename in os.listdir(SOURCE_DIR):
        if not filename.endswith(".csv"):
            continue

        # Check if filename matches Dukascopy pattern
        match = FILENAME_PATTERN.match(filename)
        if not match:
            # File does not look like a raw Dukascopy file (maybe already renamed?)
            continue

        raw_asset = match.group(1)
        year = match.group(3)

        # Check if asset is in our whitelist/mapping
        if raw_asset in ASSET_MAP:
            target_asset = ASSET_MAP[raw_asset]
            
            # Construct new filename: {TARGET_ASSET}_{YEAR}_M1.csv
            new_filename = f"{target_asset}_{year}_M1.csv"
            
            old_path = os.path.join(SOURCE_DIR, filename)
            new_path = os.path.join(SOURCE_DIR, new_filename)

            # Prevent overwriting existing files silently
            if os.path.exists(new_path):
                print(f"[WARN] Target file already exists, skipping: {new_filename}")
                count_skipped += 1
                continue

            try:
                os.rename(old_path, new_path)
                print(f"[OK] Renamed: '{filename}' -> '{new_filename}'")
                count_renamed += 1
            except OSError as e:
                print(f"[ERROR] Could not rename '{filename}': {e}")
        else:
            # Asset recognized as Dukascopy file but not in our mapping list
            print(f"[SKIP] Asset '{raw_asset}' not in ASSET_MAP. File: {filename}")
            count_skipped += 1

    print("-" * 40)
    print(f"Finished. Renamed: {count_renamed}, Skipped/Ignored: {count_skipped}")

if __name__ == "__main__":
    main()