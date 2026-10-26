# Cartagra Cut Content Restoration Patch

A patch that restores the content the Steam release of **Cartagra ~Tsuki kurui no Yamai~ REBIRTH FHD SIZE EDITION** censored: 24 cut or rewritten scenes, 150 CGs, 1,901 voice clips and 51 edited pictures. The source of the restored content is the uncensored Japanese FHD release.

The patch contains no game files. You build it on your own computer from your own copies of the game.

Technical details, file formats and reverse-engineering notes are in [TECHNICAL_NOTES.md](TECHNICAL_NOTES.md). The working journal is [MODLOG.md](MODLOG.md).

## Languages

| Language | Build command | Target release | Status |
| --- | --- | --- | --- |
| Russian (`ru`) | `python build.py --language ru` | Russian 2026 release by Innocence translations and The Hounds of God (Steam build) | **Incomplete.** Built and tested in game. All 4,422 restored lines are translated; 3,970 of them were added on 2026-10-26 and have not been checked in game yet |
| English (`en`) | `python build.py --language en` | English Steam release | **Untested.** Never built: the English Steam files were not available. It may not work at all |

`python build.py --list-languages` shows the same list. Each build writes its status into `BUILD_INFO.txt` next to the patch files.

## What the Patch Restores

| Content | Details |
| --- | --- |
| Scenes | 20 scenes that Steam rewrote are replaced by the uncensored versions; 4 removed scenes are added back |
| Game start | New Game plays the prologue (narration over CGs, no interface) and the opening movie again before the first scene, as in the Japanese release. Steam had moved both to just before the second part; the Rengoku movie goes back there, as in the Japanese release. The game's own Russian prologue text and movie files are used |
| CGs | 150 event CGs that Steam removed |
| Edited pictures | 51 pictures that Steam edited (clothes added, blood, wounds and bodies hidden) are replaced by the originals |
| Voices | 1,901 voice clips of the restored scenes |
| Text | Restored lines use the language's translation tables, then the existing translation where the same line exists elsewhere in the game; lines with neither show the Japanese text |
| Interface (Russian) | The menus, options, dialogs, music and ending titles that the Russian release left in English are translated into Russian (277 of 296 strings in `CARTAGRA.exe`; tested in game). Interface elements that are pictures stay English; you can replace them with your own (see [Translating the Interface](#translating-the-interface)) |

The patch replaces these files of the game:

| File | Approximate size |
| --- | --- |
| `CARTAGRA.exe` | 7 MB (only when the language translates the interface; `ru` does) |
| `files/SCRIPT.PAK` | 6 MB |
| `files/image/EVENTCG.PAK` | 569 MB |
| `files/image/OTHCG.PAK` | 340 MB |
| `files/voice/VOICE.PAK` | 807 MB |

Replacement images add the archives they belong to (for example `files/image/resident/PARTS.PAK`).

## Requirements

- The game release you want to patch (the Russian 2026 release by Innocence translations and The Hounds of God, or the English Steam release).
- The Japanese FHD release v1.1 (also the version the Chinese fan patch installs over). Needed only to build the patch.
- Python 3.8 or newer. No extra packages are needed; installing `xxhash` (`pip install xxhash`) makes the build a little faster.
- About 6 GB of free space: 4.6 GB for the input copies and 1.7 GB for the output.

## Step 1: Provide the Input Files

The build never reads from your game installation. Copy the needed files from the `files/` folder of each release into the project's `inputs/` folder, keeping the subfolders:

```text
inputs/
  jp-fhd/files/      Japanese FHD release v1.1
  ru-steam/files/    Russian 2026 release by Innocence translations and The Hounds of God (for --language ru)
  ru-steam/CARTAGRA.exe   the game's executable, from the game folder itself (for the interface translation)
  en-steam/files/    English Steam release     (for --language en)
```

The files must be **unmodified originals**. If the patch is already installed in your game, take the files from your backup instead.

| Input set | Files |
| --- | --- |
| `jp-fhd` | `SCRIPT.PAK`; `image/`: `BGCG.PAK`, `CHARCG.PAK`, `EVENTCG.PAK`, `EVENTCG_SAVE.PAK`, `OTHCG.PAK`, `PARTS.PAK`, `SYSCG.PAK`, `SYSCG2.PAK`; `voice/`: `SYSVOICE.PAK`, `VOICE0.PAK`, `VOICE1.PAK` |
| `ru-steam`, `en-steam` | `SCRIPT.PAK`; `image/`: `BGCG.PAK`, `CHARCG.PAK`, `EVENTCG.PAK`, `MANUAL.PAK`, `MANUAL_DECK.PAK`, `OTHCG.PAK`, `SYSCG.PAK`, `SYSCG2.PAK`; `voice/`: `SYSVOICE.PAK`, `VOICE.PAK`. Also `../CARTAGRA.exe` (the game folder's executable, next to `files/`) when the language translates the interface, and `image/resident/PARTS.PAK` only if you replace pictures from it |

The exact sizes and checksums are listed in [definitions/inputs.json](definitions/inputs.json). The English file list is an assumption (the same as the Russian one); nobody has checked it.

Example for Windows `cmd.exe`, run from the project folder (replace the game paths with yours):

```bat
robocopy "D:\Games\Cartagra_FHD\files" "inputs\jp-fhd\files" SCRIPT.PAK
robocopy "D:\Games\Cartagra_FHD\files\image" "inputs\jp-fhd\files\image" BGCG.PAK CHARCG.PAK EVENTCG.PAK EVENTCG_SAVE.PAK OTHCG.PAK PARTS.PAK SYSCG.PAK SYSCG2.PAK
robocopy "D:\Games\Cartagra_FHD\files\voice" "inputs\jp-fhd\files\voice" SYSVOICE.PAK VOICE0.PAK VOICE1.PAK
robocopy "D:\Games\Cartagra2023RUS\files" "inputs\ru-steam\files" SCRIPT.PAK
robocopy "D:\Games\Cartagra2023RUS\files\image" "inputs\ru-steam\files\image" BGCG.PAK CHARCG.PAK EVENTCG.PAK MANUAL.PAK MANUAL_DECK.PAK OTHCG.PAK SYSCG.PAK SYSCG2.PAK
robocopy "D:\Games\Cartagra2023RUS\files\voice" "inputs\ru-steam\files\voice" SYSVOICE.PAK VOICE.PAK
robocopy "D:\Games\Cartagra2023RUS" "inputs\ru-steam" CARTAGRA.exe
```

Then check them:

```bash
python build.py --language ru --check
```

The check reports every missing file and every file that does not match the original release (for example a file that is already patched).

Instead of copying, you can point the build at other folders with `--jp-files DIR` and `--target-files DIR`, or at another `inputs` folder with `--inputs DIR`. The build only reads these folders. Do not point it at your game installation if the patch is installed there.

## Step 2: Build

```bash
python build.py --language ru
```

The build takes under a minute. It shows each step and finishes with the location of the patch. When something is wrong, it stops with a message that starts with `error:` and an exit code other than 0.

| Option | Effect |
| --- | --- |
| `--language ru` / `en` | Language to build (required) |
| `--check` | Only check the input files |
| `--export-images` | Export the interface pictures as PNG for translation (see [Interface pictures](#interface-pictures)) |
| `--list-languages` | Show the languages and their status |
| `--skip-checksums` | Skip the checksum check of the inputs (faster; sizes are still checked) |
| `--no-voice` | Do not build `VOICE.PAK` (the restored lines play without voice) |
| `--help` | Show all options |

Options for testing only: `--scenes SCENE ...` restores only the named scenes (output in `dist/<lang>-partial/`); `--test-start SCENE` makes New Game jump straight into a scene, and `--test-set VAR=VALUE` sets game variables first (output in `dist/<lang>-test/`). Never install these builds for normal play.

### Output

```text
dist/ru/
  BUILD_INFO.txt     language, status, and the destination and checksum of each file
  CARTAGRA.exe       the executable with the translated interface
  files/SCRIPT.PAK
  files/image/EVENTCG.PAK
  files/image/OTHCG.PAK
  files/voice/VOICE.PAK
```

Intermediate files go to `build/ru/`. `dist/ru/` is replaced only when a build succeeds. Building twice from the same inputs gives identical files.

## Step 3: Install

The build does not install anything. Install by hand:

1. Back up the original files from your game folder (`CARTAGRA.exe`, and in `files/`: `SCRIPT.PAK`, `image/EVENTCG.PAK`, `image/OTHCG.PAK`, `voice/VOICE.PAK`) and your saves. Keep the backups somewhere safe. The input copies in `inputs/` also work as a backup.
2. Copy the contents of `dist/ru/` into the game folder and replace the files: `CARTAGRA.exe` goes next to the game's `CARTAGRA.exe`, and `files/` into the game's `files/` folder. `BUILD_INFO.txt` lists the destination of each file.
3. Start the game.

Example for `cmd.exe` (replace the game path):

```bat
robocopy "dist\ru" "D:\Games\Cartagra2023RUS" /E /XF BUILD_INFO.txt
```

**Saves:** saves made inside one of the restored scenes, or inside the scripts `0216-04-03`, `0216-05-02`, `0217-01-04`, `0217-99-03`, `0208-15-00` and `0210-07-00` (the patch changes them slightly), may not load correctly after installing or removing the patch. Saves made elsewhere are not affected. The Russian release keeps its saves in `%APPDATA%\GSE Saves\4290390`; back that folder up before installing.

## Removing the Patch

Copy the original files back into the game folder, for example from the input copies:

```bat
robocopy "inputs\ru-steam" "D:\Games\Cartagra2023RUS" CARTAGRA.exe
robocopy "inputs\ru-steam\files" "D:\Games\Cartagra2023RUS\files" SCRIPT.PAK
robocopy "inputs\ru-steam\files\image" "D:\Games\Cartagra2023RUS\files\image" EVENTCG.PAK OTHCG.PAK
robocopy "inputs\ru-steam\files\voice" "D:\Games\Cartagra2023RUS\files\voice" VOICE.PAK
```

If an old version of this patch installed `EVENTCG_SAVE.PAK` into `files\image\`, delete it too. If you installed replacement images, copy their original archives back as well (for example `files\image\resident\PARTS.PAK`).

## Translating the Restored Scenes

Each restored scene has a table in `languages/<lang>/translation/<scene>.tsv` (UTF-8, tab-separated). Fill in the `translation` column and build again. A row with an empty `translation` shows an identical line of the target release if there is one, otherwise the Japanese text.

| Column | Meaning |
| --- | --- |
| `row` | Line number inside the scene |
| `kind` | `msg` (dialogue) or `select` (choice; options are separated by `$d`) |
| `voice` | Voice ID in the Japanese release (0 = no voice) |
| `jp` | Japanese original (do not edit) |
| `translation` | **The translation.** When it is not empty, it is shown in the game |

Keep the engine markup: `@Name@` at the start sets the speaker name (for example `@Казуна@`), `$d` separates choices, `$[base$/ruby$]` is ruby text. Write a line break as `\n` and a tab as `\t`.

The build never changes the tables in `languages/`. It writes a copy of every table, in the current format, to `build/<lang>/translation/`; for a language without tables these are empty tables to start from. Tables in older formats (with `source` and `existing` columns, or `ru` instead of `translation`) are still read. To translate into a new language, start from the original tables in [languages/_original_jp/](languages/_original_jp/README.md).

## Translating the Interface

### Interface text

The interface text (options, confirmation dialogs, the save screen's months, music and ending titles, the start-up notice) is stored in `CARTAGRA.exe`. The Russian release left it in English. Its translation is in `languages/<lang>/interface.tsv` (UTF-8, tab-separated):

| Column | Meaning |
| --- | --- |
| `id` | Position of the string in `CARTAGRA.exe` (do not edit) |
| `original` | The English text of the release (do not edit; the build checks it against your `CARTAGRA.exe`) |
| `translation` | **The translation.** When it is not empty, the game shows it instead of the original |

Everything here is based on the Steam (Russian) release only: its interface differs from the Japanese release's.

Write a line break as `\n` and a tab as `\t`. Keep the engine markup (`$A1`, `$d`, `$S(42)`, `$C(230,230,126)`) and keep printf placeholders such as `%d`, `%02d`, `%s` and `%%` in the same order: the build stops if they differ. Leading and trailing spaces center short labels on their buttons. Translations may be longer than the original, but labels have limited room in the game: check them in game.

Limits of the game's fonts (found in game):

- The interface font has no `«` and `»` (they show as blanks); use `❝` and `❞` (shown as “ ”), as the English text does.
- The slider labels and the version number use a small font without Cyrillic letters: Russian text there is not shown. These strings stay English: `Slow`/`Fast`, `Solid`/`Clear`, `Auto`, the colour names of "Read Text Color" (`Orange`, `Yellow`, `Green`, `Blue`, `Purple`, `Red`), the scale labels of Text2 (`0 sec/char`, `0.1 sec/char`, `0 sec`..`3 sec`) and `Game Ver. `.
- `BGM`, `SE` and `MOVIE` are not in the table: the same strings are names of script commands in the executable, so they stay English (the BGM volume label shows "BGM").

The build copies the table to `build/<lang>/interface.tsv`. To translate the interface into another language, copy [languages/_original_steam/en/interface.tsv](languages/_original_steam/en/interface.tsv) (English only) to `languages/<code>/interface.tsv` and fill in the `translation` column.

The table fits only the `CARTAGRA.exe` of the Russian release (its checksum is in `definitions/inputs.json`). `python -m cartagra_patch.exe_text check <exe> <table>` checks a table against an executable, and `python -m cartagra_patch.exe_text list <exe>` lists every string the code refers to (to find strings for another version).

### Interface pictures

Some interface elements are pictures with English text: the title menu, the Extras headings and "Completion Rate", the logo with its tagline, the options tabs, the system menu, the in-game buttons, the SAVE/LOAD labels, the "Jump" indicators, the key names and the manual pages (134 pictures). The build does not change them unless you replace them. [languages/_original_steam/en/images.tsv](languages/_original_steam/en/images.tsv) lists them with what each one shows.

To translate them:

1. Export the originals once:
   ```bash
   python build.py --language ru --export-images
   ```
   It writes every listed picture as PNG to `languages/_original_steam/en/images/<archive>/<entry>.png` and copies the ones you do not have yet to `languages/ru/images/` (existing copies are never overwritten). `<archive>` is the archive's path below `files/image/` without `.PAK`, for example `resident/PARTS` or `SYSCG`. The archives are read from the input set; `image/resident/PARTS.PAK` must be there too.
2. Edit the copies in `languages/ru/images/`. Keep their size in pixels and save them as 8-bit PNG (RGBA is best; transparency is kept). Leave `languages/_original_steam/en/images/` unchanged: the build compares against it.
3. Build. Pictures that differ from the originals are written into their archives in `dist/<lang>/files/image/...`; install them like the other files. Unedited copies are skipped, so the patch stays the same until you change a picture.

Any other picture of an archive can be replaced the same way: export it with `python -m cartagra_patch.cztool export <archive.PAK> <folder> <entry>` and put the edited PNG in `languages/<lang>/images/<archive>/`.

Pictures are stored uncompressed (CZ0), so an archive grows (`PARTS.PAK` by about 0.5 MB for the options tabs); the Russian release already uses CZ0 pictures for its title menu. Tested in game with a recoloured `options_tab_en`. The PNG files are not committed to git (`.gitignore`): they are the game's art; `--export-images` makes them again from your own copy of the game.

## Testing Status

Tested in game with the Russian release (2026-10-25 and 2026-10-26):

- New game: the first scenes show the correct backgrounds (the black-screen bug of the old patch is fixed). This test was made before the prologue was restored.
- Restored scenes `a1-7-2h`, `0208-13-01H` (choices and branches) and `0217-99-04h` (a removed scene) play, with voices and restored CGs, and continue into the following scenes.
- The restored pictures display uncensored.
- The restored game start: New Game plays the prologue and the opening movie, then the first scene.

Not tested yet: the other 21 restored scenes, a full playthrough, loading saves across installing the patch, the CG gallery, scene replay, and anything in English.

Interface translation (2026-10-26): the start-up notice, all Options pages, the exit and back-to-title dialogs were checked in game; a replacement picture was shown in game. Not checked in game: the save and load dialogs, the voice collection, the music and ending titles (locked on a new profile). See [TECHNICAL_NOTES.md](TECHNICAL_NOTES.md#interface-text-and-images).

When you report a problem, give the scene name if you know it (for example `0208-13-01H`), what you saw, and whether the unpatched game behaves differently there.

## Known Limitations

- The 3,970 Russian lines added to the restored scenes on 2026-10-26 have not been checked in game yet.
- Restored CGs may not appear in the Extras CG gallery, and restored scenes are not in scene replay.
- Restored scenes have no save thumbnails.
- `0210-10-00` and `0215-03-00` show the Japanese date screen instead of the English one.
- In `0210-99-01`, the Russian release shows Steam's substitute picture (a kiss) just before the restored scene; this picture is kept.
- In `0208-15-00`, Steam's own extra frame is no longer shown; the scene shows the original frames instead.
- Before 2026-10-26 the patch did not update the read-text and choice records, so in restored scenes "Skip read text" skipped unread lines and chosen options were not remembered. Fixed and tested in game. The game writes this data only when you save (also quick save), not when you quit. It keeps this data in `%APPDATA%\GSE Saves\4290390\remote\data000.dat` (the bundled Steam emulator puts all saves there; the empty `userdata` folder in the game folder is not used). Back up that folder before installing a new build.
- Chosen options are shown in another color only if **Options > Text1 > "Color of Previously Read Text"** is set to "Only Choices" (chosen options only, as in the Japanese release) or "On" (all read text). With "Off" the game still remembers your choices but doesn't mark them.
- Slider labels, the version label and `BGM` stay English (see [Interface text](#interface-text)). Character names on the Voice page come from `PARAM.PAK` and are not translated.
- Interface pictures (title menu, options tabs, system menu, in-game buttons, save screen labels, manual pages) are still in English. You can replace them; see [Interface pictures](#interface-pictures).
- The English build has never been made or tested.
- There is no installer.

The full list of known issues and open questions is in [TECHNICAL_NOTES.md](TECHNICAL_NOTES.md#known-issues).

## Project Layout

| Path | Contents |
| --- | --- |
| `build.py` | The build command |
| `cartagra_patch/` | Source code |
| `definitions/` | What the patch restores and which input files it needs (shared by all languages) |
| `languages/<lang>/` | Language settings, translation tables, the interface table and its pictures |
| `languages/_original_jp/` | The original scene tables (Japanese release text), a basis for translations into other languages |
| `languages/_original_steam/en/` | The Steam release's English interface: the interface table, the list of pictures with text and the exported pictures |
| `tests/` | Automated tests (`python tests/test_core.py`) |
| `inputs/` | Your copies of the original game files (not in git) |
| `build/` | Intermediate files (not in git) |
| `dist/` | The finished patch (not in git) |

## Sources

- [VNDB: Cartagra](https://vndb.org/v515)
- [Steam: CARTAGRA](https://store.steampowered.com/app/4290390/CARTAGRA/) (app ID 4290390)
- [Chinese patch (lzacg)](https://lzacg.cc/7683)
- [Chinese patch source: HIllya51/Cartagra_FHD_CHS](https://github.com/HIllya51/Cartagra_FHD_CHS)
- [Russian release (ruvn)](https://s.ruvn.org/novels/cartagra-tsuki-kurui-no-yamai)
- Russian translation: [Innocence translations](https://t.me/innocence_translations) and [The Hounds of God](https://vk.ru/thgteam)

## Disclaimer

This patch is only for owners of legitimate copies of the game. It contains no game files; you build it from your own copies. Do not share the contents of `inputs/`, `build/` or `dist/`, or the translation tables (they contain game text). Use at your own risk; the tools are provided "as is" for educational purposes.
