"""Lecture des processus et regroupement par application.

Pour rester léger (moins de 2 % de CPU), toute la liste est lue en UN seul appel
Windows (NtQuerySystemInformation), comme le fait le Gestionnaire de tâches.
Seul le chemin du fichier est demandé à part, une fois par processus."""
import ctypes
import os
import struct
import time
import winreg
from ctypes import wintypes
from dataclasses import dataclass, field

import psutil

CPU_COUNT = psutil.cpu_count() or 1

_ntdll = ctypes.WinDLL("ntdll")
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_ntdll.NtQuerySystemInformation.restype = ctypes.c_long
_ntdll.NtQuerySystemInformation.argtypes = (ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                                            ctypes.POINTER(ctypes.c_ulong))
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                                 wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

SystemProcessInformation = 5
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004 - (1 << 32)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Positions des champs de SYSTEM_PROCESS_INFORMATION (Windows 64 bits)
assert struct.calcsize("P") == 8, "SimpleTask nécessite Python 64 bits"
_OFF_NEXT, _OFF_PRIVATE_WS, _OFF_CREATE = 0x00, 0x08, 0x20
_OFF_USER, _OFF_KERNEL, _OFF_NAME_LEN, _OFF_NAME_PTR = 0x28, 0x30, 0x38, 0x40
_OFF_PID, _OFF_WS = 0x50, 0x90
_OFF_READ_BYTES, _OFF_WRITE_BYTES = 0xE8, 0xF0   # octets lus / écrits depuis le lancement

_user32 = ctypes.WinDLL("user32")
_dwmapi = ctypes.WinDLL("dwmapi")
_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
GWL_EXSTYLE, WS_EX_TOOLWINDOW, GW_OWNER, DWMWA_CLOAKED = -20, 0x80, 4, 14


@dataclass
class Group:
    key: str                 # nom + chemin, en minuscules
    name: str
    path: str
    pids: list = field(default_factory=list)
    cpu: float = 0.0         # % du processeur total (comme le Gestionnaire de tâches)
    ram: int = 0             # octets (mémoire privée, comme le Gestionnaire de tâches)
    disk: float = 0.0        # octets lus + écrits par seconde
    net: int = 0             # connexions réseau actives
    gpu: float = 0.0         # % du moteur graphique le plus utilisé
    gpu_engine: str = ""     # ex. « GPU 0 - 3D »
    is_app: bool = False     # a une fenêtre visible (section « Applications »)
    high_cpu_since: float = 0.0
    _gpu: dict = field(default_factory=dict, repr=False)


def app_window_pids():
    """PID des processus qui ont une vraie fenêtre visible, comme le Gestionnaire de tâches :
    visible, sans propriétaire, pas une palette d'outils, non masquée, avec un titre."""
    pids = set()

    def cb(hwnd, _):
        if not _user32.IsWindowVisible(hwnd) or _user32.GetWindow(hwnd, GW_OWNER):
            return True
        if _user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if not _user32.GetWindowTextLengthW(hwnd):
            return True
        cloaked = ctypes.c_int(0)
        _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), 4)
        if cloaked.value:
            return True
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pids.add(pid.value)
        return True

    _user32.EnumWindows(_EnumWindowsProc(cb), 0)
    return pids


def connection_counts():
    """Connexions réseau établies par processus (lisible sans droits administrateur)."""
    counts = {}
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.pid and c.status == psutil.CONN_ESTABLISHED:
                counts[c.pid] = counts.get(c.pid, 0) + 1
    except (psutil.Error, OSError):
        pass
    return counts


def self_pids():
    """Notre propre processus (et le lanceur PyInstaller) : jamais fermables."""
    pids = {os.getpid()}
    try:
        me = psutil.Process()
        parent = me.parent()
        if parent and parent.name().lower() == me.name().lower():
            pids.add(parent.pid)
    except psutil.Error:
        pass
    return pids


def _image_path(raw):
    """Chemin de l'exécutable dans une valeur ImagePath (guillemets, arguments, variables)."""
    p = os.path.expandvars(str(raw).strip())
    if p.startswith('"'):
        p = p[1:].split('"', 1)[0]
    else:
        i = p.lower().find(".exe")
        if i == -1:
            return ""
        p = p[:i + 4]
    if p.lower().startswith("\\systemroot\\"):
        p = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), p[12:])
    elif p.startswith("\\??\\"):
        p = p[4:]
    return p if p.lower().endswith(".exe") else ""


def service_image_paths():
    """{nom.exe en minuscules: chemin} pour les services Windows, lu dans le registre.

    Lisible sans droits administrateur : sert quand Windows refuse de donner le chemin d'un
    processus qui tourne sous le compte système. Les noms ambigus sont ignorés."""
    found = {}
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services")
    except OSError:
        return {}
    with root:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(root, name) as k:
                    raw, _ = winreg.QueryValueEx(k, "ImagePath")
            except OSError:
                continue
            p = _image_path(raw)
            if p:
                found.setdefault(os.path.basename(p).lower(), set()).add(os.path.normpath(p))
    return {n: next(iter(ps)) for n, ps in found.items() if len(ps) == 1}


def exe_path(pid):
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        _kernel32.CloseHandle(h)


class _PDH_FMT(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("pad", wintypes.DWORD),
                ("doubleValue", ctypes.c_double)]


class _PDH_ITEM(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _PDH_FMT)]


_ENGINE_LABEL = {"3D": "3D", "VideoDecode": "Video Decode", "VideoEncode": "Video Encode",
                 "Copy": "Copy", "Compute": "Compute", "VideoProcessing": "Video Processing"}


class GpuMonitor:
    """Utilisation du processeur graphique par processus, via les compteurs de performance
    « GPU Engine » de Windows (ceux du Gestionnaire de tâches), sans droits administrateur."""

    PDH_FMT_DOUBLE, PDH_MORE_DATA = 0x200, 0x800007D2

    def __init__(self):
        self._pdh = ctypes.WinDLL("pdh")
        self._q, self._c = ctypes.c_void_p(), ctypes.c_void_p()
        if self._pdh.PdhOpenQueryW(None, None, ctypes.byref(self._q)):
            raise OSError("PDH indisponible")
        if self._pdh.PdhAddEnglishCounterW(self._q, r"\GPU Engine(*)\Utilization Percentage",
                                           None, ctypes.byref(self._c)):
            raise OSError("compteurs GPU indisponibles")
        self._pdh.PdhCollectQueryData(self._q)
        self.total = 0.0

    def sample(self):
        """{pid: {"GPU 0 - 3D": %, ...}} et met à jour self.total (moteur le plus chargé)."""
        out, per_engine = {}, {}
        if self._pdh.PdhCollectQueryData(self._q):
            return out
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        st = self._pdh.PdhGetFormattedCounterArrayW(self._c, self.PDH_FMT_DOUBLE,
                                                    ctypes.byref(size), ctypes.byref(count), None)
        if (st & 0xFFFFFFFF) != self.PDH_MORE_DATA or not size.value:
            return out
        buf = (ctypes.c_byte * size.value)()
        if self._pdh.PdhGetFormattedCounterArrayW(self._c, self.PDH_FMT_DOUBLE,
                                                  ctypes.byref(size), ctypes.byref(count), buf):
            return out
        items = ctypes.cast(buf, ctypes.POINTER(_PDH_ITEM))
        for i in range(count.value):
            v = items[i].FmtValue.doubleValue
            if items[i].FmtValue.CStatus not in (0, 1) or v <= 0:
                continue
            # « pid_1234_luid_..._phys_0_eng_3_engtype_3D »
            parts = items[i].szName.split("_")
            try:
                pid = int(parts[1])
                phys = parts[parts.index("phys") + 1]
                etype = items[i].szName.split("engtype_", 1)[1]
            except (IndexError, ValueError):
                continue
            label = f"GPU {phys} - {_ENGINE_LABEL.get(etype, etype)}"
            d = out.setdefault(pid, {})
            d[label] = d.get(label, 0.0) + v
            per_engine[label] = per_engine.get(label, 0.0) + v
        self.total = min(max(per_engine.values(), default=0.0), 100.0)
        return out


class Scanner:
    def __init__(self):
        self._buf = ctypes.create_string_buffer(512 * 1024)
        self._exe_cache = {}        # (pid, création) -> chemin (ou "")
        self._prev_times = {}       # (pid, création) -> temps CPU cumulé
        self._prev_clock = None
        self._prev_names = set()
        self._high_since = {}       # clé de groupe -> moment où le CPU a dépassé le seuil
        self.self_pids = self_pids()
        self._services = {}
        self._services_at = 0.0
        self.totals = {"disk": 0.0, "net": 0, "gpu": None}
        try:
            self.gpu = GpuMonitor()
        except OSError:
            self.gpu = None  # compteurs graphiques indisponibles : colonne « — »
        psutil.cpu_percent(None)

    def _service_path(self, name):
        """Chemin d'un service Windows (registre), relu au plus toutes les 5 minutes."""
        now = time.monotonic()
        if now - self._services_at > 300:
            self._services = service_image_paths()
            self._services_at = now
        p = self._services.get(name.lower(), "")
        return p if p and os.path.isfile(p) else ""

    def _snapshot(self):
        ret = ctypes.c_ulong()
        while True:
            st = _ntdll.NtQuerySystemInformation(SystemProcessInformation, self._buf,
                                                 len(self._buf), ctypes.byref(ret))
            if st != STATUS_INFO_LENGTH_MISMATCH:
                break
            self._buf = ctypes.create_string_buffer(max(ret.value, len(self._buf)) * 2)
        if st < 0:
            raise OSError(f"NtQuerySystemInformation a échoué ({st & 0xFFFFFFFF:#x})")
        base = ctypes.addressof(self._buf)
        data = self._buf.raw[:ret.value]
        u32, u64, u16 = struct.Struct("<I"), struct.Struct("<Q"), struct.Struct("<H")
        off = 0
        while True:
            pid = u64.unpack_from(data, off + _OFF_PID)[0]
            nlen = u16.unpack_from(data, off + _OFF_NAME_LEN)[0]
            nptr = u64.unpack_from(data, off + _OFF_NAME_PTR)[0]
            name = ""
            if nlen and nptr:
                s = nptr - base
                name = data[s:s + nlen].decode("utf-16-le", "replace")
            yield (pid, name,
                   u64.unpack_from(data, off + _OFF_CREATE)[0],
                   u64.unpack_from(data, off + _OFF_USER)[0]
                   + u64.unpack_from(data, off + _OFF_KERNEL)[0],
                   u64.unpack_from(data, off + _OFF_PRIVATE_WS)[0]
                   or u64.unpack_from(data, off + _OFF_WS)[0],
                   u64.unpack_from(data, off + _OFF_READ_BYTES)[0]
                   + u64.unpack_from(data, off + _OFF_WRITE_BYTES)[0])
            nxt = u32.unpack_from(data, off + _OFF_NEXT)[0]
            if not nxt:
                break
            off += nxt

    def scan(self, high_cpu_threshold):
        """Retourne (groupes, noms nouvellement lancés)."""
        clock = time.perf_counter()
        elapsed = (clock - self._prev_clock) if self._prev_clock else 0
        self._prev_clock = clock
        groups = {}
        times = {}
        windows = app_window_pids()
        conns = connection_counts()
        gpu = self.gpu.sample() if self.gpu else {}
        for pid, name, created, cputime, ram, io in self._snapshot():
            if pid == 0 or not name:
                continue  # « Processus inactif du système » : pas un vrai programme
            ident = (pid, created)
            times[ident] = (cputime, io)
            cpu = disk = 0.0
            prev = self._prev_times.get(ident)
            if prev is not None and elapsed > 0:
                cpu = (cputime - prev[0]) / (elapsed * 1e7 * CPU_COUNT) * 100
                disk = (io - prev[1]) / elapsed
            exe = self._exe_cache.get(ident)
            if exe is None:
                exe = self._exe_cache[ident] = exe_path(pid) or self._service_path(name)
            key = f"{name.lower()}|{exe.lower()}"
            g = groups.get(key)
            if g is None:
                g = groups[key] = Group(key=key, name=name, path=exe)
            g.pids.append(pid)
            g.cpu += max(cpu, 0.0)
            g.ram += ram
            g.disk += max(disk, 0.0)
            g.net += conns.get(pid, 0)
            g.is_app = g.is_app or pid in windows
            for engine, value in gpu.get(pid, {}).items():
                g._gpu[engine] = g._gpu.get(engine, 0.0) + value
        self._prev_times = times
        for g in groups.values():
            if g._gpu:  # comme le Gestionnaire : le moteur graphique le plus sollicité
                g.gpu_engine, g.gpu = max(g._gpu.items(), key=lambda kv: kv[1])
                g.gpu = min(g.gpu, 100.0)
        self.totals = {
            "disk": sum(g.disk for g in groups.values()),
            "net": sum(g.net for g in groups.values()),
            "gpu": self.gpu.total if self.gpu else None,
        }
        for ident in list(self._exe_cache):
            if ident not in times:
                del self._exe_cache[ident]

        now = time.time()
        for g in groups.values():
            g.cpu = min(g.cpu, 100.0)
            if g.cpu >= high_cpu_threshold:
                g.high_cpu_since = self._high_since.setdefault(g.key, now)
            else:
                self._high_since.pop(g.key, None)
        for k in list(self._high_since):
            if k not in groups:
                del self._high_since[k]

        names = {g.name.lower() for g in groups.values()}
        launched = names - self._prev_names
        self._prev_names = names
        return list(groups.values()), launched


def global_usage():
    vm = psutil.virtual_memory()
    return psutil.cpu_percent(None), vm.percent, vm.used, vm.total
