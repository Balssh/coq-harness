using System;
using System.Runtime.InteropServices;

namespace CoQMcpBridge
{
    /// <summary>
    /// OS-level keyboard injection via SendInput.
    /// Works for uGUI screens (main menu, chargen, options) that read from
    /// UnityEngine.Input / EventSystems, which ConsoleLib.Keyboard.PushKey
    /// cannot reach. Also works in-game (the game's input bridge converts
    /// Unity events into ConsoleLib.Keyboard events).
    /// </summary>
    public static class OsInput
    {
        private const uint INPUT_KEYBOARD = 1;
        private const uint KEYEVENTF_KEYUP = 0x0002;
        private const uint KEYEVENTF_SCANCODE = 0x0008;
        private const int SW_RESTORE = 9;

        [DllImport("user32.dll", SetLastError = true)]
        private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool SetForegroundWindow(IntPtr hWnd);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool IsIconic(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern IntPtr GetForegroundWindow();

        [DllImport("user32.dll")]
        private static extern uint MapVirtualKey(uint uCode, uint uMapType);

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);

        [DllImport("kernel32.dll")]
        private static extern uint GetCurrentThreadId();

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr FindWindow(string lpClassName, string lpWindowName);

        [DllImport("user32.dll")]
        private static extern IntPtr GetActiveWindow();

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool BringWindowToTop(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern IntPtr SetActiveWindow(IntPtr hWnd);

        [StructLayout(LayoutKind.Sequential)]
        private struct INPUT
        {
            public uint type;
            public INPUTUNION U;
        }

        [StructLayout(LayoutKind.Explicit)]
        private struct INPUTUNION
        {
            [FieldOffset(0)] public KEYBDINPUT ki;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct KEYBDINPUT
        {
            public ushort wVk;
            public ushort wScan;
            public uint dwFlags;
            public uint time;
            public IntPtr dwExtraInfo;
        }

        private static IntPtr GameHwnd
        {
            get { return System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle; }
        }

        /// <summary>Focus the game window so SendInput reaches it.
        /// Uses AttachThreadInput to bypass Windows focus-stealing restrictions.</summary>
        public static bool FocusWindow()
        {
            try
            {
                IntPtr hwnd = GameHwnd;
                if (hwnd == IntPtr.Zero) return false;

                IntPtr fg = GetForegroundWindow();
                uint fgPid;
                uint fgTid = GetWindowThreadProcessId(fg, out fgPid);
                uint curTid = GetCurrentThreadId();

                AttachThreadInput(curTid, fgTid, true);
                try
                {
                    if (IsIconic(hwnd))
                        ShowWindow(hwnd, SW_RESTORE);
                    SetForegroundWindow(hwnd);
                    System.Threading.Thread.Sleep(50);
                }
                finally
                {
                    AttachThreadInput(curTid, fgTid, false);
                }

                return GetForegroundWindow() == hwnd;
            }
            catch { return false; }
        }

        public static bool IsForeground()
        {
            try { return GetForegroundWindow() == GameHwnd; }
            catch { return false; }
        }

        /// <summary>Inject a key press (down + up) at the OS level.
        /// Does NOT focus the window — call FocusWindow() first (on the main thread).</summary>
        public static void Tap(ushort vk)
        {
            INPUT[] inputs = new INPUT[2];

            inputs[0].type = INPUT_KEYBOARD;
            inputs[0].U.ki.wVk = vk;
            inputs[0].U.ki.wScan = (ushort)MapVirtualKey(vk, 0);
            inputs[0].U.ki.dwFlags = KEYEVENTF_SCANCODE;
            inputs[0].U.ki.time = 0;
            inputs[0].U.ki.dwExtraInfo = IntPtr.Zero;

            inputs[1].type = INPUT_KEYBOARD;
            inputs[1].U.ki.wVk = vk;
            inputs[1].U.ki.wScan = (ushort)MapVirtualKey(vk, 0);
            inputs[1].U.ki.dwFlags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP;
            inputs[1].U.ki.time = 0;
            inputs[1].U.ki.dwExtraInfo = IntPtr.Zero;

            SendInput(2, inputs, Marshal.SizeOf(typeof(INPUT)));
        }

        /// <summary>Hold a modifier key down.</summary>
        public static void KeyDown(ushort vk)
        {
            INPUT[] inputs = new INPUT[1];
            inputs[0].type = INPUT_KEYBOARD;
            inputs[0].U.ki.wVk = vk;
            inputs[0].U.ki.wScan = (ushort)MapVirtualKey(vk, 0);
            inputs[0].U.ki.dwFlags = KEYEVENTF_SCANCODE;
            inputs[0].U.ki.time = 0;
            inputs[0].U.ki.dwExtraInfo = IntPtr.Zero;
            SendInput(1, inputs, Marshal.SizeOf(typeof(INPUT)));
        }

        /// <summary>Release a modifier key.</summary>
        public static void KeyUp(ushort vk)
        {
            INPUT[] inputs = new INPUT[1];
            inputs[0].type = INPUT_KEYBOARD;
            inputs[0].U.ki.wVk = vk;
            inputs[0].U.ki.wScan = (ushort)MapVirtualKey(vk, 0);
            inputs[0].U.ki.dwFlags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP;
            inputs[0].U.ki.time = 0;
            inputs[0].U.ki.dwExtraInfo = IntPtr.Zero;
            SendInput(1, inputs, Marshal.SizeOf(typeof(INPUT)));
        }

        // VK codes
        private const ushort VK_BACK = 0x08;
        private const ushort VK_TAB = 0x09;
        private const ushort VK_RETURN = 0x0D;
        private const ushort VK_SHIFT = 0x10;
        private const ushort VK_CONTROL = 0x11;
        private const ushort VK_MENU = 0x12; // Alt
        private const ushort VK_ESCAPE = 0x1B;
        private const ushort VK_SPACE = 0x20;
        private const ushort VK_PRIOR = 0x21; // PageUp
        private const ushort VK_NEXT = 0x22;  // PageDown
        private const ushort VK_END = 0x23;
        private const ushort VK_HOME = 0x24;
        private const ushort VK_LEFT = 0x25;
        private const ushort VK_UP = 0x26;
        private const ushort VK_RIGHT = 0x27;
        private const ushort VK_DOWN = 0x28;
        private const ushort VK_INSERT = 0x2D;
        private const ushort VK_DELETE = 0x2E;

        /// <summary>Map a friendly key name to a Windows virtual-key code.</summary>
        public static ushort? MapKeyName(string key)
        {
            if (string.IsNullOrEmpty(key)) return null;

            if (key.Length == 1)
            {
                char c = char.ToUpper(key[0]);
                if (c >= 'A' && c <= 'Z') return (ushort)c; // VK_A..VK_Z = 0x41..0x5A
                if (c >= '0' && c <= '9') return (ushort)c; // VK_0..VK_9 = 0x30..0x39
                switch (c)
                {
                    case ' ': return VK_SPACE;
                    case '-': return 0xBD; // VK_OEM_MINUS
                    case '=': return 0xBB; // VK_OEM_PLUS
                    case ',': return 0xBC; // VK_OEM_COMMA
                    case '.': return 0xBE; // VK_OEM_PERIOD
                    case '/': return 0xBF; // VK_OEM_2
                    case ';': return 0xBA; // VK_OEM_1
                    case '\'': return 0xDE; // VK_OEM_7
                    case '[': return 0xDB; // VK_OEM_4
                    case ']': return 0xDD; // VK_OEM_6
                    case '\\': return 0xDC; // VK_OEM_5
                    case '`': return 0xC0; // VK_OEM_3
                }
                return null;
            }

            switch (key.ToLowerInvariant())
            {
                case "enter": case "return": return VK_RETURN;
                case "escape": case "esc": return VK_ESCAPE;
                case "space": return VK_SPACE;
                case "tab": return VK_TAB;
                case "backspace": case "back": return VK_BACK;
                case "up": return VK_UP;
                case "down": return VK_DOWN;
                case "left": return VK_LEFT;
                case "right": return VK_RIGHT;
                case "insert": case "ins": return VK_INSERT;
                case "delete": case "del": return VK_DELETE;
                case "home": return VK_HOME;
                case "end": return VK_END;
                case "pageup": case "pgup": return VK_PRIOR;
                case "pagedown": case "pgdn": return VK_NEXT;
                case "shift": return VK_SHIFT;
                case "ctrl": case "control": return VK_CONTROL;
                case "alt": return VK_MENU;
                case "f1": return 0x70;
                case "f2": return 0x71;
                case "f3": return 0x72;
                case "f4": return 0x73;
                case "f5": return 0x74;
                case "f6": return 0x75;
                case "f7": return 0x76;
                case "f8": return 0x77;
                case "f9": return 0x78;
                case "f10": return 0x79;
                case "f11": return 0x7A;
                case "f12": return 0x7B;
                default: return null;
            }
        }
    }
}
