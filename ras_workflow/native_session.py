"""Exclusive ownership checks for the inspected Windows HEC-RAS adapter."""
import ctypes
from ctypes import wintypes as wt
from contextlib import contextmanager


def ras_processes():
    # Toolhelp lists executable names without opening unrelated processes.
    class Entry(ctypes.Structure):
        _fields_=[('dwSize',wt.DWORD),('cntUsage',wt.DWORD),('pid',wt.DWORD),
            ('heap',ctypes.c_size_t),('module',wt.DWORD),('threads',wt.DWORD),
            ('parent',wt.DWORD),('priority',wt.LONG),('flags',wt.DWORD),('exe',wt.WCHAR*260)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[wt.DWORD,wt.DWORD];kernel.CreateToolhelp32Snapshot.restype=wt.HANDLE
    for name in ('Process32FirstW','Process32NextW'):
        fn=getattr(kernel,name);fn.argtypes=[wt.HANDLE,ctypes.POINTER(Entry)];fn.restype=wt.BOOL
    kernel.CloseHandle.argtypes=[wt.HANDLE];kernel.CloseHandle.restype=wt.BOOL
    handle=kernel.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    rows=[];entry=Entry();entry.dwSize=ctypes.sizeof(entry)
    try:
        success=kernel.Process32FirstW(handle,ctypes.byref(entry))
        if not success:raise ctypes.WinError(ctypes.get_last_error())
        while success:
            if entry.exe.lower()=='ras.exe':rows.append(entry.pid)
            success=kernel.Process32NextW(handle,ctypes.byref(entry))
        if ctypes.get_last_error()!=18:raise ctypes.WinError(ctypes.get_last_error())
    finally:kernel.CloseHandle(handle)
    return rows


def require_exclusive(owned_pid=None):
    processes=ras_processes()
    if set(processes)!=(set() if owned_pid is None else {owned_pid}):
        raise RuntimeError('HEC_RAS_ALREADY_OPEN: Save and close HEC-RAS, then retry. Existing windows were not modified. / 请保存并关闭 HEC-RAS 后重试；现有窗口未被修改。')


@contextmanager
def session_lock():
    # Also serializes two SteadyReach checkouts in the same Windows session.
    import win32api,win32event,win32con
    handle=win32event.CreateMutex(None,False,'Local\\SteadyReach_HECRAS701')
    owned=False
    try:
        result=win32event.WaitForSingleObject(handle,0)
        owned=result in (win32con.WAIT_OBJECT_0,win32con.WAIT_ABANDONED)
        if not owned:raise RuntimeError('Another SteadyReach checkout is using HEC-RAS; retry when it finishes.')
        yield
    finally:
        if owned:win32event.ReleaseMutex(handle)
        win32api.CloseHandle(handle)
