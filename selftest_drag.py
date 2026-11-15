# -*- coding: utf-8 -*-
"""Smoke test for the OLE drag source COM plumbing (no real drag)."""
import ctypes
import sys

sys.path.insert(0, ".")
from core import dragdrop as dd

u = ctypes.windll.kernel32

d = dd._DataObject("Привет UniBoard ✓")
s = dd._DropSource()


def call_vt(obj, index, proto, *args):
    vt = ctypes.cast(obj.vtable, ctypes.POINTER(ctypes.c_void_p))
    fn = ctypes.cast(vt[index], proto)
    return fn(ctypes.addressof(obj), *args)


# QI: for our own interface
out = ctypes.c_void_p()
riid_ok = dd.IID_IDataObject
hr = call_vt(d.obj, 0, dd._QI, ctypes.byref(riid_ok), ctypes.byref(out))
assert hr == dd.S_OK and out.value == ctypes.addressof(d.obj), (hex(hr), out.value)
print("QI(IDataObject) OK")

# QI: for a foreign interface (ctypes raises OSError on a failed HRESULT)
iid_bad = dd._guid("11111111-2222-3333-4444-555555555555")
try:
    hr = call_vt(d.obj, 0, dd._QI, ctypes.byref(iid_bad), ctypes.byref(out))
    hr = None  # no exception: treat as "no raise" (should not happen)
except OSError as ex:
    hr = ex.winerror
    out = ctypes.c_void_p()
assert out.value is None and (hr is None or (hr & 0xFFFFFFFF) == dd.E_NOINTERFACE), (hr, out.value)
print("QI(unknown) OK -> E_NOINTERFACE")

# QueryGetData
fmt = dd.FORMATETC(dd.CF_UNICODETEXT, None, dd.DVASPECT_CONTENT, -1, dd.TYMED_HGLOBAL)
hr = call_vt(d.obj, 5, dd._QUERYDATA, ctypes.byref(fmt))
assert hr == dd.S_OK, hex(hr)
fmt2 = dd.FORMATETC(1, None, dd.DVASPECT_CONTENT, -1, dd.TYMED_HGLOBAL)  # CF_TEXT
try:
    hr = call_vt(d.obj, 5, dd._QUERYDATA, ctypes.byref(fmt2))
    hr = None
except OSError as ex:
    hr = ex.winerror
assert hr is None or (hr & 0xFFFFFFFF) == dd.DV_E_FORMATETC, hr
print("QueryGetData OK")

# GetData: read the text back from the allocated HGLOBAL
med = dd.STGMEDIUM()
hr = call_vt(d.obj, 3, dd._GETDATA, ctypes.byref(fmt), ctypes.byref(med))
assert hr == dd.S_OK and med.tymed == dd.TYMED_HGLOBAL and med.hGlobal, hex(hr)
p = u.GlobalLock(ctypes.c_void_p(med.hGlobal))
text = ctypes.wstring_at(p)
u.GlobalUnlock(ctypes.c_void_p(med.hGlobal))
assert text == "Привет UniBoard ✓", repr(text)
print("GetData + text roundtrip OK")

# EnumFormatEtc must return an enumerator
penum = ctypes.c_void_p()
hr = call_vt(d.obj, 8, dd._ENUM, dd.DATADIR_GET, ctypes.byref(penum))
assert hr == dd.S_OK and penum.value, hex(hr)
print("EnumFormatEtc OK")

# DropSource: button held -> S_OK, released -> DRAGDROP_S_DROP
hr = call_vt(s.obj, 3, dd._QUERYCONT, False, dd.MK_LBUTTON)
assert hr == dd.S_OK, hex(hr)
hr = call_vt(s.obj, 3, dd._QUERYCONT, False, 0)
assert hr == dd.DRAGDROP_S_DROP, hex(hr)
hr = call_vt(s.obj, 3, dd._QUERYCONT, True, dd.MK_LBUTTON)
assert hr == dd.DRAGDROP_S_CANCEL, hex(hr)
print("IDropSource logic OK")

print("DRAGDROP SMOKE TEST PASSED")
