using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using XRL;
using XRL.World;
using XRL.World.Skills;

namespace CoQMcpBridge
{
    /// <summary>
    /// Skill / power purchases and attribute points — what the Skills screen
    /// and the level-up attribute prompt do, without their UI.
    /// Purchases run on the game thread, like the UI's.
    /// </summary>
    public static class SkillActions
    {
        private static readonly string[] Attributes =
            { "Strength", "Agility", "Toughness", "Intelligence", "Willpower", "Ego" };

        private static IEnumerable Values(object collection) =>
            collection is IDictionary d ? (IEnumerable)d.Values : collection as IEnumerable ?? new object[0];

        private static IEnumerable<SkillEntry> Skills()
        {
            foreach (var o in Values(SkillFactory.Factory.SkillList))
                if (o is SkillEntry s) yield return s;
        }

        private static IEnumerable<PowerEntry> Powers(SkillEntry skill)
        {
            foreach (var o in Values(skill.Powers))
                if (o is PowerEntry p) yield return p;
        }

        private static bool Hidden(IPartEntry e) => (e.Flags & IPartEntry.FLAG_HIDDEN) != 0;

        private static bool Owned(GameObject player, IPartEntry e) => player.HasSkill(e.Class) || player.HasPart(e.Class);

        private static bool CanLearn(GameObject player, SkillEntry skill, PowerEntry power, out string why)
        {
            IBaseSkillEntry e = (IBaseSkillEntry)power ?? skill;
            why = null;
            if (Owned(player, e)) why = "already known";
            else if (power == null && skill.Initiatory) why = "requires initiation";
            else if (power != null && power.IsSkillInitiatory) why = "requires initiation";
            else if (power != null && !Owned(player, skill)) why = "learn the skill " + skill.Name + " first";
            else if (player.Stat("SP") < e.Cost) why = "costs " + e.Cost + " SP, you have " + player.Stat("SP");
            else if (!e.MeetsRequirements(player, false)) why = "requirements not met";
            else if (power != null && !power.MeetsAttributeMinimum(player, false)) why = "attribute too low";
            return why == null;
        }

        public static string List(GameObject player, bool all)
        {
            if (player == null) return "{\"error\":\"not in game\"}";
            var sb = new StringBuilder(8192);
            sb.Append("{\"ok\":true,\"action\":\"list_skills\",");
            sb.Append(Json.Num("sp", player.Stat("SP"))).Append(",");
            sb.Append(Json.Num("ap", player.Stat("AP"))).Append(",\"skills\":[");
            bool firstSkill = true;
            foreach (var skill in Skills())
            {
                if (Hidden(skill)) continue;
                bool hasSkill = Owned(player, skill);
                var powers = new List<string>();
                foreach (var power in Powers(skill))
                {
                    if (Hidden(power)) continue;
                    bool owned = Owned(player, power);
                    bool ok = CanLearn(player, skill, power, out string why);
                    if (!all && !owned && !ok && !hasSkill) continue;
                    powers.Add("{" + Json.Str("name", power.Name) + "," + Json.Num("cost", power.Cost) + "," +
                               Json.Bool("owned", owned) + "," + Json.Bool("canLearn", ok) +
                               (why != null && !owned ? "," + Json.Str("why", why) : "") + "}");
                }
                bool skillOk = CanLearn(player, skill, null, out string skillWhy);
                if (!all && !hasSkill && !skillOk) continue;
                if (!firstSkill) sb.Append(",");
                firstSkill = false;
                sb.Append("{").Append(Json.Str("name", skill.Name)).Append(",");
                sb.Append(Json.Num("cost", skill.Cost)).Append(",");
                sb.Append(Json.Bool("owned", hasSkill)).Append(",");
                sb.Append(Json.Bool("canLearn", skillOk));
                if (skillWhy != null && !hasSkill) sb.Append(",").Append(Json.Str("why", skillWhy));
                sb.Append(",\"powers\":[").Append(string.Join(",", powers)).Append("]}");
            }
            sb.Append("]}");
            return sb.ToString();
        }

        private static bool Find(string name, out SkillEntry skill, out PowerEntry power)
        {
            string n = (name ?? "").Trim().ToLowerInvariant();
            skill = null;
            power = null;
            foreach (var s in Skills())
            {
                if (Hidden(s)) continue;
                if ((s.Name ?? "").ToLowerInvariant() == n || (s.Class ?? "").ToLowerInvariant() == n)
                {
                    skill = s;
                    return true;
                }
                foreach (var p in Powers(s))
                {
                    if (Hidden(p)) continue;
                    if ((p.Name ?? "").ToLowerInvariant() == n || (p.Class ?? "").ToLowerInvariant() == n)
                    {
                        skill = s;
                        power = p;
                        return true;
                    }
                }
            }
            return false;
        }

        public static string Learn(GameObject player, string name)
        {
            if (player == null) return "{\"error\":\"not in game\"}";
            if (!Find(name, out var skill, out var power))
                return "{\"error\":\"no skill or power named '" + Json.Escape(name) + "' (use list_skills)\"}";
            if (!CanLearn(player, skill, power, out string why))
                return "{\"error\":\"cannot learn " + Json.Escape((power?.Name ?? skill.Name) + ": " + why) + "\"}";

            IBaseSkillEntry e = (IBaseSkillEntry)power ?? skill;
            string error = null;
            var done = new System.Threading.ManualResetEventSlim(false);
            GameManager.Instance.gameQueue.queueTask(() =>
            {
                try
                {
                    var part = player.GetPart<XRL.World.Parts.Skills>();
                    if (part == null) { error = "player has no Skills part"; return; }
                    // Pay first: AddSkill may show "you gained an ability" and
                    // block this thread until the popup is answered.
                    player.GetStat("SP").Penalty += e.Cost;
                    part.AddSkill(e.Class);
                }
                catch (Exception ex)
                {
                    error = ex.GetType().Name + ": " + ex.Message;
                    Console.WriteLine("[mcp] learn_skill error: " + ex);
                }
                finally { done.Set(); }
            });
            bool finished = done.Wait(3000);
            if (error != null) return "{\"error\":\"" + Json.Escape(error) + "\"}";
            return "{\"ok\":true,\"action\":\"learn_skill\"," + Json.Bool("popup", !finished) + "," + Json.Str("learned", e.Name) + "," +
                   Json.Num("cost", e.Cost) + "," + Json.Num("spLeft", player.Stat("SP")) + "}";
        }

        public static string RaiseAttribute(GameObject player, string attribute)
        {
            if (player == null) return "{\"error\":\"not in game\"}";
            string attr = null;
            foreach (var a in Attributes)
                if (a.StartsWith((attribute ?? "").Trim(), StringComparison.OrdinalIgnoreCase) && (attribute ?? "").Trim().Length >= 3)
                    attr = a;
            if (attr == null)
                return "{\"error\":\"attribute must be one of " + string.Join(", ", Attributes) + "\"}";
            if (player.Stat("AP") < 1)
                return "{\"error\":\"no attribute points to spend\"}";
            string error = null;
            var done = new System.Threading.ManualResetEventSlim(false);
            GameManager.Instance.gameQueue.queueTask(() =>
            {
                try
                {
                    player.GetStat(attr).BaseValue += 1;
                    player.GetStat("AP").Penalty += 1;
                }
                catch (Exception ex) { error = ex.GetType().Name + ": " + ex.Message; }
                finally { done.Set(); }
            });
            if (!done.Wait(3000)) return "{\"error\":\"raise_attribute timed out\"}";
            if (error != null) return "{\"error\":\"" + Json.Escape(error) + "\"}";
            return "{\"ok\":true,\"action\":\"raise_attribute\"," + Json.Str("attribute", attr) + "," +
                   Json.Num("value", player.Stat(attr)) + "," + Json.Num("apLeft", player.Stat("AP")) + "}";
        }
    }
}
