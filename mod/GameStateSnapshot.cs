using System;
using System.Collections.Generic;
using System.Text;
using XRL;
using XRL.World;
using XRL.World.Parts;

namespace CoQMcpBridge
{
    public static class GameStateSnapshot
    {
        public static string BuildFullState(GameObject player)
        {
            if (player == null)
                return "{\"error\":\"no player\"}";

            var sb = new StringBuilder(8192);
            sb.Append("{");
            sb.Append("\"type\":\"state\",");
            sb.Append(Json.Str("protocol", Protocol.ProtocolVersion.ToString()));
            sb.Append(",");
            sb.Append(Json.Str("version", Protocol.Version));
            sb.Append(",");

            AppendPlayer(sb, player);
            sb.Append(",");
            AppendZone(sb, player);
            sb.Append(",");
            AppendCells(sb, player);
            sb.Append(",");
            AppendMessages(sb);
            sb.Append(",");
            AppendEffects(sb, player);
            sb.Append(",");
            AppendInventory(sb, player);
            sb.Append(",");
            AppendAbilities(sb, player);
            sb.Append(",");
            AppendTime(sb);
            sb.Append("}");

            return sb.ToString();
        }

        private static void AppendPlayer(StringBuilder sb, GameObject player)
        {
            sb.Append("\"player\":{");

            sb.Append(Json.Str("name", SafeGet(() => player.DisplayNameOnly)));
            sb.Append(",");
            sb.Append(Json.Num("hp", SafeGet(() => player.hitpoints, -1)));
            sb.Append(",");
            sb.Append(Json.Num("hpMax", SafeGet(() => player.baseHitpoints, -1)));
            sb.Append(",");
            sb.Append(Json.Num("level", SafeGet(() => player.GetStatValue("Level"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("xp", SafeGet(() => player.GetStatValue("XP"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("xpNext", SafeGet(() => player.GetStatValue("XPForNextLevel"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("qn", SafeGet(() => player.GetStatValue("Quickness"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("ms", SafeGet(() => player.GetStatValue("MoveSpeed"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("av", SafeGet(() => player.GetStatValue("AV"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("dv", SafeGet(() => player.GetStatValue("DV"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("ma", SafeGet(() => player.GetStatValue("MA"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("strength", SafeGet(() => player.GetStatValue("Strength"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("agility", SafeGet(() => player.GetStatValue("Agility"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("toughness", SafeGet(() => player.GetStatValue("Toughness"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("willpower", SafeGet(() => player.GetStatValue("Willpower"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("ego", SafeGet(() => player.GetStatValue("Ego"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("intelligence", SafeGet(() => player.GetStatValue("Intelligence"), 0)));

            var cell = player.CurrentCell;
            if (cell != null)
            {
                sb.Append(",");
                sb.Append(Json.Num("x", cell.X));
                sb.Append(",");
                sb.Append(Json.Num("y", cell.Y));
            }

            sb.Append(",");
            sb.Append(Json.Str("location", SafeGet(() => cell?.ParentZone?.DisplayName ?? "unknown")));

            sb.Append(",");
            sb.Append(Json.Num("hunger", SafeGet(() => GetHungerLevel(player), -1)));
            sb.Append(",");
            sb.Append(Json.Num("thirst", SafeGet(() => GetThirstLevel(player), -1)));
            sb.Append(",");
            sb.Append(Json.Num("temperature", SafeGet(() => player.pPhysics?.Temperature ?? 0, 0)));
            sb.Append(",");
            sb.Append(Json.Num("weight", SafeGet(() => player.GetStatValue("CarryingCapacity") > 0 ? (int)(player.GetCarriedWeight() * 100 / player.GetStatValue("CarryingCapacity")) : 0, 0)));

            sb.Append(",");
            sb.Append(Json.Bool("inCombat", SafeGet(() => IsInCombat(player), false)));

            sb.Append("}");
        }

        private static void AppendZone(StringBuilder sb, GameObject player)
        {
            sb.Append("\"zone\":{");
            var zone = player?.CurrentCell?.ParentZone;
            if (zone != null)
            {
                sb.Append(Json.Str("id", SafeGet(() => zone.ZoneID)));
                sb.Append(",");
                sb.Append(Json.Num("width", zone.Width));
                sb.Append(",");
                sb.Append(Json.Num("height", zone.Height));
                sb.Append(",");
                sb.Append(Json.Num("wx", zone.wX));
                sb.Append(",");
                sb.Append(Json.Num("wy", zone.wY));
                sb.Append(",");
                sb.Append(Json.Num("zx", zone.X));
                sb.Append(",");
                sb.Append(Json.Num("zy", zone.Y));
                sb.Append(",");
                sb.Append(Json.Num("z", zone.Z));
                sb.Append(",");
                sb.Append(Json.Str("name", SafeGet(() => zone.DisplayName)));
                sb.Append(",");
                sb.Append(Json.Bool("isWorldMap", zone.Z < 0));
            }
            else
            {
                sb.Append(Json.Str("id", ""));
            }
            sb.Append("}");
        }

        private static void AppendCells(StringBuilder sb, GameObject player)
        {
            sb.Append("\"cells\":[");
            var zone = player?.CurrentCell?.ParentZone;
            if (zone == null) { sb.Append("]"); return; }

            bool first = true;
            int px = player.CurrentCell.X;
            int py = player.CurrentCell.Y;

            for (int y = 0; y < zone.Height; y++)
            {
                for (int x = 0; x < zone.Width; x++)
                {
                    var cell = zone.GetCell(x, y);
                    if (cell == null) continue;

                    var objects = cell.GetObjects();
                    if (objects == null || objects.Count == 0) continue;

                    foreach (var obj in objects)
                    {
                        if (obj == null) continue;
                        if (obj == player) continue;

                        if (!first) sb.Append(",");
                        first = false;

                        sb.Append("{");
                        sb.Append(Json.Num("x", x));
                        sb.Append(",");
                        sb.Append(Json.Num("y", y));
                        sb.Append(",");
                        sb.Append(Json.Str("name", SafeGet(() => obj.DisplayNameOnly)));
                        sb.Append(",");
                        sb.Append(Json.Str("blueprint", SafeGet(() => obj.Blueprint)));
                        sb.Append(",");
                        sb.Append(Json.Bool("isCreature", SafeGet(() => obj.IsCreature, false)));
                        sb.Append(",");
                        sb.Append(Json.Bool("isHostile", SafeGet(() => IsHostileToPlayer(obj), false)));
                        sb.Append(",");
                        sb.Append(Json.Bool("isFriendly", SafeGet(() => IsFriendlyToPlayer(obj), false)));
                        sb.Append(",");
                        sb.Append(Json.Bool("isNeutral", SafeGet(() => IsNeutralToPlayer(obj), false)));
                        sb.Append(",");
                        sb.Append(Json.Bool("isItem", SafeGet(() => obj.HasPart("Item") || obj.IsTakeable(), false)));
                        sb.Append(",");
                        sb.Append(Json.Bool("isDoor", SafeGet(() => obj.HasPart("Door"), false)));
                        sb.Append(",");
                        sb.Append(Json.Bool("isContainer", SafeGet(() => obj.HasPart("Container"), false)));
                        sb.Append(",");
                        sb.Append(Json.Bool("blocksMovement", SafeGet(() => obj.IsWall() || (obj.pPhysics != null && obj.pPhysics.Solid), false)));
                        sb.Append(",");
                        sb.Append(Json.Num("distance", Math.Max(Math.Abs(x - px), Math.Abs(y - py))));

                        if (obj.IsCreature)
                        {
                            sb.Append(",");
                            sb.Append(Json.Num("hp", SafeGet(() => obj.hitpoints, -1)));
                            sb.Append(",");
                            sb.Append(Json.Num("hpMax", SafeGet(() => obj.baseHitpoints, -1)));
                            sb.Append(",");
                            sb.Append(Json.Num("level", SafeGet(() => obj.GetStatValue("Level"), 0)));
                            sb.Append(",");
                            sb.Append(Json.Str("faction", SafeGet(() => GetFactionName(obj))));
                        }

                        sb.Append("}");
                    }
                }
            }
            sb.Append("]");
        }

        private static void AppendMessages(StringBuilder sb)
        {
            sb.Append("\"messages\":[");
            try
            {
                var game = The.Game;
                var messages = game?.Player?.Messages;
                if (messages?.Messages != null)
                {
                    int count = messages.Messages.Count;
                    int start = Math.Max(0, count - 40);
                    bool first = true;
                    for (int i = start; i < count; i++)
                    {
                        var msg = messages.Messages[i];
                        if (msg == null) continue;
                        string text = msg.Text ?? "";
                        if (string.IsNullOrEmpty(text)) continue;

                        if (!first) sb.Append(",");
                        first = false;
                        sb.Append("\"").Append(Json.Escape(StripMarkup(text))).Append("\"");
                    }
                    sb.Append(",");
                    sb.Append(Json.Num("msgCount", count));
                }
            }
            catch { }
            sb.Append("]");
        }

        private static void AppendEffects(StringBuilder sb, GameObject player)
        {
            sb.Append("\"effects\":[");
            bool first = true;
            try
            {
                if (player.Effects != null)
                {
                    foreach (var effect in player.Effects)
                    {
                        if (effect == null) continue;
                        if (!first) sb.Append(",");
                        first = false;
                        sb.Append("{");
                        sb.Append(Json.Str("name", SafeGet(() => effect.GetDescription() ?? effect.ClassName)));
                        sb.Append(",");
                        sb.Append(Json.Num("duration", SafeGet(() => effect.Duration, -1)));
                        sb.Append("}");
                    }
                }
            }
            catch { }
            sb.Append("]");
        }

        private static void AppendInventory(StringBuilder sb, GameObject player)
        {
            sb.Append("\"inventory\":[");
            bool first = true;
            try
            {
                var body = player.Body;
                if (body != null)
                {
                    foreach (var part in body.GetParts())
                    {
                        if (part == null) continue;
                        var item = part.Equipped;
                        if (item != null)
                        {
                            if (!first) sb.Append(",");
                            first = false;
                            sb.Append("{");
                            sb.Append(Json.Str("name", SafeGet(() => item.DisplayNameOnly)));
                            sb.Append(",");
                            sb.Append(Json.Str("slot", SafeGet(() => part.Type ?? "unknown")));
                            sb.Append(",");
                            sb.Append(Json.Bool("equipped", true));
                            sb.Append("}");
                        }
                    }
                }

                var inventory = player.GetPart<Inventory>();
                if (inventory != null)
                {
                    foreach (var item in inventory.Objects)
                    {
                        if (item == null) continue;
                        if (!first) sb.Append(",");
                        first = false;
                        sb.Append("{");
                        sb.Append(Json.Str("name", SafeGet(() => item.DisplayNameOnly)));
                        sb.Append(",");
                        sb.Append(Json.Str("blueprint", SafeGet(() => item.Blueprint)));
                        sb.Append(",");
                        sb.Append(Json.Bool("equipped", false));
                        sb.Append("}");
                    }
                }
            }
            catch { }
            sb.Append("]");
        }

        private static void AppendAbilities(StringBuilder sb, GameObject player)
        {
            sb.Append("\"abilities\":[");
            bool first = true;
            try
            {
                var activated = player.GetPart<ActivatedAbilities>();
                if (activated != null && activated.AbilityList != null)
                {
                    foreach (var ability in activated.AbilityList)
                    {
                        if (ability == null) continue;
                        if (!first) sb.Append(",");
                        first = false;
                        sb.Append("{");
                        sb.Append(Json.Str("name", SafeGet(() => ability.DisplayName)));
                        sb.Append(",");
                        sb.Append(Json.Str("command", SafeGet(() => ability.Command)));
                        sb.Append(",");
                        sb.Append(Json.Str("hotkey", SafeGet(() => ability.Hotkey)));
                        sb.Append("}");
                    }
                }
            }
            catch { }
            sb.Append("]");
        }

        private static void AppendTime(StringBuilder sb)
        {
            sb.Append("\"time\":{");
            try
            {
                var calendar = The.Game?.Calendar;
                if (calendar != null)
                {
                    sb.Append(Json.Num("segment", SafeGet(() => calendar.CurrentSegment, 0)));
                    sb.Append(",");
                    sb.Append(Json.Num("segmentsPerDay", 12000));
                    sb.Append(",");
                    sb.Append(Json.Bool("isDay", SafeGet(() => calendar.IsDay(), true)));
                    sb.Append(",");
                    sb.Append(Json.Num("day", SafeGet(() => calendar.GetCurrentDay(), 0)));
                    sb.Append(",");
                    sb.Append(Json.Num("hour", SafeGet(() => calendar.GetCurrentHour(), 0)));
                }
            }
            catch { }
            sb.Append("}");
        }

        private static string StripMarkup(string text)
        {
            if (string.IsNullOrEmpty(text)) return text;
            var sb = new StringBuilder(text.Length);
            bool inTag = false;
            foreach (char c in text)
            {
                if (c == '{') { inTag = true; continue; }
                if (c == '}') { inTag = false; continue; }
                if (!inTag) sb.Append(c);
            }
            return sb.ToString();
        }

        private static int GetHungerLevel(GameObject player)
        {
            try
            {
                var stomach = player.GetPart<Stomach>();
                if (stomach != null)
                {
                    return (int)stomach.HungerLevel;
                }
            }
            catch { }
            return -1;
        }

        private static int GetThirstLevel(GameObject player)
        {
            try
            {
                var stomach = player.GetPart<Stomach>();
                if (stomach != null)
                {
                    return (int)stomach.ThirstLevel;
                }
            }
            catch { }
            return -1;
        }

        private static bool IsInCombat(GameObject player)
        {
            try
            {
                var zone = player?.CurrentCell?.ParentZone;
                if (zone == null) return false;
                foreach (var obj in zone.GetObjects())
                {
                    if (obj != null && obj.IsCreature && obj != player && IsHostileToPlayer(obj))
                    {
                        var cell = player.CurrentCell;
                        if (cell != null)
                        {
                            var objCell = obj.CurrentCell;
                            if (objCell != null)
                            {
                                int dist = Math.Max(Math.Abs(cell.X - objCell.X), Math.Abs(cell.Y - objCell.Y));
                                if (dist <= 5) return true;
                            }
                        }
                    }
                }
            }
            catch { }
            return false;
        }

        private static bool IsHostileToPlayer(GameObject obj)
        {
            try
            {
                if (!obj.IsCreature) return false;
                var brain = obj.GetPart<Brain>();
                if (brain == null) return false;
                return brain.IsHostileToPlayer();
            }
            catch { }
            return false;
        }

        private static bool IsFriendlyToPlayer(GameObject obj)
        {
            try
            {
                if (!obj.IsCreature) return false;
                var brain = obj.GetPart<Brain>();
                if (brain == null) return false;
                return brain.IsFriendlyToPlayer();
            }
            catch { }
            return false;
        }

        private static bool IsNeutralToPlayer(GameObject obj)
        {
            try
            {
                if (!obj.IsCreature) return false;
                var brain = obj.GetPart<Brain>();
                if (brain == null) return false;
                return brain.IsNeutralToPlayer();
            }
            catch { }
            return false;
        }

        private static string GetFactionName(GameObject obj)
        {
            try
            {
                var faction = obj.GetPart<Factions>()?.GetFaction();
                return faction?.DisplayName ?? "";
            }
            catch { }
            return "";
        }

        private static T SafeGet<T>(Func<T> getter, T fallback = default(T))
        {
            try { return getter(); }
            catch { return fallback; }
        }
    }
}
