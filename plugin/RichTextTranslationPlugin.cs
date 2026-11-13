using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using BepInEx;
using BepInEx.Unity.IL2CPP;
using Il2CppInterop.Runtime.InteropTypes;
using Torappu.UI;
using UnityEngine;
using XUnity.AutoTranslator.Plugin.Core;

namespace ArknightsLocalization.RichTextFix;

[BepInPlugin(PluginGuid, PluginName, PluginVersion)]
[BepInDependency(
    "gravydevsupreme.xunity.autotranslator",
    BepInDependency.DependencyFlags.HardDependency)]
public sealed class RichTextTranslationPlugin : BasePlugin
{
    public const string PluginGuid = "arklocalizer.richtextfix";
    public const string PluginName = "Arknights Localization Rich Text Fix";
    public const string PluginVersion = "2.0.0";

    private const uint GetWindowOwner = 4;
    private const int ShowWindowHide = 0;
    private const int ConsoleHidePollMilliseconds = 100;
    private const int ConsoleHideTimeoutMilliseconds = 120_000;

    private readonly object registrationGate = new();
    private ITranslator? translator;
    private bool registered;
    private int firstTranslationLogged;
    private int firstFragmentFallbackBlockedLogged;
    private int firstCommentedTextLogged;
    private int firstCommentedTextErrorLogged;
    private int firstCommentedTextCastMissLogged;
    private int firstCommentedTextProbeLogged;
    private readonly HashSet<string> reportedScoreLabels = new();
    private readonly HashSet<string> reportedBareTags = new();

    private static readonly Regex BreakTag = new(
        @"<br\s*/?>",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

    private static readonly Regex WhitespaceAroundLineBreak = new(
        @"[ \t]*\n[ \t]*",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private static readonly Regex RuntimeNumber = new(
        @"\A[0-9]+(?:\.[0-9]+)?\z",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private static readonly Regex BareTag = new(
        @"\A(?:DPS|Support|Healing|Defense|Survival|AoE|Crowd-Control|Debuff|Nuker|Tank|Slow|Shift|Summon|Recovery)\z",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

    // The game appends progress counters and stock counts to an already
    // localized label at runtime ("Path x20", "Zone(0/2)", "(0/1)"). The pack
    // only holds the base string, so split the suffix off, translate the base
    // and glue the untouched suffix back on.
    private static readonly Regex RuntimeSuffix = new(
        @"(?<suffix>\s*(?:\(\s*\d+(?:\s*/\s*\d+)?\s*\)|[x×]\s*\d+))\z",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

    public override void Load()
    {
        DebugTextLog.Configure(Config, Log);
        try { ContextTranslations.Load(); }
        catch (Exception exception) { Log.LogWarning($"Could not load contextual translations: {exception}"); }
        try { Log.LogInfo($"Loaded {OfficialRichStyles.Load()} exact CN rich-text style targets."); }
        catch (Exception exception) { Log.LogWarning($"Could not load CN rich styles; using source span recovery: {exception}"); }
        try
        {
            CnFontOverride.Enable(Log);
        }
        catch (Exception exception)
        {
            Log.LogError($"Could not enable CN font loading: {exception}");
        }
        if (!DebugTextLog.Enabled) StartConsoleAutoHide();

        // XUnity's BepInEx entry point is loaded before this plugin, but its
        // AutoTranslationPlugin.Current singleton is created later by an IL2CPP
        // proxy behaviour. Its public completion event runs after the cache and
        // hooks are ready, on the Unity thread.
        AutoTranslatorState.PluginInitializationCompleted += OnXUnityInitialized;
        if (AutoTranslatorState.PluginInitialized)
        {
            OnXUnityInitialized();
        }
        else
        {
            Log.LogInfo("Waiting for XUnity before enabling whole rich-text lookup.");
        }
    }

    private void OnXUnityInitialized()
    {
        try
        {
            lock (registrationGate)
            {
                if (registered)
                {
                    return;
                }

                ITranslator? current = AutoTranslator.Default;
                if (current is null)
                {
                    Log.LogError("XUnity reported initialization without a translator instance.");
                    return;
                }

                try
                {
                    CnFontOverride.EnableComponentCoverage();
                }
                catch (Exception exception)
                {
                    Log.LogError($"Could not enable full CN font coverage: {exception}");
                }
                current.RegisterOnTranslatingCallback(TranslateWholeRichText);
                ComponentTranslationStabilization.Enable();
                try { BattleFinishWrap.Enable(Log); }
                catch (Exception exception) { Log.LogWarning($"Could not enable BattleFinish wrapping: {exception}"); }
                translator = current;
                DynamicTranslations.StaticLookup = text =>
                    current.TryTranslate(text, out string value)
                    && !string.IsNullOrWhiteSpace(value) && value != text
                        ? value
                        : null;
                registered = true;

                AutoTranslatorState.PluginInitializationCompleted -= OnXUnityInitialized;
                Log.LogInfo("Whole rich-text lookup enabled for Arknights skill descriptions.");
            }
        }
        catch (Exception exception)
        {
            // XUnity catches event-subscriber exceptions as well, but keeping
            // this boundary produces a clear plugin-specific diagnostic.
            Log.LogError($"Could not register rich-text lookup: {exception}");
        }
    }

    // UICommentedText owns the parser for the game's own <@...>/<$...> markup.
    // Plain Text controls only understand Unity rich text, so a <$ba.stun>
    // keyword there cannot produce the clickable terminology tooltip. Let the
    // game rebuild the comment text (links, buttons, keyword colours) from the
    // translated string with restored tags when the component supports it.
    private static string? TranslateTagWords(string role, string original)
    {
        if (string.IsNullOrWhiteSpace(original)) return null;
        string[] parts = Regex.Split(original, @"(\s+)");
        bool changed = false;
        for (int i = 0; i < parts.Length; i++)
        {
            string part = parts[i];
            if (string.IsNullOrWhiteSpace(part)) continue;
            string? translated = ContextTranslations.Lookup(role, part);
            if (translated == null) return null;
            parts[i] = translated;
            changed = true;
        }
        return changed ? string.Concat(parts) : null;
    }

    private void ApplyTranslation(ComponentTranslationContext context, string original, string text)
    {
        if (text == "Счёт" && reportedScoreLabels.Add(original))
            Log.LogInfo($"[tags] 'Счёт' for original '{original}' on {context.Component?.GetType().FullName ?? "?"}");
        if (text.Contains("<@") || text.Contains("<$"))
        {
            if (TrySetCommentedText(context, original, text)) return;
            // Panels without a comment renderer still understand Unity colours;
            // resolve the official macros so <@ba.vup> shows as colour instead
            // of raw markup. Never install components or add links here.
            text = OfficialRichStyles.ResolveMacros(text);
        }
        context.OverrideTranslatedText(text);
    }

    private bool TrySetCommentedText(ComponentTranslationContext context, string original, string text)
    {
        if (context.Component is not Il2CppObjectBase obj) return false;
        try
        {
            UICommentedText? commented = obj.TryCast<UICommentedText>();
            if (commented == null) commented = FindCommentedOwner(obj, original);
            if (commented == null) return false;
            if (!UICommentedText.SetCommentedText(commented, text, commented.useDarkColor)) return false;
            if (Interlocked.Exchange(ref firstCommentedTextLogged, 1) == 0)
                Log.LogInfo("Rebuilt clickable rich text through UICommentedText.SetCommentedText.");
            return true;
        }
        catch (Exception exception)
        {
            if (Interlocked.Exchange(ref firstCommentedTextErrorLogged, 1) == 0)
                Log.LogWarning($"Could not rebuild clickable rich text: {exception}");
            return false;
        }
    }

    // A prefab may bind UICommentedText through a field declared as Text, so the
    // wrapper seen by XUnity is the base class. Walk the nearby hierarchy and
    // pick only the comment renderer that currently shows this exact string.
    private UICommentedText? FindCommentedOwner(Il2CppObjectBase obj, string original)
    {
        Component? native = obj.TryCast<Component>();
        if (native == null) return null;
        Transform? transform = native.transform;
        if (transform == null) return null;
        for (Transform? node = transform; node != null; node = node.parent)
            foreach (UICommentedText candidate in node.GetComponents<UICommentedText>())
            {
                if (candidate == null) continue;
                if (Interlocked.Exchange(ref firstCommentedTextProbeLogged, 1) == 0)
                    Log.LogInfo($"[richtags] found UICommentedText '{node.name}' near '{transform.name}'");
                if (candidate.text == original || candidate.Pointer == obj.Pointer) return candidate;
            }
        if (Interlocked.Exchange(ref firstCommentedTextCastMissLogged, 1) == 0)
            Log.LogInfo($"[richtags] no UICommentedText near '{transform.name}' ({native.GetType().FullName})");
        return null;
    }

    private void TranslateWholeRichText(ComponentTranslationContext context)    {
        string original = context.OriginalText;
        if (string.IsNullOrWhiteSpace(original))
        {
            return;
        }
        if (DebugTextLog.Enabled) DebugTextLog.Write(context);

        string? role = ComponentFields.Role(context.Component);
        if (role == null && BareTag.IsMatch(original.Trim()) && reportedBareTags.Add(original.Trim()))
            Log.LogInfo($"[tags] bare tag '{original.Trim()}' on {context.Component?.GetType().FullName ?? "?"}");
        if (role == "identity")
        {
            context.IgnoreComponent();
            return;
        }
        string? typed = role == null ? null : DynamicTranslations.Lookup(role, original)
            ?? ContextTranslations.Lookup(role, original);
        if (typed == null && role == "operator-autochess" && !ContextTranslations.IsAmbiguous(role, original))
            typed = ContextTranslations.Lookup("operator", original);
        if (typed != null)
        {
            ApplyTranslation(context, original, OfficialRichStyles.Restore(original, typed, _ => null));
            return;
        }
        // Character-info and recruit tag rows are often one Text holding several
        // words ("Healing DPS Support", possibly newline-separated). The context
        // dictionary stores single tags, so compose them word by word.
        if (role is "operator-tag" or "recruit-tag")
        {
            string? composed = TranslateTagWords(role, original);
            if (composed != null)
            {
                ApplyTranslation(context, original, OfficialRichStyles.Restore(original, composed, _ => null));
                return;
            }
        }
        if (role != null && (ContextTranslations.IsAmbiguous(role, original)
            || (role == "operator-autochess" && ContextTranslations.IsAmbiguous("operator", original))))
        {
            context.IgnoreComponent();
            return;
        }

        // Global macro templates (skill/module/talent numbers, {0} slots,
        // {nickname}, ...). These used to live in 14_regex.txt, where XUnity
        // compiled them all and scanned every one for every unmatched text.
        // The plugin indexes them by a literal anchor and runs before XUnity's
        // lookup, so the expensive regex pass is not needed for them.
        //
        // Exact static translations must be tried first: a broad template such
        // as "Complete {0}" otherwise swallows a long quest description that
        // has its own exact RU line, producing a mixed RU/EN sentence.
        ITranslator? exactTranslator = translator;
        if (exactTranslator != null
            && exactTranslator.TryTranslate(original, out string exactTarget)
            && !string.IsNullOrWhiteSpace(exactTarget)
            && exactTarget != original)
        {
            ApplyTranslation(context, original, OfficialRichStyles.Restore(original, exactTarget, _ => null));
            return;
        }

        string? dynamicTemplate = DynamicTranslations.LookupAny(original);
        if (dynamicTemplate != null)
        {
            ApplyTranslation(context, original, OfficialRichStyles.Restore(original, dynamicTemplate, _ => null));
            return;
        }

        string? scoped = ComponentContext.Lookup(context.Component, original, true)
            ?? ComponentContext.LookupId(context.Component, original);
        if (scoped != null)
        {
            ApplyTranslation(context, original, OfficialRichStyles.Restore(original, scoped, _ => null));
            return;
        }
        bool containsMarkup = original.IndexOf('<') >= 0;
        bool containsLineBreak = original.IndexOf('\n') >= 0
            || original.IndexOf('\r') >= 0
            || BreakTag.IsMatch(original);
        if (!containsMarkup && !containsLineBreak)
        {
            // Some game paths resolve/remove data macros before assigning the
            // component. The exact CN target still carries the lost style.
            ITranslator? active = translator;
            if (active != null && active.TryTranslate(original, out string target)
                && target != original && OfficialRichStyles.HasTarget(target))
                ApplyTranslation(context, original, OfficialRichStyles.Restore(original, target, _ => null));
            else if (active != null && (!active.TryTranslate(original, out string existing) || existing == original))
            {
                scoped = ComponentContext.Lookup(context.Component, original, false);
                if (scoped != null) ApplyTranslation(context, original, OfficialRichStyles.Restore(original, scoped, _ => null));
                else if (TryTranslateWithRuntimeSuffix(active, original, out string suffixed))
                    ApplyTranslation(context, original, suffixed);
            }
            return;
        }

        string plain = RichTextStyleRestorer.PlainText(original);
        plain = plain.Replace("\\r\\n", "\n", StringComparison.Ordinal)
            .Replace("\\n", "\n", StringComparison.Ordinal)
            .Replace("\\r", "\n", StringComparison.Ordinal)
            .Replace("\r\n", "\n", StringComparison.Ordinal)
            .Replace('\r', '\n');
        plain = WhitespaceAroundLineBreak.Replace(plain, "\n").Trim();

        ITranslator? current = translator;
        if (current is null)
        {
            return;
        }

        // Authored templates carry the CN highlight tags, while XUnity's pack
        // stores tag-stripped values. Prefer the authored target so restored
        // skill descriptions keep every <@ba.*> highlight (e.g. "moderately").
        string? translation = DynamicTranslations.LookupAny(plain);
        if (string.IsNullOrWhiteSpace(translation)
            && current.TryTranslate(plain, out string wholeTranslation)
            && !string.IsNullOrWhiteSpace(wholeTranslation))
        {
            translation = wholeTranslation;
        }
        else if (string.IsNullOrWhiteSpace(translation) && TryTranslateSargonAgreement(plain, out string sargonTranslation))
        {
            // Sargon's in-battle description is the only current agreement
            // that formats a stack-dependent duration before assigning the
            // rich-text component. XUnity's component callback can miss the
            // generated regex entry depending on the active translation
            // scope, so handle this one official, tightly identified format
            // without relaxing fragment fallback for any other component.
            translation = sargonTranslation;
        }
        else if (string.IsNullOrWhiteSpace(translation) && containsLineBreak
            && TryTranslateLines(current, plain, out string lineTranslation))
        {
            // Operator tags and module-enhanced traits are assembled into one
            // TMP component from independently translated data fields. Fall
            // back to an all-or-nothing line lookup when no composite key is
            // present, so the UI never shows a Chinese/English mixture.
            translation = lineTranslation;
        }

        if (string.IsNullOrWhiteSpace(translation))
            translation = ComponentContext.Lookup(context.Component, original, false);
        if (string.IsNullOrWhiteSpace(translation)
            && TryTranslateWithRuntimeSuffix(current, original, out string runtimeSuffixTranslation))
            translation = runtimeSuffixTranslation;

        if (!string.IsNullOrWhiteSpace(translation))
        {
            // Keep the whole-string lookup, then transfer only styles whose
            // target spans can be identified without guessing word order.
            // A no-op translation must not strip literal markup in <noparse>.
            if (translation == plain) { context.IgnoreComponent(); return; }
            ApplyTranslation(context, original, OfficialRichStyles.Restore(original, translation,
                fragment => current.TryTranslate(fragment, out string result) ? result : null));
            if (Interlocked.Exchange(ref firstTranslationLogged, 1) == 0)
            {
                Log.LogInfo("Applied the first whole rich-text translation.");
            }
        }
        else if (containsMarkup)
        {
            // Returning the default behaviour here lets XUnity split the
            // component around its rich-text tags. Auto Chess descriptions
            // are assembled dynamically and reuse one TMP component, so a
            // partial hit can leave mismatched closing tags and poison later
            // agreement selections. Keep this update untranslated instead;
            // the next text assigned to the component is evaluated afresh.
            context.IgnoreComponent();
            if (Interlocked.Exchange(ref firstFragmentFallbackBlockedLogged, 1) == 0)
            {
                Log.LogInfo("Blocked XUnity fragment fallback for an unmatched rich-text component.");
            }
        }
    }

    private void StartConsoleAutoHide()
    {
        if (!OperatingSystem.IsWindows() || GetConsoleWindow() == IntPtr.Zero)
        {
            return;
        }

        Thread worker = new(HideConsoleAfterGameWindowAppears)
        {
            IsBackground = true,
            Name = "ArknightsLocalization.ConsoleAutoHide",
        };
        worker.Start();
    }

    private void HideConsoleAfterGameWindowAppears()
    {
        try
        {
            IntPtr consoleWindow = GetConsoleWindow();
            if (consoleWindow == IntPtr.Zero)
            {
                return;
            }

            uint processId = unchecked((uint)Process.GetCurrentProcess().Id);
            int attempts = ConsoleHideTimeoutMilliseconds / ConsoleHidePollMilliseconds;
            for (int attempt = 0; attempt < attempts; attempt++)
            {
                if (HasVisibleGameWindow(processId, consoleWindow))
                {
                    ShowWindowAsync(consoleWindow, ShowWindowHide);
                    Log.LogInfo("Game window detected; BepInEx console moved to the background.");
                    return;
                }
                Thread.Sleep(ConsoleHidePollMilliseconds);
            }
            Log.LogWarning("Timed out waiting for the game window; leaving the BepInEx console visible.");
        }
        catch (Exception exception)
        {
            // Console presentation is cosmetic. Never let it affect the
            // translation callback or game startup when Windows APIs fail.
            Log.LogWarning($"Could not auto-hide the BepInEx console: {exception.Message}");
        }
    }

    private static bool HasVisibleGameWindow(uint processId, IntPtr consoleWindow)
    {
        bool found = false;
        EnumWindows(
            (window, _) =>
            {
                if (window == consoleWindow
                    || !IsWindowVisible(window)
                    || GetWindow(window, GetWindowOwner) != IntPtr.Zero)
                {
                    return true;
                }

                GetWindowThreadProcessId(window, out uint windowProcessId);
                if (windowProcessId != processId)
                {
                    return true;
                }

                found = true;
                return false;
            },
            IntPtr.Zero);
        return found;
    }

    private delegate bool EnumWindowsCallback(IntPtr window, IntPtr parameter);

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetConsoleWindow();

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool EnumWindows(EnumWindowsCallback callback, IntPtr parameter);

    [DllImport("user32.dll")]
    private static extern IntPtr GetWindow(IntPtr window, uint command);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindowVisible(IntPtr window);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ShowWindowAsync(IntPtr window, int command);

    private static bool TrySplitRuntimeSuffix(string text, out string baseText, out string suffix)
    {
        baseText = text;
        suffix = "";
        Match match = RuntimeSuffix.Match(text);
        if (!match.Success || match.Index == 0)
        {
            return false;
        }
        baseText = text.Substring(0, match.Index).TrimEnd();
        suffix = match.Groups["suffix"].Value;
        return baseText.Length > 0;
    }

    private bool TryTranslateWithRuntimeSuffix(ITranslator active, string original,
        out string translation)
    {
        translation = "";
        if (!TrySplitRuntimeSuffix(original, out string baseText, out string suffix))
        {
            return false;
        }
        string? value = DynamicTranslations.LookupAny(baseText);
        if (string.IsNullOrWhiteSpace(value)
            && active.TryTranslate(baseText, out string baseTranslation)
            && !string.IsNullOrWhiteSpace(baseTranslation) && baseTranslation != baseText)
        {
            value = baseTranslation;
        }
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }
        char first = suffix.TrimStart()[0];
        bool needsSpace = value[value.Length - 1] is not (' ' or '(' or '[') && char.IsLetterOrDigit(first);
        translation = needsSpace ? value + " " + suffix.TrimStart() : value + suffix;
        return true;
    }

    private static bool TryTranslateSargonAgreement(string text, out string translation)
    {
        const string englishPrefix =
            "When any [Sargon] Operator activates a skill, all [Sargon] Operators " +
            "+12 ASPD (up to +300), lasting for ";
        const string englishDurationSuffix = " seconds (affected by no. of stacks)";
        const string englishEffectMarker =
            "Skill activations will also cause all [Sargon] Operators to gain " +
            "+12% ATK (up to +300%)";

        string duration;
        bool includesStrategy;
        if (text.StartsWith(englishPrefix, StringComparison.Ordinal)
            && text.Contains("<With 6 different [Sargon] Operators on ", StringComparison.Ordinal)
            && text.Contains(englishEffectMarker, StringComparison.Ordinal)
            && TryExtractDuration(
                text,
                englishPrefix.Length,
                englishDurationSuffix,
                out duration))
        {
            includesStrategy = text.Contains(
                "When using Narantuya's Strategy",
                StringComparison.Ordinal);
        }
        else
        {
            translation = string.Empty;
            return false;
        }

        translation =
            "【萨尔贡】干员开启技能时，所有【萨尔贡】干员攻击速度+12（至多+300），持续" +
            duration +
            "秒（受层数影响）\n" +
            "<在场6名不同【萨尔贡】干员>开启技能还会使所有【萨尔贡】干员攻击力+12%（至多+300%）";
        if (includesStrategy)
        {
            translation +=
                "\n选择策略【娜仁图亚】时，<在场6名不同【萨尔贡】干员>的效果会有所改变";
        }
        return true;
    }

    private static bool TryExtractDuration(
        string text,
        int startIndex,
        string suffix,
        out string duration)
    {
        int endIndex = text.IndexOf(suffix, startIndex, StringComparison.Ordinal);
        if (endIndex <= startIndex)
        {
            duration = string.Empty;
            return false;
        }

        duration = text.Substring(startIndex, endIndex - startIndex).Trim();
        if (!RuntimeNumber.IsMatch(duration))
        {
            duration = string.Empty;
            return false;
        }
        return true;
    }

    private static bool TryTranslateLines(ITranslator current, string text, out string translation)
    {
        string[] lines = text.Split('\n');
        if (lines.Length < 2)
        {
            translation = string.Empty;
            return false;
        }

        bool translatedAny = false;
        StringBuilder builder = new(text.Length);
        for (int index = 0; index < lines.Length; index++)
        {
            if (index > 0)
            {
                builder.Append('\n');
            }

            string line = lines[index].Trim();
            if (line.Length == 0)
            {
                continue;
            }
            if (!current.TryTranslate(line, out string translatedLine)
                || string.IsNullOrWhiteSpace(translatedLine))
            {
                // The popup uses one TMP component for two independently
                // templated lines, e.g. "(Currently held: 2)" followed by
                // "Are you sure you want to open 2 Firearms Workshop Giftbox?".
                // Neither line is an exact key, so fall back to macro rules
                // per line before giving up.
                string? dynamicLine = DynamicTranslations.LookupAny(line);
                if (string.IsNullOrWhiteSpace(dynamicLine))
                {
                    translation = string.Empty;
                    return false;
                }
                translatedLine = dynamicLine;
            }
            builder.Append(translatedLine);
            translatedAny = true;
        }
        translation = builder.ToString();
        return translatedAny;
    }
}
