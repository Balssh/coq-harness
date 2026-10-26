using System;
using System.Collections.Generic;
using System.Text;

namespace CoQMcpBridge
{
    public static class MiniJson
    {
        public abstract class Node
        {
            public abstract string ToJson();
        }

        public class Obj : Node
        {
            public readonly Dictionary<string, Node> Fields = new Dictionary<string, Node>();

            public string GetStr(string key, string fallback = "")
            {
                if (Fields.TryGetValue(key, out var n) && n is Str s) return s.Value;
                return fallback;
            }

            public int GetInt(string key, int fallback = 0)
            {
                if (Fields.TryGetValue(key, out var n) && n is Num num) return (int)num.Value;
                return fallback;
            }

            public double GetNum(string key, double fallback = 0)
            {
                if (Fields.TryGetValue(key, out var n) && n is Num num) return num.Value;
                return fallback;
            }

            public bool GetBool(string key, bool fallback = false)
            {
                if (Fields.TryGetValue(key, out var n) && n is Bool b) return b.Value;
                return fallback;
            }

            public override string ToJson()
            {
                var sb = new StringBuilder("{");
                bool first = true;
                foreach (var kv in Fields)
                {
                    if (!first) sb.Append(",");
                    first = false;
                    sb.Append("\"").Append(Json.Escape(kv.Key)).Append("\":").Append(kv.Value.ToJson());
                }
                sb.Append("}");
                return sb.ToString();
            }
        }

        public class Arr : Node
        {
            public readonly List<Node> Items = new List<Node>();

            public override string ToJson()
            {
                var sb = new StringBuilder("[");
                bool first = true;
                foreach (var item in Items)
                {
                    if (!first) sb.Append(",");
                    first = false;
                    sb.Append(item.ToJson());
                }
                sb.Append("]");
                return sb.ToString();
            }
        }

        public class Str : Node
        {
            public readonly string Value;
            public Str(string v) { Value = v; }
            public override string ToJson() { return "\"" + Json.Escape(Value) + "\""; }
        }

        public class Num : Node
        {
            public readonly double Value;
            public Num(double v) { Value = v; }
            public override string ToJson()
            {
                if (Value == Math.Floor(Value) && Math.Abs(Value) < 1e15)
                    return ((long)Value).ToString();
                return Value.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
            }
        }

        public class Bool : Node
        {
            public readonly bool Value;
            public Bool(bool v) { Value = v; }
            public override string ToJson() { return Value ? "true" : "false"; }
        }

        public class Null : Node
        {
            public override string ToJson() { return "null"; }
        }

        public static Node Parse(string json)
        {
            int pos = 0;
            return ParseValue(json, ref pos);
        }

        private static void SkipWs(string s, ref int pos)
        {
            while (pos < s.Length && char.IsWhiteSpace(s[pos])) pos++;
        }

        private static Node ParseValue(string s, ref int pos)
        {
            SkipWs(s, ref pos);
            if (pos >= s.Length) return new Null();

            char c = s[pos];
            if (c == '{') return ParseObject(s, ref pos);
            if (c == '[') return ParseArray(s, ref pos);
            if (c == '"') return new Str(ParseString(s, ref pos));
            if (c == 't' || c == 'f') return ParseBool(s, ref pos);
            if (c == 'n') { pos += 4; return new Null(); }
            return ParseNumber(s, ref pos);
        }

        private static Obj ParseObject(string s, ref int pos)
        {
            var obj = new Obj();
            pos++; // {
            SkipWs(s, ref pos);
            if (pos < s.Length && s[pos] == '}') { pos++; return obj; }

            while (pos < s.Length)
            {
                SkipWs(s, ref pos);
                string key = ParseString(s, ref pos);
                SkipWs(s, ref pos);
                if (pos < s.Length && s[pos] == ':') pos++;
                var value = ParseValue(s, ref pos);
                obj.Fields[key] = value;
                SkipWs(s, ref pos);
                if (pos < s.Length && s[pos] == ',') { pos++; continue; }
                if (pos < s.Length && s[pos] == '}') { pos++; break; }
                break;
            }
            return obj;
        }

        private static Arr ParseArray(string s, ref int pos)
        {
            var arr = new Arr();
            pos++; // [
            SkipWs(s, ref pos);
            if (pos < s.Length && s[pos] == ']') { pos++; return arr; }

            while (pos < s.Length)
            {
                var value = ParseValue(s, ref pos);
                arr.Items.Add(value);
                SkipWs(s, ref pos);
                if (pos < s.Length && s[pos] == ',') { pos++; continue; }
                if (pos < s.Length && s[pos] == ']') { pos++; break; }
                break;
            }
            return arr;
        }

        private static string ParseString(string s, ref int pos)
        {
            var sb = new StringBuilder();
            pos++; // opening "
            while (pos < s.Length)
            {
                char c = s[pos++];
                if (c == '"') break;
                if (c == '\\' && pos < s.Length)
                {
                    char next = s[pos++];
                    switch (next)
                    {
                        case 'n': sb.Append('\n'); break;
                        case 'r': sb.Append('\r'); break;
                        case 't': sb.Append('\t'); break;
                        case '"': sb.Append('"'); break;
                        case '\\': sb.Append('\\'); break;
                        case '/': sb.Append('/'); break;
                        case 'u':
                            if (pos + 4 <= s.Length)
                            {
                                sb.Append((char)Convert.ToInt32(s.Substring(pos, 4), 16));
                                pos += 4;
                            }
                            break;
                        default: sb.Append(next); break;
                    }
                }
                else
                {
                    sb.Append(c);
                }
            }
            return sb.ToString();
        }

        private static Node ParseNumber(string s, ref int pos)
        {
            int start = pos;
            while (pos < s.Length && (char.IsDigit(s[pos]) || s[pos] == '-' || s[pos] == '+' || s[pos] == '.' || s[pos] == 'e' || s[pos] == 'E'))
                pos++;
            string numStr = s.Substring(start, pos - start);
            if (double.TryParse(numStr, System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out double val))
                return new Num(val);
            return new Num(0);
        }

        private static Node ParseBool(string s, ref int pos)
        {
            if (s.Substring(pos).StartsWith("true")) { pos += 4; return new Bool(true); }
            pos += 5; return new Bool(false);
        }
    }
}
