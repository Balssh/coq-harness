using System;
using System.Threading;
using XRL;
using XRL.Core;
using XRL.World;

namespace CoQMcpBridge
{
    public static class Bridge
    {
        private const int PublishThrottleMs = 66;

        private static McpServer _server;
        private static readonly object _gate = new object();
        private static long _lastPublishTicks;

        public static McpServer Server
        {
            get
            {
                if (_server == null)
                {
                    lock (_gate)
                    {
                        if (_server == null)
                        {
                            var s = new McpServer();
                            s.Log = m => System.Console.WriteLine("[mcp] " + m);
                            s.OnPayload = OnPayload;
                            s.Start();
                            _server = s;
                            StartFocusKeeper();
                            StartPump();
                        }
                    }
                }
                return _server;
            }
        }

        public static void EnsureStarted()
        {
            var _ = Server;
            BridgeMainThread.EnsureCreated();
        }

        private static void OnPayload(string json)
        {
            _server?.Incoming.Enqueue(json);
        }

        public static void Tick(GameObject player)
        {
            var server = _server;
            if (server == null) return;

            DrainCommands(player);

            if (server.ClientCount == 0) return;

            string state = GameStateSnapshot.BuildFullState(player);
            PublishToClients(state);
        }

        public static void TickRender(GameObject player)
        {
            var server = _server;
            if (server == null) return;

            DrainCommands(player);

            if (server.ClientCount == 0) return;

            long now = DateTime.UtcNow.Ticks;
            if (now - Interlocked.Read(ref _lastPublishTicks) < PublishThrottleMs * TimeSpan.TicksPerMillisecond)
                return;
            Interlocked.Exchange(ref _lastPublishTicks, now);

            string state = GameStateSnapshot.BuildFullState(player);
            PublishToClients(state);
        }

        public static void TickAction(GameObject player)
        {
            var server = _server;
            if (server == null) return;

            DrainCommands(player);
        }

        private static void DrainCommands(GameObject player)
        {
            var server = _server;
            if (server == null) return;

            // When called from the pump thread, player is null — look up the
            // real player so get_state returns full data even during modal states.
            if (player == null)
                player = GameStateSnapshot.Player();

            while (server.Incoming.TryDequeue(out string json))
            {
                try
                {
                    var cmd = MiniJson.Parse(json) as MiniJson.Obj;
                    if (cmd == null) continue;

                    string type = cmd.GetStr("type", "");

                    if (type == "command")
                    {
                        string cmdId = cmd.GetStr("cmdId", "");
                        string result = GameActions.ExecuteCommand(player, json);
                        string resultWithId = InjectCmdId(result, cmdId);
                        PublishToClients("{\"type\":\"command_result\",\"result\":" + resultWithId + "}");
                    }
                    else if (type == "get_state")
                    {
                        string state = GameStateSnapshot.BuildFullState(player);
                        PublishToClients(state);
                    }
                }
                catch (Exception e)
                {
                    PublishToClients("{\"type\":\"error\",\"message\":\"" + Json.Escape(e.Message) + "\"}");
                }
            }
        }

        private static string InjectCmdId(string resultJson, string cmdId)
        {
            if (string.IsNullOrEmpty(cmdId)) return resultJson;
            if (!resultJson.StartsWith("{")) return resultJson;
            return resultJson.Substring(0, 1) + Json.Str("cmdId", cmdId) + "," + resultJson.Substring(1);
        }

        private static void PublishToClients(string json)
        {
            _server?.Broadcast(json);
        }

        private static Thread _focusKeeper;

        private static void StartFocusKeeper()
        {
            if (_focusKeeper != null) return;
            _focusKeeper = new Thread(() =>
            {
                while (true)
                {
                    try
                    {
                        if (_server != null && _server.ClientCount > 0)
                        {
                            XRLCore.bThreadFocus = true;
                            GameManager.focused = true;
                        }
                        Thread.Sleep(50);
                    }
                    catch { Thread.Sleep(200); }
                }
            }) { IsBackground = true, Name = "McpFocusKeeper" };
            _focusKeeper.Start();
        }

        // Drains MCP messages on a background thread so commands are processed
        // even when the game is in a modal state (look mode, menus, chargen)
        // where the BridgePart events don't fire. Thread-safe: both this and
        // the BridgePart tick use ConcurrentQueue.TryDequeue.
        private static Thread _pump;

        private static void StartPump()
        {
            if (_pump != null) return;
            _pump = new Thread(() =>
            {
                while (true)
                {
                    try
                    {
                        var server = _server;
                        if (server == null) { Thread.Sleep(200); continue; }

                        DrainCommands(null);
                        Thread.Sleep(15);
                    }
                    catch { Thread.Sleep(200); }
                }
            }) { IsBackground = true, Name = "McpPump" };
            _pump.Start();
        }
    }

    // Invoked by the game during startup (end of ModManager.Init and again in
    // XRLCore.LoadEverything), before the main menu — so the MCP server is up
    // for character creation as well as for play.
    [HasModSensitiveStaticCache]
    public class BridgeBootstrap
    {
        [ModSensitiveCacheInit]
        [PreGameCacheInit]
        public static void Start()
        {
            try { Bridge.EnsureStarted(); }
            catch { }
        }
    }
}
