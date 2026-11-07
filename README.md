# SimpleTask

Gestionnaire de tâches simplifié et guidé pour Windows 10 / 11, avec un assistant IA
(Google Gemini) facultatif pour décrire les processus inconnus.

## Lancer

- **Exécutable** : `dist\SimpleTask.exe` (un seul fichier, aucune installation).
- **Depuis le code** : `pip install psutil sv-ttk` puis double-clic sur `SimpleTask.pyw`.

## Interface

Menu latéral comme le Gestionnaire de tâches de Windows 11 :

| Page | Contenu |
|---|---|
| Processus | Liste par application, pastilles de catégorie, cellules colorées selon le processeur et la mémoire, recherche, tri par clic sur les en-têtes, « Fin de tâche », « Libérer de la RAM », panneau de conseil |
| Performances | Courbes en direct du processeur et de la mémoire |
| À compléter | Processus inconnus, suggestions de l'IA, export / import pour Claude |
| Assistant IA | « Décrire les inconnus », progression, annulation, résultats, confirmer / corriger / rejeter / réanalyser |
| Journal | Ce qui a été fermé |
| Réglages | Surveillance, liste blanche, assistant IA, droits administrateur |

Thème clair / sombre (thème Sun Valley, barre de titre assortie).

- **Comme le Gestionnaire de tâches** : icônes des applications, sections « Applications »,
  « Processus en arrière-plan » et « Processus Windows » (case « Regrouper par type »),
  colonnes Processeur, Mémoire, Disque, Réseau, GPU et Moteur GPU. Clic droit sur les titres
  pour afficher ou masquer des colonnes. Sans droits administrateur, Windows ne donne pas
  le débit réseau de chaque processus : la colonne Réseau indique le nombre de connexions
  actives.
- **Fin de tâche** : bouton en haut et dans le panneau de détail, ou touche **Suppr** sur la
  ligne choisie (toujours avec confirmation ; ignorée quand on tape dans la recherche).
- **Largeur des colonnes** : glissez la séparation entre deux titres pour agrandir une
  colonne au détriment de sa voisine. Les largeurs sont mémorisées ; double-clic sur une
  séparation pour revenir aux largeurs d'origine.
- **Légèreté** : le survol ne recolore que deux lignes, les dessins sont regroupés, et rien
  n'est redessiné quand la fenêtre est réduite (utile pendant un jeu).

## Assistant IA (Gemini)

### Configurer la clé API

1. Créez une clé gratuite sur <https://aistudio.google.com/apikey>.
2. Au choix :
   - **Réglages › Assistant IA › Clé API › Enregistrer la clé** : la clé est rangée dans le
     Gestionnaire d'identification Windows (chiffré pour votre session), jamais dans un fichier ;
   - ou la variable d'environnement `GEMINI_API_KEY` (prioritaire), voir `.env.example`.
3. **Lister les modèles disponibles** puis **Tester la connexion**. Choisissez un modèle
   « flash » ou « flash-lite » (souvent inclus dans l'offre gratuite).

### Configuration (`%APPDATA%\SimpleTask\gemini.json`, sans aucun secret)

| Clé | Rôle |
|---|---|
| `active` | Active ou désactive la fonction |
| `modele` | Nom du modèle Gemini : changeable sans toucher au code |
| `api_base` | Adresse de l'API (ou de votre serveur relais) |
| `proxy_sans_cle` | `true` si `api_base` est un relais qui détient la clé |
| `taille_lot` | Processus par requête |
| `delai_attente_s` | Délai d'attente d'une réponse |
| `tentatives_max` | Tentatives en cas d'erreur réseau / serveur (délai 2 s, 4 s, 8 s…) |
| `pause_entre_lots_s` | Pause entre deux requêtes (quota) |

Valeurs par défaut : `config/gemini.json`, copié au premier lancement.

### Ce qui est envoyé à Google

Uniquement, après votre accord (une fois) et votre confirmation (à chaque analyse) :
nom du processus, produit, éditeur, description et version du fichier, signataire.
Jamais : nom d'utilisateur, chemins, documents, contenu des fichiers, lignes de commande,
mots de passe ou clés. Le bouton « Voir exactement ce qui sera envoyé » montre le contenu.

### Garde-fous

- Les réponses sont validées (champs, types, listes de valeurs, longueur) avant d'être
  enregistrées ; une réponse invalide est ignorée et le processus pourra être réanalysé.
- Les suggestions restent **séparées** des validations : elles n'entrent dans la base
  qu'après « Confirmer » ou « Corriger ».
- L'IA ne décide jamais si un processus peut être fermé : ce choix est fait par vous dans la
  fenêtre de confirmation. La détection des processus suspects reste indépendante.
- Aucune réponse n'est exécutée et aucune action (fermeture, suppression, registre, pilotes,
  droits) n'est déclenchée par l'IA.
- Cache par **empreinte SHA-256** du fichier (calculée sur le PC, jamais envoyée) :
  pas de requête répétée, mais un fichier différent ou mis à jour est réanalysable.
- Quota dépassé : arrêt immédiat sans relance, résultats conservés, message « réessayez plus
  tard ». Sans clé ou sans Internet : tout le reste fonctionne.
- La clé n'apparaît ni dans les URL (envoyée en en-tête), ni dans les messages d'erreur, ni
  dans les fichiers.

### Distribuer l'application à d'autres personnes

Une clé intégrée à un programme distribué n'est jamais secrète. Deux options :
1. chaque utilisateur saisit **sa propre clé** (fonctionnement actuel) ;
2. vous hébergez un **serveur relais** qui détient la clé et limite les requêtes, et vous
   mettez son adresse dans `api_base` avec `"proxy_sans_cle": true`.

## Données (`%APPDATA%\SimpleTask`)

| Fichier | Contenu |
|---|---|
| `base.json` | Base de connaissances (champs ajoutés par l'IA : `type`, `ia`) |
| `ia_cache.json` | Identifications de l'IA par empreinte, modèle, date, statut de validation |
| `gemini.json` | Réglages de l'assistant IA (sans clé) |
| `journal.json`, `reglages.json`, `signatures.json`, `sauvegardes\` | Comme avant |

## Organisation du code

| Fichier | Rôle |
|---|---|
| `simpletask/ui.py` | Fenêtre principale et pages |
| `simpletask/widgets.py` | Liste dessinée, courbes, menu latéral |
| `simpletask/ia_ui.py` | Page Assistant IA et ses fenêtres (accord, envoi, confirmation) |
| `simpletask/gemini.py` | Client Gemini, validation, lots, relances |
| `simpletask/ia_cache.py` | Empreintes et cache des identifications |
| `simpletask/cle_api.py` | Clé API : variable d'environnement ou Gestionnaire d'identification |
| `simpletask/scanner.py`, `base.py`, `seed.py`, `safety.py`, `signatures.py`, `actions.py` | Inchangés dans leur rôle |

## Tests et construction

```
python tests\test_acceptance.py     # critères d'acceptation du cahier des charges
python tests\test_gemini.py         # IA : validation JSON, cache, erreurs, hors ligne (réponses simulées)
python build.py                     # construit dist\SimpleTask.exe (pyinstaller, pillow)
```

Les tests de l'IA n'appellent jamais Google : aucun quota n'est consommé.
