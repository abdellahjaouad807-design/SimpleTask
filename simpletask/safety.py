"""Garde-fous (processus jamais fermables) et détection des processus suspects."""
import os

# Processus système protégés EN DUR : jamais fermables, quoi que dise la base.
PROTECTED = frozenset(n.lower() for n in (
    "System", "System Idle Process", "Registry", "Memory Compression", "Secure System",
    "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
    "lsass.exe", "lsaiso.exe", "svchost.exe", "explorer.exe", "dwm.exe",
    "fontdrvhost.exe", "sihost.exe", "LogonUI.exe", "userinit.exe", "spoolsv.exe",
    "audiodg.exe", "MsMpEng.exe", "NisSrv.exe", "SecurityHealthService.exe",
    "MpDefenderCoreService.exe", "sppsvc.exe", "TrustedInstaller.exe", "TiWorker.exe",
    "msiexec.exe", "conhost.exe", "ctfmon.exe", "WUDFHost.exe", "dllhost.exe",
    "taskhostw.exe", "RuntimeBroker.exe", "wlanext.exe", "smartscreen.exe",
    "SgrmBroker.exe", "MsSense.exe", "AggregatorHost.exe", "LsaIso.exe",
))

_WIN = os.environ.get("SystemRoot", r"C:\Windows").lower()
_SYS32 = os.path.join(_WIN, "system32")
_WOW64 = os.path.join(_WIN, "syswow64")

# Noms de processus Windows connus -> dossiers où ils doivent se trouver.
SYSTEM_LOCATIONS = {
    "svchost.exe": (_SYS32, _WOW64),
    "csrss.exe": (_SYS32,),
    "lsass.exe": (_SYS32,),
    "smss.exe": (_SYS32,),
    "wininit.exe": (_SYS32,),
    "winlogon.exe": (_SYS32,),
    "services.exe": (_SYS32,),
    "spoolsv.exe": (_SYS32,),
    "dwm.exe": (_SYS32,),
    "taskhostw.exe": (_SYS32,),
    "sihost.exe": (_SYS32,),
    "ctfmon.exe": (_SYS32, _WOW64),
    "conhost.exe": (_SYS32,),
    "dllhost.exe": (_SYS32, _WOW64),
    "rundll32.exe": (_SYS32, _WOW64),
    "runtimebroker.exe": (_SYS32,),
    "fontdrvhost.exe": (_SYS32,),
    "audiodg.exe": (_SYS32,),
    "wmiprvse.exe": (os.path.join(_SYS32, "wbem"), os.path.join(_WOW64, "wbem")),
    "explorer.exe": (_WIN,),
    "lsaiso.exe": (_SYS32,),
    "userinit.exe": (_SYS32,),
    "searchindexer.exe": (_SYS32,),
}

_LEET = str.maketrans({"0": "o", "1": "l", "3": "e", "5": "s", "7": "t", "4": "a", "8": "b", "!": "i"})


def is_protected(name):
    return (name or "").lower() in PROTECTED


def unusual_folder(path):
    """Temp, AppData ou Téléchargements : là où un programme système n'a rien à faire."""
    if not path:
        return False
    p = path.lower()
    markers = ("\\appdata\\", "\\temp\\", "\\tmp\\", "\\downloads\\", "\\téléchargements\\")
    if any(m in p for m in markers):
        return True
    tmp = os.environ.get("TEMP", "").lower()
    return bool(tmp) and p.startswith(tmp)


def _distance_1(a, b):
    """Vrai si a et b diffèrent d'une seule lettre (ajout, retrait, remplacement, inversion)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return (len(diff) == 2 and diff[1] == diff[0] + 1
                and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def impersonated_system_name(name):
    """Retourne le nom Windows imité (ex. 'svchost.exe' pour 'svch0st.exe'), sinon None."""
    n = (name or "").lower()
    if n in SYSTEM_LOCATIONS:
        return None
    stem = n[:-4] if n.endswith(".exe") else n
    for real in SYSTEM_LOCATIONS:
        rstem = real[:-4]
        if len(rstem) < 5:
            continue
        if stem.translate(_LEET) == rstem or _distance_1(stem, rstem):
            return real
    return None


def suspect_reasons(name, path, signature, known, sustained_high_cpu):
    """Liste des raisons (en français simple) pour lesquelles un processus est suspect.

    signature : "signe", "non_signe" ou "" (pas encore vérifiée).
    known     : True si le processus est décrit dans la base (pas « Inconnu »).
    """
    reasons = []
    lname = (name or "").lower()
    if signature == "non_signe" and unusual_folder(path):
        reasons.append("Il n'est pas signé numériquement et se lance depuis un dossier "
                       "inhabituel (Temp, AppData ou Téléchargements).")
    if path and lname in SYSTEM_LOCATIONS:
        folder = os.path.dirname(path).lower()
        if folder not in SYSTEM_LOCATIONS[lname]:
            reasons.append(f"Il porte le nom d'un programme de Windows ({name}) mais n'est pas "
                           f"rangé au bon endroit ({os.path.dirname(path)}).")
    imitated = impersonated_system_name(name)
    if imitated and not known:
        reasons.append(f"Son nom ressemble beaucoup à « {imitated} », un programme de Windows. "
                       "C'est une ruse classique des logiciels malveillants.")
    # Un programme signé par un éditeur vérifié (un jeu, par exemple) n'est pas concerné.
    if sustained_high_cpu and not known and signature != "signe":
        reasons.append("Il utilise beaucoup le processeur depuis longtemps alors qu'aucune "
                       "application connue ne lui correspond.")
    return reasons
