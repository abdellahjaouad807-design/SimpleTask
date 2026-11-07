"""Interface moderne inspirée du Gestionnaire de tâches de Windows 11 :
menu latéral, pages Processus, Performances, À compléter, Assistant IA, Journal, Réglages."""
import ctypes
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

import psutil
import sv_ttk

from . import actions, cle_api, config, gemini, safety
from .base import KnowledgeBase
from .ia_cache import IACache
from .icons import IconCache
from .scanner import Scanner, global_usage
from .signatures import SignatureChecker
from .widgets import (CAT_COLORS, PALETTES, FlatButton, LineChart, NavItem, ScrollFrame,
                      Sparkline, Table, follow_width,
                      pick_font)

CAT_LABEL = {
    "vital": "Vital",
    "peut_etre_ferme": "Peut être fermé",
    "inconnu": "Inconnu",
    "suspect": "Suspect",
}
CAT_ORDER = {"suspect": 0, "inconnu": 1, "peut_etre_ferme": 2, "vital": 3}
RISQUE_LABEL = {"aucun": "Aucun", "faible": "Faible", "eleve": "Élevé", "": "—"}
SIG_LABEL = {"signe": "Signé (éditeur vérifié)", "non_signe": "Non signé",
             "": "Pas encore vérifiée"}
CONF_SHORT = {"high": "élevée", "medium": "moyenne", "low": "faible"}

# Icônes de la police Segoe MDL2 Assets / Segoe Fluent Icons (fournies avec Windows)
ICON = {"proc": "", "perf": "", "todo": "", "ia": "✦", "log": "",
        "settings": "", "theme": "", "search": ""}


def fmt_mo(octets):
    mo = octets / (1024 * 1024)
    if mo >= 1024:
        return f"{mo / 1024:.1f} Go".replace(".", ",")
    return f"{mo:.0f} Mo"


def fmt_pct(v):
    return f"{v:.1f} %".replace(".", ",")


def fmt_duration(s):
    s = int(s)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, _ = divmod(s, 60)
    return (f"{d} j " if d else "") + f"{h:02d}:{m:02d}"


class Row:
    """Ce qu'on affiche pour une application (un groupe de processus)."""
    __slots__ = ("g", "entry", "display", "category", "shown_cat", "reasons", "gourmand",
                 "is_self", "whitelisted", "signature", "editeur", "ia")


def ram_candidates(rows, min_ram=20 * 1024 * 1024):
    """Applications proposées par « Libérer de la RAM » : uniquement « Peut être fermé »,
    ni suspectes, ni en liste blanche, ni protégées, ni SimpleTask lui-même.
    (Une suggestion de l'IA ne rend jamais un processus « fermable ».)"""
    cands = [r for r in rows
             if r.shown_cat == "peut_etre_ferme" and r.category == "peut_etre_ferme"
             and not r.whitelisted and not r.is_self
             and actions.can_close(r.g.name, r.category, r.is_self)[0]
             and r.g.ram > min_ram]
    cands.sort(key=lambda r: -r.g.ram)
    return cands


def dark_title_bar(window, dark):
    """Barre de titre sombre sous Windows 10 (20H1+) et 11."""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4) == 0:
                break
        # force Windows à redessiner la barre de titre (SWP_FRAMECHANGED | NOMOVE | NOSIZE | NOZORDER)
        ctypes.windll.user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001 | 0x0004)
    except (AttributeError, OSError):
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.settings = config.load_settings()
        self.kb = KnowledgeBase()
        self.kb.backup("demarrage")
        self.journal = actions.Journal()
        self.scanner = Scanner()
        self.sig = SignatureChecker()
        self.ia_cache = IACache()
        self.ia_cfg = gemini.load_config()
        self.rows = {}
        self.usage = (0.0, 0.0, 0, 1)
        self.busy = False
        self._last_sig_save = time.time()
        self._themed = []           # (widget, fond, texte) à recolorer au changement de thème
        self._flat_buttons = []     # boutons plats, recolorés au changement de thème
        self.boot_time = psutil.boot_time()

        self.title(f"{config.APP_NAME} — gestionnaire de tâches")
        self.k = max(1.0, self.winfo_fpixels("1i") / 96)
        self.icons = IconCache(self, self.px(16))
        w = min(self.px(1500), int(self.winfo_screenwidth() * 0.92))
        h = min(self.px(840), int(self.winfo_screenheight() * 0.88))
        self.geometry(f"{w}x{h}")
        self.minsize(min(self.px(960), w), min(self.px(620), h))
        self.protocol("WM_DELETE_WINDOW", self.on_quit)
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(__file__)))
        try:
            self.iconbitmap(default=os.path.join(base, "assets", "simpletask.ico"))
        except tk.TclError:
            pass

        family = pick_font(self, "Segoe UI Variable Text", "Segoe UI")
        icons = pick_font(self, "Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol")
        self.font_normal = tkfont.Font(family=family, size=10)
        self.font_bold = tkfont.Font(family=family, size=10, weight="bold")
        self.font_small = tkfont.Font(family=family, size=9)
        self.font_italic = tkfont.Font(family=family, size=10, slant="italic")
        self.font_title = tkfont.Font(family=family, size=18, weight="bold")
        self.font_h2 = tkfont.Font(family=family, size=13, weight="bold")
        self.font_big = tkfont.Font(family=family, size=22, weight="bold")
        self.font_header_value = tkfont.Font(family=family, size=11, weight="bold")
        self.font_icon = tkfont.Font(family=icons, size=12)

        sv_ttk.set_theme("dark" if self.settings["theme"] == "sombre" else "light")
        self.pal = PALETTES[self.settings["theme"]]
        self.style = ttk.Style(self)
        self._build()
        self.apply_theme()
        self.show_page("proc")
        self.bind_all("<Delete>", self._on_delete_key)
        self.bind("<Map>", lambda e: self._on_restore() if e.widget is self else None)
        self.deiconify()
        self.after(50, self.refresh)

    # ================================================================ outils
    def px(self, n):
        return int(n * self.k)

    def themed(self, widget, bg="bg", fg=None):
        self._themed.append((widget, bg, fg))
        return widget

    def label(self, parent, text="", bg="bg", fg="fg", font=None, **kw):
        lbl = tk.Label(parent, text=text, font=font or self.font_normal, anchor="w",
                       justify="left", **kw)
        return self.themed(lbl, bg, fg)

    def _run_bg(self, func, done):
        box = {}

        def worker():
            try:
                box["r"] = func()
            except Exception as ex:  # transmis à l'interface
                box["e"] = ex

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        def poll():
            if t.is_alive():
                self.after(100, poll)
            else:
                done(box.get("r"), box.get("e"))
        self.after(100, poll)

    # ================================================================ construction
    def _build(self):
        self.side = self.themed(tk.Frame(self, width=self.px(230)), "side")
        self.side.pack(side="left", fill="y")
        self.side.pack_propagate(False)
        self.content = self.themed(tk.Frame(self), "bg")
        self.content.pack(side="left", fill="both", expand=True)

        brand = self.themed(tk.Frame(self.side), "side")
        brand.pack(fill="x", padx=self.px(14), pady=(self.px(16), self.px(18)))
        self.logo = self.themed(tk.Canvas(brand, width=self.px(26), height=self.px(26),
                                          highlightthickness=0), "side")
        self.logo.pack(side="left")
        self.label(brand, config.APP_NAME, bg="side", font=self.font_h2).pack(
            side="left", padx=self.px(10))

        from .ia_ui import IAPage  # import local : évite une dépendance circulaire
        self.pages = {
            "proc": ProcessPage(self),
            "perf": PerfPage(self),
            "todo": TodoPage(self),
            "ia": IAPage(self),
            "log": JournalPage(self),
            "settings": SettingsPage(self),
        }
        self.nav = {}
        for key, text in (("proc", "Processus"), ("perf", "Performances"),
                          ("todo", "À compléter"), ("ia", "Assistant IA"),
                          ("log", "Journal")):
            item = NavItem(self.side, self, ICON[key], text, lambda k=key: self.show_page(k))
            item.pack(fill="x", padx=self.px(6), pady=1)
            self.nav[key] = item
        bottom = self.themed(tk.Frame(self.side), "side")
        bottom.pack(side="bottom", fill="x", pady=self.px(10))
        self.theme_item = NavItem(bottom, self, ICON["theme"], "", self.toggle_theme)
        self.theme_item.pack(fill="x", padx=self.px(6), pady=1)
        item = NavItem(bottom, self, ICON["settings"], "Réglages",
                       lambda: self.show_page("settings"))
        item.pack(fill="x", padx=self.px(6), pady=1)
        self.nav["settings"] = item

        self.status = self.label(self.content, "", fg="muted", font=self.font_small)
        self.status.pack(side="bottom", fill="x", padx=self.px(24), pady=(0, self.px(8)))
        # Une seule page est placée à la fois : les pages cachées ne sont ni recalculées ni
        # redessinées quand la fenêtre change de taille.
        self.current = None

    def _on_restore(self):
        """Fenêtre ré-affichée : remet la page courante à jour tout de suite."""
        if self.current:
            self.pages[self.current].on_show()

    def show_page(self, key):
        if self.current and self.current != key:
            self.pages[self.current].frame.place_forget()
        self.current = key
        for k, item in self.nav.items():
            item.set_active(k == key)
        self.pages[key].frame.place(in_=self.content, x=0, y=0, relwidth=1, relheight=1,
                                    height=-self.px(34))
        self.pages[key].on_show()

    # ================================================================ thème
    def apply_theme(self):
        p = self.pal = PALETTES[self.settings["theme"]]
        dark = self.settings["theme"] == "sombre"
        self.configure(bg=p["bg"])
        for w, bg, fg in self._themed:
            try:
                w.configure(bg=p[bg])
                if fg:
                    w.configure(fg=p[fg])
            except tk.TclError:
                pass
        self.option_add("*TCombobox*Listbox.background", p["surface"])
        self.option_add("*TCombobox*Listbox.foreground", p["fg"])
        self.style.configure("Muted.TLabel", foreground=p["muted"])
        self.style.configure("Title.TLabel", font=self.font_title)
        self.style.configure("H2.TLabel", font=self.font_h2)
        self.style.configure("Small.TLabel", font=self.font_small, foreground=p["muted"])
        self.style.configure("Treeview", rowheight=int(self.font_normal.metrics("linespace") * 1.8))
        self.theme_item.label.configure(text="Thème clair" if dark else "Thème sombre")
        for item in list(self.nav.values()) + [self.theme_item] + self._flat_buttons:
            item.apply_theme()
        self.logo.delete("all")
        s = self.px(12)
        for i, c in enumerate(("vital", "peut_etre_ferme", "inconnu", "suspect")):
            x, y = (i % 2) * (s + 2), (i // 2) * (s + 2)
            self.logo.create_oval(x, y, x + s, y + s, fill=CAT_COLORS[c], outline="")
        for page in self.pages.values():
            page.apply_theme()
        dark_title_bar(self, dark)

    def toggle_theme(self):
        self.settings["theme"] = "clair" if self.settings["theme"] == "sombre" else "sombre"
        config.save_settings(self.settings)
        sv_ttk.set_theme("dark" if self.settings["theme"] == "sombre" else "light")
        self.apply_theme()

    # ================================================================ rafraîchissement
    def refresh(self):
        try:
            self._refresh_once()
        finally:
            self.after(int(max(1, float(self.settings["rafraichissement_s"])) * 1000),
                       self.refresh)

    def _refresh_once(self):
        st = self.settings
        groups, launched = self.scanner.scan(float(st["suspect_cpu"]))
        now = time.time()
        white = set(st["liste_blanche"])
        ia_by_name = self.ia_cache.latest_by_name()
        new_rows = {}
        created = 0
        for g in groups:
            lname = g.name.lower()
            if self.kb.observe(g.name, g.path, new_launch=lname in launched):
                created += 1
            info = self.sig.lookup(g.path) if g.path else None
            signature = (info or {}).get("signature", "")
            editeur = (info or {}).get("editeur") or (info or {}).get("signataire") or ""
            if info:
                self.kb.set_identity(g.name, signature, editeur)
            entry = self.kb.get(g.name)
            category = entry.get("categorie", "inconnu")
            sustained = bool(g.high_cpu_since) and now - g.high_cpu_since >= float(
                st["suspect_duree_s"])
            # La détection des suspects reste indépendante de l'IA.
            reasons = safety.suspect_reasons(g.name, g.path, signature,
                                             category != "inconnu", sustained)
            r = Row()
            r.g, r.entry, r.category = g, entry, category
            r.reasons = reasons
            r.shown_cat = "suspect" if reasons else category
            r.gourmand = (g.cpu >= float(st["seuil_cpu"])
                          or g.ram >= float(st["seuil_ram_mo"]) * 1024 * 1024)
            r.is_self = any(p in self.scanner.self_pids for p in g.pids)
            r.whitelisted = lname in white
            r.signature = signature
            r.editeur = entry.get("editeur") or editeur
            ia = ia_by_name.get(lname)
            r.ia = ia if ia and ia.get("validation") != "rejetee" else None
            nice = (info or {}).get("nom_lisible", "")
            stem = g.name[:-4] if g.name.lower().endswith(".exe") else g.name
            r.display = nice if nice and len(nice) <= 40 else stem
            new_rows[g.key] = r
        self.rows = new_rows
        self.kb.save()
        if now - self._last_sig_save > 30:
            self.sig.save()
            self._last_sig_save = now

        cpu, ram_pct, used, total = global_usage()
        self.usage = (cpu, ram_pct, used, total)
        n_unknown = len(self.kb.unknowns())
        self.nav["todo"].set_badge(str(n_unknown) if n_unknown else "")
        for page in self.pages.values():
            page.on_refresh(created)
        n_susp = sum(1 for r in new_rows.values() if r.shown_cat == "suspect")
        msg = (f"{len(new_rows)} applications · "
               f"{sum(len(r.g.pids) for r in new_rows.values())} processus")
        if created:
            msg += f" · {created} nouveau(x) processus enregistré(s) dans la base"
        if n_susp:
            msg += f" · ⚠ {n_susp} processus suspect(s)"
        if not self.busy:
            self.status.configure(text=msg)

    # ================================================================ actions communes
    def _set_busy(self, busy, msg=""):
        self.busy = busy
        if msg:
            self.status.configure(text=msg)
        self.pages["proc"].render_detail()

    def close_row(self, r):
        if r is None or self.busy:
            return
        ok, reason = actions.can_close(r.g.name, r.category, r.is_self)
        if not ok:
            messagebox.showinfo(config.APP_NAME, reason, parent=self)
            return
        extra = ""
        if r.category == "inconnu":
            extra = ("\n\nAttention : SimpleTask ne sait pas ce qu'est ce processus. "
                     "Le fermer pourrait faire planter un programme.")
        if not messagebox.askyesno(
                "Fin de tâche ?",
                f"Fermer « {r.display} » ({len(r.g.pids)} processus, {fmt_mo(r.g.ram)}) ?\n\n"
                "Ce qui n'est pas enregistré dans cette application sera perdu." + extra,
                icon="warning", parent=self):
            return
        self.close_groups([r], "Fermeture manuelle")

    def close_groups(self, rows, origine):
        self._set_busy(True, "Fermeture en cours…")

        def work():
            results = []
            for r in rows:
                try:
                    closed, denied = actions.close_pids(r.g.name, r.category, list(r.g.pids),
                                                        self.scanner.self_pids)
                    results.append((r, closed, denied, None))
                except actions.Refused as ex:
                    results.append((r, 0, 0, str(ex)))
                except psutil.AccessDenied:
                    results.append((r, 0, len(r.g.pids), None))  # lancé en administrateur
                except Exception as ex:  # une application ne doit jamais bloquer les autres
                    results.append((r, 0, 0, f"erreur inattendue ({type(ex).__name__})"))
            return results

        def done(results, err):
            self._set_busy(False)
            if err:
                messagebox.showerror(config.APP_NAME, f"Erreur : {err}", parent=self)
                return
            denied_names = []
            freed = 0
            for r, closed, denied, refused in results:
                if refused:
                    res = f"Refusé : {refused}"
                elif denied:
                    res = (f"{closed} fermé(s), {denied} refusé(s) par Windows (droits "
                           "administrateur nécessaires)")
                    denied_names.append(r.display)
                else:
                    res = "Fermé"
                if closed and not denied:
                    freed += r.g.ram
                self.journal.add(r.g.name, len(r.g.pids), r.g.ram / 1048576 if closed else 0,
                                 res, origine)
            self.pages["log"].render()
            self.status.configure(text=f"Terminé. Environ {fmt_mo(freed)} de mémoire libérée.")
            if denied_names and actions.is_admin():
                messagebox.showwarning(
                    "Fermeture refusée",
                    "Windows a refusé de fermer : " + ", ".join(denied_names) + ".\n\nCe "
                    "processus est protégé par Windows ou par son éditeur.", parent=self)
            elif denied_names:
                if messagebox.askyesno(
                        "Droits administrateur nécessaires",
                        "Windows a refusé de fermer : " + ", ".join(denied_names) + ".\n\n"
                        "Ce programme a été lancé avec les droits administrateur : seul un "
                        "programme qui a aussi ces droits peut le fermer.\n\n"
                        "Relancer SimpleTask en administrateur ? (Windows vous demandera "
                        "confirmation.)", parent=self):
                    if actions.relaunch_as_admin():
                        self.on_quit()
        self._run_bg(work, done)

    def free_ram(self):
        if self.busy:
            return
        cands = ram_candidates(self.rows.values())
        if not cands:
            messagebox.showinfo("Libérer de la RAM",
                                "Rien à fermer : aucune application « Peut être fermé » "
                                "n'utilise beaucoup de mémoire en ce moment.", parent=self)
            return
        FreeRamDialog(self, cands)

    def toggle_whitelist(self, name):
        wl = self.settings["liste_blanche"]
        n = name.lower()
        if n in wl:
            wl.remove(n)
        else:
            wl.append(n)
        config.save_settings(self.settings)
        for r in self.rows.values():
            if r.g.name.lower() == n:
                r.whitelisted = n in wl
        self.pages["proc"].render_rows()

    def save_settings(self):
        config.save_settings(self.settings)

    def is_visible(self):
        """Faux si la fenêtre est réduite dans la barre des tâches."""
        return self.state() != "iconic" and self.winfo_viewable()

    def _on_delete_key(self, event):
        """Touche Suppr : fin de tâche de la ligne choisie (avec confirmation)."""
        if self.current != "proc":
            return
        focus = self.focus_get()
        if isinstance(focus, (tk.Entry, ttk.Entry, tk.Text, tk.Listbox)):
            return  # Suppr efface du texte dans un champ de saisie : on n'y touche pas
        self.close_row(self.pages["proc"].selected_row())
        return "break"

    def describe_with_ia(self, names=None, force=False):
        self.show_page("ia")
        self.pages["ia"].start_analysis(names, force)

    def on_quit(self):
        try:
            ia = self.pages.get("ia")
            if ia and ia.job and not ia.job.finished:
                ia.job.cancel()
            self.kb.save(force=True)
            self.sig.save()
        finally:
            self.destroy()


# ==================================================================== pages
class Page:
    def __init__(self, app, title, subtitle=""):
        self.app = app
        self.frame = app.themed(tk.Frame(app.content), "bg")
        pad = app.px(24)
        self.top = app.themed(tk.Frame(self.frame), "bg")
        self.top.pack(fill="x", padx=pad, pady=(app.px(18), app.px(10) if not subtitle else 0))
        app.label(self.top, title, font=app.font_title).pack(side="left")
        if subtitle:  # sur sa propre ligne : les boutons de droite gardent leur place
            self.subtitle = app.label(self.frame, subtitle, fg="muted", font=app.font_small)
            self.subtitle.pack(fill="x", padx=pad, pady=(0, app.px(10)))
            follow_width(self.subtitle, [self.subtitle])
        self.body = app.themed(tk.Frame(self.frame), "bg")
        self.body.pack(fill="both", expand=True, padx=pad, pady=(0, app.px(6)))

    def on_show(self):
        pass

    def on_refresh(self, created):
        pass

    def apply_theme(self):
        pass


SORT_KEYS = {"nom": "nom", "statut": "cat", "cpu": "cpu", "ram": "ram", "disk": "disk",
             "net": "net", "gpu": "gpu"}
SECTIONS = (("app", "Applications"), ("bg", "Processus en arrière-plan"),
            ("win", "Processus Windows"))


def fmt_disk(bps):
    return f"{bps / 1048576:.1f} Mo/s".replace(".", ",")


def row_section(r):
    """Comme le Gestionnaire de tâches : applications (fenêtre visible), processus Windows,
    ou processus en arrière-plan."""
    if r.g.is_app and not r.is_self:
        return "app"
    windir = os.environ.get("SystemRoot", r"C:\Windows").lower() + "\\"
    path = (r.g.path or "").lower()
    if (path.startswith(windir) or (not path and safety.is_protected(r.g.name))
            or (r.category == "vital" and (r.entry.get("editeur") or "") == "Microsoft")):
        return "win"
    return "bg"


class ProcessPage(Page):
    def __init__(self, app):
        super().__init__(app, "Processus")
        self.sort, self.desc = "ram", True
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.render_rows())
        FlatButton(self.top, app,text="Libérer de la RAM", style="Accent.TButton",
                   command=app.free_ram).pack(side="right")
        self.b_end = FlatButton(self.top, app,text="✕  Fin de tâche (Suppr)",
                                command=lambda: app.close_row(self.selected_row()))
        self.b_end.pack(side="right", padx=app.px(8))
        search = ttk.Entry(self.top, textvariable=self.search_var, width=30)
        search.pack(side="right", padx=app.px(8))
        app.label(self.top, ICON["search"], fg="muted", font=app.font_icon).pack(side="right")

        legend = app.themed(tk.Frame(self.body), "bg")
        legend.pack(fill="x", pady=(0, app.px(8)))
        self.legend_labels = []
        for cat in ("vital", "peut_etre_ferme", "inconnu", "suspect"):
            dot = tk.Canvas(legend, width=app.px(10), height=app.px(10), highlightthickness=0)
            dot.create_oval(0, 0, app.px(10), app.px(10), fill=CAT_COLORS[cat], outline="")
            app.themed(dot, "bg")
            dot.pack(side="left", padx=(0, app.px(6)))
            app.label(legend, CAT_LABEL[cat], fg="muted", font=app.font_small).pack(
                side="left", padx=(0, app.px(18)))
        self.counts = app.label(legend, "", fg="muted", font=app.font_small)
        self.counts.pack(side="right")
        self.group_var = tk.BooleanVar(value=app.settings.get("grouper", True))
        ttk.Checkbutton(legend, text="Regrouper par type", variable=self.group_var,
                        command=self._toggle_group).pack(side="right", padx=app.px(16))
        app.label(legend, "Clic droit sur les titres : choisir les colonnes", fg="faint",
                  font=app.font_small).pack(side="right", padx=app.px(8))

        self.table = Table(self.body, app, [
            {"key": "nom", "title": "Nom", "width": 230, "kind": "name", "stretch": True},
            {"key": "statut", "title": "Statut", "width": 225, "kind": "pill"},
            {"key": "cpu", "title": "Processeur", "width": 95, "anchor": "e", "kind": "heat"},
            {"key": "ram", "title": "Mémoire", "width": 100, "anchor": "e", "kind": "heat"},
            {"key": "disk", "title": "Disque", "width": 95, "anchor": "e", "kind": "heat"},
            {"key": "net", "title": "Réseau", "width": 90, "anchor": "e", "kind": "heat",
             "menu": "Réseau (connexions actives)"},
            {"key": "gpu", "title": "GPU", "width": 90, "anchor": "e",
             "kind": "heat", "menu": "Processeur graphique (GPU)"},
            {"key": "engine", "title": "Moteur GPU", "width": 140, "sortable": False,
             "menu": "Moteur du processeur graphique"},
            {"key": "desc", "title": "Ce que c'est", "width": 360, "stretch": True,
             "sortable": False},
        ], on_select=lambda rid: self.render_detail(), on_double=lambda rid: self.edit(),
            on_context=self._context, on_sort=self._sort,
            empty_text="Lecture des processus…", name="processus")
        self.table.set_sort("ram", True)
        self.table.pack(fill="both", expand=True)

        d = self.detail = app.themed(tk.Frame(self.body), "bg")
        d.pack(fill="x", pady=(app.px(12), 0))
        self.d_title = app.label(d, "", font=app.font_h2)
        self.d_title.pack(anchor="w")
        self.d_advice = app.label(d, "", font=app.font_bold)
        self.d_advice.pack(anchor="w", pady=(app.px(2), app.px(2)))
        self.d_desc = app.label(d, "")
        self.d_desc.pack(anchor="w")
        self.d_ia = app.label(d, "", fg="ia", font=app.font_italic)
        self.d_ia.pack(anchor="w")
        self.d_info = app.label(d, "", fg="muted", font=app.font_small)
        self.d_info.pack(anchor="w", pady=(app.px(4), app.px(8)))
        btns = app.themed(tk.Frame(d), "bg")
        btns.pack(anchor="w")
        self.b_end2 = FlatButton(btns, app,text="✕  Fin de tâche (Suppr)",
                                 command=lambda: app.close_row(self.selected_row()))
        self.b_white = FlatButton(btns, app,text="Ajouter à la liste blanche", command=self.whitelist)
        self.b_edit = FlatButton(btns, app,text="Modifier l'explication", command=self.edit)
        self.b_ia = FlatButton(btns, app,text="✦ Décrire avec l'IA", command=self.describe)
        self.b_open = FlatButton(btns, app,text="Ouvrir l'emplacement", command=self.open_location)
        for b in (self.b_end2, self.b_white, self.b_edit, self.b_ia, self.b_open):
            b.pack(side="left", padx=(0, app.px(8)))

        follow_width(d, [self.d_advice, self.d_desc, self.d_info, self.d_ia])
        self.render_detail()

    def apply_theme(self):
        self.table.apply_theme()
        self.render_rows()
        self.render_detail()

    def on_show(self):
        self.render_rows()

    def on_refresh(self, created):
        cpu, ram_pct, used, total = self.app.usage
        self.table.set_header_extra("cpu", f"{cpu:.0f} %")
        self.table.set_header_extra("ram", f"{ram_pct:.0f} %")
        tot = self.app.scanner.totals
        self.table.set_header_extra("disk", fmt_disk(tot["disk"]))
        self.table.set_header_extra("net", f"{tot['net']} conn.")
        if tot["gpu"] is not None:
            self.table.set_header_extra("gpu", f"{tot['gpu']:.0f} %")
        # fenêtre réduite ou autre page : rien à redessiner (économise le processeur en jeu)
        if self.app.current == "proc" and self.app.is_visible():
            self.render_rows()
            self.render_detail()

    def _sort(self, key):
        mode = SORT_KEYS.get(key)
        if not mode:
            return
        if self.sort == mode:
            self.desc = not self.desc
        else:
            self.sort, self.desc = mode, mode in ("ram", "cpu")
        self.table.set_sort(key, self.desc)
        self.render_rows()

    def render_rows(self):
        app, p = self.app, self.app.pal
        q = self.search_var.get().strip().lower()
        rows = list(app.rows.values())
        if q:
            rows = [r for r in rows if q in r.display.lower() or q in r.g.name.lower()
                    or q in (r.entry.get("description") or "").lower()
                    or q in (r.editeur or "").lower()]
        if self.sort == "ram":
            rows.sort(key=lambda r: r.g.ram)
        elif self.sort == "cpu":
            rows.sort(key=lambda r: (r.g.cpu, r.g.ram))
        elif self.sort == "disk":
            rows.sort(key=lambda r: (r.g.disk, r.g.ram))
        elif self.sort == "net":
            rows.sort(key=lambda r: (r.g.net, r.g.ram))
        elif self.sort == "gpu":
            rows.sort(key=lambda r: (r.g.gpu, r.g.ram))
        elif self.sort == "cat":
            rows.sort(key=lambda r: (-CAT_ORDER[r.shown_cat], r.g.ram))
        else:
            rows.sort(key=lambda r: r.display.lower())
            rows.reverse()
        if self.desc:
            rows.reverse()
        if self.group_var.get():
            # sections du Gestionnaire de tâches, triées chacune selon la colonne choisie
            by = {k: [] for k, _ in SECTIONS}
            for r in rows:
                by[row_section(r)].append(r)
            ordered = []
            for k, title in SECTIONS:
                if by[k]:
                    ordered.append(("section", f"{title} ({len(by[k])})"))
                    ordered.extend(by[k])
        else:
            ordered = rows
        out = []
        budget = [12]  # icônes nouvelles lues par rafraîchissement (évite les saccades)
        for r in ordered:
            if isinstance(r, tuple):
                out.append({"id": "§" + r[1], "section": r[1], "cells": {}})
                continue
            n = len(r.g.pids)
            sub = []
            if r.gourmand:
                sub.append("▲ Gourmand")
            if r.whitelisted:
                sub.append("★")
            desc = r.entry.get("description") or ""
            fg, italic = {}, set()
            if r.reasons:
                desc = "⚠ " + r.reasons[0]
                fg["desc"] = CAT_COLORS["suspect"]
            elif not desc and r.ia:
                res = r.ia["resultat"]
                desc = (f"✦ Suggestion IA (confiance {CONF_SHORT[res['confidence']]}) : "
                        f"{res['description']}")
                fg["desc"], italic = p["ia"], {"desc"}
            elif not desc:
                desc = "Pas encore dans la base. Dans le doute, laissez-le tranquille."
                fg["desc"] = p["muted"]
            gpu_ok = app.scanner.gpu is not None
            out.append({
                "id": r.g.key,
                "cells": {"nom": f"{r.display}  ({n})" if n > 1 else r.display,
                          "statut": "  ".join(sub), "cpu": fmt_pct(r.g.cpu),
                          "ram": fmt_mo(r.g.ram), "disk": fmt_disk(r.g.disk),
                          "net": f"{r.g.net} conn.",
                          "gpu": fmt_pct(r.g.gpu) if gpu_ok else "—",
                          "engine": r.g.gpu_engine if r.g.gpu >= 0.05 else "",
                          "desc": desc},
                "dot": CAT_COLORS[r.shown_cat],
                "icon": self._icon(r.g.path, budget),
                "pill": {"statut": (CAT_LABEL[r.shown_cat], CAT_COLORS[r.shown_cat])},
                "heat": {"cpu": min(r.g.cpu / 25, 1), "ram": min(r.g.ram / (1500 << 20), 1),
                         "disk": min(r.g.disk / (5 << 20), 1), "net": min(r.g.net / 20, 1),
                         "gpu": min(r.g.gpu / 30, 1)},
                "fg": fg, "italic": italic,
            })
        self.table.set_rows(out)
        n_apps = sum(1 for o in out if not o.get("section"))
        self.counts.configure(text=f"{n_apps} applications affichées")

    def _icon(self, path, budget):
        """Icône de l'application ; au plus quelques nouvelles par rafraîchissement."""
        icons = self.app.icons
        key = (path or "").lower()
        if key in icons._cache:
            return icons._cache[key]
        if budget[0] <= 0:
            return None
        budget[0] -= 1
        return icons.get(path)

    def _toggle_group(self):
        self.app.settings["grouper"] = bool(self.group_var.get())
        self.app.save_settings()
        self.render_rows()

    def selected_row(self):
        return self.app.rows.get(self.table.selected)

    def render_detail(self):
        app, p = self.app, self.app.pal
        r = self.selected_row()
        if r is None:
            self.d_title.configure(text="")
            self.d_advice.configure(text="Cliquez sur une ligne pour savoir ce qu'est ce "
                                         "processus et quoi en faire.", fg=p["muted"])
            for lbl in (self.d_desc, self.d_info, self.d_ia):
                lbl.configure(text="")
            for b in (self.b_end, self.b_end2, self.b_white, self.b_edit, self.b_ia, self.b_open):
                b.state(["disabled"])
            return
        e = r.entry
        protected = safety.is_protected(r.g.name)
        self.d_title.configure(text=f"{r.display}   ·   {r.g.name}")
        if r.reasons:
            advice = ("Attention : ce processus présente des signes inhabituels.\n• "
                      + "\n• ".join(r.reasons)
                      + "\nConseil : lancez une analyse avec votre antivirus. "
                        "SimpleTask ne supprime jamais rien.")
            color = CAT_COLORS["suspect"]
        elif r.is_self:
            advice, color = "C'est SimpleTask lui-même.", p["ok"]
        elif protected or r.category == "vital":
            advice = ("Ne fermez pas ce processus : Windows ou un pilote en a besoin. "
                      "SimpleTask bloque sa fermeture.")
            color = p["danger"]
        elif r.category == "peut_etre_ferme":
            advice = ("Vous pouvez le fermer. La fonction qu'il assure s'arrêtera jusqu'au "
                      "prochain démarrage." if e.get("risque") == "faible" else
                      "Vous pouvez le fermer sans risque si vous ne l'utilisez pas.")
            color = p["ok"]
        else:
            advice = ("SimpleTask ne connaît pas encore ce processus. Dans le doute, laissez-le "
                      "tranquille. Décrivez-le vous-même ou demandez une suggestion à l'IA.")
            color = p["fg"]
        self.d_advice.configure(text=advice, fg=color)
        self.d_desc.configure(text=e.get("description") or "Aucune description validée.")
        if r.ia and r.category == "inconnu":
            res = r.ia["resultat"]
            self.d_ia.configure(text=(
                f"✦ Suggestion de l'IA, non vérifiée (confiance {CONF_SHORT[res['confidence']]}"
                f", estimation) : {res['description']}  —  Voir l'onglet Assistant IA."))
            self.d_ia.pack(anchor="w", after=self.d_desc)
        else:
            self.d_ia.configure(text="")
            self.d_ia.pack_forget()
        parts = [
            f"Catégorie : {CAT_LABEL[r.shown_cat]}",
            f"Risque si on le ferme : {RISQUE_LABEL.get(e.get('risque', ''), '—')}",
            f"Éditeur : {r.editeur or 'inconnu'}",
            "Signature : " + (SIG_LABEL.get(r.signature, '—') if r.g.path
                              else "inaccessible sans droits administrateur"),
        ]
        line2 = [f"{len(r.g.pids)} processus · {fmt_pct(r.g.cpu)} du processeur · "
                 f"{fmt_mo(r.g.ram)} de mémoire"]
        if r.gourmand:
            line2.append("▲ Gourmand en ce moment")
        if r.whitelisted:
            line2.append("★ Liste blanche")
        line2.append(f"Emplacement : {r.g.path or 'inaccessible sans droits administrateur'}")
        self.d_info.configure(text="   ·   ".join(parts) + "\n" + "   ·   ".join(line2))
        ok, _ = actions.can_close(r.g.name, r.category, r.is_self)
        for b in (self.b_end, self.b_end2):
            b.state(["!disabled"] if ok and not app.busy else ["disabled"])
        self.b_white.configure(text="Retirer de la liste blanche" if r.whitelisted
                               else "Ajouter à la liste blanche")
        self.b_white.state(["!disabled"])
        self.b_edit.state(["!disabled"])
        self.b_ia.state(["!disabled"] if r.category == "inconnu" else ["disabled"])
        self.b_open.state(["!disabled"] if r.g.path else ["disabled"])

    def whitelist(self):
        r = self.selected_row()
        if r:
            self.app.toggle_whitelist(r.g.name)
            self.render_detail()

    def edit(self):
        r = self.selected_row()
        if r:
            EditDialog(self.app, r.g.name, on_save=self.render_detail)

    def describe(self):
        r = self.selected_row()
        if r:
            self.app.describe_with_ia([r.g.name])

    def open_location(self):
        r = self.selected_row()
        if r:
            actions.open_file_location(r.g.path)

    def _context(self, rid, event):
        r = self.app.rows.get(rid)
        if not r:
            return
        m = tk.Menu(self.app, tearoff=0)
        ok, _ = actions.can_close(r.g.name, r.category, r.is_self)
        m.add_command(label="Fin de tâche…", accelerator="Suppr",
                      command=lambda: self.app.close_row(r),
                      state="normal" if ok else "disabled")
        m.add_command(label="Retirer de la liste blanche" if r.whitelisted
                      else "Ajouter à la liste blanche", command=self.whitelist)
        m.add_command(label="Modifier l'explication…", command=self.edit)
        m.add_command(label="Décrire avec l'IA…", command=self.describe,
                      state="normal" if r.category == "inconnu" else "disabled")
        m.add_command(label="Ouvrir l'emplacement du fichier", command=self.open_location,
                      state="normal" if r.g.path else "disabled")
        m.tk_popup(event.x_root, event.y_root)


class PerfPage(Page):
    def __init__(self, app):
        super().__init__(app, "Performances", "Les 2 dernières minutes, mises à jour en direct.")
        self.body.grid_columnconfigure(0, weight=1, uniform="c")
        self.body.grid_columnconfigure(1, weight=1, uniform="c")
        self.body.grid_rowconfigure(0, weight=1)
        self.cpu = self._card(0, "Processeur (CPU)", "chart_cpu")
        self.ram = self._card(1, "Mémoire (RAM)", "chart_ram")

    def _card(self, col, title, color):
        app = self.app
        card = app.themed(tk.Frame(self.body, highlightthickness=1), "surface")
        app.themed(card, "surface")
        card.grid(row=0, column=col, sticky="nsew",
                  padx=(0, app.px(8)) if col == 0 else (app.px(8), 0))
        inner = app.themed(tk.Frame(card), "surface")
        inner.pack(fill="both", expand=True, padx=app.px(18), pady=app.px(16))
        app.label(inner, title, bg="surface", fg="muted").pack(anchor="w")
        big = app.label(inner, "—", bg="surface", font=app.font_big)
        big.pack(anchor="w")
        chart = LineChart(inner, app, color)
        chart.pack(fill="both", expand=True, pady=(app.px(10), app.px(12)))
        stats = app.themed(tk.Frame(inner), "surface")
        stats.pack(fill="x")
        cells = []
        for i in range(4):
            f = app.themed(tk.Frame(stats), "surface")
            f.grid(row=0, column=i, sticky="w", padx=(0, app.px(24)))
            t = app.label(f, "", bg="surface", fg="muted", font=app.font_small)
            t.pack(anchor="w")
            v = app.label(f, "", bg="surface", font=app.font_bold)
            v.pack(anchor="w")
            cells.append((t, v))
        return {"card": card, "big": big, "chart": chart, "cells": cells}

    def apply_theme(self):
        for c in (self.cpu, self.ram):
            c["card"].configure(highlightbackground=self.app.pal["border"],
                                highlightcolor=self.app.pal["border"])
            c["chart"].draw()

    def on_show(self):
        self.on_refresh(0)

    def on_refresh(self, created):
        app = self.app
        cpu, ram_pct, used, total = app.usage
        self.cpu["chart"].values.append(cpu)
        self.ram["chart"].values.append(ram_pct)
        if app.current != "perf" or not app.is_visible():
            return
        self.cpu["chart"].draw()
        self.ram["chart"].draw()
        self.cpu["big"].configure(text=f"{cpu:.0f} %")
        self.ram["big"].configure(text=f"{fmt_mo(used)} / {fmt_mo(total)}")
        n_proc = sum(len(r.g.pids) for r in app.rows.values())
        for (t, v), (a, b) in zip(self.cpu["cells"], (
                ("Utilisation", f"{cpu:.0f} %"), ("Applications", str(len(app.rows))),
                ("Processus", str(n_proc)),
                ("Allumé depuis", fmt_duration(time.time() - app.boot_time)))):
            t.configure(text=a)
            v.configure(text=b)
        for (t, v), (a, b) in zip(self.ram["cells"], (
                ("Utilisée", f"{ram_pct:.0f} %"), ("Disponible", fmt_mo(total - used)),
                ("Total", fmt_mo(total)), ("", ""))):
            t.configure(text=a)
            v.configure(text=b)


class TodoPage(Page):
    def __init__(self, app):
        super().__init__(app, "À compléter",
                         "Processus rencontrés sur votre PC que SimpleTask ne connaît pas encore. "
                         "Ils restent « Inconnu » tant que vous ne les avez pas validés.")
        FlatButton(self.top, app,text="✦ Décrire les inconnus", style="Accent.TButton",
                   command=lambda: app.describe_with_ia()).pack(side="right")
        FlatButton(self.top, app,text="Importer…", command=self.import_entries).pack(
            side="right", padx=app.px(8))
        FlatButton(self.top, app,text="Exporter pour Claude…", command=self.export_unknowns).pack(
            side="right")
        FlatButton(self.top, app,text="Compléter", command=self.edit).pack(
            side="right", padx=app.px(8))
        self.table = Table(self.body, app, [
            {"key": "nom", "title": "Nom du fichier", "width": 230, "kind": "name"},
            {"key": "vues", "title": "Lancé", "width": 70, "anchor": "e"},
            {"key": "derniere", "title": "Dernière fois", "width": 150},
            {"key": "editeur", "title": "Éditeur", "width": 170},
            {"key": "ia", "title": "Suggestion de l'IA (à vérifier)", "width": 360,
             "stretch": True},
            {"key": "chemin", "title": "Emplacement", "width": 260, "stretch": True},
        ], on_double=lambda rid: self.edit(),
            empty_text="Rien à compléter : tous les processus rencontrés sont connus.",
            name="a_completer")
        self.table.pack(fill="both", expand=True)

    def apply_theme(self):
        self.table.apply_theme()
        self.render()

    def on_show(self):
        self.render()

    def on_refresh(self, created):
        if created and self.app.current == "todo":
            self.render()

    def render(self):
        app, p = self.app, self.app.pal
        latest = app.ia_cache.latest_by_name()
        rows = []
        for e in app.kb.unknowns():
            ia = latest.get(e["nom"].lower())
            txt, fg = "", {}
            if ia and ia.get("validation") != "rejetee":
                res = ia["resultat"]
                txt = f"✦ {res['description']} (confiance {CONF_SHORT[res['confidence']]})"
                fg = {"ia": p["ia"]}
            rows.append({"id": e["nom"].lower(), "dot": CAT_COLORS["inconnu"], "fg": fg,
                         "italic": {"ia"} if txt else set(),
                         "cells": {"nom": e["nom"], "vues": e.get("nb_vues", 0),
                                   "derniere": e.get("derniere_vue", ""),
                                   "editeur": e.get("editeur", ""), "ia": txt,
                                   "chemin": e.get("chemin", "")}})
        self.table.set_rows(rows)

    def edit(self):
        rid = self.table.selected
        if not rid:
            messagebox.showinfo(config.APP_NAME, "Choisissez d'abord une ligne.",
                                parent=self.app)
            return
        e = self.app.kb.get(rid)
        if e:
            EditDialog(self.app, e["nom"], on_save=self.render)

    def export_unknowns(self):
        kb = self.app.kb
        if not kb.unknowns():
            messagebox.showinfo(config.APP_NAME, "Aucun processus inconnu à exporter.",
                                parent=self.app)
            return
        path = filedialog.asksaveasfilename(
            parent=self.app, title="Exporter les inconnus", defaultextension=".txt",
            initialfile="processus_inconnus.txt", filetypes=[("Fichier texte", "*.txt")])
        if not path:
            return
        n = kb.export_unknowns(path)
        messagebox.showinfo(
            "Export terminé",
            f"{n} processus exportés dans :\n{path}\n\n"
            "1. Ouvrez ce fichier et copiez tout son contenu.\n"
            "2. Collez-le dans une conversation avec Claude.\n"
            "3. Enregistrez la réponse de Claude dans un fichier texte.\n"
            "4. Revenez ici et cliquez sur « Importer… ».", parent=self.app)

    def import_entries(self):
        path = filedialog.askopenfilename(
            parent=self.app, title="Importer les entrées complétées",
            filetypes=[("Texte ou JSON", "*.txt *.json"), ("Tous les fichiers", "*.*")])
        if not path:
            return
        try:
            ok, ignored = self.app.kb.import_file(path)
        except (OSError, ValueError) as ex:
            messagebox.showerror("Import impossible",
                                 f"Le fichier n'a pas pu être lu.\n\n{ex}", parent=self.app)
            return
        self.render()
        messagebox.showinfo("Import terminé",
                            f"{ok} entrée(s) importée(s)."
                            + (f"\n{ignored} entrée(s) ignorée(s) (incomplètes ou invalides)."
                               if ignored else "")
                            + "\nUne sauvegarde de la base a été faite avant l'import.",
                            parent=self.app)


class JournalPage(Page):
    def __init__(self, app):
        super().__init__(app, "Journal", "Historique de ce que SimpleTask a fermé.")
        self.table = Table(self.body, app, [
            {"key": "date", "title": "Date", "width": 160},
            {"key": "nom", "title": "Application", "width": 220, "stretch": True},
            {"key": "nb", "title": "Processus", "width": 90, "anchor": "e"},
            {"key": "ram", "title": "Mémoire libérée", "width": 130, "anchor": "e"},
            {"key": "resultat", "title": "Résultat", "width": 300, "stretch": True},
            {"key": "origine", "title": "Comment", "width": 160},
        ], empty_text="Rien n'a encore été fermé avec SimpleTask.", name="journal")
        self.table.pack(fill="both", expand=True)

    def apply_theme(self):
        self.table.apply_theme()

    def on_show(self):
        self.render()

    def render(self):
        rows = []
        for i, it in enumerate(reversed(self.app.journal.items)):
            rows.append({"id": i, "cells": {
                "date": it["date"], "nom": it["nom"], "nb": it["nb_processus"],
                "ram": f"{it['ram_mo']} Mo", "resultat": it["resultat"],
                "origine": it["origine"]}})
        self.table.set_rows(rows)


class SettingsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Réglages")
        self.scroll = ScrollFrame(self.body, app)
        self.scroll.pack(fill="both", expand=True)
        f = self.scroll.inner
        self.vars = {}
        P = app.px

        def section(title, text=""):
            ttk.Label(f, text=title, style="H2.TLabel").pack(anchor="w", pady=(P(18), P(2)))
            if text:
                ttk.Label(f, text=text, style="Small.TLabel", wraplength=P(820),
                          justify="left").pack(anchor="w", pady=(0, P(6)))
            box = ttk.Frame(f)
            box.pack(fill="x")
            return box

        # ---------- surveillance ----------
        box = section("Surveillance")
        fields = (
            ("rafraichissement_s", "Mise à jour de la liste toutes les (secondes)", 1, 30),
            ("seuil_cpu", "Badge « Gourmand » au-delà de (% du processeur)", 1, 100),
            ("seuil_ram_mo", "... ou au-delà de (Mo de mémoire)", 50, 32000),
            ("suspect_cpu", "Inconnu suspect s'il dépasse (% du processeur)", 5, 100),
            ("suspect_duree_s", "... pendant plus de (secondes)", 10, 3600),
        )
        for i, (k, label, lo, hi) in enumerate(fields):
            ttk.Label(box, text=label).grid(row=i, column=0, sticky="w", pady=P(3))
            v = tk.StringVar(value=str(app.settings[k]))
            ttk.Spinbox(box, from_=lo, to=hi, textvariable=v, width=8).grid(
                row=i, column=1, sticky="w", padx=P(12))
            self.vars[k] = (v, lo, hi)

        # ---------- liste blanche ----------
        box = section("Liste blanche", "Ces processus ne sont jamais proposés à la fermeture.")
        self.wl = tk.Listbox(box, height=5, relief="flat", font=app.font_normal,
                             highlightthickness=1, activestyle="none", width=50)
        app.themed(self.wl, "surface", "fg")
        self.wl.grid(row=0, column=0, sticky="w")
        ttk.Button(box, text="Retirer", command=self._remove_wl).grid(
            row=0, column=1, sticky="nw", padx=P(12))
        ttk.Button(f, text="Enregistrer ces réglages", style="Accent.TButton",
                   command=self.save).pack(anchor="w", pady=(P(12), 0))

        # ---------- assistant IA ----------
        box = section("Assistant IA (Google Gemini)",
                      "Fonction facultative : elle décrit les processus inconnus. SimpleTask "
                      "fonctionne entièrement sans elle. La clé n'est jamais écrite dans un "
                      "fichier : elle vient de la variable d'environnement GEMINI_API_KEY ou du "
                      "Gestionnaire d'identification Windows. Chaque utilisateur utilise sa "
                      "propre clé (gratuite sur aistudio.google.com).")
        self.ia_active = tk.BooleanVar(value=app.ia_cfg["active"])
        ttk.Checkbutton(box, text="Activer l'assistant IA", variable=self.ia_active,
                        style="Switch.TCheckbutton").grid(row=0, column=0, columnspan=3,
                                                          sticky="w", pady=P(4))
        ttk.Label(box, text="Clé API").grid(row=1, column=0, sticky="w", pady=P(4))
        self.key_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.key_var, show="•", width=42).grid(
            row=1, column=1, sticky="w", padx=P(12))
        kb_ = ttk.Frame(box)
        kb_.grid(row=1, column=2, sticky="w")
        ttk.Button(kb_, text="Enregistrer la clé", command=self._save_key).pack(side="left")
        ttk.Button(kb_, text="Supprimer", command=self._delete_key).pack(side="left",
                                                                         padx=P(6))
        self.key_status = ttk.Label(box, text="", style="Small.TLabel")
        self.key_status.grid(row=2, column=1, columnspan=2, sticky="w", padx=P(12))

        ttk.Label(box, text="Modèle").grid(row=3, column=0, sticky="w", pady=P(4))
        self.model_var = tk.StringVar(value=app.ia_cfg["modele"])
        self.model_cb = ttk.Combobox(box, textvariable=self.model_var, width=40)
        self.model_cb.grid(row=3, column=1, sticky="w", padx=P(12))
        mb = ttk.Frame(box)
        mb.grid(row=3, column=2, sticky="w")
        ttk.Button(mb, text="Lister les modèles disponibles", command=self._list_models).pack(
            side="left")
        ttk.Button(mb, text="Tester la connexion", command=self._test).pack(side="left",
                                                                            padx=P(6))
        ttk.Label(box, text="Modèles de secours").grid(row=4, column=0, sticky="w", pady=P(4))
        self.backup_var = tk.StringVar(value=", ".join(app.ia_cfg["modeles_secours"]))
        ttk.Entry(box, textvariable=self.backup_var, width=42).grid(row=4, column=1, sticky="w",
                                                                   padx=P(12))
        ttk.Label(box, text="séparés par des virgules ; essayés si le modèle principal est "
                            "saturé ou indisponible", style="Small.TLabel").grid(
            row=4, column=2, sticky="w")
        self.ia_vars = {}
        for i, (k, label, lo, hi) in enumerate((
                ("taille_lot", "Processus par requête (taille des lots)", 1, 25),
                ("delai_attente_s", "Délai d'attente d'une réponse (secondes)", 5, 180),
                ("tentatives_max", "Nombre maximal de tentatives par modèle", 1, 6),
                ("delai_relance_s", "Attente avant un nouvel essai (secondes, puis doublée)",
                 1, 60),
                ("pause_entre_lots_s", "Pause entre deux lots (secondes)", 0, 120))):
            ttk.Label(box, text=label).grid(row=5 + i, column=0, sticky="w", pady=P(3))
            v = tk.StringVar(value=f"{app.ia_cfg[k]:g}")
            ttk.Spinbox(box, from_=lo, to=hi, textvariable=v, width=8).grid(
                row=5 + i, column=1, sticky="w", padx=P(12))
            self.ia_vars[k] = (v, lo, hi)
        self.consent_lbl = ttk.Label(box, text="", style="Small.TLabel")
        self.consent_lbl.grid(row=10, column=0, columnspan=2, sticky="w", pady=(P(8), 0))
        ttk.Button(box, text="Retirer mon accord d'envoi", command=self._revoke).grid(
            row=10, column=2, sticky="w", pady=(P(8), 0))
        ttk.Button(f, text="Enregistrer les réglages de l'IA", style="Accent.TButton",
                   command=self.save_ia).pack(anchor="w", pady=(P(12), 0))
        ttk.Label(f, style="Small.TLabel", wraplength=P(820), text=(
            f"Fichier de configuration : {gemini.CONFIG_FILE}")).pack(anchor="w", pady=P(4))

        # ---------- système ----------
        box = section("Système et données")
        admin = actions.is_admin()
        ttk.Label(box, style="Small.TLabel", wraplength=P(820), text=(
            "SimpleTask fonctionne en administrateur." if admin else
            "SimpleTask fonctionne sans droits administrateur (suffisant pour lire). "
            "Certains processus ne peuvent être fermés qu'en administrateur.")).pack(anchor="w")
        bb = ttk.Frame(box)
        bb.pack(anchor="w", pady=P(8))
        if not admin:
            ttk.Button(bb, text="Relancer en administrateur", command=self._admin).pack(
                side="left", padx=(0, P(8)))
        ttk.Button(bb, text="Ouvrir le dossier des données",
                   command=lambda: os.startfile(config.DATA_DIR)).pack(side="left")
        ttk.Label(f, style="Small.TLabel", text=(
            f"Version {config.VERSION}. Sans l'assistant IA, rien ne quitte ce PC.")).pack(
            anchor="w", pady=(P(14), P(20)))

    def on_show(self):
        app = self.app
        self.wl.delete(0, "end")
        for n in app.settings["liste_blanche"]:
            self.wl.insert("end", n)
        self.wl.configure(highlightbackground=app.pal["border"],
                          selectbackground=app.pal["sel"], selectforeground=app.pal["fg"])
        self._refresh_key_status()
        c = app.settings.get("ia_consentement")
        self.consent_lbl.configure(text=f"Accord d'envoi à Google donné le {c}." if c else
                                   "Vous n'avez pas encore donné votre accord d'envoi.")

    def apply_theme(self):
        self.scroll.apply_theme()
        self.on_show()

    def _refresh_key_status(self):
        key, src = cle_api.get_key()
        if src == "environnement":
            t = f"Clé trouvée dans la variable GEMINI_API_KEY ({cle_api.mask(key)})."
        elif src == "windows":
            t = f"Clé enregistrée dans le Gestionnaire d'identification ({cle_api.mask(key)})."
        else:
            t = "Aucune clé configurée : l'assistant IA est indisponible."
        self.key_status.configure(text=t)

    def _save_key(self):
        k = self.key_var.get().strip()
        if not k:
            return
        try:
            cle_api.store(k)
        except (OSError, ValueError) as ex:
            messagebox.showerror(config.APP_NAME, str(ex), parent=self.app)
            return
        self.key_var.set("")
        self._refresh_key_status()

    def _delete_key(self):
        if messagebox.askyesno(config.APP_NAME, "Supprimer la clé enregistrée dans le "
                               "Gestionnaire d'identification Windows ?", parent=self.app):
            cle_api.delete()
            self._refresh_key_status()

    def _cfg_from_form(self):
        cfg = dict(self.app.ia_cfg)
        cfg["active"] = bool(self.ia_active.get())
        cfg["modele"] = self.model_var.get().strip().replace("models/", "")
        cfg["modeles_secours"] = [m.strip().replace("models/", "")
                                  for m in self.backup_var.get().split(",") if m.strip()]
        for k, (v, lo, hi) in self.ia_vars.items():
            try:
                val = float(v.get().replace(",", "."))
            except ValueError:
                continue
            val = min(max(val, lo), hi)
            cfg[k] = int(val) if k in ("taille_lot", "tentatives_max") else val
        return cfg

    def _client(self):
        key, _ = cle_api.get_key()
        cfg = self._cfg_from_form()
        cfg["active"] = True
        if not cfg["modele"]:
            cfg["modele"] = "-"
        return gemini.GeminiClient(cfg, key), key

    def _list_models(self):
        try:
            client, key = self._client()
        except gemini.GeminiError as e:
            messagebox.showinfo("Assistant IA", e.user_message(), parent=self.app)
            return
        self.key_status.configure(text="Interrogation de Google…")

        def done(models, err):
            self._refresh_key_status()
            if err:
                messagebox.showerror("Assistant IA", gemini.scrub(
                    getattr(err, "user_message", lambda: str(err))(), key), parent=self.app)
                return
            self.model_cb.configure(values=models)
            messagebox.showinfo("Assistant IA",
                                f"{len(models)} modèles disponibles pour votre clé. Choisissez-en "
                                "un dans la liste « Modèle » (les modèles « flash » ou "
                                "« flash-lite » conviennent et ont souvent un quota gratuit).",
                                parent=self.app)
        self.app._run_bg(client.list_models, done)

    def _test(self):
        try:
            client, key = self._client()
        except gemini.GeminiError as e:
            messagebox.showinfo("Assistant IA", e.user_message(), parent=self.app)
            return
        model = client.cfg["modele"]
        self.key_status.configure(text="Test en cours…")

        def done(models, err):
            self._refresh_key_status()
            if err:
                messagebox.showerror("Assistant IA", gemini.scrub(
                    getattr(err, "user_message", lambda: str(err))(), key), parent=self.app)
            elif model in models:
                messagebox.showinfo("Assistant IA", f"Connexion réussie. Le modèle « {model} » "
                                    "est disponible pour votre clé.", parent=self.app)
            else:
                messagebox.showwarning("Assistant IA", f"La clé fonctionne, mais le modèle "
                                       f"« {model} » n'est pas dans la liste de vos modèles. "
                                       "Choisissez-en un autre.", parent=self.app)
        self.app._run_bg(client.list_models, done)

    def _revoke(self):
        self.app.settings.pop("ia_consentement", None)
        config.save_settings(self.app.settings)
        self.on_show()

    def _remove_wl(self):
        for i in reversed(self.wl.curselection()):
            self.wl.delete(i)

    def _admin(self):
        if actions.relaunch_as_admin():
            self.app.on_quit()

    def save(self):
        s = self.app.settings
        for k, (v, lo, hi) in self.vars.items():
            try:
                val = float(v.get().replace(",", "."))
            except ValueError:
                continue
            val = min(max(val, lo), hi)
            s[k] = int(val) if k in ("rafraichissement_s", "seuil_ram_mo",
                                     "suspect_duree_s") else val
        s["liste_blanche"] = list(self.wl.get(0, "end"))
        config.save_settings(s)
        self.app.status.configure(text="Réglages enregistrés.")

    def save_ia(self):
        cfg = self._cfg_from_form()
        gemini.save_config(cfg)
        self.app.ia_cfg = gemini.load_config()
        self.app.pages["ia"].on_show()
        self.app.status.configure(text="Réglages de l'assistant IA enregistrés.")


# ==================================================================== dialogues
class Dialog(tk.Toplevel):
    def __init__(self, app, title):
        super().__init__(app)
        self.app = app
        self.title(title)
        self.configure(bg=app.pal["bg"])
        self.transient(app)
        self.resizable(False, False)
        self.body = ttk.Frame(self, padding=app.px(20))
        self.body.pack(fill="both", expand=True)

    def show(self):
        self.update_idletasks()
        x = self.app.winfo_rootx() + (self.app.winfo_width() - self.winfo_width()) // 2
        y = self.app.winfo_rooty() + (self.app.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dark_title_bar(self, self.app.settings["theme"] == "sombre")
        self.grab_set()
        self.focus_set()

    def text_box(self, parent, height, value="", width=64):
        app = self.app
        t = tk.Text(parent, width=width, height=height, wrap="word", font=app.font_normal,
                    bg=app.pal["surface"], fg=app.pal["fg"], insertbackground=app.pal["fg"],
                    relief="flat", highlightthickness=1,
                    highlightbackground=app.pal["border"], highlightcolor=app.pal["accent"],
                    padx=app.px(8), pady=app.px(6))
        t.insert("1.0", value)
        return t


class EditDialog(Dialog):
    def __init__(self, app, name, on_save=None):
        super().__init__(app, "Modifier l'explication")
        self.name, self.on_save = name, on_save
        e = app.kb.get(name) or {}
        b = self.body
        P = app.px
        ttk.Label(b, text=name, style="H2.TLabel").grid(row=0, column=0, columnspan=2,
                                                        sticky="w", pady=(0, P(10)))
        ttk.Label(b, text="Ce que c'est (une phrase simple) :").grid(row=1, column=0,
                                                                     columnspan=2, sticky="w")
        self.desc = self.text_box(b, 3, e.get("description", ""))
        self.desc.grid(row=2, column=0, columnspan=2, sticky="we", pady=(P(4), P(10)))
        ttk.Label(b, text="Catégorie :").grid(row=3, column=0, sticky="nw")
        self.cat = tk.StringVar(value=e.get("categorie", "inconnu"))
        cf = ttk.Frame(b)
        cf.grid(row=3, column=1, sticky="w")
        for val, txt in (("vital", "Vital : ne jamais fermer"),
                         ("peut_etre_ferme", "Peut être fermé"),
                         ("inconnu", "Inconnu : je ne sais pas encore")):
            ttk.Radiobutton(cf, text=txt, value=val, variable=self.cat).pack(anchor="w")
        ttk.Label(b, text="Risque si on le ferme :").grid(row=4, column=0, sticky="w", pady=P(8))
        self.risque = tk.StringVar(value=RISQUE_LABEL.get(e.get("risque", ""), "—"))
        ttk.Combobox(b, textvariable=self.risque, state="readonly", width=12,
                     values=["Aucun", "Faible", "Élevé"]).grid(row=4, column=1, sticky="w")
        ttk.Label(b, text="Éditeur :").grid(row=5, column=0, sticky="w")
        self.edit = tk.StringVar(value=e.get("editeur", ""))
        ttk.Entry(b, textvariable=self.edit, width=40).grid(row=5, column=1, sticky="w")
        if e.get("chemin"):
            ttk.Label(b, text=f"Emplacement : {e['chemin']}", style="Small.TLabel",
                      wraplength=P(520)).grid(row=6, column=0, columnspan=2, sticky="w",
                                              pady=P(8))
        bf = ttk.Frame(b)
        bf.grid(row=7, column=0, columnspan=2, sticky="e", pady=(P(12), 0))
        ttk.Button(bf, text="Annuler", command=self.destroy).pack(side="right")
        ttk.Button(bf, text="Enregistrer", style="Accent.TButton",
                   command=self.save).pack(side="right", padx=P(8))
        self.show()

    def save(self):
        risque = {"Aucun": "aucun", "Faible": "faible", "Élevé": "eleve"}.get(self.risque.get())
        self.app.kb.update_entry(self.name, self.desc.get("1.0", "end"), self.cat.get(),
                                 risque, self.edit.get())
        self.destroy()
        if self.on_save:
            self.on_save()


class FreeRamDialog(Dialog):
    def __init__(self, app, rows):
        super().__init__(app, "Libérer de la RAM")
        self.rows = rows
        b = self.body
        P = app.px
        ttk.Label(b, text="Libérer de la mémoire", style="H2.TLabel").pack(anchor="w")
        ttk.Label(b, wraplength=P(560), justify="left", style="Small.TLabel", text=(
            "Ces applications peuvent être fermées. Décochez celles que vous utilisez : ce qui "
            "n'y est pas enregistré sera perdu. Les processus vitaux, inconnus, suspects et ceux "
            "de la liste blanche ne sont jamais proposés.")).pack(anchor="w", pady=(P(4), P(12)))
        self.vars = []
        for r in rows:
            # les éléments à risque « faible » arrêtent une fonction : décochés par défaut
            v = tk.BooleanVar(value=r.entry.get("risque") != "faible")
            v.trace_add("write", lambda *a: self._update_total())
            txt = f"{r.display}  —  {fmt_mo(r.g.ram)}"
            if r.entry.get("risque") == "faible":
                txt += "   (une fonction s'arrêtera)"
            ttk.Checkbutton(b, text=txt, variable=v).pack(anchor="w", pady=1)
            self.vars.append(v)
        self.total = ttk.Label(b, font=app.font_bold)
        self.total.pack(anchor="w", pady=P(12))
        bf = ttk.Frame(b)
        bf.pack(fill="x")
        ttk.Button(bf, text="Annuler", command=self.destroy).pack(side="right")
        self.ok = ttk.Button(bf, text="Fermer la sélection", style="Accent.TButton",
                             command=self.confirm)
        self.ok.pack(side="right", padx=P(8))
        self._update_total()
        self.show()

    def _chosen(self):
        return [r for r, v in zip(self.rows, self.vars) if v.get()]

    def _update_total(self):
        ch = self._chosen()
        self.total.configure(text=f"{len(ch)} application(s) choisie(s) · environ "
                                  f"{fmt_mo(sum(r.g.ram for r in ch))} libérés")
        self.ok.state(["!disabled"] if ch else ["disabled"])

    def confirm(self):
        ch = self._chosen()
        if not ch:
            return
        self.destroy()
        self.app.close_groups(ch, "Libérer de la RAM")


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    app = App()
    app.mainloop()
