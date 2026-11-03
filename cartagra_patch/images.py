"""
Interface pictures with text (Steam release).

languages/_original_steam/en/images.tsv lists them (UTF-8, tab-separated):
  archive  path of the archive below files/image/ without .PAK (e.g. resident/PARTS)
  entry    entry name, or a pattern with * and ? (e.g. en_*)
  shows    what the picture shows (documentation only)

`export` writes them as PNGs to languages/_original_steam/en/images/<archive>/<entry>.png; a language gets
copies in languages/<code>/images/ to edit. The build replaces only the pictures that differ from the
exported originals, so unedited copies change nothing.
"""

import filecmp
import fnmatch
import os
import shutil

from . import cztool
from .lucapak import LucaPak

LIST_COLUMNS = ("archive", "entry", "shows")


def load_list(path):
    """[(archive, entry pattern, shows)]"""
    rows = []
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        if [c for c in LIST_COLUMNS if c not in header]:
            raise ValueError(
                f"{path}: the header must have the columns {', '.join(LIST_COLUMNS)}"
            )
        col = {name: i for i, name in enumerate(header)}
        for line in f:
            cells = line.rstrip("\n").split("\t")
            if len(cells) >= len(header):
                rows.append(tuple(cells[col[c]] for c in LIST_COLUMNS))
    return rows


def archive_path(files_dir, archive):
    return os.path.join(files_dir, "image", *archive.split("/")) + ".PAK"


def export(files_dir, rows, out_root, log=print):
    """Write the listed pictures of the archives in files_dir/image/ as PNGs. Returns the number written."""
    by_archive = {}
    for archive, pattern, _ in rows:
        by_archive.setdefault(archive, []).append(pattern)
    total = 0
    for archive, patterns in by_archive.items():
        path = archive_path(files_dir, archive)
        if not os.path.isfile(path):
            raise ValueError(
                f"{path} not found: copy it into the input set to export its pictures"
            )
        pak = LucaPak.read(path)
        names = [e.name for e in pak.entries if e.data[:2] == b"CZ"]
        wanted = set()
        for pattern in patterns:
            match = fnmatch.filter(names, pattern)
            if not match:
                raise ValueError(f"{archive}.PAK has no picture matching {pattern!r}")
            wanted.update(match)
        done = cztool.export(pak, os.path.join(out_root, *archive.split("/")), wanted)
        total += len(done)
        log(f"  {archive}.PAK: {len(done)} pictures")
    return total


def copy_missing(src_root, dst_root):
    """Copy the PNGs of src_root that dst_root does not have yet (never overwrites). Returns the number copied."""
    copied = 0
    for dirpath, _, names in os.walk(src_root):
        for n in names:
            if not n.lower().endswith(".png"):
                continue
            dst = os.path.join(dst_root, os.path.relpath(dirpath, src_root), n)
            if not os.path.exists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(os.path.join(dirpath, n), dst)
                copied += 1
    return copied


def language_images(lang):
    """{archive: [png paths]} of languages/<code>/images/."""
    out = {}
    root = lang["images_dir"]
    for dirpath, _, names in os.walk(root):
        pngs = sorted(
            os.path.join(dirpath, n) for n in names if n.lower().endswith(".png")
        )
        if pngs:
            out[os.path.relpath(dirpath, root).replace(os.sep, "/")] = pngs
    return dict(sorted(out.items()))


def reference_png(lang, archive, png):
    """The exported original of a language's picture, or None (no interface_original or not exported)."""
    if not lang.get("interface_original_dir"):
        return None
    ref = os.path.join(
        lang["interface_original_dir"],
        "images",
        *archive.split("/"),
        os.path.basename(png),
    )
    return ref if os.path.isfile(ref) else None


def changed_images(lang):
    """
    {archive: [png paths]} of the language's pictures that are not byte-identical to the exported original
    (pictures without an exported original count as changed; the build compares their pixels).
    """
    out = {}
    for archive, pngs in language_images(lang).items():
        changed = [
            p
            for p in pngs
            if not (
                reference_png(lang, archive, p)
                and filecmp.cmp(p, reference_png(lang, archive, p), shallow=False)
            )
        ]
        if changed:
            out[archive] = changed
    return out
