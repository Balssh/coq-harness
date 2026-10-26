using System;
using System.Text;

namespace CoQMcpBridge
{
    public static class Protocol
    {
        public const int DefaultPort = 47321;
        public const string Version = "1.0.0";
        public const int ProtocolVersion = 1;

        public static byte[] Frame(string json)
        {
            byte[] payload = Encoding.UTF8.GetBytes(json);
            byte[] header = new byte[4];
            header[0] = (byte)(payload.Length >> 24);
            header[1] = (byte)(payload.Length >> 16);
            header[2] = (byte)(payload.Length >> 8);
            header[3] = (byte)(payload.Length);
            byte[] frame = new byte[4 + payload.Length];
            Buffer.BlockCopy(header, 0, frame, 0, 4);
            Buffer.BlockCopy(payload, 0, frame, 4, payload.Length);
            return frame;
        }
    }

    public static class Json
    {
        public static string Escape(string s)
        {
            if (s == null) return "";
            var sb = new StringBuilder(s.Length + 8);
            foreach (char c in s)
            {
                switch (c)
                {
                    case '\\': sb.Append("\\\\"); break;
                    case '"': sb.Append("\\\""); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20)
                            sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else
                            sb.Append(c);
                        break;
                }
            }
            return sb.ToString();
        }

        public static string Str(string key, string value)
        {
            return "\"" + key + "\":\"" + Escape(value) + "\"";
        }

        public static string Num(string key, int value)
        {
            return "\"" + key + "\":" + value;
        }

        public static string Num(string key, long value)
        {
            return "\"" + key + "\":" + value;
        }

        public static string Num(string key, double value)
        {
            return "\"" + key + "\":" + value.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
        }

        public static string Bool(string key, bool value)
        {
            return "\"" + key + "\":" + (value ? "true" : "false");
        }
    }
}
