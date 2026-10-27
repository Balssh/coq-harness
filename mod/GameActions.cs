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
        /// Continue the last save from the main menu. Finds the most recent save
        /// and calls XRLGame.LoadCurrentGame() (static) on the main thread.
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

                    var gameType = FindType("XRL.XRLGame");
                    if (gameType == null)
                    {
                        result = "{\"error\":\"XRLGame type not found\"}";
                        return;
                    }

                    // LoadCurrentGame(string GameName, bool ShowPopup, GameState) — static
                    var loadMethod = gameType.GetMethod("LoadCurrentGame",
                        BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
                    if (loadMethod == null)
                    {
                        result = "{\"error\":\"LoadCurrentGame not found\"}";
                        return;
                    }

                    var ps = loadMethod.GetParameters();
                    var args = new object[ps.Length];
                    for (int i = 0; i < ps.Length; i++)
                    {
                        var p = ps[i];
                        string pname = p.Name.ToLowerInvariant();
                        if (pname == "gamename" || pname == "name")
                            args[i] = saveId;
                        else if (p.ParameterType == typeof(bool))
                            args[i] = true;
                        else if (p.HasDefaultValue)
                            args[i] = p.DefaultValue;
                        else
                            args[i] = null;
                    }

                    loadMethod.Invoke(null, args);
                    result = "{\"ok\":true,\"action\":\"continue_game\",\"saveId\":\"" + Json.Escape(saveId) + "\"}";
                }
                catch (Exception e)
                {
                    var inner = e.InnerException?.Message ?? e.Message;
                    result = "{\"error\":\"" + Json.Escape(inner) + "\"}";
                }
            }, timeoutMs: 15000);

            if (!completed)
                return "{\"error\":\"timeout\"}";
            return result ?? "{\"ok\":true,\"action\":\"continue_game\"}";
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
