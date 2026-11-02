# Technical Notes

Working notes for reverse engineering and development of the Cartagra cut-content patch. For the build steps and the translation files, see [README.md](README.md) and [languages/README.md](languages/README.md); what the patch changes, the build options and installing are in [Patch Contents and Usage](#patch-contents-and-usage). The chronological journal is [MODLOG.md](MODLOG.md).

## Evidence Labels

| Tag | Meaning |
| --- | --- |
| **[V]** Verified | Checked against the files, code or the running game (the method is given) |
| **[O]** Observed | Seen in game; not fully explained |
| **[H]** Hypothesis | Plausible, but not tested |
| **[?]** Open | Unknown; needs investigation |

Sizes are in bytes, with MiB (1,048,576 bytes) where useful. Unless noted otherwise, [V] findings were checked on 2026-10-25 with read-only scripts, by round-tripping archives through `lucapak`/`lucascript`, or in game.

Module names refer to `cartagra_patch/<name>.py`. Before the 2026-10-26 refactoring they were top-level scripts (`lucapak.py`, `build_patch.py`, ...); see [Build System](#build-system).

## Contents

- [Summary of Findings](#summary-of-findings)
- [Patch Contents and Usage](#patch-contents-and-usage)
- [Game Installations in This Project](#game-installations-in-this-project)
- [PAK Archive Format](#pak-archive-format)
- [Resource IDs](#resource-ids)
- [Cause of the Wrong Background and Black Screen](#cause-of-the-wrong-background-and-black-screen)
- [Scene Scripts](#scene-scripts)
- [Porting Scripts from JP to RUS](#porting-scripts-from-jp-to-rus)
- [What Steam Censored](#what-steam-censored)
- [Start Sequence](#start-sequence)
- [Read Flags and Saves](#read-flags-and-saves)
- [Interface Text and Images](#interface-text-and-images)
- [EVENTCG.PAK Comparison](#eventcgpak-comparison)
- [Censored Images](#censored-images)
- [CG Gallery](#cg-gallery)
- [Voice, Music and Sound Effects](#voice-music-and-sound-effects)
- [Sound Crash](#sound-crash)
- [CZ4 Image Format and Engine](#cz4-image-format-and-engine)
- [The Chinese Patch (Reference Implementation)](#the-chinese-patch-reference-implementation)
- [Patch Generation](#patch-generation)
- [Build System](#build-system)
- [Language Targets](#language-targets)
- [Test Results](#test-results)
- [Known Issues](#known-issues)
- [Open Questions](#open-questions)
- [Roadmap](#roadmap)
- [Tools](#tools)
- [References](#references)

## Summary of Findings

1. **[V]** Scripts refer to images and voices by **numeric resource ID = archive `id_start` + entry index**, not by name. Archive order is part of the format.
2. **[V]** The old patch failed because `pak_tool.py` reset EVENTCG's `id_start` from 1001 to 1 (the range BGCG uses) and re-sorted the entries. The fix keeps every original entry in place and appends new ones; it is verified in game.
3. **[V]** The Russian release is the Steam multi-language build. Its scripts use a shifted opcode table and store an extra "English" text slot that the Russian translators filled with Russian.
4. **[V]** Steam did not only remove images. It **rewrote** 20 scenes (most dialogue replaced by a few new lines) and **removed** 4 scenes entirely. Restoring the CGs therefore requires porting the uncensored JP scene scripts.
5. **[V]** 1,901 voice clips (the H-scene voices) were removed from the Steam `VOICE.PAK`.
6. **[V]** All 24 censored scenes are now ported and all 150 restored CGs are referenced. 3,970 of 4,422 restored lines have no Russian translation in the release; since 2026-10-26 the Russian tables translate all of them (see [Text for the Russian slot](#text-for-the-russian-slot)).
7. **[V]** Steam also **edited 51 pictures** that the Russian scripts still show (35 EVENTCG, 16 OTHCG): clothes painted on, blood, wounds and corpses removed or blacked out, frames recomposed. The patch puts the JP originals back in the same slots.
8. **[V]** Steam **moved the prologue and the opening movie** from New Game to just before part 2, and the Rengoku movie from there to the end of `0209-08-00`. The patch restores the JP order with three script edits (see [Start Sequence](#start-sequence)).
9. **[V]** The bitmaps for read lines and chosen options in the system data are sized by the `_arflag` table of `SCRIPT.PAK`, which the patch must update for every changed script (see [Read Flags and Saves](#read-flags-and-saves)).
10. **[V]** The interface text is in `CARTAGRA.exe` (Japanese, Chinese and English strings; the Russian release shows the English ones). The patch translates it from a TSV table by adding a section with the translations and redirecting the references, the same method the Russian translators used for the prologue text. Interface pictures stay as they are but can be replaced (see [Interface Text and Images](#interface-text-and-images)).
11. **[V]** The Extras ending list starts 7 of its 18 endings at a script label, whose bytecode offset comes from `_scr_label`. In the Russian release those offsets still belong to the shorter English scripts and point into the middle of instructions (only 8 of 359 are instruction starts), so these endings began with garbage instead of their first instruction (user report 2026-11-02: black screen). The patch writes the table anew (see [Label table](#label-table)).
12. **[V]** The game crashes now and then with an integer division by zero in its Ogg sound code (`0x2f42ba`; 29 crash reports on this PC from 2026-10-31 on, all at that address). It is a race in the Steam executable, not caused by the patch's data; the patch changes one byte of the executable so the code no longer reads the freed value (see [Sound Crash](#sound-crash)).

## Patch Contents and Usage

Moved here from README.md on 2026-11-03. The README keeps the build steps and the translation files.

### What the patch changes

| Content | Details |
| --- | --- |
| Scenes | 20 scenes that Steam rewrote are replaced by the uncensored versions; 4 removed scenes are added back ([What Steam Censored](#what-steam-censored)) |
| CGs | 150 event CGs that Steam removed |
| Edited pictures | 51 pictures that Steam edited (clothes added, blood, wounds and bodies hidden) are replaced by the originals ([Censored Images](#censored-images)) |
| Voices | 1,901 voice clips of the restored scenes |
| Game start | New Game plays the prologue and the opening movie before the first scene, as in the Japanese release; the Rengoku movie goes back before part 2 ([Start Sequence](#start-sequence)) |
| Crash fix | One byte of `CARTAGRA.exe`: the sound code always uses the game's 48 kHz rate instead of a value that may already be freed ([Sound Crash](#sound-crash)) |
| CG gallery | Extras > CG gallery lists the restored CGs too: 259 slots on 18 pages instead of 185 on 13, in the release's order ([CG Gallery](#cg-gallery)) |
| Ending replay | `_scr_label` is written anew, so the endings in Extras > Endings start at their first instruction ([Label table](#label-table)) |
| Text | Restored lines use the language's tables, then an identical line of the release, otherwise the Japanese text |
| Interface (`ru` only) | Interface strings of `CARTAGRA.exe` (296 of 297), 28 interface pictures, Cyrillic letters in FONT1, a Cyrillic `№` in FONT0, the scene headings of the save screens ([Interface Text and Images](#interface-text-and-images)) |

**[V]** (2026-11-03) What each build writes:

| Build | Files | Size |
| --- | --- | --- |
| `ru` | `CARTAGRA.exe` (interface + crash fix), `files/SCRIPT.PAK`, `files/PARAM.PAK`, `files/image/EVENTCG.PAK`, `OTHCG.PAK`, `SYSCG.PAK`, `SYSCG2.PAK`, `resident/PARTS.PAK`, `files/voice/VOICE.PAK`, `files/font_win32_1920/FONT0*.PAK` and `FONT1*.PAK` (14 files) | 1.9 GB |
| `en` | `CARTAGRA.exe` (the target's original text, no translation, + crash fix), `files/SCRIPT.PAK` (restored scenes, the two picture fixes, start sequence, label table, `_arflag`; no translation), `files/PARAM.PAK` (CG gallery), `files/image/EVENTCG.PAK`, `OTHCG.PAK`, `SYSCG2.PAK` (gallery previews), `files/voice/VOICE.PAK` | 1.7 GB |

The `en` row comes from a trial build with `--language en --target-files inputs/ru-steam/files` (the English Steam files are not available): it has no interface table, scene titles, pictures or font keys, so it writes only the restoration, the crash fix and the start sequence; 3,970 restored lines stay Japanese (452 reuse lines of the release). **[V]** Its executable has no translation either: `exe_original_text` (in `languages/en/language.json`) removes the Russian translators' `.rtransl` section when the input exe has it ([Strings in CARTAGRA.exe](#strings-in-cartagraexe)). Checked again on 2026-11-03 with the user's `inputs/en-steam/` (Russian archives, the Steam `CARTAGRA_backup.exe`): the output exe has no Cyrillic text and differs from the input only by the crash fix.

Approximate sizes of the replaced files: `CARTAGRA.exe` 7 MB, `SCRIPT.PAK` 6 MB, `EVENTCG.PAK` 569 MB, `OTHCG.PAK` 341 MB, `VOICE.PAK` 807 MB, `PARAM.PAK` 0.1 MB, `SYSCG2.PAK` 23 MB; `ru` also `SYSCG.PAK` 62 MB, `resident/PARTS.PAK` 91 MB (pictures stored uncompressed as CZ0; the original is 22 MB), FONT0 80 MB, FONT1 15 MB.

### Inputs

The build reads only `inputs/<set>/` (or `--jp-files`, `--target-files`, `--inputs`): `jp-fhd/files/` (Japanese FHD 2023: `SCRIPT.PAK`, `PARAM.PAK`, `image/*.PAK`, `voice/*.PAK`), `<target>/files/` (`SCRIPT.PAK`, `PARAM.PAK`, `image/*.PAK`, `voice/*.PAK`; `image/resident/PARTS.PAK` when pictures are replaced; `font_win32_1920/FONT0*`, `FONT1*` when `font_glyphs` or `font_numero` is set) and `<target>/CARTAGRA.exe` (always needed now, for the executable fixes). `definitions/inputs.json` lists every file with size, entry count and SHA-256; the English list is an assumption (copied from `ru-steam`, no checksums). About 4.8 GB for the inputs and 2 GB for the output.

### Command line

| Option | Effect |
| --- | --- |
| `--language ru` / `en` | Language to build (required) |
| `--check` | Only check the input files |
| `--export-images` | Export the interface pictures as PNG for translation ([languages/README.md](languages/README.md#interface-pictures-images)) |
| `--list-languages` | Show the languages and their status |
| `--skip-checksums` | Skip the SHA-256 check of the inputs (sizes and entry counts are still checked) |
| `--no-voice` | Do not build `VOICE.PAK` (restored lines play without voice) |
| `--inputs DIR`, `--jp-files DIR`, `--target-files DIR` | Read the inputs from other folders (never from an installation the patch is in) |
| `--scenes SCENE ...` | Testing: restore only these scenes (output `dist/<lang>-partial/`) |
| `--test-start SCENE`, `--test-set VAR=VALUE` | Testing: New Game jumps straight into a scene, after setting game variables (output `dist/<lang>-test/`) |

A `ru` build takes about 4 minutes (most of it the FONT0 re-encoding), an `en` build under a minute. On an error it prints a line starting with `error:` and exits with 1 (2 for usage errors). Intermediate files go to `build/<lang>/`; `dist/<lang>/` is replaced only when a build succeeds; two builds from the same inputs give identical files.

### Installing and removing

The build installs nothing. Copy the contents of `dist/<lang>/` into the game folder (`CARTAGRA.exe` next to the game's `CARTAGRA.exe`, `files/` into `files/`), after backing up the files `BUILD_INFO.txt` lists and the saves. For example (`cmd.exe`):

```bat
robocopy "dist\ru" "D:\Games\Cartagra-2026-RU-Final" /E /XF BUILD_INFO.txt
```

To remove the patch, copy the same files back from the backup or from `inputs/<target>/`. If an old version installed `files/image/EVENTCG_SAVE.PAK`, delete it.

Saves: the Russian release keeps them in `%APPDATA%\GSE Saves\4290390` (the bundled Steam emulator; the empty `userdata` folder of the game is not used), including the read-text and choice records in `remote\data000.dat` ([Read Flags and Saves](#read-flags-and-saves)). Saves made inside a restored scene or inside `0216-04-03`, `0216-05-02`, `0217-01-04`, `0217-99-03`, `0208-15-00`, `0210-07-00` and the start-sequence scripts may not load correctly after installing or removing the patch.

## Game Installations in This Project

All paths are relative to the project root `Cartagra-Patch/`. Folder layout since 2026-11-03 (the user renamed and split the folders; older entries of [MODLOG.md](MODLOG.md) use the old names given in brackets):

| Directory | What it is |
| --- | --- |
| `Cartagra-2023-JP/` | Japanese FHD 2023 release (カルタグラ FHD, `カルタグラ FHD.exe`), unmodified. Source of the cut content. **[V]** (2026-11-03) its 12 input archives have the sizes and SHA-256 recorded for `jp-fhd` in `definitions/inputs.json` (the copies in `Patch/inputs/jp-fhd/` came from the same release, earlier installed with the Chinese fan patch in `Cartagra_FHD_CHS_GAME_v1.1/`; that patch reads its own files from `CHSPAK\` and leaves these archives unchanged) |
| `Cartagra-2026-RU-Steam/` | Russian 2026 release by Innocence translations and The Hounds of God (Steam build, app ID 4290390, with a Goldberg-type Steam emulator in `steam_settings/`, `language=english`), unmodified. Target of `ru`. Executable `CARTAGRA.exe` (window title "CARTAGRA - Ver.1.0.0.1"). **[V]** (2026-11-03) its files match the `ru-steam` checksums |
| `Cartagra-2026-RU-Final/` | The Russian release with the patch installed (was `Cartagra2023RUS/`); its `BUILD_INFO.txt` names the installed build. Used for the in-game tests |
| `Patch/` | This project (git repository) |
| `Patch/inputs/` | Local copies of the original files the build reads (outside git): `jp-fhd/files/` from `Cartagra-2023-JP/files/`; `ru-steam/` from `Cartagra-2026-RU-Steam/`. The build never reads the installations themselves |

The source code of the Chinese fan patch (`Cartagra_FHD_CHS/`, from [HIllya51/Cartagra_FHD_CHS](https://github.com/HIllya51/Cartagra_FHD_CHS)) was used as a reference (see [The Chinese Patch](#the-chinese-patch-reference-implementation)); it is no longer kept here. The old `backup/` folder (pristine Russian files in `backup/orig/`, save backups in `backup/saves/`) is gone too: `Cartagra-2026-RU-Steam/` and `Patch/inputs/ru-steam/` hold the pristine files.

### Archives present

**[V]** (entry counts from headers)

| Archive | RUS | JP (`files/`) | Notes |
| --- | --- | --- | --- |
| `SCRIPT.PAK` | 5,210,545 B, 274 entries | 2,066,360 B, 277 entries | block size 4 |
| `PARAM.PAK` | 104,280 B, 7 | 121,184 B, 4 | block size 4 |
| `SYSFONT.PAK` | 19,986,432 B, 12 | 4,452,352 B, 17 | |
| `SYSFONT_ZC.PAK` | 1,572,864 B, 4 | absent | |
| `SYSSE.PAK` | 303,104 B, 13 | 303,104 B, 13 | |
| `FONT.PAK`, `FONT_V.PAK`, `SHADER.PAK` | absent | present | RUS has `font_win32_1920*/FONT0_*`, `FONT1_*`, `fontzc_*` instead |
| `image/EVENTCG.PAK` | 371,456,000 B, 223 | 551,507,968 B, 364 | |
| `image/EVENTCG_SAVE.PAK` | absent | 15,243,264 B, 130 | |
| `image/BGCG.PAK` | 487,849,984 B, 179 | 477,325,312 B, 175 | |
| `image/CHARCG.PAK` | 381,585,408 B, 976 | 376,979,456 B, 892 | |
| `image/OTHCG.PAK` | 339,937,280 B, 362 | 345,741,312 B, 436 | |
| `image/SYSCG.PAK` | 55,107,584 B, 49 | 33,372,160 B, 46 | |
| `image/SYSCG2.PAK` | 8,034,304 B, 185 | 11,309,056 B, 254 | |
| `image/PARTS.PAK` | `image/resident/PARTS.PAK`: 22,243,328 B, 440 | 9,873,408 B, 116 | interface parts |
| `image/MANUAL.PAK`, `MANUAL_DECK.PAK` | present | absent | |
| `voice/VOICE.PAK` (JP: `VOICE0.PAK`) | 601,276,416 B, 8,183 | 10,080 entries | |
| `voice/VOICE1.PAK` | absent | 3 entries | |
| `voice/SYSVOICE.PAK` | 18 entries | 19 entries | |
| `music/MUSIC.PAK` | 44 | 44 | same names and order |
| `se/SE.PAK` | 241 | 236 | JP list is a prefix of the RUS list |
| `movie/` | `cartagra_movie_NN_en.webm` | `cartagra_movie_NN.webm` | scripts name movies without the `_en` suffix in both. Steam swapped 01 and 02 (see [Start Sequence](#start-sequence)) |

**[V]** The RUS executable contains the string `*.PAK` and mounts image archives by wildcard.

### Current install state

**[V]** (2026-11-03) `Cartagra-2026-RU-Final/` has the `ru` build installed; its `BUILD_INFO.txt` lists the SHA-256 of every installed file. The pristine originals are in `Cartagra-2026-RU-Steam/` (SHA-256 prefixes: EVENTCG `8f2a9b21300cb3fa`, OTHCG `477b30ba8f36e5e9`, VOICE `42e87d76474c8ae6`, SCRIPT `c33dd504c40a120f`, `CARTAGRA.exe` `e2d463e971a95236`).

**[V]** `Cartagra-2026-RU-Steam/` also contains `CARTAGRA_backup.exe` (6,856,704 B) next to `CARTAGRA.exe` (6,630,400 B); this project did not create either. `CARTAGRA.exe` is the Russian release's own executable: it has an extra section `.rtransl` with the Russian prologue text (see [Interface Text and Images](#interface-text-and-images)).

## PAK Archive Format

**[V]** Layout, verified by a byte-identical round trip (`python -m cartagra_patch.lucapak roundtrip <pak>`) of RUS and JP `EVENTCG.PAK`, JP `EVENTCG_SAVE.PAK`, RUS `BGCG.PAK`, `SYSCG.PAK`, `SCRIPT.PAK`, `VOICE.PAK` and JP `SCRIPT.PAK`:

| Offset | Size | Field |
| --- | --- | --- |
| `0x00` | u32 | `data_offset`: start of file data (multiple of `block_size`) |
| `0x04` | u32 | `count` |
| `0x08` | u32 | `id_start`: resource ID of entry 0 (see [Resource IDs](#resource-ids)) |
| `0x0C` | u32 | `block_size`: 2048 (images, voice, fonts), 4 (`SCRIPT`, `PARAM`), 4096 (`SHADER`) |
| `0x10` | 16 B | Usually zero (`PARTS.PAK`: `0x10` = `0x3CC`). Copied verbatim |
| `0x20` | u8 | `nsec`: number of per-entry sections |
| `0x21` | u8 | `flags`: bit 0 = per-entry metadata table present; bit 1 = name table present; bit 2 set in all originals (meaning unknown) |
| `0x22` | 6 B × `nsec` | Section descriptors: u8 type, u8 element size, u32 offset |
| aligned to 4 | u32 | `names_offset` |
| next | 8 B × `count` | Index: u32 offset **in blocks**, u32 size in bytes |
| next (if flags bit 0) | `meta_size` × `count` | Per-entry metadata (BGCG: 12 bytes, starting with width/height `0x780`, `0x438`) |
| `names_offset` | | `count` NUL-terminated UTF-8 names |
| section offsets | elem size × `count` | Sections, in descriptor order |
| `data_offset` | | Data; each entry starts on a block boundary |

**[V]** The filler between entries is **not always zero**, and the last entry of `SCRIPT.PAK` is not padded. `lucapak` keeps each entry's original filler, which is what makes the round trip byte-identical.

### Section types

| Type | Size | Image archives | Voice archives |
| --- | --- | --- | --- |
| `0x01` | 2 | **Parent (base) image ID** of a variant, e.g. `e001k1` → ID of `e001`; 0 = none | Per-clip value (identical in JP and RUS for the same clip) |
| `0x03` | 1 | 0 in all EVENTCG entries | — |
| `0x04` | 2 | 0 in EVENTCG | Per-clip value (identical in JP and RUS) |
| `0x0B` | 8 | **xxHash64 (seed 0) of the entry data**, little-endian. Only in the RUS (Steam) build | same |

**[V]** The engine does **not** verify the `0x0B` hashes: all 274 RUS `SCRIPT.PAK` hashes are stale (the Russian translators changed the scripts without updating them), yet the game runs. The patch still writes correct hashes for new and changed entries.

**[V]** How readers find the index: from `0x24`, step 4 bytes until the u32 equals `data_offset / block_size`. Both the old `pak_tool.py` and the Chinese `pak.py` do this. The descriptor-based parse above is exact.

## Resource IDs

**[V]** A resource's ID is `id_start + entry index` of its archive. Scripts use these numbers directly: for example, the RUS image-load instruction `0001 5504` loads image 0x455 = 1109 = EVENTCG entry 108.

| Namespace | Archive: `id_start` (RUS) |
| --- | --- |
| Images | BGCG 1, EVENTCG 1001, EVENTCG_SAVE 1501 (JP), CHARCG 10001, OTHCG 25001, SYSCG 60001, MANUAL_DECK 62000, SYSCG2 63000, PARTS 64000 (JP), MANUAL 64500; IDs 65000/65001/65100 are used by scripts but belong to no archive (**[H]** built-in colour layers) |
| Voice | VOICE 1, VOICE1 55001 (JP), SYSVOICE 65000 |
| Music | MUSIC 100001 |
| Sound effects | SE 200001 |

**[V]** Images and voices are separate namespaces (BGCG and VOICE both start at 1 in the original game).

**[V]** Consequences: an archive's entry order must never change, and new entries can only be appended. The same name has different IDs in the two builds (only 14 of 214 common EVENTCG names share an ID; voice `kaz3039` is 2395 in JP and 2022 in RUS), so ported scripts must remap IDs **by name**.

## Cause of the Wrong Background and Black Screen

**[V]** Reported symptom (old `EVENTCG_patched.PAK`): scene 1 correct, scene 2 an entirely wrong background, then a black screen where the scene no longer advances while the UI still works.

**[V]** Cause: `pak_tool.py pack` wrote `id_start = 1` (the original is 1001) and dropped the sections. It also sorted entries by name and inserted the 150 new files among them. So:

- EVENTCG entries took IDs 1..373, overlapping BGCG's 1..179. Background loads returned event CGs, which gave the wrong background in scene 2 (scene 1, `0000-op1`, uses only OTHCG/EVENTCG art that is loaded differently). **[H]** which archive wins on a collision was not tested.
- No EVENTCG entry had an ID ≥ 1001 any more, so every event-CG load failed, which gave the black screen.

**[V]** Fix: the build keeps the 223 RUS entries untouched (IDs 1001–1223), appends the 150 JP-only CGs (IDs 1224–1373) with their parent IDs remapped by name, and keeps the header and sections. Tested in game: scene 1 (`0000-op1`), scene 2 (correct newspaper CG) and further scenes play normally.

## Scene Scripts

### Instruction format

**[V]** (round trip of all 264 RUS and 268 JP scripts through `lucascript` is byte-identical)

```text
u16 length   (header included, padding excluded)
u8  opcode
u8  flags    (bit 0: a u16 debug line number follows; MESSAGE uses flags 3)
[u16 line]   source line number, for debugging only
body ...
[00]         one pad byte if length is odd
```

Strings inside bodies are `i16 -n`, then n bytes (Shift-JIS/ASCII), then NUL. Example: `f9ff 61312d372d3268 00` is `"a1-7-2h"`.

### Control flow

**[V]** Jump targets are absolute byte offsets inside the same script. All 1,840 RUS and 1,843 JP jump fields point at instruction starts. The opcodes are the same in both builds:

| Op | Meaning | Body |
| --- | --- | --- |
| 15 | GOTO | u32 target |
| 16 | jump by choice result | str (condition, e.g. `#28001`), u16, u32 target, then (u16, u32 target)* |
| 18 | GOSUB-like | str, u32 target |
| 19 | IF | str (e.g. `#6069!=0`), u32 target |
| 21 | JUMP to another script | str (script name) |

**[V]** No script refers to a label by name; the executable does (the ending list, see [Label table](#label-table)).

### Text instructions

**[V]** MESSAGE (op 36), body after the debug line:

| Build | Layout |
| --- | --- |
| JP | u16 line index, u16 voice ID, u16 n + UTF-16 JP text + `00 00`, 5-byte tail |
| RUS | u16 line index, u16 voice ID, JP text (same encoding), **"EN" slot as i16 -n + UTF-8 + `00`**, **the same text again as u16 n + UTF-16 + `00 00`**, 5-byte tail |

- Empty strings are a bare `00 00` with no terminator.
- The two RUS copies are equal in 17,532 of 17,534 messages. The Russian translation lives in this "EN" slot; the game runs with `language=english`.
- Tail: u8 flags (`0x0B`, `0x03`, `0x05`), u16 per-line value (JP: always 10; RUS: varies in steps of 10; **[H]** auto-mode timing), u16 0.
- Text markup: `@Name@` speaker prefix, `$d` separator, `$[base$/ruby$]` ruby.

**[V]** SELECT (op 40): 8-byte head (u16 `0x6D61`, u16 **flag slot**, u16 index in script, u16 `0x4000 | first bit` in the script's chosen-option bitmap, see [Read Flags and Saves](#read-flags-and-saves)), JP text (`$d` between options), then in RUS **two UTF-16 copies** of the Russian text, then a tail (u16 0, u16 number of options). A select uses one flag slot per option. RUS slots run up to 196; JP slots differ (only offsets like +2, −34 between matching selects).

**[V]** Op 43 is another text instruction (RUS adds Russian slots). It does not occur in the ported scenes.

### Metadata entries

**[V]** `SCRIPT.PAK` also holds `_varset_システムフラグ`, `_arflag` (bitmap sizes per script, see [Read Flags and Saves](#read-flags-and-saves)), `_varstr` (scene headings, see [Scene titles](#scene-titles)), `_varnum`, `_varname`, `_colorbg`, `_scr_label`, `_task`, plus `_build_time`/`_varstrname` (RUS) or `_build_count` (JP).

- `_varname`: u16 ID + NUL-terminated name. 134 names are common to both builds; IDs 6044–6069 are shifted by −1 in RUS (e.g. `SNOW` is 6069 in JP and 6068 in RUS).
- `_scr_label`: the script labels, see [Label table](#label-table).

**[V]** The early unpacked folders `SCRIPT_RUS_unpacked/` and `SCRIPT_CHS_unpacked/` (now in `local/legacy/`, outside git) lack 9 and 8 of these metadata entries, so they cannot be repacked. The build reads the archives directly; `python -m cartagra_patch.lucapak unpack <pak> <dir>` extracts every entry for inspection.

### Label table

**[V]** `_scr_label` is `LZW\0`, u32 total size, u32 chunk count, then per chunk u32 code count, u32 output size and 16-bit LZW codes (new codes from 257; one chunk in both builds; `lucascript.lzw_pack` reproduces both entries byte for byte). It decodes to an empty line, then one line per script in entry order (line *n* = resource ID *n*), then two empty lines: `LABEL:offset,` (JP) or `LABEL:offset(source line),` (RUS), UTF-8, `\r\n` between lines.

**[V]** (2026-11-02, disassembly of the Steam `CARTAGRA.exe`) The Extras ending list (`task::EndingList`) is an array of 18 entries of 0xE0 bytes (built at `0x160e0`): index, unlock flag (`0x2f00`..`0x2f11`), script name, label (empty for most) and titles in three languages. Playing an entry looks up the label in the script's line of `_scr_label`, reads the number after `:` (the part in parentheses is skipped) and starts the script with the program counter set to that number (`0x25c2e0`; the instruction decoder reads `u16 length` at that offset). Endings with a label (position in the list, English title):

| Position | Title | Script | Label |
| --- | --- | --- | --- |
| 2 | Nana's Delight | `0210-12-01h` (ported) | `ENDING` |
| 4 | Rin's Joy | `0210-99-01` | `ENDING` |
| 9 | Light in the Darkness | `0218-01-04` | `ENDING` |
| 10 | Toji's Love | `0221-99-01` | `ENDING` |
| 11 | Epilogue | `0223-01-01` | `ENDING` |
| 14 | Departure | `a1-6-1` | `DEFAULT` |
| 15 | True End | `a1-6-1` | `ENDING` |

The other eleven start at the beginning of their script; among them Holy Slave (`0210-10-00`, ported) and Grand Epilogue (`0308-02-00`, start sequence edited).

**[V]** JP offsets are exact: all 393 are instruction starts. RUS offsets are not: 8 of 359 are instruction starts, and all 7 ending labels point into the middle of a message (for example `ENDING:1782(48)` in `0210-12-01h`, where line 48 is at offset 2762). They fit the English Steam scripts, which the translation made longer. The source line still places a label: it stands before the first instruction with a higher debug line number. Checked on the 18 scripts with the same instruction count in both builds: for all 48 labels they share, this rule gives the instruction at the JP offset.

The build writes the table anew (`script_port.rebuild_scr_label`):

- **Target scripts** (unchanged or edited by the build): each label goes before the first instruction after its source line, followed through the build's edits (instructions aligned on opcode and line; an instruction that was removed maps to the next one).
- **Ported scripts**: the JP labels with their exact offsets, followed through the port (ops translated by the opcode map; a label on a dropped op lands on the next instruction). Labels that only the target has (only `ENDING` of `0210-12-01h`, added by Steam) go after the message that precedes them in the target script, found in the ported script by its Russian text (`После операции...`). Steam's script has an `IF (#30021)` block there that the JP script lacks.
- The 4 added scenes get lines for their resource IDs 265..268.

Result for `ru`: 400 labels, all instruction starts; 351 of the target's offsets corrected. The build stops if a label cannot be placed.

**[V]** In game (2026-11-02, Extras > Endings, endings unlocked in the user's profile: 5 of 18): Nana's Delight starts on the cloud background with «Меня увезли из Токио в реабилитационную клинику в глуши.» (the line after «После операции...»); Light in the Darkness on the candle-lit corridor («Узкий проход разинул свою пасть...»); Epilogue with text on black («Растаял покрывавший улицы снег...», no picture command between the label and this line), then the station scene. Powerless (no label) plays from the start. Text advances; memory stays at about 1.0-1.06 GB; "End playback?" returns to the list.

## Porting Scripts from JP to RUS

`script_port` converts a JP scene script to the RUS dialect. Every rule below was measured by aligning all scripts that exist in both builds.

### Opcode map (JP → RUS)

**[V]** Derived from the 65 scripts with equal instruction counts, then checked by argument shapes.

| JP | RUS | JP | RUS | JP | RUS |
| --- | --- | --- | --- | --- | --- |
| 1–48 (all used ones) | same | 54 (image load) | 55 | 79 | 80 |
| 51 | 52 | 57 (move) | 58 | 106 | 107 |
| 52 | 53 | 61 | 62 | 111 (SE) | 113 |
| 63 | 64 | 70 | 71 | 115 | 117 |
| 71 | 72 | 73 | 74 | 117 (movie) | 119 |
| 74 | 75 | 78 | 79 | 121 | 123 |
| 122 | 124 | 132 | 138 | 129, 130 | **none: dropped** |
| 62 | 63 | 118 (mark CG as seen) | 120 | | |

JP 130 sets a save thumbnail from `EVENTCG_SAVE.PAK` (argument = EVENTCG_SAVE ID); JP 129 appears at scene ends (**[H]** scene-replay marker). Neither exists in the RUS build. A jump that targets a dropped instruction is redirected to the next kept one.

### Argument changes

| Instruction | Change |
| --- | --- |
| MESSAGE (36) | add the RUS text slots; remap the voice ID by clip name |
| SELECT (40) | add the RUS text slots; give it **new flag slots from 197** (every ported select is new to RUS) |
| Image load (JP 54) and JP 74 | image ID at body[2:4] remapped by archive and name |
| JP 118 → RUS 120 (mark CG as seen, for the gallery) | image ID at body[0:2] remapped |
| JP 57 → RUS 58 | u8 at body[3] becomes a u16: 0→1, 1→2, 2→3, 10→33 (3,211 aligned instances; other bytes unchanged) |
| Op 3 | JP stores the value as a decimal string (`ffff "1"`); RUS as `fe7f` + i16 |
| Ops 1, 3 | variable ID remapped by name (`_varname`) |
| Ops 16, 18, 19 | `#NNNN` variable references in the condition string remapped |
| Jumps (15, 16, 18, 19) | targets relocated to the new layout |

**[V]** Unchanged: music and SE IDs (identical order), debug line numbers, movie names.

### Text for the Russian slot

The build picks, in order:

1. the `translation` column of `languages/<lang>/translation/<scene>.tsv` (columns `row kind voice jp translation`; older tables: `ru`, extra columns ignored);
2. an existing Russian line whose JP text is identical (same scene first, then any scene; 16,504 known lines);
3. the JP text as a placeholder, with the `@speaker@` tag translated when known (37 names).

**[V]** Translations added on 2026-10-26: `local/cartagra_fhd_jp/` (local only, not in git) holds a Russian translation of the whole JP game, one `<script>.txt` per script in the format of the Chinese patch's `SCRIPT_FHD/text/` (pairs of lines `offset|JP` and `offset|Russian`, `＄` = line break). For the 24 restored scenes its lines matched the tables one to one: same count (4,422) and identical JP text in the same order. Rules used to fill the `translation` column:

- Filled only rows with no translation yet (`todo`): 3,970 rows, all of which have a Russian line in the file. No row was left empty.
- The 452 rows that reused a line of the Russian release keep it. It was later copied into their `translation` column when the `source`/`existing` columns were dropped (same text, so `SCRIPT.PAK` stayed byte-identical). The file words 33 of them differently (mostly short lines like `ああ――`, and `Такако-чан` where the release writes `Такако-тян`).
- `0215-03-00` (an NVL-style passage): the JP lines end with a line break, which the file drops; the Russian release instead starts every line after the first with one. The 29 filled lines of that scene got the leading line break, so they match the 8 lines reused from the release.
- Latin look-alike letters inside Cyrillic words were replaced by the Cyrillic ones: 111 letters (`a` 96, `M` 8, `A` 5, `H` 1, `o` 1) in 77 words of 50 lines (`0210-03-01h`, `0215-05-02`, `0215-08-03h`, `0216-05-03h`, `0217-01-05h`, `0220-02-06h`), mostly moaning such as `Хьяaaaaа`. No word is written in Latin letters only. The release's own line in `0215-05-02` row 7 (`Aaаа`) is reused text and stays as shipped.
- Text kept as written otherwise. The file writes no ruby (27 JP lines have `$[...$]`), which is fine.

After the rebuild, no message in the Russian slot of `SCRIPT.PAK` contains kana.

### Validation

**[V]** Oracle test: 44 uncensored scripts were ported from JP and compared with the real RUS versions.

- All 264 jump targets landed on the same instruction index.
- Voice IDs matched 2,056/2,059.
- Image IDs matched 493/512. The differences are Steam's own sprite substitutions (`u*` for `s*` variants) and BG `h003c` for `h003a`.
- The remaining body differences are Steam re-tunings (move coordinates, extra SE parameters) or JP-only data.

This test found the op 3, op 74 and SELECT rules.

### Entering removed scenes

**[V]** The 4 removed scenes are entered by a script JUMP from a predecessor. The JUMP sequences of the JP and RUS predecessors align one to one, so the patch retargets only the aligned JUMP:

| Predecessor | Was | Now |
| --- | --- | --- |
| `0216-04-03` | `0217-01-00` | `0216-04-03h` (which exits to `0217-01-00`) |
| `0216-05-02` | `0216-05-04` | `0216-05-03h` |
| `0217-01-04` | `0217-01-06` | `0217-01-05h` |
| `0217-99-03` | `0217-99-05END` | `0217-99-04h` |

New scripts are inserted after the last original script, before the metadata entries, as in both original archives (all scripts first). Existing script indices do not move; the metadata entries move by 4 (nothing refers to them by number except their own `_arflag` record, which is renumbered). Until 2026-10-26 they were appended after the metadata, and the game then kept no read or choice flags for them (see [Read Flags and Saves](#read-flags-and-saves)).

## What Steam Censored

**[V]** Comparison of the image sequences loaded by each script (op 54/55, resolved to names): 144 of 264 common scripts load identical sequences. Most other differences are Steam additions (English eyecatch logos `eye_*_logo*en`, title cards) or sprite swaps. Censorship differences:

| Scene | RUS lines | JP lines | Existing Russian reused | Kind |
| --- | --- | --- | --- | --- |
| `0207-13-01H` | 12 | 86 | 1 | rewritten |
| `0207-13-03H` | 49 | 166 | 38 | rewritten |
| `0208-13-01H` | 8 | 351 | 8 | rewritten (3 choices) |
| `0210-03-01h` | 18 | 317 | 21 | rewritten (2 choices) |
| `0210-12-01h` | 74 | 155 | 67 | rewritten |
| `0210-99-02h` | 6 | 130 | 2 | rewritten |
| `0215-08-03h` | 14 | 115 | 8 | rewritten |
| `0215-10-02h` | 12 | 284 | 4 | rewritten (2 choices) |
| `0217-02-12h` | 36 | 234 | 34 | rewritten (1 choice) |
| `0220-02-06h` | 12 | 394 | 14 | rewritten (1 choice) |
| `0220-02-12H` | 12 | 253 | 13 | rewritten (1 choice) |
| `0221-99-02h` | 75 | 150 | 56 | rewritten |
| `a1-2-3h` | 19 | 114 | 20 | rewritten |
| `a1-7-2h` | 7 | 38 | 3 | rewritten |
| `a2-3-4h` | 37 | 134 | 31 | rewritten |
| `a2-5-2h` | 26 | 42 | 18 | rewritten |
| `0210-10-00` | 27 | 74 | 26 | H part cut from a story script |
| `0214-05-00` | 45 | 312 | 40 | H part cut |
| `0215-03-00` | 16 | 37 | 8 | H part cut |
| `0215-05-02` | 26 | 35 | 22 | H part cut |
| `0216-04-03h` | — | 230 | 5 | removed |
| `0216-05-03h` | — | 440 | 10 | removed (4 choices) |
| `0217-01-05h` | — | 212 | 1 | removed (2 choices) |
| `0217-99-04h` | — | 119 | 2 | removed |
| **Total** | | **4,422** | **452** | |

"Existing Russian reused" can exceed the RUS line count because one Russian line can match several JP lines.

**[V]** Steam's rewritten versions replace explicit lines with new, shorter ones. Those Steam-only Russian lines are dropped when the JP scene is ported.

## Start Sequence

**[V]** (scripts compared instruction by instruction, movies compared by duration and frames)

| | JP FHD | Steam (RUS) |
| --- | --- | --- |
| New Game starts | `0000-op0_HD` (**[H]** the first script; the JP executable names no script) | `0000-op1` (the executable contains the string `0000-op1`) |
| `0000-op0_HD` (prologue: 36 narrated lines over CGs, op 43, no interface) | ends with the opening movie, then JUMPs to `0000-op1` | the same prologue with Russian text in all 36 lines; ends with the same opening movie and returns (op 20). Called (op 22) only by `0308-02-00` |
| `0000-op1` (the burial) | entered from the prologue | entered from New Game |
| `0209-08-00` | JUMPs to `0209-09-00` | plays the Rengoku movie first (plus `#12054 = 1` and a pause) |
| `0308-02-00` (before part 2, routes `a1`/`a2`) | plays the Rengoku movie, then JUMPs to `a1-1-1` or `a2-1-1` | calls `0000-op0_HD` (prologue + opening) instead |

Movies: Steam swapped the file names. Steam `cartagra_movie_02_en` (110.7 s) is the JP opening `cartagra_movie_01` ("Sea of Solitude", 112.0 s) with English credits; Steam `cartagra_movie_01_en` (139.8 s) is the JP Rengoku movie `cartagra_movie_02` (138.3 s), re-edited. So the Steam scripts already play the right file in each place, and the patch needs no movie files.

`0000-op0_HD` in the Steam build starts with a "watch / skip the prologue" choice (`プロローグを見る$dプロローグを見ない`). It is preceded by `#12052 = 0` and `IF (#12052)`, which jumps over it, so it is never shown (**[H]** op 19 jumps when the condition is false, as the if/else blocks elsewhere show; not checked in game).

The patch restores the JP order without changing the executable (`definitions/restoration.json`, `start_sequence`):

1. `0000-op1`: a call of `0000-op0_HD` (op 22, like Steam's own call in `0308-02-00`) is inserted after the setup instructions (op 26 to op 27). The prologue plays, returns, and the burial follows.
2. `0308-02-00`: both calls of `0000-op0_HD` are replaced by the Rengoku block taken from `0209-08-00` (movie, op 123, `#12054 = 1`; without the pause), as in JP.
3. `0209-08-00`: the Rengoku block (movie, op 123, `#12054 = 1`, pause) is removed; jumps to it go to the following JUMP.

Ops 25 and 119 carry a marker ID (`0x8000 | n`, unique and ascending in script order in every script of both builds, mostly 0, 1, 2...; the bit of the "passed markers" bitmap, see [Read Flags and Saves](#read-flags-and-saves)). The two edited scripts are renumbered from 0, which gives the JP numbering. The build checks that JP `0000-op0_HD` leads to `0000-op1`, that `0308-02-00` is the only caller of the prologue and that the movie block has the expected instructions; otherwise it stops.

**[V]** Checked in game by the user on 2026-10-26 ("everything works").

## Read Flags and Saves

**[V]** Where the Steam build stores its data: through the Steam API, which the bundled emulator (`steam_api64.dll`, settings in `steam_settings/`, account ID 22202) redirects to `%APPDATA%\GSE Saves\4290390\remote\`:

| File | Contents |
| --- | --- |
| `data000.dat` | System data (`SAVEDATA` magic; the log line `SYSDATA_SIZE=22405` at startup): global settings and flags, then one record per script (below) |
| `dataNNN.dat`, `.info`, `.thm` | Save slots (NNN = slot), their header and thumbnail |
| `config.dat` | Options |

The empty `userdata\22202\` folder in the game folder is created by the emulator and is not used by the game. `%APPDATA%\PROTOTYPE\CARTAGRA\savedata\` only holds `config2.dat`. The JP release saves to `%APPDATA%\PROTOTYPE\<title>\savedata\` instead.

**[V]** Per-script record in the system data, in `SCRIPT.PAK` order: NUL-terminated script name, then three bitmaps, each u32 byte count + bits (1 bit each), then u32 0:

1. **read lines**: bit = MESSAGE/op 43 line index. "Skip read text" skips a line only when its bit is set;
2. **chosen options**: each SELECT owns `2 * options + 1` bits from the first bit in its head (u16 at [6] = `0x4000 | first bit`). Bit `first + k` is set once option k has been chosen (in game: choosing option 0 set bit 0, choosing option 1 set bit 1); the other `options + 1` bits were never seen set (**[?]** meaning unknown). The game shows chosen options in another text color only when Options > Text1 > "Color of Previously Read Text" is "Only Choices" or "On" (see below);
3. **passed markers**: bit = marker ID of ops 25 and 119 (`0x8000 | ID` in the first u16).

**[V]** The bitmap sizes come from the `_arflag` metadata entry of `SCRIPT.PAK`: 16-byte records `u16 16, u16 0x011F, u16 0, u16 script number (entry index + 1), u16 lines, u16 select bits, u16 markers, u16 0`. Each value is the highest index used + 1 (`lines` = highest line index + 1, `select bits` = end of the last select's range, `markers` = highest marker ID + 1). This rule reproduces all 264 script records of the RUS build and all 268 of the JP build; one more record each (the last) belongs to `_varset_システムフラグ` (0, 0, 4).

**[V]** Bug fixed on 2026-10-26: the patch did not update `_arflag`. The 20 ported scenes kept the sizes of Steam's short versions (for example `0208-13-01H`: 8 lines instead of 351), the 4 added scenes had no record, and `0308-02-00` kept 3 markers instead of 5. The user's system data showed exactly those sizes. Reported in game: "Skip read text" skipped unread text, and chosen options were not remembered. **[H]** Lines and options beyond a bitmap count as read and their bits are not stored. The build now recomputes the record of every script and adds records for new scripts (`script_port.rebuild_arflag`; a no-op on the unmodified RUS `SCRIPT.PAK`). The new values of the 24 restored scenes equal the JP records.

**[V]** The game keeps per-script records in the system data only for the scripts before the metadata entries (up to the `_varset...` record, which is last in both originals). With the 4 added scenes appended after the metadata, they got no records even with `_arflag` records. The build therefore inserts new scripts before the metadata entries and writes the records sorted by number.

**[V]** Existing system data is migrated: with the new `SCRIPT.PAK` the game read the user's `data000.dat` (written with the old sizes) and on the next save wrote every record with the new size, keeping all old bits (20 restored scenes resized; nothing else changed).

**[V]** The system data is written to disk when the player saves (also quick save), not when the game quits. Read lines and choices after the last save are lost on quitting. This is the game's behaviour, not the patch's.

**[V]** In-game test, 2026-10-26 (test build starting in the added scene `0217-01-05h`, window 1280×720):

- SKIP is greyed out on unread lines. After reading 11 lines, returning to the title and starting again, SKIP was enabled and stopped exactly at the last line read.
- After fast-forwarding to the first choice and choosing the first option, SKIP (read text only) ran through all 68 lines up to the choice. (The darker box of that option seen then is not the chosen-option marker; see the next paragraph.)
- After a quick save, `data000.dat` had records for all 4 added scenes; `0217-01-05h` had 69 read bits and the choice bit set.
- The user's save folder was restored from the backup afterwards, and the normal build reinstalled.

**[V]** Chosen options in another color (user report after the fix, with a screenshot of the JP game: the chosen option's text is purple). This is an option, not a bug: Options > Text1 > "Color of Previously Read Text" = Off / Only Choices / On, plus "Read Text Color" (a slider from yellow to purple; default purple-blue) when it is not Off. It was Off in the user's `config.dat`, so no chosen option was colored, in native Steam scenes too. Checked in game on 2026-10-26:

- Off: in native `0207-06-00` (the user's data: both options chosen before, bits `03`) both options white.
- On: both options of that choice in lavender (every previously read line is colored).
- Only Choices, in the restored `0217-01-05h` (test build, record empty): both options white; after choosing the second option and coming back, that option was lavender (text pixels about (160,160,255)) and the first stayed white, as in the JP screenshot.

## Interface Text and Images

### Strings in CARTAGRA.exe

**[V]** (2026-10-26, `exe_text` on the Russian release's `CARTAGRA.exe`) The interface strings are NUL-terminated UTF-8 strings in `.rdata`, one per language: Japanese, Simplified Chinese and English, picked by the Text1 "Language" option. The Russian release uses the English slot (the Russian text of the scripts is there too), so the interface showed English.

**[V]** Each string is loaded by `lea r64, [rip+disp32]` (`48`/`4C` `8D`, ModRM `05`..`3D`); a string used in several places has several loads. The month names of the save screen are read from a pointer table in `.data` (absolute addresses, DIR64 base relocations). `exe_text.PE.references()` finds both kinds.

**[V]** The Russian translators used the same method for the 58 strings of the prologue text: a section `.rtransl` (RVA 0x194E000, 0x2000 B) with Russian UTF-8 strings, each loaded by a redirected `lea`. **[V]** (2026-11-03) Compared with the Steam executable (`CARTAGRA_backup.exe` in `Cartagra-2026-RU-Steam/`: the same sections plus Steam's `.bind` wrapper instead of `.rtransl`, `.text` not encrypted), the Russian `CARTAGRA.exe` differs only in the displacements of those 58 `lea` instructions; the original English strings are still in `.rdata`, unreferenced. `restoration.json` `exe_original_text` lists each `lea` with its original target (read from the Steam executable), and `exe_text.restore_original_text` points them back and removes the section: the result is byte-identical to the Steam executable in every section. The `en` build does this (language key `exe_original_text`), so a Russian exe in `inputs/en-steam/` gives an English one; an exe without `.rtransl` is used as it is.

**[V]** The table `languages/_original_steam/en/interface.tsv` (297 strings since 2026-11-03, with `No.%d`) was made from the Steam (Russian) release's executable only:

- English strings whose `lea` is within 768 bytes of a `lea` of a Japanese string (the code picks one of the three per language);
- the month names (pointer table);
- minus identifiers, file and resource names, format-only strings, debug messages, Steam interface names, the Dear ImGui debug interface (strings at RVA 0x4EF000..0x4F2000) and `『LUNA』` (used for Japanese too);
- plus 7 strings found missing in game: the linker merged identical strings, so `Window`, `Delete`, `Mouse`, `Font`, `Clear` and `All` of the game are stored among the Dear ImGui strings (their references come from both; the debug interface shows the translation too), and `Game Ver. `.

**[V]** `BGM`, `SE` and `MOVIE` are also referenced from the script command name table (pointers in `.data`), so they are not in the table.

Not translated: `Steam Deck: Proton ` and the date format `%s %d, %04d` (the month comes first; printf arguments cannot be reordered). `python -m cartagra_patch.exe_text list <exe>` lists every string the code refers to, with the number of `lea` and pointer references.

**[V]** Patch method (`exe_text.translate`):

1. Check the table: every `original` must equal the string at `id` (so a table made for another executable is rejected), the string must be referenced, and printf placeholders must be the same and in the same order.
2. Append a section `.uitext` (initialized data, read-only) after the last section: the translations as UTF-8, NUL-terminated, 8-byte aligned, identical texts stored once. For `ru` it is at RVA 0x1950000, 0x3608 B.
3. Rewrite the `disp32` of every `lea` and the value of every relocated pointer to the translation. The relocation entries stay valid (the loader adds the base delta to whatever value is there).
4. Update `NumberOfSections`, `SizeOfImage` and the PE checksum. The original strings and everything else stay unchanged (1,240 bytes differ in the original range: 307 references plus header fields).

The executable must not be signed or have an overlay, and must not already have `.uitext`. For `ru`: 277 of 296 strings translated, 307 references. After patching, every reference resolves to its translation (checked by re-reading the patched file).

**[V]** In game (2026-10-26, window 1280×720; the build tested had one more string translated, `Game Ver. `):

- start-up notice, all nine Options pages, the exit and back-to-title dialogs show the Russian text; labels fit (after shortening `Быстр. загрузка` and the notice);
- the interface font has no `«»` (blank); `❝❞` render as “ ”;
- the slider labels (`Slow`/`Fast`, `Solid`/`Clear`, `Auto`, the colour names of "Read Text Color" (`Orange`, `Yellow`, `Green`, `Blue`, `Purple`, `Red`), the scale labels of Text2 (`0 sec/char`, `0.1 sec/char`, `0 sec`..`3 sec`)) and the version label use a small font without Cyrillic: Russian text there showed as blanks or as `0 /`. They stay English;
- not reached: save/load dialogs, the voice collection, music and ending titles (locked on a new profile), the months on the save screen.

**[V]** In game (2026-10-31): the save date on the save and load screens (`%s %d, %04d`) uses a font without Cyrillic (FONT1, see [Fonts](#fonts)); the translated month showed as a blank (`. 31, 2026`). **[V]** 2026-11-02, with the months English again: `Oct. 27, 2026` shown. The load-confirmation dialog shows its Russian text. Since the build adds Cyrillic to FONT1 (`font_glyphs`), the months, the slider labels and `Game Ver. ` are translated again (**[V]** shown in game, see [Fonts](#fonts)).

**[V]** 2026-11-03 (user's screenshot of the load screen): the slot number `No.1` was still English. It is `No.%d` (RVA 0x50d4dc, one `lea` at 0x375f12, used for slots below 201), drawn with FONT0 size 40 (font argument 0x28) and right-aligned at x 390; the `ru` table now has `№%d`. **[V]** In game (user's screenshot, same day): the slot number still looked like `No.11`, because FONT0's `№` has the Japanese shape (N, small o, dot). Fixed in the font, see [Fonts](#fonts).

### Scene titles

**[V]** The heading above the text preview on the save and load screens (`Feb. 10`, `Chapter 1`) is not in the executable but in the `_varstr` entry of `SCRIPT.PAK`: 77 records in the instruction format (op 29, flags 1, line 0), each with the script name (`i16 -n` UTF-8 string), a u16 string variable ID (201..204) and the text in the three language slots (Japanese, English, Chinese), each `u16 n` UTF-16 code units followed by a NUL unit (`n` = 0: no characters and no NUL). 58 records have text: `Prologue`, `Chapter 1`..`4`, `Epilogue`, `Snow Camellia`, `White Clover` and short dates (`Feb. 6`..`Feb. 23`, `Mar. 10`, `Dec. 3`..`Dec. 25`); 19 are empty. The Russian release shows the English slot and left it in English. The JP `_varstr` has a different layout.

**[V]** Every save keeps its own copy of the heading in all three languages (UTF-8 at 0x92, 0x516 and 0x99a of `dataNNN.info`, next to the text preview), so saves made before the patch keep the English heading until they are overwritten.

Fix (`script_port.translate_varstr`, table `languages/<lang>/scene_titles.tsv` with columns `original`, `translation`): replace the English slot's text by the translation, keep the other slots; the build stops if a row's original is not in the target's `_varstr` and logs headings without a translation. Unchanged records stay byte-identical. For `ru`: 31 texts, 58 records (dates as «10 февраля», like the scene date picture; `Chapter n` → «Глава n»). Not yet seen in game.

### Interface pictures

**[V]** These pictures contain English text (exported and looked at); `languages/_original_steam/en/images.tsv` lists them (140 pictures with the manual pages) and `build.py --export-images` exports them:

| Archive (`files/image/`) | Entries | What they show |
| --- | --- | --- |
| `SYSCG.PAK` | `title_menu1`, `title_menu2`, `title_menu3` (CZ0) | Title menu: START, LOAD, OPTIONS, MANUAL, GALLERY, MUSIC, MOVIES, ENDINGS, VIDEOS, EXTRAS, BACK, EXIT |
| `SYSCG.PAK` | `title_extras` (CZ0), `extra_title` (CZ4), `extra_pt2`, `extra_pt`, `graphic_pt` (CZ0/CZ4) | Extras headings (EXTRAS, GALLERY, MUSIC, MOVIES, ENDINGS, VIDEOS), "Completion Rate", page numbers with "No." |
| `SYSCG.PAK` | `title_logo01_en`, `title_logo02_en` (CZ4), `title_bg02_en` (CZ3) | Logo with the tagline "An affliction of the soul..." (`CAUTION_TEXT` is only the background of the start-up notice, whose text is in the exe) |
| `resident/PARTS.PAK` | `options_tab_en`, `options_tab_en_oc`, `CONFIG_TAB1_en` (CZ1) | Options tabs |
| `resident/PARTS.PAK` | `system_menu_icon` (CZ1) | System menu (SAVE, LOAD, OPTIONS, TITLE, Q.SAVE, Q.LOAD, MANUAL, BACK, EXIT) |
| `resident/PARTS.PAK` | `legacy_pt_minimum`, `legacy_pt_full1` (CZ1) | In-game buttons (MENU, REWIND, SKIP, AUTO, BACK, NEXT, SAVE, LOAD, OPTIONS, VOICE, CLOSE, LOG, EXIT) |
| `resident/PARTS.PAK` | `save_bg_text_*`, `load_bg_text_*` (CZ1, palette) | SAVE and LOAD labels |
| `resident/PARTS.PAK` | `INDICATOR_ICON_*_en` (CZ1, palette) | "Jump" indicators |
| `resident/PARTS.PAK` | `pc_button_*` (CZ1) | Key names |
| `resident/PARTS.PAK` | `save_bg`, `load_bg`, `qload_bg`, `options_bg`, `system_menu_bg` (1920×1080 backgrounds) | Screen headings SAVE, LOAD, QUICK LOAD, OPTIONS, SYSTEM MENU (found in game 2026-10-31; the `save_bg_text_*`/`load_bg_text_*` labels are not shown in the PC layout) |
| `OTHCG.PAK` | `datewin_text_en` | Scene date labels (February 6th .. December 26th, 24 rows of 50 px) shown at the top left of a scene; `day_*` are Japanese only |
| `MANUAL.PAK`, `MANUAL_DECK.PAK` | `en_manual*`, `en_help*`, `deck_en_*` (CZ1) | Manual pages |

**[V]** `resident/PARTS.PAK` has the bytes `PARTS/\0` between the index and the first entry name, and the engine looks its pictures up as `PARTS/<name>`. `lucapak` used to drop them when rewriting an archive (the only Steam archive with such a prefix); the rewritten archive then crashed the game when the options screen opened. `LucaPak.name_prefix` now keeps them: all Steam UI archives and `SCRIPT.PAK` round-trip byte for byte.

**[V]** The engine loads CZ0 (64-byte header and raw RGBA rows) wherever another CZ type is expected: the Russian release replaced the Japanese `title_menu1`/`title_menu2` (CZ1) by CZ0 pictures, and they are shown. The build therefore writes replacement pictures as CZ0 (`cztool.encode_cz0`), keeping the original header's placement fields (offset, visible size, canvas). The stored width is rounded up to a multiple of 8 (for example 1144 for a visible width of 1140); exported PNGs have the stored size, and the build requires the same size. **[V]** In game: a recoloured `options_tab_en` (CZ1 in the original) written as CZ0 into `PARTS.PAK` was shown on the options screen. `cztool` now decodes CZ0 too and reads PNGs (8-bit, non-interlaced, all colour types, all filters).

**[V]** Translated pictures (`tools/image_text.py`, `languages/ru/images_text.json`). For each English text in a box:

1. The letters of the original are found by a threshold on alpha × luminance (light letters) or alpha × (1 − luminance) (dark letters). The English text is rendered with the chosen font (4× supersampled) and fitted to them: size from their height and horizontal scale from their width, or (`"fit": "width"`, long mixed-case lines) size from the width, optionally smaller with letter spacing making up the width; then the position is refined by correlation (±1.5 px).
2. The original look is measured as a premultiplied layer over the background as a function of the signed distance to the edge of the original letters (0.25 px bins, at least 8 pixels per bin): per bin, a least-squares fit of colour and alpha so that original = layer over background. On a black background the alpha is free, so it is set to cover the colour. Optionally the inside of the letters is measured per row (vertical gradient, `"fill": "rows"`) or per pixel, spread from the original letters (grunge texture, `"fill": "texture"`). The font's letters are thickened or thinned (±1.5 px) to the area of the original letters.
3. The English text is erased: the box is cleared (transparent sheets), or the letters and their effect are filled in from the surroundings (OpenCV Telea; the alpha of the fill is sharpened so that it does not leave a half-transparent haze where an icon meets transparency, and the effect is limited to the erased radius).
4. The translation is drawn at the same size and baseline, keeping the left/centre/right edge; when too wide, its letters are first moved closer (`tighten`), then squeezed (to `min_sx`, 0.85-0.92) and then reduced until it fits the box (or `limit`/`max_w`); `"uniform"` gives all texts of a picture the size of the one reduced most. Vertical labels are rendered in a turned box.

Checked by re-rendering the English text the same way and comparing with the original (comparison sheets), then by eye. The built archives decode to exactly the rendered PNGs.

**[V]** In game (user's screenshot, 2026-10-31): the title menu is laid out horizontally and **each item is cut to the width the original English item covered** (its alpha extent in the 380-px cell: START 200, LOAD 185, OPTIONS 275, MANUAL 270, EXTRAS 237, EXIT 160 px), centred with a gap of about 26 px; the first Russian sheets (words up to about 345 px) were cut off (НАЧАТ, ЗАГРУ, НАСТРОЙ, БОНУСЬ, ВЫХО). The widths are not taken from the replaced sheets and are not a table in `CARTAGRA.exe`, `SCRIPT.PAK` or `PARAM.PAK` (searched as int16/int32/float, any stride up to 64, any constant offset, also at 1280 scale); where the engine gets them is unknown. The menu words are therefore fitted into those widths (`"keep_extent"`): one size per screen (title screen: about 0.8 of the English size, ЗАГРУЗКА squeezed to 0.75; Extras screen: nearly full size) and one squeeze per word in all three sheets, so that a word does not change size between button states.

**[V]** In game (2026-11-02, window 1280×720): the title and Extras menus show every word whole, also in the hover state; the options tabs, the system menu labels and both in-game button layouts (classic `legacy_pt_full1`, touch `legacy_pt_minimum`) are not cut. The headings drawn into the screen backgrounds share their space with other elements: on the save and load screens the slot number (`No.17`, right-aligned, up to three digits) starts at about x 265 (1920 scale), so the heading must end by x 240 (SAVE became ЗАПИСЬ; СОХРАНЕНИЕ would be about half size); the options heading must leave the gap to the first tab (ends by x 345); the quick load screen has no slot number. The scene date label (`datewin_text_en`) shows «10 февраля». The short date on the save screen (`Feb. 15`) is a table in the scripts, not a picture (see [Scene titles](#scene-titles)).

**[V]** User's screenshots (2026-11-02): ЗАГРУЗКА on the title screen and Б.СОХР./Б.ЗАГР. in the system menu looked distorted. Measured: ЗАГРУЗКА and МУЗЫКА were squeezed to 0.75 of their width (`min_sx` 0.75 for the title sheets), and every system menu label got its own fit: Q's tail made "Q.SAVE"/"Q.LOAD" look taller, so they were fitted at 26.6 px instead of about 34 and stretched to 1.46/1.39 to match the width (the other labels 1.06-1.15). Now (`same_fit`, `max_sx`, `tighten`): the labels of a group start from the median size, horizontal scale (at most 1.0 for the system menu) and baseline of the English fits; a word that is too wide first gets closer letters (up to 4% of the size per gap), then is squeezed to at most 0.9, then shrinks. The English text is still erased and measured with each item's own fit. Result: the system menu labels have one size (37.3 px), none stretched; the title screen words are about 0.68 of the English size (0.77 before), ЗАГРУЗКА squeezed to 0.91; the Extras words about 0.85 (МУЗЫКА 0.89). **[V]** In game (2026-11-02): the system menu labels have one size and baseline in the normal, hover and disabled states; ЗАГРУЗКА fills the same width as before but is lower (width/height 5.7 instead of 5.0 on screenshots).

**[V]** User's screenshot (2026-11-02): the title menu words are spaced unevenly (gaps 83, 71, 76, 132, 112 px at 1920 scale). The layout model (buttons cut to the English widths 200, 185, 274, 269, 235, 159 px, 26 px apart, centred) reproduces the word positions within about 8 px. Each Russian word started at the English word's left edge, so the spare room of each button ended up on different sides. `menu` (tool): the words of each menu are placed by a linear program (most even gaps, then the most room to the button edges), the same place in every state. At the old size the buttons allow 83, 72, 100, 101, 101 (ЗАГРУЗКА and ВЫХОД fill their buttons and cannot move); with the words 10% smaller (title) and 5% smaller (Extras, order Gallery, Music, Videos, Endings, Back) the gaps are 104, 104, 111, 111, 111 and 92, 92, 92, 86 px. **[V]** In game (2026-11-02, screenshots measured at 1920 scale): title gaps 106, 109, 115, 115, 118 px, Extras 109, 109, 108, 102 px (wider than the model because the faint glow is not counted as ink); words do not move on hover; equal baselines.

### Fonts

**[V]** The Steam release has three bitmap font sets: `SYSFONT.PAK` (system: Gothic 18, Mincho 20/40/42/44, vertical Mincho 44), `font_win32_1920/FONT0_*` (sizes 16, 20, 24, 40, 42, 44) and `font_win32_1920/FONT1_*` (sizes 35, 37, 52, 56, 72); each FONT set has five faces (`GOTHIC1` ゴシック, `GOTHIC2` 丸ゴシック, `GOTHIC3` 太丸ゴシック, `MINCHO` 明朝, `MODERN` モダン) and one `FONTn__INFO.PAK` with an `info<size>` entry per size, shared by the faces. SYSFONT and FONT0 have Cyrillic (66 letters А-я, Ё, ё; FONT0's were added by the Russian translators, 7,193 glyphs); **FONT1 has none** (1,263 glyphs: Latin, Latin-1, kana; size 72: 235, no kana).

**[V]** Info entry (283,731 B for 7,193 glyphs): `u16 size, u16 line height, u16 100, u16 glyph count`; per glyph `u8 a, u8 width, u8 c`; `u16[65536]` character → glyph (0 = none); `u16[65536]` character → `width << 8 | a` for characters with their own width (Latin, Cyrillic). Width = advance (ink end + 1). `c` is about size / 9 for letters and 0 for digits and punctuation. `a` is 0 except for Cyrillic, where it is about (size − width) / 2, yet the ink starts at the cell's left edge (SYSFONT too): the engine does not crop at `a` (Cyrillic in FONT0 and SYSFONT displays correctly). Sheets: CZ2, glyph *i* in the cell at column *i* % 100, row *i* // 100, cells size + 1 px square, sheet width 100 × cell + padding (FONT1 37: 3808 × 495).

**[V]** CZ2: header (`CZ2\0`, u32 header length 18, u16 width, height, bits 8, u16 4, u16 0), a 256-entry RGBA palette (white; alpha rising with the index, 247 distinct values; the same in every font sheet), u32 block count, per block u32 compressed bytes and u32 raw bytes, then the blocks. Each block is LZW over the indices: codes packed LSB first, each a flag bit and 15 bits (flag 0) or 18 bits (flag 1); the dictionary starts with the 256 bytes, new entries from 257, one per code after the first; a block ends after 261,885 codes (dictionary at 2¹⁸ − 3), and the next block starts with a new dictionary. `cztool.decode_cz2`/`encode_cz2` re-encode `明朝37` (FONT1), `明朝72` and `システム_明朝20` byte for byte.

**[V]** In game (2026-11-02, user's screenshot and the earlier tests): labels drawn with FONT1 show translated text as blanks: the bottom bar of the options, save and load screens (`Defaults`, `Close`, ...), the slider labels, the version label and the save date. **[V]** FONT1's Latin letters are FONT0's design at a smaller size: FONT0 44 scaled by size / 44 (bicubic) lands within 0.6 px of FONT1's own glyphs (centroids), slightly softer at 72.

Fix (`fonts.add_glyphs`, language key `font_glyphs`): for every FONT1 size, append the missing letters as new glyphs (indices after the last), with `a` and width scaled from FONT0 44 and `c` as for FONT1's letters; for every face, resample FONT0 44's glyph cells to the FONT1 cell and append them to the sheet (one more row of cells), written as CZ2 again. Output: `FONT1__INFO.PAK` and the five `FONT1_*.PAK` (2.1-2.6 MB → 2.3-2.9 MB).

**[V]** In game (2026-11-02, Mincho face, window 1280×720): the game starts and shows Russian in every FONT1 label checked: the bottom bars of Options, Save, Load, Gallery, Music and Videos (По умолчанию, Удалить, К последнему, Выбрать музыку, Назад), the slider labels (Медленно/Быстро, Непрозрачно/Прозрачно, the colour names, 0 сек/симв., 0 сек..3 сек, Авто), «Версия игры 1.0.0.1» and the save date «окт. 27, 2026». The colour slider shows Yellow at both ends in the original too (`Yellow` has two references, `Orange` one). **[V]** The right-hand bottom box keeps its left edge where the English "Close" box starts and grows to the right: «Закрыть» ran off the screen, so `Close` is «Назад» (as wide as "Close"); the left-hand boxes and the page bar adapt. The other faces were checked only in rendered previews.

**[V]** FONT0's `№` (U+2116, glyph 811 in every size, a full-width cell without a width of its own) has the Japanese shape, which reads as `No.`. Fix (`fonts.redraw_numero`, language key `font_numero`): in every size and face, compose a Cyrillic-style sign from the face's own `N` and `o`: N (narrowed when the sign would not fit the cell), an o scaled to half the cap height, top-aligned with the N, and a bar under it (7% of the cap height thick); the advance becomes N + gap + o + side bearing, at most one cell (size 40: 41 px instead of 40), stored in the width table and the glyph's cell entry. Only glyph 811 changes (checked: 748 pixels of the size-40 Mincho sheet, all in its cell); each sheet is decoded and re-encoded whole (about 5 s; the re-encoding of an unchanged sheet is byte-identical). Output: `FONT0__INFO.PAK` and the five `FONT0_*.PAK` (13-18 MB each; about 2 minutes of build time). Rendered previews of Mincho, Gothic and Modern at sizes 20, 40 and 44 look right. Not yet seen in game.

## EVENTCG.PAK Comparison

**[V]** From the archives (names and sizes):

| Set | Count |
| --- | --- |
| In both versions | 214 (170 same size, 44 different) |
| Only in JP (appended by the patch, IDs 1224–1373) | 150, all referenced by the ported scenes |
| Only in RUS (kept) | 9: `pkg_cs`, `pkg_sos`, `e033k2`, `e064k1`, `e064k2`, `e064k3`, `eh001k0`, `eh055k0`, `ne013` |

**[V]** 68 RUS entries have a parent ID. `eh088k1` has a parent in JP (`eh088`) but none in RUS, because `eh088` is missing there.

### Files only in the JP version (150)

By prefix: `eh*` 132, `e04x` 4, `e05x` 7, `e06x` 2, `ne0xx` 5.

- `e047k1`, `e047k2`, `e048`, `e048k1`, `e052`, `e052k1`, `e055`, `e055k1`, `e056`, `e057`, `e057k1`, `e061`, `e068`
- `ne009a`, `ne009b`, `ne011a`, `ne012a`, `ne012b`
- `eh001k3`, `eh001k4`, `eh002`, `eh002k1`, `eh003`, `eh003k1`, `eh004`, `eh005`, `eh005k1`, `eh006`, `eh006k1`, `eh007`, `eh008`, `eh008k1`, `eh010k1`, `eh010k2`, `eh011`, `eh013`, `eh014`, `eh014k1`, `eh015`, `eh015k1`, `eh016`, `eh016k1`, `eh016k2`, `eh017`, `eh018`, `eh018k1`, `eh018k2`, `eh018k3`, `eh019`, `eh019k1`, `eh019k2`, `eh020`, `eh021`, `eh021k1`, `eh021k2`, `eh022`, `eh022k1`, `eh022k2`, `eh022k3`, `eh022k4`, `eh026`, `eh026k1`, `eh027`, `eh027k1`, `eh027k2`, `eh027k3`, `eh028`, `eh028k1`, `eh028k2`, `eh030`, `eh031`, `eh032`, `eh033`, `eh033k1`, `eh033k2`, `eh034`, `eh034k1`, `eh035`, `eh035k1`, `eh036`, `eh036k1`, `eh036k2`, `eh036k3`, `eh037`, `eh037k1`, `eh037k2`, `eh037k3`, `eh039`, `eh039k1`, `eh040`, `eh040k1`, `eh040k2`, `eh041`, `eh041k1`, `eh041k2`, `eh041k3`, `eh042`, `eh042k1`, `eh042k2`, `eh043`, `eh044`, `eh045`, `eh045k1`, `eh045k2`, `eh045k3`, `eh046`, `eh047`, `eh047k1`, `eh048`, `eh049`, `eh049k1`, `eh050`, `eh050k1`, `eh055k1`, `eh072`, `eh072k1`, `eh073`, `eh074`, `eh074k1`, `eh076`, `eh076k1`, `eh077`, `eh077k1`, `eh078`, `eh079`, `eh079k1`, `eh079k2`, `eh079k3`, `eh082k1`, `eh085`, `eh085k1`, `eh085k2`, `eh086`, `eh086k1`, `eh086k2`, `eh087`, `eh087k1`, `eh087k2`, `eh088`, `eh088k2`, `eh089`, `eh090`, `eh090k1`, `eh091`, `eh091k1`, `eh093`, `eh093k1`, `eh094`, `eh094k1`, `eh095`

**[V]** The RUS build keeps 28 `eh*` entries. The JP build has 158.

### Common files whose size differs

**[V]** 44 common entries differ: 37 are censored edits and are now restored (see [Censored Images](#censored-images)); 7 are not censorship and stay RUS: `eh001`, `ne001n`, `ne001r`, `ne001v` (here RUS even adds an IV tube), `e033k7`, `e033k8`, `e033k9`.

## Censored Images

**[V]** Method (2026-10-26): every image whose data differs between the builds, in every image archive, was decoded with `cztool` (variants composited onto their parents) and compared as a pixel-difference map (share of pixels differing by more than 48 levels, bounding box of the difference). Each candidate was then judged visually at full resolution in the differing region.

| Archive | Differing pairs | Censored (restored) | Not censorship (kept RUS) |
| --- | --- | --- | --- |
| EVENTCG | 44 | 37: 35 in place, `e047` split, `e007k0` (Steam-only frame) taken out of use | 7: `eh001`, `ne001n/r/v`, `e033k7/k8/k9` |
| OTHCG | 55 | 16: `f001c`, `f001e`, `f001f`, `f001fk1`, `f008`, `f008d`, `f017a`, `f017ak1`, `f022f`, `f027c`, `f027m`, `f035`, `f037ck6`, `f037ck7`, `f047`, `f050` | 39: English localization (`CHAPTER_*_TEXT`, `datewin_*`, `day2_*`, `eye_*_logo*`, `op_credit*`, `op_insert_*`) and palette images that decode identically (`000`–`005`, `g001*`) |
| CHARCG | 67 | 0 | 67 `u*` sprites: different expressions and redraws that the RUS scripts rely on (Steam reorganized these sets); no ported scene uses them |
| BGCG, SYSCG | 1 + 11 | 0 | title screens, caution text, logo (localization) |

Kinds of censorship found:

- Nudity covered or reframed: `e003`, `e003k1`, `e007`, `e039`, `e051`, `e053`, `e060`, `e067`, `eh001k1`, `eh001k2`, `eh012`, `eh025`, `eh029`, `eh038k2`, `eh082`, `eh084`, `eh084k1`, `eh092`, `eh092k1`, `ne008a`, `ne010a`, `f001*`, `f017a*`, `f022f`.
- Gore removed: `e006`, `e007k1` (eye), `e010` (wound), `e016*` (hanging body), `e036`, `e036k1`, `e045` (top cropped: 1934 instead of 2160 px), `e046`, `f008*`, `f027*`, `f035` (bodies blacked out), `f037ck*`, `f047`, `f050`.
- Other: `e035k1`, `e035k2` (school uniform painted over); substitute pictures in the slot: `e047` (a clothed couple), `eh055` (a flower); `eh088k1` stored without its parent.

**[V]** How each is restored (rules in `definitions/restoration.json`, applied by `pipeline`):

1. **In place** (`censored_images`: 35 EVENTCG + 16 OTHCG). The JP data, metadata and parent (remapped by name) replace the RUS entry. The resource ID does not change, so every RUS script, the ported scenes and the CG gallery flags (op 120, "mark CG as seen") use the original. This was chosen only after checking that the unported RUS scripts load each image at the same points as the JP scripts. Geometry differs only for `e003k1`, `eh038k2`, `eh084k1`, `eh092k1` (overlay size and offset are in the CZ header, so nothing else changes) and `e045` (see below). `eh088k1` gets its JP parent `eh088` (appended).
2. **Split** (`split_images`). The unported RUS `0210-99-01` shows its substitute `e047` just before the scene, where JP shows nothing. The JP `e047` is appended as `e047_jp` (ID 1374), and only the ported `0210-99-02h` uses it.
3. **Target script fixes** (`script_fixes`, in place, no size change):
   - `0208-15-00`: Steam inserted its own frame `e007k0` (awl approaching, clothed body) and shifted the sequence. The JP script shows the large pan image of the corpse, then `e007k1`. The RUS script now shows `e007` (uncensored, same composition, static) and then `e007k1` where it showed `e007k0`. The JP 4368×2457 pan image is not used.
   - `0210-07-00`: the two moves after the `e045` load set y = −854 (for the 1934-px RUS picture). They are changed to −1080, as in the JP script (2160-px picture).

**[V]** In game: `f035` in `0207-15-00` (the scene in the user's report) shows uncensored, and the user confirmed the uncensored pictures in game.

## CG Gallery

**[V]** (2026-11-03) Extras > CG gallery is the entry `_cggallery` of `PARAM.PAK` (the JP release: `_cgmode`, same format), read once by `CARTAGRA.exe` at RVA 0x22970 (Steam build). Words are little-endian u16:

| Part | Content |
| --- | --- |
| Head | 3 words (0), number of slot lists (1), 1 word (1) |
| Slot list | count, then one word per slot: an image ID, or 0x10000 − k for picture group k (from 1); then one UTF-16 string per slot (all empty) |
| Groups | count, then per group: n, n image IDs |
| Ranges | per image archive: base ID (u32), n, n seen-flag numbers (0xFFFF = none); the reader stops at n = 0 or at the end |

The gallery shows 15 slots per page (the exe divides the slot number by 15 and by 5); the page indicator is drawn with the digits of `SYSCG/graphic_pt`, so the page count follows the slot count. A slot is unlocked when one of its pictures has its seen flag. The engine sets the flag from the image ID through the ranges when a script shows the picture, and with op 120 ("mark CG as seen"): the release's scripts use op 120 only 16 times and show most gallery pictures (for example `e001`) only with the image load instruction. The flags are 1,000 bits (`0x5859F0` in the exe, checked before every use).

| | JP | Steam (`ru-steam`) | Patched |
| --- | --- | --- | --- |
| Slots (pages) | 254 (17) | 185 (13) | 259 (18) |
| Pictures | 473 (EVENTCG 344, OTHCG 129) | 301 (EVENTCG 187, OTHCG 113, BGCG 1) | 484 |
| Highest seen flag | 523 | 380 | 532 |

The JP release shows 18 pages in game (user's screenshot) for its 254 slots; why is not known (its executable is a different, 32-bit build). The Steam gallery is in story order (EVENTCG and OTHCG mixed), the JP one lists EVENTCG first. Seen-flag numbers differ between the releases, so the save's flags stay valid only with the target's numbers.

`gallery.merge` (build step 1) keeps the target's slots, order and flags and adds the JP pictures, mapped by archive and name to the patched archives (`e047` → `e047_jp` and Steam's `e047`):

- a JP slot that shares a picture with a target slot adds its other pictures to that slot (for example `e001k3`, `eh001k1`–`k4`);
- a JP slot with only new pictures becomes a new slot after the slot that holds the previous JP slot (74 new slots, mostly the H-scenes);
- new gallery pictures get the free seen-flag numbers 381–532 in image ID order; the EVENTCG range grows to the 374 entries of the patched archive;
- left out: `f022b`, `f022j` (JP OTHCG pictures the patch does not add; no restored scene shows them).

**Previews.** `image/SYSCG2.PAK` holds one preview per slot (`CGGALLERY_CH01_001`...; JP `CGMODE_CH01_001`...), and the gallery takes the preview of slot k by image ID: `id_start` (63000) + k. The executable has no name for them. **[V]** In game (2026-11-03, user's screenshots), with only `PARAM.PAK` changed, slot 94 (page 7, slot 4) showed Steam's preview 94 but opened `eh029`, and almost every slot after the first new one was off the same way. `gallery.build_previews` therefore rewrites `SYSCG2.PAK` in the merged slot order: the target's preview of each target slot, the JP preview of each new slot. The two releases crop the previews the same way, but Steam's are 304x169 (visible 301x169, black margin) and JP's 320x170 (visible 306x170). The JP preview's visible part is scaled to 301x169 (`cztool.resize`, linear filter) and stored as CZ0 with a Steam header; the entries are renamed in order. The JP previews of H-scenes have white blobs over parts of the picture, as in the JP release.

**[V]** In game: 18 pages and the previously unlocked CGs (user's screenshot of page 7, with only `PARAM.PAK`). The rebuilt previews are not seen in game yet.

## Voice, Music and Sound Effects

**[V]** `VOICE.PAK`: 8,179 clip names are common, 1,901 exist only in JP `VOICE0.PAK`, and 4 only in RUS (`nur0006a`, `nur0006b`, `shu5001`, `tyu0008`). Same names have different IDs. The patch appends the 1,901 clips (IDs 8184–10084) and copies their `0x01`/`0x04` section values. Ported MESSAGEs get their voice IDs remapped by name; no ported line references an unmapped clip.

**[V]** MUSIC: identical names and order. SE: the JP list equals the first 236 RUS entries. No remapping is needed for music (op 106 → 107, u32 ID) or SE (op 111 → 113, u32 ID at body[1]).

## Sound Crash

**[V]** User report (2026-11-02): the game crashes at random moments while reading, mostly late in a route; after loading the save and skipping to the same place it goes on, and may crash later. Windows' Application log on this PC has 29 crash reports for `CARTAGRA.exe` (version 1.0.0.1, time stamp `0x6a3e8961` = the Steam executable) from 2026-10-31 on, all `0xc0000094` (integer division by zero) at RVA `0x2f42ba`; `%LOCALAPPDATA%\CrashDumps` holds four dumps (2026-10-31, 2026-11-02).

**[V]** The faulting function (`0x2f4220`) is slot 6 of the vtable of `cSoundCodec_Ogg` (RTTI): length of the sound in ms = `[codec+0x288]` (total samples, `ov_pcm_total`) / (rate / 1000), with the rate read from `[codec+0x5d8]+8`, the channel's `vorbis_info` (`ov_info`; 48000 if the pointer is null or the rate 0). It divides by zero when the rate read is 1..999.

**[V]** From the dumps (main thread): main loop `0x31dc39` → `0x1b4a59` → `0x23d021` (or `0x195bea`) → `0x1b4300` (start a sound: take a free channel from a static array of 0x8E8-byte codecs, open the Ogg with `0x2f1b70`, then, when the request has a value at `+0xfc`, ask the new channel's codec for its length, `call [rax+0x30]` at `0x1b441c`, to time a fade) → `0x2f4220`. In all four dumps the codec is one of the static channels and the rate divisor is 0. About 169 threads exist in every dump, 62 of them parked in the Ogg decoder (one per channel).

**[V]** The decoder thread of a channel opens the stream and then stores `ov_pcm_total` in `+0x288` and the `ov_info` pointer in `+0x5d8` (`0x2f25c7`, `0x2f25e6`); nothing clears `+0x5d8` when a sound ends (it is written nowhere else), and the length function takes no lock (it only unlocks at the end; the position function `0x2f4140` locks). So right after a sound starts on a channel that played before, the main thread can read the previous sound's `vorbis_info`, which `ov_clear` has freed: whatever the heap holds there becomes the rate. Timing decides it, which is why the crash is random and does not repeat when the same place is reached again. The code is the unchanged Steam code (the patch's executable differs only in its strings), so the unpatched Russian release has the same race; not tested unpatched.

**[V]** All game audio is 48000 Hz: `VOICE.PAK` (8,183 clips; 10,084 with the restored ones), `SYSVOICE.PAK`, JP `VOICE0/1.PAK`, `MUSIC.PAK` (44), `SE.PAK` (241), `SYSSE.PAK` (13), checked in the Vorbis headers.

**Fix** (`restoration.json` `exe_fixes`, applied by the build to `CARTAGRA.exe` after the interface translation, `exe_text.apply_fixes`; the build stops if the original bytes differ): at `0x2f4293` `je` → `jmp` (`74 08` → `eb 08`), so the function always takes its own 48000 default and never reads the pointer. For 48 kHz audio the result is the same; the stale pointer is not dereferenced at all. A length computed during the race may still come from the previous sound's sample count (`+0x288` is written first, so usually it is the new one); it only times a fade. Not changed: the position function (`0x2f4140`) also uses `vorbis_info` but under the channel lock, and no crash points there.

## CZ4 Image Format and Engine

- **[V]** EVENTCG and EVENTCG_SAVE entries are `CZ4`; OTHCG also has `CZ1` (palette) entries and SYSCG has `CZ0` entries. `cztool` decodes CZ0/CZ1/CZ3/CZ4 (after `czximage/cz2image.cpp`): header (u32 header length, u16 width/height/bits, u16 x/y offset of an overlay, canvas size), then LZW blocks (u32 count; per block u32 code count and u32 raw size; 16-bit codes). The LZW dictionary gets an entry for every code, including the first, starting from `"\0"`. CZ4 holds RGB rows followed by an alpha plane; each row is delta-coded against the previous one except at the start of each of 3 horizontal bands. CZ1 holds a 256-entry RGBA palette plus LZW indices (or raw RGBA). CZ2 (font sheets) is described under [Fonts](#fonts). Encoders: CZ0 (uncompressed), for replacement interface pictures (see [Interface Text and Images](#interface-text-and-images)), and CZ2, for the font sheets.
- **[H]** (strong) The engine is **LucaSystem** (Prototype). The PAK layout, `id_start` scheme and opcode list order match the LucaSystem tools shipped with the Chinese patch, including their opcode tables for other LucaSystem games.
- **[V]** The RUS font renders Japanese text (kanji placeholder lines display correctly in game).

## The Chinese Patch (Reference Implementation)

**[V]** From `Cartagra_FHD_CHS/patch/patch.cpp`: `CHSpatch.dll` hooks `CreateFileW` (MinHook). It redirects `PARTS.PAK`, `SYSCG.PAK`, `FONT.PAK`, `SYSFONT.PAK` and `SCRIPT.PAK` to `CHSPAK\`, patches `OTHCG.PAK`/`BGCG.PAK` reads in memory, and shows lyrics from `CHSPAK\LRC\`. `EVENTCG.PAK`, `EVENTCG_SAVE.PAK` and `files/SCRIPT.PAK` are not modified. So the JP files used here are the stock Japanese ones: `files/SCRIPT.PAK` holds the Japanese text, and the Chinese text is in `CHSPAK/SCRIPT.PAK`.

**[V]** The Chinese `pak.py` repacks by keeping the original header and order and rewriting only the index. That is the same principle as `lucapak`.

Repository contents: `pak.py`, `SCRIPT.PAK`, `SCRIPT_FHD/` (`solvev2.py` text extractor: text opcodes 0x24/0x28/0x2b/0x1d, plus `text/`), `image/` (CZ tools), `font/` (font generation, LucaSystem tools), `patch/` (DLL source), `writeback.py` (writes translations back with length padding), `uitext.py`, `genuitextcpp.py`, `checkformat.py`, `kouryaku/` (walkthrough).

## Patch Generation

`pipeline.run_build` (started by `build.py`, see [Command line](#command-line)). `<target>` is the input set of the language (`inputs/ru-steam/files/` for `ru`), `<jp>` is `inputs/jp-fhd/files/`:

1. **EVENTCG**: read `<target>/image/EVENTCG.PAK`, append the JP-only entries (`lucapak.append_missing`: parents remapped by name, xxh64 computed), replace the censored entries in place (`replace_from`) and append the split copy `e047_jp` (`append_copy`). Untouched entries are byte-identical and in their original order (verified).
   **OTHCG**: replace the 16 censored pictures in place.
   **Gallery**: add the JP gallery's pictures to `_cggallery` in `<target>/PARAM.PAK`, put the previews of `<target>/image/SYSCG2.PAK` in the new slot order (JP previews scaled for the new slots) and write both ([CG Gallery](#cg-gallery)).
2. **VOICE**: the same for `VOICE.PAK` with `VOICE0.PAK` as donor, copying section values.
3. **SCRIPT**: build the name maps (images over all target image archives with the new EVENTCG; voices with the new VOICE; variables from `_varname`), the translation memory and the first free select slot. Port the 24 scenes, check every jump target, write the translation tables, retarget the 4 predecessor JUMPs and insert the 4 new scenes before the metadata entries. Then apply the two target script fixes for censored pictures and restore the [start sequence](#start-sequence) (3 scripts). Write `_scr_label` anew ([Label table](#label-table)), translate the scene headings in `_varstr` ([Scene titles](#scene-titles)) and finally recompute `_arflag` for all scripts ([Read Flags and Saves](#read-flags-and-saves)). 242 of the 274 original entries stay byte-identical (2026-11-03).
4. **Interface**: read `<target>/../CARTAGRA.exe`, restore its original text when the language has `exe_original_text`, translate its strings when `languages/<lang>/interface.tsv` has translations (see [Interface Text and Images](#interface-text-and-images)), apply the executable fixes of `restoration.json` ([Sound Crash](#sound-crash)) and write it; write the table to `build/<lang>/interface.tsv`. Replace the pictures in `languages/<lang>/images/<archive>/` that differ from the exported originals in `languages/<interface_original>/images/` (byte comparison of the PNG files; without an exported original the pixels are compared). Archives already written by step 1 are modified there, others are read from `<target>/image/`; an archive is written only if a picture in it changed.
5. **Output**: write `BUILD_INFO.txt` and move the staging folder to `dist/<lang>/`.

**Obsolete (moved to `local/legacy/`, outside git, on 2026-10-26):** `pak_tool.py`, `create_patch.py`, `Patch/create_patch.py` and their outputs (`EVENTCG_patched.PAK`, `EVENTCG_patched/`, `PATCH_REPORT.md`). `pak_tool.py pack` rewrites the header (`id_start` = 1, sections dropped, entries sorted), which caused the bug. `create_patch.py` also replaced only `[:5]` of the 27 size-different files while reporting 27. The useful parts of `pak_tool.py` (`unpack`, `compare`) are now `lucapak` commands; there is deliberately no `pack` command.

## Build System

Refactored on 2026-10-26 so the project no longer depends on the game installations and can target more than one language.

### Layout

| Path | Contents | In git |
| --- | --- | --- |
| `build.py` | CLI: argument checks, input validation, progress, exit codes (0 OK, 1 failed, 2 usage error) | yes |
| `cartagra_patch/project.py` | Paths (all resolved from the project root, never from the working directory), language and definition loading, input validation (`check_inputs`), `BuildError` | yes |
| `cartagra_patch/pipeline.py` | `BuildOptions`, `run_build` (the steps above), `BUILD_INFO.txt` | yes |
| `cartagra_patch/lucapak.py`, `lucascript.py`, `script_port.py`, `cztool.py` | Format libraries and the porter (moved from the top level; code unchanged except for package imports, a pluggable `xxh64`, the `lucapak` CLI and neutral TSV column names) | yes |
| `cartagra_patch/exe_text.py` | Interface strings of `CARTAGRA.exe`: PE reader, references, table I/O and checks, adding `.uitext` | yes |
| `cartagra_patch/gallery.py` | The CG gallery table (`PARAM.PAK` `_cggallery`): reading, writing, adding the JP pictures | yes |
| `definitions/restoration.json` | What to restore: censored and removed scenes (with predecessors), censored images, split images, target script fixes, the start sequence, the New Game script. Moved out of the code; shared by all languages | yes |
| `definitions/inputs.json` | Required files per input set, with use (`data` = copied or patched, `index` = only entry names read), size, entry count and SHA-256; `optional` files (`../CARTAGRA.exe`, `image/resident/PARTS.PAK`) are required only by builds that use them | yes |
| `languages/<lang>/language.json`, `translation/`, `interface.tsv`, `scene_titles.tsv` | Language settings and status; translation tables; interface table; scene headings of the save screens ([languages/README.md](languages/README.md)) | yes |
| `languages/<lang>/images/` | Interface pictures to translate (PNG copies of the originals) | no (`*.png` is ignored) |
| `languages/_original_jp/` | Scene tables with the Japanese release's text (basis for new languages) | yes |
| `languages/_original_steam/en/` | Steam release interface originals: `interface.tsv`, `images.tsv` (pictures with text); `images/` (exported PNGs) | tables yes, PNGs no |
| `cartagra_patch/images.py` | Interface pictures: list, export, copying to a language, changed pictures | yes |
| `cartagra_patch/fonts.py` | Font info tables; copies letters from FONT0 into the small font set FONT1 (`font_glyphs`), scaled; redraws FONT0's `№` (`font_numero`); CZ2 decoding and encoding are in `cztool.py` | yes |
| `languages/ru/images_text.json` | The English texts in the interface pictures with their boxes and translations | yes |
| `tools/image_text.py` | Renders the translations into the pictures (needs Pillow, numpy, scipy, OpenCV; not used by the build) | yes |
| `tests/test_core.py` | Automated tests (standard library `unittest`) | yes |
| `inputs/<set>/files/` | Local copies of the original files | no |
| `build/<name>/staging/`, `build/<name>/translation/` | Archives while being written; the translation tables in the current format | no |
| `dist/<name>/` | Finished patch: `files/...`, `CARTAGRA.exe` (interface translated) + `BUILD_INFO.txt` | no |
| `local/legacy/` | Old tools, unpacked archives and outputs (kept for reference, not used) | no |

`<name>` is the language code, `<code>-test` for `--test-start` builds and `<code>-partial` for `--scenes` builds, so debug builds never overwrite a normal build.

### Guarantees

- **[V]** Inputs are only read. The build writes only below `build/` and `dist/`; the integration test checks that the inputs are unchanged after a build.
- **[V]** Input validation before any work: missing files, size, PAK header sanity, entry count, and SHA-256 for `data` files (a patched file in `inputs/` is reported, not used). `--skip-checksums` keeps the size and entry-count checks.
- **[V]** Reproducible: no timestamps or absolute paths in the output; two builds from the same inputs give identical files (integration test).
- **[V]** The refactored build produces the same bytes as the previous `build_patch.py` for `ru` (SHA-256 of all four archives compared, 2026-10-26).
- `dist/<name>/` is replaced only after the whole build succeeded, and only if it contains a `BUILD_INFO.txt` (a folder the build did not make is never deleted).
- TSV tables: the build reads `languages/<lang>/translation/` and writes to `build/<name>/translation/`; it never writes into `languages/`. Header: `row kind voice jp translation`. The build reads only `row`, `jp` and `translation` (by column name), so older tables with `source`/`existing` or `ru_existing`/`ru` columns still load. Which text a line gets (table, release line, Japanese) is reported in the build log, not stored in the tables.

## Language Targets

| Code | Input set | Status | Evidence |
| --- | --- | --- | --- |
| `ru` | `ru-steam` | incomplete | Built and tested in game; all restored lines translated, the 3,970 added lines not yet checked in game |
| `en` | `en-steam` | untested | Never built |

**[H]** The English Steam release is assumed to be the same multi-language build as the Russian one before translation: the same archives, opcode table and script names, with English in the "EN" text slot. If so, the same restoration rules apply and the porter fills the EN slot with existing English lines where the JP text matches. Unverified points:

- the file list in `definitions/inputs.json` (copied from `ru-steam`; no sizes, entry counts or checksums yet, so only presence and PAK headers are checked);
- whether the English `SCRIPT.PAK` has the same script names, predecessor JUMPs and free select slots;
- whether the English EVENTCG/OTHCG have the same censored entries at the same indices (the image comparison was done on the Russian release only);
- the two target script fixes (`0208-15-00`, `0210-07-00`) match by image ID and coordinates; the build fails with a clear error if they match nothing;
- the start sequence assumes the same Steam layout (`0308-02-00` calls `0000-op0_HD`, `0209-08-00` plays `cartagra_movie_01`); the build fails if it differs.

The build accepts `--language en`, but it fails at the input check until `inputs/en-steam/files/` exists.

## Test Results

Test setup: `CARTAGRA.exe`, window resized to 1280×720 (on a 2048×1280 screen at 125% DPI, the default 1920×1080 window does not fit). Driven with keyboard and mouse automation, checked by screenshots.

| Date | Build | Test | Result |
| --- | --- | --- | --- |
| before 2026-10-25 | old `EVENTCG_patched.PAK` (`pak_tool.py`) | New game | **[O]** scene 1 OK, scene 2 wrong background, then black screen, no advancing |
| 2026-10-25 | fixed `EVENTCG.PAK` only | New game, ~100 lines | **[V]** scene 1 (`0000-op1`; the prologue was not restored yet) OK, scene 2 correct newspaper CG, study background, dialogue advances. Bug fixed |
| 2026-10-25 | full patch, test start `a1-7-2h` | Whole scene | **[V]** JP placeholder and existing Russian lines display; speaker names in Russian; voice indicator on; restored CG `e061` shown; continues into the next Russian script |
| 2026-10-25 | full patch, test start `0208-13-01H` | Choices | **[V]** restored CGs shown; the choice menus work; option 2 of choice 1 branches to choice 3 (as in the JP script); after the scene the game continues to the next day with the original Russian choices |
| 2026-10-25 | full patch, test start `0217-99-03` | Removed scene | **[V]** the predecessor jumps into `0217-99-04h`, which plays with voice |
| 2026-10-26 | full patch with restored pictures, test start `0207-15-00` | Photo picture | **[V]** `f035` uncensored at the line of the user's report |
| 2026-10-26 | same | Restored pictures | **[V]** confirmed in game by the user |
| 2026-10-26 | full patch with the start sequence | New Game | **[V]** prologue, opening and the following scenes work; confirmed in game by the user |
| 2026-10-26 | interface translation | Start-up notice, Options, dialogs, replacement picture | **[V]** Russian text shown and fits; small-font labels kept English; replacement picture shown (see [Interface Text and Images](#interface-text-and-images)) |
| 2026-11-02 | label table written anew | Extras > Endings: Nana's Delight, Light in the Darkness, Epilogue (labels), Powerless | **[V]** each starts at its ending scene and advances; no black screen, memory steady; back to the list (see [Label table](#label-table)) |
| 2026-10-26 | `_arflag` fix, test start `0217-01-05h` | Skip read text, remembered choice, system data | **[V]** SKIP stops at the first unread line; the chosen option is marked; records of the added scenes saved (see [Read Flags and Saves](#read-flags-and-saves)) |
| 2026-11-02 | translated interface pictures and FONT1 letters | Title and Extras menus, options tabs, system menu, in-game buttons, screen headings, save and load screens, scene date label, bottom bars | **[V]** Russian shown, words whole (see [Interface pictures](#interface-pictures), [Fonts](#fonts)); not seen: the "Jump" indicators, SAVE/LOAD side labels, `CONFIG_TAB1_en`, Extras subpages |
| 2026-11-03 | translated `_varstr` | Load screen | **[V]** heading «6 февраля» (user's screenshot); the redrawn `№` not seen yet |

The 4 scenes added last (`0210-10-00`, `0214-05-00`, `0215-03-00`, `0215-05-02`) went through the same automatic checks but have not been played in game.

The refactored build (2026-10-26) was not tested in game: its `ru` output is byte-identical to the build that was.

### Automated tests

`python tests/test_core.py` (or `python -m unittest discover -s tests`). Standard library only; unit tests use synthetic data, no game files.

| Area | Tests |
| --- | --- |
| Archives | xxHash64 test vectors; byte-identical PAK round trip (also with a name prefix such as `PARTS/`); appending keeps the IDs of existing entries and remaps parent IDs by name; in-place replacement keeps the ID |
| Scripts | `_arflag` counts (lines incl. op 43, select bit ranges, markers) and record rebuild (stale record fixed, metadata record kept, missing record appended); jump targets relocated after inserting an odd-length instruction; `LZW\0` entry round trip; label table: line rule, instruction alignment (removed instruction maps to the next), rebuild (stale target offset corrected through an inserted instruction, JP labels followed through a port with a dropped op, target-only label placed after the same message, new script gets a line, clear errors when a label cannot be placed); scene headings (`_varstr`): read, round trip, translation of the English slot only (padding of odd-length records kept), unknown table row rejected, table file (duplicate rejected), the `ru` table translates all 58 headings of `inputs/ru-steam` (when present); start sequence: call inserted after the setup instructions, movie block cut (jumps redirected, marker IDs renumbered), calls replaced by the movie (jumps land on it) |
| Images | CZ4 decode of an image made by a test encoder (2 LZW blocks, delta bands); alpha compositing; CZ0 encode/decode keeps the placement fields; PNG reader (RGBA, RGB, palette with transparency; filters 0-4) and PNG round trip; replacement pictures in a build (archive entry replaced and its hash updated, other entries kept; wrong size and unknown entry rejected); picture export by name and pattern, copies never overwritten, unedited copies skipped (no archive written, no input needed), pixel comparison without exported originals; `images.tsv` matches the Steam archives (when present); fonts: letters copied into a smaller font set (`add_glyphs`: indices, scaled widths, cells drawn), `№` redrawn (`redraw_numero`: other cells unchanged, narrowed N, raised o, bar, width entry; missing glyph rejected) |
| Gallery | table round trip (groups, ranges, strings); previews in the new order (target preview reused, JP preview scaled into the target's visible size with a black margin, CZ0, renamed, hash); merge: shared picture adds the JP slot's others to the target slot, a new JP slot goes after the slot of its JP predecessor, missing pictures left out, target flags kept and new ones numbered in image ID order, ranges extended, image outside every range rejected; name map with a split picture; both releases' tables read and written back unchanged (when present) |
| Interface text | synthetic PE: `lea` and relocated-pointer references, translation into `.uitext` (references redirected, originals kept, `SizeOfImage`, second run rejected, empty table = unchanged); table checks (placeholders, duplicate id, wrong original, id outside the file); table round trip; the `ru` and original tables fit `inputs/ru-steam/CARTAGRA.exe` (when present); executable fixes (bytes and checksum changed, second run and RVA outside the sections rejected; the `restoration.json` fixes fit `inputs/ru-steam/CARTAGRA.exe` after the translation, when present); original text: a translation section undone (equal to the original apart from the checksum; no section = unchanged; missing, wrong and foreign entries rejected), `exe_original_text` on `inputs/ru-steam/CARTAGRA.exe` (58 references, no `.rtransl`, no Cyrillic, only the `lea` bytes changed, the crash fix still applies; when present) |
| Translation tables | write/read round trip with escapes and the five-column header; older formats (`source`/`existing`/`translation`, `ru_existing`/`ru`); missing table |
| Languages and paths | every language has a valid status and an existing input set; `en` is not `complete`; unknown language rejected; project paths are absolute and independent of the working directory; output names `ru`, `ru-partial`, `ru-test` |
| Input validation | missing folder and files; wrong entry count; wrong size; changed data detected by SHA-256 and skipped with `verify_checksums=False`; optional files required only when needed; executable header and checksum |
| CLI | `--help` (0), no language (2), unknown language (2), `--test-set` without `--test-start` (2), `--list-languages` shows the statuses, missing inputs (1); run from a working directory with spaces, inputs in a folder with spaces |
| Integration (`CARTAGRA_INTEGRATION=1`) | `ru` build from `inputs/` into a temporary folder as the reference build (`reference=True`: no tables, start sequence or `_arflag` update; equal to the SHA-256 of the pre-refactoring build), then twice normally (identical output; New Game calls the prologue, `0308-02-00` no longer does; `_arflag` correct for every script; every `_scr_label` offset an instruction start, `ENDING` in `0210-12-01h`; `CARTAGRA.exe` written only by the normal builds); inputs still pass the checksum check and are not modified |

**[V]** 2026-10-26 (`_original_jp`/`_original_steam` split, picture export): 32 unit tests and the integration test pass.

**[V]** 2026-10-26 (after the `_arflag` fix and the new-script placement): 21 unit tests and the integration test pass (106 s in total). `python build.py --language ru` (with input checksums) takes about 40 s and reproduces the reference SHA-256 of all four archives; `--language en --check` fails with exit code 1 because `inputs/en-steam/files/` does not exist.

## Known Issues

1. The 3,970 Russian lines added on 2026-10-26 have not been checked in game (line length, line breaks, choice menus).
2. **[?]** Saves made inside the 24 changed scenes, the 4 retargeted predecessors or the 3 start-sequence scripts (`0000-op1`, `0209-08-00`, `0308-02-00`) may break after installing or removing the patch (they store positions in scripts whose layout changed). Not tested.
3. **[H]** New select flag slots (197+) assume the engine's flag array is large enough. The JP build uses slots up to 229 (plus its options), and the in-game choice test worked.
4. Save thumbnails for restored scenes are not set (JP op 130 dropped); `EVENTCG_SAVE.PAK` is unused.
5. The Extras CG gallery lists the restored CGs since 2026-11-03 (18 pages seen in game; the rebuilt previews not yet). Their pictures unlock only when their scenes are played with the new gallery installed: playing them before did not set their seen flags. JP `f022b` and `f022j` are not in the gallery (the patch does not add them to `OTHCG.PAK`; no restored scene shows them). The scene replay (Extras > SCENEgallery) is not studied (JP op 129 dropped).
6. `0210-10-00` and `0215-03-00` show the Japanese date eyecatch instead of the English one the RUS build uses.
7. Steam-only Russian lines inside censored scenes are dropped with the Steam rewrite.
8. Restored pictures: the JP 4368×2457 pan image `e007k0` is not used (the RUS script shows the static uncensored `e007` instead), and Steam's own frame `e007k0` is no longer shown.
9. Of the endings started at a label (see [Label table](#label-table)), Rin's Joy, Toji's Love, Departure and True End have not been played from the Extras list (locked in the test profile); Nana's Delight, Light in the Darkness and Epilogue were.
10. 21 of the 24 restored scenes have not been played in game.
11. Read lines and chosen options are written to disk only when saving (game behaviour; see [Read Flags and Saves](#read-flags-and-saves)).
12. Interface: `BGM`/`SE`/`MOVIE` stay English; character names on the Voice page (`PARAM.PAK` `_voice_param`) are not translated; the manual pages and the key names are English. The labels drawn with FONT1 (bottom bar, slider labels, version, save date) rely on the letters the build adds to that font (seen in game with the Mincho face only). The voice collection and the music and ending titles have not been seen in game. The translated scene headings are seen in game (2026-11-03); the redrawn `№` of the slot number is not yet; saves made before the patch keep their English heading ([Scene titles](#scene-titles)).
13. In `0210-99-01` (not ported) the Russian release shows Steam's substitute picture `e047` just before the restored scene; it is kept ([Censored Images](#censored-images)).
14. Chosen options are drawn in another colour only with Options > Text1 > "Color of Previously Read Text" set to "Only Choices" or "On"; with "Off" the game remembers them but does not mark them ([Read Flags and Saves](#read-flags-and-saves)).
15. `ru` interface pictures: the title menu buttons are cut to the width of the English words, so the Russian words there are smaller (about 0.6 of the English size); the save and load headings must leave room for the slot number (SAVE is ЗАПИСЬ, ЗАГРУЗКА is smaller than LOAD). The right-hand bottom label is "Назад" rather than "Закрыть": the box keeps the English width.
16. The `en` build has never been made with the English Steam files or tested; its file list and checksums are not known. There is no installer.

## Open Questions

- Do saves inside changed scripts survive? (Test: save in a ported scene, reload.)
- How does the scene replay (Extras > SCENEgallery) choose its scenes, and can the restored scenes be added?
- What exactly are JP op 129 and the RUS MESSAGE tail value?
- Where did `CARTAGRA_backup.exe` come from? (`CARTAGRA.exe` is the Russian release's executable with its `.rtransl` section.)

## Roadmap

1. Check the added Russian lines in game; proofread them (see [Text for the Russian slot](#text-for-the-russian-slot)).
2. Play through the remaining 21 restored scenes; test saves and loads.
3. Check the restored CGs in the gallery in game; investigate the scene replay so restored scenes are listed.
4. Translate the text inside restored CG images and the manual pages (`MANUAL`, `MANUAL_DECK`); the other interface pictures are translated (`tools/image_text.py`).
5. Get the English Steam files, record their checksums in `definitions/inputs.json`, build `en` and test it.
6. An installer with version checks and rollback.

## Tools

Run from the project folder.

- `python build.py`: the build (see [Build System](#build-system)).
- `lucapak`: PAK read/write with header, sections, metadata and filler preserved; `read_index` (fast name list); `append_missing`, `replace_from`, `append_copy`; `xxh64` (the `xxhash` module if installed, else pure Python). CLI: `python -m cartagra_patch.lucapak list|roundtrip|unpack|compare ...`.
- `lucascript`: script instruction parser and assembler with jump relocation; `check()` validates jump targets.
- `cztool`: CZ0/CZ1/CZ3/CZ4 decoder, CZ0 encoder, compositing of variants, PNG output and input. CLI: `python -m cartagra_patch.cztool png <pak> <entry> <out.png> [--composite]`, `python -m cartagra_patch.cztool export <pak> <out_dir> [entry ...]`.
- `images`: interface pictures (`images.tsv`, export, copies, changed pictures). CLI: `python build.py --language <code> --export-images`.
- `exe_text`: interface strings of `CARTAGRA.exe`. CLI: `python -m cartagra_patch.exe_text list <exe>`, `python -m cartagra_patch.exe_text check <exe> <table.tsv>`.
- `script_port`: JP → target porter (opcode map, resource and variable remapping, text slots, select slots, TSV handling, predecessor retargeting).
- `python tests/test_core.py`: the automated tests.
- Obsolete, in `local/legacy/` (outside git): `pak_tool.py`, `create_patch.py`.

## References

- [VNDB: Cartagra](https://vndb.org/v515)
- [Steam: CARTAGRA](https://store.steampowered.com/app/4290390/CARTAGRA/)
- [Chinese patch (lzacg)](https://lzacg.cc/7683)
- [HIllya51/Cartagra_FHD_CHS](https://github.com/HIllya51/Cartagra_FHD_CHS)
- [Russian release (ruvn)](https://s.ruvn.org/novels/cartagra-tsuki-kurui-no-yamai)
- Russian translation: [Innocence translations](https://t.me/innocence_translations), [The Hounds of God](https://vk.ru/thgteam)
