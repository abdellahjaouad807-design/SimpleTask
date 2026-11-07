# SimpleTask
But : gestionnaire de tâches Windows simplifié et guidé (façon Gestionnaire de tâches Win 11), assistant IA Gemini facultatif pour décrire les processus inconnus.
Stack : Python, **tkinter + sv-ttk** (thème Sun Valley, pas PyQt6), psutil, Pillow (icône au build).
Lancer : `python SimpleTask.pyw`
Builder : `python build.py` → `dist\SimpleTask.exe` (onefile).
Fichiers : `simpletask/` (code), `SimpleTask.pyw` (lanceur), `build.py`, `tests/`, `README.md` (doc complète des pages).
Config : `.env` (clé Gemini, exclu de git) ; modèle dans `.env.example`.
Pièges : sans droits admin, pas de débit réseau par processus (colonne Réseau = nb de connexions).
Perf : ne redessiner que le nécessaire (survol = 2 lignes, rien quand la fenêtre est réduite).
