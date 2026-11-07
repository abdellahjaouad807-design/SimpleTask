"""Clé API Gemini : jamais dans le code, jamais dans un fichier de configuration.

Ordre de recherche :
1. variable d'environnement GEMINI_API_KEY ;
2. Gestionnaire d'identification Windows (chiffré par Windows pour votre session).
"""
import ctypes
import os
from ctypes import wintypes

ENV_VAR = "GEMINI_API_KEY"
TARGET = "SimpleTask/GeminiAPIKey"

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_advapi = ctypes.WinDLL("advapi32", use_last_error=True)
_advapi.CredReadW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(_CREDENTIAL)))
_advapi.CredWriteW.argtypes = (ctypes.POINTER(_CREDENTIAL), wintypes.DWORD)
_advapi.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
_advapi.CredFree.argtypes = (ctypes.c_void_p,)


def read_stored(target=TARGET):
    p = ctypes.POINTER(_CREDENTIAL)()
    if not _advapi.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
        return ""
    try:
        c = p.contents
        raw = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)
        return raw.decode("utf-16-le")
    finally:
        _advapi.CredFree(p)


def store(key, target=TARGET):
    key = key.strip()
    if not key:
        raise ValueError("Clé vide")
    blob = key.encode("utf-16-le")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    c = _CREDENTIAL()
    c.Type = CRED_TYPE_GENERIC
    c.TargetName = target
    c.Comment = "Clé API Gemini utilisée par SimpleTask"
    c.CredentialBlobSize = len(blob)
    c.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
    c.Persist = CRED_PERSIST_LOCAL_MACHINE
    c.UserName = "SimpleTask"
    if not _advapi.CredWriteW(ctypes.byref(c), 0):
        raise OSError("Impossible d'enregistrer la clé dans le Gestionnaire d'identification "
                      f"(erreur {ctypes.get_last_error()}).")


def delete(target=TARGET):
    return bool(_advapi.CredDeleteW(target, CRED_TYPE_GENERIC, 0))


def get_key():
    """Retourne (clé, source) ; source = "environnement", "windows" ou ""."""
    k = os.environ.get(ENV_VAR, "").strip()
    if k:
        return k, "environnement"
    k = read_stored()
    if k:
        return k, "windows"
    return "", ""


def mask(key):
    """Pour l'affichage : seulement les 4 derniers caractères."""
    return ("•" * 8 + key[-4:]) if len(key) > 8 else "•" * 8
