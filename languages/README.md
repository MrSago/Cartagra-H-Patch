# Language resources

One folder per target language. `build.py --language <code>` accepts every folder here that has a `language.json`.

```text
languages/<code>/
  language.json        settings (see below)
  translation/*.tsv    translations of restored lines, one table per restored scene (optional)
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

The table format is described in the main [README](../README.md#translating-the-restored-scenes). The build reads the tables here and writes refreshed copies to `build/<code>/translation/`; it never writes into this folder.

`_original/` holds the 24 tables as first generated (Japanese text plus the existing Russian lines), as a basis for new languages; it is not a language and the build does not read it. See [_original/README.md](_original/README.md).

To add a language: add its input set to `definitions/inputs.json`, create `languages/<code>/language.json` with `status` `untested`, optionally copy the tables from `_original/` to `languages/<code>/translation/`, build, and test in game before marking it `incomplete` or `complete`.
