using System;
using System.Linq;
using System.Reflection;
using XRL;
using XRL.Core;
using XRL.World;
using XRL.World.Parts;
using ConsoleLib.Console;
using KeyCode = UnityEngine.KeyCode;

namespace CoQMcpBridge
{
    public static class GameActions
    {
        /// <summary>
        /// Push a command via the main thread (fire-and-forget). The pump
        /// thread must never call Keyboard.PushCommand directly — some commands
        /// trigger modal dialogs that hold the keyboard lock, which would
        /// deadlock the pump thread.
        /// </summary>
        private static void PushCommandSafe(string cmd)
        {
            BridgeMainThread.Enqueue(() => Keyboard.PushCommand(cmd));
        }

        public static string ExecuteCommand(GameObject player, string commandJson)
        {
            try
            {
                var cmd = MiniJson.Parse(commandJson) as MiniJson.Obj;
                if (cmd == null)
                    return "{\"error\":\"invalid command JSON\"}";

                string action = cmd.GetStr("action", "");

                // A modal popup blocks the game thread; queued commands would
                // fire later in surprising ways. Make the caller answer it first.
                if (PopupBridge.IsOpen && BlockedByPopup(action))
                    return "{\"error\":\"a popup is open — answer it with respond_popup (option/button) or close_menu first\",\"popup\":" +
                           (PopupBridge.SnapshotJson ?? "null") + "}";

                switch (action)
                {
                    case "respond_popup":
                        return RespondPopup(cmd.GetInt("option", 0), cmd.GetStr("button", ""),
                                            cmd.GetBool("dismiss", false),
                                            cmd.Has("text") ? cmd.GetStr("text", "") : null);
                    case "move":
                        return Move(cmd.GetStr("direction", ""));
                    case "wait":
                        return Wait(cmd.GetInt("turns", 1));
                    case "interact":
                        return Interact(cmd.GetStr("direction", ""));
                    case "get":
                        return Get();
                    case "use_item":
                        return UseItem(player, cmd.GetStr("item", ""), cmd.GetStr("item_action", ""));
                    case "press_key":
                        return PressKey(cmd.GetStr("key", ""));
                    case "send_key":
                        return SendKey(cmd.GetStr("key", ""));
                    case "focus_window":
                        return FocusWindow();
                    case "start_new_game":
                        return StartNewGame();
                    case "continue_game":
                        return ContinueGame(cmd.GetStr("save_id", ""));
                    case "complete_chargen":
                        return CompleteChargen(cmd.GetStr("code", ""));
                    case "chargen_auto":
                        return ChargenAuto();
                    case "chargen_state":
                        return ChargenState();
                    case "chargen_advance":
                        return ChargenAdvance(cmd.GetBool("force", true));
                    case "chargen_random":
                        return ChargenRandom();
                    case "chargen_ui_event":
                        return ChargenUIEvent(cmd.GetStr("event", ""), cmd.GetStr("element", ""));
                    case "press_command":
                        return PressCommand(cmd.GetStr("command", ""));
                    case "open_screen":
                        return OpenScreen(cmd.GetStr("screen", ""));
                    case "close_menu":
                        return CloseMenu();
                    case "confirm_popup":
                        return ConfirmPopup(cmd.GetStr("command", "Yes"));
                    case "choose_option":
                        return ChooseOption(cmd.GetInt("option", 0));
                    case "auto_explore":
                        return AutoExplore();
                    case "travel":
                        return Travel(cmd.GetStr("direction", ""));
                    case "go_stairs":
                        return GoStairs(cmd.GetStr("direction", ""));
                    case "save":
                        return Save();
                    case "save_game":
                        return SaveGame();
                    case "load_game":
                        return LoadGame();
                    case "quit":
                        return Quit();
                    case "quit_to_menu":
                        return QuitToMenu();
                    case "abandon":
                        return Abandon();
                    case "look":
                        return Look();
                    case "show_labels":
                        return ShowLabels();
                    case "list_saves":
                        return ListSaves();
                    default:
                        return "{\"error\":\"unknown action: " + Json.Escape(action) + "\"}";
                }
            }
            catch (Exception e)
            {
                return "{\"error\":\"" + Json.Escape(e.Message) + "\"}";
            }
        }

        private static string Move(string direction)
        {
            string cmd = DirectionToMoveCommand(direction);
            if (cmd == null)
                return "{\"error\":\"invalid direction: " + Json.Escape(direction) + "\"}";

            PushCommandSafe(cmd);
            return "{\"ok\":true,\"action\":\"move\",\"direction\":\"" + Json.Escape(direction) + "\"}";
        }

        private static string Wait(int turns)
        {
            for (int i = 0; i < turns; i++)
                PushCommandSafe("CmdWait");
            return "{\"ok\":true,\"action\":\"wait\",\"turns\":" + turns + "}";
        }

        private static string Interact(string direction)
        {
            string cmd = DirectionToUseCommand(direction);
            if (cmd == null)
                return "{\"error\":\"invalid direction: " + Json.Escape(direction) + "\"}";

            PushCommandSafe(cmd);
            return "{\"ok\":true,\"action\":\"interact\",\"direction\":\"" + Json.Escape(direction) + "\"}";
        }

        private static string Get()
        {
            PushCommandSafe("CmdGet");
            return "{\"ok\":true,\"action\":\"get\"}";
        }

        /// <summary>
        /// Use an item from inventory. Item actions (Eat, Drink, Apply, Drop,
        /// Unequip) are NOT keyboard commands — they are InventoryActionEvent
        /// commands fired by the inventory UI. We fire the event directly on
        /// the main thread so modal dialogs (e.g. "empty waterskin") are handled
        /// by the game's normal flow without deadlocking the pump thread.
        /// </summary>
        private static string UseItem(GameObject player, string itemName, string action)
        {
            if (player == null)
                return "{\"error\":\"not in game\"}";

            // Map action to the InventoryActionEvent command name
            string command;
            switch (action.ToLower())
            {
                case "eat":     command = "Eat"; break;
                case "quaff":
                case "drink":   command = "Drink"; break;
                case "equip":
                case "wear":
                case "wield":   command = "Equip"; break;
                case "apply":   command = "Apply"; break;
                case "unequip": command = "Unequip"; break;
                case "drop":    command = "Drop"; break;
                default:
                    return "{\"error\":\"unknown item action: " + Json.Escape(action) + "\"}";
            }

            // Find the item in the player's inventory by name (fuzzy match)
            GameObject item = FindItemInInventory(player, itemName);
            if (item == null)
                return "{\"error\":\"item not found in inventory: " + Json.Escape(itemName) + "\"}";

            GameObject capturedPlayer = player;
            GameObject capturedItem = item;
            string capturedCommand = command;

            // Fire the InventoryActionEvent on the main thread.
            // This is non-blocking from the pump thread's perspective — the
            // action runs during the next frame's Update().
            BridgeMainThread.Enqueue(() =>
            {
                try
                {
                    if (capturedCommand == "Equip")
                        capturedPlayer.FireEvent(XRL.World.Event.New("CommandEquipObject", "Object", capturedItem));
                    else
                        FireInventoryAction(capturedPlayer, capturedItem, capturedCommand);
                }
                catch (Exception e)
                {
                    System.Console.WriteLine("[mcp] UseItem error: " + e);
                }
            });

            return "{\"ok\":true,\"action\":\"use_item\",\"item\":\"" + Json.Escape(itemName) +
                   "\",\"itemAction\":\"" + Json.Escape(action) + "\"}";
        }

        /// <summary>
        /// Fire an InventoryActionEvent using reflection to call the static
        /// Check method. The exact overload is resolved at runtime.
        /// </summary>
        private static void FireInventoryAction(GameObject actor, GameObject item, string command)
        {
            var evtType = typeof(InventoryActionEvent);

            // Find the Check method — prefer the one with the most parameters
            // (the full overload that takes Object, Actor, Item, Command, etc.)
            var checkMethods = evtType.GetMethods(BindingFlags.Public | BindingFlags.Static)
                .Where(m => m.Name == "Check")
                .OrderByDescending(m => m.GetParameters().Length)
                .ToList();

            if (checkMethods.Count == 0)
            {
                // Fallback: create event from pool and dispatch manually
                var fromPool = evtType.GetMethod("FromPool", BindingFlags.Public | BindingFlags.Static,
                    null, Type.EmptyTypes, null);
                if (fromPool != null)
                {
                    var evt = fromPool.Invoke(null, null);
                    evtType.GetField("Command")?.SetValue(evt, command);
                    evtType.GetField("InventoryTarget")?.SetValue(evt, item);
                    actor.HandleEvent((MinEvent)evt);
                }
                return;
            }

            // Use the fullest overload
            var method = checkMethods[0];
            var ps = method.GetParameters();
            var args = new object[ps.Length];

            for (int i = 0; i < ps.Length; i++)
            {
                var p = ps[i];
                string pname = p.Name.ToLowerInvariant();

                if (pname == "object" || pname == "actor")
                    args[i] = actor;
                else if (pname == "item" || pname == "inventorytarget")
                    args[i] = item;
                else if (pname == "command")
                    args[i] = command;
                else if (p.ParameterType == typeof(bool))
                    args[i] = false;
                else if (p.ParameterType == typeof(int))
                    args[i] = 0;
                else if (p.HasDefaultValue)
                    args[i] = p.DefaultValue;
                else
                    args[i] = null;
            }

            method.Invoke(null, args);
        }

        /// <summary>
        /// Find an item in the player's inventory by fuzzy name match.
        /// Matches against DisplayNameOnly (case-insensitive substring).
        /// </summary>
        private static GameObject FindItemInInventory(GameObject player, string itemName)
        {
            if (string.IsNullOrEmpty(itemName))
                return null;

            string lower = itemName.ToLowerInvariant();

            // Check equipped items first
            var body = player.Body;
            if (body != null)
            {
                foreach (var part in body.GetParts())
                {
                    var equipped = part.Equipped;
                    if (equipped != null && ColorUtility.StripFormatting(equipped.DisplayNameOnly).ToLowerInvariant().Contains(lower))
                        return equipped;
                }
            }

            // Check inventory
            var inventory = player.GetPart<Inventory>();
            if (inventory != null)
            {
                foreach (var obj in inventory.Objects)
                {
                    if (obj != null && ColorUtility.StripFormatting(obj.DisplayNameOnly).ToLowerInvariant().Contains(lower))
                        return obj;
                }
            }

            return null;
        }

        private static string PressKey(string key)
        {
            if (string.IsNullOrEmpty(key))
                return "{\"error\":\"no key specified\"}";

            KeyCode? code = MapKeyName(key);
            if (code == null)
                return "{\"error\":\"unknown key: " + Json.Escape(key) + "\"}";

            KeyCode capturedCode = code.Value;
            BridgeMainThread.Enqueue(() => Keyboard.PushKey(capturedCode));
            return "{\"ok\":true,\"action\":\"press_key\",\"key\":\"" + Json.Escape(key) + "\"}";
        }

        private static KeyCode? MapKeyName(string key)
        {
            if (key.Length == 1)
            {
                char c = char.ToLower(key[0]);
                if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == ' ')
                    return (KeyCode)c;
                return null;
            }
            switch (key.ToLower())
            {
                case "enter": case "return": return KeyCode.Return;
                case "escape": case "esc": return KeyCode.Escape;
                case "space": return KeyCode.Space;
                case "tab": return KeyCode.Tab;
                case "backspace": return KeyCode.Backspace;
                case "up": return KeyCode.UpArrow;
                case "down": return KeyCode.DownArrow;
                case "left": return KeyCode.LeftArrow;
                case "right": return KeyCode.RightArrow;
                default: return null;
            }
        }

        private static string SendKey(string key)
        {
            if (string.IsNullOrEmpty(key))
                return "{\"error\":\"no key specified\"}";

            ushort? vk = OsInput.MapKeyName(key);
            if (vk == null)
                return "{\"error\":\"unknown key: " + Json.Escape(key) + "\"}";

            // Focus + SendInput must run on the main thread (the window owner)
            // for SetForegroundWindow to succeed.
            BridgeMainThread.EnqueueAndWait(() =>
            {
                OsInput.FocusWindow();
                System.Threading.Thread.Sleep(100); // let focus take effect
                OsInput.Tap(vk.Value);
            }, timeoutMs: 5000);

            return "{\"ok\":true,\"action\":\"send_key\",\"key\":\"" + Json.Escape(key) + "\"}";
        }

        private static string FocusWindow()
        {
            bool focused = OsInput.FocusWindow();
            return "{\"ok\":true,\"action\":\"focus_window\",\"focused\":" + (focused ? "true" : "false") +
                   ",\"isForeground\":" + (OsInput.IsForeground() ? "true" : "false") + "}";
        }

        /// <summary>
        /// Start a new game from the main menu. Calls XRLCore.NewGame() on the
        /// main thread, which pushes the EmbarkBuilder (character creation)
        /// view and blocks until chargen is complete.
        /// </summary>
        private static string StartNewGame()
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                try
                {
                    // Check if we're already in chargen
                    string view = SafeGetView();
                    if (view == "EmbarkBuilder" || view == "Chargen")
                    {
                        result = "{\"ok\":true,\"action\":\"start_new_game\",\"note\":\"already in chargen\"}";
                        return;
                    }

                    // Check if we're in-game — need to quit first
                    if (view == "Stage")
                    {
                        result = "{\"error\":\"currently in game — use quit_to_menu first\"}";
                        return;
                    }

                    // From MainMenu, call XRLCore.NewGame() to start chargen.
                    // XRLCore.Core is the static singleton instance.
                    // This is a blocking call that runs the chargen flow.
                    // We run it on a background thread so the main thread
                    // can continue to render and process input.
                    var t = new System.Threading.Thread(() =>
                    {
                        try { XRLCore.Core.NewGame(); }
                        catch (Exception e) { System.Console.WriteLine("[mcp] NewGame error: " + e); }
                    }) { IsBackground = true, Name = "McpNewGame" };
                    t.Start();

                    result = "{\"ok\":true,\"action\":\"start_new_game\",\"note\":\"chargen started\"}";
                }
                catch (Exception e)
                {
                    result = "{\"error\":\"" + Json.Escape(e.ToString()) + "\"}";
                }
            }, timeoutMs: 5000);

            if (!completed)
                return "{\"error\":\"timeout waiting for main thread\"}";
            return result ?? "{\"error\":\"no result\"}";
        }

        /// <summary>
        /// Continue a save the same way the main menu's Continue button does:
        /// push "Pick:Continue" so the game thread (XRLCore._Start) opens the
        /// save list and blocks in SaveManagement.ContinueMenu, which awaits
        /// completionSource; then resolve completionSource with the chosen
        /// SaveGameInfo. Defaults to the most recently written save.
        /// </summary>
        private static string ContinueGame(string saveId)
        {
            if (SafeGetView() == "Stage")
                return "{\"error\":\"already in game\"}";
            if (string.IsNullOrEmpty(saveId))
                saveId = FindMostRecentSave();
            if (string.IsNullOrEmpty(saveId))
                return "{\"error\":\"no saves found\"}";

            var smType = FindType("Qud.UI.SaveManagement");
            if (smType == null)
                return "{\"error\":\"Qud.UI.SaveManagement not found\"}";

            if (SafeGetView() != "ModernSaveManagement")
            {
                string err = null;
                BridgeMainThread.EnqueueAndWait(() =>
                {
                    try
                    {
                        var push = typeof(Keyboard).GetMethods(BindingFlags.Static | BindingFlags.Public)
                            .FirstOrDefault(m => m.Name == "PushMouseEvent" && m.GetParameters().Length == 2);
                        if (push == null) { err = "Keyboard.PushMouseEvent not found"; return; }
                        push.Invoke(null, new object[] { "Pick:Continue", null });
                    }
                    catch (Exception e) { err = e.InnerException?.Message ?? e.Message; }
                });
                if (err != null)
                    return "{\"error\":\"" + Json.Escape(err) + "\"}";
            }

            const BindingFlags Inst = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
            string result = null;
            var deadline = DateTime.UtcNow.AddSeconds(15);
            while (result == null && DateTime.UtcNow < deadline)
            {
                System.Threading.Thread.Sleep(150);
                BridgeMainThread.EnqueueAndWait(() =>
                {
                    try
                    {
                        var inst = UnityEngine.Object.FindObjectOfType(smType) as UnityEngine.Component;
                        if (inst == null || !inst.gameObject.activeInHierarchy) return;
                        var tcs = smType.GetField("completionSource", Inst)?.GetValue(inst);
                        var task = tcs?.GetType().GetProperty("Task")?.GetValue(tcs) as System.Threading.Tasks.Task;
                        if (task == null || task.IsCompleted) return;
                        var saves = smType.GetField("saves", Inst)?.GetValue(inst) as System.Collections.IEnumerable;
                        if (saves == null) return;

                        object chosen = null;
                        var ids = new System.Collections.Generic.List<string>();
                        foreach (var item in saves)
                        {
                            if (item == null) continue;
                            var info = item.GetType().GetField("SaveGame", Inst)?.GetValue(item) ?? item;
                            var id = info.GetType().GetField("ID", Inst)?.GetValue(info) as string;
                            ids.Add(id ?? "?");
                            if (chosen == null && id == saveId) chosen = info;
                        }
                        if (chosen == null)
                        {
                            // Back out to the main menu rather than leave the list open.
                            smType.GetMethod("Exit", Inst, null, Type.EmptyTypes, null)?.Invoke(inst, null);
                            result = "{\"error\":\"save not found in save list\",\"saveId\":\"" + Json.Escape(saveId) +
                                     "\",\"available\":[" + string.Join(",", ids.Select(i => "\"" + Json.Escape(i) + "\"")) + "]}";
                            return;
                        }
                        tcs.GetType().GetMethod("TrySetResult").Invoke(tcs, new[] { chosen });
                        result = "{\"ok\":true,\"action\":\"continue_game\",\"saveId\":\"" + Json.Escape(saveId) + "\",\"loading\":true}";
                    }
                    catch (Exception e)
                    {
                        result = "{\"error\":\"" + Json.Escape(e.InnerException?.Message ?? e.Message) + "\"}";
                    }
                });
            }
            return result ?? "{\"error\":\"save list did not open (view=" + Json.Escape(SafeGetView()) + ")\"}";
        }

        /// <summary>
        /// Find the full path to a save directory by its ID (directory name).
        /// </summary>
        private static string FindSavePath(string saveId)
        {
            try
            {
                var savePaths = new System.Collections.Generic.List<string>();
                try
                {
                    string syncedPath = XRLCore.SyncedPath;
                    if (!string.IsNullOrEmpty(syncedPath))
                        savePaths.Add(System.IO.Path.Combine(syncedPath, "Saves"));
                }
                catch { }
                try { savePaths.Add(XRLCore.SavePath); } catch { }
                savePaths.Add(System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) + "Low",
                    "Freehold Games", "CavesOfQud", "Synced", "Saves"));
                savePaths.Add(System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) + "Low",
                    "Freehold Games", "CavesOfQud", "Saves"));

                foreach (var path in savePaths)
                {
                    if (string.IsNullOrEmpty(path) || !System.IO.Directory.Exists(path))
                        continue;
                    var candidate = System.IO.Path.Combine(path, saveId);
                    if (System.IO.Directory.Exists(candidate))
                        return candidate;
                }
            }
            catch { }
            return null;
        }

        /// <summary>
        /// Find the most recently modified save directory.
        /// Returns the save ID (directory name) or null.
        /// </summary>
        private static string FindMostRecentSave()
        {
            try
            {
                var savePaths = new System.Collections.Generic.List<string>();
                try
                {
                    string syncedPath = XRLCore.SyncedPath;
                    if (!string.IsNullOrEmpty(syncedPath))
                        savePaths.Add(System.IO.Path.Combine(syncedPath, "Saves"));
                }
                catch { }
                try { savePaths.Add(XRLCore.SavePath); } catch { }
                savePaths.Add(System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) + "Low",
                    "Freehold Games", "CavesOfQud", "Synced", "Saves"));

                string bestId = null;
                long bestTime = 0;

                foreach (var path in savePaths)
                {
                    if (string.IsNullOrEmpty(path) || !System.IO.Directory.Exists(path))
                        continue;

                    foreach (var dir in System.IO.Directory.GetDirectories(path))
                    {
                        // Check if it has a save file
                        bool hasSave = System.IO.File.Exists(System.IO.Path.Combine(dir, "Primary.sav.gz"))
                                    || System.IO.File.Exists(System.IO.Path.Combine(dir, "Checkpoint.sav.gz"));
                        if (!hasSave) continue;

                        long time = System.IO.Directory.GetLastWriteTimeUtc(dir).Ticks;
                        if (time > bestTime)
                        {
                            bestTime = time;
                            bestId = System.IO.Path.GetFileName(dir);
                        }
                    }
                }

                return bestId;
            }
            catch { return null; }
        }

        /// <summary>
        /// Complete character creation by setting the EmbarkBuilder's
        /// finishedEvent result, which unblocks XRLCore.NewGame().
        /// Optionally configure the character from a build code.
        /// </summary>
        private static string CompleteChargen(string code)
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                try
                {
                    var builder = UnityEngine.Object.FindObjectOfType<XRL.CharacterBuilds.EmbarkBuilder>();
                    if (builder == null)
                    {
                        result = "{\"error\":\"EmbarkBuilder not found — are you on the chargen screen?\"}";
                        return;
                    }

                    // Optionally configure the character from a build code
                    if (!string.IsNullOrEmpty(code))
                    {
                        try
                        {
                            var initMethod = typeof(XRL.CharacterBuilds.EmbarkBuilder).GetMethod(
                                "InitModulesFromCode",
                                BindingFlags.Instance |
                                BindingFlags.Public |
                                BindingFlags.NonPublic);
                            if (initMethod != null)
                            {
                                // InitModulesFromCode(string code, bool silent)
                                var ps = initMethod.GetParameters();
                                object[] args;
                                if (ps.Length == 1)
                                    args = new object[] { code };
                                else
                                    args = new object[] { code, true }; // silent=true
                                initMethod.Invoke(builder, args);
                            }
                            else
                                result = "{\"error\":\"InitModulesFromCode not found\"}";
                        }
                        catch (Exception e)
                        {
                            result = "{\"error\":\"InitModulesFromCode failed: " + Json.Escape(e.Message) + "\"}";
                            return;
                        }
                    }

                    // Try exitWithInfo() — the game's normal chargen completion method.
                    // This validates the character, sets finishedEvent, and exits the view.
                    var exitMethod = typeof(XRL.CharacterBuilds.EmbarkBuilder).GetMethod(
                        "exitWithInfo",
                        BindingFlags.Instance |
                        BindingFlags.Public |
                        BindingFlags.NonPublic);

                    if (exitMethod != null)
                    {
                        exitMethod.Invoke(builder, null);
                        result = "{\"ok\":true,\"action\":\"complete_chargen\",\"method\":\"exitWithInfo\"}";
                    }
                    else
                    {
                        // Fallback: set finishedEvent directly
                        var embarkInfoField = typeof(XRL.CharacterBuilds.EmbarkBuilder).GetField(
                            "embarkInfo",
                            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                        object embarkInfo = embarkInfoField?.GetValue(builder);

                        if (embarkInfo == null)
                        {
                            try
                            {
                                var infoProp = typeof(XRL.CharacterBuilds.EmbarkBuilder).GetProperty("info",
                                    BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                                embarkInfo = infoProp?.GetValue(builder, null);
                            }
                            catch { }
                        }

                        var finishedEventField = typeof(XRL.CharacterBuilds.EmbarkBuilder).GetField(
                            "finishedEvent",
                            BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
                        object finishedEvent = finishedEventField?.GetValue(null);

                        if (finishedEvent == null || embarkInfo == null)
                        {
                            result = "{\"error\":\"Could not access EmbarkBuilder internals (finishedEvent=" +
                                     (finishedEvent != null ? "ok" : "null") + ", embarkInfo=" +
                                     (embarkInfo != null ? "ok" : "null") + ")\"}";
                            return;
                        }

                        var trySetResult = finishedEvent.GetType().GetMethod("TrySetResult");
                        trySetResult?.Invoke(finishedEvent, new object[] { embarkInfo });

                        // Also pop the EmbarkBuilder view
                        try { GameManager.Instance?.PopGameView(); } catch { }

                        result = "{\"ok\":true,\"action\":\"complete_chargen\",\"method\":\"TrySetResult+Pop\"}";
                    }
                }
                catch (Exception e)
                {
                    result = "{\"error\":\"" + Json.Escape(e.ToString()) + "\"}";
                }
            }, timeoutMs: 15000);

            if (!completed)
                return "{\"error\":\"timeout waiting for main thread\"}";
            return result ?? "{\"error\":\"no result\"}";
        }

        /// <summary>
        /// Automatically create a character in the EmbarkBuilder.
        /// Strategy: select game mode "Classic", then char type "Random" (which
        /// auto-generates a valid character), then call exitWithInfo().
        /// Modules are enabled/disabled dynamically based on selections, so we
        /// configure them in dependency order and re-check after each step.
        /// </summary>
        private static string ChargenAuto()
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                try
                {
                    var builder = UnityEngine.Object.FindObjectOfType<XRL.CharacterBuilds.EmbarkBuilder>();
                    if (builder == null)
                    {
                        result = "{\"error\":\"EmbarkBuilder not found — are you on the chargen screen?\"}";
                        return;
                    }

                    var builderType = typeof(XRL.CharacterBuilds.EmbarkBuilder);
                    var baseModuleType = FindType("XRL.CharacterBuilds.AbstractEmbarkBuilderModule");

                    // Get ALL modules (not just enabled) from the protected 'modules' field
                    var modulesField = builderType.GetField("modules",
                        BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                    var allModules = modulesField?.GetValue(builder) as System.Collections.IEnumerable;

                    // Reflection helpers
                    var randomNoUI = baseModuleType?.GetMethod("RandomSelectionNoUI",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    var isValid = baseModuleType?.GetMethod("IsDataValid",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    var initFromSeed = baseModuleType?.GetMethod("InitFromSeed",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    var getEnabled = baseModuleType?.GetMethod("get_enabled",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);

                    var steps = new System.Collections.Generic.List<string>();

                    // Helper: find a module by type name
                    System.Func<string, object> findModule = (string typeName) =>
                    {
                        if (allModules == null) return null;
                        foreach (var m in allModules)
                        {
                            if (m == null) continue;
                            if (m.GetType().Name == typeName) return m;
                        }
                        return null;
                    };

                    // Helper: get enabled modules
                    System.Func<System.Collections.Generic.List<object>> getEnabledModules = () =>
                    {
                        var list = new System.Collections.Generic.List<object>();
                        if (allModules == null) return list;
                        foreach (var m in allModules)
                        {
                            if (m == null) continue;
                            try
                            {
                                if (getEnabled != null && (bool)getEnabled.Invoke(m, null))
                                    list.Add(m);
                            }
                            catch { }
                        }
                        return list;
                    };

                    // Helper: check all enabled modules valid
                    System.Func<System.Collections.Generic.List<string>> checkValid = () =>
                    {
                        var issues = new System.Collections.Generic.List<string>();
                        foreach (var m in getEnabledModules())
                        {
                            try
                            {
                                bool valid = isValid != null && (bool)isValid.Invoke(m, null);
                                if (!valid)
                                    issues.Add(m.GetType().Name);
                            }
                            catch { issues.Add(m.GetType().Name + " (error)"); }
                        }
                        return issues;
                    };

                    // Helper: random-select all enabled modules
                    System.Func<int, int> randomSelectAll = (int seed) =>
                    {
                        int count = 0;
                        foreach (var m in getEnabledModules())
                        {
                            try
                            {
                                if (initFromSeed != null)
                                {
                                    var ips = initFromSeed.GetParameters();
                                    if (ips.Length == 1 && ips[0].ParameterType == typeof(int))
                                        initFromSeed.Invoke(m, new object[] { seed });
                                }
                                if (randomNoUI != null)
                                {
                                    randomNoUI.Invoke(m, null);
                                    count++;
                                }
                            }
                            catch { }
                        }
                        return count;
                    };

                    // Step 1: Select game mode "Classic" on QudGamemodeModule
                    var gameModeModule = findModule("QudGamemodeModule");
                    if (gameModeModule != null)
                    {
                        var selectMode = gameModeModule.GetType().GetMethod("SelectMode",
                            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                        if (selectMode != null)
                        {
                            System.Console.WriteLine("[mcp] ChargenAuto: selecting game mode 'Classic'");
                            selectMode.Invoke(gameModeModule, new object[] { "Classic" });
                            steps.Add("selected_game_mode=Classic");
                        }
                        else
                        {
                            steps.Add("SelectMode_not_found");
                        }
                    }
                    else
                    {
                        steps.Add("QudGamemodeModule_not_found");
                    }

                    // Step 2: Select char type "Random" on QudChartypeModule
                    var charTypeModule = findModule("QudChartypeModule");
                    if (charTypeModule != null)
                    {
                        var selectType = charTypeModule.GetType().GetMethod("selectType",
                            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                        if (selectType == null)
                            selectType = charTypeModule.GetType().GetMethod("SelectType",
                                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                        if (selectType != null)
                        {
                            System.Console.WriteLine("[mcp] ChargenAuto: selecting char type 'Random'");
                            selectType.Invoke(charTypeModule, new object[] { "Random" });
                            steps.Add("selected_char_type=Random");
                        }
                        else
                        {
                            steps.Add("selectType_not_found");
                        }
                    }
                    else
                    {
                        steps.Add("QudChartypeModule_not_found");
                    }

                    // Step 3: Random-select any remaining enabled modules (pass 1)
                    int seed = new System.Random().Next();
                    int randomized = randomSelectAll(seed);
                    steps.Add("randomized_modules=" + randomized);
                    System.Console.WriteLine("[mcp] ChargenAuto: pass 1 randomized " + randomized + " modules");

                    // Step 3b: Random-select again (pass 2) — dependent modules
                    // (like subtype) may need a second pass after their
                    // dependencies (like genotype) have been configured.
                    int randomized2 = randomSelectAll(seed + 500);
                    steps.Add("randomized_modules_pass2=" + randomized2);
                    System.Console.WriteLine("[mcp] ChargenAuto: pass 2 randomized " + randomized2 + " modules");

                    // Step 3c: Third pass with fresh seeds for any remaining invalid
                    int randomized3 = randomSelectAll(seed + 1000);
                    steps.Add("randomized_modules_pass3=" + randomized3);

                    // Step 4: For any remaining invalid modules, try selecting
                    // the first available option via module-specific methods
                    var invalidModules = checkValid();
                    foreach (var modName in invalidModules)
                    {
                        var mod = findModule(modName);
                        if (mod == null) continue;
                        try
                        {
                            // Try SelectSubtype on QudSubtypeModule
                            if (modName == "QudSubtypeModule")
                            {
                                var getSubtypes = mod.GetType().GetMethod("get_subtypes",
                                    BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                                var getAvail = mod.GetType().GetMethod("getAvailableSelections",
                                    BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                                var selectSubtype = mod.GetType().GetMethod("SelectSubtype",
                                    BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                                
                                if (selectSubtype != null)
                                {
                                    // Try getAvailableSelections first
                                    object selections = null;
                                    if (getAvail != null)
                                        selections = getAvail.Invoke(mod, null);
                                    
                                    if (selections is System.Collections.IEnumerable seqs)
                                    {
                                        foreach (var sel in seqs)
                                        {
                                            if (sel == null) continue;
                                            // Try to get an ID or Name from the selection
                                            var selType = sel.GetType();
                                            string id = null;
                                            var idProp = selType.GetProperty("ID") ?? selType.GetProperty("Id") ?? selType.GetProperty("id");
                                            var nameProp = selType.GetProperty("Name") ?? selType.GetProperty("name");
                                            var idField = selType.GetField("ID") ?? selType.GetField("Id") ?? selType.GetField("id");
                                            var nameField = selType.GetField("Name") ?? selType.GetField("name");
                                            
                                            if (idProp != null) id = idProp.GetValue(sel, null)?.ToString();
                                            else if (idField != null) id = idField.GetValue(sel)?.ToString();
                                            else if (nameProp != null) id = nameProp.GetValue(sel, null)?.ToString();
                                            else if (nameField != null) id = nameField.GetValue(sel)?.ToString();
                                            else id = sel.ToString();
                                            
                                            if (!string.IsNullOrEmpty(id))
                                            {
                                                System.Console.WriteLine("[mcp] ChargenAuto: selecting subtype '" + id + "'");
                                                selectSubtype.Invoke(mod, new object[] { id });
                                                steps.Add("selected_subtype=" + id);
                                                break;
                                            }
                                        }
                                    }
                                    else
                                    {
                                        // Fallback: try get_subtypes
                                        if (getSubtypes != null)
                                        {
                                            var subtypes = getSubtypes.Invoke(mod, null) as System.Collections.IEnumerable;
                                            if (subtypes != null)
                                            {
                                                foreach (var st in subtypes)
                                                {
                                                    if (st == null) continue;
                                                    string id = st.ToString();
                                                    var stType = st.GetType();
                                                    var nameProp = stType.GetProperty("Name");
                                                    var nameField = stType.GetField("Name");
                                                    if (nameProp != null) id = nameProp.GetValue(st, null)?.ToString() ?? id;
                                                    else if (nameField != null) id = nameField.GetValue(st)?.ToString() ?? id;
                                                    
                                                    if (!string.IsNullOrEmpty(id))
                                                    {
                                                        System.Console.WriteLine("[mcp] ChargenAuto: selecting subtype '" + id + "'");
                                                        selectSubtype.Invoke(mod, new object[] { id });
                                                        steps.Add("selected_subtype=" + id);
                                                        break;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            
                            // Generic: try RandomSelectionNoUI one more time
                            if (isValid != null && !(bool)isValid.Invoke(mod, null) && randomNoUI != null)
                            {
                                if (initFromSeed != null)
                                {
                                    var ips = initFromSeed.GetParameters();
                                    if (ips.Length == 1 && ips[0].ParameterType == typeof(int))
                                        initFromSeed.Invoke(mod, new object[] { seed + 2000 });
                                }
                                randomNoUI.Invoke(mod, null);
                            }
                        }
                        catch (Exception e)
                        {
                            System.Console.WriteLine("[mcp] ChargenAuto: fix " + modName + " error: " + e.Message);
                        }
                    }

                    // Step 5: Check final validity
                    var remainingInvalid = checkValid();
                    var enabledModules = getEnabledModules();
                    int validCount = enabledModules.Count - remainingInvalid.Count;

                    System.Console.WriteLine("[mcp] ChargenAuto: " + validCount + "/" + enabledModules.Count + " valid");

                    // Build module status
                    var moduleStatuses = new System.Collections.Generic.List<string>();
                    foreach (var m in enabledModules)
                    {
                        try
                        {
                            bool valid = isValid != null && (bool)isValid.Invoke(m, null);
                            moduleStatuses.Add("{\"module\":\"" + Json.Escape(m.GetType().Name) +
                                "\",\"valid\":" + (valid ? "true" : "false") + "}");
                        }
                        catch
                        {
                            moduleStatuses.Add("{\"module\":\"" + Json.Escape(m.GetType().Name) + "\",\"valid\":false}");
                        }
                    }

                    // Step 6: Try exitWithInfo() — boot modules (SpecificCharacterInit,
                    // SpecificBootHandlers, GameBoot) have no user-selectable data and
                    // may always report invalid, but exitWithInfo() should still work
                    // if all user-facing modules are valid.
                    {
                        try
                        {
                            var exitMethod = builderType.GetMethod("exitWithInfo",
                                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                            if (exitMethod != null)
                            {
                                exitMethod.Invoke(builder, null);
                                result = "{\"ok\":true,\"action\":\"chargen_auto\",\"steps\":[\"" +
                                         string.Join("\",\"", steps) + "\"],\"modulesValid\":" + validCount +
                                         ",\"modulesTotal\":" + enabledModules.Count +
                                         ",\"modules\":[" + string.Join(",", moduleStatuses) + "]}";
                                return;
                            }
                        }
                        catch (Exception e)
                        {
                            result = "{\"error\":\"exitWithInfo failed: " + Json.Escape(e.InnerException?.Message ?? e.Message) +
                                     "\",\"steps\":[\"" + string.Join("\",\"", steps) + "\"],\"modulesValid\":" + validCount +
                                     ",\"invalidModules\":[\"" + string.Join("\",\"", remainingInvalid) + "\"]}";
                            return;
                        }
                    }

                    result = "{\"ok\":false,\"action\":\"chargen_auto\",\"steps\":[\"" +
                             string.Join("\",\"", steps) +
                             "\"],\"modulesValid\":" + validCount +
                             ",\"modulesTotal\":" + enabledModules.Count +
                             ",\"invalidModules\":[\"" + string.Join("\",\"", remainingInvalid) +
                             "\"],\"modules\":[" + string.Join(",", moduleStatuses) + "]}";
                }
                catch (Exception e)
                {
                    result = "{\"error\":\"" + Json.Escape(e.ToString()) + "\"}";
                }
            }, timeoutMs: 30000);

            if (!completed)
                return "{\"error\":\"timeout waiting for main thread\"}";
            return result ?? "{\"error\":\"no result\"}";
        }

        /// <summary>
        /// Get the current state of character creation modules.
        /// Returns a list of enabled modules with their validity status,
        /// errors, and current data summary.
        /// </summary>
        private static string ChargenState()
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                try
                {
                    var builder = UnityEngine.Object.FindObjectOfType<XRL.CharacterBuilds.EmbarkBuilder>();
                    if (builder == null)
                    {
                        result = "{\"error\":\"EmbarkBuilder not found\"}";
                        return;
                    }

                    var builderType = typeof(XRL.CharacterBuilds.EmbarkBuilder);
                    var baseModuleType = FindType("XRL.CharacterBuilds.AbstractEmbarkBuilderModule");

                    var getEnabledModules = builderType.GetMethod("get_enabledModules",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    var modules = getEnabledModules?.Invoke(builder, null) as System.Collections.IEnumerable;

                    var isValid = baseModuleType?.GetMethod("IsDataValid",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    var dataErrorsProp = baseModuleType?.GetProperty("DataErrors",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    var dataWarningsProp = baseModuleType?.GetProperty("DataWarnings",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    var getData = baseModuleType?.GetMethod("getData",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    var getEnabled = baseModuleType?.GetMethod("get_enabled",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);

                    var moduleList = new System.Collections.Generic.List<string>();
                    if (modules != null)
                    {
                        foreach (var module in modules)
                        {
                            if (module == null) continue;
                            var mt = module.GetType();
                            string name = mt.Name;

                            bool valid = false;
                            bool enabled = true;
                            string errors = "";
                            string warnings = "";
                            string dataSummary = "";

                            try { if (isValid != null) valid = (bool)isValid.Invoke(module, null); } catch { }
                            try { if (getEnabled != null) enabled = (bool)getEnabled.Invoke(module, null); } catch { }
                            try
                            {
                                if (dataErrorsProp != null)
                                {
                                    var v = dataErrorsProp.GetValue(module, null);
                                    if (v != null) errors = v.ToString();
                                }
                            } catch { }
                            try
                            {
                                if (dataWarningsProp != null)
                                {
                                    var v = dataWarningsProp.GetValue(module, null);
                                    if (v != null) warnings = v.ToString();
                                }
                            } catch { }

                            // Try to get a data summary (e.g. selected genotype name)
                            try
                            {
                                if (getData != null)
                                {
                                    var data = getData.Invoke(module, null);
                                    if (data != null)
                                    {
                                        var sb = new System.Text.StringBuilder();
                                        foreach (var f in data.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public))
                                        {
                                            try
                                            {
                                                var val = f.GetValue(data);
                                                if (val != null)
                                                {
                                                    string vs = val.ToString();
                                                    if (vs.Length > 60) vs = vs.Substring(0, 60);
                                                    if (sb.Length > 0) sb.Append(", ");
                                                    sb.Append(f.Name).Append("=").Append(vs);
                                                }
                                            }
                                            catch { }
                                        }
                                        dataSummary = sb.ToString();
                                    }
                                }
                            }
                            catch { }

                            moduleList.Add("{\"module\":\"" + Json.Escape(name) +
                                "\",\"enabled\":" + (enabled ? "true" : "false") +
                                ",\"valid\":" + (valid ? "true" : "false") +
                                (errors.Length > 0 ? ",\"errors\":\"" + Json.Escape(errors) + "\"" : "") +
                                (warnings.Length > 0 ? ",\"warnings\":\"" + Json.Escape(warnings) + "\"" : "") +
                                (dataSummary.Length > 0 ? ",\"data\":\"" + Json.Escape(dataSummary) + "\"" : "") +
                                "}");
                        }
                    }

                    // Get current view
                    string view = SafeGetView();

                    result = "{\"ok\":true,\"action\":\"chargen_state\",\"view\":\"" + Json.Escape(view) +
                             "\",\"modules\":[" + string.Join(",", moduleList) + "]}";
                }
                catch (Exception e)
                {
                    result = "{\"error\":\"" + Json.Escape(e.ToString()) + "\"}";
                }
            }, timeoutMs: 10000);

            if (!completed)
                return "{\"error\":\"timeout\"}";
            return result ?? "{\"error\":\"no result\"}";
        }

        /// <summary>
        /// Advance the EmbarkBuilder to the next chargen screen.
        /// Calls EmbarkBuilder.advance(force, editableOnly, deferLayout) on the main thread.
        /// </summary>
        private static string ChargenAdvance(bool force)
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                try
                {
                    var builder = UnityEngine.Object.FindObjectOfType<XRL.CharacterBuilds.EmbarkBuilder>();
                    if (builder == null)
                    {
                        result = "{\"error\":\"EmbarkBuilder not found\"}";
                        return;
                    }

                    var advanceMethod = typeof(XRL.CharacterBuilds.EmbarkBuilder).GetMethod(
                        "advance",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (advanceMethod == null)
                    {
                        result = "{\"error\":\"advance method not found\"}";
                        return;
                    }

                    var ps = advanceMethod.GetParameters();
                    object[] args;
                    if (ps.Length == 1)
                        args = new object[] { force };
                    else if (ps.Length == 2)
                        args = new object[] { force, false };
                    else
                        args = new object[] { force, false, false };

                    advanceMethod.Invoke(builder, args);
                    result = "{\"ok\":true,\"action\":\"chargen_advance\"}";
                }
                catch (Exception e)
                {
                    result = "{\"error\":\"" + Json.Escape(e.ToString()) + "\"}";
                }
            }, timeoutMs: 10000);

            if (!completed)
                return "{\"error\":\"timeout\"}";
            return result ?? "{\"ok\":true,\"action\":\"chargen_advance\"}";
        }

        /// <summary>
        /// Trigger a random selection in the current chargen screen.
        /// Pushes CmdChargenRandom via the console keyboard (works if the
        /// EmbarkBuilder reads from ConsoleLib.Console.Keyboard).
        /// </summary>
        private static string ChargenRandom()
        {
            PushCommandSafe("CmdChargenRandom");
            return "{\"ok\":true,\"action\":\"chargen_random\"}";
        }

        /// <summary>
        /// Fire a UI event on the EmbarkBuilder (e.g. "Chargen:Next", "Accept").
        /// </summary>
        private static string ChargenUIEvent(string eventId, string element)
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                try
                {
                    var builder = UnityEngine.Object.FindObjectOfType<XRL.CharacterBuilds.EmbarkBuilder>();
                    if (builder == null)
                    {
                        result = "{\"error\":\"EmbarkBuilder not found\"}";
                        return;
                    }

                    var method = typeof(XRL.CharacterBuilds.EmbarkBuilder).GetMethod(
                        "handleUIEvent",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (method == null)
                    {
                        result = "{\"error\":\"handleUIEvent not found\"}";
                        return;
                    }

                    var ps = method.GetParameters();
                    object[] args;
                    if (ps.Length == 1)
                        args = new object[] { eventId };
                    else
                        args = new object[] { eventId, string.IsNullOrEmpty(element) ? null : element };

                    method.Invoke(builder, args);
                    result = "{\"ok\":true,\"action\":\"chargen_ui_event\",\"event\":\"" + Json.Escape(eventId) + "\"}";
                }
                catch (Exception e)
                {
                    result = "{\"error\":\"" + Json.Escape(e.ToString()) + "\"}";
                }
            }, timeoutMs: 10000);

            if (!completed)
                return "{\"error\":\"timeout\"}";
            return result ?? "{\"ok\":true,\"action\":\"chargen_ui_event\"}";
        }

        private static string PressCommand(string command)
        {
            if (string.IsNullOrEmpty(command))
                return "{\"error\":\"no command specified\"}";

            PushCommandSafe(command);
            return "{\"ok\":true,\"action\":\"press_command\",\"command\":\"" + Json.Escape(command) + "\"}";
        }

        private static string OpenScreen(string screen)
        {
            // Command names verified against Commands.xml
            string cmd;
            switch (screen.ToLower())
            {
                case "inventory": cmd = "CmdInventory"; break;
                case "equipment": cmd = "CmdEquipment"; break;
                case "skills": cmd = "CmdSkillsPowers"; break;
                case "powers": cmd = "CmdSkillsPowers"; break;
                case "character": cmd = "CmdCharacter"; break;
                case "attributes": cmd = "CmdCharacter"; break;
                case "companions": cmd = "CmdCompanions"; break;
                case "quests": cmd = "CmdQuests"; break;
                case "journal": cmd = "CmdJournal"; break;
                case "abilities": cmd = "CmdAbilities"; break;
                case "factions": cmd = "CmdFactions"; break;
                case "reputation": cmd = "CmdFactions"; break;
                case "effects": cmd = "CmdActiveEffects"; break;
                case "status": cmd = "CmdActiveEffects"; break;
                case "help": cmd = "CmdHelp"; break;
                case "options": cmd = "CmdOptions"; break;
                case "messages": cmd = "CmdMessageHistory"; break;
                case "message_history": cmd = "CmdMessageHistory"; break;
                default:
                    return "{\"error\":\"unknown screen: " + Json.Escape(screen) + "\"}";
            }

            PushCommandSafe(cmd);
            return "{\"ok\":true,\"action\":\"open_screen\",\"screen\":\"" + Json.Escape(screen) + "\"}";
        }

        /// <summary>
        /// Close the current menu/screen. View-aware:
        /// - Stage: push CmdEscape (for console modals like look mode)
        /// - StatusScreensScreen: call Exit() on the screen instance (uGUI)
        /// - PopupMessage / DynamicPopupMessage: call Hide() on the PopupMessage instance.
        ///   NEVER call PopGameView() on popups — it can freeze the game.
        /// - Looker: push CmdEscape
        /// - MainMenu / EmbarkBuilder / Chargen: do nothing (top-level screens)
        /// - Unknown overlay: try Hide() on any WindowBase, then PopGameView() as last resort
        ///   (without pushing escape, which can exit the underlying screen)
        /// </summary>
        private static string CloseMenu()
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                try
                {
                    string view = SafeGetView();
                    string closed = "none";

                    // Modern-UI popups (incl. conversations) sit on top of any
                    // view: dismiss through the popup's own Cancel/Continue
                    // button so the blocked game thread resumes cleanly.
                    PopupBridge.Refresh();
                    if (PopupBridge.IsOpen)
                    {
                        result = PopupBridge.Respond(0, null, true, null);
                        return;
                    }

                    switch (view)
                    {
                        case "":
                        case "Stage":
                            // Console modals (look mode, etc.) — push Escape key
                            Keyboard.PushKey(KeyCode.Escape);
                            closed = "esc_key";
                            break;

                        case "PopupMessage":
                        case "DynamicPopupMessage":
                            // View says popup but none is answerable (already
                            // closing). Do nothing: Hide() or Escape here would
                            // cancel the game's wait or exit the screen below.
                            closed = "none";
                            break;

                        case "Looker":
                            // Looker is a console screen — push Escape key
                            // (not CmdEscape command, which it may not handle)
                            Keyboard.PushKey(KeyCode.Escape);
                            closed = "esc_key";
                            break;

                        case "MainMenu":
                        case "Chargen":
                            // Top-level screens — nothing to close
                            closed = "none";
                            break;

                        case "EmbarkBuilder":
                            // In chargen — don't close (would abort character creation)
                            closed = "none";
                            break;

                        default:
                            // Generic uGUI screen handling. NEVER use PopGameView()
                            // directly — it can freeze the game (confirmed with
                            // AbilityManagerScreen and PopupMessage). Instead, find
                            // the screen instance and call Exit(), Cancel(), or
                            // Hide() on it. These methods internally schedule the
                            // view pop safely (next frame, from within the screen's
                            // own update loop).
                            if (TryCallScreenExit("Qud.UI." + view, "Exit"))
                            {
                                closed = "Exit";
                            }
                            else if (TryCallScreenExit("Qud.UI." + view, "Cancel"))
                            {
                                closed = "Cancel";
                            }
                            else if (TryHideScreenByViewName(view))
                            {
                                closed = "Hide";
                            }
                            else
                            {
                                // Last resort: push Escape key (for console
                                // screens) — do NOT call PopGameView.
                                Keyboard.PushKey(KeyCode.Escape);
                                closed = "esc_key";
                            }
                            break;
                    }

                    result = "{\"ok\":true,\"action\":\"close_menu\",\"view\":\"" + Json.Escape(view) +
                             "\",\"method\":\"" + Json.Escape(closed) + "\"}";
                }
                catch (Exception e)
                {
                    result = "{\"error\":\"" + Json.Escape(e.Message) + "\"}";
                }
            }, timeoutMs: 5000);

            if (!completed)
                return "{\"error\":\"timeout waiting for main thread\"}";
            return result ?? "{\"ok\":true,\"action\":\"close_menu\"}";
        }

        /// <summary>
        /// Find a screen instance by view name (e.g. "StatusScreensScreen")
        /// and call Exit() or Hide() on it. Tries Exit() first (proper close),
        /// then Hide(). Searches Qud.UI namespace first.
        /// </summary>
        private static bool TryHideScreenByViewName(string viewName)
        {
            try
            {
                // Try Qud.UI.{viewName}
                var type = FindType("Qud.UI." + viewName);
                if (type == null)
                {
                    // Try XRL.UI.{viewName}
                    type = FindType("XRL.UI." + viewName);
                }
                if (type == null) return false;

                var instance = UnityEngine.Object.FindObjectOfType(type);
                if (instance == null) return false;

                // Try Exit() first — StatusScreensScreen needs this
                var exitMethod = type.GetMethod("Exit",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (exitMethod != null)
                {
                    exitMethod.Invoke(instance, null);
                    return true;
                }

                // Try Cancel() — AbilityManagerScreen uses this
                var cancelMethod = type.GetMethod("Cancel",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (cancelMethod != null && cancelMethod.GetParameters().Length == 0)
                {
                    cancelMethod.Invoke(instance, null);
                    return true;
                }

                // Then try Hide() — PopupMessage uses this
                var hideMethod = type.GetMethod("Hide",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (hideMethod != null)
                {
                    hideMethod.Invoke(instance, null);
                    return true;
                }
            }
            catch { }
            return false;
        }

        private static string SafeGetView()
        {
            try { return GameManager.Instance?.CurrentGameView ?? ""; }
            catch { return ""; }
        }

        /// <summary>
        /// Press a popup button by command/label (default "Yes"). Falls back to
        /// the console key for classic-UI popups (Options.ModernUI off).
        /// </summary>
        private static string ConfirmPopup(string command)
        {
            if (string.IsNullOrEmpty(command)) command = "Yes";
            string captured = command;
            return OnPopupOrClassic(
                () => PopupBridge.Respond(0, captured, false, null),
                () => Keyboard.PushKey(captured.ToLowerInvariant() == "no" ? KeyCode.N : KeyCode.Y),
                "confirm_popup");
        }

        private static string RespondPopup(int option, string button, bool dismiss, string text)
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                PopupBridge.Refresh();
                result = PopupBridge.Respond(option, button, dismiss, text);
            }, timeoutMs: 5000);
            if (!completed)
                return "{\"error\":\"timeout waiting for main thread\"}";
            return result ?? "{\"error\":\"no result\"}";
        }

        /// <summary>
        /// Run popupAction on the main thread if a modern popup is open;
        /// otherwise, if a classic console popup is showing, run classicAction
        /// (which pushes console keys).
        /// </summary>
        private static string OnPopupOrClassic(Func<string> popupAction, Action classicAction, string actionName)
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                PopupBridge.Refresh();
                if (PopupBridge.IsOpen)
                {
                    result = popupAction();
                    return;
                }
                string view = SafeGetView();
                if (view.StartsWith("Popup:"))
                {
                    classicAction();
                    result = "{\"ok\":true,\"action\":\"" + actionName + "\",\"via\":\"console_key\",\"view\":\"" + Json.Escape(view) + "\"}";
                    return;
                }
                result = "{\"error\":\"no popup is open\",\"view\":\"" + Json.Escape(view) + "\"}";
            }, timeoutMs: 5000);
            if (!completed)
                return "{\"error\":\"timeout waiting for main thread\"}";
            return result ?? "{\"error\":\"no result\"}";
        }

        /// <summary>Actions that make no sense while a modal popup is up.</summary>
        private static bool BlockedByPopup(string action)
        {
            switch (action)
            {
                case "move":
                case "wait":
                case "interact":
                case "get":
                case "use_item":
                case "auto_explore":
                case "travel":
                case "go_stairs":
                case "open_screen":
                case "look":
                case "press_command":
                    return true;
                default:
                    return false;
            }
        }

        /// <summary>
        /// Find a uGUI screen instance by type name and call a method on it.
        /// </summary>
        private static bool TryCallScreenExit(string typeName, string methodName)
        {
            try
            {
                var type = FindType(typeName);
                if (type == null) return false;
                var instance = UnityEngine.Object.FindObjectOfType(type);
                if (instance == null) return false;
                var method = type.GetMethod(methodName, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (method == null) return false;
                method.Invoke(instance, null);
                return true;
            }
            catch { return false; }
        }

        private static bool TryCallScreenHide(string typeName, string methodName)
        {
            return TryCallScreenExit(typeName, methodName);
        }

        private static Type FindType(string fullName)
        {
            // Search all loaded assemblies
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                var type = asm.GetType(fullName);
                if (type != null) return type;
            }
            return null;
        }

        private static string ChooseOption(int option)
        {
            if (option < 1)
                return "{\"error\":\"option must be >= 1\"}";

            int captured = option;
            return OnPopupOrClassic(
                () => PopupBridge.Respond(captured, null, false, null),
                () =>
                {
                    if (captured <= 9) Keyboard.PushKey((KeyCode)('0' + captured));
                },
                "choose_option");
        }

        private static string AutoExplore()
        {
            PushCommandSafe("CmdAutoExplore");
            return "{\"ok\":true,\"action\":\"auto_explore\"}";
        }

        private static string Travel(string direction)
        {
            string cmd = DirectionToTravelCommand(direction);
            if (cmd == null)
                return "{\"error\":\"invalid direction: " + Json.Escape(direction) + "\"}";

            PushCommandSafe(cmd);
            return "{\"ok\":true,\"action\":\"travel\",\"direction\":\"" + Json.Escape(direction) + "\"}";
        }

        private static string GoStairs(string direction)
        {
            switch (direction.ToLower())
            {
                case "up":
                    PushCommandSafe("CmdMoveU");
                    break;
                case "down":
                    PushCommandSafe("CmdMoveD");
                    break;
                default:
                    return "{\"error\":\"invalid stairs direction: " + Json.Escape(direction) + "\"}";
            }
            return "{\"ok\":true,\"action\":\"go_stairs\",\"direction\":\"" + Json.Escape(direction) + "\"}";
        }

        private static string Save()
        {
            PushCommandSafe("CmdSave");
            return "{\"ok\":true,\"action\":\"save\"}";
        }

        /// <summary>
        /// Directly save the game by calling XRLGame.SaveGame() or QuickSave()
        /// on the main thread, bypassing the CmdSave command which may open
        /// a dialog or require confirmation.
        /// </summary>
        private static string SaveGame()
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                try
                {
                    var game = XRLCore.Core?.Game;
                    if (game == null)
                    {
                        result = "{\"error\":\"no active game to save\"}";
                        return;
                    }

                    // Try QuickSave first (simplest, no params)
                    var quickSave = game.GetType().GetMethod("QuickSave",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (quickSave != null)
                    {
                        System.Console.WriteLine("[mcp] SaveGame: calling QuickSave()");
                        quickSave.Invoke(game, null);
                        result = "{\"ok\":true,\"action\":\"save_game\",\"method\":\"QuickSave\"}";
                        return;
                    }

                    // Fallback: SaveGame(GameName, Message, CopyCache, CopyPrimary)
                    var saveGame = game.GetType().GetMethod("SaveGame",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (saveGame != null)
                    {
                        var ps = saveGame.GetParameters();
                        var args = new object[ps.Length];
                        for (int i = 0; i < ps.Length; i++)
                        {
                            var p = ps[i];
                            if (p.ParameterType == typeof(string))
                                args[i] = null;
                            else if (p.ParameterType == typeof(bool))
                                args[i] = true;
                            else if (p.HasDefaultValue)
                                args[i] = p.DefaultValue;
                            else
                                args[i] = null;
                        }
                        System.Console.WriteLine("[mcp] SaveGame: calling SaveGame() with " + ps.Length + " params");
                        saveGame.Invoke(game, args);
                        result = "{\"ok\":true,\"action\":\"save_game\",\"method\":\"SaveGame\"}";
                        return;
                    }

                    // Last resort: XRLCore.Core.SaveGame(null)
                    var coreSave = typeof(XRLCore).GetMethod("SaveGame",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (coreSave != null)
                    {
                        System.Console.WriteLine("[mcp] SaveGame: calling XRLCore.SaveGame(null)");
                        coreSave.Invoke(XRLCore.Core, new object[] { null });
                        result = "{\"ok\":true,\"action\":\"save_game\",\"method\":\"XRLCore.SaveGame\"}";
                        return;
                    }

                    result = "{\"error\":\"no save method found\"}";
                }
                catch (Exception e)
                {
                    result = "{\"error\":\"" + Json.Escape(e.InnerException?.Message ?? e.Message) + "\"}";
                }
            }, timeoutMs: 30000);

            if (!completed)
                return "{\"error\":\"timeout\"}";
            return result ?? "{\"error\":\"no result\"}";
        }

        /// <summary>
        /// Open the load game screen. Pushes CmdLoad which opens the save
        /// selection UI from the main menu or in-game.
        /// </summary>
        private static string LoadGame()
        {
            PushCommandSafe("CmdLoad");
            return "{\"ok\":true,\"action\":\"load_game\"}";
        }

        private static string Quit()
        {
            PushCommandSafe("CmdQuit");
            return "{\"ok\":true,\"action\":\"quit\"}";
        }

        /// <summary>
        /// Quit the current game and return to the main menu.
        /// Pushes CmdQuit which triggers the save-and-quit flow.
        /// </summary>
        private static string QuitToMenu()
        {
            PushCommandSafe("CmdQuit");
            return "{\"ok\":true,\"action\":\"quit_to_menu\"}";
        }

        private static string Abandon()
        {
            // No direct "abandon character" command exists; quitting to the menu ends the run.
            PushCommandSafe("CmdQuit");
            return "{\"ok\":true,\"action\":\"abandon\"}";
        }

        private static string Look()
        {
            PushCommandSafe("CmdLook");
            return "{\"ok\":true,\"action\":\"look\"}";
        }

        private static string ShowLabels()
        {
            return "{\"error\":\"show_labels is not supported in this build\"}";
        }

        /// <summary>
        /// List available save games by scanning the save directory.
        /// </summary>
        private static string ListSaves()
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                try
                {
                    var sb = new System.Text.StringBuilder();
                    sb.Append("{\"ok\":true,\"action\":\"list_saves\",\"saves\":[");

                    string savePath = null;
                    try { savePath = XRLCore.SavePath; } catch { }

                    // Also check Synced/Saves (Steam Cloud saves)
                    var savePaths = new System.Collections.Generic.List<string>();
                    if (!string.IsNullOrEmpty(savePath))
                        savePaths.Add(savePath);
                    try
                    {
                        string syncedPath = XRLCore.SyncedPath;
                        if (!string.IsNullOrEmpty(syncedPath))
                            savePaths.Add(System.IO.Path.Combine(syncedPath, "Saves"));
                    }
                    catch { }
                    // Also check common locations
                    savePaths.Add(System.IO.Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) + "Low",
                        "Freehold Games", "CavesOfQud", "Synced", "Saves"));
                    savePaths.Add(System.IO.Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) + "Low",
                        "Freehold Games", "CavesOfQud", "Saves"));

                    bool first = true;
                    var seenSaves = new System.Collections.Generic.HashSet<string>();
                    foreach (var path in savePaths)
                    {
                        if (string.IsNullOrEmpty(path) || !System.IO.Directory.Exists(path))
                            continue;

                        foreach (var dir in System.IO.Directory.GetDirectories(path))
                        {
                            var name = System.IO.Path.GetFileName(dir);
                            if (seenSaves.Contains(name)) continue;

                            // Check for save files (Primary.sav.gz or Checkpoint.sav.gz)
                            bool hasSave = System.IO.File.Exists(System.IO.Path.Combine(dir, "Primary.sav.gz"))
                                        || System.IO.File.Exists(System.IO.Path.Combine(dir, "Checkpoint.sav.gz"))
                                        || System.IO.File.Exists(System.IO.Path.Combine(dir, name + ".sav"));

                            // Try to read Primary.json for the character name
                            string charName = name;
                            try
                            {
                                var jsonPath = System.IO.Path.Combine(dir, "Primary.json");
                                if (System.IO.File.Exists(jsonPath))
                                {
                                    var json = System.IO.File.ReadAllText(jsonPath);
                                    // Simple extraction of "Name" field
                                    var match = System.Text.RegularExpressions.Regex.Match(json, "\"Name\"\\s*:\\s*\"([^\"]+)\"");
                                    if (match.Success)
                                        charName = match.Groups[1].Value;
                                }
                            }
                            catch { }

                            if (hasSave)
                            {
                                seenSaves.Add(name);
                                if (!first) sb.Append(",");
                                first = false;
                                sb.Append("{\"id\":\"").Append(Json.Escape(name))
                                  .Append("\",\"name\":\"").Append(Json.Escape(charName))
                                  .Append("\",\"path\":\"").Append(Json.Escape(dir)).Append("\"}");
                            }
                        }
                    }

                    sb.Append("]}");
                    result = sb.ToString();
                }
                catch (Exception e)
                {
                    result = "{\"error\":\"" + Json.Escape(e.Message) + "\"}";
                }
            }, timeoutMs: 5000);

            if (!completed)
                return "{\"error\":\"timeout\"}";
            return result ?? "{\"ok\":true,\"action\":\"list_saves\",\"saves\":[]}";
        }

        public static string DirectionToMoveCommand(string direction)
        {
            switch (direction.ToLower())
            {
                case "up": case "n": case "north": return "CmdMoveN";
                case "down": case "s": case "south": return "CmdMoveS";
                case "left": case "w": case "west": return "CmdMoveW";
                case "right": case "e": case "east": return "CmdMoveE";
                case "up_left": case "nw": case "northwest": return "CmdMoveNW";
                case "up_right": case "ne": case "northeast": return "CmdMoveNE";
                case "down_left": case "sw": case "southwest": return "CmdMoveSW";
                case "down_right": case "se": case "southeast": return "CmdMoveSE";
                default: return null;
            }
        }

        public static string DirectionToUseCommand(string direction)
        {
            switch (direction.ToLower())
            {
                case "": return "CmdUse";
                case "up": case "n": case "north": return "CmdUseN";
                case "down": case "s": case "south": return "CmdUseS";
                case "left": case "w": case "west": return "CmdUseW";
                case "right": case "e": case "east": return "CmdUseE";
                case "up_left": case "nw": case "northwest": return "CmdUseNW";
                case "up_right": case "ne": case "northeast": return "CmdUseNE";
                case "down_left": case "sw": case "southwest": return "CmdUseSW";
                case "down_right": case "se": case "southeast": return "CmdUseSE";
                default: return null;
            }
        }

        public static string DirectionToTravelCommand(string direction)
        {
            switch (direction.ToLower())
            {
                case "up": case "n": case "north": return "CmdMoveFarN";
                case "down": case "s": case "south": return "CmdMoveFarS";
                case "left": case "w": case "west": return "CmdMoveFarW";
                case "right": case "e": case "east": return "CmdMoveFarE";
                default: return null;
            }
        }
    }
}
