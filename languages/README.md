# Language resources

One folder per target language. `build.py --language <code>` accepts every folder here that has a `language.json`.

```text
languages/<code>/
  language.json        settings (see below)
  translation/*.tsv    translations of restored lines, one table per restored scene (optional)
  interface.tsv        translation of the interface text in CARTAGRA.exe (optional)
  scene_titles.tsv     translation of the scene headings of the save and load screens (optional)
  images/<archive>/<entry>.png   interface pictures to translate (optional; not in git)
  images_text.json     the texts in the interface pictures and their translations, for tools/image_text.py (optional)
_original_jp/          the scene tables with the Japanese release's text (see _original_jp/README.md)
_original_steam/en/    the Steam release's English interface (see _original_steam/README.md)
```

`language.json` keys:

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
| `font_numero` | Optional (`true`). Redraw the large fonts' `№`, which has the Japanese shape (`No.`), as the Cyrillic sign; the save and load screens show the slot number with it when the interface table translates `No.%d` as `№%d`. The build then writes `files/font_win32_1920/FONT0__INFO.PAK` and `FONT0_*.PAK` |

The table formats are described in the main README: [scene tables](../README.md#translating-the-restored-scenes), [interface table and pictures](../README.md#translating-the-interface). The build reads the files here and writes copies of the tables in the current format to `build/<code>/`; it never writes into this folder.

The `_original_*` folders are not languages; they hold starting points for new languages:

- `_original_jp/`: the 24 scene tables as first generated, with the Japanese release's text only (Russian removed). The build does not read it. See [_original_jp/README.md](_original_jp/README.md).
- `_original_steam/en/`: the English interface of the Steam release (the interface table, the list of pictures with text, the exported pictures). The Steam release also has a Japanese interface; it is not needed yet (`_original_steam/jp/` would hold it). See [_original_steam/README.md](_original_steam/README.md).

To add a language: add its input set to `definitions/inputs.json`, create `languages/<code>/language.json` with `status` `untested`, optionally copy the scene tables from `_original_jp/` to `languages/<code>/translation/` and `_original_steam/en/interface.tsv` to `languages/<code>/interface.tsv`, set `interface_original` to `_original_steam/en` and run `build.py --language <code> --export-images` for the pictures, build, and test in game before marking it `incomplete` or `complete`.
