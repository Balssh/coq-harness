"""Input injection for the Qud window.

Primary path: SendInput with temporary focus steal (AttachThreadInput +
SetForegroundWindow, with ShowWindow and SwitchToThisWindow fallbacks).
The previous foreground window is restored after every chord.

Fallback path: PostMessage(WM_KEYDOWN/WM_KEYUP) when focus cannot be
obtained. Unity/Qud may ignore PostMessage (Raw Input backend), but it
is better than silently dropping input.
"""

import ctypes
import time
from ctypes import wintypes

import win32api
import win32con
import win32gui

# ---------------------------------------------------------------------------
# Keymap: name -> (vk_code, is_extended)
# ---------------------------------------------------------------------------

VK = {
    # Movement: strictly numpad. Cardinal = 8/2/4/6, diagonals = 7/9/1/3.
    # Numpad VK codes are NumLock-independent when sent via SendInput.
    "up":         (win32con.VK_NUMPAD8, False),
    "down":       (win32con.VK_NUMPAD2, False),
    "left":       (win32con.VK_NUMPAD4, False),
    "right":      (win32con.VK_NUMPAD6, False),
    "up_left":    (win32con.VK_NUMPAD7, False),
    "up_right":   (win32con.VK_NUMPAD9, False),
    "down_left":  (win32con.VK_NUMPAD1, False),
    "down_right": (win32con.VK_NUMPAD3, False),
    # Modifiers
    "shift":      (win32con.VK_SHIFT,   False),
    "ctrl":       (win32con.VK_CONTROL, False),
    "alt":        (win32con.VK_MENU,    False),
    # Actions
    "enter":      (win32con.VK_RETURN,  False),
    "escape":     (win32con.VK_ESCAPE,  False),
    "tab":        (win32con.VK_TAB,     False),
    "space":      (win32con.VK_SPACE,   False),
    "backspace":  (win32con.VK_BACK,    False),
    # Numpad
    "num_0":      (win32con.VK_NUMPAD0, False),
    "num_1":      (win32con.VK_NUMPAD1, False),
    "num_2":      (win32con.VK_NUMPAD2, False),
    "num_3":      (win32con.VK_NUMPAD3, False),
    "num_4":      (win32con.VK_NUMPAD4, False),
    "num_5":      (win32con.VK_NUMPAD5, False),
    "num_6":      (win32con.VK_NUMPAD6, False),
    "num_7":      (win32con.VK_NUMPAD7, False),
    "num_8":      (win32con.VK_NUMPAD8, False),
    "num_9":      (win32con.VK_NUMPAD9, False),
    "num_add":    (win32con.VK_ADD,     False),
    "num_sub":    (win32con.VK_SUBTRACT, False),
    "num_mul":    (win32con.VK_MULTIPLY, False),
    "num_div":    (win32con.VK_DIVIDE,  False),
    "num_enter":  (win32con.VK_RETURN,  True),
}

# Letters a-z
for _c in range(ord("a"), ord("z") + 1):
    VK[chr(_c)] = (_c, False)

# Digits 0-9
for _d in range(10):
    VK[str(_d)] = (ord(str(_d)), False)

# Function keys f1-f12
for _i in range(1, 13):
    VK[f"f{_i}"] = (win32con.VK_F1 + _i - 1, False)

# Punctuation / OEM keys (raw VK codes — win32con doesn't export these)
VK["."]  = (0xBE, False)   # . >   (VK_OEM_PERIOD)
VK[","]  = (0xBC, False)   # , <   (VK_OEM_COMMA)
VK[";"]  = (0xBA, False)   # ; :   (VK_OEM_1)
VK["/"]  = (0xBF, False)   # / ?   (VK_OEM_2)
VK["`"]  = (0xC0, False)   # ` ~   (VK_OEM_3)
VK["["]  = (0xDB, False)   # [ {   (VK_OEM_4)
VK["\\"] = (0xDC, False)   # \ |   (VK_OEM_5)
VK["]"]  = (0xDD, False)   # ] }   (VK_OEM_6)
VK["'"]  = (0xDE, False)   # ' "   (VK_OEM_7)
VK["-"]  = (0xBD, False)   # - _   (VK_OEM_MINUS)
VK["="]  = (0xBB, False)   # = +   (VK_OEM_PLUS)


def _vk(name: str) -> tuple[int, bool]:
    if name not in VK:
        raise ValueError(f"Unknown key: {name!r}")
    return VK[name]


# ---------------------------------------------------------------------------
# PostMessage path
# ---------------------------------------------------------------------------

def _post_key(hwnd: int, vk: int, extended: bool, down: bool) -> None:
    msg = win32con.WM_KEYDOWN if down else win32con.WM_KEYUP
    scan_code = win32api.MapVirtualKey(vk, 0)
    lparam = (1 << 0) | (scan_code << 16)
    if not down:
        lparam |= (1 << 30) | (1 << 31)  # previous state + transition
    if extended:
        lparam |= (1 << 24)
    win32gui.PostMessage(hwnd, msg, vk, lparam)


# ---------------------------------------------------------------------------
# SendInput fallback path
# ---------------------------------------------------------------------------

# Structures for SendInput
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]

_INPUT_KEYBOARD = 1
_KEYEVENTF_SCANCODE = 0x0008
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_EXTENDEDKEY = 0x0001


def _send_input_key(vk: int, extended: bool, down: bool) -> None:
    flags = 0
    if extended:
        flags |= _KEYEVENTF_EXTENDEDKEY
    if not down:
        flags |= _KEYEVENTF_KEYUP
    scan = win32api.MapVirtualKey(vk, 0)
    # Set both wVk and wScan — some engines check one or the other
    ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
    inp = INPUT(type=_INPUT_KEYBOARD, union=_INPUT_UNION(ki=ki))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


# ---------------------------------------------------------------------------
# Focus management for SendInput
# ---------------------------------------------------------------------------

# Raw Win32 calls via ctypes — bypass pywin32 for full control over return values
_GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
_GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_GetWindowThreadProcessId.restype = wintypes.DWORD

_AttachThreadInput = ctypes.windll.user32.AttachThreadInput
_AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
_AttachThreadInput.restype = wintypes.BOOL

_SetForegroundWindow_raw = ctypes.windll.user32.SetForegroundWindow
_SetForegroundWindow_raw.argtypes = [wintypes.HWND]
_SetForegroundWindow_raw.restype = wintypes.BOOL

_GetForegroundWindow_raw = ctypes.windll.user32.GetForegroundWindow
_GetForegroundWindow_raw.argtypes = []
_GetForegroundWindow_raw.restype = wintypes.HWND

_SetWindowPos = ctypes.windll.user32.SetWindowPos
_SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                          ctypes.c_int, ctypes.c_int, wintypes.UINT]
_SetWindowPos.restype = wintypes.BOOL

_ShowWindow = ctypes.windll.user32.ShowWindow
_ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_ShowWindow.restype = wintypes.BOOL

_AllowSetForegroundWindow = ctypes.windll.user32.AllowSetForegroundWindow
_AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
_AllowSetForegroundWindow.restype = wintypes.BOOL

# PeekMessage to ensure the thread has a message queue
_PeekMessageW = ctypes.windll.user32.PeekMessageW
_PeekMessageW.argtypes = [wintypes.LPVOID, wintypes.HWND, wintypes.UINT,
                          wintypes.UINT, wintypes.UINT]
_PeekMessageW.restype = wintypes.BOOL

class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
    ]

_PM_NOREMOVE = 0x0000
_SW_RESTORE = 9
_SW_SHOW = 5
_HWND_TOP = 0
_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001
_SWP_SHOWWINDOW = 0x0040
_SWP_NOACTIVATE = 0x0010
_ASFW_ANY = 0xFFFFFFFF


def _get_window_thread_id(hwnd: int) -> int:
    pid = wintypes.DWORD()
    return _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))


def _ensure_msg_queue() -> None:
    """Force creation of a message queue for the current thread.

    AttachThreadInput fails if either thread lacks a message queue.
    PeekMessage with hwnd=NULL creates one if it doesn't exist.
    """
    msg = _MSG()
    _PeekMessageW(ctypes.byref(msg), 0, 0, 0, _PM_NOREMOVE)


def _fg() -> int:
    return _GetForegroundWindow_raw()


def _log(msg: str) -> None:
    print(f"[input] {msg}", flush=True)


def _force_foreground(hwnd: int) -> tuple[int, bool]:
    """Force the target window to the foreground. Returns (prev_hwnd, success).

    Tries multiple techniques in order:
    1. Already foreground — return immediately.
    2. Ensure msg queue, AttachThreadInput, SetForegroundWindow (raw ctypes).
    3. SetWindowPos TOPMOST then NOTOPMOST, then SetForegroundWindow.
    4. ShowWindow(SW_RESTORE) + SetForegroundWindow.
    5. AllowSetForegroundWindow(ASFW_ANY) + AttachThreadInput + retry loop.

    Never raises for focus failures — callers decide what to do.
    """
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError(f"Window no longer exists (HWND={hwnd})")
    prev = _fg()
    if prev == hwnd:
        _log(f"Already foreground (HWND={hwnd})")
        return prev, True

    _log(f"Stealing focus: HWND={hwnd} prev_fg={prev}")
    _ensure_msg_queue()

    cur_thread = win32api.GetCurrentThreadId()
    tgt_thread = _get_window_thread_id(hwnd)
    _log(f"  threads: cur={cur_thread} tgt={tgt_thread}")

    # Technique 1: AttachThreadInput + raw SetForegroundWindow
    _log(f"  T1: AttachThreadInput + SetForegroundWindow(raw)")
    attached = _AttachThreadInput(cur_thread, tgt_thread, True)
    _log(f"    AttachThreadInput returned {attached}")
    if attached:
        win32gui.BringWindowToTop(hwnd)
        ok = _SetForegroundWindow_raw(hwnd)
        _log(f"    SetForegroundWindow(raw) returned {ok}")
        time.sleep(0.05)
        if _fg() == hwnd:
            _log(f"  T1 SUCCESS")
            return prev, True
        _log(f"    foreground still {_fg()}")
        _AttachThreadInput(cur_thread, tgt_thread, False)
        time.sleep(0.02)

    # Technique 2: SetWindowPos TOPMOST -> NOTOPMOST -> SetForegroundWindow
    _log(f"  T2: SetWindowPos TOPMOST/NOTOPMOST + SetForegroundWindow")
    try:
        _SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
                      _SWP_NOMOVE | _SWP_NOSIZE | _SWP_SHOWWINDOW)
        time.sleep(0.03)
        _SetWindowPos(hwnd, _HWND_NOTOPMOST, 0, 0, 0, 0,
                      _SWP_NOMOVE | _SWP_NOSIZE | _SWP_SHOWWINDOW)
        time.sleep(0.03)
        ok = _SetForegroundWindow_raw(hwnd)
        _log(f"    SetForegroundWindow returned {ok}")
        time.sleep(0.05)
        if _fg() == hwnd:
            _log(f"  T2 SUCCESS")
            return prev, True
    except Exception as e:
        _log(f"    T2 exception: {e}")

    # Technique 3: ShowWindow + SetForegroundWindow
    _log(f"  T3: ShowWindow(SW_RESTORE) + SetForegroundWindow")
    try:
        _ShowWindow(hwnd, _SW_RESTORE)
        time.sleep(0.05)
        ok = _SetForegroundWindow_raw(hwnd)
        _log(f"    SetForegroundWindow returned {ok}")
        time.sleep(0.05)
        if _fg() == hwnd:
            _log(f"  T3 SUCCESS")
            return prev, True
    except Exception as e:
        _log(f"    T3 exception: {e}")

    # Technique 4: AllowSetForegroundWindow + AttachThreadInput + retry loop
    _log(f"  T4: ASFW + AttachThreadInput + retry x5")
    try:
        _AllowSetForegroundWindow(_ASFW_ANY)
        attached = _AttachThreadInput(cur_thread, tgt_thread, True)
        _log(f"    AttachThreadInput returned {attached}")
        if attached:
            for i in range(5):
                win32gui.BringWindowToTop(hwnd)
                ok = _SetForegroundWindow_raw(hwnd)
                time.sleep(0.03)
                if _fg() == hwnd:
                    _log(f"  T4 SUCCESS on attempt {i+1}")
                    return prev, True
                _log(f"    attempt {i+1}: fg={_fg()} ok={ok}")
            _AttachThreadInput(cur_thread, tgt_thread, False)
    except Exception as e:
        _log(f"    T4 exception: {e}")

    # Technique 5: AttachThreadInput kept active, SetForegroundWindow with pywin32
    _log(f"  T5: AttachThreadInput(held) + pywin32.SetForegroundWindow")
    try:
        attached = _AttachThreadInput(cur_thread, tgt_thread, True)
        if attached:
            for i in range(3):
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                time.sleep(0.03)
                if _fg() == hwnd:
                    _log(f"  T5 SUCCESS on attempt {i+1}")
                    return prev, True
            _AttachThreadInput(cur_thread, tgt_thread, False)
    except Exception as e:
        _log(f"    T5 exception: {e}")

    _log(f"  ALL TECHNIQUES FAILED — falling back to PostMessage")
    return prev, False


def _restore_foreground(prev_hwnd: int) -> None:
    if prev_hwnd and win32gui.IsWindow(prev_hwnd):
        try:
            _SetForegroundWindow_raw(prev_hwnd)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class InputInjector:
    """Sends keys to a specific window by HWND.

    Uses SendInput with focus management. PostMessage was tried first
    but Unity/Qud ignores it (likely Raw Input / DirectInput backend).
    """

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd

    def _post_chord(self, vks: list[tuple[int, bool]]) -> None:
        """Fallback: send keys via PostMessage when focus steal fails."""
        for vk, ext in vks:
            _post_key(self.hwnd, vk, ext, down=True)
        time.sleep(0.03)
        for vk, ext in reversed(vks):
            _post_key(self.hwnd, vk, ext, down=False)
        time.sleep(0.05)

    def send_chord(self, keys: list[str]) -> None:
        """Press all keys in order, release in reverse. ~30ms hold time.

        Never leaves keys held: if anything fails mid-chord, all keys that
        are still down are released before the exception propagates.
        Falls back to PostMessage if foreground focus cannot be obtained.
        """
        vks = [_vk(k) for k in keys]
        _log(f"send_chord: keys={keys}")
        prev, focused = _force_foreground(self.hwnd)
        if not focused:
            _log(f"  -> PostMessage fallback for {keys}")
            self._post_chord(vks)
            return
        _log(f"  -> SendInput path for {keys}")
        pressed: list[tuple[int, bool]] = []
        try:
            for vk, ext in vks:
                _send_input_key(vk, ext, down=True)
                pressed.append((vk, ext))
            time.sleep(0.03)
            for vk, ext in reversed(vks):
                _send_input_key(vk, ext, down=False)
                pressed.pop()
            time.sleep(0.05)  # let the game process
        finally:
            for vk, ext in reversed(pressed):
                try:
                    _send_input_key(vk, ext, down=False)
                except Exception:
                    pass
            _restore_foreground(prev)

    def key_down(self, key: str) -> None:
        vk, ext = _vk(key)
        prev, focused = _force_foreground(self.hwnd)
        if not focused:
            _post_key(self.hwnd, vk, ext, down=True)
            return
        try:
            _send_input_key(vk, ext, down=True)
        finally:
            _restore_foreground(prev)

    def key_up(self, key: str) -> None:
        vk, ext = _vk(key)
        prev, focused = _force_foreground(self.hwnd)
        if not focused:
            _post_key(self.hwnd, vk, ext, down=False)
            return
        try:
            _send_input_key(vk, ext, down=False)
        finally:
            _restore_foreground(prev)

    def send_sequence(self, keys: list[str], delay: float = 0.08) -> None:
        """Send key presses sequentially within a single focus session.

        Unlike calling send_chord multiple times (which does a full
        force-foreground/restore cycle per call), this forces foreground
        once, sends each key press-release with a small delay, then
        restores foreground. Prevents focus loss between sequential keys
        like Space + direction (talk/interact).
        Falls back to PostMessage if foreground focus cannot be obtained.
        """
        vks = [_vk(k) for k in keys]
        prev, focused = _force_foreground(self.hwnd)
        if not focused:
            for vk, ext in vks:
                _post_key(self.hwnd, vk, ext, down=True)
                time.sleep(0.03)
                _post_key(self.hwnd, vk, ext, down=False)
                time.sleep(delay)
            time.sleep(0.05)
            return
        pressed: list[tuple[int, bool]] = []
        try:
            for vk, ext in vks:
                _send_input_key(vk, ext, down=True)
                pressed.append((vk, ext))
                time.sleep(0.03)
                _send_input_key(vk, ext, down=False)
                pressed.pop()
                time.sleep(delay)
            time.sleep(0.05)  # let the game process
        finally:
            for vk, ext in reversed(pressed):
                try:
                    _send_input_key(vk, ext, down=False)
                except Exception:
                    pass
            _restore_foreground(prev)
