"""Vérification des signatures numériques en arrière-plan (Get-AuthenticodeSignature).

Un seul appel PowerShell par lot de fichiers, résultats gardés en cache sur le disque :
un fichier n'est revérifié que s'il a changé."""
import base64
import json
import os
import queue
import subprocess
import tempfile
import threading

from . import config

_PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$paths = Get-Content -LiteralPath '{inp}' -Encoding UTF8
$out = @(foreach ($line in $paths) {{
  $p = [string]$line
  if (-not $p) {{ continue }}
  $st = 'Error'; $signer = ''; $company = ''; $desc = ''; $prod = ''; $ver = ''
  try {{
    $s = Get-AuthenticodeSignature -LiteralPath $p -ErrorAction Stop
    $st = [string]$s.Status
    if ($s.SignerCertificate) {{ $signer = $s.SignerCertificate.GetNameInfo('SimpleName', $false) }}
  }} catch {{}}
  try {{
    $vi = (Get-Item -LiteralPath $p).VersionInfo
    $company = [string]$vi.CompanyName; $desc = [string]$vi.FileDescription
    $prod = [string]$vi.ProductName; $ver = [string]$vi.FileVersion
  }} catch {{}}
  [pscustomobject]@{{p = $p; s = $st; n = $signer; c = $company; d = $desc; pn = $prod; v = $ver}}
}})
ConvertTo-Json -InputObject $out -Compress | Out-File -LiteralPath '{out}' -Encoding UTF8
"""

_STATUS = {"Valid": "signe", "NotSigned": "non_signe", "HashMismatch": "non_signe",
           "NotTrusted": "non_signe"}

CREATE_NO_WINDOW = 0x08000000


def _mtime(path):
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return None


class SignatureChecker:
    def __init__(self):
        self._lock = threading.Lock()
        self._cache = config.read_json(config.SIGNATURES_FILE, {})
        self._pending = set()
        self._queue = queue.Queue()
        self._dirty = False
        threading.Thread(target=self._worker, daemon=True).start()

    def lookup(self, path):
        """Retourne {"signature", "signataire", "editeur"} ou None si pas encore connu.
        Demande la vérification si nécessaire."""
        if not path:
            return None
        key = path.lower()
        with self._lock:
            info = self._cache.get(key)
            # "produit" absent = entrée d'une ancienne version : on la revérifie
            if info and info.get("mtime") == _mtime(path) and "produit" in info:
                return info
            if key not in self._pending:
                self._pending.add(key)
                self._queue.put(path)
        return None

    def save(self):
        with self._lock:
            if not self._dirty:
                return
            data = dict(self._cache)
            self._dirty = False
        config.write_json(config.SIGNATURES_FILE, data)

    def _worker(self):
        while True:
            batch = [self._queue.get()]
            try:
                while len(batch) < 200:
                    batch.append(self._queue.get(timeout=0.5))
            except queue.Empty:
                pass
            results = self._run_powershell(batch)
            with self._lock:
                for path in batch:
                    key = path.lower()
                    r = results.get(key)
                    self._cache[key] = {
                        "signature": _STATUS.get(r["s"], "") if r else "",
                        "signataire": (r or {}).get("n") or "",
                        "editeur": (r or {}).get("c") or "",
                        "nom_lisible": ((r or {}).get("d") or "").strip(),
                        "produit": ((r or {}).get("pn") or "").strip(),
                        "version": ((r or {}).get("v") or "").strip(),
                        "mtime": _mtime(path),
                    }
                    self._pending.discard(key)
                self._dirty = True

    @staticmethod
    def _run_powershell(paths):
        results = {}
        fd_in, inp = tempfile.mkstemp(suffix=".txt", prefix="simpletask_")
        fd_out, out = tempfile.mkstemp(suffix=".json", prefix="simpletask_")
        os.close(fd_out)
        try:
            with os.fdopen(fd_in, "w", encoding="utf-8") as f:
                f.write("\n".join(paths))
            script = _PS_SCRIPT.format(inp=inp.replace("'", "''"), out=out.replace("'", "''"))
            encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW, timeout=180)
            with open(out, "r", encoding="utf-8-sig") as f:
                data = json.loads(f.read() or "[]")
            if isinstance(data, dict):
                data = [data]
            for r in data:
                if isinstance(r, dict) and isinstance(r.get("p"), str):
                    results[r["p"].lower()] = r
        except Exception:  # le fil de vérification ne doit jamais s'arrêter
            pass
        finally:
            for p in (inp, out):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return results
