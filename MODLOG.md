# MODLOG: Cartagra cut-content patch

Working journal (per the universal-modder workflow). Newest entries at the bottom.

## Route

Data/assets only (PAK archives) for now. A DLL route like the Chinese `CHSpatch.dll` stays as a fallback.
Single-player VN, no anti-cheat.

## Restore path

- Original RUS `files/image/EVENTCG.PAK`: 371,456,000 bytes, 223 entries. Unpacked copy in `Patch/local/legacy/EVENTCG_RUS_unpacked/` (outside git).
- Back up anything in `Cartagra2023RUS/files/` before replacing it (see the backup step entries below).
- Backups (outside the git repo): `Cartagra-Patch/backup/orig/image/EVENTCG.PAK`, `backup/orig/voice/VOICE.PAK`,
  `backup/orig/SCRIPT.PAK` (pristine RUS files; SHA-256 prefixes `8f2a9b21300cb3fa`, `42e87d76474c8ae6`, `c33dd504c40a120f`);
  saves in `backup/saves/GSE_4290390` (from `%APPDATA%/GSE Saves/4290390`) and `backup/saves/PROTOTYPE_CARTAGRA`
  (from `%APPDATA%/PROTOTYPE/CARTAGRA`).
- Restore: copy the four files from `backup/orig/` (or `Patch/inputs/ru-steam/files/`) back into `Cartagra2023RUS/files/` (see README "Removing the Patch").

## 2026-10-25 session 2

- User report (with the old `EVENTCG_patched.PAK` installed): scene 1 plays correctly; scene 2 shows a completely wrong background; advancing further gives a black screen; the UI keeps working but the scene does not advance.
- Knowledge base: no notes for LucaSystem / Cartagra / Innocent Grey.
- Script format (from `Cartagra_FHD_CHS/SCRIPT_FHD/solvev2.py`): a stream of instructions `u16 length, u8 opcode, ...`, padded to an even size. Text opcodes are 0x24, 0x28, 0x2b, 0x1d, with UTF-16LE text.
- PAK header decoded: `0x08` = id_start; `0x20` = section count; `0x21` = flags; then `(u8 type, u8 elem_size, u32 offset)` per section; align 4; u32 names_offset; index. Section 0x01 = parent (base image) ID, 0x0b = xxh64(data, seed 0), 0x03/0x04 = zeros. Flag bit 0 = per-entry meta table (BGCG: width/height).
- **Cause of the bug:** scripts load images by resource ID = id_start + entry index. `pak_tool.py` wrote id_start = 1 (colliding with BGCG ids 1..179) and re-sorted/inserted entries, so every EVENTCG id moved.
- The RUS build is the Steam multi-language build: its opcode numbers are shifted versus the JP build (RUS 55 = JP 54 image load, ...), and MESSAGE holds JP UTF-16 + an "English" slot (UTF-8, then UTF-16) that the Russian translators filled with Russian. Hashes (0x0b) of all 274 RUS scripts mismatch, so the engine does not verify them.
- `lucapak.py`: round trip is byte-identical for RUS/JP EVENTCG, EVENTCG_SAVE, BGCG, SYSCG.
- `build_eventcg.py` (later merged into `build_patch.py`) -> `out/EVENTCG.PAK`: 223 RUS entries untouched (ids 1001..1223) + 150 JP-only appended (1224..1373), parents remapped, xxh64 computed.
- In-game test (CARTAGRA.exe, window resized to 1280x720): prologue OK, scene 2 (`0206-01-00`) shows the correct newspaper CG, then the study BG; dialogue keeps advancing. Bug fixed. Restored CGs are not shown anywhere yet: RUS scripts never reference ids 1224+.
- Driving notes: screen is 2048x1280 at 125% DPI; game client after `size 1280 720` is at physical (80,48) 1600x900. Capture with a DPI-aware CopyFromScreen; WinDrive click coords = logical client coords (= 2 x pixel in a 0.4-scale capture). Title-screen START at (215,586). Enter (0x0D) advances text.
- Restoring CGs needs scene porting: Steam rewrote 20 scenes and removed 4 (H-scenes), so RUS scripts never load the cut CGs. 3,970 of 4,422 restored lines have no Russian translation. User decision: reuse existing Russian, show JP as placeholder, export TSVs; restore voices.
- Voice: RUS VOICE.PAK lacks 1,901 JP clips; IDs positional, remap by name. MUSIC/SE identical order.
- Opcode map JP -> RUS derived from 65 equal-length scripts (table in TECHNICAL_NOTES). JP 129/130 have no RUS equivalent (130 = save thumbnail via EVENTCG_SAVE ids) -> dropped.
- Jump ops 15/16/18/19 hold absolute in-script offsets; op 21 jumps to a script by name. `_scr_label` = LZW (16-bit codes, dict from 257) source map, not referenced by scripts -> left unchanged.
- Argument changes found by an oracle test (port uncensored JP scripts, compare with real RUS): op57->58 u8->u16 ease (0->1,1->2,2->3,10->33); op3 value string -> fe7f+i16; op74 carries an image id; SELECT flag slots must be new (RUS max slot 196 -> new from 197); vars 6044..6069 shifted by -1.
- Oracle result: 264/264 jump targets at the same instruction index; voice ids 2056/2059; image ids 493/512 (rest = Steam sprite swaps).
- Tools: lucapak.py (byte-identical round trip incl. SCRIPT/VOICE after keeping original filler), lucascript.py (all 264 RUS / 268 JP scripts reassemble identically), script_port.py, build_patch.py (`--test-start SCENE` for test builds).
- In-game (test builds): a1-7-2h plays (JP placeholder + RU lines, kanji render, RU speaker names, voice icon, restored e061, continues to next RU script); 0208-13-01H choices and branches work, continues to next day; 0217-99-03 now jumps into restored 0217-99-04h (voiced).
- Final build installed (not a test build): 24 scenes ported, 150/150 restored CGs referenced, 254/274 scripts byte-identical, EVENTCG first 223 entries identical.
- New game starts at `0000-op1` (prologue), not `0000-op0_HD`. Window position changes per launch: capture from WinDrive `rect` x 1.25. Ctrl (0x11) held = skip; stops at choices.
- Next: translation of TSVs; play-test the other 21 scenes; saves across the change; gallery/replay; check the 44 size-different CGs.

## 2026-10-26 session 3: censored pictures

- User report: some CGs still censored (screenshot: `0207-15-00`, picture `OTHCG:f035`, photos with black blobs).
- `cztool.py`: CZ1/CZ3/CZ4 decoder after `czximage/cz2image.cpp`. Gotcha: the LZW dictionary adds an entry for every code including the first (w starts as "\0"); without that, decoding fails at the first new code.
- Compared all differing RUS/JP image pairs (pixel-difference maps + full-resolution crops): EVENTCG 37 of 44 censored, OTHCG 16 of 55 (rest = English localization), CHARCG 0 of 67 (expression redraws), BGCG/SYSCG 0 (title screens).
- Usage check: all censored images are shown by the unported RUS scripts at the same points as in JP, except `e047` (RUS `0210-99-01` shows a substitute) and the `e007` family in `0208-15-00` (Steam inserted its own frame `e007k0`).
- Build: 35 EVENTCG + 16 OTHCG replaced in place (same IDs, parents remapped), `e047_jp` appended for the ported scene, RUS script fixes: `0208-15-00` e007k0 -> e007k1, `0210-07-00` e045 move y -854 -> -1080. JP op 118 (RUS 120) = mark CG as seen, takes an image id; added to the porter.
- Backup: `backup/orig/image/OTHCG.PAK` (SHA-256 prefix `477b30ba8f36e5e9`).
- In game: `f035` uncensored at the reported line. `e045` sits behind `#6021==5` (route variable), so the test stub skipped it; added `--test-set VAR=VALUE`. User confirmed the restored pictures in game. Normal build installed.
- Driving tip from the user: Space hides the UI (clean CG screenshots).

## 2026-10-26 session 4: build system refactoring

- Goal: separate the project from the game installations, one build command per language (`python build.py --language ru|en`), tests. No new restoration features, no translations, no install step.
- Inputs: the build reads only `inputs/<set>/files/` (or `--jp-files`/`--target-files`). `definitions/inputs.json` lists the required files per set with size, entry count and SHA-256; `data` files are hash-checked before building. Local copies made: `inputs/jp-fhd/files` from `Cartagra_FHD_CHS_GAME_v1.1/files`, `inputs/ru-steam/files` from `backup/orig` + unmodified RUS index archives (4.6 GB, ignored by git).
- Code: `build_patch.py` split into `build.py` (CLI) + `cartagra_patch/project.py` (paths, configs, input checks) + `cartagra_patch/pipeline.py`. Restoration rules moved to `definitions/restoration.json`. Format modules moved into `cartagra_patch/` unchanged apart from imports; `lucapak` got the `unpack`/`compare` commands of the old `pak_tool.py` (no `pack`, on purpose).
- Languages: `languages/<code>/language.json` with status (`ru` incomplete, `en` untested: no English Steam files available, file list assumed equal to RUS). TSV header now `row kind voice source jp existing translation`; old `ru` tables still load. Tables moved from `translation/` to `languages/ru/translation/`.
- Output: `build/<name>/` (staging, refreshed tables) and `dist/<name>/` (files + `BUILD_INFO.txt`, replaced only after success). `--test-start` -> `<code>-test`, `--scenes` -> `<code>-partial`.
- Gotcha: on Windows a new `patch/` folder is the same as the old `Patch/` folder; the definitions folder is therefore `definitions/`.
- Verified: `dist/ru/files/*` byte-identical to the previous `build_patch.py` output (SHA-256 of all four archives). Old tools, unpacked folders and outputs (~2 GB) untracked and moved to `local/legacy/`.
- Tests: `tests/test_core.py` (17 tests; the integration test needs `CARTAGRA_INTEGRATION=1`).
- The installed game was not touched in this session.
- Original translation tables (commit `2265978`, `translation/*.tsv`) restored byte for byte from git into `languages/_original/` as a basis for other languages; not read by the build.
- Git history reset: the old repository (6 commits, 1.2 GB, including the 544 MB `EVENTCG_patched.PAK` and unpacked CGs) is kept in `local/legacy2/` (full `.git` plus the working tree of that moment). The project was re-initialized with an empty history; `.gitignore` now also excludes game file types (`*.PAK`, `*_unpacked/`, executables, images, audio, video, saves) anywhere in the tree.

## 2026-10-26 session 5: Russian translation of the restored scenes

- Source: `local/cartagra_fhd_jp/` (full-game Russian translation, Chinese-patch text format `offset|JP` / `offset|RU`; local only).
- All 24 restored scenes align one to one with the tables (4,422 lines, identical JP). Filled the `translation` column of the 3,970 `todo` rows; none missing. The 452 rows reusing the release text are unchanged (33 worded differently in the file).
- `0215-03-00`: leading line break added to 29 lines (release convention for that NVL passage).
- Build: 0 untranslated lines; SCRIPT.PAK 6,380,200 bytes; EVENTCG/OTHCG/VOICE unchanged. Integration test now builds once without tables (reference hashes) and twice with them (identical).
- Not yet checked in game.
- Fixed mixed scripts in the added lines: 111 Latin look-alike letters inside Cyrillic words replaced by Cyrillic (50 lines, 6 scenes); nothing else changed (checked character by character). The `$d` choice separator is markup, not a stray `d`.
- Tables: `source` set to `tsv` in all 452 Russian rows that were `rus` (label only; the build ignores this column and still reuses the release line from `existing`). `languages/_original/`: Russian text removed (`ru_existing` cleared in 452 rows) and `source` set to `todo` everywhere.
- Table format reduced to `row kind voice jp translation`: `source` and `existing` dropped (never read by the build). Before dropping, the 452 release lines in `existing` were copied into `translation`; `SCRIPT.PAK` byte-identical. `languages/_original/` converted too (translation empty). Older formats still load.

## 2026-10-26 session 6: prologue and opening (branch `restore-prologue-opening`)

- User report: in the JP game New Game plays a prologue (CG + narration at the bottom, no UI), then the opening movie, then the burial scene; the Steam game starts with the burial.
- Found: the prologue `0000-op0_HD` is still in the Steam `SCRIPT.PAK`, fully translated (36 op 43 lines), ending with the opening and op 20 (return). Steam's executable starts New Game at `0000-op1`; the prologue is called (op 22) from `0308-02-00`, before part 2. The Rengoku movie moved from `0308-02-00` to the end of `0209-08-00`.
- Movies: Steam swapped the names: Steam `cartagra_movie_02_en` = JP `cartagra_movie_01` (opening, "Sea of Solitude"), Steam `cartagra_movie_01_en` = JP `cartagra_movie_02` (Rengoku). Checked with ffprobe durations and contact sheets. No movie file needs to be shipped.
- Build: new start-sequence step: `0000-op1` calls the prologue after its setup; `0308-02-00` plays Rengoku instead of calling the prologue; `0209-08-00` no longer plays it. Marker IDs of ops 25/119 renumbered (gives the JP numbering). No executable change. SCRIPT.PAK 6,380,340 bytes.
- Tests: 3 unit tests for the new script edits; the integration test compares the reference with `start_sequence=False`.
- In game: checked by the user ("everything works"). The agent did not touch the installed game.

## 2026-10-26 session 7: read text and choices (branch `fix-read-text-and-choices`)

- `restore-prologue-opening` merged into `master` (fast-forward); new branch `fix-read-text-and-choices`.
- User report (Russian Steam build only): "Skip read text" skips unread text; chosen options are not remembered; the `userdata` folder stays empty; saves are elsewhere.
- Saves: the game uses the Steam API; the bundled emulator writes to `%APPDATA%/GSE Saves/4290390/remote/` (`data000.dat` = system data, `dataNNN.*` = slots, `config.dat`). `userdata/22202/` is the emulator's (account ID 22202) and unused. Not a bug.
- System data: per script three bitmaps (read lines, chosen options, passed markers), sized by `_arflag` in `SCRIPT.PAK`. Decoded the record format and the size rule (reproduces all RUS and JP records). The user's `data000.dat` had Steam's short sizes for the 20 ported scenes and no records for the 4 added ones: the patch never updated `_arflag`. That is the cause.
- Fix: the build recomputes `_arflag` (26 scripts changed, 4 records added). The restored scenes now have the JP values.
- Backup of the user's saves before testing: `backup/saves/GSE_4290390_2026-10-26/`.
- Tests: 2 new unit tests; integration test option renamed to `reference=True`.
- The game migrated the user's old `data000.dat` to the new sizes on the next save, keeping all bits. But the 4 added scenes still had no records: the game only tracks scripts before the metadata entries. New scripts are now inserted before the metadata (as in both originals); `_arflag` records sorted by number, `_varset` last.
- In game (test build `--test-start 0217-01-05h`, window 1280x720, saves backed up to `backup/saves/GSE_4290390_2026-10-26_before_ingame_test/`): SKIP greyed on unread lines, stops at the first unread line after a restart of the scene; the chosen option is drawn with a darker box; after a quick save `data000.dat` has records for all 4 added scenes (69 read bits + choice bit in `0217-01-05h`).
- System data is written only on save (also quick save), not on quit.
- Driving notes: the plugin's gfxcapture filter is missing; screenshots via a DPI-aware CopyFromScreen of the client area (PowerShell). At 1280x720 logical (1600x900 physical at 125%), logical click = 2 x pixel of a 0.4-scale shot. Title START (216,588); right click = SYSTEM MENU (TITLE 924,300; Q.SAVE 356,470); confirm Yes (542,382); in-game SKIP (1088,702), EXIT (1258,703, asks to quit). Launch with run_in_background: stopping the launching command kills the game. Long `hold` calls can hang if the PC locks.
- Afterwards: the user's save folder restored from that backup (identical), normal `dist/ru` SCRIPT.PAK installed.
- User: chosen options are still not colored (JP screenshot: chosen option in purple). Native Steam scene `0207-06-00` (slot 16, both options chosen before, bits `03`): text white too, so not a patch issue. Cause: Options > Text1 > "Color of Previously Read Text" was Off. "On" colors all read text (both options lavender); "Only Choices" colors only chosen options. Verified in restored `0217-01-05h`: chose option 2, came back: option 2 lavender, option 1 white. Chosen-option bits: bit first+k = option k chosen.
- My earlier "darker box = chosen marker" reading was wrong; corrected in TECHNICAL_NOTES.
- Afterwards: saves restored from `backup/saves/GSE_4290390_2026-10-26_before_ingame_test/` (so the option is Off again), normal build installed.

## 2026-10-26 session 8: interface translation (branch `translate-interface`)

- Branch `translate-interface` from `fix-read-text-and-choices`. User: base everything on the Steam (Russian) release only; its interface differs from the JP release.
- Interface text is in `CARTAGRA.exe` (.rdata, UTF-8, JP/ZC/EN sets; RU shows EN). Each string loaded by `lea r64,[rip+disp32]`; month names via a relocated pointer table. The RU translators already added `.rtransl` (58 prologue strings) the same way.
- New `exe_text`: references (lea + DIR64 relocs), table `languages/<lang>/interface.tsv` (`id original translation`), checks (original matches, referenced, printf placeholders), adds `.uitext` and redirects references. Optional inputs `../CARTAGRA.exe`, `image/resident/PARTS.PAK` in `inputs.json`.
- Candidates: EN strings loaded within 768 code bytes of a JP string + months; curated to 289, then +7 after the game test (strings merged with the Dear ImGui ones: Window, Delete, Mouse, Font, Clear, All; Game Ver.). BGM/SE/MOVIE excluded (script command names).
- In game: notice, Options (all pages), exit/back-to-title dialogs in Russian. Font has no `«»` -> `❝❞`. Small font (slider labels, version) has no Cyrillic -> 17 labels kept English. Shortened two strings. Final: 277 of 296 translated, 307 references.
- Images: list of English interface pictures documented; replacement PNGs in `languages/<lang>/images/<archive>/<entry>.png`, written as CZ0 (`cztool.encode_cz0`, PNG reader, `cztool export`). First in-game test crashed on Options: `lucapak` dropped the `PARTS/\0` name prefix of `resident/PARTS.PAK`. Fixed (`name_prefix`); recoloured options tabs then shown in game.
- Game folder during the tests: exe and PARTS.PAK swapped, user's config backed up to `backup/saves/GSE_4290390_2026-10-26_before_ui_test/`; afterwards original exe and PARTS.PAK back, save folder restored from that backup (test data in `..._after_ui_test/`). Originals also in `backup/orig/CARTAGRA.exe`, `backup/orig/image/resident/PARTS.PAK`.
- Tests: 31 (incl. integration) pass. The exact `dist/ru` exe was not run in game; it differs from the tested one only by leaving `Game Ver. ` untranslated.

## 2026-10-26 session 9: originals split by source, picture export

- `languages/_original/` renamed to `languages/_original_jp/` (scene tables, JP release text). The Steam interface moved to `languages/_original_steam/en/`: `interface.tsv`, new `images.tsv` (pictures with text; patterns for the manual pages). `_original_steam/jp/` not made (not needed yet).
- New `images` module and `build.py --language <code> --export-images`: exports the 134 listed pictures from the input set to `_original_steam/en/images/` (9 s, 22 MB) and copies missing ones to `languages/<code>/images/`. Done for `ru`. PNGs stay out of git (`.gitignore`).
- New optional `language.json` key `interface_original` (`_original_steam/en` for ru and en). The build replaces only pictures that differ from the exported originals (byte comparison; pixel comparison without them) and writes an archive only when one changed; optional input archives are needed only for changed pictures. `ru` build: 134 unchanged copies skipped, output unchanged.
- Picture list checked by eye: added `title_bg02_en`, `extra_pt`, `graphic_pt`; dropped `CAUTION_TEXT` (background only; the notice text is in the exe), `title_copyright*`, `title_menu1_bar`, `legacy_pt_full2`, `MWIN_BASE03_EN` (no text).

## 2026-10-26 session 10: Russian interface text reviewed

- `languages/ru/interface.tsv` reviewed line by line; 66 translations changed, no rows added. Every interface string the game itself uses is already in the table; what is left untranslated is either debug or log text, or the 18 small-font labels (no Cyrillic in that font) plus `❝LUNA❞` (the title is Latin in the original too).
- Consistent terms: a voice clip is now «фраза» (not «голос»), and a choice option is «вариант» (Положение вариантов, Только варианты, Диалоги и варианты); Wait Time is «пауза» (Пауза на символ, Базовая пауза).
- Clearer options: Hide → Скрыто, the rumble strength options are feminine (Слабая/Средняя/Сильная), While Pressed/Start/Stop → При удержании/Переключение, C/Z → пропуск/перемотка, Rewind/Forward Once → Шаг назад/вперёд, the read-text row → «Выделять прочитанное» (so it no longer repeats «Цвет прочитанного» on the next row), SFX → Звуковые эффекты.
- Smoother dialog and hint wording (corrupted data, quick save, reset to defaults, touch hints, voice collection), several music titles corrected (Snowblossom, Brilliance, Unfathomable, Demise, Sunny Spot, White Period), Grand Epilogue → Финальный эпилог, Nov. → ноя.
- Checked with `exe_text check` (0 problems) and the unit tests. Not checked in game: label widths of the longer strings (Звуковые эффекты, Положение вариантов, Удерж. (A): играть подряд).

## 2026-10-29 session 11: interface pictures translated (manual pages next)

- New `tools/image_text.py` + `languages/ru/images_text.json`: renders the Russian text into copies of the exported originals (Pillow, numpy, scipy, OpenCV in a separate venv; the build stays stdlib-only). Fonts: EB Garamond (OFL, downloaded with the user's OK, not committed) for the serif texts, Arial/Arial Bold for the sans ones.
- Method: fit the English text with the font to the original letters (size by height or width, horizontal scale or letter spacing), learn the look as a layer over the background per signed-distance bin, erase (clear or Telea inpaint), draw the translation at the same baseline. Each picture checked with a sheet: original / English re-rendered / Russian.
- 22 pictures done: `title_menu1-3`, `title_extras`, `extra_title`, `extra_pt2`, `graphic_pt` (No. -> №), `title_logo01/02_en` and `title_bg02_en` (tagline «Недуг души, в котором любовь оборачивается одержимостью и безумием.»), `options_tab_en(_oc)`, `CONFIG_TAB1_en`, `system_menu_icon`, `legacy_pt_minimum`, `legacy_pt_full1`, `save/load_bg_text_1280/1920`, `INDICATOR_ICON_1280/1920_en`. Kept: `pc_button*` (Latin key labels), `extra_pt` (arrows only, no text despite images.tsv).
- Pitfalls fixed on the way: letter look learned from the font's letters was blurred by 1 px misfit (now from the original letters); bins with 1-2 pixels decided the fill; over a black background the alpha was free and clipped the colour; inpainting next to transparency left a blue haze (alpha sharpened, effect limited to the erase radius); the grunge-textured hover state needed a texture fill.
- Word choices for space: tabs Общие/Клавиши/Сенсор/Текст1; system menu Б.СОХР./Б.ЗАГР./В МЕНЮ; buttons ВОЗВРАТ/ПРОПУСК/НАЗАД/ВПЕРЁД/СОХР./ЗАГР./НАСТР./СКРЫТЬ/ЖУРНАЛ; Jump -> Переход (shrunk to the English width). The title menu words are wider than the English ones (up to ~345 of the 380-px cells).
- Build: 22 pictures replaced, archives decode to exactly the PNGs; 33 tests pass with the integration test (it now expects the archives of changed pictures). Not seen in game yet.

## 2026-10-31 session 12: title menu words cut off in game

- User's screenshot: the horizontal title menu cuts every item to the alpha extent of the original English item (START 200, LOAD 185, OPTIONS 275, EXTRAS 237, EXIT 160 px; measured from the screenshot, matches the original sheets within the measurement error). The Russian words (up to ~345 px) were cut.
- Where the widths come from is not found: not in the replaced sheets (the cut ignores them), not as a table in CARTAGRA.exe / SCRIPT.PAK / PARAM.PAK (int16/int32/float, strides up to 64, any constant offset, 1280 scale), not in SYSCG2. Dead ends recorded so they are not repeated.
- `tools/image_text.py`: new `keep_extent` (stay within the original item's columns), `group` for `uniform` (one size per screen), uniform now spans the `copy_to` pictures (same size and squeeze for a word in all button states), letter-weight correction scaled with the size and shared per sheet column (some words looked bolder after shrinking). LOAD -> ЗАГРУЗКА (shorter than ЗАГРУЗИТЬ); title menu `min_sx` 0.75.
- Result checked with a mock-up of the cut-and-centred layout for all three sheets (title and Extras screens). Build: 22 pictures; 33 tests pass. Not yet seen in game.

## 2026-11-02 session 13: interface pictures checked in game

- In game (user's OK; saves backed up to `backup/saves/GSE_4290390_2026-10-31_before_menu_test/` and `..._2026-11-02_before_heading_test/`; installed files that the test replaced backed up to `backup/installed_before_test_2026-11-02/`). Window 1280x720 logical = 1600x901 physical; the client moved between launches, `shot.ps1` reads it. Clicks (logical): title НАЧАТЬ (218,592), ЗАГРУЗКА (365,592), НАСТРОЙКИ (537,592), БОНУСЫ (918,592), Extras НАЗАД (1022,592); system menu (right click) СОХРАНИТЬ (352,264), ЗАГРУЗИТЬ (544,264), НАСТРОЙКИ (784,264), Б.СОХР. (352,448), Б.ЗАГР. (544,448); Options quick menu Сенсорное (824,118), Классическое (1045,118); first save slot (187,216); dialog Да (542,382), Нет (734,382).
- Title and Extras menus: every word whole, hover states fine; the squeezed ЗАГРУЗКА and ВЫХОД look a little lighter. Options tabs, system menu labels, both in-game button layouts (classic and touch): not cut.
- Found English text not in the picture list: the headings drawn into `save_bg`, `load_bg`, `qload_bg`, `options_bg`, `system_menu_bg` (PARTS) and the scene date labels `datewin_text_en` (OTHCG). Added to `images.tsv` and `images_text.json` (EB Garamond, thr 0.85, weight shift -0.75 to match the thin original; Arial for the dates: «10 февраля»).
- First try: ЗАГРУЗКА and СОХРАНЕНИЕ ran into the right-aligned slot number (`No.17`), НАСТРОЙКИ touched the first tab. Limits: save/load headings end by x 240 (1920 scale), options by x 345. SAVE -> ЗАПИСЬ (СОХРАНЕНИЕ would be about half size), also on the side labels. Quick load has no slot number (БЫСТРАЯ ЗАГРУЗКА fits).
- The save date months (`Oct.`) are drawn with a font without Cyrillic (`. 31, 2026`): month translations removed, test updated. `Oct. 27, 2026` shown afterwards.
- Left: the short scene date on the save screen (`Feb. 15`) is a table in the scripts. PARTS.PAK grows from 56 to 91 MB (five CZ0 backgrounds).
- After the fix (rebuilt `dist/ru`, in game): НАСТРОЙКИ leaves a clear gap to the tabs; ЗАГРУЗКА clears `No.17` and (narrowly) `No.200`; ЗАПИСЬ clears `No.20`; БЫСТРАЯ ЗАГРУЗКА fits. From the title, Load opens the quick load page first when a quick save exists (Tab or the page buttons switch). A quick save was made for the test.
- Afterwards: save folder restored from `..._2026-11-02_before_heading_test/` (test state in `..._after_heading_test/`), the game's exe, OTHCG.PAK and PARTS.PAK restored from `backup/installed_before_test_2026-11-02/` (the previous build the user had installed). Tests: 33 pass with the integration test (it now also leaves out picture archives on the reference side; the kept-English list includes the months).

## 2026-11-02 session 14: empty bottom bar labels (FONT1 has no Cyrillic)

- User's screenshots: the bottom bar of Options shows the key icons W and X but no labels (English: Defaults, Close); the same in other menus.
- Cause: the labels are drawn with the small font set `font_win32_1920/FONT1_*` (sizes 35, 37, 52, 56, 72), which has no Cyrillic (1,263 glyphs: Latin, Latin-1, kana). FONT0 (16..44) and SYSFONT have the 66 Cyrillic letters. The same font explains the blank slider labels and months found earlier.
- Font format worked out (TECHNICAL_NOTES "Fonts"): info = header, 3 bytes per glyph, char -> glyph table, char -> width table; sheets CZ2 = palette + bit-packed LZW (flag bit + 15/18-bit codes, LSB first, block ends at 261,885 codes). The CHS project's `drawfont.py` gave the cell layout (100 per row, cell = size + 1). New `cztool.decode_cz2`/`encode_cz2`: byte-identical round trip of three original sheets.
- New `fonts.add_glyphs` + language key `font_glyphs`: copies the letters from FONT0 44 into every FONT1 size and face (bicubic, scaled by size / 44; checked on Latin: within 0.6 px of FONT1's own glyphs), extends the info tables, re-encodes as CZ2. 12 font archives added as optional inputs (`inputs/ru-steam/files/font_win32_1920/`, copied from the game folder, unmodified). Build +28 s.
- With Cyrillic in FONT1, the months, slider labels (Медленно/Быстро, Непрозрачно/Прозрачно, colour names, «0 сек/симв.» ...), «Версия игры» and «Авто» are translated; only «❝LUNA❞» stays English.
- In game (user's OK; saves backed up to `backup/saves/GSE_4290390_2026-11-02_before_font_test/`, the replaced exe and FONT1 files to `backup/installed_before_font_test_2026-11-02/`): the game starts with the new fonts; Russian shown in the bottom bars (Options, Save, Load, Gallery, Music, Videos), all slider labels, «Версия игры 1.0.0.1», «Авто» and the save date «окт. 27, 2026». Only «Закрыть» ran off the right edge (the right box keeps the English left edge): `Close` -> «Назад», checked again. Colour slider: Yellow at both ends as in the original.
- Afterwards: saves unchanged (compared with the backup), exe and FONT1 files restored to the build the user had installed. Tests: 36 pass with the integration test.
