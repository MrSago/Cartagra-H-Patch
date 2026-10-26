# Original translation tables

The 24 tables as first generated (commit `2265978`, 2026-10-26, folder `translation/`), with all Russian text removed. They are a starting point for translating the restored scenes into another language. The build never reads this folder; it is not a language (no `language.json`).

Each table lists every line of one restored scene with the Japanese original; nothing is translated yet:

| Column | Meaning |
| --- | --- |
| `row` | Line number inside the scene |
| `kind` | `msg` (dialogue) or `select` (choice; options separated by `$d`) |
| `voice` | Voice ID in the Japanese release (0 = no voice) |
| `jp` | Japanese original |
| `translation` | Empty in every row |

The first tables also had `source` and `ru_existing` (the Russian release's line) columns, and called `translation` `ru`; they were dropped because the build does not use them.

To start a new language:

1. Create `languages/<code>/` with a `language.json` (see [../README.md](../README.md)).
2. Copy these tables to `languages/<code>/translation/`.
3. Write the translation into the `translation` column.
4. Build. Rows left empty show an identical line of that language's release if there is one, otherwise the Japanese text.

Keep the engine markup: `@Name@` speaker prefix, `$d` choice separator, `$[base$/ruby$]` ruby, `\n` for a line break and `\t` for a tab.
