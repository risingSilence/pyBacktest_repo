import os
import zipfile
import shutil
from datetime import datetime

# KONFIGURATION
SOURCE_FOLDER = "pyBacktest"
GEM_OUTPUT_FOLDER = "pyBacktest_GEM"
EXTRA_FILE = "buildSnapshot.py"

def create_gem_folder():
    """
    Erstellt den Ordner 'pyBacktest_GEM' (Light Mode).
    Regeln:
    - Root 'data': Leer.
    - charting/data: Alles AUẞER '_signals_'.
    - charting allgemein: 
        - 'data.json' ignorieren (da generiert & riesig).
        - Andere .json Dateien BEHALTEN (z.B. Configs).
        - Keine *_raw_for_json.csv.
    """
    print(f"Erstelle Ordner-Struktur: '{GEM_OUTPUT_FOLDER}' (Light Mode)...")

    if os.path.exists(GEM_OUTPUT_FOLDER):
        print(f" -> Lösche alten Ordner '{GEM_OUTPUT_FOLDER}', um sauber zu überschreiben...")
        shutil.rmtree(GEM_OUTPUT_FOLDER)
    
    os.makedirs(GEM_OUTPUT_FOLDER, exist_ok=True)

    if os.path.exists(EXTRA_FILE):
        shutil.copy2(EXTRA_FILE, os.path.join(GEM_OUTPUT_FOLDER, EXTRA_FILE))
        print(f" -> '{EXTRA_FILE}' in Root kopiert.")

    count_files = 0
    target_base_path = os.path.join(GEM_OUTPUT_FOLDER, SOURCE_FOLDER)

    for root, dirs, files in os.walk(SOURCE_FOLDER):
        rel_path = os.path.relpath(root, SOURCE_FOLDER)
        path_parts = rel_path.split(os.sep)
        is_in_charting_tree = (len(path_parts) >= 1 and path_parts[0] == "charting")

        # 1. Globale Filter
        for junk in [".git", "__pycache__", ".idea", ".vscode"]:
            if junk in dirs:
                dirs.remove(junk)

        if rel_path == "." and "dukascopy_m1" in dirs:
            dirs.remove("dukascopy_m1")
        
        if is_in_charting_tree and "backup" in dirs:
            dirs.remove("backup")

        # 2. Spezialfall: Root 'data' -> leerer Ordner
        if rel_path == "data":
            empty_target_dir = os.path.join(target_base_path, rel_path)
            os.makedirs(empty_target_dir, exist_ok=True)
            files[:] = [] # Keine Dateien kopieren
            continue

        # 3. Dateien verarbeiten
        for file in files:
            should_include = True
            
            # Regel A: Charting Generierte Files weg
            if is_in_charting_tree:
                # NUR data.json filtern, andere JSONs behalten!
                if file == "data.json":
                    should_include = False
                if file.endswith("_raw_for_json.csv"):
                    should_include = False

            # Regel B: charting/data -> Alles außer _signals_
            is_charting_data = (
                len(path_parts) >= 2 and 
                path_parts[0] == "charting" and 
                path_parts[1] == "data"
            )
            
            if is_charting_data:
                if "_signals_" in file:
                    should_include = False

            if should_include:
                src_file_path = os.path.join(root, file)
                dest_dir = os.path.join(target_base_path, rel_path)
                dest_file_path = os.path.join(dest_dir, file)
                os.makedirs(dest_dir, exist_ok=True)
                shutil.copy2(src_file_path, dest_file_path)
                count_files += 1

    print(f"-> {count_files} Dateien in '{target_base_path}' kopiert.\n")


def create_full_zip(zip_filename):
    """
    Erstellt ein FULL Backup als Zip.
    REGELN:
    - charting/data -> LEER (nur Ordnerstruktur)
    - data -> LEER (nur Ordnerstruktur)
    - charting -> keine '_raw_for_json.csv'
    - charting -> 'data.json' ignorieren, andere JSONs behalten
    """
    print(f"Erstelle FULL Backup: '{zip_filename}'...")
    
    count_files = 0
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        
        for root, dirs, files in os.walk(SOURCE_FOLDER):
            
            rel_path = os.path.relpath(root, SOURCE_FOLDER)
            # Normalisierten Pfad für Vergleiche nutzen (Slash statt Backslash)
            rel_path_norm = rel_path.replace("\\", "/")
            path_parts = rel_path.split(os.sep)
            is_in_charting_tree = (len(path_parts) >= 1 and path_parts[0] == "charting")

            # Globale Filter
            for junk in [".git", "__pycache__", ".idea", ".vscode"]:
                if junk in dirs:
                    dirs.remove(junk)

            # ---------------------------------------------------------
            # Leere Ordner Logik für 'data' und 'charting/data'
            # ---------------------------------------------------------
            # Prüfen auf "data" (Root) ODER "charting/data"
            if rel_path_norm == "data" or rel_path_norm == "charting/data":
                # Wir fügen den Ordner explizit hinzu (damit er leer im Zip existiert)
                # ZipInfo mit Slash am Ende signalisiert Directory
                zip_dir_name = os.path.join(SOURCE_FOLDER, rel_path).replace("\\", "/") + "/"
                zifi = zipfile.ZipInfo(zip_dir_name)
                # Zeitstempel setzen (optional, aber sauberer)
                zifi.date_time = datetime.now().timetuple()[:6]
                zipf.writestr(zifi, "")
                
                # Inhalt ignorieren -> Listen leeren und continue
                files[:] = []
                dirs[:] = [] 
                continue

            # Dateien verarbeiten
            for file in files:
                should_include = True
                
                if is_in_charting_tree:
                    # NUR data.json weg
                    if file == "data.json":
                        should_include = False
                    # Keine Raw-CSV für JSON
                    if file.endswith("_raw_for_json.csv"):
                        should_include = False

                if should_include:
                    file_path = os.path.join(root, file)
                    
                    # Pfad im Zip: pyBacktest/...
                    arcname = os.path.join(SOURCE_FOLDER, rel_path, file)
                    if rel_path == ".":
                        arcname = os.path.join(SOURCE_FOLDER, file)
                    
                    zipf.write(file_path, arcname)
                    count_files += 1

        # buildSnapshot.py hinzufügen
        if os.path.exists(EXTRA_FILE):
            print(f" -> Füge '{EXTRA_FILE}' hinzu...")
            zipf.write(EXTRA_FILE, arcname=EXTRA_FILE)
            count_files += 1
        else:
            print(f"WARNUNG: '{EXTRA_FILE}' wurde nicht gefunden.")

    print(f"-> {count_files} Dateien archiviert.\n")


def create_snapshots():
    if not os.path.exists(SOURCE_FOLDER):
        print(f"FEHLER: Der Ordner '{SOURCE_FOLDER}' wurde nicht gefunden.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_full_name = f"{SOURCE_FOLDER}_FULL_{timestamp}.zip"

    print("-" * 40)
    
    # 1. GEM Ordner (Light Version)
    create_gem_folder()

    # 2. Full Version (Zip mit speziellen Filtern)
    create_full_zip(zip_full_name)

    print("-" * 40)
    print("✅ GEM-Ordner und FULL-Zip erfolgreich erstellt.")

if __name__ == "__main__":
    create_snapshots()