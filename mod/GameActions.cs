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

                switch (action)
                {
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
                        return ContinueGame();
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
                case "wield":
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
                    if (equipped != null && equipped.DisplayNameOnly.ToLowerInvariant().Contains(lower))
                        return equipped;
                }
            }

            // Check inventory
            var inventory = player.GetPart<Inventory>();
            if (inventory != null)
            {
                foreach (var obj in inventory.Objects)
                {
                    if (obj != null && obj.DisplayNameOnly.ToLowerInvariant().Contains(lower))
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
        /// Continue the last save from the main menu. Tries multiple approaches:
        /// 1. XRLGame.LoadCurrentGame(saveId, true, null) — static, takes save dir name
        /// 2. XRLGame.LoadGame(fullPath, null, true, null) — static, takes full path
        /// 3. Find Qud.UI.SaveManagement instance and call ContinueMenu()
        /// 4. Run LoadCurrentGame on a background thread (it may block)
        /// </summary>
        private static string ContinueGame()
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                try
                {
                    string view = SafeGetView();
                    if (view == "Stage")
                    {
                        result = "{\"error\":\"already in game\"}";
                        return;
                    }

                    // Find the most recent save directory
                    string saveId = FindMostRecentSave();
                    if (string.IsNullOrEmpty(saveId))
                    {
                        result = "{\"error\":\"no saves found\"}";
                        return;
                    }

                    // Build the full path to the save directory
                    string savePath = FindSavePath(saveId);
                    System.Console.WriteLine("[mcp] ContinueGame: saveId=" + saveId + " path=" + savePath);

                    var gameType = FindType("XRL.XRLGame");
                    if (gameType == null)
                    {
                        result = "{\"error\":\"XRLGame type not found\"}";
                        return;
                    }

                    // Approach 1: LoadCurrentGame(GameName, ShowPopup, GameState)
                    var loadCurrent = gameType.GetMethod("LoadCurrentGame",
                        BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
                    if (loadCurrent != null)
                    {
                        var ps = loadCurrent.GetParameters();
                        
                        // Read the character name from Primary.json
                        string charName = saveId; // fallback to UUID
                        try
                        {
                            var jsonPath = System.IO.Path.Combine(savePath ?? "", "Primary.json");
                            if (System.IO.File.Exists(jsonPath))
                            {
                                var json = System.IO.File.ReadAllText(jsonPath);
                                var match = System.Text.RegularExpressions.Regex.Match(json, "\"Name\"\\s*:\\s*\"([^\"]+)\"");
                                if (match.Success) charName = match.Groups[1].Value;
                            }
                        }
                        catch { }
                        System.Console.WriteLine("[mcp] ContinueGame: charName=" + charName + " saveId=" + saveId);

                        // Try both UUID and character name as GameName
                        foreach (var gameName in new[] { charName, saveId })
                        {
                            var args = new object[ps.Length];
                            for (int i = 0; i < ps.Length; i++)
                            {
                                var p = ps[i];
                                string pname = p.Name.ToLowerInvariant();
                                if (pname == "gamename" || pname == "name" || pname == "id")
                                    args[i] = gameName;
                                else if (p.ParameterType == typeof(bool))
                                    args[i] = true;
                                else if (p.ParameterType.IsGenericType && 
                                         p.ParameterType.GetGenericTypeDefinition() == typeof(System.Collections.Generic.Dictionary<,>))
                                {
                                    // Create an empty dictionary of the right type
                                    args[i] = System.Activator.CreateInstance(p.ParameterType);
                                }
                                else if (p.HasDefaultValue)
                                    args[i] = p.DefaultValue;
                                else
                                    args[i] = null;
                            }
                            System.Console.WriteLine("[mcp] Trying LoadCurrentGame with GameName=" + gameName + ", GameState=" + (args[ps.Length-1] != null ? "dict" : "null"));
                            try
                            {
                                var t = new System.Threading.Thread(() =>
                                {
                                    try { loadCurrent.Invoke(null, args); }
                                    catch (Exception e)
                                    {
                                        System.Console.WriteLine("[mcp] LoadCurrentGame(" + gameName + ") error: " + e.InnerException?.Message);
                                    }
                                }) { IsBackground = true, Name = "McpLoadGame" };
                                t.Start();
                                result = "{\"ok\":true,\"action\":\"continue_game\",\"saveId\":\"" + Json.Escape(saveId) + "\",\"gameName\":\"" + Json.Escape(gameName) + "\",\"method\":\"LoadCurrentGame\"}";
                                return;
                            }
                            catch (Exception e)
                            {
                                System.Console.WriteLine("[mcp] LoadCurrentGame(" + gameName + ") invoke failed: " + e.Message);
                            }
                        }
                    }

                    // Approach 2: LoadGame(Path, Session, ShowPopup, GameState)
                    var loadGame = gameType.GetMethod("LoadGame",
                        BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
                    if (loadGame != null && !string.IsNullOrEmpty(savePath))
                    {
                        var ps = loadGame.GetParameters();
                        var args = new object[ps.Length];
                        for (int i = 0; i < ps.Length; i++)
                        {
                            var p = ps[i];
                            string pname = p.Name.ToLowerInvariant();
                            if (pname == "path")
                                args[i] = savePath;
                            else if (p.ParameterType == typeof(bool))
                                args[i] = true;
                            else if (p.HasDefaultValue)
                                args[i] = p.DefaultValue;
                            else
                                args[i] = null;
                        }
                        System.Console.WriteLine("[mcp] Trying LoadGame with path=" + savePath);
                        try
                        {
                            var t = new System.Threading.Thread(() =>
                            {
                                try { loadGame.Invoke(null, args); }
                                catch (Exception e)
                                {
                                    System.Console.WriteLine("[mcp] LoadGame error: " + e);
                                }
                            }) { IsBackground = true, Name = "McpLoadGame2" };
                            t.Start();
                            result = "{\"ok\":true,\"action\":\"continue_game\",\"saveId\":\"" + Json.Escape(saveId) + "\",\"method\":\"LoadGame\"}";
                            return;
                        }
                        catch (Exception e)
                        {
                            System.Console.WriteLine("[mcp] LoadGame invoke failed: " + e.Message);
                        }
                    }

                    // Approach 3: Use SaveManagement screen's ContinueMenu()
                    var smType = FindType("Qud.UI.SaveManagement");
                    if (smType != null)
                    {
                        var smInstance = UnityEngine.Object.FindObjectOfType(smType);
                        if (smInstance != null)
                        {
                            var continueMenu = smType.GetMethod("ContinueMenu",
                                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                            if (continueMenu != null)
                            {
                                System.Console.WriteLine("[mcp] Trying SaveManagement.ContinueMenu()");
                                continueMenu.Invoke(smInstance, null);
                                result = "{\"ok\":true,\"action\":\"continue_game\",\"saveId\":\"" + Json.Escape(saveId) + "\",\"method\":\"SaveManagement.ContinueMenu\"}";
                                return;
                            }
                        }
                    }

                    result = "{\"error\":\"all load approaches failed\",\"saveId\":\"" + Json.Escape(saveId) + "\"}";
                }
                catch (Exception e)
                {
                    var inner = e.InnerException?.Message ?? e.Message;
                    result = "{\"error\":\"" + Json.Escape(inner) + "\",\"stack\":\"" + Json.Escape(e.StackTrace ?? "") + "\"}";
                }
            }, timeoutMs: 15000);

            if (!completed)
                return "{\"error\":\"timeout\"}";
            return result ?? "{\"ok\":true,\"action\":\"continue_game\"}";
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
                            // uGUI popup — find PopupMessage instance and call Hide().
                            // DO NOT push escape or PopGameView — that exits the
                            // underlying screen (e.g. EmbarkBuilder) too.
                            TryHideAnyPopup();
                            closed = "Popup.Hide";
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

        /// <summary>
        /// Find any active PopupMessage (or WindowBase) instance and call Hide() on it.
        /// </summary>
        private static bool TryHideAnyPopup()
        {
            try
            {
                // Try PopupMessage first
                var popupType = FindType("Qud.UI.PopupMessage");
                if (popupType != null)
                {
                    var instance = UnityEngine.Object.FindObjectOfType(popupType);
                    if (instance != null)
                    {
                        var hideMethod = popupType.GetMethod("Hide",
                            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                        if (hideMethod != null)
                        {
                            hideMethod.Invoke(instance, null);
                            return true;
                        }
                    }
                }

                // Try WindowBase (base class of PopupMessage)
                var windowType = FindType("Qud.UI.WindowBase");
                if (windowType != null)
                {
                    var instances = UnityEngine.Object.FindObjectsOfType(windowType);
                    foreach (var inst in instances)
                    {
                        if (inst == null) continue;
                        // Only hide if it's not the Stage or MainMenu
                        var name = inst.GetType().Name;
                        if (name == "Stage" || name == "MainMenu" || name == "EmbarkBuilder") continue;
                        var hideMethod = inst.GetType().GetMethod("Hide",
                            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                        if (hideMethod != null)
                        {
                            hideMethod.Invoke(inst, null);
                            return true;
                        }
                    }
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
        /// Confirm the current popup. For Yes/No popups, this activates the
        /// "Yes" button. Tries multiple approaches:
        /// 1. Call commandCallback delegate via DynamicInvoke
        /// 2. Call OnActivateCommand with a QudMenuItem
        /// 3. Find and click a button GameObject
        /// </summary>
        private static string ConfirmPopup(string command)
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                try
                {
                    var popupType = FindType("Qud.UI.PopupMessage");
                    if (popupType == null)
                    {
                        result = "{\"error\":\"PopupMessage type not found\"}";
                        return;
                    }

                    var instance = UnityEngine.Object.FindObjectOfType(popupType);
                    if (instance == null)
                    {
                        result = "{\"error\":\"no active popup\"}";
                        return;
                    }

                    // Approach 1: Call commandCallback delegate via DynamicInvoke
                    var callbackField = popupType.GetField("commandCallback",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (callbackField != null)
                    {
                        var callback = callbackField.GetValue(instance);
                        if (callback != null)
                        {
                            var cbType = callback.GetType();
                            var invokeMethod = cbType.GetMethod("Invoke");
                            if (invokeMethod != null)
                            {
                                var cbParams = invokeMethod.GetParameters();
                                if (cbParams.Length == 1)
                                {
                                    // Try to create the right parameter type
                                    var paramType = cbParams[0].ParameterType;
                                    object arg = null;
                                    if (paramType == typeof(string))
                                        arg = command;
                                    else if (paramType.Name == "QudMenuItem")
                                    {
                                        // Create a QudMenuItem with the command as text/command
                                        var menuItemType = FindType("Qud.UI.QudMenuItem");
                                        if (menuItemType != null)
                                        {
                                            arg = System.Activator.CreateInstance(menuItemType);
                                            // Try to set Command or Text property
                                            var cmdProp = menuItemType.GetProperty("Command") ?? menuItemType.GetProperty("command");
                                            var textProp = menuItemType.GetProperty("Text") ?? menuItemType.GetProperty("text");
                                            var cmdField = menuItemType.GetField("Command") ?? menuItemType.GetField("command");
                                            var textField = menuItemType.GetField("Text") ?? menuItemType.GetField("text");
                                            if (cmdProp != null) cmdProp.SetValue(arg, command, null);
                                            else if (cmdField != null) cmdField.SetValue(arg, command);
                                            if (textProp != null) textProp.SetValue(arg, command, null);
                                            else if (textField != null) textField.SetValue(arg, command);
                                        }
                                    }
                                    
                                    if (arg != null)
                                    {
                                        try
                                        {
                                            callback.GetType().GetMethod("Invoke").Invoke(callback, new[] { arg });
                                            result = "{\"ok\":true,\"action\":\"confirm_popup\",\"method\":\"callback\",\"command\":\"" + Json.Escape(command) + "\"}";
                                            return;
                                        }
                                        catch (Exception e)
                                        {
                                            System.Console.WriteLine("[mcp] confirm_popup callback error: " + e.InnerException?.Message);
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Approach 2: Try OnActivateCommand with a QudMenuItem
                    var onActivate = popupType.GetMethod("OnActivateCommand",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (onActivate != null)
                    {
                        var menuItemType = FindType("Qud.UI.QudMenuItem");
                        if (menuItemType != null)
                        {
                            var menuItem = System.Activator.CreateInstance(menuItemType);
                            var cmdProp = menuItemType.GetProperty("Command") ?? menuItemType.GetProperty("command");
                            var textProp = menuItemType.GetProperty("Text") ?? menuItemType.GetProperty("text");
                            var cmdField = menuItemType.GetField("Command") ?? menuItemType.GetField("command");
                            var textField = menuItemType.GetField("Text") ?? menuItemType.GetField("text");
                            if (cmdProp != null) cmdProp.SetValue(menuItem, command, null);
                            else if (cmdField != null) cmdField.SetValue(menuItem, command);
                            if (textProp != null) textProp.SetValue(menuItem, command, null);
                            else if (textField != null) textField.SetValue(menuItem, command);
                            
                            onActivate.Invoke(instance, new[] { menuItem });
                            result = "{\"ok\":true,\"action\":\"confirm_popup\",\"method\":\"OnActivateCommand\",\"command\":\"" + Json.Escape(command) + "\"}";
                            return;
                        }
                    }

                    // Approach 3: Find a button with "Yes" text and click it
                    var monoBehaviour = instance as UnityEngine.MonoBehaviour;
                    if (monoBehaviour != null)
                    {
                        var buttons = monoBehaviour.GetComponentsInChildren<UnityEngine.UI.Button>(true);
                        foreach (var btn in buttons)
                        {
                            var text = btn.GetComponentInChildren<UnityEngine.UI.Text>();
                            if (text != null && text.text.ToLower().Contains(command.ToLower()))
                            {
                                btn.onClick.Invoke();
                                result = "{\"ok\":true,\"action\":\"confirm_popup\",\"method\":\"button_click\",\"command\":\"" + Json.Escape(command) + "\"}";
                                return;
                            }
                        }
                    }

                    result = "{\"error\":\"no way to confirm popup\"}";
                }
                catch (Exception e)
                {
                    result = "{\"error\":\"" + Json.Escape(e.InnerException?.Message ?? e.Message) + "\"}";
                }
            }, timeoutMs: 5000);

            if (!completed)
                return "{\"error\":\"timeout\"}";
            return result ?? "{\"ok\":true,\"action\":\"confirm_popup\"}";
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
            if (option < 1 || option > 9)
                return "{\"error\":\"option must be 1-9\"}";

            int captured = option;
            BridgeMainThread.Enqueue(() => Keyboard.PushKey((KeyCode)('0' + captured)));
            return "{\"ok\":true,\"action\":\"choose_option\",\"option\":" + option + "}";
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
