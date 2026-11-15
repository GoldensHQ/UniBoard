# -*- coding: utf-8 -*-
"""OLE drag & drop source: dragging text from UniBoard into other apps.

A minimal IDropSource + IDataObject (CF_UNICODETEXT) in pure ctypes.
DoDragDrop runs a modal loop until the mouse button is released and reports
the resulting drop effect. Works with any drop-capable application (browsers,
editors, terminals...): the text lands exactly where the cursor points.
"""
import ctypes
from ctypes import wintypes

kernel32 = ctypes.windll.kernel32
ole32 = ctypes.windll.ole32
shell32 = ctypes.windll.shell32

CF_UNICODETEXT = 13
DVASPECT_CONTENT = 1
TYMED_HGLOBAL = 1
DATADIR_GET = 1
GMEM_MOVEABLE = 0x0002
MK_LBUTTON = 0x0001

S_OK = 0
S_FALSE = 1
E_NOINTERFACE = 0x80004002
E_NOTIMPL = 0x80004001
DV_E_FORMATETC = 0x80040064
DATA_S_SAMEFORMATETC = 0x00040130
OLE_E_ADVISENOTSUPPORTED = 0x80040003
DRAGDROP_S_DROP = 0x00040100
DRAGDROP_S_CANCEL = 0x00040101
DRAGDROP_S_USEDEFAULTCURSORS = 0x00040102
RPC_E_CHANGED_MODE = 0x80010106

DROPEFFECT_COPY, DROPEFFECT_MOVE, DROPEFFECT_LINK = 1, 2, 4

HRESULT = ctypes.HRESULT
CLIPFORMAT = ctypes.c_ushort


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


def _guid(s):
    p = s.split("-")
    d = GUID()
    d.Data1 = int(p[0], 16)
    d.Data2 = int(p[1], 16)
    d.Data3 = int(p[2], 16)
    d.Data4[:] = bytes.fromhex(p[3] + p[4])
    return d


IID_IUnknown = _guid("00000000-0000-0000-C000-000000000046")
IID_IDataObject = _guid("0000010e-0000-0000-C000-000000000046")
IID_IDropSource = _guid("00000121-0000-0000-C000-000000000046")


def _guid_bytes(g):
    return ctypes.string_at(ctypes.byref(g), ctypes.sizeof(GUID))


class FORMATETC(ctypes.Structure):
    _fields_ = [("cfFormat", CLIPFORMAT), ("ptd", ctypes.c_void_p),
                ("dwAspect", wintypes.DWORD), ("lindex", ctypes.c_long),
                ("tymed", wintypes.DWORD)]


class STGMEDIUM(ctypes.Structure):
    _fields_ = [("tymed", wintypes.DWORD), ("hGlobal", ctypes.c_void_p),
                ("pUnkForRelease", ctypes.c_void_p)]


class _ComObj(ctypes.Structure):
    """A COM object as seen from native code: [0] = pointer to the vtable."""
    _fields_ = [("vtable", ctypes.c_void_p)]


# --- method prototypes (COM = stdcall) --------------------------------------

_QI = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID),
                         ctypes.POINTER(ctypes.c_void_p))
_REF = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)
_GETDATA = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC),
                              ctypes.POINTER(STGMEDIUM))
_QUERYDATA = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC))
_CANON = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC),
                            ctypes.POINTER(FORMATETC))
_SETDATA = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC),
                              ctypes.POINTER(STGMEDIUM), ctypes.c_int, ctypes.c_int)
_ENUM = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.DWORD,
                           ctypes.POINTER(ctypes.c_void_p))
_ADV = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC),
                          wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))
_UNADV = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.DWORD)
_QUERYCONT = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD)
_GIVEFB = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.DWORD)

ole32.DoDragDrop.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                             ctypes.POINTER(wintypes.DWORD)]
shell32.SHCreateStdEnumFmtEtc.argtypes = [wintypes.UINT, ctypes.POINTER(FORMATETC),
                                          ctypes.POINTER(ctypes.c_void_p)]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.restype = ctypes.c_int
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.restype = ctypes.c_void_p
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]


def _make_vtable(fp_list):
    """Attach a vtable to an object built from ctypes function pointers."""
    vt = (ctypes.c_void_p * len(fp_list))()
    for i, f in enumerate(fp_list):
        vt[i] = ctypes.cast(f, ctypes.c_void_p)
    obj = _ComObj()
    obj.vtable = ctypes.cast(vt, ctypes.c_void_p)
    return obj, vt, fp_list  # fp_list must be kept alive (GC)


def _alloc_text(text):
    """GlobalAlloc(GMEM_MOVEABLE): UTF-16 + NUL. Freed by the target app."""
    raw = text.encode("utf-16-le") + b"\x00\x00"
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(raw))
    p = kernel32.GlobalLock(h)
    ctypes.memmove(p, raw, len(raw))
    kernel32.GlobalUnlock(h)
    return h


class _DataObject:
    """IDataObject with a single available format: CF_UNICODETEXT."""

    def __init__(self, text):
        self.text = text
        self.ref = 1
        fmt = FORMATETC(CF_UNICODETEXT, None, DVASPECT_CONTENT, -1, TYMED_HGLOBAL)
        self.fmt = fmt

        def qi(_this, riid, ppv):
            if ppv:
                ppv[0] = None
            if not riid:
                return E_NOINTERFACE
            want = _guid_bytes(riid[0]) in (_guid_bytes(IID_IUnknown),
                                            _guid_bytes(IID_IDataObject))
            if not want:
                return E_NOINTERFACE
            ppv[0] = ctypes.addressof(self.obj)
            self.ref += 1
            return S_OK

        def addref(_this):
            self.ref += 1
            return self.ref

        def release(_this):
            self.ref -= 1
            return max(self.ref, 0)

        def get_data(_this, pfmt, pmed):
            try:
                f = pfmt[0]
                if (f.cfFormat != CF_UNICODETEXT
                        or not (f.dwAspect & DVASPECT_CONTENT)
                        or not (f.tymed & TYMED_HGLOBAL)):
                    return DV_E_FORMATETC
                pmed[0] = STGMEDIUM(TYMED_HGLOBAL, _alloc_text(self.text), None)
                return S_OK
            except Exception:
                return DV_E_FORMATETC

        def get_data_here(_this, pfmt, pmed):
            return E_NOTIMPL

        def query_data(_this, pfmt):
            f = pfmt[0]
            if (f.cfFormat == CF_UNICODETEXT
                    and (f.dwAspect & DVASPECT_CONTENT)
                    and (f.tymed & TYMED_HGLOBAL)):
                return S_OK
            return DV_E_FORMATETC

        def canon(_this, pin, pout):
            if pout:
                pout[0] = pin[0]
            return DATA_S_SAMEFORMATETC

        def set_data(_this, pfmt, pmed, frelease, fret):
            return E_NOTIMPL

        def enum_fmt(_this, direction, ppenum):
            if direction != DATADIR_GET or not ppenum:
                return DV_E_FORMATETC
            arr = (FORMATETC * 1)(fmt)
            return shell32.SHCreateStdEnumFmtEtc(1, arr, ppenum)

        def dadvise(_this, pfmt, advf, psink, pconn):
            return OLE_E_ADVISENOTSUPPORTED

        def dunadvise(_this, conn):
            return OLE_E_ADVISENOTSUPPORTED

        # Order of methods as in the IDataObject vtable
        self.obj, self._vt, self._fp = _make_vtable([
            _QI(qi), _REF(addref), _REF(release),
            _GETDATA(get_data), _GETDATA(get_data_here),
            _QUERYDATA(query_data), _CANON(canon), _SETDATA(set_data),
            _ENUM(enum_fmt), _ADV(dadvise), _UNADV(dunadvise),
        ])


class _DropSource:
    """IDropSource: hold — continue, Esc — cancel, button released — drop."""

    def __init__(self):
        self.ref = 1

        def qi(_this, riid, ppv):
            if ppv:
                ppv[0] = None
            if not riid:
                return E_NOINTERFACE
            want = _guid_bytes(riid[0]) in (_guid_bytes(IID_IUnknown),
                                            _guid_bytes(IID_IDropSource))
            if not want:
                return E_NOINTERFACE
            ppv[0] = ctypes.addressof(self.obj)
            self.ref += 1
            return S_OK

        def addref(_this):
            self.ref += 1
            return self.ref

        def release(_this):
            self.ref -= 1
            return max(self.ref, 0)

        def query_cont(_this, f_escape, keys):
            if f_escape:
                return DRAGDROP_S_CANCEL
            if not (keys & MK_LBUTTON):
                return DRAGDROP_S_DROP
            return S_OK

        def give_fb(_this, effect):
            return DRAGDROP_S_USEDEFAULTCURSORS

        self.obj, self._vt, self._fp = _make_vtable([
            _QI(qi), _REF(addref), _REF(release),
            _QUERYCONT(query_cont), _GIVEFB(give_fb),
        ])


_ole_ready = False


def _ole_init():
    global _ole_ready
    if _ole_ready:
        return True
    hr = ole32.OleInitialize(None)
    if hr in (S_OK, S_FALSE, RPC_E_CHANGED_MODE):
        _ole_ready = True
        return True
    return False


def drag_text(text):
    """Start an OLE drag with the text. Blocks until the drop; returns the effect.

    A non-zero return means the text was dropped into the target application.
    Call from the UI thread: DoDragDrop runs a modal message loop.
    """
    if not text or not _ole_init():
        return 0
    dobj = _DataObject(text)
    dsrc = _DropSource()
    effect = wintypes.DWORD(0)
    try:
        hr = ole32.DoDragDrop(ctypes.addressof(dobj.obj),
                              ctypes.addressof(dsrc.obj),
                              DROPEFFECT_COPY | DROPEFFECT_MOVE | DROPEFFECT_LINK,
                              ctypes.byref(effect))
    except Exception:
        return 0
    if hr in (S_OK, DRAGDROP_S_DROP):
        return effect.value
    return 0
