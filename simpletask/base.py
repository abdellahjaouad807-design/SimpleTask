"""Base de connaissances : un seul fichier JSON local qui grandit tout seul."""
import json
import shutil
import time
from datetime import datetime

from . import config
from .seed import load_seed

CATEGORIES = ("vital", "peut_etre_ferme", "inconnu")
RISQUES = ("aucun", "faible", "eleve")
MAX_BACKUPS = 15
SAVE_DELAY_S = 15  # les mises à jour « dernière vue » sont regroupées


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class KnowledgeBase:
    def __init__(self, path=None):
        self.path = path or config.BASE_FILE
        config.ensure_dirs()
        data = config.read_json(self.path, None)
        self.entries = {}
        if isinstance(data, dict):
            for e in data.get("processus", []):
                if e.get("nom"):
                    self.entries[e["nom"].lower()] = e
        # Ajoute les entrées de la base initiale qui manquent (premier lancement
        # ou nouvelle version), sans jamais écraser ce qui existe déjà.
        added = 0
        for e in load_seed():
            old = self.entries.get(e["nom"].lower())
            if old is None:
                self.entries[e["nom"].lower()] = e
                added += 1
            elif old.get("source") == "auto" and old.get("categorie") == "inconnu":
                # enregistré automatiquement avant d'être ajouté à la base initiale :
                # on prend la description livrée et on garde l'historique (dates, chemin)
                old.update(e)
                added += 1
        self._dirty = added > 0
        self._last_save = 0.0
        if self._dirty:
            self.save(force=True)

    # ---------- lecture ----------
    def get(self, name):
        return self.entries.get((name or "").lower())

    def unknowns(self):
        items = [e for e in self.entries.values() if e.get("categorie") == "inconnu"]
        items.sort(key=lambda e: (-int(e.get("nb_vues", 0)), e["nom"].lower()))
        return items

    # ---------- enregistrement automatique ----------
    def observe(self, name, path=None, new_launch=False):
        """Note qu'un processus a été vu. Crée une entrée « auto » s'il est nouveau.

        Retourne True si une entrée vient d'être créée."""
        key = name.lower()
        e = self.entries.get(key)
        ts = now_str()
        created = False
        if e is None:
            e = {
                "nom": name,
                "description": "",
                "categorie": "inconnu",
                "risque": "",
                "editeur": "",
                "source": "auto",
                "chemin": path or "",
                "signature": "",
                "premiere_vue": ts,
                "derniere_vue": ts,
                "nb_vues": 1,
            }
            self.entries[key] = e
            created = True
        else:
            if not e.get("premiere_vue"):
                e["premiere_vue"] = ts
            e["derniere_vue"] = ts
            if new_launch:
                e["nb_vues"] = int(e.get("nb_vues", 0)) + 1
            if path and not e.get("chemin"):
                e["chemin"] = path
        self._dirty = True
        return created

    def set_identity(self, name, signature, editeur):
        """Complète la signature / l'éditeur d'une entrée (sans toucher à la catégorie)."""
        e = self.get(name)
        if not e:
            return
        if signature and e.get("signature") != signature:
            e["signature"] = signature
            self._dirty = True
        if editeur and not e.get("editeur"):
            e["editeur"] = editeur
            self._dirty = True

    # ---------- modifications par l'utilisateur ----------
    def update_entry(self, name, description, categorie, risque=None, editeur=None,
                     extra=None):
        """Modification validée par l'utilisateur. extra : champs supplémentaires
        (ex. "type" et "ia" quand l'utilisateur confirme une suggestion de l'IA)."""
        if categorie not in CATEGORIES:
            raise ValueError("Catégorie invalide")
        self.backup("modification")
        e = self.get(name)
        if e is None:
            self.observe(name)
            e = self.get(name)
        e["description"] = description.strip()
        e["categorie"] = categorie
        if risque is not None:
            e["risque"] = risque
        elif not e.get("risque"):
            e["risque"] = {"vital": "eleve", "peut_etre_ferme": "aucun"}.get(categorie, "")
        if editeur is not None and editeur.strip():
            e["editeur"] = editeur.strip()
        e["source"] = "utilisateur"
        if extra:
            e.update(extra)
        self._dirty = True
        self.save(force=True)

    # ---------- export / import ----------
    def export_unknowns(self, out_path):
        items = [{
            "nom": e["nom"],
            "chemin": e.get("chemin", ""),
            "editeur": e.get("editeur", ""),
            "signature": e.get("signature", ""),
            "description": "",
            "categorie": "inconnu",
            "risque": "",
        } for e in self.unknowns()]
        text = (
            "Bonjour Claude. Voici des processus Windows que mon gestionnaire de tâches "
            "SimpleTask ne connaît pas encore.\n"
            "Pour chacun, complète :\n"
            '- "description" : une phrase courte en français simple, sans jargon ;\n'
            '- "categorie" : "vital" (Windows ou un pilote en dépend, ne jamais fermer) '
            'ou "peut_etre_ferme" (application non essentielle) ;\n'
            '- "risque" si on le ferme : "aucun", "faible" ou "eleve" ;\n'
            '- "editeur" : la société qui le publie.\n'
            'Si tu n\'es pas sûr, laisse "categorie": "inconnu".\n'
            "Réponds uniquement avec le tableau JSON complété, sans autre texte.\n\n"
            + json.dumps(items, ensure_ascii=False, indent=2) + "\n"
        )
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        return len(items)

    def import_file(self, in_path):
        """Importe des entrées complétées. Retourne (nb importées, nb ignorées)."""
        with open(in_path, "r", encoding="utf-8-sig") as f:
            text = f.read()
        items = _extract_json_list(text)
        self.backup("import")
        ok = ignored = 0
        for it in items:
            if not isinstance(it, dict) or not str(it.get("nom", "")).strip():
                ignored += 1
                continue
            cat = str(it.get("categorie", "inconnu")).strip().lower()
            if cat not in CATEGORIES:
                ignored += 1
                continue
            name = str(it["nom"]).strip()
            e = self.get(name)
            if e is None:
                self.observe(name, it.get("chemin") or None)
                e = self.get(name)
            desc = str(it.get("description", "")).strip()
            if desc:
                e["description"] = desc
            e["categorie"] = cat
            risque = str(it.get("risque", "")).strip().lower()
            if risque in RISQUES:
                e["risque"] = risque
            if str(it.get("editeur", "")).strip():
                e["editeur"] = str(it["editeur"]).strip()
            e["source"] = "utilisateur"
            ok += 1
        self._dirty = True
        self.save(force=True)
        return ok, ignored

    # ---------- sauvegarde ----------
    def save(self, force=False):
        if not self._dirty:
            return
        if not force and time.time() - self._last_save < SAVE_DELAY_S:
            return
        data = {
            "version": 1,
            "processus": sorted(self.entries.values(), key=lambda e: e["nom"].lower()),
        }
        config.write_json(self.path, data)
        self._dirty = False
        self._last_save = time.time()

    def backup(self, reason):
        """Copie de sécurité du fichier avant une modification importante."""
        self.save(force=True)
        if not self.path.exists():
            return
        config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(self.path, config.BACKUP_DIR / f"base_{stamp}_{reason}.json")
        olds = sorted(config.BACKUP_DIR.glob("base_*.json"))
        for p in olds[:-MAX_BACKUPS]:
            try:
                p.unlink()
            except OSError:
                pass


def _extract_json_list(text):
    """Accepte un tableau JSON brut, ou entouré de texte / de ```json ... ```."""
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError("Aucun tableau JSON trouvé dans le fichier.")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, list):
        raise ValueError("Le fichier doit contenir une liste d'entrées.")
    return data
