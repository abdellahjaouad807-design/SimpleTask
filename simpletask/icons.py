"""Icônes des applications, extraites des fichiers .exe comme dans le Gestionnaire de tâches.

Chaque icône est lue une seule fois par chemin puis gardée en mémoire."""
import ctypes
import tkinter as tk
from ctypes import wintypes

_shell32 = ctypes.WinDLL("shell32")
_user32 = ctypes.WinDLL("user32")
_gdi32 = ctypes.WinDLL("gdi32")

SHGFI_ICON, SHGFI_SMALLICON, SHGFI_USEFILEATTRIBUTES = 0x100, 0x1, 0x10
FILE_ATTRIBUTE_NORMAL = 0x80


class _SHFILEINFOW(ctypes.Structure):
    _fields_ = [("hIcon", wintypes.HICON), ("iIcon", ctypes.c_int),
                ("dwAttributes", wintypes.DWORD), ("szDisplayName", wintypes.WCHAR * 260),
                ("szTypeName", wintypes.WCHAR * 80)]


class _ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD), ("hbmMask", wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP)]


class _BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long),
                ("bmHeight", ctypes.c_long), ("bmWidthBytes", ctypes.c_long),
                ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                ("bmBits", ctypes.c_void_p)]


_shell32.SHGetFileInfoW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD,
                                    ctypes.POINTER(_SHFILEINFOW), wintypes.UINT, wintypes.UINT)
_shell32.SHGetFileInfoW.restype = ctypes.c_void_p
_user32.GetIconInfo.argtypes = (wintypes.HICON, ctypes.POINTER(_ICONINFO))
_user32.DestroyIcon.argtypes = (wintypes.HICON,)
_gdi32.GetObjectW.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p)
_gdi32.GetDIBits.argtypes = (wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT)
_gdi32.DeleteObject.argtypes = (wintypes.HANDLE,)
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)


def _hicon_pixels(hicon):
    """(largeur, hauteur, liste de lignes [(r, g, b, a), ...]) depuis un HICON."""
    info = _ICONINFO()
    if not _user32.GetIconInfo(hicon, ctypes.byref(info)):
        return None
    try:
        bm = _BITMAP()
        _gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, bm.bmHeight
        if not w or not h:
            return None
        header = (ctypes.c_uint32 * 10)(40, w, ctypes.c_uint32(-h).value, 0x200001, 0, 0, 0, 0, 0, 0)
        hdc = _user32.GetDC(None)
        try:
            color = (ctypes.c_ubyte * (w * h * 4))()
            _gdi32.GetDIBits(hdc, info.hbmColor, 0, h, color, header, 0)
            mask = (ctypes.c_ubyte * (w * h * 4))()
            _gdi32.GetDIBits(hdc, info.hbmMask, 0, h, mask, header, 0)
        finally:
            _user32.ReleaseDC(None, hdc)
        has_alpha = any(color[i] for i in range(3, len(color), 4))
        rows = []
        for y in range(h):
            row = []
            for x in range(w):
                i = (y * w + x) * 4
                b, g, r, a = color[i], color[i + 1], color[i + 2], color[i + 3]
                if not has_alpha:  # anciennes icônes : transparence par le masque
                    a = 0 if mask[i] else 255
                row.append((r, g, b, a))
            rows.append(row)
        return w, h, rows
    finally:
        if info.hbmColor:
            _gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            _gdi32.DeleteObject(info.hbmMask)


class IconCache:
    def __init__(self, root, size):
        self.root, self.size = root, size
        self._cache = {}
        self._default = None

    def _load(self, path, generic=False):
        sfi = _SHFILEINFOW()
        flags = SHGFI_ICON | SHGFI_SMALLICON
        if generic:
            flags |= SHGFI_USEFILEATTRIBUTES
        if not _shell32.SHGetFileInfoW(path, FILE_ATTRIBUTE_NORMAL, ctypes.byref(sfi),
                                       ctypes.sizeof(sfi), flags) or not sfi.hIcon:
            return None
        try:
            px = _hicon_pixels(sfi.hIcon)
        finally:
            _user32.DestroyIcon(sfi.hIcon)
        if not px:
            return None
        w, h, rows = px
        img = tk.PhotoImage(master=self.root, width=w, height=h)
        # couleurs ligne par ligne ; les pixels presque transparents restent vides
        img.put(" ".join("{" + " ".join(f"#{r:02x}{g:02x}{b:02x}" for r, g, b, _ in row) + "}"
                         for row in rows), to=(0, 0))
        for y, row in enumerate(rows):
            for x, (_, _, _, a) in enumerate(row):
                if a < 110:
                    img.tk.call(img.name, "transparency", "set", x, y, 1)
        if w > self.size * 1.4:  # icône trop grande pour une ligne : on la réduit
            factor = max(1, round(w / self.size))
            img = img.subsample(factor, factor)
        return img

    def get(self, path):
        """Icône du fichier, ou icône générique d'application."""
        key = (path or "").lower()
        if key in self._cache:
            return self._cache[key]
        img = None
        if path:
            try:
                img = self._load(path)
            except (OSError, tk.TclError):
                img = None
        if img is None:
            if self._default is None:
                try:
                    self._default = self._load("programme.exe", generic=True) or False
                except (OSError, tk.TclError):
                    self._default = False
            img = self._default or None
        self._cache[key] = img
        return img
