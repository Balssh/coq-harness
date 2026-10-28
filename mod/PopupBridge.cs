using System;
using System.Collections.Generic;
using System.Text;
using ConsoleLib.Console;
using Qud.UI;

namespace CoQMcpBridge
{
    /// <summary>
    /// Reads and answers modern-UI popups (Qud.UI.PopupMessage).
    ///
    /// Every new-style popup — message boxes, Yes/No prompts, option lists,
    /// conversations, text/number prompts — is a PopupMessage. The game thread
    /// that opened it blocks (Popup.WaitNewPopupMessage → Task.Wait) until the
    /// popup's commandCallback / selectCallback fires with one of its own
    /// QudMenuItems. Keyboard.PushKey never reaches it (uGUI reads Unity input,
    /// not the console key queue) and Hide() only cancels the wait, which throws
    /// on the game thread. So we answer popups exactly the way a mouse click
    /// does: OnActivateCommand(item) with the real item.
    ///
    /// Unity objects may only be touched on the main thread: Refresh() runs
    /// from BridgeMainThread.Update and publishes a JSON snapshot that the pump
    /// thread can read freely; Respond() must be called on the main thread.
    /// </summary>
    public static class PopupBridge
    {
        private const float RefreshIntervalSec = 0.1f;

        private static volatile string _snapshotJson;
        private static float _nextRefresh;

        /// <summary>JSON object describing the open popup, or null if none.</summary>
        public static string SnapshotJson => _snapshotJson;

        public static bool IsOpen => _snapshotJson != null;

        public static void Tick()
        {
            float now = UnityEngine.Time.unscaledTime;
            if (now < _nextRefresh) return;
            _nextRefresh = now + RefreshIntervalSec;
            Refresh();
        }

        public static void Refresh()
        {
            try
            {
                var popup = FindOpen();
                if (popup != null) { _snapshotJson = Describe(popup); return; }
                var picker = PickerBridge.FindOpen();
                _snapshotJson = picker == null ? null : PickerBridge.Describe(picker);
            }
            catch (Exception e)
            {
                _snapshotJson = null;
                Console.WriteLine("[mcp] PopupBridge.Refresh error: " + e.Message);
            }
        }

        /// <summary>The topmost popup that is still waiting for an answer.</summary>
        private static PopupMessage FindOpen()
        {
            PopupMessage best = null;
            int bestOrder = int.MinValue;
            foreach (var p in UnityEngine.Object.FindObjectsOfType<PopupMessage>())
            {
                if (p == null || !p.gameObject.activeInHierarchy) continue;
                // Hide() clears interactable; answered popups linger for 2 frames.
                if (p.canvasGroup != null && !p.canvasGroup.interactable) continue;
                if (p.commandCallback == null && p.selectCallback == null) continue;
                int order = p.transform.GetSiblingIndex();
                if (best == null || order > bestOrder)
                {
                    best = p;
                    bestOrder = order;
                }
            }
            return best;
        }

        private static List<QudMenuItem> Options(PopupMessage p) =>
            p.controller?.menuData ?? new List<QudMenuItem>();

        private static List<QudMenuItem> Buttons(PopupMessage p) =>
            p.controller?.bottomContextOptions ?? new List<QudMenuItem>();

        private static bool HasInput(PopupMessage p) =>
            p.inputBox != null && p.inputBox.gameObject.activeSelf;

        // Strips color markup and spells out the CP437 stat glyphs Qud puts in
        // item names (armor "♦1 ○0", weapons "→4 ♥1d4"), which are control
        // characters that vanish as plain text.
        internal static string Clean(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            s = ColorUtility.StripFormatting(s);
            var sb = new StringBuilder(s.Length + 8);
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                char next = i + 1 < s.Length ? s[i + 1] : ' ';
                bool statFollows = char.IsDigit(next) || next == '-' || next == '+';
                if (c == '\u0004') sb.Append("AV");
                else if (c == '\t' && statFollows) sb.Append("DV");
                else if (c == '\u001a') sb.Append("PV");
                else if (c == '\u0003') sb.Append("dmg ");
                else if (c >= ' ' || c == '\n') sb.Append(c);
                else sb.Append(' ');
            }
            return sb.ToString().Trim();
        }

        private static string Describe(PopupMessage p)
        {
            var sb = new StringBuilder(1024);
            sb.Append("{");
            sb.Append(Json.Str("title", Clean(p.Title?.text)));
            sb.Append(",");
            sb.Append(Json.Str("message", Clean(p.Message?.text)));
            sb.Append(",");
            sb.Append(Json.Str("id", p.PopupID ?? ""));

            sb.Append(",\"options\":[");
            var options = Options(p);
            for (int i = 0; i < options.Count; i++)
            {
                if (i > 0) sb.Append(",");
                sb.Append("{");
                sb.Append(Json.Num("n", i + 1));
                sb.Append(",");
                sb.Append(Json.Str("text", Clean(options[i].text)));
                sb.Append("}");
            }
            sb.Append("]");

            sb.Append(",\"buttons\":[");
            var buttons = Buttons(p);
            for (int i = 0; i < buttons.Count; i++)
            {
                if (i > 0) sb.Append(",");
                sb.Append("{");
                sb.Append(Json.Str("command", buttons[i].command ?? ""));
                sb.Append(",");
                sb.Append(Json.Str("text", ButtonLabel(buttons[i])));
                sb.Append("}");
            }
            sb.Append("]");

            bool input = HasInput(p);
            sb.Append(",");
            sb.Append(Json.Bool("hasInput", input));
            if (input)
            {
                sb.Append(",");
                sb.Append(Json.Str("input", p.inputBox.text ?? ""));
            }
            sb.Append("}");
            return sb.ToString();
        }

        /// <summary>Button text minus the "[Esc]"-style keybind prefix.</summary>
        private static string ButtonLabel(QudMenuItem item)
        {
            string t = Clean(item.text);
            return System.Text.RegularExpressions.Regex.Replace(t, @"^\[?[^\]\s]{1,12}\]\s*", "");
        }

        /// <summary>
        /// Answer the open popup. Exactly one of: option (1-based), button
        /// (command or label, case-insensitive), or dismiss. text, if given,
        /// is typed into the popup's input box first. Main thread only.
        /// </summary>
        public static string Respond(int option, string button, bool dismiss, string text)
        {
            var p = FindOpen();
            if (p == null)
            {
                var picker = PickerBridge.FindOpen();
                if (picker != null)
                {
                    string r = PickerBridge.Respond(picker, option, button, dismiss);
                    _snapshotJson = null;
                    return r;
                }
                return "{\"error\":\"no popup is open\"}";
            }

            string before = Describe(p);
            var options = Options(p);
            var buttons = Buttons(p);

            if (text != null)
            {
                if (!HasInput(p))
                    return Error("this popup has no text input", before);
                p.inputBox.text = text;
            }

            QudMenuItem item;
            string how;
            if (option > 0)
            {
                if (option > options.Count)
                    return Error("option " + option + " out of range (popup has " + options.Count + " options)", before);
                item = options[option - 1];
                how = "option";
            }
            else if (!string.IsNullOrEmpty(button))
            {
                int idx = FindButton(buttons, button);
                if (idx < 0)
                    return Error("no button matching '" + button + "'", before);
                item = buttons[idx];
                how = "button";
            }
            else if (dismiss || text != null)
            {
                // Dismiss: Cancel if offered; otherwise the single acknowledge
                // button ("Continue"); otherwise an any-key popup. With text, the
                // submit/accept button.
                int idx = text != null
                    ? FindSubmit(buttons)
                    : FindButton(buttons, "Cancel");
                if (idx < 0 && buttons.Count == 1 && options.Count == 0) idx = 0;
                if (idx >= 0)
                {
                    item = buttons[idx];
                    how = "button";
                }
                else if (buttons.Count == 0 && options.Count == 0)
                {
                    // Non-null strings: some callbacks call item.text.Replace().
                    item = new QudMenuItem { text = "", command = "", hotkey = "" };
                    how = "anykey";
                }
                else
                {
                    return Error("popup cannot be dismissed — pick an option or button", before);
                }
            }
            else
            {
                return Error("specify option, button, or dismiss", before);
            }

            if (!Activate(p, item))
                return Error("popup refused the selection (tutorial lock?)", before);

            _snapshotJson = null; // force fresh read; next Tick repopulates
            return "{\"ok\":true,\"action\":\"popup\",\"via\":\"" + how + "\"," +
                   Json.Str("chose", item.command ?? "") + ",\"popup\":" + before + "}";
        }

        internal static string Error(string message, string popupJson) =>
            "{\"error\":\"" + Json.Escape(message) + "\",\"popup\":" + popupJson + "}";

        private static bool Activate(PopupMessage p, QudMenuItem item)
        {
            // OnActivateCommand ignores "CmdOptions" items (those are submitted
            // through the select path), and both paths no-op if the tutorial
            // blocks the item. Detect that by checking the callback was consumed.
            if (item.command != "CmdOptions" && p.commandCallback != null)
            {
                p.OnActivateCommand(item);
                if (p.commandCallback == null) return true;
            }
            if (p.selectCallback != null)
            {
                p.OnSelect(item);
                if (p.selectCallback == null) return true;
            }
            return false;
        }

        private static int FindButton(List<QudMenuItem> buttons, string wanted)
        {
            string w = wanted.Trim().ToLowerInvariant();
            // Common synonyms the model may use.
            if (w == "ok" || w == "continue" || w == "accept") w = "accept";
            for (int i = 0; i < buttons.Count; i++)
            {
                string cmd = (buttons[i].command ?? "").ToLowerInvariant();
                string hot = (buttons[i].hotkey ?? "").ToLowerInvariant();
                string label = ButtonLabel(buttons[i]).ToLowerInvariant();
                if (cmd == w || label == w || hot == w) return i;
            }
            // "accept" also matches the lone "Continue" / "keep" button
            if (w == "accept")
            {
                for (int i = 0; i < buttons.Count; i++)
                {
                    string label = ButtonLabel(buttons[i]).ToLowerInvariant();
                    if (label == "continue" || label == "submit" || buttons[i].command == "keep") return i;
                }
            }
            for (int i = 0; i < buttons.Count; i++)
            {
                if (ButtonLabel(buttons[i]).ToLowerInvariant().StartsWith(w)) return i;
            }
            return -1;
        }

        private static int FindSubmit(List<QudMenuItem> buttons)
        {
            for (int i = 0; i < buttons.Count; i++)
            {
                string hot = buttons[i].hotkey ?? "";
                if (hot == "Submit" || hot == "Accept" || hot == "CmdOptions") return i;
            }
            return FindButton(buttons, "accept");
        }
    }

    /// <summary>
    /// The modern item picker (Qud.UI.PickGameObjectScreen) — opened by
    /// containers, autoexplore and "get" on a pile. Like popups it blocks the
    /// game thread on a TaskCompletionSource, so it is answered through its own
    /// handlers: HandleSelectItem(line) takes/selects an item, HandleMenuOption
    /// (TAKE_ALL) takes everything, Cancel() closes it. Fields are private, so
    /// everything goes through reflection. Main thread only.
    /// </summary>
    public static class PickerBridge
    {
        private const System.Reflection.BindingFlags All =
            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic |
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Static;

        internal static object Get(object o, string name)
        {
            if (o == null) return null;
            var t = o.GetType();
            var f = t.GetField(name, All);
            if (f != null) return f.GetValue(o);
            var p = t.GetProperty(name, All);
            return p?.GetValue(o, null);
        }

        internal static object Call(object o, string name, params object[] args)
        {
            var m = o.GetType().GetMethod(name, All);
            return m?.Invoke(o, args);
        }

        public static PickGameObjectScreen FindOpen()
        {
            foreach (var s in UnityEngine.Object.FindObjectsOfType<PickGameObjectScreen>())
            {
                if (s == null || !s.gameObject.activeInHierarchy) continue;
                var tcs = Get(s, "menucomplete");
                var task = Get(tcs, "Task") as System.Threading.Tasks.Task;
                if (task == null || task.IsCompleted) continue;
                return s;
            }
            return null;
        }

        /// <summary>Item lines (categories skipped), in display order.</summary>
        private static List<object> Items(PickGameObjectScreen s)
        {
            var result = new List<object>();
            if (Get(s, "listItems") is System.Collections.IEnumerable lines)
            {
                foreach (var line in lines)
                {
                    if (line is PickGameObjectLineData d && d.type == PickGameObjectLineDataType.Item && d.go != null)
                        result.Add(line);
                }
            }
            return result;
        }

        private static string Title(PickGameObjectScreen s)
        {
            var title = Get(s, "titleText");
            var text = Get(title, "text") as string;
            return PopupBridge.Clean(text ?? "Pick an item");
        }

        public static string Describe(PickGameObjectScreen s)
        {
            var sb = new StringBuilder(1024);
            sb.Append("{");
            sb.Append(Json.Str("title", Title(s)));
            sb.Append(",");
            sb.Append(Json.Str("message", "Item list: option=N takes/selects that item."));
            sb.Append(",");
            sb.Append(Json.Str("id", "PickGameObject"));
            sb.Append(",\"options\":[");
            var items = Items(s);
            for (int i = 0; i < items.Count; i++)
            {
                if (i > 0) sb.Append(",");
                var go = ((PickGameObjectLineData)items[i]).go;
                sb.Append("{");
                sb.Append(Json.Num("n", i + 1));
                sb.Append(",");
                sb.Append(Json.Str("text", PopupBridge.Clean(go.DisplayName)));
                sb.Append("}");
            }
            sb.Append("],\"buttons\":[");
            if (Get(s, "TAKE_ALL") != null)
                sb.Append("{\"command\":\"take_all\",\"text\":\"Take all\"},");
            sb.Append("{\"command\":\"Cancel\",\"text\":\"Cancel\"}]");
            sb.Append(",\"hasInput\":false}");
            return sb.ToString();
        }

        public static string Respond(PickGameObjectScreen s, int option, string button, bool dismiss)
        {
            string before = Describe(s);
            string b = (button ?? "").Trim().ToLowerInvariant();
            try
            {
                if (option > 0)
                {
                    var items = Items(s);
                    if (option > items.Count)
                        return PopupBridge.Error("option " + option + " out of range (" + items.Count + " items)", before);
                    Call(s, "HandleSelectItem", items[option - 1]);
                    return Ok("option", before);
                }
                if (b == "take_all" || b == "take all" || b == "takeall" || b == "take")
                {
                    var takeAll = Get(s, "TAKE_ALL");
                    if (takeAll == null) return PopupBridge.Error("this list has no Take all", before);
                    Call(s, "HandleMenuOption", takeAll);
                    return Ok("take_all", before);
                }
                if (dismiss || b == "cancel" || b == "close")
                {
                    Call(s, "Cancel");
                    return Ok("cancel", before);
                }
            }
            catch (Exception e)
            {
                var inner = e.InnerException ?? e;
                return PopupBridge.Error("picker action failed: " + inner.Message, before);
            }
            return PopupBridge.Error("specify option=N, button='Take all' or dismiss", before);
        }

        private static string Ok(string how, string before) =>
            "{\"ok\":true,\"action\":\"popup\",\"via\":\"" + how + "\",\"popup\":" + before + "}";
    }
}
