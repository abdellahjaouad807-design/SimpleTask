"""Composants visuels modernes : liste dessinée (style Gestionnaire de tâches de Windows 11),
graphiques, menu latéral, cartes. Tout est dessiné avec Tkinter, sans dépendance lourde."""
import tkinter as tk
from collections import deque
from tkinter import font as tkfont
from tkinter import ttk

PALETTES = {
    "sombre": dict(
        bg="#1c1c1c", side="#202020", surface="#2b2b2b", surface2="#333333",
        fg="#ffffff", muted="#a6a6a6", faint="#6e6e6e", border="#3a3a3a",
        accent="#4cc2ff", accent_fg="#000000", sel="#1f3a4f", hover="#2f2f2f",
        heat_lo="#2b2b2b", heat_hi="#8a6a12", header="#202020",
        danger="#ff6b6b", ok="#4fd18b", warn="#ffa94d", ia="#c9a6ff",
        chart_cpu="#4cc2ff", chart_ram="#c9a6ff", grid="#333333"),
    "clair": dict(
        bg="#fafafa", side="#f0f0f0", surface="#ffffff", surface2="#f5f5f5",
        fg="#1b1b1b", muted="#5f5f5f", faint="#9a9a9a", border="#e3e3e3",
        accent="#005fb8", accent_fg="#ffffff", sel="#d6e9fa", hover="#f2f2f2",
        heat_lo="#ffffff", heat_hi="#ffd04a", header="#fafafa",
        danger="#c4314b", ok="#107c41", warn="#c75000", ia="#7a3fc2",
        chart_cpu="#0f6cbd", chart_ram="#8a3fd1", grid="#e8e8e8"),
}

CAT_COLORS = {
    "vital": "#e5484d", "peut_etre_ferme": "#30a46c", "inconnu": "#8b8d98", "suspect": "#f76b15",
}


def pick_font(root, *families):
    available = set(tkfont.families(root))
    for f in families:
        if f in available:
            return f
    return families[-1]


def follow_width(frame, labels, margin=10):
    """Adapte le retour à la ligne des textes à la largeur du cadre, une seule fois par
    redimensionnement (les événements de taille arrivent en rafale pendant un agrandissement)."""
    state = {"pending": None, "width": 0}

    def apply():
        state["pending"] = None
        w = frame.winfo_width()
        if abs(w - state["width"]) < 8:
            return
        state["width"] = w
        for lbl in labels:
            lbl.configure(wraplength=max(w - margin, 200))

    def on_configure(_):
        if state["pending"] is None:
            state["pending"] = frame.after_idle(apply)

    frame.bind("<Configure>", on_configure, add="+")


def blend(c1, c2, t):
    """Mélange deux couleurs #rrggbb (t = 0 -> c1, t = 1 -> c2)."""
    t = min(max(t, 0.0), 1.0)
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


class Table(tk.Frame):
    """Liste rapide dessinée sur un Canvas : seules les lignes visibles sont dessinées.

    columns : [{"key", "title", "width", "anchor" ("w"/"e"), "stretch", "kind"}]
      kind : "name" (pastille + texte), "pill" (étiquette colorée), "heat" (fond coloré
      selon la valeur, comme le Gestionnaire de tâches), "text".
    rows : [{"id", "cells": {clé: texte}, "dot": couleur, "pill": {clé: (texte, couleur)},
             "heat": {clé: 0..1}, "fg": {clé: couleur}, "italic": {clés}}]
    """

    GRIP = 6  # pixels autour d'une séparation d'en-tête où l'on peut tirer

    def __init__(self, master, app, columns, on_select=None, on_double=None,
                 on_context=None, on_sort=None, empty_text="Rien à afficher.", name=None):
        super().__init__(master, highlightthickness=0, bd=0)
        self.app, self.name = app, name
        self.defaults = [dict(c) for c in columns]
        self.columns = [dict(c) for c in columns]
        hidden = set((app.settings.get("colonnes_masquees") or {}).get(name, [])) if name else ()
        for c in self.columns[1:]:  # la 1re colonne (le nom) reste toujours visible
            c["hidden"] = c["key"] in hidden
        saved = (app.settings.get("colonnes") or {}).get(name) if name else None
        if saved:
            self._apply_widths(saved)
        self.on_select, self.on_double = on_select, on_double
        self.on_context, self.on_sort = on_context, on_sort
        self.empty_text = empty_text
        self.rows, self.index = [], {}
        self.selected = None
        self.hover = None
        self.offset = 0
        self.sort_key, self.sort_desc = None, True
        self.header_extra = {}
        self._fit_cache = {}
        self._text_w = {}       # (texte, police) -> largeur en pixels
        self._draw_pending = None
        self._bg_items = {}     # id de ligne -> rectangle de fond (pour le survol)
        self._drag = None
        self.head = tk.Canvas(self, highlightthickness=0, bd=0)
        self.body = tk.Canvas(self, highlightthickness=0, bd=0, takefocus=1)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self._on_scrollbar)
        self.head.grid(row=0, column=0, sticky="we")
        self.body.grid(row=1, column=0, sticky="nsew")
        self.sb.grid(row=0, column=1, rowspan=2, sticky="ns")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        b = self.body
        b.bind("<Configure>", lambda e: self.request_draw())
        b.bind("<Button-1>", self._click)
        b.bind("<Double-1>", self._double)
        b.bind("<Button-3>", self._context)
        b.bind("<Motion>", self._motion)
        b.bind("<Leave>", lambda e: self._set_hover(None))
        b.bind("<MouseWheel>", self._wheel)
        b.bind("<Up>", lambda e: self._step(-1))
        b.bind("<Down>", lambda e: self._step(1))
        h = self.head
        h.bind("<Button-1>", self._head_press)
        h.bind("<B1-Motion>", self._head_drag)
        h.bind("<ButtonRelease-1>", self._head_release)
        h.bind("<Motion>", self._head_motion)
        h.bind("<Double-1>", self._head_double)
        h.bind("<Button-3>", self._head_menu)
        h.bind("<Configure>", lambda e: self.request_draw())
        b.bind("<Map>", lambda e: self.request_draw())
        self.apply_theme()

    def request_draw(self):
        """Regroupe les demandes de dessin : un seul dessin par passage de la boucle."""
        if self._draw_pending is None:
            self._draw_pending = self.after_idle(self._do_draw)

    def _do_draw(self):
        self._draw_pending = None
        w = self.head.winfo_width()
        if w != getattr(self, "_head_w", None):  # en-tête redessiné seulement si la largeur change
            self._head_w = w
            self.draw_header()
        self.draw()

    def destroy(self):
        if self._draw_pending is not None:
            self.after_cancel(self._draw_pending)
            self._draw_pending = None
        super().destroy()

    @property
    def vis(self):
        """Colonnes affichées."""
        return [c for c in self.columns if not c.get("hidden")]

    # ---------- colonnes affichées (clic droit sur l'en-tête) ----------
    def _head_menu(self, e):
        m = tk.Menu(self, tearoff=0)
        self._menu_vars = []
        for c in self.columns[1:]:
            v = tk.BooleanVar(value=not c.get("hidden"))
            self._menu_vars.append(v)
            m.add_checkbutton(label=c.get("menu", c["title"]), variable=v,
                              command=lambda c=c, v=v: self.set_hidden(c["key"], not v.get()))
        m.add_separator()
        m.add_command(label="Largeurs d'origine", command=self.reset_widths)
        m.tk_popup(e.x_root, e.y_root)

    def set_hidden(self, key, hidden):
        for c in self.columns:
            if c["key"] == key and c is not self.columns[0]:
                c["hidden"] = hidden
        if self.name and self.name in (self.app.settings.get("colonnes") or {}):
            self._apply_widths({c["key"]: c["width"] for c in self.columns})
        if self.name:
            self.app.settings.setdefault("colonnes_masquees", {})[self.name] = [
                c["key"] for c in self.columns if c.get("hidden")]
            self.app.save_settings()
        self._fit_cache.clear()
        self.draw_header()
        self.request_draw()

    # ---------- largeur des colonnes (glisser les séparations de l'en-tête) ----------
    def _apply_widths(self, widths):
        """Largeurs choisies par l'utilisateur : la dernière colonne affichée prend la place
        restante."""
        for c in self.columns:
            if c["key"] in widths:
                c["width"] = max(30, float(widths[c["key"]]))
            c["stretch"] = False
        vis = self.vis
        if vis:
            vis[-1]["stretch"] = True

    def reset_widths(self):
        hidden = {c["key"]: c.get("hidden", False) for c in self.columns}
        self.columns = [dict(c, hidden=hidden[c["key"]]) for c in self.defaults]
        if self.name:
            (self.app.settings.get("colonnes") or {}).pop(self.name, None)
            self.app.save_settings()
        self._fit_cache.clear()
        self.draw_header()
        self.request_draw()

    def _boundary_at(self, x):
        cols = self._layout(self.head.winfo_width())
        for i, (cx, w) in enumerate(cols[:-1]):
            if abs(x - (cx + w)) <= self.GRIP * self.app.k:
                return i, cols
        return None, cols

    def _head_motion(self, e):
        i, _ = self._boundary_at(e.x)
        self.head.configure(cursor="sb_h_double_arrow" if i is not None else "")

    def _head_press(self, e):
        i, cols = self._boundary_at(e.x)
        self._drag = (i, e.x, [w for _, w in cols]) if i is not None else None
        self._press_x = e.x
        self._dragged = False

    def _head_drag(self, e):
        if not self._drag:
            return
        i, x0, widths = self._drag
        k = self.app.k
        minw = 50 * k
        dx = e.x - x0
        dx = max(dx, minw - widths[i])           # la colonne de gauche garde un minimum
        dx = min(dx, widths[i + 1] - minw)       # celle de droite aussi
        new = list(widths)
        new[i] += dx
        new[i + 1] -= dx
        self._apply_widths({c["key"]: w / k for c, w in zip(self.vis, new)})
        self._dragged = True
        self.draw_header()
        self.request_draw()

    def _head_release(self, e):
        if self._drag:
            if self._dragged and self.name:
                self.app.settings.setdefault("colonnes", {})[self.name] = {
                    c["key"]: round(c["width"], 1) for c in self.columns}
                self.app.save_settings()
            self._drag = None
            return
        self._head_click(e)

    def _head_double(self, e):
        """Double-clic sur une séparation : largeurs d'origine."""
        i, _ = self._boundary_at(e.x)
        if i is not None:
            self.reset_widths()

    # ---------- apparence ----------
    def apply_theme(self):
        p = self.app.pal
        self.configure(bg=p["surface"])
        self.head.configure(bg=p["header"])
        self.body.configure(bg=p["surface"])
        self.f = self.app.font_normal
        self.fb = self.app.font_bold
        self.fs = self.app.font_small
        self.fi = self.app.font_italic
        self.row_h = int(self.f.metrics("linespace") * 2.0)
        self.head_h = int(self.f.metrics("linespace") * 2.9)
        self.head.configure(height=self.head_h)
        self._fit_cache.clear()
        self._text_w.clear()
        self.draw_header()
        self.draw()

    def _layout(self, width):
        """Position (x, largeur) de chaque colonne affichée."""
        k = self.app.k
        vis = self.vis
        stretch = [c for c in vis if c.get("stretch")] or vis[-1:]
        fixed = sum(int(c["width"] * k) for c in vis if c not in stretch)
        base = sum(int(c["width"] * k) for c in stretch) or 1
        if fixed + base > width:
            # pas assez de place : toutes les colonnes rétrécissent ensemble
            k *= width / (fixed + base)
            fixed = sum(int(c["width"] * k) for c in vis if c not in stretch)
            base = sum(int(c["width"] * k) for c in stretch) or 1
        extra = max(width - fixed, base)
        xs, x = [], 0
        for c in vis:
            w = int(c["width"] * k)
            if c in stretch:
                w = int(extra * (c["width"] * k) / base)
            xs.append((x, w))
            x += w
        return xs

    def _fit(self, text, width, font):
        key = (text, width, str(font))
        r = self._fit_cache.get(key)
        if r is not None:
            return r
        if len(self._fit_cache) > 6000:
            self._fit_cache.clear()
        # largeur complète du texte mesurée une seule fois, quelle que soit la colonne :
        # un redimensionnement ne refait pas toutes les mesures
        wkey = (text, str(font))
        full = self._text_w.get(wkey)
        if full is None:
            if len(self._text_w) > 6000:
                self._text_w.clear()
            full = self._text_w[wkey] = font.measure(text)
        if full <= width:
            r = text
        elif width <= 0 or not text:
            r = ""
        else:
            # estimation proportionnelle, puis ajustement de quelques caractères
            n = max(0, min(len(text), int(len(text) * width / full)))
            while n > 0 and font.measure(text[:n] + "…") > width:
                n -= max(1, n // 12)
            while n < len(text) and font.measure(text[:n + 1] + "…") <= width:
                n += 1
            r = text[:n] + "…" if n else ""
        self._fit_cache[key] = r
        return r

    def set_header_extra(self, key, text):
        if self.header_extra.get(key) != text:
            self.header_extra[key] = text
            self.draw_header()

    def set_sort(self, key, desc):
        self.sort_key, self.sort_desc = key, desc
        self.draw_header()

    def draw_header(self):
        p, h = self.app.pal, self.head
        h.delete("all")
        width = h.winfo_width()
        if width < 10:
            return
        pad = int(10 * self.app.k)
        for c, (x, w) in zip(self.vis,self._layout(width)):
            anchor = c.get("anchor", "w")
            tx = x + pad if anchor == "w" else x + w - pad
            extra = self.header_extra.get(c["key"])
            title = c["title"]
            if self.sort_key == c["key"]:
                title += "  ↓" if self.sort_desc else "  ↑"
            if extra:
                h.create_text(tx, self.head_h * 0.36, text=extra, anchor=anchor,
                              fill=p["fg"], font=self.app.font_header_value)
                h.create_text(tx, self.head_h * 0.74, text=self._fit(title, w - 2 * pad, self.fs),
                              anchor=anchor, fill=p["muted"], font=self.fs)
            else:
                h.create_text(tx, self.head_h * 0.74, text=self._fit(title, w - 2 * pad, self.fs),
                              anchor=anchor, fill=p["muted"], font=self.fs)
            if x:
                h.create_line(x, self.head_h * 0.25, x, self.head_h, fill=p["border"])
        h.create_line(0, self.head_h - 1, width, self.head_h - 1, fill=p["border"])

    # ---------- données ----------
    def set_rows(self, rows):
        self.rows = rows
        self.index = {r["id"]: i for i, r in enumerate(rows)}
        self._clamp()
        self.request_draw()

    def select(self, rid, notify=True):
        self.selected = rid
        self.draw()
        if notify and self.on_select:
            self.on_select(rid)

    def selected_row(self):
        i = self.index.get(self.selected)
        return self.rows[i] if i is not None else None

    # ---------- dessin ----------
    def draw(self):
        p, b = self.app.pal, self.body
        if not b.winfo_viewable() and getattr(self.app, "visible_only", True):
            return  # page cachée ou fenêtre réduite : rien à dessiner (redessiné à l'affichage)
        b.delete("all")
        self._bg_items = {}
        width, height = b.winfo_width(), b.winfo_height()
        if width < 10:
            return
        if not self.rows:
            b.create_text(width / 2, height / 3, text=self.empty_text, fill=p["muted"],
                          font=self.f, width=width * 0.8, justify="center")
            self._update_scrollbar(height)
            return
        cols = self._layout(width)
        pad = int(10 * self.app.k)
        first = max(self.offset // self.row_h, 0)
        last = min(len(self.rows), first + height // self.row_h + 2)
        dot_r = max(4, int(self.row_h * 0.16))
        for i in range(first, last):
            r = self.rows[i]
            y0 = i * self.row_h - self.offset
            y1 = y0 + self.row_h
            ym = (y0 + y1) / 2
            if r.get("section"):  # titre de section : « Applications (5) »
                b.create_rectangle(0, y0, width, y1, fill=p["surface"], outline="")
                for c, (x, w) in zip(self.vis, cols):
                    if c.get("kind") == "heat":
                        b.create_rectangle(x, y0, x + w, y1, outline="",
                                           fill=blend(p["heat_lo"], p["heat_hi"], 0.06))
                b.create_text(pad, y1 - self.row_h * 0.3, text=r["section"], anchor="sw",
                              fill=p["accent"], font=self.app.font_header_value)
                continue
            if r["id"] == self.selected:
                bg = p["sel"]
            elif r["id"] == self.hover:
                bg = p["hover"]
            else:
                bg = p["surface"]
            self._bg_items[r["id"]] = b.create_rectangle(0, y0, width, y1, fill=bg, outline="")
            heat = r.get("heat", {})
            for c, (x, w) in zip(self.vis,cols):
                key, kind = c["key"], c.get("kind", "text")
                if kind == "heat" and key in heat and r["id"] != self.selected:
                    b.create_rectangle(x, y0, x + w, y1 - 1, outline="",
                                       fill=blend(p["heat_lo"], p["heat_hi"], heat[key]))
                text = str(r["cells"].get(key, ""))
                fg = r.get("fg", {}).get(key, p["fg"])
                font = self.fi if key in r.get("italic", ()) else self.f
                anchor = c.get("anchor", "w")
                if kind == "name":
                    dot = r.get("dot")
                    tx = x + pad
                    icon = r.get("icon")
                    if icon:
                        b.create_image(tx, ym, image=icon, anchor="w")
                        tx += icon.width() + pad
                    elif dot:
                        b.create_oval(tx, ym - dot_r, tx + 2 * dot_r, ym + dot_r, fill=dot,
                                      outline="")
                        tx += 2 * dot_r + pad
                    b.create_text(tx, ym, text=self._fit(text, x + w - tx - pad, font),
                                  anchor="w", fill=fg, font=font)
                elif kind == "pill" and key in r.get("pill", {}):
                    label, color = r["pill"][key]
                    t = self._fit(label, w - 4 * pad, self.fs)
                    tw = self.fs.measure(t) + 2 * pad
                    ph = self.row_h * 0.62
                    px0 = x + pad
                    b.create_rectangle(px0, ym - ph / 2, px0 + tw, ym + ph / 2, outline="",
                                       fill=blend(bg, color, 0.22))
                    b.create_text(px0 + pad, ym, text=t, anchor="w", fill=color, font=self.fs)
                    sub = r["cells"].get(key, "")
                    if sub:
                        b.create_text(px0 + tw + pad / 2, ym, anchor="w", fill=p["warn"],
                                      font=self.fs,
                                      text=self._fit(sub, x + w - px0 - tw - pad, self.fs))
                else:
                    tx = x + pad if anchor == "w" else x + w - pad
                    b.create_text(tx, ym, text=self._fit(text, w - 2 * pad, font),
                                  anchor=anchor, fill=fg, font=font)
            b.create_line(0, y1 - 1, width, y1 - 1, fill=p["surface2"])
        self._update_scrollbar(height)

    # ---------- défilement ----------
    def _content_h(self):
        return len(self.rows) * self.row_h

    def _clamp(self):
        h = self.body.winfo_height()
        self.offset = int(min(max(self.offset, 0), max(self._content_h() - h, 0)))

    def _update_scrollbar(self, height):
        total = max(self._content_h(), 1)
        self.sb.set(self.offset / total, min((self.offset + height) / total, 1.0))

    def _on_scrollbar(self, *args):
        h = self.body.winfo_height()
        if args[0] == "moveto":
            self.offset = int(float(args[1]) * self._content_h())
        elif args[0] == "scroll":
            step = self.row_h if args[2] == "units" else h
            self.offset += int(args[1]) * step
        self._clamp()
        self.request_draw()

    def _wheel(self, e):
        self.offset -= int(e.delta / 120) * self.row_h * 3
        self._clamp()
        self.request_draw()

    def _row_at(self, y):
        """Ligne sous la souris (les titres de section ne se sélectionnent pas)."""
        i = int((y + self.offset) // self.row_h)
        if 0 <= i < len(self.rows) and not self.rows[i].get("section"):
            return self.rows[i]["id"]
        return None

    def _set_hover(self, rid):
        """Survol : on recolore seulement les deux lignes concernées (pas tout le dessin)."""
        if rid == self.hover:
            return
        p = self.app.pal
        old, self.hover = self.hover, rid
        for r, color in ((old, p["surface"]), (rid, p["hover"])):
            item = self._bg_items.get(r)
            if item and r != self.selected:
                self.body.itemconfigure(item, fill=color)

    def _motion(self, e):
        self._set_hover(self._row_at(e.y))

    def _click(self, e):
        self.body.focus_set()
        rid = self._row_at(e.y)
        if rid is not None:
            self.select(rid)

    def _double(self, e):
        rid = self._row_at(e.y)
        if rid is not None and self.on_double:
            self.on_double(rid)

    def _context(self, e):
        rid = self._row_at(e.y)
        if rid is not None:
            self.select(rid)
            if self.on_context:
                self.on_context(rid, e)

    def _step(self, d):
        if not self.rows:
            return
        i = self.index.get(self.selected, -1) + d
        while 0 <= i < len(self.rows) and self.rows[i].get("section"):
            i += d  # on saute les titres de section
        if not 0 <= i < len(self.rows):
            return
        self.select(self.rows[i]["id"])
        y = i * self.row_h
        h = self.body.winfo_height()
        if y < self.offset:
            self.offset = y
        elif y + self.row_h > self.offset + h:
            self.offset = y + self.row_h - h
        self._clamp()
        self.draw()

    def _head_click(self, e):
        if not self.on_sort:
            return
        for c, (x, w) in zip(self.vis,self._layout(self.head.winfo_width())):
            if x <= e.x < x + w and c.get("sortable", True):
                self.on_sort(c["key"])
                return


class LineChart(tk.Canvas):
    """Courbe des 60 dernières mesures, remplie, avec grille légère."""

    def __init__(self, master, app, color_key, maxlen=60):
        super().__init__(master, highlightthickness=0, bd=0)
        self.app, self.color_key = app, color_key
        self.values = deque(maxlen=maxlen)
        self._pending = None
        self.bind("<Configure>", lambda e: self._schedule())

    def _schedule(self):
        """Un seul dessin par rafale de redimensionnement."""
        if self._pending is None:
            self._pending = self.after_idle(self._redraw)

    def _redraw(self):
        self._pending = None
        self.draw()

    def push(self, v):
        self.values.append(v)
        self.draw()

    def draw(self):
        p = self.app.pal
        self.configure(bg=p["surface"])
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 10:
            return
        color = p[self.color_key]
        for i in range(1, 4):
            y = h * i / 4
            self.create_line(0, y, w, y, fill=p["grid"])
        n = self.values.maxlen
        for i in range(1, 6):
            x = w * i / 6
            self.create_line(x, 0, x, h, fill=p["grid"])
        self.create_rectangle(0, 0, w - 1, h - 1, outline=blend(p["surface"], color, 0.5))
        vals = list(self.values)
        if len(vals) < 2:
            return
        step = w / (n - 1)
        x0 = w - step * (len(vals) - 1)
        pts = [(x0 + i * step, h - 2 - (h - 4) * min(max(v, 0), 100) / 100)
               for i, v in enumerate(vals)]
        poly = [(pts[0][0], h)] + pts + [(pts[-1][0], h)]
        self.create_polygon(*[c for pt in poly for c in pt], fill=blend(p["surface"], color, 0.25),
                            outline="")
        self.create_line(*[c for pt in pts for c in pt], fill=color, width=2 * self.app.k,
                         smooth=False)


class Sparkline(LineChart):
    def draw(self):
        p = self.app.pal
        bg = p["surface"]
        self.configure(bg=bg)
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        vals = list(self.values)
        if w < 10 or len(vals) < 2:
            return
        color = p[self.color_key]
        step = w / (self.values.maxlen - 1)
        x0 = w - step * (len(vals) - 1)
        pts = [(x0 + i * step, h - 1 - (h - 2) * min(max(v, 0), 100) / 100)
               for i, v in enumerate(vals)]
        poly = [(pts[0][0], h)] + pts + [(pts[-1][0], h)]
        self.create_polygon(*[c for pt in poly for c in pt], fill=blend(bg, color, 0.2),
                            outline="")
        self.create_line(*[c for pt in pts for c in pt], fill=color, width=1.5 * self.app.k)


class FlatButton(tk.Label):
    """Bouton plat façon Windows 11, beaucoup plus léger à repeindre que les boutons à
    images du thème (utile quand on agrandit la fenêtre). Même usage qu'un ttk.Button :
    command=, configure(text=...), state(["disabled"]) / state(["!disabled"])."""

    def __init__(self, master, app, text="", command=None, accent=False, style=None):
        super().__init__(master, text=text, cursor="hand2", font=app.font_normal,
                         padx=int(12 * app.k), pady=int(4 * app.k), bd=0,
                         highlightthickness=1)
        self.app, self.command = app, command
        self.accent = accent or style == "Accent.TButton"
        self.disabled = self.hovered = self.pressed = False
        self.bind("<Enter>", lambda e: self._set(hovered=True))
        self.bind("<Leave>", lambda e: self._set(hovered=False, pressed=False))
        self.bind("<ButtonPress-1>", lambda e: self._set(pressed=True))
        self.bind("<ButtonRelease-1>", self._release)
        app._flat_buttons.append(self)
        self.apply_theme()

    def _set(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self.apply_theme()

    def _release(self, e):
        inside = 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height()
        self._set(pressed=False)
        if inside and not self.disabled and self.command:
            self.command()

    def state(self, spec=None):
        if spec is None:
            return ("disabled",) if self.disabled else ()
        for s in spec:
            if s == "disabled":
                self.disabled = True
            elif s == "!disabled":
                self.disabled = False
        self.configure(cursor="arrow" if self.disabled else "hand2")
        self.apply_theme()

    def apply_theme(self):
        p = self.app.pal
        if self.accent:
            bg = p["accent"] if not self.disabled else p["surface2"]
            if self.hovered and not self.disabled:
                bg = blend(p["accent"], p["bg"], 0.15 if not self.pressed else 0.3)
            fg = p["accent_fg"] if not self.disabled else p["faint"]
            border = bg
        else:
            bg = p["surface"]
            if self.hovered and not self.disabled:
                bg = p["surface2"] if not self.pressed else p["hover"]
            fg = p["faint"] if self.disabled else p["fg"]
            border = p["border"]
        self.configure(bg=bg, fg=fg, activebackground=bg, highlightbackground=border,
                       highlightcolor=border)


class NavItem(tk.Frame):
    """Entrée du menu latéral : icône + texte, barre d'accent quand elle est active."""

    def __init__(self, master, app, icon, text, command):
        super().__init__(master, cursor="hand2", highlightthickness=0, bd=0)
        self.app, self.command, self.active, self.hovered = app, command, False, False
        self.bar = tk.Frame(self, width=max(3, int(3 * app.k)))
        self.bar.pack(side="left", fill="y", pady=int(8 * app.k))
        self.icon = tk.Label(self, text=icon, font=app.font_icon, width=2)
        self.icon.pack(side="left", padx=(int(10 * app.k), int(8 * app.k)),
                       pady=int(9 * app.k))
        self.label = tk.Label(self, text=text, font=app.font_normal, anchor="w")
        self.label.pack(side="left", fill="x", expand=True)
        self.badge = tk.Label(self, text="", font=app.font_small)
        self.badge.pack(side="right", padx=int(10 * app.k))
        for w in (self, self.icon, self.label, self.badge, self.bar):
            w.bind("<Button-1>", lambda e: self.command())
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))
        self.apply_theme()

    def _hover(self, on):
        self.hovered = on
        self.apply_theme()

    def set_active(self, on):
        self.active = on
        self.apply_theme()

    def set_badge(self, text):
        self.badge.configure(text=text)

    def apply_theme(self):
        p = self.app.pal
        bg = p["surface2"] if self.active else (p["hover"] if self.hovered else p["side"])
        for w in (self, self.icon, self.label, self.badge):
            w.configure(bg=bg)
        self.icon.configure(fg=p["accent"] if self.active else p["fg"])
        self.label.configure(fg=p["fg"], font=self.app.font_bold if self.active
                             else self.app.font_normal)
        self.badge.configure(fg=p["muted"])
        self.bar.configure(bg=p["accent"] if self.active else bg)


class ScrollFrame(tk.Frame):
    """Zone défilante verticale (pour les réglages)."""

    def __init__(self, master, app):
        super().__init__(master, highlightthickness=0, bd=0)
        self.app = app
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self.win, width=e.width))
        self.bind_all("<MouseWheel>", self._wheel, add="+")
        self.apply_theme()

    def _wheel(self, e):
        w = self.winfo_containing(e.x_root, e.y_root)
        while w is not None:
            if w is self:
                self.canvas.yview_scroll(int(-e.delta / 120), "units")
                return
            w = getattr(w, "master", None)

    def apply_theme(self):
        self.canvas.configure(bg=self.app.pal["bg"])
        self.configure(bg=self.app.pal["bg"])
