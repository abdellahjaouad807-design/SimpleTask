"""Tests des critères d'acceptation (section 8 du cahier des charges).

Lancer :  python -m unittest tests.test_acceptance -v
Les données de test vont dans un dossier temporaire (rien n'est touché dans %APPDATA%)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix="simpletask_test_")
os.environ["SIMPLETASK_DATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simpletask import actions, config, safety  # noqa: E402
from simpletask.base import KnowledgeBase  # noqa: E402
from simpletask.scanner import Scanner  # noqa: E402
from simpletask.signatures import SignatureChecker  # noqa: E402
from simpletask.ui import ram_candidates  # noqa: E402


def wait_for(cond, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        r = cond()
        if r:
            return r
        time.sleep(0.5)
    return None


class Acceptance(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TMP, ignore_errors=True)

    def test_1_liste_avec_categories(self):
        kb = KnowledgeBase()
        self.assertGreaterEqual(len(kb.entries), 200)
        groups, _ = Scanner().scan(30)
        names = {g.name.lower() for g in groups}
        self.assertIn("explorer.exe", names)
        self.assertEqual(kb.get("explorer.exe")["categorie"], "vital")
        self.assertTrue(kb.get("explorer.exe")["description"])

    def test_2_et_3_enregistrement_unique_et_persistant(self):
        kb = KnowledgeBase()
        self.assertTrue(kb.observe("MonOutilInconnu.exe", r"C:\Outils\MonOutilInconnu.exe", True))
        self.assertFalse(kb.observe("monoutilinconnu.exe", None, False))
        self.assertFalse(kb.observe("MonOutilInconnu.exe", None, True))
        n = sum(1 for k in kb.entries if k == "monoutilinconnu.exe")
        self.assertEqual(n, 1)
        e = kb.get("MonOutilInconnu.exe")
        self.assertEqual((e["categorie"], e["source"], e["nb_vues"]), ("inconnu", "auto", 2))
        self.assertEqual(e["chemin"], r"C:\Outils\MonOutilInconnu.exe")
        kb.save(force=True)
        kb2 = KnowledgeBase()  # « réouverture » de l'application
        self.assertEqual(kb2.get("monoutilinconnu.exe")["nb_vues"], 2)

    def test_4_export_import(self):
        kb = KnowledgeBase()
        kb.observe("OutilExport.exe", r"C:\X\OutilExport.exe")
        out = os.path.join(_TMP, "export.txt")
        n = kb.export_unknowns(out)
        self.assertGreaterEqual(n, 1)
        with open(out, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("OutilExport.exe", text)
        # Réponse simulée de Claude, entourée de texte et de ```json
        reply = [{"nom": "OutilExport.exe", "description": "Petit outil de test.",
                  "categorie": "peut_etre_ferme", "risque": "aucun", "editeur": "Moi"},
                 {"nom": "Mauvais.exe", "categorie": "n'importe quoi"}]
        inp = os.path.join(_TMP, "reponse.txt")
        with open(inp, "w", encoding="utf-8") as f:
            f.write("Voici :\n```json\n" + json.dumps(reply, ensure_ascii=False) + "\n```\n")
        ok, ignored = kb.import_file(inp)
        self.assertEqual((ok, ignored), (1, 1))
        e = KnowledgeBase().get("outilexport.exe")
        self.assertEqual((e["categorie"], e["source"], e["description"]),
                         ("peut_etre_ferme", "utilisateur", "Petit outil de test."))
        self.assertTrue(list(config.BACKUP_DIR.glob("base_*_import.json")))

    def test_5_vital_jamais_fermable(self):
        for name in ("csrss.exe", "lsass.exe", "explorer.exe", "System", "svchost.exe"):
            self.assertFalse(actions.can_close(name, "peut_etre_ferme")[0], name)
        self.assertFalse(actions.can_close("RtkAudUService64.exe", "vital")[0])
        with self.assertRaises(actions.Refused):
            actions.close_pids("csrss.exe", "vital", [4242], set())
        with self.assertRaises(actions.Refused):
            actions.close_pids("Truc.exe", "vital", [4242], set())

    def test_6_liberer_ram(self):
        def row(name, cat, shown=None, white=False, me=False, ram=500):
            return SimpleNamespace(g=SimpleNamespace(name=name, ram=ram * 1048576),
                                   category=cat, shown_cat=shown or cat, whitelisted=white,
                                   is_self=me, entry={})
        rows = [row("chrome.exe", "peut_etre_ferme"),
                row("Discord.exe", "peut_etre_ferme", white=True),
                row("explorer.exe", "peut_etre_ferme"),      # protégé en dur
                row("NVDisplay.Container.exe", "vital"),
                row("Inconnu.exe", "inconnu"),
                row("Faux.exe", "peut_etre_ferme", shown="suspect"),
                row("SimpleTask.exe", "peut_etre_ferme", me=True)]
        self.assertEqual([r.g.name for r in ram_candidates(rows)], ["chrome.exe"])

    def test_6b_fermeture_reelle(self):
        p = subprocess.Popen(["ping", "-n", "60", "127.0.0.1"],
                             stdout=subprocess.DEVNULL, creationflags=0x08000000)
        time.sleep(0.5)
        closed, denied = actions.close_pids("PING.EXE", "inconnu", [p.pid], set())
        self.assertEqual((closed, denied), (1, 0))
        self.assertIsNotNone(p.poll())

    def test_6c_processus_administrateur_refuse(self):
        """Cas réel : nvsphelper64.exe (lancé en administrateur) refuse terminate() ET
        l'observation. close_pids doit répondre « refusé », sans lever d'erreur."""
        from unittest import mock

        class AdminProc:
            pid = 3852

            def name(self):
                return "nvsphelper64.exe"

            def terminate(self):
                raise actions.psutil.AccessDenied(self.pid, "nvsphelper64.exe")

            def is_running(self):
                return True

            def status(self):
                raise actions.psutil.AccessDenied(self.pid, "nvsphelper64.exe")

        with mock.patch.object(actions.psutil, "Process", lambda pid: AdminProc()), \
                mock.patch.object(actions, "_post_close_to_windows", lambda pids: False), \
                mock.patch.object(actions.psutil, "pid_exists", lambda pid: True):
            self.assertEqual(actions.close_pids("nvsphelper64.exe", "peut_etre_ferme",
                                                [3852], set()), (0, 1))

    def test_7_faux_svchost(self):
        self.assertEqual(safety.impersonated_system_name("svch0st.exe"), "svchost.exe")
        self.assertEqual(safety.impersonated_system_name("scvhost.exe"), "svchost.exe")
        self.assertIsNone(safety.impersonated_system_name("chrome.exe"))
        # Autres signes : non signé dans Temp, CPU élevé et constant sans application connue
        tmp_exe = os.path.join(os.environ["TEMP"], "truc.exe")
        self.assertTrue(safety.suspect_reasons("truc.exe", tmp_exe, "non_signe", False, False))
        self.assertFalse(safety.suspect_reasons("truc.exe", tmp_exe, "signe", False, False))
        self.assertTrue(safety.suspect_reasons("x.exe", r"C:\X\x.exe", "non_signe", False, True))
        self.assertFalse(safety.suspect_reasons("jeu.exe", r"C:\Jeux\jeu.exe", "signe", False, True))
        # Un vrai faux svchost.exe lancé depuis le dossier Temp
        d = tempfile.mkdtemp(prefix="faux_", dir=_TMP)
        fake = os.path.join(d, "svchost.exe")
        shutil.copy(os.path.join(os.environ["SystemRoot"], "System32", "PING.EXE"), fake)
        p = subprocess.Popen([fake, "-n", "60", "127.0.0.1"], stdout=subprocess.DEVNULL,
                             creationflags=0x08000000)
        try:
            time.sleep(1)
            groups, _ = Scanner().scan(30)
            g = next(g for g in groups if p.pid in g.pids)
            self.assertEqual(os.path.normcase(g.path), os.path.normcase(fake))
            reasons = safety.suspect_reasons(g.name, g.path, "", True, False)
            self.assertTrue(any("bon endroit" in r for r in reasons), reasons)
            # Le vrai svchost (System32) n'est pas suspect
            real = os.path.join(os.environ["SystemRoot"], "System32", "svchost.exe")
            self.assertEqual(safety.suspect_reasons("svchost.exe", real, "signe", True, False), [])
            # Signature : la copie de PING.EXE n'a pas de signature intégrée
            sig = SignatureChecker()
            info = wait_for(lambda: sig.lookup(fake))
            self.assertIsNotNone(info, "vérification de signature trop lente")
            real_info = wait_for(lambda: sig.lookup(real))
            self.assertEqual(real_info["signature"], "signe")
        finally:
            p.kill()
            p.wait()


if __name__ == "__main__":
    unittest.main(verbosity=2)
