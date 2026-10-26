using System;
using XRL;
using XRL.World;
using ConsoleLib.Console;

namespace CoQMcpBridge
{
    public static class GameActions
    {
        public static string ExecuteCommand(GameObject player, string commandJson)
        {
            if (player == null)
                return "{\"error\":\"no player\"}";

            try
            {
                var cmd = MiniJson.Parse(commandJson) as MiniJson.Obj;
                if (cmd == null)
                    return "{\"error\":\"invalid command JSON\"}";

                string action = cmd.GetStr("action", "");

                switch (action)
                {
                    case "move":
                        return Move(player, cmd.GetStr("direction", ""));
                    case "wait":
                        return Wait(player, cmd.GetInt("turns", 1));
                    case "interact":
                        return Interact(player, cmd.GetStr("direction", ""));
                    case "get":
                        return Get(player);
                    case "use_item":
                        return UseItem(player, cmd.GetStr("item", ""), cmd.GetStr("action", ""));
                    case "press_key":
                        return PressKey(cmd.GetStr("key", ""));
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
                        return "{\"error\":\"unknown action: " + action + "\"}";
                }
            }
            catch (Exception e)
            {
                return "{\"error\":\"" + Json.Escape(e.Message) + "\"}";
            }
        }

        private static string Move(GameObject player, string direction)
        {
            string cmd = DirectionToMoveCommand(direction);
            if (cmd == null)
                return "{\"error\":\"invalid direction: " + direction + "\"}";

            Keyboard.PushCommand(cmd);
            return "{\"ok\":true,\"action\":\"move\",\"direction\":\"" + direction + "\"}";
        }

        private static string Wait(GameObject player, int turns)
        {
            for (int i = 0; i < turns; i++)
                Keyboard.PushCommand("CmdWait");
            return "{\"ok\":true,\"action\":\"wait\",\"turns\":" + turns + "}";
        }

        private static string Interact(GameObject player, string direction)
        {
            string cmd = DirectionToMoveCommand(direction);
            if (cmd == null)
                return "{\"error\":\"invalid direction: " + direction + "\"}";

            Keyboard.PushCommand("CmdInteract");
            Thread_Sleep(50);
            Keyboard.PushCommand(cmd);
            return "{\"ok\":true,\"action\":\"interact\",\"direction\":\"" + direction + "\"}";
        }

        private static string Get(GameObject player)
        {
            Keyboard.PushCommand("CmdGet");
            return "{\"ok\":true,\"action\":\"get\"}";
        }

        private static string UseItem(GameObject player, string itemName, string action)
        {
            var inventory = player.GetPart<Inventory>();
            if (inventory == null)
                return "{\"error\":\"no inventory\"}";

            GameObject item = null;
            foreach (var obj in inventory.Objects)
            {
                if (obj != null && obj.DisplayNameOnly != null &&
                    obj.DisplayNameOnly.ToLower().Contains(itemName.ToLower()))
                {
                    item = obj;
                    break;
                }
            }

            if (item == null)
                return "{\"error\":\"item not found: " + itemName + "\"}";

            string cmd = null;
            switch (action)
            {
                case "equip":
                case "wear":
                case "wield":
                    cmd = "CmdEquip";
                    break;
                case "drop":
                    cmd = "CmdDrop";
                    break;
                case "quaff":
                case "drink":
                    cmd = "CmdQuaff";
                    break;
                case "eat":
                    cmd = "CmdEat";
                    break;
                case "unequip":
                    cmd = "CmdUnequip";
                    break;
                default:
                    return "{\"error\":\"unknown item action: " + action + "\"}";
            }

            Keyboard.PushCommand("CmdInventory");
            Thread_Sleep(50);
            CommandEvent.Send(player, cmd, item);
            return "{\"ok\":true,\"action\":\"use_item\",\"item\":\"" + Json.Escape(itemName) + "\",\"itemAction\":\"" + action + "\"}";
        }

        private static string PressKey(string key)
        {
            if (string.IsNullOrEmpty(key))
                return "{\"error\":\"no key specified\"}";

            Keyboard.PushKey(key.Length == 1 ? key[0] : '\0', bAllowMap: true);
            return "{\"ok\":true,\"action\":\"press_key\",\"key\":\"" + Json.Escape(key) + "\"}";
        }

        private static string PressCommand(string command)
        {
            if (string.IsNullOrEmpty(command))
                return "{\"error\":\"no command specified\"}";

            Keyboard.PushCommand(command);
            return "{\"ok\":true,\"action\":\"press_command\",\"command\":\"" + Json.Escape(command) + "\"}";
        }

        private static string OpenScreen(string screen)
        {
            string cmd = null;
            switch (screen.ToLower())
            {
                case "inventory": cmd = "CmdInventory"; break;
                case "equipment": cmd = "CmdEquipment"; break;
                case "skills": cmd = "CmdSkills"; break;
                case "character": cmd = "CmdCharacterSheet"; break;
                case "quests": cmd = "CmdQuests"; break;
                case "journal": cmd = "CmdJournal"; break;
                case "abilities": cmd = "CmdAbilities"; break;
                case "mutations": cmd = "CmdMutations"; break;
                case "map": cmd = "CmdWorldMap"; break;
                case "factions": cmd = "CmdFactions"; break;
                default:
                    return "{\"error\":\"unknown screen: " + screen + "\"}";
            }

            Keyboard.PushCommand(cmd);
            return "{\"ok\":true,\"action\":\"open_screen\",\"screen\":\"" + screen + "\"}";
        }

        private static string CloseMenu()
        {
            Keyboard.PushCommand("CmdEscape");
            return "{\"ok\":true,\"action\":\"close_menu\"}";
        }

        private static string ChooseOption(int option)
        {
            if (option < 1 || option > 9)
                return "{\"error\":\"option must be 1-9\"}";

            Keyboard.PushKey((char)('0' + option), bAllowMap: true);
            return "{\"ok\":true,\"action\":\"choose_option\",\"option\":" + option + "}";
        }

        private static string AutoExplore()
        {
            Keyboard.PushCommand("CmdAutoExplore");
            return "{\"ok\":true,\"action\":\"auto_explore\"}";
        }

        private static string Travel(string direction)
        {
            string cmd = DirectionToCardinalCommand(direction);
            if (cmd == null)
                return "{\"error\":\"invalid direction: " + direction + "\"}";

            Keyboard.PushCommand("CmdTravel");
            Thread_Sleep(50);
            Keyboard.PushCommand(cmd);
            return "{\"ok\":true,\"action\":\"travel\",\"direction\":\"" + direction + "\"}";
        }

        private static string GoStairs(string direction)
        {
            switch (direction.ToLower())
            {
                case "up":
                    Keyboard.PushCommand("CmdGoUp");
                    break;
                case "down":
                    Keyboard.PushCommand("CmdGoDown");
                    break;
                default:
                    return "{\"error\":\"invalid stairs direction: " + direction + "\"}";
            }
            return "{\"ok\":true,\"action\":\"go_stairs\",\"direction\":\"" + direction + "\"}";
        }

        private static string Save()
        {
            Keyboard.PushCommand("CmdSave");
            return "{\"ok\":true,\"action\":\"save\"}";
        }

        private static string Quit()
        {
            Keyboard.PushCommand("CmdQuit");
            return "{\"ok\":true,\"action\":\"quit\"}";
        }

        private static string Abandon()
        {
            Keyboard.PushCommand("CmdAbandon");
            return "{\"ok\":true,\"action\":\"abandon\"}";
        }

        private static string Look()
        {
            Keyboard.PushCommand("CmdLook");
            return "{\"ok\":true,\"action\":\"look\"}";
        }

        private static string ShowLabels()
        {
            Keyboard.PushCommand("CmdShowLabels");
            return "{\"ok\":true,\"action\":\"show_labels\"}";
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

        public static string DirectionToCardinalCommand(string direction)
        {
            switch (direction.ToLower())
            {
                case "up": case "n": case "north": return "CmdMoveN";
                case "down": case "s": case "south": return "CmdMoveS";
                case "left": case "w": case "west": return "CmdMoveW";
                case "right": case "e": case "east": return "CmdMoveE";
                default: return null;
            }
        }

        private static void Thread_Sleep(int ms)
        {
            System.Threading.Thread.Sleep(ms);
        }
    }
}
