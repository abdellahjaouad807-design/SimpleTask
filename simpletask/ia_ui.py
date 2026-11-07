"""Page « Assistant IA » : description des processus inconnus par Gemini.

L'IA PROPOSE, l'utilisateur DÉCIDE : aucune réponse ne modifie la base sans validation,
et aucune action (fermeture, suppression...) n'est jamais déclenchée par l'IA."""
import json
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import cle_api, config, gemini
from .ia_cache import prepare_items
from .ui import Dialog, Page
from .widgets import FlatButton, Table, follow_width

CONF = {
    "high": ("Confiance élevée", "ok",
             "Identification probable. Vous pouvez la vérifier avant de la confirmer."),
    "medium": ("Confiance moyenne", "warn", "Identification à confirmer."),
    "low": ("Confiance faible", "danger", "Résultat incertain : vérifiez-le vous-même."),
}
UNKNOWN = ("Non identifié", "muted", "Aucune identification fiable n'a été possible.")
VALIDATION = {
    "proposee": ("Suggestion IA", "ia"),
    "confirmee": ("Confirmée", "ok"),
    "corrigee": ("Corrigée", "accent"),
    "rejetee": ("Rejetée", "muted"),
}


def conf_info(res):
    if res.get("identification_status") == "unknown":
        return UNKNOWN
    return CONF[res["confidence"]]


class IAPage(Page):
    def __init__(self, app):
        super().__init__(app, "Assistant IA",
                         "Gemini propose une description des processus inconnus. Ce sont des "
                         "suggestions : c'est vous qui les confirmez ou les corrigez.")
        P = app.px
        self.job = None
        self.b_run = FlatButton(self.top, app,text="✦ Décrire les inconnus", style="Accent.TButton",
                                command=lambda: self.start_analysis())
        self.b_run.pack(side="right")
        self.b_cancel = FlatButton(self.top, app,text="Annuler", command=self.cancel)
        self.b_cancel.pack(side="right", padx=P(8))
        self.b_cancel.state(["disabled"])

        st = app.themed(tk.Frame(self.body), "bg")
        st.pack(fill="x", pady=(0, P(8)))
        self.state_lbl = app.label(st, "", fg="muted", font=app.font_small)
        self.state_lbl.pack(side="left")
        self.b_config = FlatButton(st, app,text="Configurer…",
                                   command=lambda: app.show_page("settings"))
        prog = app.themed(tk.Frame(self.body), "bg")
        prog.pack(fill="x", pady=(0, P(8)))
        self.progress = ttk.Progressbar(prog, maximum=1, value=0)
        self.progress.pack(fill="x")
        self.prog_lbl = app.label(prog, "", font=app.font_small)
        self.prog_lbl.pack(anchor="w", pady=(P(4), 0))

        self.table = Table(self.body, app, [
            {"key": "nom", "title": "Processus", "width": 210, "kind": "name"},
            {"key": "produit", "title": "Logiciel", "width": 170},
            {"key": "desc", "title": "Description proposée", "width": 420, "stretch": True},
            {"key": "cat", "title": "Catégorie", "width": 140},
            {"key": "conf", "title": "Confiance (estimation)", "width": 190, "kind": "pill"},
            {"key": "valid", "title": "Statut", "width": 170, "kind": "pill"},
        ], on_select=lambda rid: self.render_detail(), on_double=lambda rid: self.confirm(),
            empty_text="Aucune identification pour l'instant.\nCliquez sur « Décrire les "
                       "inconnus » pour demander à Gemini de décrire les processus inconnus.",
            name="ia")
        self.table.pack(fill="both", expand=True)

        d = self.detail = app.themed(tk.Frame(self.body), "bg")
        d.pack(fill="x", pady=(P(10), 0))
        self.d_title = app.label(d, "", font=app.font_h2)
        self.d_title.pack(anchor="w")
        self.d_conf = app.label(d, "", font=app.font_bold)
        self.d_conf.pack(anchor="w")
        self.d_desc = app.label(d, "")
        self.d_desc.pack(anchor="w", pady=(P(2), 0))
        self.d_info = app.label(d, "", fg="muted", font=app.font_small)
        self.d_info.pack(anchor="w", pady=(P(4), P(6)))
        btns = app.themed(tk.Frame(d), "bg")
        btns.pack(anchor="w")
        self.b_confirm = FlatButton(btns, app,text="Confirmer…", style="Accent.TButton",
                                    command=self.confirm)
        self.b_fix = FlatButton(btns, app,text="Corriger…", command=lambda: self.confirm(True))
        self.b_reject = FlatButton(btns, app,text="Rejeter", command=self.reject)
        self.b_again = FlatButton(btns, app,text="Réanalyser", command=self.reanalyze)
        for b in (self.b_confirm, self.b_fix, self.b_reject, self.b_again):
            b.pack(side="left", padx=(0, P(8)))
        self.disclaimer = app.label(d, (
            "Les niveaux de confiance sont une estimation donnée par l'IA, pas une probabilité "
            "vérifiée. Une suggestion de l'IA ne rend jamais un processus « sûr » ou "
            "« dangereux » : la détection des processus suspects de SimpleTask reste séparée, "
            "et l'IA ne déclenche jamais aucune action."), fg="faint", font=app.font_small)
        self.disclaimer.pack(anchor="w", pady=(P(8), 0))

        follow_width(d, [self.d_conf, self.d_desc, self.d_info, self.disclaimer])

    # ---------- affichage ----------
    def apply_theme(self):
        self.table.apply_theme()
        self.render()

    def on_show(self):
        self.render_state()
        self.render()

    def render_state(self):
        cfg = self.app.ia_cfg
        key, src = cle_api.get_key()
        if not cfg["active"]:
            txt, ok = "L'assistant IA est désactivé (Réglages).", False
        elif not key and not cfg.get("proxy_sans_cle"):
            txt, ok = ("Aucune clé API Gemini : l'assistant est indisponible. Le reste de "
                       "SimpleTask fonctionne normalement."), False
        elif not cfg["modele"]:
            txt, ok = "Aucun modèle Gemini n'est configuré (Réglages).", False
        else:
            where = {"environnement": "variable GEMINI_API_KEY",
                     "windows": "Gestionnaire d'identification Windows"}.get(src, "serveur relais")
            txt, ok = f"Prêt · modèle {cfg['modele']} · clé : {where}", True
        self.state_lbl.configure(text=txt, fg=self.app.pal["muted" if ok else "warn"])
        if ok:
            self.b_config.pack_forget()
        else:
            self.b_config.pack(side="left", padx=self.app.px(10))

    def render(self):
        app, p = self.app, self.app.pal
        rows = []
        for rec in app.ia_cache.all():
            res = rec["resultat"]
            label, color_key, _ = conf_info(res)
            vlabel, vcolor = VALIDATION.get(rec.get("validation"), VALIDATION["proposee"])
            shown = rec.get("correction") or res
            rows.append({
                "id": rec["empreinte"],
                "dot": p[color_key],
                "cells": {"nom": rec["process_name"], "produit": shown.get("product_name", ""),
                          "desc": shown.get("description", ""),
                          "cat": shown.get("category", ""), "conf": "", "valid": ""},
                "pill": {"conf": (label, p[color_key]), "valid": (vlabel, p[vcolor])},
                "fg": {"desc": p["muted"]} if rec.get("validation") == "rejetee" else {},
            })
        self.table.set_rows(rows)
        self.render_detail()

    def selected(self):
        fp = self.table.selected
        return self.app.ia_cache.get(fp) if fp else None

    def render_detail(self):
        app, p = self.app, self.app.pal
        rec = self.selected()
        running = bool(self.job and not self.job.finished)
        if not rec:
            self.d_title.configure(text="")
            self.d_conf.configure(text="")
            self.d_desc.configure(text="")
            self.d_info.configure(text="")
            for b in (self.b_confirm, self.b_fix, self.b_reject, self.b_again):
                b.state(["disabled"])
            return
        res = rec["resultat"]
        label, color_key, sentence = conf_info(res)
        title = rec["process_name"]
        if res.get("product_name"):
            title += f"   ·   {res['product_name']}"
        self.d_title.configure(text=title)
        verif = ("Vérification recommandée." if res["verification_needed"]
                 else "Aucune vérification particulière signalée.")
        self.d_conf.configure(text=f"{label} — {sentence} {verif}", fg=p[color_key])
        desc = f"Proposition de l'IA : {res['description']}"
        if rec.get("correction"):
            desc += f"\nVotre version : {rec['correction'].get('description', '')}"
        self.d_desc.configure(text=desc)
        sent = ", ".join(f"{k} = {v}" for k, v in rec.get("infos_techniques", {}).items())
        evidence = " ; ".join(res.get("evidence") or []) or "aucun indice fourni"
        vlabel, _ = VALIDATION.get(rec.get("validation"), VALIDATION["proposee"])
        self.d_info.configure(text=(
            f"Catégorie proposée : {res['category']}   ·   Éditeur : {res.get('publisher') or '—'}"
            f"   ·   Statut : {vlabel}\n"
            f"Indices utilisés par l'IA : {evidence}\n"
            f"Informations envoyées : {sent or '—'}\n"
            f"Analysé le {rec['date_analyse']} avec le modèle {rec['modele']}   ·   "
            f"empreinte {rec['empreinte'][:19]}…"))
        for b in (self.b_confirm, self.b_fix, self.b_reject):
            b.state(["!disabled"])
        self.b_again.state(["disabled"] if running else ["!disabled"])

    # ---------- analyse ----------
    def start_analysis(self, names=None, force=False):
        app = self.app
        if self.job and not self.job.finished:
            messagebox.showinfo("Assistant IA", "Une analyse est déjà en cours.", parent=app)
            return
        cfg = app.ia_cfg = gemini.load_config()
        key, _ = cle_api.get_key()
        self.render_state()
        try:
            gemini.GeminiClient(cfg, key)  # vérifie clé, modèle et activation
        except gemini.GeminiError as e:
            messagebox.showinfo("Assistant IA indisponible",
                                e.user_message() + "\n\nLes processus inconnus restent "
                                "consultables et pourront être analysés plus tard.", parent=app)
            return
        if not app.settings.get("ia_consentement"):
            if not ConsentDialog(app).result:
                return
        if names is None:
            entries = [(e["nom"], e.get("chemin", "")) for e in app.kb.unknowns()]
        else:
            entries = [(e["nom"], e.get("chemin", ""))
                       for e in (app.kb.get(n) for n in names) if e]
        if not entries:
            messagebox.showinfo("Décrire les inconnus",
                                "Aucun processus inconnu : tous les processus rencontrés sont "
                                "déjà décrits dans la base.", parent=app)
            return
        self._busy_ui(True, "Préparation : calcul des empreintes des fichiers (sur ce PC)…")
        lookup = app.sig.lookup

        def done(result, err):
            self._busy_ui(False, "")
            if err:
                messagebox.showerror("Assistant IA", f"Préparation impossible : {err}",
                                     parent=app)
                return
            to_send, cached = result
            if not to_send:
                messagebox.showinfo(
                    "Décrire les inconnus",
                    f"Les {len(cached)} processus inconnus ont déjà été analysés : leurs "
                    "résultats sont dans la liste. Utilisez « Réanalyser » pour en refaire un.",
                    parent=app)
                return
            if RunDialog(app, to_send, cached, cfg).result:
                self._run(cfg, key, to_send)
        app._run_bg(lambda: prepare_items(entries, lookup, app.ia_cache, force), done)

    def _busy_ui(self, busy, text):
        self.b_run.state(["disabled"] if busy else ["!disabled"])
        self.prog_lbl.configure(text=text, fg=self.app.pal["fg"])

    def _run(self, cfg, key, items):
        cache = self.app.ia_cache
        self.job = gemini.AnalysisJob(cfg, key, items, on_result=cache.put)
        self.progress.configure(maximum=max(len(items), 1), value=0)
        self.b_run.state(["disabled"])
        self.b_cancel.state(["!disabled"])
        self.job.start()
        self._poll()

    def _poll(self):
        job = self.job
        if job is None:
            return
        with job.lock:
            done, total, ok, status = job.done, job.total, job.succeeded, job.status
            finished, fatal = job.finished, job.fatal
        self.progress.configure(value=done)
        self.prog_lbl.configure(
            text=f"{done} / {total} traités · {total - done} restants · {ok} décrits   —   "
                 f"{status}", fg=self.app.pal["fg"])
        self.render()
        if not finished:
            self.app.after(300, self._poll)
            return
        self.b_run.state(["!disabled"])
        self.b_cancel.state(["disabled"])
        self.app.pages["todo"].render()
        summary = f"Analyse terminée : {ok} processus décrits sur {total}."
        if fatal and fatal.kind == "cancelled":
            summary = f"Analyse annulée : {ok} processus décrits (résultats conservés)."
        notes = list(getattr(job, "notes", []))
        if notes:
            summary += f"  ·  {notes[-1]}"
        self.prog_lbl.configure(text=summary, fg=self.app.pal["fg"])
        if fatal and fatal.kind != "cancelled":
            extra = ""
            if fatal.kind in ("quota", "overloaded"):
                extra = "\n\nVous pourrez relancer « Décrire les inconnus » plus tard : " \
                        "seuls les processus restants seront envoyés."
            if notes:
                extra += "\n\n" + "\n".join(notes)
            messagebox.showwarning("Assistant IA", f"{fatal.user_message()}\n\n{summary}"
                                   + extra, parent=self.app)
        elif job.failed:
            self.prog_lbl.configure(text=summary + f"  ({job.failed} sans réponse exploitable : "
                                    f"{job.errors[0] if job.errors else 'erreur'} ; ils pourront "
                                    "être réanalysés)")

    def cancel(self):
        if self.job and not self.job.finished:
            self.job.cancel()
            self.prog_lbl.configure(text="Annulation… (la requête en cours se termine)")
            self.b_cancel.state(["disabled"])

    # ---------- validation par l'utilisateur ----------
    def confirm(self, correct=False):
        rec = self.selected()
        if rec:
            ConfirmDialog(self.app, rec, correct, on_done=self._after_validation)

    def reject(self):
        rec = self.selected()
        if not rec:
            return
        self.app.ia_cache.set_validation(rec["empreinte"], "rejetee")
        self._after_validation()

    def reanalyze(self):
        rec = self.selected()
        if rec:
            self.start_analysis([rec["process_name"]], force=True)

    def _after_validation(self):
        self.render()
        self.app.pages["todo"].render()
        self.app.pages["proc"].render_rows()


class ConsentDialog(Dialog):
    """Explication obligatoire avant le tout premier envoi."""

    def __init__(self, app):
        super().__init__(app, "Avant d'utiliser l'assistant IA")
        self.result = False
        b, P = self.body, app.px
        ttk.Label(b, text="Ce qui sera envoyé à Google", style="H2.TLabel").pack(anchor="w")
        ttk.Label(b, wraplength=P(600), justify="left", text=(
            "Pour décrire un processus inconnu, SimpleTask envoie au service Google Gemini, "
            "uniquement quand vous le demandez :\n"
            "  • le nom du processus (ex. RtkAudUService64.exe) ;\n"
            "  • le nom du produit, l'éditeur, la description et la version du fichier ;\n"
            "  • le nom de l'entreprise qui a signé le fichier, s'il existe.\n\n"
            "Ne sont JAMAIS envoyés : votre nom d'utilisateur, les chemins de vos dossiers, vos "
            "documents, le contenu des fichiers, les lignes de commande, vos mots de passe ou "
            "clés.\n\n"
            "Avec l'offre gratuite de Gemini, Google peut utiliser les données envoyées pour "
            "améliorer ses services. Les métadonnées ci-dessus ne contiennent aucune donnée "
            "personnelle, mais c'est à vous de décider.\n\n"
            "Les réponses sont des suggestions : elles ne ferment, ne suppriment et ne modifient "
            "jamais rien. Vous pourrez retirer votre accord dans les Réglages.")
        ).pack(anchor="w", pady=(P(8), P(12)))
        self.ok_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(b, text="J'ai compris et j'accepte ces envois", variable=self.ok_var,
                        command=self._toggle).pack(anchor="w")
        bf = ttk.Frame(b)
        bf.pack(fill="x", pady=(P(14), 0))
        ttk.Button(bf, text="Refuser", command=self.destroy).pack(side="right")
        self.b_ok = ttk.Button(bf, text="Accepter", style="Accent.TButton", command=self._accept)
        self.b_ok.pack(side="right", padx=P(8))
        self.b_ok.state(["disabled"])
        self.show()
        self.wait_window()

    def _toggle(self):
        self.b_ok.state(["!disabled"] if self.ok_var.get() else ["disabled"])

    def _accept(self):
        self.app.settings["ia_consentement"] = time.strftime("%Y-%m-%d %H:%M")
        config.save_settings(self.app.settings)
        self.result = True
        self.destroy()


class RunDialog(Dialog):
    """Confirmation avant chaque envoi, avec le contenu exact qui partira."""

    def __init__(self, app, items, cached, cfg):
        super().__init__(app, "Décrire les inconnus")
        self.result = False
        b, P = self.body, app.px
        size = cfg["taille_lot"]
        lots = (len(items) + size - 1) // size
        ttk.Label(b, text=f"{len(items)} processus inconnus à décrire",
                  style="H2.TLabel").pack(anchor="w")
        txt = (f"Ils seront envoyés à Google Gemini (modèle {cfg['modele']}) en {lots} "
               f"requête(s) de {size} processus au maximum.")
        if cached:
            txt += f"\n{len(cached)} processus déjà analysés ne seront pas renvoyés."
        txt += "\nVous pourrez annuler à tout moment ; les résultats obtenus seront conservés."
        ttk.Label(b, text=txt, wraplength=P(600), justify="left").pack(anchor="w",
                                                                     pady=(P(6), P(10)))
        self.preview = None
        self.items = [{k: v for k, v in it.items() if not k.startswith("_")} for it in items]
        self.b_show = ttk.Button(b, text="Voir exactement ce qui sera envoyé",
                                 command=self._toggle_preview)
        self.b_show.pack(anchor="w")
        self.pv_frame = ttk.Frame(b)
        self.pv_frame.pack(fill="x")
        bf = ttk.Frame(b)
        bf.pack(fill="x", pady=(P(14), 0))
        ttk.Button(bf, text="Annuler", command=self.destroy).pack(side="right")
        ttk.Button(bf, text="Envoyer à Gemini", style="Accent.TButton",
                   command=self._ok).pack(side="right", padx=P(8))
        self.show()
        self.wait_window()

    def _toggle_preview(self):
        if self.preview:
            self.preview.destroy()
            self.preview = None
            return
        self.preview = self.text_box(self.pv_frame, 12, json.dumps(
            self.items, ensure_ascii=False, indent=1), width=80)
        self.preview.configure(state="disabled")
        self.preview.pack(fill="x", pady=(self.app.px(8), 0))

    def _ok(self):
        self.result = True
        self.destroy()


class ConfirmDialog(Dialog):
    """Confirmer ou corriger une suggestion. La catégorie de SÉCURITÉ (Vital / Peut être
    fermé) est toujours choisie par l'utilisateur : l'IA ne la décide jamais."""

    def __init__(self, app, rec, correct, on_done):
        super().__init__(app, "Corriger l'identification" if correct
                         else "Confirmer l'identification")
        self.rec, self.on_done = rec, on_done
        res = rec.get("correction") or rec["resultat"]
        self.orig = rec["resultat"]
        b, P = self.body, app.px
        ttk.Label(b, text=rec["process_name"], style="H2.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        label, _, sentence = conf_info(self.orig)
        ttk.Label(b, text=f"{label} (estimation de l'IA). {sentence}", style="Small.TLabel",
                  wraplength=P(560)).grid(row=1, column=0, columnspan=2, sticky="w",
                                          pady=(0, P(10)))
        ttk.Label(b, text="Description :").grid(row=2, column=0, columnspan=2, sticky="w")
        desc = res.get("description", "")
        if desc == "Identification impossible":
            desc = ""
        self.desc = self.text_box(b, 3, desc)
        self.desc.grid(row=3, column=0, columnspan=2, sticky="we", pady=(P(4), P(8)))
        ttk.Label(b, text="Type de logiciel :").grid(row=4, column=0, sticky="w")
        self.cat = tk.StringVar(value=res.get("category", "Inconnu"))
        ttk.Combobox(b, textvariable=self.cat, values=list(gemini.CATEGORIES), state="readonly",
                     width=24).grid(row=4, column=1, sticky="w", pady=P(3))
        ttk.Label(b, text="Éditeur :").grid(row=5, column=0, sticky="w")
        self.pub = tk.StringVar(value=res.get("publisher", ""))
        ttk.Entry(b, textvariable=self.pub, width=34).grid(row=5, column=1, sticky="w",
                                                           pady=P(3))
        ttk.Label(b, text="Peut-on le fermer ? (votre choix)").grid(
            row=6, column=0, sticky="nw", pady=(P(10), 0))
        current = (app.kb.get(rec["process_name"]) or {}).get("categorie", "inconnu")
        self.safety = tk.StringVar(value=current)
        sf = ttk.Frame(b)
        sf.grid(row=6, column=1, sticky="w", pady=(P(10), 0))
        for val, txt in (("vital", "Vital : ne jamais fermer"),
                         ("peut_etre_ferme", "Peut être fermé"),
                         ("inconnu", "Je ne sais pas encore (reste « Inconnu »)")):
            ttk.Radiobutton(sf, text=txt, value=val, variable=self.safety).pack(anchor="w")
        ttk.Label(b, style="Small.TLabel", wraplength=P(560), text=(
            "L'IA ne décide pas si un processus peut être fermé : ce choix reste le vôtre.")
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(P(6), 0))
        bf = ttk.Frame(b)
        bf.grid(row=8, column=0, columnspan=2, sticky="e", pady=(P(14), 0))
        ttk.Button(bf, text="Annuler", command=self.destroy).pack(side="right")
        ttk.Button(bf, text="Enregistrer dans la base", style="Accent.TButton",
                   command=self.save).pack(side="right", padx=P(8))
        self.show()

    def save(self):
        app, rec = self.app, self.rec
        desc = " ".join(self.desc.get("1.0", "end").split())
        if not desc:
            messagebox.showinfo(config.APP_NAME, "Écrivez au moins une courte description.",
                                parent=self)
            return
        cat, pub = self.cat.get(), self.pub.get().strip()
        changed = (desc != self.orig["description"] or cat != self.orig["category"]
                   or pub != (self.orig.get("publisher") or ""))
        validation = "corrigee" if changed else "confirmee"
        correction = {"description": desc, "category": cat, "publisher": pub,
                      "product_name": self.orig.get("product_name", "")} if changed else None
        app.ia_cache.set_validation(rec["empreinte"], validation, correction)
        app.kb.update_entry(rec["process_name"], desc, self.safety.get(), editeur=pub or None,
                            extra={"type": cat, "ia": {
                                "empreinte": rec["empreinte"], "validation": validation,
                                "modele": rec["modele"],
                                "confiance": self.orig["confidence"],
                                "date_analyse": rec["date_analyse"]}})
        self.destroy()
        self.on_done()
