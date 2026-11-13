using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace ArknightsLocalization.RichTextFix;

internal static class DynamicTranslations
{
    private sealed class Rule
    {
        internal string Scope = "", Target = "", Anchor = "";
        internal Regex Pattern = null!;
        internal Dictionary<string, string> Roles = new();
        internal Dictionary<string, string> Groups = new();
    }
    // Any placeholder: {0}, {0:d2}, {cost}, {atk:0%}, {@nickname}, ...
    private static readonly Regex Slot = new(@"\{(?<key>[^{}:\r\n]+)(?::[^{}\r\n]+)?\}");
    private static readonly Regex Number = new(@"\A[+\-]?[0-9][0-9,.]*(?:%|K|M|万|億|亿)?\z");
    private static readonly List<Rule> rules = new();

    /// <summary>
    /// Exact static lookup supplied by the plugin. Macro captures often hold
    /// an item/operator name that also has its own translation key; without
    /// this, "{1}" in the giftbox popup would stay English.
    /// </summary>
    internal static Func<string, string?>? StaticLookup;

    /// <summary>Canonical slot key: case and {@name}/{name} spelling do not matter.</summary>
    private static string SlotKey(string raw)
    {
        int colon = raw.IndexOf(':');
        if (colon >= 0) raw = raw[..colon];
        return raw.Trim().TrimStart('@').ToLowerInvariant();
    }

    internal static void Load(IEnumerable<string> records)
    {
        rules.Clear();
        foreach (string record in records)
        {
            using JsonDocument json = JsonDocument.Parse(record);
            var root = json.RootElement;
            Rule rule = new() { Scope = root.GetProperty("scope").GetString()!, Target = root.GetProperty("target").GetString()! };
            foreach (var pair in JsonSerializer.Deserialize<Dictionary<string, string>>(root.GetProperty("roles").GetRawText())!)
            {
                rule.Roles[SlotKey(pair.Key)] = pair.Value;
            }
            string source = Normalize(RichTextStyleRestorer.PlainText(root.GetProperty("source").GetString()!));
            int cursor = 0;
            string pattern = "\\A";
            bool hasSlot = false;
            string lastBeforeSlot = "";
            foreach (Match slot in Slot.Matches(source))
            {
                hasSlot = true;
                string literal = source[cursor..slot.Index];
                lastBeforeSlot = literal;
                if (literal.Length > rule.Anchor.Length) rule.Anchor = literal;
                pattern += Regex.Escape(literal);
                string key = SlotKey(slot.Groups["key"].Value);
                if (rule.Groups.TryGetValue(key, out string? group)) pattern += "\\k<" + group + ">";
                else
                {
                    group = "p" + rule.Groups.Count;
                    rule.Groups[key] = group;
                    pattern += "(?<" + group + ">[^\\r\\n]{1,128}?)";
                }
                cursor = slot.Index + slot.Length;
            }
            if (!hasSlot) continue;
            string tail = source[cursor..];
            if (tail.Length > rule.Anchor.Length) rule.Anchor = tail;
            // All-numeric rules ("{0} sec", "ATK +{atk:0%}", "<@ping.high>{0}</>ms")
            // may rely on a 2-3 char anchor: the Number check below rejects any
            // non-numeric capture, so a short anchor cannot misfire on prose.
            bool numericOnly = rule.Groups.Count > 0 && rule.Groups.Keys.All(
                key => rule.Roles.TryGetValue(key, out string? role) && role == "number");
            // "Dr. {@nickname}!" / "Dr. {@nickname}." / "'Dr. {@nickname}?'":
            // a 3-char greeting anchor is safe because the whole string is
            // anchored and the vocative must be "Dr.". Do not generalize to a
            // bare "I am {@nickname}." rule, which would swallow prose.
            bool nicknameGreeting = rule.Groups.Count == 1
                && rule.Groups.ContainsKey("nickname")
                && lastBeforeSlot.TrimEnd().EndsWith("Dr.", StringComparison.OrdinalIgnoreCase);
            int minAnchor = numericOnly ? 2 : nicknameGreeting ? 3 : 6;
            // A rule with no meaningful literal would match arbitrary text.
            if (rule.Anchor.Trim().Length < minAnchor) continue;
            if (rule.Groups.Count == 0) continue;
            rule.Pattern = new Regex(pattern + Regex.Escape(tail) + "\\z", RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(30));
            rules.Add(rule);
        }
        // Longest anchors first: the cheap Contains filter drops almost every
        // rule before any regex runs.
        rules.Sort((a, b) => b.Anchor.Length.CompareTo(a.Anchor.Length));
    }

    internal static string Normalize(string text) => text.Replace("\\n", "\n").Replace("\r\n", "\n").Trim();

    internal static string? Lookup(string scope, string original)
    {
        return LookupCore(original, scope, any: false);
    }

    /// <summary>
    /// Global template lookup used before XUnity's cache/regex pass. Rules
    /// emitted with scope "any" are template pairs that would otherwise need a
    /// (very expensive) XUnity regex entry.
    /// </summary>
    internal static string? LookupAny(string original)
    {
        return LookupCore(original, null, any: true);
    }

    private static string? LookupCore(string original, string? scope, bool any)
    {
        string plain = Normalize(RichTextStyleRestorer.PlainText(original));
        string? result = null;
        int bestAnchor = -1;
        foreach (Rule rule in rules)
        {
            if (any ? rule.Scope != "any" : rule.Scope != scope) continue;
            if (!plain.Contains(rule.Anchor, StringComparison.Ordinal)) continue;
            Match match;
            try { match = rule.Pattern.Match(plain); }
            catch (RegexMatchTimeoutException) { continue; }
            if (!match.Success) continue;
            Dictionary<string, string> values = new();
            bool valid = true;
            foreach (var entry in rule.Groups)
            {
                string value = match.Groups[entry.Value].Value;
                string role = rule.Roles.TryGetValue(entry.Key, out string? declared) ? declared : "identity";
                if (role == "number" && !Number.IsMatch(value)) { valid = false; break; }
                if (role is not ("identity" or "number"))
                {
                    string? translated = ContextTranslations.Lookup(role, value);
                    if (translated == null && role == "activity-name" && !ContextTranslations.IsTarget(role, value)) { valid = false; break; }
                    value = translated ?? value;
                }
                else if (role == "identity" && value.Length <= 80)
                {
                    // Not every identity argument is opaque: the giftbox popup
                    // passes the item name in a slot. Prefer an exact static
                    // translation for the captured value when one exists.
                    // Keep this to short values so a broad template can never
                    // wrap a whole sentence that has its own exact line.
                    string? translated = StaticLookup?.Invoke(value);
                    if (!string.IsNullOrWhiteSpace(translated) && translated != value)
                    {
                        value = translated;
                    }
                }
                // Identity arguments are never passed to a translation lookup.
                values[entry.Key] = value;
            }
            if (!valid) continue;
            string candidate = Slot.Replace(rule.Target, slot =>
            {
                string key = SlotKey(slot.Groups["key"].Value);
                return values.TryGetValue(key, out string? value) ? value : slot.Value;
            });
            int anchor = rule.Anchor.Length;
            // Several templates can match one runtime string (generic vs
            // specific). Prefer the most specific rule; only an equally long
            // tie with a different result is treated as ambiguous.
            if (anchor > bestAnchor)
            {
                bestAnchor = anchor;
                result = candidate;
            }
            else if (anchor == bestAnchor && result != candidate)
            {
                return null;
            }
        }
        return result;
    }
}
