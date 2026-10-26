using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace CoQMcpBridge
{
    public sealed class McpServer
    {
        private const int Port = 47321;
        private const int MaxFrameBytes = 16 << 20;
        private const int WriteStallMs = 5000;
        private const int WriteChunkBytes = 64 * 1024;

        private TcpListener _listener;
        private Thread _acceptThread;
        private volatile bool _running;
        private readonly object _clientsLock = new object();
        private readonly List<ClientConn> _clients = new List<ClientConn>();

        public readonly ConcurrentQueue<string> Incoming = new ConcurrentQueue<string>();
        public Action<string> OnPayload;
        public Action<string> Log = _ => { };

        public int ClientCount { get { lock (_clientsLock) return _clients.Count; } }

        public void Start()
        {
            if (_running) return;
            _running = true;
            // Bind all interfaces: the harness runs in WSL (NAT mode), where the
            // Windows host is reached via the gateway IP, not via shared loopback.
            _listener = new TcpListener(IPAddress.Any, Port);
            _listener.Start();
            _acceptThread = new Thread(AcceptLoop) { IsBackground = true, Name = "McpAccept" };
            _acceptThread.Start();
            Log($"MCP server listening on 0.0.0.0:{Port}");
        }

        public void Stop()
        {
            _running = false;
            try { _listener?.Stop(); } catch { }
            ClientConn[] snapshot;
            lock (_clientsLock) { snapshot = _clients.ToArray(); _clients.Clear(); }
            foreach (var c in snapshot) c.Kill();
        }

        private void AcceptLoop()
        {
            while (_running)
            {
                TcpClient client;
                try { client = _listener.AcceptTcpClient(); }
                catch
                {
                    if (!_running) break;
                    Thread.Sleep(100);
                    continue;
                }

                client.NoDelay = true;
                ClientConn conn;
                try { conn = new ClientConn(this, client); }
                catch { try { client.Close(); } catch { } continue; }

                lock (_clientsLock) _clients.Add(conn);
                conn.Start();
                Log("MCP client connected");
            }
        }

        public void Broadcast(string json)
        {
            byte[] frame = Protocol.Frame(json);
            lock (_clientsLock)
            {
                for (int i = 0; i < _clients.Count; i++)
                    _clients[i].Offer(frame);
            }
        }

        private void Remove(ClientConn conn)
        {
            bool had;
            lock (_clientsLock) had = _clients.Remove(conn);
            if (had) Log("MCP client disconnected");
        }

        private static bool ReadFully(Stream s, byte[] buf, int count)
        {
            int off = 0;
            while (off < count)
            {
                int n = s.Read(buf, off, count - off);
                if (n <= 0) return false;
                off += n;
            }
            return true;
        }

        private sealed class ClientConn
        {
            private readonly McpServer _srv;
            private readonly TcpClient _tcp;
            private readonly Socket _sock;
            private readonly NetworkStream _stream;
            private readonly AutoResetEvent _wake = new AutoResetEvent(false);
            private readonly Queue<byte[]> _outbox = new Queue<byte[]>();
            private readonly object _outboxLock = new object();
            private volatile bool _alive = true;
            private int _killed;

            public ClientConn(McpServer srv, TcpClient tcp)
            {
                _srv = srv;
                _tcp = tcp;
                _sock = tcp.Client;
                _stream = tcp.GetStream();
            }

            public void Start()
            {
                new Thread(ReadLoop) { IsBackground = true, Name = "McpRead" }.Start();
                new Thread(WriteLoop) { IsBackground = true, Name = "McpWrite" }.Start();
            }

            public void Offer(byte[] frame)
            {
                if (!_alive) return;
                lock (_outboxLock) _outbox.Enqueue(frame);
                try { _wake.Set(); } catch { }
            }

            private void WriteLoop()
            {
                try
                {
                    while (_alive)
                    {
                        byte[] frame = null;
                        lock (_outboxLock)
                        {
                            if (_outbox.Count > 0)
                                frame = _outbox.Dequeue();
                        }

                        if (frame == null)
                        {
                            _wake.WaitOne(100);
                            continue;
                        }

                        if (!_sock.Poll(WriteStallMs * 1000, SelectMode.SelectWrite))
                        {
                            break;
                        }

                        int offset = 0;
                        while (offset < frame.Length && _alive)
                        {
                            int chunk = Math.Min(WriteChunkBytes, frame.Length - offset);
                            if (!_sock.Poll(WriteStallMs * 1000, SelectMode.SelectWrite))
                                break;
                            _stream.Write(frame, offset, chunk);
                            offset += chunk;
                        }

                        if (offset < frame.Length)
                            break;

                        _stream.Flush();
                    }
                }
                catch { }
                finally { Kill(); }
            }

            private void ReadLoop()
            {
                try
                {
                    var lenBuf = new byte[4];
                    while (_alive && _srv._running)
                    {
                        if (!ReadFully(_stream, lenBuf, 4)) break;
                        int len = (lenBuf[0] << 24) | (lenBuf[1] << 16) | (lenBuf[2] << 8) | lenBuf[3];
                        if (len < 0 || len > MaxFrameBytes) break;
                        var payload = new byte[len];
                        if (!ReadFully(_stream, payload, len)) break;
                        string s = Encoding.UTF8.GetString(payload);
                        Action<string> hook = _srv.OnPayload;
                        if (hook != null) hook(s); else _srv.Incoming.Enqueue(s);
                    }
                }
                catch { }
                finally { Kill(); }
            }

            public void Kill()
            {
                if (Interlocked.Exchange(ref _killed, 1) != 0) return;
                _alive = false;
                try { _wake.Set(); } catch { }
                try { _tcp.Close(); } catch { }
                _srv.Remove(this);
            }
        }
    }
}
