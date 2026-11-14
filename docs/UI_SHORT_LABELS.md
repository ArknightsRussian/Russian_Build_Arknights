# Short UI labels and canon fixes

The 1.0.42 build tightens labels that did not fit their Arknights UI slots and
fixes several canon names that the community glossary did not cover.

## Exact overrides

`ru-overrides/09_short_ui.json` holds the hand-picked labels:

| English key | Old RU | New RU |
|---|---|---|
| `Challenge Mode` | Режим испытания | Испытание |
| `Enemy Info` | Информация о враге | О враге |
| `Facility Info` | Информация о помещении | О помещении |
| `Building Mode` | Режим строительства | Строительство |
| `Guaranteed` | Гарантированно | Гарант. |
| `Use Drones` | Использовать дроны | Дроны |
| `Precious Metal Order` | Заказ драгоценных металлов | Заказ |
| `Originium Order` | Ориджиниевый приказ | Приказ |
| `Set as default` | Установить по умолчанию | Установить |
| `Intel Squad` | Разведывательный отряд | Разведка |
| `Tap a room to view details` | Нажмите на комнату, чтобы посмотреть детали | Нажмите на комнату |
| `Very Rare` | Очень редкий | Оч. редк. |
| `Building Materials` | Стройматериалы | Стройматериал |
| `Material` / `Upgrade Materials` | Материалы | Материал |
| `Precious Metals` | Драгоценные металлы | Металл |
| `Originium Materials` | Материалы из Ориджиния | Материал |
| `Orundum` | Ориджиниум | Орундум |
| `Originite Prime` | Чистый ориджиний | Чистый орундум |
| `Clear 17-13 to obtain this Operator` | — | Пройдите 17-13, чтобы получить этого Оперативника |

## Pattern rewrites

`tools/ui_short.py` runs in both the merged-manifest build and the XUnity pack
build, so overrides and story rows appended later are covered too.

* `Иммунитет к X` -> `НЕУЯЗ. X` for short enemy-resistance labels, with the
  status abbreviated (`Оглуш.`, `Замор.`, `Замедл.`, `Левит.`, ...).
* `Элитный N` -> `Элита N` for promotion/level labels.
* Declined `Монста` -> indeclinable `Мон3тр`.
* `нейросеть` family -> `нейромодуль` family (context-aware forms).
* `L.G.D.` / `L. G. D.` -> `Д.О.Л.`.
* `СОМ`/`СОП` next to `{magic_resistance}` -> `СОПР`.
* Latin `HP` -> `ХП`, `ATK` -> `АТК` in every translated value.

## Medals and bulleted rows

The game prefixes medal conditions and some mission rows with a generated
bullet (`-`, `–`, `—`, `−`, `•`, `·`). The exact translation key therefore
never matched. `RichTextTranslationPlugin` now strips the bullet, looks the body
up through the static dictionary and the macro-template index, and restores the
bullet. It also normalizes typographic dashes before the lookup and strips the
runtime `(0/1)` counter. This covers the medal conditions and the
`Clear ... to obtain this Operator` reward rows.
