# Translation files

One folder per target language. `build.py --language <code>` accepts every folder here that has a `language.json`.

```text
languages/<code>/
  language.json        settings (see below)
  translation/*.tsv    translations of the restored scenes, one table per scene (optional)
  interface.tsv        translation of the interface text in CARTAGRA.exe (optional)
  scene_titles.tsv     translation of the scene headings of the save and load screens (optional)
  images/<archive>/<entry>.png   interface pictures to translate (optional; not in git)
  images_text.json     the texts in the interface pictures and their translations, for tools/image_text.py (optional)
_original_jp/          the scene tables with the Japanese text only (see _original_jp/README.md)
_original_steam/en/    the Steam release's English interface (see _original_steam/README.md)
```

All tables are UTF-8 and tab-separated. Inside a cell, write a line break as `\n` and a tab as `\t`. The build reads the files here and writes copies of the tables in the current format to `build/<code>/`; it never writes into this folder.

## Restored scenes (`translation/*.tsv`)

The 24 restored scenes (the scenes Steam cut or rewrote, mostly the H-scenes) have one table each: `languages/<lang>/translation/<scene>.tsv`. Fill in the `translation` column and build again.

| Column | Meaning |
| --- | --- |
| `row` | Line number inside the scene |
| `kind` | `msg` (dialogue) or `select` (choice; options are separated by `$d`) |
| `voice` | Voice ID in the Japanese release (0 = no voice) |
| `jp` | Japanese original (do not edit) |
| `translation` | **The translation.** When it is not empty, the game shows it |

A row with an empty `translation` shows an identical line of the target release if there is one, otherwise the Japanese text.

Keep the engine markup: `@Name@` at the start sets the speaker name (for example `@Казуна@`), `$d` separates choices, `$[base$/ruby$]` is ruby text.

To start a new language, copy the tables from [_original_jp/](_original_jp/README.md) (Japanese text, empty `translation`), or build once and copy them from `build/<code>/translation/`. Tables in older formats (with `source` and `existing` columns, or `ru` instead of `translation`) are still read.

## Interface text (`interface.tsv`)

The interface text (options, confirmation dialogs, the save screen's months and slot number, music and ending titles, the start-up notice) is stored in `CARTAGRA.exe`. The Russian release left it in English.

| Column | Meaning |
| --- | --- |
| `id` | Position of the string in `CARTAGRA.exe` (do not edit) |
| `original` | The English text of the release (do not edit; the build checks it against your `CARTAGRA.exe`) |
| `translation` | **The translation.** When it is not empty, the game shows it instead of the original |

Keep the engine markup (`$A1`, `$d`, `$S(42)`, `$C(230,230,126)`) and the printf placeholders (`%d`, `%02d`, `%s`, `%%`) in the same order: the build stops if they differ. Leading and trailing spaces center short labels on their buttons. Labels have limited room in the game: check them in game.

Limits of the game's fonts (found in game):

- The interface font has no `«` and `»` (they show as blanks); use `❝` and `❞` (shown as “ ”), as the English text does.
- Some labels use the small font set `FONT1`, which has Latin letters only (the bottom bar, the slider labels, the version number, the save date). `font_glyphs` in `language.json` copies the needed letters into it.
- The large font set `FONT0` draws `№` as `No.`; `font_numero` in `language.json` redraws it as the Cyrillic sign.
- `BGM`, `SE` and `MOVIE` are not in the table: the same strings are script command names, so they stay English.

To translate the interface into another language, copy [_original_steam/en/interface.tsv](_original_steam/en/interface.tsv) to `languages/<code>/interface.tsv`. The table fits only the `CARTAGRA.exe` of the Steam release (its checksum is in `definitions/inputs.json`). `python -m cartagra_patch.exe_text check <exe> <table>` checks a table against an executable; `python -m cartagra_patch.exe_text list <exe>` lists every string the code refers to.

## Scene headings (`scene_titles.tsv`)

The heading above the text preview on the save and load screens (`Feb. 10`, `Chapter 1`) is stored in `SCRIPT.PAK`, not in the executable. The table has two columns, `original` (the English text) and `translation`; the Russian table has 31 rows. The build stops if an `original` is not in the release. Saves keep the heading they were made with.

## Interface pictures (`images/`)

Some interface elements are pictures with English text (title menu, Extras headings, options tabs, system menu, buttons, screen headings, date labels, "Jump" indicators, key names, manual pages: 140 pictures). [_original_steam/en/images.tsv](_original_steam/en/images.tsv) lists them. The build changes only the ones you replace:

1. Export the originals once: `python build.py --language <code> --export-images`. This writes them as PNG to `_original_steam/en/images/<archive>/<entry>.png` and copies the missing ones to `languages/<code>/images/` (existing copies are kept). `<archive>` is the archive path below `files/image/` without `.PAK`, for example `resident/PARTS` or `SYSCG`.
2. Edit the copies in `languages/<code>/images/`. Keep their size and save them as 8-bit PNG (RGBA is best). Leave `_original_steam/en/images/` unchanged: the build compares against it.
3. Build. Changed pictures are written into their archives in `dist/<code>/files/image/...`.

For Russian the pictures are made by a script: `languages/ru/images_text.json` lists every English text with its place and translation, and

```bash
python tools/image_text.py --language ru --fonts <folder with EBGaramond.ttf>
```

renders the translations into copies of the originals with the same look (28 pictures). It needs `pip install pillow numpy scipy opencv-python-headless`, [EB Garamond](https://github.com/google/fonts/tree/main/ofl/ebgaramond) (saved as `EBGaramond.ttf`) and Arial. `--compare <folder>` writes comparison sheets for checking by eye.

Any other picture can be replaced the same way: export it with `python -m cartagra_patch.cztool export <archive.PAK> <folder> <entry>` and put the edited PNG in `languages/<code>/images/<archive>/`. The PNG files are not committed to git: they are the game's art.

## `language.json`

| Key | Meaning |
| --- | --- |
| `code` | Language code; must equal the folder name |
| `name` | Display name |
| `target` | Input set of the release this language patches (a key of `sets` in `definitions/inputs.json`) |
| `target_description` | Release description, copied into `BUILD_INFO.txt` |
| `status` | `complete`, `incomplete` (works, but parts are missing) or `untested` (never verified) |
| `status_note` | One sentence on what is missing or unverified, shown by the build and in `BUILD_INFO.txt` |
| `placeholder` | What untranslated lines show |
| `interface_original` | Optional. Folder below `languages/` with the originals of the target release's interface (`_original_steam/en`): `build.py --export-images` writes the pictures there, and the build replaces only pictures that differ from them |
| `font_glyphs` | Optional. Letters to copy from the game's large fonts (FONT0) into its small interface fonts (FONT1), which have Latin letters only; needed when translated labels drawn with FONT1 (bottom bar, slider labels, save date) use other letters. The build then writes `files/font_win32_1920/FONT1__INFO.PAK` and `FONT1_*.PAK` |
| `exe_original_text` | Optional (`true`, set for `en`). Remove a translation another release added to `CARTAGRA.exe` (the Russian release's `.rtransl` section, see `definitions/restoration.json`), so the executable shows its original English text; an executable without it is used as it is |
| `font_numero` | Optional (`true`). Redraw the large fonts' `№`, which has the Japanese shape (`No.`), as the Cyrillic sign; the save and load screens show the slot number with it when the interface table translates `No.%d` as `№%d`. The build then writes `files/font_win32_1920/FONT0__INFO.PAK` and `FONT0_*.PAK` (about 80 MB) |

## Adding a language

The `_original_*` folders are not languages; they hold starting points:

- `_original_jp/`: the 24 scene tables with the Japanese text only. See [_original_jp/README.md](_original_jp/README.md).
- `_original_steam/en/`: the English interface of the Steam release (the interface table, the list of pictures with text, the exported pictures). See [_original_steam/README.md](_original_steam/README.md).

Steps: add the release's input set to `definitions/inputs.json`, create `languages/<code>/language.json` with `status` `untested`, copy the scene tables from `_original_jp/` to `languages/<code>/translation/` and, if the interface is translated, `_original_steam/en/interface.tsv` to `languages/<code>/interface.tsv` (set `interface_original` to `_original_steam/en` and run `build.py --language <code> --export-images` for the pictures). Build, and test in game before marking it `incomplete` or `complete`.
