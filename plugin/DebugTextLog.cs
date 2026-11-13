using System;
using System.Collections.Generic;
using System.Text;
using BepInEx.Configuration;
using BepInEx.Logging;
using Il2CppInterop.Runtime.InteropTypes;
using Il2CppInterop.Runtime.InteropTypes.Arrays;
using UnityEngine;
using XUnity.AutoTranslator.Plugin.Core;

namespace ArknightsLocalization.RichTextFix;

// Debug aid for adding contextual translations. Off by default; switched on in
// BepInEx/config/arklocalizer.richtextfix.cfg ([Debug] LogTextContext = true).
// For every text the game shows it writes one "[TextContext]" line to
// BepInEx/LogOutput.log: the text, its textId, its object path, the context the
// plugin picked, and every script field that points at this text object
// ("Owner.Type/_field" — the pair component_fields.json expects).
internal static class DebugTextLog
{
    private const int MaxDepth = 12;
    private const int MaxLogged = 50_000;
    private const Il2CppSystem.Reflection.BindingFlags DeclaredInstance = (Il2CppSystem.Reflection.BindingFlags)54;

    private static ManualLogSource? log;
    private static string[] filters = Array.Empty<string>();
    private static bool exactFilter;
    private static readonly HashSet<string> seen = new();

    internal static bool Enabled { get; private set; }

    internal static void Configure(ConfigFile config, ManualLogSource logger)
    {
        Enabled = config.Bind("Debug", "LogTextContext", false,
            "Write the context of every shown text to LogOutput.log ([TextContext] lines). " +
            "Used to find owner/field pairs for component_fields.json. Keeps the BepInEx console visible.").Value;
        string filter = config.Bind("Debug", "LogTextFilter", "",
            "Only log texts containing one of these substrings (case-insensitive), separated by |. " +
            "Example: Idle|Talk 1|Archive File. Empty = log everything.").Value ?? "";
        filters = filter.Split('|', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        string filterMode = config.Bind("Debug", "LogTextFilterMode", "Contains",
            "Contains matches a substring; Exact matches the whole text (both case-insensitive). " +
            "Filter values are separated by |.").Value ?? "Contains";
        exactFilter = string.Equals(filterMode, "Exact", StringComparison.OrdinalIgnoreCase);
        if (!exactFilter && !string.Equals(filterMode, "Contains", StringComparison.OrdinalIgnoreCase))
            logger.LogWarning($"[TextContext] unknown LogTextFilterMode '{filterMode}', using Contains.");
        log = logger;
        if (Enabled)
            log.LogWarning($"[TextContext] debug logging is ON{(filters.Length > 0 ? $", {filterMode} filter: " + string.Join(" | ", filters) : "")}.");
    }

    internal static void Write(ComponentTranslationContext context) => Write(context.Component, context.OriginalText);

    // Called from both XUnity paths: the translating callback and the fast path for
    // texts that already have a cached translation (it skips callbacks).
    internal static void Write(object? component, string? value)
    {
        try
        {
            string original = value ?? "";
            if (original.Trim().Length == 0) return;
            if (filters.Length > 0 && !Array.Exists(filters,
                    f => exactFilter
                        ? string.Equals(original, f, StringComparison.OrdinalIgnoreCase)
                        : original.IndexOf(f, StringComparison.OrdinalIgnoreCase) >= 0)) return;
            if (component is not Il2CppObjectBase obj) return;
            Component? text = obj.TryCast<Component>();
            if (text == null) return;

            string path = PathOf(text.transform);
            if (seen.Count >= MaxLogged || !seen.Add(original + "\u0001" + path)) return;

            StringBuilder line = new("[TextContext] \"");
            line.Append(OneLine(original)).Append("\" | ").Append(text.GetIl2CppType().Name);
            string? textId = obj.TryCast<UnityEngine.UI.Text>()?.textId;
            if (!string.IsNullOrEmpty(textId)) line.Append(" | textId=").Append(textId);
            line.Append(" | context=").Append(CurrentContext(component, original));
            line.Append(" | path=").Append(path);
            line.Append(" | owners: ").Append(Owners(text));
            log?.LogInfo(line.ToString());
        }
        catch (Exception exception)
        {
            log?.LogWarning($"[TextContext] could not describe a text: {exception.Message}");
        }
    }

    private static string CurrentContext(object component, string original)
    {
        string? role = ComponentFields.Role(component);
        if (role != null) return role;
        // Scopes resolved in code (promotion, skill, talent) instead of component_fields.json.
        if (component is Il2CppObjectBase obj && obj.TryCast<Component>() is { } native)
            for (Transform? parent = native.transform; parent != null; parent = parent.parent)
                foreach (MonoBehaviour owner in parent.GetComponents<MonoBehaviour>())
                    if (owner != null && ContextTranslations.ScopeForType(owner.GetIl2CppType().FullName) is { } scope)
                        return scope + " (by owner type)";
        return "-";
    }

    // Every MonoBehaviour field (on this object or a parent) that references this text.
    private static string Owners(Component text)
    {
        List<string> found = new();
        int depth = 0;
        for (Transform? parent = text.transform; parent != null && depth < MaxDepth; parent = parent.parent, depth++)
            foreach (MonoBehaviour owner in parent.GetComponents<MonoBehaviour>())
            {
                if (owner == null) continue;
                for (Il2CppSystem.Type? type = owner.GetIl2CppType(); type != null; type = type.BaseType)
                {
                    string typeName = (type.IsGenericType ? type.GetGenericTypeDefinition() : type).FullName;
                    if (typeName.StartsWith("UnityEngine.", StringComparison.Ordinal)) break;
                    foreach (var field in type.GetFields(DeclaredInstance))
                    {
                        if (References(field, owner, text, out bool array))
                            found.Add($"{typeName}/{field.Name}{(array ? "[]" : "")} (up {depth})");
                    }
                }
            }
        return found.Count == 0 ? "-" : string.Join("; ", found);
    }

    private static bool References(Il2CppSystem.Reflection.FieldInfo field, MonoBehaviour owner, Component text,
        out bool array)
    {
        array = false;
        try
        {
            Il2CppSystem.Type fieldType = field.FieldType;
            if (fieldType.IsValueType || fieldType.IsPrimitive) return false;
            var value = field.GetValue(owner);
            if (value == null) return false;
            if (fieldType.IsArray)
            {
                // component_fields.json supports Text[] arrays only.
                if (fieldType.GetElementType().FullName != "UnityEngine.UI.Text") return false;
                foreach (var element in new Il2CppReferenceArray<UnityEngine.UI.Text>(value.Pointer))
                    if (element != null && element == text) return array = true;
                return false;
            }
            Component? component = value.TryCast<Component>();
            return component != null && component == text;
        }
        catch
        {
            return false;
        }
    }

    private static string PathOf(Transform transform)
    {
        List<string> names = new();
        for (Transform? node = transform; node != null && names.Count < MaxDepth; node = node.parent)
            names.Add(node.name);
        names.Reverse();
        return string.Join("/", names);
    }

    private static string OneLine(string text)
    {
        string flat = text.Replace("\r", "").Replace("\n", "\\n");
        return flat.Length <= 200 ? flat : flat[..199] + "…";
    }
}
