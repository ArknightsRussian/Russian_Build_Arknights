using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using Il2CppInterop.Runtime.InteropTypes;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace ArknightsLocalization.RichTextFix;

/// <summary>
/// Shrink a translated text that no longer fits its box.
///
/// Russian is 10-20% longer than English, so skill/talent descriptions and
/// module trait rows can overflow a prefab that was sized for the English line.
/// The pack keeps the full translation; this policy only reduces the font size
/// of that one component (down to 72% of the original) when the rendered text
/// is taller than its rect. The game restores the original size when a shorter
/// string is assigned.
/// </summary>
internal static class TextFitPolicy
{
    private const float MinimumScale = 0.72f;
    private const int MinimumFontSize = 8;

    private sealed class State
    {
        internal int BaseSize;
        internal int AppliedSize;
        internal string? LastText;
    }

    private static readonly Dictionary<int, State> states = new();

    internal static void Adjust(object? component)
    {
        if (component is not Il2CppObjectBase obj) return;
        try
        {
            TMP_Text? tmp = obj.TryCast<TMP_Text>();
            if (tmp != null)
            {
                FitTmp(tmp);
                return;
            }
            Text? ugui = obj.TryCast<Text>();
            if (ugui != null) FitUgui(ugui);
        }
        catch
        {
            // Fitting is cosmetic; a layout edge case must never break display.
        }
    }

    private static void FitTmp(TMP_Text text)
    {
        if (text == null || text.enableAutoSizing) return;
        string value = text.text ?? "";
        if (value.Length == 0) return;
        RectTransform? rect = text.rectTransform;
        if (rect == null) return;
        float width = rect.rect.width;
        float height = rect.rect.height;
        if (width < 8f || height < 8f || IsScrollable(rect)) return;

        int id = text.GetInstanceID();
        if (!states.TryGetValue(id, out State? state)) states[id] = state = new State();
        int current = Mathf.RoundToInt(text.fontSize);
        if (state.LastText != value)
        {
            // The game or XUnity assigned a new string. Keep our own reduced
            // size out of the baseline; only an external size change resets it.
            if (state.BaseSize == 0 || current != state.AppliedSize)
                state.BaseSize = current;
            state.LastText = value;
        }
        if (state.BaseSize <= 0) return;

        Vector2 preferred = text.GetPreferredValues(value, width, 0f);
        int target = state.BaseSize;
        if (preferred.y > height * 1.02f)
        {
            float scale = Mathf.Max(height / preferred.y, MinimumScale);
            target = Mathf.Max(Mathf.RoundToInt(state.BaseSize * scale), MinimumFontSize);
        }
        target = Mathf.Min(target, state.BaseSize);
        if (current == target) return;
        text.fontSize = target;
        state.AppliedSize = target;
    }

    private static void FitUgui(Text text)
    {
        if (text == null || text.resizeTextForBestFit) return;
        string value = text.text ?? "";
        if (value.Length == 0) return;
        RectTransform? rect = text.rectTransform;
        if (rect == null) return;
        float width = rect.rect.width;
        float height = rect.rect.height;
        if (width < 8f || height < 8f || IsScrollable(rect)) return;

        int id = text.GetInstanceID();
        if (!states.TryGetValue(id, out State? state)) states[id] = state = new State();
        int current = text.fontSize;
        if (state.LastText != value)
        {
            if (state.BaseSize == 0 || current != state.AppliedSize)
                state.BaseSize = current;
            state.LastText = value;
        }
        if (state.BaseSize <= 0) return;

        float preferred = text.preferredHeight;
        int target = state.BaseSize;
        if (preferred > height * 1.02f)
        {
            float scale = Mathf.Max(height / preferred, MinimumScale);
            target = Mathf.Max(Mathf.RoundToInt(state.BaseSize * scale), MinimumFontSize);
        }
        target = Mathf.Min(target, state.BaseSize);
        if (current == target) return;
        text.fontSize = target;
        state.AppliedSize = target;
    }

    private static bool IsScrollable(RectTransform rect)
    {
        for (Transform? node = rect; node != null; node = node.parent)
            if (node.GetComponent<ScrollRect>() != null) return true;
        return false;
    }
}

/// <summary>
/// Strings the client builds in code instead of reading from a table.
/// They cannot be matched by a translation key, but their shape is stable.
/// </summary>
internal static class RuntimeRewrites
{
    private static readonly Regex EliteLevel = new(
        @"\bElite\s*(\d)\s*Level\s*(\d+)",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
    private static readonly Regex EliteOnly = new(
        @"\AElite\s+(\d+)\z",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
    private static readonly Regex LevelOnly = new(
        @"\ALevel\s*(\d+)\z",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
    private static readonly Regex SkillPointLabel = new(
        @"\A(?:SP|СП)\z",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
    private static readonly Regex StageMode = new(
        @"\A(?<mode>Standard|Adverse)\s+(?<code>\d+\s*[-–—]\s*\d+)\z",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
    private static readonly Regex AtElite = new(
        @"\bat\s+Elite\s*(\d+)\b",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
    private static readonly Regex EliteAnywhere = new(
        @"\bElite\s*(\d+)\b",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
    private static readonly Regex SpAnywhere = new(
        @"(?<![A-Za-zА-Яа-яЁё])(?:SP|СП)(?![A-Za-zА-Яа-яЁё])",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    internal static bool TryFix(string text, out string translation)
    {
        translation = "";
        if (string.IsNullOrWhiteSpace(text)) return false;

        Match elite = EliteLevel.Match(text);
        if (elite.Success)
        {
            translation = $"Элита {elite.Groups[1].Value} Ур. {elite.Groups[2].Value}";
            return true;
        }
        Match promotion = EliteOnly.Match(text.Trim());
        if (promotion.Success)
        {
            translation = $"Элита {promotion.Groups[1].Value}";
            return true;
        }
        Match level = LevelOnly.Match(text.Trim());
        if (level.Success)
        {
            translation = $"Ур. {level.Groups[1].Value}";
            return true;
        }
        if (SkillPointLabel.IsMatch(text.Trim()))
        {
            translation = "ОН";
            return true;
        }
        Match atElite = AtElite.Match(text.Trim());
        if (atElite.Success && atElite.Index == 0 && atElite.Length == text.Trim().Length)
        {
            translation = $"Элита {atElite.Groups[1].Value}";
            return true;
        }
        Match stage = StageMode.Match(text.Trim());
        if (stage.Success)
        {
            string mode = stage.Groups["mode"].Value.Equals("Adverse", StringComparison.OrdinalIgnoreCase)
                ? "Сложно"
                : "Стандарт";
            translation = $"{mode} {stage.Groups["code"].Value.Replace('–', '-').Replace('—', '-')}";
            return true;
        }
        return false;
    }

    /// <summary>
    /// Fix English fragments the client splices into an already translated
    /// string ("Модуль Elite 2Level60", "Удачи~ at Elite 2", "50 SP").
    /// </summary>
    internal static string Apply(string text)
    {
        if (string.IsNullOrEmpty(text)) return text;
        if (text.IndexOf("Elite", StringComparison.OrdinalIgnoreCase) >= 0)
        {
            text = EliteLevel.Replace(text,
                m => $"Элита {m.Groups[1].Value} Ур. {m.Groups[2].Value}");
            text = AtElite.Replace(text, m => $"Элита {m.Groups[1].Value}");
            text = EliteAnywhere.Replace(text, m => $"Элита {m.Groups[1].Value}");
        }
        // "SP" is deliberately not rewritten in composed text: item/series
        // names such as "Swimming Suit Type SP" are not skill points. The
        // standalone label and the data pack handle the stat UI.
        return text;
    }
}
