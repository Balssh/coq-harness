using System;
using XRL;
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
        /// (CmdDrink, CmdEat, etc.) trigger modal dialogs that hold the keyboard
        /// lock, which would deadlock the pump thread.
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
                    case "new_game":
                        return NewGame(cmd.GetStr("code", ""));
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
                    case "quit":
                        return Quit();
                    case "abandon":
                        return Abandon();
                    case "look":
                        return Look();
                    case "show_labels":
                        return ShowLabels();
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

        private static string UseItem(GameObject player, string itemName, string action)
        {
            if (player == null)
                return "{\"error\":\"not in game\"}";

            // Push the command via the game's input queue (non-blocking).
            // The game will prompt for item selection; the model handles that
            // through the UI. Do NOT use InventoryActionEvent.Check — it blocks
            // synchronously and can deadlock the pump thread if a modal dialog
            // appears (e.g. "this waterskin is empty").
            string cmd;
            switch (action)
            {
                case "eat":     cmd = "CmdEat"; break;
                case "quaff":
                case "drink":   cmd = "CmdDrink"; break;
                case "equip":
                case "wear":
                case "wield":   cmd = "CmdApply"; break;
                case "unequip": cmd = "CmdUnequip"; break;
                case "drop":    cmd = "CmdDrop"; break;
                default:
                    return "{\"error\":\"unknown item action: " + Json.Escape(action) + "\"}";
            }

            PushCommandSafe(cmd);
            return "{\"ok\":true,\"action\":\"use_item\",\"item\":\"" + Json.Escape(itemName) + "\",\"itemAction\":\"" + Json.Escape(action) + "\"}";
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
        /// Complete character creation by setting the EmbarkBuilder's finishedEvent
        /// result, which unblocks XRLCore.NewGame(). Optionally configure the
        /// character from a build code (base64+gzip+JSON, e.g. lastcharacter.txt).
        /// </summary>
        private static string NewGame(string code)
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
                                System.Reflection.BindingFlags.Instance |
                                System.Reflection.BindingFlags.Public |
                                System.Reflection.BindingFlags.NonPublic);
                            if (initMethod != null)
                                initMethod.Invoke(builder, new object[] { code });
                            else
                                result = "{\"error\":\"InitModulesFromCode not found\"}";
                        }
                        catch (Exception e)
                        {
                            result = "{\"error\":\"InitModulesFromCode failed: " + Json.Escape(e.Message) + "\"}";
                            return;
                        }
                    }

                    // Get the embarkInfo field
                    var embarkInfoField = typeof(XRL.CharacterBuilds.EmbarkBuilder).GetField(
                        "embarkInfo",
                        System.Reflection.BindingFlags.Instance |
                        System.Reflection.BindingFlags.Public |
                        System.Reflection.BindingFlags.NonPublic);
                    object embarkInfo = embarkInfoField?.GetValue(builder);

                    // Get the finishedEvent (TaskCompletionSource<EmbarkInfo>)
                    var finishedEventField = typeof(XRL.CharacterBuilds.EmbarkBuilder).GetField(
                        "finishedEvent",
                        System.Reflection.BindingFlags.Instance |
                        System.Reflection.BindingFlags.Public |
                        System.Reflection.BindingFlags.NonPublic);
                    object finishedEvent = finishedEventField?.GetValue(builder);

                    if (finishedEvent == null || embarkInfo == null)
                    {
                        result = "{\"error\":\"Could not access EmbarkBuilder internals\"}";
                        return;
                    }

                    // Complete the Task — this unblocks XRLCore.NewGame()
                    var trySetResult = finishedEvent.GetType().GetMethod("TrySetResult");
                    trySetResult?.Invoke(finishedEvent, new object[] { embarkInfo });

                    result = "{\"ok\":true,\"action\":\"new_game\"}";
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

        private static string PressCommand(string command)
        {
            if (string.IsNullOrEmpty(command))
                return "{\"error\":\"no command specified\"}";

            PushCommandSafe(command);
            return "{\"ok\":true,\"action\":\"press_command\",\"command\":\"" + Json.Escape(command) + "\"}";
        }

        private static string OpenScreen(string screen)
        {
            string cmd;
            switch (screen.ToLower())
            {
                case "inventory": cmd = "CmdInventory"; break;
                case "equipment": cmd = "CmdEquipment"; break;
                case "skills": cmd = "CmdSkillsPowers"; break;
                case "character": cmd = "CmdCharacter"; break;
                case "companions": cmd = "CmdCompanions"; break;
                case "quests": cmd = "CmdQuests"; break;
                case "journal": cmd = "CmdJournal"; break;
                case "abilities": cmd = "CmdAbilities"; break;
                case "factions": cmd = "CmdFactions"; break;
                case "help": cmd = "CmdHelp"; break;
                case "options": cmd = "CmdOptions"; break;
                default:
                    return "{\"error\":\"unknown screen: " + Json.Escape(screen) + "\"}";
            }

            PushCommandSafe(cmd);
            return "{\"ok\":true,\"action\":\"open_screen\",\"screen\":\"" + Json.Escape(screen) + "\"}";
        }

        private static string CloseMenu()
        {
            // Two strategies:
            // 1. GameManager.PopGameView() — closes uGUI overlay screens
            //    (StatusScreensScreen, etc.) which don't read ConsoleLib.Console.Keyboard.
            // 2. PushCommand(CmdSystemMenu + CmdEscape) — closes console-based
            //    modal screens (look mode, etc.) that DO read the keyboard queue.
            // Both run on the main thread for safety.
            string result = null;
            BridgeMainThread.EnqueueAndWait(() =>
            {
                try
                {
                    var gm = GameManager.Instance;
                    if (gm != null)
                    {
                        string view = null;
                        try { view = gm.CurrentGameView; } catch { }
                        if (!string.IsNullOrEmpty(view) && view != "Stage")
                            gm.PopGameView();
                    }
                }
                catch { }

                // Also send escape commands for console-based modal screens
                PushCommandSafe("CmdSystemMenu");
                PushCommandSafe("CmdEscape");

                result = "{\"ok\":true,\"action\":\"close_menu\"}";
            }, timeoutMs: 5000);

            return result ?? "{\"ok\":true,\"action\":\"close_menu\"}";
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

        private static string Quit()
        {
            PushCommandSafe("CmdQuit");
            return "{\"ok\":true,\"action\":\"quit\"}";
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
