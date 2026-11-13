# Russian_Build_Arknights

Скрипты и исходники, которыми собирается русская локализация Arknights EN:
XUnity-пак текста, контекстный словарь RichTextFix, динамические шаблоны
и сам плагин `ArknightsLocalization.RichTextFix`.

## Что лежит в репозитории

| Путь | Назначение |
| --- | --- |
| `build.ps1` | Полный конвейер сборки: глоссарий → карта переводов → динамические шаблоны → XUnity-пак → контекст → DLL → ZIP → установка. |
| `build.config.json` | Пути и версия. Перед запуском замените `python`, `game`, `gameInterop`. |
| `tools/import_glossary.py` | Импорт глоссария оперативников и терминов. |
| `tools/build_story_names.py` | Имена говорящих для сюжета. |
| `tools/build_ru_merged_pack.py` | Слияние всех RU-источников в `merged-manifests/99_merged.json`; здесь же вызывается восстановление rich-тегов. |
| `tools/rich_tags.py` | Возвращает потерянные `<@ba.*>`-теги (цвет значений) и только их: `$`-подсказки и `@char.*` в обычных `Text` ломают вёрстку. |
| `tools/build_skill_direct.py` | Прямые переводы навыков и модулей. |
| `tools/build_dynamic_templates.py` | Шаблоны с макросами (`{atk_scale}`, `{0}` и т.п.) для плагина. |
| `tools/build_ru_context_merged.py` | Собирает `context_translations.json.gz` для плагина. |
| `tools/build_rich_styles.py` | Таблица стилей `<@...>`/`<$...>` из CN-клиента. |
| `tools/build_cn_display_font.py`, `tools/build_ru_font_bundle.py`, `tools/build_tmp_shader.py` | Шрифтовой бандл и TMP-шейдер. |
| `tools/package_merged_hook.py` | Сборка ZIP-релиза. |
| `tools/contract_test.py` | Проверка целостности пака. |
| `arklocalizer/` | Сборщик XUnity-пака (`build-custom-pack`). |
| `plugin/` | Исходники C#-плагина RichTextFix. |
| `docs/PLUGIN_README_RU.md` | Русский перевод документации плагина (шрифты, rich-текст, контекст, сборка). |

## Чего в репозитории нет

Исходные данные перевода слишком большие и/или содержат сторонние материалы,
поэтому они не коммитятся. Положите их рядом со скриптами:

```
ru-manifests/            новые переводы (gap-fill, *.json)
ru-manifests-all/99_all.json  базовая карта
ru-overrides/            точечные правки (00_fixes.json применяется последним)
RUKAMI/*.txt             ручные правки
glossary/                глоссарий
work/translated_1-521504.tsv  исходный TSV
runtime/                 AutoTranslatorConfig.ini, sharedassets1.assets,
                         en-zh-offline-final/arknights_cn_notosanshans
```

Дополнительно нужен `D:\ARKRUBUILD3\ru_txt` — вычитанный вручную RU-источник.
Путь задан константой `FRIEND_RU_TXT` в `tools/build_ru_merged_pack.py`.

## Сборка

```powershell
# 1. Зависимости
py -m pip install -r requirements.txt

# 2. Интероп-сборки игры: запустите игру один раз с BepInEx,
#    появится <game>/BepInEx/interop.

# 3. Полная сборка и установка
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -Force -Install
```

Без `-Install` собирается только ZIP в `dist/`. `-SkipTests` пропускает
`contract_test.py`.

## Важные правила

- `ru_txt` из BUILD4 не импортируется: источник — `D:\ARKRUBUILD3\ru_txt`.
- Новые переводы кладутся в `ru-manifests/ru_fill_*.json`.
- Точечные исправления — в `ru-overrides/00_fixes.json`, он применяется последним.
- `ambiguous.json` исключён из сборки.
- Постбоевые реплики переносятся по `tools/voice_line_keys.json` (лимит строки 54).
- rich-теги: восстанавливаются только `<@ba.*>`. Не добавляйте обратно `$...`
  и `@char.*`/`@lv.*` — в панелях с обычным `Text` они показываются сырым
  `<color=...>` или создают ложные подсказки.
- Плагин не создаёт компоненты и не включает ссылки насильно: если игра
  отрисовала строку обычным `Text`, остаётся только цвет.
