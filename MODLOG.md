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
