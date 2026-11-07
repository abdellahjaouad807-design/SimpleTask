"""Chemins des fichiers et réglages de l'utilisateur."""
import json
import os
from pathlib import Path

APP_NAME = "SimpleTask"
VERSION = "1.0.0"

# Toutes les données restent sur le PC, dans %APPDATA%\SimpleTask
# (variable SIMPLETASK_DATA possible pour les tests).
DATA_DIR = Path(os.environ.get("SIMPLETASK_DATA")
                or Path(os.environ.get("APPDATA", Path.home())) / APP_NAME)
BASE_FILE = DATA_DIR / "base.json"
JOURNAL_FILE = DATA_DIR / "journal.json"
SETTINGS_FILE = DATA_DIR / "reglages.json"
SIGNATURES_FILE = DATA_DIR / "signatures.json"
BACKUP_DIR = DATA_DIR / "sauvegardes"

DEFAULT_SETTINGS = {
    "rafraichissement_s": 2,     # intervalle de mise à jour de la liste
    "seuil_cpu": 10.0,           # badge « Gourmand » au-delà de ce % de CPU
    "seuil_ram_mo": 500,         # ... ou de ce nombre de Mo de RAM
    "suspect_cpu": 30.0,         # inconnu qui dépasse ce % de CPU...
    "suspect_duree_s": 60,       # ... pendant cette durée => Suspect
    "theme": "sombre",           # "sombre" ou "clair"
    "liste_blanche": [],         # noms (en minuscules) jamais proposés à la fermeture
}


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    """Écriture atomique : on écrit un fichier temporaire puis on le renomme."""
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    s.update(read_json(SETTINGS_FILE, {}))
    s["liste_blanche"] = [n.lower() for n in s.get("liste_blanche", [])]
    return s


def save_settings(s):
    ensure_dirs()
    write_json(SETTINGS_FILE, s)
