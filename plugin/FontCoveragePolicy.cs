using System;
using System.Linq;
using System.Text;

namespace ArknightsLocalization.RichTextFix;

// EN client faces (Unity 2021.3.39f1) checked for Cyrillic: Novecentowide-Normal/-Bold,
// AEwide, JovannyLemonad-Bender, Dosis-Regular/-Bold, Arvo-Bold, GroovyScript(Extrude) and
// ADDWB__ have none, SourceHanSansCN-Heavy only part of it. "-Bold"/"-Heavy"/"-Black" faces
// get the heavy replacement, every other face the regular one. The EN 方正特雅宋_GBK face
// already covers Cyrillic, so the Song replacement is rarely needed.
internal static class FontCoveragePolicy
{
    internal const string MediumName = "NotoSansHans-Medium";
    internal const string HeavyName = "SourceHanSansCN-Heavy";

    // TMP can name a font after its asset or report the source font family.
    internal static string? ExactReplacementName(string? name)
    {
        if (name == null) return null;
        if (name.EndsWith(" SDF", StringComparison.OrdinalIgnoreCase) ||
            name.EndsWith("-SDF", StringComparison.OrdinalIgnoreCase) ||
            name.EndsWith("_SDF", StringComparison.OrdinalIgnoreCase))
            name = name[..^4];
        if (name.Equals(MediumName, StringComparison.OrdinalIgnoreCase) ||
            name.Equals("Noto Sans S Chinese Medium", StringComparison.OrdinalIgnoreCase))
            return MediumName;
        if (name.Equals(HeavyName, StringComparison.OrdinalIgnoreCase) ||
            name.Equals("Source Han Sans CN Heavy", StringComparison.OrdinalIgnoreCase))
            return HeavyName;
        return null;
    }

    internal static bool PreferSong(string? name) => name != null &&
        (name.Contains("方正特雅宋", StringComparison.Ordinal) || name.Contains("FZTeYaSong", StringComparison.OrdinalIgnoreCase));

    internal static bool PreferHeavy(string? name) => name != null &&
        (name.EndsWith("-Heavy", StringComparison.OrdinalIgnoreCase)
         || name.EndsWith("-Bold", StringComparison.OrdinalIgnoreCase)
         || name.EndsWith("-Black", StringComparison.OrdinalIgnoreCase));

    // True when the text needs the replacement face: it contains Cyrillic (or Han) letters
    // and the current face lacks at least one glyph the text uses. The method keeps its
    // original name because several call sites share it.
    internal static bool NeedsCnFont(string text, Func<int, bool> hasGlyph)
    {
        string visible = RichTextStyleRestorer.PlainText(text);
        // Numeric counters, English names, abbreviations and icon fonts keep
        // their original face. Markup attributes are not visible characters.
        if (!visible.EnumerateRunes().Any(rune => IsCyrillic(rune.Value) || IsHan(rune.Value))) return false;
        foreach (Rune rune in visible.EnumerateRunes())
            if (NeedsGlyph(rune.Value) && !hasGlyph(rune.Value)) return true;
        return false;
    }

    private static bool NeedsGlyph(int code) => IsCyrillic(code) || IsHan(code) || IsRussianPunctuation(code)
        || code is >= 0x3000 and <= 0x303f or >= 0xff01 and <= 0xff65;

    internal static bool IsCyrillic(int code) => code is >= 0x0400 and <= 0x052f or >= 0x1c80 and <= 0x1c8f
        or >= 0x2de0 and <= 0x2dff or >= 0xa640 and <= 0xa69f;

    // Marks used in Russian text that Latin-only game faces may lack: « » – — “ ” „ … №
    private static bool IsRussianPunctuation(int code) => code is 0x00ab or 0x00bb or 0x2013 or 0x2014
        or 0x201c or 0x201d or 0x201e or 0x2026 or 0x2116;

    private static bool IsHan(int code) => code is >= 0x3400 and <= 0x4dbf or >= 0x4e00 and <= 0x9fff
        or >= 0xf900 and <= 0xfaff or >= 0x20000 and <= 0x323af;
}
