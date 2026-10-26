# Technical Notes

Working notes for reverse engineering and development of the Cartagra cut-content patch. For installation, usage and user-facing status, see [README.md](README.md). The chronological journal is [MODLOG.md](MODLOG.md).

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
- [Game Installations in This Project](#game-installations-in-this-project)
- [PAK Archive Format](#pak-archive-format)
- [Resource IDs](#resource-ids)
- [Cause of the Wrong Background and Black Screen](#cause-of-the-wrong-background-and-black-screen)
- [Scene Scripts](#scene-scripts)
- [Porting Scripts from JP to RUS](#porting-scripts-from-jp-to-rus)
- [What Steam Censored](#what-steam-censored)
- [EVENTCG.PAK Comparison](#eventcgpak-comparison)
- [Censored Images](#censored-images)
- [Voice, Music and Sound Effects](#voice-music-and-sound-effects)
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
6. **[V]** All 24 censored scenes are now ported and all 150 restored CGs are referenced. 3,970 of 4,422 restored lines have no Russian translation.
7. **[V]** Steam also **edited 51 pictures** that the Russian scripts still show (35 EVENTCG, 16 OTHCG): clothes painted on, blood, wounds and corpses removed or blacked out, frames recomposed. The patch puts the JP originals back in the same slots.

## Game Installations in This Project

All paths are relative to the project root `Cartagra-Patch/`.

| Directory | What it is |
| --- | --- |
| `Cartagra2023RUS/` | Russian 2026 release by Innocence translations and The Hounds of God (Steam build, app ID 4290390, with a Goldberg-type Steam emulator in `steam_settings/`, `language=english`). Target. Executable `CARTAGRA.exe` (window title "CARTAGRA - Ver.1.0.0.1") |
| `Cartagra_FHD_CHS_GAME_v1.1/` | Japanese FHD release v1.1 with the Chinese fan patch. Source of the cut content |
| `Cartagra_FHD_CHS/` | Source code of the Chinese fan patch |
| `Patch/` | This project (git repository) |
| `Patch/inputs/` | Local copies of the original files the build reads (outside git): `jp-fhd/files/` from `Cartagra_FHD_CHS_GAME_v1.1/files/`; `ru-steam/files/` from `backup/orig/` (the four replaced archives) plus the unmodified index-only archives of `Cartagra2023RUS/files/`. The build never reads the installations themselves |
| `backup/` | Pristine copies of the RUS files the patch replaces (`backup/orig/`) and save backups (`backup/saves/`). Outside git |

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
| `image/PARTS.PAK` | absent | 9,873,408 B, 116 | |
| `image/MANUAL.PAK`, `MANUAL_DECK.PAK` | present | absent | |
| `voice/VOICE.PAK` (JP: `VOICE0.PAK`) | 601,276,416 B, 8,183 | 10,080 entries | |
| `voice/VOICE1.PAK` | absent | 3 entries | |
| `voice/SYSVOICE.PAK` | 18 entries | 19 entries | |
| `music/MUSIC.PAK` | 44 | 44 | same names and order |
| `se/SE.PAK` | 241 | 236 | JP list is a prefix of the RUS list |
| `movie/` | `cartagra_movie_NN_en.webm` | `cartagra_movie_NN.webm` | scripts name movies without the `_en` suffix in both |

**[V]** The RUS executable contains the string `*.PAK` and mounts image archives by wildcard.

### Current install state

**[V]** As of 2026-10-26 the **full patch is installed**: `Cartagra2023RUS/files/image/EVENTCG.PAK`, `files/image/OTHCG.PAK`, `files/voice/VOICE.PAK` and `files/SCRIPT.PAK` are identical to the output of the old `build_patch.py`, which is byte-identical to `Patch/dist/ru/files/...` from `build.py --language ru` (SHA-256 prefixes: SCRIPT `578b31f79f8d8a8b`, EVENTCG `a390601d1758eee6`, OTHCG `46ddcb03fb3a6a90`, VOICE `d1ddf178abbee528`). The originals are in `backup/orig/` (SHA-256 prefixes: EVENTCG `8f2a9b21300cb3fa`, OTHCG `477b30ba8f36e5e9`, VOICE `42e87d76474c8ae6`, SCRIPT `c33dd504c40a120f`).

**[V]** `Cartagra2023RUS/` also contains `CARTAGRA_backup.exe` (6,856,704 B) next to `CARTAGRA.exe` (6,630,400 B). This project did not create either. **[?]** Origin unknown.

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

- EVENTCG entries took IDs 1..373, overlapping BGCG's 1..179. Background loads returned event CGs, which gave the wrong background in scene 2 (scene 1, the prologue, uses only OTHCG/EVENTCG art that is loaded differently). **[H]** which archive wins on a collision was not tested.
- No EVENTCG entry had an ID ≥ 1001 any more, so every event-CG load failed, which gave the black screen.

**[V]** Fix: the build keeps the 223 RUS entries untouched (IDs 1001–1223), appends the 150 JP-only CGs (IDs 1224–1373) with their parent IDs remapped by name, and keeps the header and sections. Tested in game: the prologue, scene 2 (correct newspaper CG) and further scenes play normally.

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

**[V]** No script refers to a label by name.

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

**[V]** SELECT (op 40): 8-byte head (u16 `0x6D61`, u16 **flag slot**, u16 index in script, u16 `0x40xx`), JP text (`$d` between options), then in RUS **two UTF-16 copies** of the Russian text, then a tail (u16 0, u16 number of options). A select uses one flag slot per option. RUS slots run up to 196; JP slots differ (only offsets like +2, −34 between matching selects).

**[V]** Op 43 is another text instruction (RUS adds Russian slots). It does not occur in the ported scenes.

### Metadata entries

**[V]** `SCRIPT.PAK` also holds `_varset_システムフラグ`, `_arflag`, `_varstr`, `_varnum`, `_varname`, `_colorbg`, `_scr_label`, `_task`, plus `_build_time`/`_varstrname` (RUS) or `_build_count` (JP).

- `_varname`: u16 ID + NUL-terminated name. 134 names are common to both builds; IDs 6044–6069 are shifted by −1 in RUS (e.g. `SNOW` is 6069 in JP and 6068 in RUS).
- `_scr_label`: `LZW\0`, u32 total size, u32 chunk count, then per chunk u32 code count, u32 output size, and 16-bit LZW codes (dictionary from 257). It decodes to one line per script, `LABEL:offset,` (JP) or `LABEL:offset(line),` (RUS). The offsets point into the **source text**, not the bytecode (they exceed the bytecode size). **[H]** debug source map only; the patch leaves it unchanged, and the in-game tests showed no problem.

**[V]** The early unpacked folders `SCRIPT_RUS_unpacked/` and `SCRIPT_CHS_unpacked/` (now in `local/legacy/`, outside git) lack 9 and 8 of these metadata entries, so they cannot be repacked. The build reads the archives directly; `python -m cartagra_patch.lucapak unpack <pak> <dir>` extracts every entry for inspection.

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

1. the `translation` column of `languages/<lang>/translation/<scene>.tsv` (legacy tables: `ru`);
2. an existing Russian line whose JP text is identical (same scene first, then any scene; 16,504 known lines);
3. the JP text as a placeholder, with the `@speaker@` tag translated when known (37 names).

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

New scripts are appended at the end of `SCRIPT.PAK`, after the metadata entries, so existing entry indices do not move.

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

## Voice, Music and Sound Effects

**[V]** `VOICE.PAK`: 8,179 clip names are common, 1,901 exist only in JP `VOICE0.PAK`, and 4 only in RUS (`nur0006a`, `nur0006b`, `shu5001`, `tyu0008`). Same names have different IDs. The patch appends the 1,901 clips (IDs 8184–10084) and copies their `0x01`/`0x04` section values. Ported MESSAGEs get their voice IDs remapped by name; no ported line references an unmapped clip.

**[V]** MUSIC: identical names and order. SE: the JP list equals the first 236 RUS entries. No remapping is needed for music (op 106 → 107, u32 ID) or SE (op 111 → 113, u32 ID at body[1]).

## CZ4 Image Format and Engine

- **[V]** EVENTCG and EVENTCG_SAVE entries are `CZ4`; OTHCG also has `CZ1` (palette) entries and SYSCG has `CZ0` entries. `cztool` decodes CZ1/CZ3/CZ4 (after `czximage/cz2image.cpp`): header (u32 header length, u16 width/height/bits, u16 x/y offset of an overlay, canvas size), then LZW blocks (u32 count; per block u32 code count and u32 raw size; 16-bit codes). The LZW dictionary gets an entry for every code, including the first, starting from `"\0"`. CZ4 holds RGB rows followed by an alpha plane; each row is delta-coded against the previous one except at the start of each of 3 horizontal bands. CZ1 holds a 256-entry RGBA palette plus LZW indices (or raw RGBA). Encoding back to CZ has not been needed.
- **[H]** (strong) The engine is **LucaSystem** (Prototype). The PAK layout, `id_start` scheme and opcode list order match the LucaSystem tools shipped with the Chinese patch, including their opcode tables for other LucaSystem games.
- **[V]** The RUS font renders Japanese text (kanji placeholder lines display correctly in game).

## The Chinese Patch (Reference Implementation)

**[V]** From `Cartagra_FHD_CHS/patch/patch.cpp`: `CHSpatch.dll` hooks `CreateFileW` (MinHook). It redirects `PARTS.PAK`, `SYSCG.PAK`, `FONT.PAK`, `SYSFONT.PAK` and `SCRIPT.PAK` to `CHSPAK\`, patches `OTHCG.PAK`/`BGCG.PAK` reads in memory, and shows lyrics from `CHSPAK\LRC\`. `EVENTCG.PAK`, `EVENTCG_SAVE.PAK` and `files/SCRIPT.PAK` are not modified. So the JP files used here are the stock Japanese ones: `files/SCRIPT.PAK` holds the Japanese text, and the Chinese text is in `CHSPAK/SCRIPT.PAK`.

**[V]** The Chinese `pak.py` repacks by keeping the original header and order and rewriting only the index. That is the same principle as `lucapak`.

Repository contents: `pak.py`, `SCRIPT.PAK`, `SCRIPT_FHD/` (`solvev2.py` text extractor: text opcodes 0x24/0x28/0x2b/0x1d, plus `text/`), `image/` (CZ tools), `font/` (font generation, LucaSystem tools), `patch/` (DLL source), `writeback.py` (writes translations back with length padding), `uitext.py`, `genuitextcpp.py`, `checkformat.py`, `kouryaku/` (walkthrough).

## Patch Generation

`pipeline.run_build` (started by `build.py`, see [README.md](README.md#step-2-build)). `<target>` is the input set of the language (`inputs/ru-steam/files/` for `ru`), `<jp>` is `inputs/jp-fhd/files/`:

1. **EVENTCG**: read `<target>/image/EVENTCG.PAK`, append the JP-only entries (`lucapak.append_missing`: parents remapped by name, xxh64 computed), replace the censored entries in place (`replace_from`) and append the split copy `e047_jp` (`append_copy`). Untouched entries are byte-identical and in their original order (verified).
   **OTHCG**: replace the 16 censored pictures in place.
2. **VOICE**: the same for `VOICE.PAK` with `VOICE0.PAK` as donor, copying section values.
3. **SCRIPT**: build the name maps (images over all target image archives with the new EVENTCG; voices with the new VOICE; variables from `_varname`), the translation memory and the first free select slot. Port the 24 scenes, check every jump target, write the translation tables, retarget the 4 predecessor JUMPs and append the 4 new scenes. Then apply the two target script fixes for censored pictures. 254 of 274 entries stay byte-identical.
4. **Output**: write `BUILD_INFO.txt` and move the staging folder to `dist/<lang>/`.

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
| `definitions/restoration.json` | What to restore: censored and removed scenes (with predecessors), censored images, split images, target script fixes, the New Game script used by test builds. Moved out of the code; shared by all languages | yes |
| `definitions/inputs.json` | Required files per input set, with use (`data` = copied or patched, `index` = only entry names read), size, entry count and SHA-256 | yes |
| `languages/<lang>/language.json`, `translation/` | Language settings and status; translation tables ([languages/README.md](languages/README.md)) | yes |
| `tests/test_core.py` | Automated tests (standard library `unittest`) | yes |
| `inputs/<set>/files/` | Local copies of the original files | no |
| `build/<name>/staging/`, `build/<name>/translation/` | Archives while being written; refreshed translation tables | no |
| `dist/<name>/` | Finished patch: `files/...` + `BUILD_INFO.txt` | no |
| `local/legacy/` | Old tools, unpacked archives and outputs (kept for reference, not used) | no |

`<name>` is the language code, `<code>-test` for `--test-start` builds and `<code>-partial` for `--scenes` builds, so debug builds never overwrite a normal build.

### Guarantees

- **[V]** Inputs are only read. The build writes only below `build/` and `dist/`; the integration test checks that the inputs are unchanged after a build.
- **[V]** Input validation before any work: missing files, size, PAK header sanity, entry count, and SHA-256 for `data` files (a patched file in `inputs/` is reported, not used). `--skip-checksums` keeps the size and entry-count checks.
- **[V]** Reproducible: no timestamps or absolute paths in the output; two builds from the same inputs give identical files (integration test).
- **[V]** The refactored build produces the same bytes as the previous `build_patch.py` for `ru` (SHA-256 of all four archives compared, 2026-10-26).
- `dist/<name>/` is replaced only after the whole build succeeded, and only if it contains a `BUILD_INFO.txt` (a folder the build did not make is never deleted).
- TSV tables: the build reads `languages/<lang>/translation/` and writes to `build/<name>/translation/`; it never writes into `languages/`. New header: `row kind voice source jp existing translation`. Tables with the old `ru_existing`/`ru` columns are still read.

## Language Targets

| Code | Input set | Status | Evidence |
| --- | --- | --- | --- |
| `ru` | `ru-steam` | incomplete | Built and tested in game; 3,970 untranslated lines |
| `en` | `en-steam` | untested | Never built |

**[H]** The English Steam release is assumed to be the same multi-language build as the Russian one before translation: the same archives, opcode table and script names, with English in the "EN" text slot. If so, the same restoration rules apply and the porter fills the EN slot with existing English lines where the JP text matches. Unverified points:

- the file list in `definitions/inputs.json` (copied from `ru-steam`; no sizes, entry counts or checksums yet, so only presence and PAK headers are checked);
- whether the English `SCRIPT.PAK` has the same script names, predecessor JUMPs and free select slots;
- whether the English EVENTCG/OTHCG have the same censored entries at the same indices (the image comparison was done on the Russian release only);
- the two target script fixes (`0208-15-00`, `0210-07-00`) match by image ID and coordinates; the build fails with a clear error if they match nothing.

The build accepts `--language en`, but it fails at the input check until `inputs/en-steam/files/` exists.

## Test Results

Test setup: `CARTAGRA.exe`, window resized to 1280×720 (on a 2048×1280 screen at 125% DPI, the default 1920×1080 window does not fit). Driven with keyboard and mouse automation, checked by screenshots.

| Date | Build | Test | Result |
| --- | --- | --- | --- |
| before 2026-10-25 | old `EVENTCG_patched.PAK` (`pak_tool.py`) | New game | **[O]** scene 1 OK, scene 2 wrong background, then black screen, no advancing |
| 2026-10-25 | fixed `EVENTCG.PAK` only | New game, ~100 lines | **[V]** prologue OK, scene 2 correct newspaper CG, study background, dialogue advances. Bug fixed |
| 2026-10-25 | full patch, test start `a1-7-2h` | Whole scene | **[V]** JP placeholder and existing Russian lines display; speaker names in Russian; voice indicator on; restored CG `e061` shown; continues into the next Russian script |
| 2026-10-25 | full patch, test start `0208-13-01H` | Choices | **[V]** restored CGs shown; the choice menus work; option 2 of choice 1 branches to choice 3 (as in the JP script); after the scene the game continues to the next day with the original Russian choices |
| 2026-10-25 | full patch, test start `0217-99-03` | Removed scene | **[V]** the predecessor jumps into `0217-99-04h`, which plays with voice |
| 2026-10-26 | full patch with restored pictures, test start `0207-15-00` | Photo picture | **[V]** `f035` uncensored at the line of the user's report |
| 2026-10-26 | same | Restored pictures | **[V]** confirmed in game by the user |

The 4 scenes added last (`0210-10-00`, `0214-05-00`, `0215-03-00`, `0215-05-02`) went through the same automatic checks but have not been played in game.

The refactored build (2026-10-26) was not tested in game: its `ru` output is byte-identical to the build that was.

### Automated tests

`python tests/test_core.py` (or `python -m unittest discover -s tests`). Standard library only; unit tests use synthetic data, no game files.

| Area | Tests |
| --- | --- |
| Archives | xxHash64 test vectors; byte-identical PAK round trip; appending keeps the IDs of existing entries and remaps parent IDs by name; in-place replacement keeps the ID |
| Scripts | jump targets relocated after inserting an odd-length instruction |
| Images | CZ4 decode of an image made by a test encoder (2 LZW blocks, delta bands); alpha compositing |
| Translation tables | write/read round trip with escapes; legacy `ru` column; missing table |
| Languages and paths | every language has a valid status and an existing input set; `en` is not `complete`; unknown language rejected; project paths are absolute and independent of the working directory; output names `ru`, `ru-partial`, `ru-test` |
| Input validation | missing folder and files; wrong entry count; wrong size; changed data detected by SHA-256 and skipped with `verify_checksums=False` |
| CLI | `--help` (0), no language (2), unknown language (2), `--test-set` without `--test-start` (2), `--list-languages` shows the statuses, missing inputs (1); run from a working directory with spaces, inputs in a folder with spaces |
| Integration (`CARTAGRA_INTEGRATION=1`) | full `ru` build twice from `inputs/` into a temporary folder: identical output, equal to the SHA-256 of the pre-refactoring build, inputs still pass the checksum check and are not modified |

**[V]** 2026-10-26: 16 unit tests pass; the integration test passes (74 s). `python build.py --language ru` (with input checksums) takes about 40 s and reproduces the reference SHA-256 of all four archives; `--language en --check` fails with exit code 1 because `inputs/en-steam/files/` does not exist.

## Known Issues

1. 3,970 restored lines show Japanese text (placeholder) until translated in `languages/ru/translation/`.
2. **[?]** Saves made inside the 24 changed scenes or the 4 retargeted predecessors may break after installing or removing the patch (they store positions in scripts whose layout changed). Not tested.
3. **[H]** New select flag slots (197+) assume the engine's flag array is large enough. The JP build uses slots up to 229 (plus its options), and the in-game choice test worked.
4. Save thumbnails for restored scenes are not set (JP op 130 dropped); `EVENTCG_SAVE.PAK` is unused.
5. **[?]** The Extras CG gallery and scene replay probably do not list restored content (JP op 129 dropped; gallery data not studied).
6. `0210-10-00` and `0215-03-00` show the Japanese date eyecatch instead of the English one the RUS build uses.
7. Steam-only Russian lines inside censored scenes are dropped with the Steam rewrite.
8. Restored pictures: the JP 4368×2457 pan image `e007k0` is not used (the RUS script shows the static uncensored `e007` instead), and Steam's own frame `e007k0` is no longer shown.
9. `_scr_label` is not updated for the ported scenes (**[H]** debug data only).
10. 21 of the 24 restored scenes have not been played in game.

## Open Questions

- Do saves inside changed scripts survive? (Test: save in a ported scene, reload.)
- How does the Extras gallery decide which CGs to show, and can restored CGs be added?
- What exactly are JP op 129 and the RUS MESSAGE tail value?
- Where did `CARTAGRA_backup.exe` and the modified `CARTAGRA.exe` come from?

## Roadmap

1. Translate the 3,970 restored lines (`languages/ru/translation/*.tsv`), then rebuild.
2. Play through the remaining 21 restored scenes; test saves and loads.
3. Investigate the gallery and replay data so restored CGs and scenes are listed.
4. Translate the text inside restored CG images (CZ4 tools; would go into `languages/<lang>/`).
5. Get the English Steam files, record their checksums in `definitions/inputs.json`, build `en` and test it.
6. An installer with version checks and rollback.

## Tools

Run from the project folder.

- `python build.py`: the build (see [Build System](#build-system)).
- `lucapak`: PAK read/write with header, sections, metadata and filler preserved; `read_index` (fast name list); `append_missing`, `replace_from`, `append_copy`; `xxh64` (the `xxhash` module if installed, else pure Python). CLI: `python -m cartagra_patch.lucapak list|roundtrip|unpack|compare ...`.
- `lucascript`: script instruction parser and assembler with jump relocation; `check()` validates jump targets.
- `cztool`: CZ1/CZ3/CZ4 decoder, compositing of variants, PNG output. CLI: `python -m cartagra_patch.cztool png <pak> <entry> <out.png> [--composite]`.
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
