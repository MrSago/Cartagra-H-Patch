# Original translation tables

The 24 tables as first generated (commit `2265978`, 2026-10-26, folder `translation/`), restored byte for byte from git. They are a starting point for translating the restored scenes into another language. The build never reads this folder; it is not a language (no `language.json`).

Each table lists every line of one restored scene with the Japanese original and, where the Russian release already had the same line, its Russian translation:

| Column | Meaning |
| --- | --- |
| `row` | Line number inside the scene |
| `kind` | `msg` (dialogue) or `select` (choice; options separated by `$d`) |
| `voice` | Voice ID in the Japanese release (0 = no voice) |
| `source` | `rus` = a Russian line exists (`ru_existing`), `todo` = no translation |
| `jp` | Japanese original |
| `ru_existing` | Existing Russian line, for reference (452 of 4,422 lines) |
| `ru` | Translation column (empty in all tables) |

The current format (`languages/<code>/translation/`) names the last two columns `existing` and `translation`; the rows are the same.

To start a new language:

1. Create `languages/<code>/` with a `language.json` (see [../README.md](../README.md)).
2. Copy these tables to `languages/<code>/translation/`.
3. Write the translation into the last column (`ru`). The build reads it as the translation column, whatever the language, and keeps reading tables in this old format.
4. Build. The refreshed tables in `build/<code>/translation/` use the current header, and their `existing` column then holds the lines of that language's own release.

Keep the engine markup: `@Name@` speaker prefix, `$d` choice separator, `$[base$/ruby$]` ruby, `\n` for a line break and `\t` for a tab.
