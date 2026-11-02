# Cartagra Cut Content Restoration Patch

Restores what the Steam release of **Cartagra ~Tsuki kurui no Yamai~ REBIRTH FHD SIZE EDITION** censored: 24 cut or rewritten scenes, 150 CGs, 1,901 voice clips and 51 edited pictures. The uncensored content comes from the Japanese FHD 2023 release. The Russian build also translates the interface that the Russian release left in English.

The patch contains no game files: you build it on your own computer from your own copies of the game. What exactly the patch changes, all build options, the test status and the known issues are in [TECHNICAL_NOTES.md](TECHNICAL_NOTES.md#patch-contents-and-usage). The working journal is [MODLOG.md](MODLOG.md).

## Building the Patch

You need Python 3.8 or newer (no extra packages), about 7 GB of free space, the Japanese FHD 2023 release and the release you want to patch.

**1. Copy the game files** into `inputs/` (the build never reads your game folder). Run from the project folder in `cmd.exe`, with your own paths:

```bat
robocopy "D:\Games\Cartagra-2023-JP\files" "inputs\jp-fhd\files" SCRIPT.PAK
robocopy "D:\Games\Cartagra-2023-JP\files\image" "inputs\jp-fhd\files\image" /E
robocopy "D:\Games\Cartagra-2023-JP\files\voice" "inputs\jp-fhd\files\voice" /E

robocopy "D:\Games\Cartagra-2026-RU-Steam" "inputs\ru-steam" CARTAGRA.exe
robocopy "D:\Games\Cartagra-2026-RU-Steam\files" "inputs\ru-steam\files" SCRIPT.PAK
robocopy "D:\Games\Cartagra-2026-RU-Steam\files\image" "inputs\ru-steam\files\image" /E
robocopy "D:\Games\Cartagra-2026-RU-Steam\files\voice" "inputs\ru-steam\files\voice" /E
robocopy "D:\Games\Cartagra-2026-RU-Steam\files\font_win32_1920" "inputs\ru-steam\files\font_win32_1920" /E
```

For the English Steam release, use the same commands as for the Russian release but with `inputs\en-steam` instead of `inputs\ru-steam`. The files must be unmodified originals of that release, not files from a game folder the patch is already installed in. Each build checks them against [definitions/inputs.json](definitions/inputs.json) first. `--check` runs only that check.

**2. Build:**

| Release | Command | What the patch contains | Status |
| --- | --- | --- | --- |
| Russian 2026 release by Innocence translations and The Hounds of God (Steam) | `python build.py --language ru` | The restored scenes, CGs, voices and pictures, all translated into Russian; the Russian interface; a crash fix; the Japanese game start | Incomplete: tested in game, but most restored lines not yet checked in game |
| English Steam release | `python build.py --language en` | The restored scenes, CGs, voices and pictures, with the restored lines in Japanese where the release has no English line; the same crash fix and game start. No translation: the executable keeps (or gets back) its original English text | Untested: never built with the English files |

The patch is written to `dist/<language>/`. `BUILD_INFO.txt` there lists every file and where it goes.

**3. Install** by hand. First back up the game files that `BUILD_INFO.txt` lists, and your saves (`%APPDATA%\GSE Saves\4290390` for the Russian release). Then copy the contents of `dist/<language>/` into the game folder, replacing the files there. To switch a game folder from one language's patch to another, first put back the original files that the old patch's `BUILD_INFO.txt` lists: the `en` patch replaces fewer files than `ru`, so the Russian pictures and fonts would stay.

## Translation Files

Everything translatable is in `languages/<language>/`. [languages/README.md](languages/README.md) describes every file and its columns.

| File | What it translates |
| --- | --- |
| `translation/<scene>.tsv` | The lines of the 24 restored scenes (the hentai scenes), one table per scene |
| `interface.tsv` | The interface text in `CARTAGRA.exe` (menus, options, dialogs, music and ending titles) |
| `scene_titles.tsv` | The scene headings on the save and load screens (`Feb. 10` → «10 февраля») |
| `images/`, `images_text.json` | The interface pictures with English text |
| `language.json` | The language's settings, for example the letters to add to the game's fonts |

**To translate the restored scenes:**

1. Start from the Japanese tables in [languages/_original_jp/](languages/_original_jp/README.md), or from the tables a build writes to `build/<language>/translation/`. Put them in `languages/<language>/translation/`.
2. Fill in the `translation` column. Leave `jp` unchanged. Keep the markup: `@Name@` sets the speaker, `$d` separates choices, `\n` is a line break.
3. Build again. Rows left empty show the same line from the release if it has one, otherwise the Japanese text.

To add a new language, see [languages/README.md](languages/README.md#adding-a-language).

## Sources

- [VNDB: Cartagra](https://vndb.org/v515)
- [Steam: CARTAGRA](https://store.steampowered.com/app/4290390/CARTAGRA/)
- [Chinese patch (lzacg)](https://lzacg.cc/7683) and its source code, [HIllya51/Cartagra_FHD_CHS](https://github.com/HIllya51/Cartagra_FHD_CHS), used as a reference for the file formats
- [Russian release (ruvn)](https://s.ruvn.org/novels/cartagra-tsuki-kurui-no-yamai). Russian translation: [Innocence translations](https://t.me/innocence_translations) and [The Hounds of God](https://vk.ru/thgteam)

## Disclaimer

This patch is only for owners of legitimate copies of the game. Do not share the contents of `inputs/`, `build/` or `dist/`, or the translation tables, because they contain game text. Use at your own risk.
