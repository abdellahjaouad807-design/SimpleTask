"""Fermeture des processus (avec garde-fous), droits administrateur, journal."""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime

import psutil

from . import config, safety

WM_CLOSE = 0x0010
_user32 = ctypes.windll.user32
_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class Refused(Exception):
    """Fermeture interdite par un garde-fou."""


def can_close(name, category, is_self=False):
    """Retourne (autorisé, raison si refusé). Vérifié juste avant chaque fermeture."""
    if is_self:
        return False, "C'est SimpleTask lui-même."
    if safety.is_protected(name):
        return False, "C'est un élément essentiel de Windows. Il est protégé."
    if category == "vital":
        return False, "Ce processus est vital : Windows ou un pilote en dépend."
    return True, ""


def _post_close_to_windows(pids):
    """Demande poliment aux fenêtres de se fermer (comme un clic sur la croix)."""
    pids = set(pids)
    found = []

    def cb(hwnd, _):
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and _user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    _user32.EnumWindows(_EnumProc(cb), 0)
    for hwnd in found:
        _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    return bool(found)


def close_pids(name, category, pids, self_pids):
    """Ferme les processus d'une application. Retourne (fermés, refusés_par_windows).

    D'abord une demande de fermeture normale, puis une fermeture forcée après
    quelques secondes pour ce qui reste."""
    ok, reason = can_close(name, category, any(p in self_pids for p in pids))
    if not ok:
        raise Refused(reason)
    procs = []
    for pid in pids:
        try:
            p = psutil.Process(pid)
            if p.name().lower() == name.lower():  # le PID n'a pas été réutilisé
                procs.append(p)
        except psutil.Error:
            pass
    if not procs:
        return 0, 0
    if _post_close_to_windows([p.pid for p in procs]):
        procs = _wait_gone(procs, 3)
    denied = []
    for p in procs:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            denied.append(p)
    alive = _wait_gone([p for p in procs if p not in denied], 3)
    closed = len(pids) - len(alive) - len(denied)
    return max(closed, 0), len(denied)


def _alive(p):
    """Vrai si le processus tourne encore. Ne lève jamais d'erreur : un programme lancé en
    administrateur refuse qu'on l'observe (« accès refusé »), il est alors considéré vivant."""
    try:
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.Error:
        return psutil.pid_exists(p.pid)


def _wait_gone(procs, timeout):
    """Attend la fin des processus (au plus `timeout` secondes). Retourne ceux encore actifs.

    psutil.wait_procs n'est pas utilisé : il lève « accès refusé » sur les processus lancés
    en administrateur (ex. nvsphelper64.exe de NVIDIA)."""
    end = time.monotonic() + timeout
    alive = [p for p in procs if _alive(p)]
    while alive and time.monotonic() < end:
        time.sleep(0.1)
        alive = [p for p in alive if _alive(p)]
    return alive


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def relaunch_as_admin():
    """Relance SimpleTask avec les droits administrateur (Windows demande confirmation)."""
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, ""
    else:
        exe = sys.executable
        params = subprocess.list2cmdline([os.path.abspath(sys.argv[0])] + sys.argv[1:])
    r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    return r > 32


def open_file_location(path):
    if path and os.path.exists(path):
        subprocess.Popen(["explorer.exe", "/select,", path])


class Journal:
    MAX = 2000

    def __init__(self):
        self.items = config.read_json(config.JOURNAL_FILE, [])

    def add(self, nom, nb, ram_mo, resultat, origine):
        self.items.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "nom": nom, "nb_processus": nb, "ram_mo": round(ram_mo),
            "resultat": resultat, "origine": origine,
        })
        self.items = self.items[-self.MAX:]
        config.ensure_dirs()
        config.write_json(config.JOURNAL_FILE, self.items)
