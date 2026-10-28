using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Text;
using Qud.UI;
using XRL;
using XRL.UI;
using XRL.World;

namespace CoQMcpBridge
{
    /// <summary>
    /// Drives the open modern trade screen (view "ModernTrade") the way its
    /// UI does: read both sides' item lists, set how many of an entry are
    /// selected, and press "Offer". The offer runs the game's own trade logic,
    /// so its popups ("pony up N drams... Agreed?", "Trade complete!") appear
    /// as normal popups. Side 0 is the trader, side 1 the player.
    /// All calls run on the Unity main thread (the screen's own thread).
    /// </summary>
    public static class TradeBridge
    {
        private const BindingFlags All =
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;

        private static object Get(object o, string name) => PickerBridge.Get(o, name);

        private static TradeScreen FindOpen()
        {
            foreach (var s in UnityEngine.Object.FindObjectsOfType<TradeScreen>())
            {
                if (s == null || !s.gameObject.activeInHierarchy) continue;
                var task = Get(Get(s, "menucomplete"), "Task") as System.Threading.Tasks.Task;
                if (task == null || task.IsCompleted) continue;
                return s;
            }
            return null;
        }

        private static IList Entries(TradeScreen s, int side) =>
            (Get(s, "tradeEntries") as IList)?[side] as IList;

        private static int[] Selected(TradeScreen s, int side) =>
            (Get(s, "NumberSelected") as IList)?[side] as int[];

        // Drams per item as the trade screen shows it (trader's markup applied).
        private static string Price(GameObject go, bool traderSide)
        {
            try
            {
                var value = typeof(TradeUI).GetMethod("GetValue", All).Invoke(null, new object[] { go, traderSide });
                return Convert.ToDouble(value).ToString("0.##");
            }
            catch { return "?"; }
        }

        private static string Run(Func<string> body)
        {
            string result = null;
            bool completed = BridgeMainThread.EnqueueAndWait(() =>
            {
                try { result = body(); }
                catch (Exception e)
                {
                    var inner = (e as TargetInvocationException)?.InnerException ?? e;
                    result = "{\"error\":\"" + Json.Escape(inner.GetType().Name + ": " + inner.Message) + "\"}";
                }
            }, timeoutMs: 5000);
            if (!completed) return "{\"error\":\"timeout waiting for main thread\"}";
            return result ?? "{\"error\":\"no result\"}";
        }

        private const string NotOpen = "{\"error\":\"the trade screen is not open — interact with a merchant and pick Trade first\"}";

        public static string List() => Run(() =>
        {
            var s = FindOpen();
            if (s == null) return NotOpen;
            var trader = Get(s, "Trader") as GameObject;
            var sb = new StringBuilder(4096);
            sb.Append("{\"ok\":true,");
            sb.Append(Json.Str("trader", PopupBridge.Clean(trader?.DisplayNameOnly)));
            sb.Append(",");
            sb.Append(Json.Num("traderDrams", trader?.GetFreeDrams("water") ?? 0));
            sb.Append(",");
            sb.Append(Json.Num("playerDrams", The.Player?.GetFreeDrams("water") ?? 0));
            sb.Append(",");
            sb.Append(Json.Str("balance", Balance(s)));
            sb.Append(",\"sides\":[");
            for (int side = 0; side < 2; side++)
            {
                if (side > 0) sb.Append(",");
                sb.Append("[");
                var entries = Entries(s, side);
                var selected = Selected(s, side);
                bool first = true;
                for (int i = 0; entries != null && i < entries.Count; i++)
                {
                    var go = Get(entries[i], "GO") as GameObject;
                    if (go == null) continue;  // category header
                    if (!first) sb.Append(",");
                    first = false;
                    sb.Append("{");
                    sb.Append(Json.Num("index", i));
                    sb.Append(",");
                    sb.Append(Json.Str("name", PopupBridge.Clean(go.DisplayName)));
                    sb.Append(",");
                    sb.Append(Json.Num("count", go.Count));
                    sb.Append(",");
                    sb.Append(Json.Str("price", Price(go, side == 0)));
                    sb.Append(",");
                    sb.Append(Json.Num("selected", selected != null && i < selected.Length ? selected[i] : 0));
                    sb.Append("}");
                }
                sb.Append("]");
            }
            sb.Append("]}");
            return sb.ToString();
        });

        // What the screen's totals bar says: drams the player pays (+) or gets (-).
        private static string Balance(TradeScreen s)
        {
            try
            {
                PickerBridge.Call(s, "UpdateTotals");
                var totals = Get(s, "Totals") as IList;
                if (totals == null || totals.Count < 2) return "";
                double buy = Convert.ToDouble(totals[0]), sell = Convert.ToDouble(totals[1]);
                return "you buy " + Math.Round(buy, 2) + " drams worth, sell " + Math.Round(sell, 2) +
                       " drams worth (before rounding)";
            }
            catch (Exception e) { return "unknown: " + e.Message; }
        }

        public static string Select(int side, int index, int count) => Run(() =>
        {
            var s = FindOpen();
            if (s == null) return NotOpen;
            if (side != 0 && side != 1) return "{\"error\":\"side must be 0 (trader's goods) or 1 (yours)\"}";
            var entries = Entries(s, side);
            var selected = Selected(s, side);
            if (entries == null || selected == null || index < 0 || index >= entries.Count || index >= selected.Length)
                return "{\"error\":\"no entry " + index + " on side " + side + " — use trade_list\"}";
            var go = Get(entries[index], "GO") as GameObject;
            if (go == null) return "{\"error\":\"entry " + index + " is a category header\"}";
            int n = Math.Max(0, Math.Min(count < 0 ? go.Count : count, go.Count));
            selected[index] = n;
            PickerBridge.Call(s, "UpdateTotals");
            PickerBridge.Call(s, "UpdateViewFromData");
            return "{\"ok\":true," + Json.Str("item", PopupBridge.Clean(go.DisplayName)) + "," +
                   Json.Num("selected", n) + "," + Json.Str("balance", Balance(s)) + "}";
        });

        public static string Offer() => Run(() =>
        {
            var s = FindOpen();
            if (s == null) return NotOpen;
            var option = typeof(TradeScreen).GetField("OFFER_TRADE", All)?.GetValue(null);
            if (option == null) return "{\"error\":\"OFFER_TRADE option not found\"}";
            // Async in the game: it shows the confirmation / result popups.
            typeof(TradeScreen).GetMethod("HandleMenuOption", All).Invoke(s, new[] { option });
            return "{\"ok\":true,\"action\":\"trade_offer\"}";
        });
    }
}
