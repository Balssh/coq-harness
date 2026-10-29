using System;
using System.Collections.Generic;
using System.Linq;
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
            {
                var sb0 = new StringBuilder(512);
                sb0.Append("{\"type\":\"state\",");
                sb0.Append(Json.Str("protocol", Protocol.ProtocolVersion.ToString()));
                sb0.Append(",");
                sb0.Append(Json.Str("version", Protocol.Version));
                sb0.Append(",");
                sb0.Append(Json.Str("screen", SafeGet(() => GameManager.Instance?.CurrentGameView ?? "")));
                sb0.Append(",");
                sb0.Append(Json.Bool("inGame", false));
                sb0.Append(",");
                sb0.Append(Json.Bool("isDead", false));
                sb0.Append(",");
                sb0.Append(Json.Bool("inChargen", IsInChargen()));
                sb0.Append(",");
                sb0.Append(Json.Bool("inMainMenu", IsInMainMenu()));
                sb0.Append(",");
                sb0.Append(Json.Str("viewStack", GetViewStack()));
                sb0.Append(",");
                AppendPopup(sb0);
                sb0.Append("}");
                return sb0.ToString();
            }

            var sb = new StringBuilder(8192);
            sb.Append("{");
            sb.Append("\"type\":\"state\",");
            sb.Append(Json.Str("protocol", Protocol.ProtocolVersion.ToString()));
            sb.Append(",");
            sb.Append(Json.Str("version", Protocol.Version));
            sb.Append(",");
            sb.Append(Json.Str("screen", SafeGet(() => GameManager.Instance?.CurrentGameView ?? "")));
            sb.Append(",");
            sb.Append(Json.Bool("inGame", SafeGet(() => The.Game?.Player?.Body?.CurrentCell != null, false)));
            sb.Append(",");
            sb.Append(Json.Bool("isDead", SafeGet(() => player.hitpoints <= 0, false)));
            sb.Append(",");
            sb.Append(Json.Bool("inChargen", IsInChargen()));
            sb.Append(",");
            sb.Append(Json.Bool("inMainMenu", IsInMainMenu()));
            sb.Append(",");
            sb.Append(Json.Str("viewStack", GetViewStack()));
            sb.Append(",");
            AppendPopup(sb);
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
            AppendQuests(sb);
            sb.Append(",");
            AppendTime(sb);
            sb.Append("}");

            return sb.ToString();
        }

        // Open modern-UI popup (dialog, prompt, conversation) or null. Snapshot
        // is produced on the main thread by PopupBridge; safe to read here.
        private static void AppendPopup(StringBuilder sb)
        {
            sb.Append("\"popup\":");
            sb.Append(PopupBridge.SnapshotJson ?? "null");
        }

        private static void AppendPlayer(StringBuilder sb, GameObject player)
        {
            sb.Append("\"player\":{");

            // Base name: DisplayNameOnly adds states like "bloody".
            sb.Append(Json.Str("name", SafeGet(() => PopupBridge.Clean(player.BaseDisplayName))));
            sb.Append(",");
            sb.Append(Json.Num("hp", SafeGet(() => player.hitpoints, -1)));
            sb.Append(",");
            sb.Append(Json.Num("hpMax", SafeGet(() => player.baseHitpoints, -1)));
            sb.Append(",");
            sb.Append(Json.Num("level", SafeGet(() => player.GetStatValue("Level"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("xp", SafeGet(() => player.GetStatValue("XP"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("xpNext", SafeGet(() => XRL.World.Parts.Leveler.GetXPForLevel(player.GetStatValue("Level") + 1), 0)));
            sb.Append(",");
            sb.Append(Json.Num("qn", SafeGet(() => player.GetStatValue("Quickness"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("ms", SafeGet(() => player.GetStatValue("MoveSpeed"), 0)));
            sb.Append(",");
            sb.Append(Json.Num("av", SafeGet(() => XRL.Rules.Stats.GetCombatAV(player), 0)));
            sb.Append(",");
            sb.Append(Json.Num("dv", SafeGet(() => XRL.Rules.Stats.GetCombatDV(player), 0)));
            sb.Append(",");
            sb.Append(Json.Num("ma", SafeGet(() => XRL.Rules.Stats.GetCombatMA(player), 0)));
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
            sb.Append(Json.Str("hunger", SafeGet(() => GetHungerString(player), "unknown")));
            sb.Append(",");
            sb.Append(Json.Str("thirst", SafeGet(() => GetThirstString(player), "unknown")));
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
                sb.Append(",\"explored\":[");
                for (int y = 0; y < zone.Height; y++)
                {
                    var row = new StringBuilder(zone.Width);
                    for (int x = 0; x < zone.Width; x++)
                        row.Append(SafeGet(() => zone.GetCell(x, y)?.IsExplored() ?? false, true) ? '1' : '0');
                    if (y > 0) sb.Append(",");
                    sb.Append("\"").Append(row).Append("\"");
                }
                sb.Append("]");
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
            bool worldMap = SafeGet(() => zone.IsWorldMap(), false);

            for (int y = 0; y < zone.Height; y++)
            {
                for (int x = 0; x < zone.Width; x++)
                {
                    var cell = zone.GetCell(x, y);
                    if (cell == null) continue;

                    foreach (var obj in cell.GetObjects())
                    {
                        if (obj == null) continue;
                        if (obj == player) continue;
                        // Only what the player knows: creatures in sight, and
                        // terrain/items in explored cells.
                        if (!worldMap && !SafeGet(() => obj.IsCreature ? CanSee(player, obj, cell) : cell.IsExplored(), true)) continue;

                        if (!first) sb.Append(",");
                        first = false;

                        sb.Append("{");
                        sb.Append(Json.Num("x", x));
                        sb.Append(",");
                        sb.Append(Json.Num("y", y));
                        sb.Append(",");
                        sb.Append(Json.Str("name", SafeGet(() => PopupBridge.Clean(obj.DisplayNameOnly))));
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
                            sb.Append(",");
                            sb.Append(Json.Str("baseName", SafeGet(() => BaseName(obj), "")));
                            if (obj != player)
                            {
                                // The game's own threat rating ("Tough", "Impossible"), as on look.
                                sb.Append(",");
                                sb.Append(Json.Str("difficulty", SafeGet(() => PopupBridge.Clean(
                                    XRL.World.Capabilities.DifficultyEvaluation.GetDifficultyDescription(obj, player, null, false) ?? ""), "")));
                            }
                        }

                        sb.Append("}");
                    }
                }
            }
            sb.Append("]");
        }

        // The creature's own name without the words the game adds for its state ("bloody",
        // "wounded", "wet"...): the Render part's DisplayName. Read by reflection, since its
        // member has been both a field and a property across game versions.
        private static string BaseName(GameObject obj)
        {
            var render = obj.GetPart("Render");
            if (render == null) return "";
            var t = render.GetType();
            object v = t.GetProperty("DisplayName")?.GetValue(render, null) ?? t.GetField("DisplayName")?.GetValue(render);
            return PopupBridge.Clean(v as string ?? "");
        }

        // The zone's visibility map is filled by the renderer and isn't current
        // when the snapshot runs; line of sight to a lit cell is what the
        // player sees (torches light the cells around them underground).
        private static bool CanSee(GameObject player, GameObject obj, Cell cell) =>
            obj.IsVisible() || cell.IsVisible() || (cell.IsLit() && player.HasLOSTo(obj));

        private static void AppendMessages(StringBuilder sb)
        {
            var msgs = new List<string>();
            try
            {
                var messages = The.Game?.Player?.Messages;
                if (messages != null)
                {
                    foreach (var msg in messages.Messages)
                    {
                        if (string.IsNullOrEmpty(msg)) continue;
                        msgs.Add(PopupBridge.Clean(msg));
                    }
                }
            }
            catch { }

            sb.Append("\"messages\":[");
            int start = Math.Max(0, msgs.Count - 40);
            for (int i = start; i < msgs.Count; i++)
            {
                if (i > start) sb.Append(",");
                sb.Append("\"").Append(Json.Escape(msgs[i])).Append("\"");
            }
            sb.Append("],");
            sb.Append(Json.Num("msgCount", msgs.Count));
        }

        private static void AppendEffects(StringBuilder sb, GameObject player)
        {
            sb.Append("\"effects\":[");
            bool first = true;
            try
            {
                if (player.Effects != null)
                {
                    foreach (var effect in player.Effects.GetArray())
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

        // Active (unfinished) quests with their visible steps, as in the quest log.
        private static void AppendQuests(StringBuilder sb)
        {
            sb.Append("\"quests\":[");
            bool first = true;
            try
            {
                foreach (var quest in MapValues(The.Game?.Quests))
                {
                    if (!(quest is XRL.World.Quest q) || q.Finished) continue;
                    if (!first) sb.Append(",");
                    first = false;
                    sb.Append("{");
                    sb.Append(Json.Str("name", PopupBridge.Clean(q.DisplayName ?? q.Name ?? q.ID)));
                    sb.Append(",");
                    sb.Append(Json.Str("giver", PopupBridge.Clean(q.QuestGiverName ?? "")));
                    sb.Append(",");
                    sb.Append(Json.Str("giverLocation", PopupBridge.Clean(q.QuestGiverLocationName ?? "")));
                    sb.Append(",\"steps\":[");
                    bool firstStep = true;
                    var steps = q.StepsByID?.Values.Where(st => st != null && !st.Hidden).OrderBy(st => st.Ordinal);
                    foreach (var st in steps ?? Enumerable.Empty<XRL.World.QuestStep>())
                    {
                        if (!firstStep) sb.Append(",");
                        firstStep = false;
                        sb.Append("{");
                        sb.Append(Json.Str("name", PopupBridge.Clean(st.Name ?? st.ID)));
                        sb.Append(",");
                        sb.Append(Json.Str("text", PopupBridge.Clean(st.Text ?? "")));
                        sb.Append(",");
                        sb.Append(Json.Bool("finished", st.Finished));
                        sb.Append(",");
                        sb.Append(Json.Bool("failed", st.Failed));
                        sb.Append(",");
                        sb.Append(Json.Bool("optional", st.Optional));
                        sb.Append("}");
                    }
                    sb.Append("]}");
                }
            }
            catch { }
            sb.Append("]");
        }

        // StringMap<T> values without depending on its exact API.
        private static System.Collections.Generic.IEnumerable<object> MapValues(object map)
        {
            if (!(map is System.Collections.IEnumerable items)) yield break;
            foreach (var item in items)
            {
                if (item == null) continue;
                var value = item.GetType().GetProperty("Value")?.GetValue(item, null);
                yield return value ?? item;
            }
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
                            sb.Append(Json.Str("name", SafeGet(() => PopupBridge.Clean(item.DisplayName))));
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
                        sb.Append(Json.Str("name", SafeGet(() => PopupBridge.Clean(item.DisplayName))));
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
                if (activated != null)
                {
                    foreach (var ability in activated.GetAbilityListOrderedByPreference())
                    {
                        if (ability == null) continue;
                        if (!first) sb.Append(",");
                        first = false;
                        sb.Append("{");
                        sb.Append(Json.Str("name", SafeGet(() => ability.DisplayName)));
                        sb.Append(",");
                        sb.Append(Json.Str("command", SafeGet(() => ability.Command)));
                        sb.Append(",");
                        sb.Append(Json.Str("hotkey", SafeGet(() => ability.DisplayForHotkey)));
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
                sb.Append(Json.Num("segment", Calendar.CurrentDaySegment));
                sb.Append(",");
                sb.Append(Json.Num("segmentsPerDay", Calendar.TurnsPerDay));
                sb.Append(",");
                sb.Append(Json.Bool("isDay", Calendar.IsDay()));
            }
            catch { }
            sb.Append("}");
        }

        private static string GetHungerString(GameObject player)
        {
            try
            {
                var stomach = player.GetPart<Stomach>();
                if (stomach != null)
                {
                    return HungerLevelToString(stomach.HungerLevel);
                }
            }
            catch { }
            return "unknown";
        }

        private static string GetThirstString(GameObject player)
        {
            try
            {
                var stomach = player.GetPart<Stomach>();
                if (stomach != null)
                {
                    return stomach.WaterStatus() ?? "unknown";
                }
            }
            catch { }
            return "unknown";
        }

        private static string HungerLevelToString(int level)
        {
            switch (level)
            {
                case 0: return "satiated";
                case 1: return "peckish";
                case 2: return "hungry";
                case 3: return "very hungry";
                case 4: return "starving";
                default: return "unknown";
            }
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

        internal static GameObject Player()
        {
            try { return The.Game?.Player?.Body; }
            catch { return null; }
        }

        private static bool IsInChargen()
        {
            try
            {
                string view = GameManager.Instance?.CurrentGameView ?? "";
                return view == "EmbarkBuilder" || view == "Chargen";
            }
            catch { return false; }
        }

        private static bool IsInMainMenu()
        {
            try
            {
                string view = GameManager.Instance?.CurrentGameView ?? "";
                return view == "MainMenu";
            }
            catch { return false; }
        }

        private static string GetViewStack()
        {
            try
            {
                var gm = GameManager.Instance;
                if (gm == null) return "";
                var stack = gm.GetGameViewStackCopy();
                if (stack == null) return "";
                return string.Join(">", stack.Select(v => v?.ToString() ?? "?"));
            }
            catch { return ""; }
        }

        private static bool IsHostileToPlayer(GameObject obj)
        {
            try
            {
                if (!obj.IsCreature) return false;
                var brain = obj.GetPart<Brain>();
                if (brain == null) return false;
                var player = Player();
                if (player == null) return false;
                return brain.IsHostileTowards(player);
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
                var player = Player();
                if (player == null) return false;
                return brain.GetFeelingLevel(player) == Brain.FeelingLevel.Allied;
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
                var player = Player();
                if (player == null) return false;
                return brain.IsNeutralTowards(player);
            }
            catch { }
            return false;
        }

        private static string GetFactionName(GameObject obj)
        {
            try
            {
                var brain = obj.GetPart<Brain>();
                if (brain == null) return "";
                return brain.GetPrimaryFactionName() ?? "";
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
