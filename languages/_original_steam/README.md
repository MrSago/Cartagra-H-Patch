# Steam release interface originals

The interface of the Steam release (the base of the Russian release) as a starting point for translating it. Everything here comes from the Steam (Russian) release only; the Japanese release's interface is different.

```text
en/
  interface.tsv   the 296 interface strings of CARTAGRA.exe with the English original, translation empty
  images.tsv      the interface pictures with text: archive, entry (or pattern), what it shows
  images/         those pictures as PNG, made by `python build.py --language ru --export-images` (not in git)
jp/               the Japanese interface of the Steam release (not needed yet; not made)
```

To translate the interface into a new language, copy `en/interface.tsv` to `languages/<code>/interface.tsv`, set `"interface_original": "_original_steam/en"` in its `language.json`, and run `build.py --language <code> --export-images` to get copies of the pictures in `languages/<code>/images/`. The formats are described in [languages/README.md](../README.md#interface-text-interfacetsv).

Do not edit the files in `en/images/`: the build compares a language's pictures with them and replaces only the pictures that differ.
