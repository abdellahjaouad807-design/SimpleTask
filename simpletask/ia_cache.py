"""Cache local des identifications par IA (ia_cache.json).

Chaque résultat est rangé sous l'EMPREINTE du fichier (SHA-256 calculé sur ce PC et jamais
envoyé), pas sous son nom : deux fichiers de même nom mais différents sont analysés
séparément, et un fichier mis à jour peut être réanalysé.
Les suggestions de l'IA restent distinctes des validations de l'utilisateur."""
import hashlib
import os
import threading
from datetime import datetime

from . import config
from .gemini import build_item

CACHE_FILE = config.DATA_DIR / "ia_cache.json"
VALIDATIONS = ("proposee", "confirmee", "corrigee", "rejetee")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


class IACache:
    def __init__(self, path=None):
        self.path = path or CACHE_FILE
        data = config.read_json(self.path, {})
        self.records = data.get("empreintes", {}) if isinstance(data, dict) else {}
        self.index = data.get("index_fichiers", {}) if isinstance(data, dict) else {}
        self.lock = threading.Lock()
        self._prune_name_only()

    def _prune_name_only(self):
        """Un résultat obtenu sur le vrai fichier remplace celui obtenu sur le nom seul."""
        with_file = {r["process_name"].lower() for fp, r in self.records.items()
                     if fp.startswith("sha256:")}
        for fp in [fp for fp, r in self.records.items()
                   if fp.startswith("nom:") and r["process_name"].lower() in with_file
                   and r.get("validation") == "proposee"]:
            del self.records[fp]

    # ---------- identité du fichier ----------
    def fingerprint(self, name, path):
        """'sha256:…' si le fichier est lisible, sinon 'nom:…' (identité faible)."""
        if path:
            try:
                st = os.stat(path)
                key = f"{path.lower()}|{st.st_size}|{int(st.st_mtime)}"
                with self.lock:
                    fp = self.index.get(key)
                if not fp:
                    fp = "sha256:" + sha256_file(path)
                    with self.lock:
                        self.index[key] = fp
                return fp
            except OSError:
                pass
        return "nom:" + name.lower()

    # ---------- lecture ----------
    def get(self, fp):
        with self.lock:
            r = self.records.get(fp)
            return dict(r) if r else None

    def latest_for(self, name):
        """Dernière identification connue pour ce nom (affichage uniquement)."""
        n = name.lower()
        with self.lock:
            recs = [r for r in self.records.values() if r["process_name"].lower() == n]
        return max(recs, key=lambda r: r.get("date_analyse", ""), default=None)

    def latest_by_name(self):
        """{nom en minuscules: dernier enregistrement}, calculé en une passe."""
        out = {}
        with self.lock:
            for r in self.records.values():
                n = r["process_name"].lower()
                if n not in out or r.get("date_analyse", "") > out[n].get("date_analyse", ""):
                    out[n] = r
        return out

    def all(self):
        with self.lock:
            return sorted((dict(r) for r in self.records.values()),
                          key=lambda r: r.get("date_analyse", ""), reverse=True)

    # ---------- écriture ----------
    def put(self, fp, item, result, model):
        """Enregistre un résultat VALIDÉ de l'IA (statut « proposée »)."""
        rec = {
            "empreinte": fp,
            "process_name": item.get("_nom") or result["process_name"],
            "infos_techniques": {k: v for k, v in item.items() if not k.startswith("_")},
            "resultat": result,
            "date_analyse": now_str(),
            "modele": model,
            "validation": "proposee",
        }
        with self.lock:
            self.records[fp] = rec
            self._prune_name_only()
        self.save()

    def set_validation(self, fp, validation, correction=None):
        if validation not in VALIDATIONS:
            raise ValueError(validation)
        with self.lock:
            rec = self.records.get(fp)
            if not rec:
                return
            rec["validation"] = validation
            rec["date_validation"] = now_str()
            if correction is not None:
                rec["correction"] = correction
        self.save()

    def forget(self, fp):
        with self.lock:
            self.records.pop(fp, None)
        self.save()

    def save(self):
        with self.lock:
            data = {"version": 1, "empreintes": dict(self.records),
                    "index_fichiers": dict(self.index)}
        config.ensure_dirs()
        config.write_json(self.path, data)


def prepare_items(entries, sig_lookup, cache, force=False):
    """Liste les processus à envoyer. À appeler hors de l'interface (calcul d'empreintes).

    entries : copie des entrées de la base [(nom, chemin), ...].
    Retourne (à_envoyer, déjà_en_cache). sig_lookup(chemin) -> infos du fichier ou None."""
    to_send, cached = [], []
    for name, path in entries:
        if path and not os.path.isfile(path):
            path = ""
        fp = cache.fingerprint(name, path)
        if not force and cache.get(fp):
            cached.append(name)
            continue
        item = build_item(name, sig_lookup(path) if path else None)
        if not item.get("process_name"):
            continue
        item["_fp"] = fp
        item["_nom"] = name
        to_send.append(item)
    return to_send, cached
