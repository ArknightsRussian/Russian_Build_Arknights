using System;
using System.Reflection;
using BepInEx.Logging;
using HarmonyLib;
using UnityEngine;
using UnityEngine.UI;

namespace ArknightsLocalization.RichTextFix;

// The post-battle VOICE banner (Torappu.UI.BattleFinish.BattleFinishIllustView)
// draws a single UnityEngine.UI.Text. Its horizontal overflow is left at
// "Overflow" by the game, so a line longer than the plate is clipped at the
// right edge; the game's own _ProcessCharWordLineSplitting helpers are not
// applied to Russian text.
//
// The map already contains explicit breaks for every result line
// (charword_table THREE_STAR/TWO_STAR/FOUR_STAR/LOSE, <=54 characters). This
// patch is the runtime safety net: it forces Wrap/vertical overflow, clamps the
// label width to the banner container when the label is wider, and logs the
// real box size at mesh-generation time (Render runs before layout, where the
// rect is still 0x0).
internal static class BattleFinishWrap
{
    private const string ViewTypeName = "Torappu.UI.BattleFinish.BattleFinishIllustView";
    private static readonly BindingFlags Instance =
        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

    private static PropertyInfo? illustTextField;
    private static PropertyInfo? illustTextContainerField;
    private static ManualLogSource? log;
    private static bool enabled;

    private static Text? banner;
    private static int bannerId;
    private static RectTransform? container;
    private static string? lastLogged;
    private static int logBudget = 12;

    internal static void Enable(ManualLogSource logger)
    {
        if (enabled) return;
        log = logger;
        Type? view = AccessTools.TypeByName(ViewTypeName);
        if (view == null)
        {
            log.LogWarning($"BattleFinish wrap: {ViewTypeName} not found");
            return;
        }
        illustTextField = view.GetProperty("_illustText", Instance);
        illustTextContainerField = view.GetProperty("_illustTextContainer", Instance);
        MethodInfo? render = AccessTools.Method(view, "Render");
        if (illustTextField == null || render == null)
        {
            log.LogWarning("BattleFinish wrap: Render/_illustText not found");
            return;
        }
        Harmony harmony = new("arklocalizer.battlefinish.wrap");
        harmony.Patch(render, postfix: new HarmonyMethod(typeof(BattleFinishWrap), nameof(AfterRender)));
        MethodInfo? populate = AccessTools.Method(typeof(Text), "OnPopulateMesh", new[] { typeof(VertexHelper) });
        if (populate != null)
        {
            harmony.Patch(populate, prefix: new HarmonyMethod(typeof(BattleFinishWrap), nameof(BeforePopulate)));
            log.LogInfo("BattleFinish wrap: Render + OnPopulateMesh hooks installed");
        }
        else
        {
            log.LogInfo("BattleFinish wrap: Render hook installed (OnPopulateMesh not found)");
        }
        enabled = true;
    }

    private static void AfterRender(object __instance)
    {
        try
        {
            if (__instance == null || illustTextField == null) return;
            if (illustTextField.GetValue(__instance) is not Text text) return;
            banner = text;
            bannerId = text.GetInstanceID();
            if (illustTextContainerField?.GetValue(__instance) is Transform transform)
                container = transform.TryCast<RectTransform>();
            Apply(text);
        }
        catch (Exception exception)
        {
            log?.LogWarning($"BattleFinish wrap failed: {exception}");
        }
    }

    private static void BeforePopulate(Text __instance)
    {
        try
        {
            if (__instance == null || banner == null) return;
            if (__instance.GetInstanceID() != bannerId) return;
            Apply(__instance);
            LogOnce(__instance);
        }
        catch (Exception exception)
        {
            log?.LogWarning($"BattleFinish wrap failed: {exception}");
        }
    }

    private static void Apply(Text text)
    {
        if (text.horizontalOverflow != HorizontalWrapMode.Wrap)
            text.horizontalOverflow = HorizontalWrapMode.Wrap;
        if (text.verticalOverflow != VerticalWrapMode.Overflow)
            text.verticalOverflow = VerticalWrapMode.Overflow;
        // Keep the original size when the text fits; shrink only up to 70% when
        // even wrapped text cannot fit the box.
        if (!text.resizeTextForBestFit)
        {
            int size = text.fontSize;
            text.resizeTextMaxSize = size;
            text.resizeTextMinSize = Math.Max(12, size * 7 / 10);
            text.resizeTextForBestFit = true;
        }
        // [УДАЛЕНО СКРИПТОМ] Блок принудительного сжатия ширины удален, чтобы текст заполнял плашку.
    }

    private static void LogOnce(Text text)
    {
        string value = text.text ?? "";
        if (value.Length == 0 || value == lastLogged || logBudget <= 0) return;
        lastLogged = value;
        logBudget--;
        Rect rect = text.rectTransform.rect;
        Rect? outer = container != null ? container.rect : null;
        string[] lines = value.Split('\n');
        int first = lines.Length > 0 ? lines[0].Length : 0;
        int longest = 0;
        foreach (string line in lines) longest = Math.Max(longest, line.Length);
        log?.LogInfo(
            $"BattleFinish voice text: lines={lines.Length}, first={first}, longest={longest}, " +
            $"wrap={text.horizontalOverflow}, vertical={text.verticalOverflow}, " +
            $"bestFit={text.resizeTextForBestFit}, fontSize={text.fontSize}, " +
            $"box={rect.width:0}x{rect.height:0}, " +
            $"container={(outer.HasValue ? $"{outer.Value.width:0}x{outer.Value.height:0}" : "?")}, " +
            $"canvas={Screen.width}x{Screen.height}, parent={text.transform.parent?.name}");
    }
}
