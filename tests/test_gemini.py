"""Tests de l'assistant IA, sans jamais appeler Google (réponses simulées).

Lancer :  python tests\\test_gemini.py"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import urllib.error

_TMP = tempfile.mkdtemp(prefix="simpletask_ia_test_")
os.environ["SIMPLETASK_DATA"] = _TMP
os.environ.pop("GEMINI_API_KEY", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simpletask import cle_api, gemini  # noqa: E402
from simpletask.base import KnowledgeBase  # noqa: E402
from simpletask.ia_cache import IACache, prepare_items  # noqa: E402

KEY = "AIzaTEST_fake_key_0123456789abcdefghij"
CFG = dict(gemini._BASE_DEFAULTS, modele="modele-de-test", taille_lot=2, tentatives_max=3,
           pause_entre_lots_s=0, delai_attente_s=5, delai_relance_s=2, modeles_secours=[])


def result(name, **kw):
    r = {"process_name": name, "product_name": "Produit", "publisher": "Éditeur",
         "description": "Un outil de test.", "category": "Utilitaire", "confidence": "high",
         "evidence": ["éditeur signé"], "verification_needed": False,
         "identification_status": "identified"}
    r.update(kw)
    return r


def api_ok(results, wrap=False):
    text = json.dumps({"results": results}, ensure_ascii=False)
    if wrap:
        text = "```json\n" + text + "\n```"
    body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}
    return 200, json.dumps(body).encode()


def api_err(status, message="", reason="", retry=None):
    details = []
    if reason:
        details.append({"reason": reason})
    if retry:
        details.append({"retryDelay": retry})
    return status, json.dumps({"error": {"code": status, "message": message,
                                         "details": details}}).encode()


class FakeTransport:
    """Renvoie les réponses prévues dans l'ordre et mémorise les requêtes."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers),
                           "body": json.loads(body) if body else None})
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        if callable(r):
            return r(self.calls[-1])
        return r


def sent_names(call):
    text = call["body"]["contents"][0]["parts"][0]["text"]
    return [it["process_name"] for it in json.loads(text[text.index("\n[") + 1:])]


def echo(call):
    """Réponse valide pour tous les processus de la requête."""
    return api_ok([result(n) for n in sent_names(call)])


def run_job(items, transport, cfg=CFG, saved=None):
    saved = saved if saved is not None else []
    job = gemini.AnalysisJob(cfg, KEY, items, lambda fp, it, res, m: saved.append((fp, res)),
                             transport=transport, sleep=lambda s: False)
    job._run()
    return job, saved


def items(*names):
    return [{"process_name": n, "_fp": "sha256:" + n} for n in names]


class Validation(unittest.TestCase):
    def test_reponse_valide(self):
        valid, errors = gemini.validate_results({"results": [result("A.exe")]}, ["A.exe"])
        self.assertEqual(errors, [])
        self.assertEqual(valid["A.exe"]["category"], "Utilitaire")

    def test_champs_invalides_rejetes(self):
        data = {"results": [
            result("A.exe", confidence="certain"),           # hors liste
            result("B.exe", category="Jeux vidéo"),           # catégorie inconnue
            result("C.exe", verification_needed="peut-être"),
            {k: v for k, v in result("D.exe").items() if k != "description"},
            result("Pirate.exe"),                             # non demandé
            "pas un objet",
        ]}
        valid, errors = gemini.validate_results(data, ["A.exe", "B.exe", "C.exe", "D.exe"])
        self.assertEqual(valid, {})
        self.assertGreaterEqual(len(errors), 6)

    def test_normalisation(self):
        data = [result("a.EXE", category="pilote materiel", verification_needed="false",
                       description="  Texte\x00 avec\n\ncontrôle " + "x" * 600,
                       evidence="un seul indice"),
                result("a.exe")]                              # doublon
        valid, errors = gemini.validate_results(data, ["A.exe"])
        r = valid["A.exe"]
        self.assertEqual(r["category"], "Pilote matériel")
        self.assertIs(r["verification_needed"], False)
        self.assertLessEqual(len(r["description"]), 400)
        self.assertNotIn("\x00", r["description"])
        self.assertEqual(r["evidence"], ["un seul indice"])
        self.assertTrue(any("double" in e for e in errors))

    def test_inconnu_et_confiance(self):
        valid, _ = gemini.validate_results([
            result("U.exe", identification_status="unknown", confidence="high",
                   category="Windows", description=""),
            result("M.exe", confidence="medium", verification_needed=False)],
            ["U.exe", "M.exe"])
        self.assertEqual((valid["U.exe"]["category"], valid["U.exe"]["confidence"],
                          valid["U.exe"]["description"]),
                         ("Inconnu", "low", "Identification impossible"))
        self.assertTrue(valid["M.exe"]["verification_needed"])  # confiance moyenne

    def test_json_entoure_de_texte(self):
        status, raw = api_ok([result("A.exe")], wrap=True)
        data = gemini._extract_json(json.loads(raw))
        self.assertIn("results", data)

    def test_json_invalide(self):
        body = {"candidates": [{"content": {"parts": [{"text": "désolé, je ne peux pas"}]},
                                "finishReason": "STOP"}]}
        with self.assertRaises(gemini.GeminiError) as c:
            gemini._extract_json(body)
        self.assertEqual(c.exception.kind, "invalid_response")

    def test_reponse_tronquee(self):
        body = {"candidates": [{"content": {"parts": [{"text": '{"results": ['}]},
                                "finishReason": "MAX_TOKENS"}]}
        with self.assertRaises(gemini.GeminiError):
            gemini._extract_json(body)


class DonneesEnvoyees(unittest.TestCase):
    def test_aucun_chemin_ni_utilisateur(self):
        user = os.environ.get("USERNAME", "utilisateurtest")
        info = {"produit": f"Outil de {user}", "editeur": "ACME",
                "nom_lisible": r"C:\Users\x\AppData\outil.exe", "version": "1.2.3",
                "signataire": "ACME Corp", "chemin": r"C:\Users\x\outil.exe",
                "signature": "signe"}
        item = gemini.build_item(r"C:\Users\x\outil.exe", info)
        self.assertEqual(item["process_name"], "outil.exe")
        self.assertNotIn("file_description", item)      # ressemblait à un chemin
        self.assertNotIn(user.lower(), json.dumps(item).lower())
        self.assertTrue(set(item) <= set(gemini.SEND_FIELDS))

    def test_requete_ne_contient_que_les_champs_autorises(self):
        t = FakeTransport(echo)
        its = [dict(process_name="A.exe", company_name="ACME", _fp="sha256:x", _nom="A.exe")]
        run_job(its, t)
        payload = json.dumps(t.calls[0]["body"])
        self.assertNotIn("sha256", payload)
        self.assertNotIn("_nom", payload)


class ClientEtErreurs(unittest.TestCase):
    def test_cle_jamais_dans_url_ni_messages(self):
        t = FakeTransport(api_err(400, f"API key not valid: {KEY}", "API_KEY_INVALID"))
        job, _ = run_job(items("A.exe"), t)
        self.assertEqual(job.fatal.kind, "invalid_key")
        self.assertNotIn(KEY, t.calls[0]["url"])
        self.assertEqual(t.calls[0]["headers"]["x-goog-api-key"], KEY)
        self.assertNotIn(KEY, job.fatal.user_message())
        self.assertNotIn(KEY, str(job.fatal.detail))

    def test_quota_pas_de_relance(self):
        t = FakeTransport(echo, api_err(429, "Quota exceeded", retry="30s"))
        job, saved = run_job(items("A.exe", "B.exe", "C.exe", "D.exe"), t)
        self.assertEqual(job.fatal.kind, "quota")
        self.assertEqual(len(t.calls), 2)           # pas de nouvelle tentative
        self.assertEqual(len(saved), 2)             # le 1er lot est conservé
        self.assertIn("30", job.fatal.user_message())

    def test_erreur_serveur_relance_progressive(self):
        delays = []
        t = FakeTransport(api_err(503, "overloaded"), urllib.error.URLError("timed out"), echo)
        job = gemini.AnalysisJob(CFG, KEY, items("A.exe"), lambda *a: None, transport=t,
                                 sleep=lambda s: delays.append(s) or False)
        job._run()
        self.assertIsNone(job.fatal)
        self.assertEqual(delays, [2, 4])
        self.assertEqual(job.succeeded, 1)

    def test_tentatives_limitees(self):
        t = FakeTransport(urllib.error.URLError("connexion refusée"))
        job, _ = run_job(items("A.exe", "B.exe", "C.exe"), t)
        self.assertEqual(len(t.calls), 3)           # 3 tentatives, puis arrêt (pas d'Internet)
        self.assertEqual(job.fatal.kind, "network")
        self.assertTrue(job.finished)

    def test_modele_sature_bascule_sur_secours(self):
        # cas réel observé : le modèle principal répond 503 « high demand »
        def by_model(call):
            if "/models/principal:" in call["url"]:
                return api_err(503, "This model is currently experiencing high demand.")
            return echo(call)
        t = FakeTransport(by_model)
        cfg = dict(CFG, modele="principal", modeles_secours=["principal", "secours"])
        job, saved = run_job(items("A", "B", "C", "D"), t, cfg=cfg)
        self.assertIsNone(job.fatal)
        self.assertEqual(job.succeeded, 4)
        self.assertEqual(sum("/principal:" in c["url"] for c in t.calls), 3)  # 3 essais, puis
        self.assertEqual(sum("/secours:" in c["url"] for c in t.calls), 2)    # le secours garde
        self.assertTrue(any("secours" in n for n in job.notes))
        recorded = []
        gemini.AnalysisJob(cfg, KEY, items("E"), lambda fp, it, res, m: recorded.append(m),
                           transport=FakeTransport(by_model), sleep=lambda s: False)._run()
        self.assertEqual(recorded, ["secours"])       # le modèle réellement utilisé est noté

    def test_tous_les_modeles_satures_arret_rapide(self):
        t = FakeTransport(api_err(503, "high demand"))
        cfg = dict(CFG, modeles_secours=["secours"])
        job, saved = run_job(items("A", "B", "C", "D", "E", "F"), t, cfg=cfg)
        self.assertEqual(job.fatal.kind, "overloaded")
        self.assertEqual(len(t.calls), 6)           # 2 modèles × 3 essais, pas les autres lots
        self.assertIn("Réessayez", job.fatal.user_message())

    def test_quota_bascule_puis_arret(self):
        t = FakeTransport(api_err(429, "Quota exceeded"))
        job, _ = run_job(items("A"), t, cfg=dict(CFG, modeles_secours=["secours"]))
        self.assertEqual(job.fatal.kind, "quota")
        self.assertEqual(len(t.calls), 2)           # 1 essai par modèle, jamais de relance

    def test_accents_html_decodes(self):
        valid, _ = gemini.validate_results(
            [result("A.exe", description="Permet de g&eacute;rer les t&eacute;l&eacute;chargements")],
            ["A.exe"])
        self.assertEqual(valid["A.exe"]["description"], "Permet de gérer les téléchargements")

    def test_modele_indisponible(self):
        t = FakeTransport(api_err(404, "models/xyz is not found"))
        job, _ = run_job(items("A.exe"), t)
        self.assertEqual(job.fatal.kind, "model")

    def test_reponse_json_invalide_puis_valide(self):
        bad = (200, json.dumps({"candidates": [{"content": {"parts": [{"text": "{oups"}]},
                                                "finishReason": "STOP"}]}).encode())
        t = FakeTransport(bad, echo)
        job, saved = run_job(items("A.exe"), t)
        self.assertEqual(len(saved), 1)

    def test_repli_si_schema_refuse(self):
        t = FakeTransport(api_err(400, "Unknown name responseJsonSchema"), echo)
        job, saved = run_job(items("A.exe"), t)
        self.assertEqual(len(saved), 1)
        gen = t.calls[1]["body"]["generationConfig"]
        self.assertIn("responseSchema", gen)
        self.assertEqual(gen["responseSchema"]["type"], "OBJECT")

    def test_lots(self):
        t = FakeTransport(echo)
        job, saved = run_job(items("A", "B", "C", "D", "E"), t)
        self.assertEqual([len(sent_names(c)) for c in t.calls], [2, 2, 1])
        self.assertEqual(job.succeeded, 5)

    def test_annulation(self):
        t = FakeTransport(echo)
        job = gemini.AnalysisJob(dict(CFG, pause_entre_lots_s=1), KEY, items("A", "B", "C"),
                                 lambda *a: None, transport=t)
        job.cancel()
        job._run()
        self.assertEqual(job.fatal.kind, "cancelled")
        self.assertEqual(t.calls, [])

    def test_hors_ligne_et_sans_cle(self):
        with self.assertRaises(gemini.GeminiError) as c:
            gemini.GeminiClient(CFG, "")
        self.assertEqual(c.exception.kind, "no_key")
        with self.assertRaises(gemini.GeminiError) as c:
            gemini.GeminiClient(dict(CFG, active=False), KEY)
        self.assertEqual(c.exception.kind, "disabled")
        t = FakeTransport(urllib.error.URLError("getaddrinfo failed"))
        job, saved = run_job(items("A.exe"), t, cfg=dict(CFG, tentatives_max=1))
        self.assertEqual(saved, [])
        self.assertTrue(job.finished)
        # la base locale reste utilisable sans Internet
        kb = KnowledgeBase()
        self.assertEqual(kb.get("explorer.exe")["categorie"], "vital")

    def test_reponse_ia_jamais_executee(self):
        evil = result("A.exe", description="Exécutez: del C:\\Windows /s",
                      evidence=["powershell -c rm -r *"])
        t = FakeTransport(api_ok([evil]))
        job, saved = run_job(items("A.exe"), t)
        # simple texte stocké : aucun champ n'est utilisé comme commande
        self.assertEqual(saved[0][1]["description"], "Exécutez: del C:\\Windows /s")


class Cache(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=_TMP)
        self.cache = IACache(os.path.join(self.dir, "ia.json"))

    def _file(self, name, content):
        d = tempfile.mkdtemp(dir=self.dir)
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(content)
        return p

    def test_meme_nom_fichiers_differents(self):
        a = self._file("outil.exe", b"version A")
        b = self._file("outil.exe", b"version B")
        self.assertNotEqual(self.cache.fingerprint("outil.exe", a),
                            self.cache.fingerprint("outil.exe", b))
        self.assertTrue(self.cache.fingerprint("outil.exe", a).startswith("sha256:"))
        self.assertEqual(self.cache.fingerprint("outil.exe", ""), "nom:outil.exe")

    def test_fichier_modifie_reanalysable(self):
        p = self._file("outil.exe", b"v1")
        fp1 = self.cache.fingerprint("outil.exe", p)
        self.cache.put(fp1, {"process_name": "outil.exe"}, result("outil.exe"), "m")
        time.sleep(1.1)
        with open(p, "wb") as f:
            f.write(b"v2 plus longue")
        to_send, cached = prepare_items([("outil.exe", p)], lambda p: None, self.cache)
        self.assertEqual((len(to_send), cached), (1, []))

    def test_pas_de_requete_repetee_et_persistance(self):
        p = self._file("outil.exe", b"abc")
        to_send, _ = prepare_items([("outil.exe", p)], lambda p: {"editeur": "ACME"},
                                   self.cache)
        it = to_send[0]
        self.assertEqual(it["company_name"], "ACME")
        self.cache.put(it["_fp"], it, result("outil.exe"), "modele-x")
        cache2 = IACache(self.cache.path)                       # réouverture
        to_send, cached = prepare_items([("outil.exe", p)], lambda p: None, cache2)
        self.assertEqual((to_send, cached), ([], ["outil.exe"]))
        rec = cache2.get(it["_fp"])
        self.assertEqual((rec["modele"], rec["validation"]), ("modele-x", "proposee"))
        self.assertNotIn("_fp", rec["infos_techniques"])
        forced, _ = prepare_items([("outil.exe", p)], lambda p: None, cache2, force=True)
        self.assertEqual(len(forced), 1)

    def test_resultat_fichier_remplace_nom_seul(self):
        self.cache.put("nom:svc.exe", {"process_name": "svc.exe"},
                       result("svc.exe", identification_status="unknown"), "m")
        self.cache.put("sha256:abc", {"process_name": "svc.exe"}, result("svc.exe"), "m")
        self.assertIsNone(self.cache.get("nom:svc.exe"))
        self.assertEqual(len(IACache(self.cache.path).all()), 1)

    def test_validation_utilisateur_distincte(self):
        self.cache.put("sha256:z", {"process_name": "z.exe"}, result("z.exe"), "m")
        self.cache.set_validation("sha256:z", "corrigee", {"description": "Ma version"})
        rec = self.cache.get("sha256:z")
        self.assertEqual(rec["resultat"]["description"], "Un outil de test.")  # IA intacte
        self.assertEqual(rec["correction"]["description"], "Ma version")
        self.assertEqual(rec["validation"], "corrigee")

    def test_base_existante_preservee(self):
        kb = KnowledgeBase()
        kb.observe("Inconnu42.exe", r"C:\X\Inconnu42.exe")
        kb.update_entry("Inconnu42.exe", "Décrit par l'IA puis confirmé", "inconnu",
                        extra={"type": "Utilitaire", "ia": {"validation": "confirmee"}})
        e = KnowledgeBase().get("inconnu42.exe")
        self.assertEqual((e["type"], e["chemin"], e["categorie"]),
                         ("Utilitaire", r"C:\X\Inconnu42.exe", "inconnu"))


class Configuration(unittest.TestCase):
    def test_modele_dans_fichier_et_pas_de_cle(self):
        cfg = gemini.load_config()
        self.assertTrue(cfg["modele"])                        # vient de config/gemini.json
        with open(gemini.CONFIG_FILE, encoding="utf-8") as f:
            self.assertNotIn("AIza", f.read())
        gemini.save_config(dict(cfg, modele="autre-modele", taille_lot=99))
        cfg2 = gemini.load_config()
        self.assertEqual((cfg2["modele"], cfg2["taille_lot"]), ("autre-modele", 25))

    def test_migration_ancienne_configuration(self):
        old = {"active": False, "modele": "ancien-modele-sature", "taille_lot": 8}
        with open(gemini.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(old, f)
        cfg = gemini.load_config()
        self.assertNotEqual(cfg["modele"], "ancien-modele-sature")
        self.assertTrue(cfg["modeles_secours"])
        self.assertIs(cfg["active"], False)          # le choix de l'utilisateur est gardé
        gemini.save_config(dict(cfg, modele="mon-choix"))
        self.assertEqual(gemini.load_config()["modele"], "mon-choix")  # pas de re-migration

    def test_modele_absent_du_code(self):
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "simpletask", "gemini.py")
        with open(src, encoding="utf-8") as f:
            code = f.read()
        self.assertNotIn("gemini-flash", code)
        self.assertNotIn("gemini-2", code)

    def test_gestionnaire_identification(self):
        target = "SimpleTask/TestUnitaire"
        cle_api.store("cle-de-test-123456", target)
        try:
            self.assertEqual(cle_api.read_stored(target), "cle-de-test-123456")
        finally:
            cle_api.delete(target)
        self.assertEqual(cle_api.read_stored(target), "")
        self.assertNotIn("123456"[:3] + "456", cle_api.mask("cle-de-test-123456")[:-4])

    def test_variable_environnement_prioritaire(self):
        os.environ["GEMINI_API_KEY"] = "cle-env"
        try:
            self.assertEqual(cle_api.get_key(), ("cle-env", "environnement"))
        finally:
            del os.environ["GEMINI_API_KEY"]


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
