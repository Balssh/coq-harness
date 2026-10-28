using System;
using System.Collections.Concurrent;
using UnityEngine;

namespace CoQMcpBridge
{
    /// <summary>
    /// MonoBehaviour that drains a thread-safe queue of actions on the main
    /// thread every frame. Lets the background pump thread schedule Unity API
    /// calls (FindObjectOfType, UI manipulation, etc.) safely during pre-game
    /// screens (main menu, chargen).
    /// </summary>
    public class BridgeMainThread : MonoBehaviour
    {
        private static readonly ConcurrentQueue<Action> _queue = new ConcurrentQueue<Action>();
        private static BridgeMainThread _instance;

        public static void EnsureCreated()
        {
            if (_instance != null) return;
            var go = new GameObject("CoQMcpBridgeMainThread");
            DontDestroyOnLoad(go);
            _instance = go.AddComponent<BridgeMainThread>();
        }

        public static void Enqueue(Action action)
        {
            _queue.Enqueue(action);
        }

        /// <summary>Enqueue an action and block until it completes (with timeout).</summary>
        public static bool EnqueueAndWait(Action action, int timeoutMs = 10000)
        {
            var done = new System.Threading.ManualResetEventSlim(false);
            _queue.Enqueue(() =>
            {
                try { action(); }
                catch (Exception e) { Console.WriteLine("[mcp] MainThread error: " + e); }
                finally { done.Set(); }
            });
            return done.Wait(timeoutMs);
        }

        void Awake()
        {
            Application.runInBackground = true;
        }

        void Update()
        {
            // Without this Unity stops calling Update() when the window loses
            // focus, which stalls every queued action and the popup snapshot.
            // Qud's options reset it (it follows the "music in background"
            // setting), so re-assert it every frame.
            if (!Application.runInBackground)
                Application.runInBackground = true;

            while (_queue.TryDequeue(out Action action))
            {
                try { action(); }
                catch (Exception e) { Console.WriteLine("[mcp] MainThread error: " + e); }
            }

            PopupBridge.Tick();
        }
    }
}
