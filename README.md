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
| Scenes | 20 scenes that Steam rewrote are replaced by the uncensored versions; 4 removed scenes are added back. All other scripts stay unchanged |
| CGs | 150 event CGs that Steam removed |
| Edited pictures | 51 pictures that Steam edited (clothes added, blood, wounds and bodies hidden) are replaced by the originals |
| Voices | 1,901 voice clips of the restored scenes |
| Text | Restored lines use the language's translation tables, then the existing translation where the same line exists elsewhere in the game; lines with neither show the Japanese text |

The patch replaces four files of the game:

| File | Approximate size |
| --- | --- |
| `files/SCRIPT.PAK` | 6 MB |
| `files/image/EVENTCG.PAK` | 569 MB |
| `files/image/OTHCG.PAK` | 340 MB |
| `files/voice/VOICE.PAK` | 807 MB |

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
  en-steam/files/    English Steam release     (for --language en)
```

The files must be **unmodified originals**. If the patch is already installed in your game, take the files from your backup instead.

| Input set | Files |
| --- | --- |
| `jp-fhd` | `SCRIPT.PAK`; `image/`: `BGCG.PAK`, `CHARCG.PAK`, `EVENTCG.PAK`, `EVENTCG_SAVE.PAK`, `OTHCG.PAK`, `PARTS.PAK`, `SYSCG.PAK`, `SYSCG2.PAK`; `voice/`: `SYSVOICE.PAK`, `VOICE0.PAK`, `VOICE1.PAK` |
| `ru-steam`, `en-steam` | `SCRIPT.PAK`; `image/`: `BGCG.PAK`, `CHARCG.PAK`, `EVENTCG.PAK`, `MANUAL.PAK`, `MANUAL_DECK.PAK`, `OTHCG.PAK`, `SYSCG.PAK`, `SYSCG2.PAK`; `voice/`: `SYSVOICE.PAK`, `VOICE.PAK` |

The exact sizes and checksums are listed in [definitions/inputs.json](definitions/inputs.json). The English file list is an assumption (the same as the Russian one); nobody has checked it.

Example for Windows `cmd.exe`, run from the project folder (replace the game paths with yours):

```bat
robocopy "D:\Games\Cartagra_FHD\files" "inputs\jp-fhd\files" SCRIPT.PAK
robocopy "D:\Games\Cartagra_FHD\files\image" "inputs\jp-fhd\files\image" BGCG.PAK CHARCG.PAK EVENTCG.PAK EVENTCG_SAVE.PAK OTHCG.PAK PARTS.PAK SYSCG.PAK SYSCG2.PAK
robocopy "D:\Games\Cartagra_FHD\files\voice" "inputs\jp-fhd\files\voice" SYSVOICE.PAK VOICE0.PAK VOICE1.PAK
robocopy "D:\Games\Cartagra2023RUS\files" "inputs\ru-steam\files" SCRIPT.PAK
robocopy "D:\Games\Cartagra2023RUS\files\image" "inputs\ru-steam\files\image" BGCG.PAK CHARCG.PAK EVENTCG.PAK MANUAL.PAK MANUAL_DECK.PAK OTHCG.PAK SYSCG.PAK SYSCG2.PAK
robocopy "D:\Games\Cartagra2023RUS\files\voice" "inputs\ru-steam\files\voice" SYSVOICE.PAK VOICE.PAK
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
| `--list-languages` | Show the languages and their status |
| `--skip-checksums` | Skip the checksum check of the inputs (faster; sizes are still checked) |
| `--no-voice` | Do not build `VOICE.PAK` (the restored lines play without voice) |
| `--help` | Show all options |

Options for testing only: `--scenes SCENE ...` restores only the named scenes (output in `dist/<lang>-partial/`); `--test-start SCENE` makes New Game jump straight into a scene, and `--test-set VAR=VALUE` sets game variables first (output in `dist/<lang>-test/`). Never install these builds for normal play.

### Output

```text
dist/ru/
  BUILD_INFO.txt     language, status, and the destination and checksum of each file
  files/SCRIPT.PAK
  files/image/EVENTCG.PAK
  files/image/OTHCG.PAK
  files/voice/VOICE.PAK
```

Intermediate files go to `build/ru/`. `dist/ru/` is replaced only when a build succeeds. Building twice from the same inputs gives identical files.

## Step 3: Install

The build does not install anything. Install by hand:

1. Back up the four original files from your game's `files/` folder (`SCRIPT.PAK`, `image/EVENTCG.PAK`, `image/OTHCG.PAK`, `voice/VOICE.PAK`) and your saves. Keep the backups somewhere safe. The input copies in `inputs/` also work as a backup.
2. Copy the contents of `dist/ru/files/` into the game's `files/` folder and replace the files. `BUILD_INFO.txt` lists the destination of each file.
3. Start the game.

Example for `cmd.exe` (replace the game path):

```bat
robocopy "dist\ru\files" "D:\Games\Cartagra2023RUS\files" /E
```

**Saves:** saves made inside one of the restored scenes, or inside the scripts `0216-04-03`, `0216-05-02`, `0217-01-04`, `0217-99-03`, `0208-15-00` and `0210-07-00` (the patch changes them slightly), may not load correctly after installing or removing the patch. Saves made elsewhere are not affected. The Russian release keeps its saves in `%APPDATA%\GSE Saves\4290390`; back that folder up before installing.

## Removing the Patch

Copy the four original files back into the game's `files/` folder, for example from the input copies:

```bat
robocopy "inputs\ru-steam\files" "D:\Games\Cartagra2023RUS\files" SCRIPT.PAK
robocopy "inputs\ru-steam\files\image" "D:\Games\Cartagra2023RUS\files\image" EVENTCG.PAK OTHCG.PAK
robocopy "inputs\ru-steam\files\voice" "D:\Games\Cartagra2023RUS\files\voice" VOICE.PAK
```

If an old version of this patch installed `EVENTCG_SAVE.PAK` into `files\image\`, delete it too.

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

The build never changes the tables in `languages/`. It writes a copy of every table, in the current format, to `build/<lang>/translation/`; for a language without tables these are empty tables to start from. Tables in older formats (with `source` and `existing` columns, or `ru` instead of `translation`) are still read. To translate into a new language, start from the original tables in [languages/_original/](languages/_original/README.md).

## Testing Status

Tested in game with the Russian release (2026-10-25 and 2026-10-26):

- New game: the prologue and the following scenes show the correct backgrounds (the black-screen bug of the old patch is fixed).
- Restored scenes `a1-7-2h`, `0208-13-01H` (choices and branches) and `0217-99-04h` (a removed scene) play, with voices and restored CGs, and continue into the following scenes.
- The restored pictures display uncensored.

Not tested yet: the other 21 restored scenes, a full playthrough, loading saves across installing the patch, the CG gallery, scene replay, and anything in English.

When you report a problem, give the scene name if you know it (for example `0208-13-01H`), what you saw, and whether the unpatched game behaves differently there.

## Known Limitations

- The 3,970 Russian lines added to the restored scenes on 2026-10-26 have not been checked in game yet.
- Restored CGs may not appear in the Extras CG gallery, and restored scenes are not in scene replay.
- Restored scenes have no save thumbnails.
- `0210-10-00` and `0215-03-00` show the Japanese date screen instead of the English one.
- In `0210-99-01`, the Russian release shows Steam's substitute picture (a kiss) just before the restored scene; this picture is kept.
- In `0208-15-00`, Steam's own extra frame is no longer shown; the scene shows the original frames instead.
- The English build has never been made or tested.
- There is no installer.

The full list of known issues and open questions is in [TECHNICAL_NOTES.md](TECHNICAL_NOTES.md#known-issues).

## Project Layout

| Path | Contents |
| --- | --- |
| `build.py` | The build command |
| `cartagra_patch/` | Source code |
| `definitions/` | What the patch restores and which input files it needs (shared by all languages) |
| `languages/<lang>/` | Language settings and translation tables |
| `languages/_original/` | The original translation tables, a basis for translations into other languages |
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
