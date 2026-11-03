"""
Build pipeline: original files in -> patch files out.

Inputs (read only):
  jp_dir      Japanese FHD 2023 release, files/ folder (input set "jp-fhd")
  target_dir  the Steam build the patch is for, files/ folder (input set of the language);
              its CARTAGRA.exe is read from the folder above
  languages/<lang>/translation/*.tsv  translations of restored lines (optional)
  languages/<lang>/interface.tsv      translation of the executable's interface strings (optional)
  languages/<lang>/scene_titles.tsv   translation of the scene headings of the save screens (optional)
  languages/<lang>/images/<archive>/<entry>.png  replacement pictures (optional; copies identical to
                                                 the exported originals are skipped)
  definitions/restoration.json        what to restore (shared by all languages)

Outputs:
  build/<lang>/staging/      archives while they are being written
  build/<lang>/translation/  the tables in the current format, one per restored scene (empty translation
                             where the language has none: a starting point for new tables)
  build/<lang>/interface.tsv the interface table in the current format (when the language has one)
  dist/<lang>/               the finished patch: files/..., CARTAGRA.exe (when the interface is
                             translated) + BUILD_INFO.txt
                             (replaced only after the whole build succeeded)
"""

import collections
import os
import shutil
import struct

from . import cztool
from . import exe_text
from . import fonts
from . import gallery
from . import lucascript as ls
from . import script_port as sp
from .images import changed_images, language_images, reference_png
from .lucapak import (
    LucaPak,
    SEC_HASH,
    append_copy,
    append_missing,
    read_index,
    replace_from,
    xxh64,
)
from .project import BUILD_DIR, DIST_DIR, BuildError, sha256_file

INFO_FILE = "BUILD_INFO.txt"
EXE_NAME = "CARTAGRA.exe"


class BuildOptions:
    def __init__(
        self,
        language,
        jp_dir,
        target_dir,
        voice=True,
        scenes=None,
        test_start=None,
        test_set=(),
        reference=False,
    ):
        self.language = (
            language  # loaded languages/<code>/language.json (project.load_language)
        )
        self.jp_dir = jp_dir
        self.target_dir = target_dir
        self.voice = voice
        # True reproduces the build tested before 2026-10-26 (no start sequence, no _arflag update, new scripts
        # after the metadata entries, no interface translation): tests only
        self.reference = reference
        self.scenes = scenes  # None = all
        self.test_start = test_start
        self.test_set = list(test_set)  # [(var, value)]

    @property
    def output_name(self):
        """dist/ and build/ folder name; debug builds never overwrite the normal one."""
        if self.test_start:
            return self.language["code"] + "-test"
        return self.language["code"] + ("-partial" if self.scenes else "")


def archive_index(files_dir, sub, overrides=None):
    """[(ARCHIVE, id_start, names)] for every PAK in files_dir/sub; overrides: {FILE.PAK: path}."""
    out = []
    folder = os.path.join(files_dir, sub)
    for f in sorted(os.listdir(folder)):
        if f.upper().endswith(".PAK"):
            path = (overrides or {}).get(f.upper(), os.path.join(folder, f))
            start, names = read_index(path)
            out.append((f[:-4].upper(), start, names))
    return out


def set_entry(entry, data):
    entry.data = data
    entry.pad = None
    entry.sections[SEC_HASH] = xxh64(data)


def test_stub(data, scene, sets=()):
    """Keep the script's setup instructions (up to op 27), set variables (op 1) and jump to `scene`."""
    instrs = ls.parse(data)
    end = next(k for k, i in enumerate(instrs) if i.op == 27)
    stub = instrs[: end + 1] + [
        ls.Instr(1, 0, None, struct.pack("<HH", var, val)) for var, val in sets
    ]
    stub.append(ls.Instr(ls.OP_JUMP_SCRIPT, 1, 1, ls.make_str(scene.encode("cp932"))))
    for i in stub:
        i.offset = None
    return ls.assemble(stub)


def _patch_archive(
    log, label, orig, donor, out, remap_parent=True, replace=(), split=None, append=True
):
    base = LucaPak.read(orig)
    jp = LucaPak.read(donor)
    n0 = len(base.entries)
    added = append_missing(base, jp, remap_parent) if append else []
    replace_from(base, jp, replace)
    for jp_name, new_name in (split or {}).items():
        append_copy(base, jp, jp_name, new_name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    base.write(out)
    extra = len(base.entries) - n0
    ids = (
        f" (ids {base.id_start + n0}..{base.id_start + len(base.entries) - 1})"
        if extra
        else ""
    )
    log(
        f"  {label}: {n0} original, {len(replace)} replaced in place, {len(added)} appended"
        f"{', ' + str(len(split)) + ' split copies' if split else ''}{ids} ({os.path.getsize(out):,} bytes)"
    )
    return base


def run_build(opt, restoration, log=print):
    """Build the patch for opt.language. Returns the dist folder. Raises BuildError."""
    lang = opt.language
    work = os.path.join(BUILD_DIR, opt.output_name)
    staging = os.path.join(work, "staging")
    files_out = os.path.join(staging, "files")
    tables_out = os.path.join(work, "translation")
    dist = os.path.join(DIST_DIR, opt.output_name)
    for d in (staging, tables_out):
        if os.path.isdir(d):
            shutil.rmtree(d)
    os.makedirs(files_out)
    os.makedirs(tables_out)

    jp, tg = opt.jp_dir, opt.target_dir
    censored = restoration["censored_images"]
    split_images = {
        (arch, name): new
        for arch, m in restoration["split_images"].items()
        if not arch.startswith("_")
        for name, new in m.items()
    }
    ported = list(restoration["censored_scenes"]["scenes"])
    removed = dict(restoration["removed_scenes"]["scenes"])

    steps = 5 if opt.voice else 4
    log(f"[1/{steps}] Images")
    eventcg_out = os.path.join(files_out, "image", "EVENTCG.PAK")
    eventcg = _patch_archive(
        log,
        "EVENTCG.PAK",
        os.path.join(tg, "image", "EVENTCG.PAK"),
        os.path.join(jp, "image", "EVENTCG.PAK"),
        eventcg_out,
        replace=censored["EVENTCG"],
        split={n: new for (a, n), new in split_images.items() if a == "EVENTCG"},
    )
    othcg_out = os.path.join(files_out, "image", "OTHCG.PAK")
    _patch_archive(
        log,
        "OTHCG.PAK",
        os.path.join(tg, "image", "OTHCG.PAK"),
        os.path.join(jp, "image", "OTHCG.PAK"),
        othcg_out,
        replace=censored["OTHCG"],
        append=False,
    )
    if not opt.reference:
        _build_gallery(
            log,
            jp,
            tg,
            files_out,
            {"EVENTCG.PAK": eventcg_out, "OTHCG.PAK": othcg_out},
            split_images,
        )

    voice_index_path = os.path.join(tg, "voice", "VOICE.PAK")
    if opt.voice:
        log(f"[2/{steps}] Voices")
        voice_index_path = os.path.join(files_out, "voice", "VOICE.PAK")
        _patch_archive(
            log,
            "VOICE.PAK",
            os.path.join(tg, "voice", "VOICE.PAK"),
            os.path.join(jp, "voice", "VOICE0.PAK"),
            voice_index_path,
            remap_parent=False,
        )

    log(f"[{steps - 2}/{steps}] Scenes")
    tg_script = LucaPak.read(os.path.join(tg, "SCRIPT.PAK"))
    jp_script = LucaPak.read(os.path.join(jp, "SCRIPT.PAK"))
    jp_by = {e.name: e for e in jp_script.entries}
    tg_by = {e.name: e for e in tg_script.entries}
    tg_names = [e.name for e in tg_script.entries]
    tg_original = [
        (e.name, e.data) for e in tg_script.entries if not e.name.startswith("_")
    ]
    first_meta = (
        len(tg_script.entries)
        if opt.reference
        else next(k for k, e in enumerate(tg_script.entries) if e.name.startswith("_"))
    )
    res = sp.ResourceMap(
        archive_index(jp, "image"),
        archive_index(tg, "image", {"EVENTCG.PAK": eventcg_out}),
        archive_index(jp, "voice"),
        archive_index(tg, "voice", {"VOICE.PAK": voice_index_path}),
        sp.read_varnames(jp_by["_varname"].data),
        sp.read_varnames(tg_by["_varname"].data),
        image_aliases=split_images,
    )
    tg_scenes = {
        e.name: e.data for e in tg_script.entries if not e.name.startswith("_")
    }
    res.next_select_id = sp.free_select_id(tg_scenes.values())
    tr = sp.Translations(tg_scenes)
    log(
        f"  translation memory: {len(tr.lines)} lines, {len(tr.names)} speaker names; "
        f"new SELECT flag slots from {res.next_select_id}; {len(res.var)} variable IDs remapped"
    )

    unknown = sorted(set(opt.scenes or ()) - set(ported) - set(removed))
    if unknown:
        raise BuildError(f"unknown scene(s): {', '.join(unknown)}")
    scenes = [
        s for s in ported + list(removed) if opt.scenes is None or s in opt.scenes
    ]
    total = collections.Counter()
    for name in scenes:
        if name not in jp_by:
            raise BuildError(f"{name} is not in the JP SCRIPT.PAK")
        data, rows = sp.port_script(
            jp_by[name].data,
            res,
            tr,
            sp.load_tsv(os.path.join(lang["translation_dir"], name + ".tsv")),
            name,
        )
        _, bad = ls.check(data)
        if bad:
            raise BuildError(f"{name}: bad jump targets after porting: {bad[:5]}")
        sp.write_tsv(os.path.join(tables_out, name + ".tsv"), rows)
        counts = {
            k: sum(1 for r in rows if r["source"] == k) for k in ("rus", "tsv", "todo")
        }
        total.update(counts)
        jp_exit = sp.final_jump(jp_by[name].data)
        if name in removed:
            pred = removed[name]
            if pred not in tg_by:
                raise BuildError(
                    f"{pred} (predecessor of {name}) is not in the target SCRIPT.PAK"
                )
            pdata, n = sp.retarget_jump(
                tg_by[pred].data, jp_by[pred].data, name, jp_exit
            )
            set_entry(tg_by[pred], pdata)
            # scripts come before the metadata entries, as in the originals: the game keeps read and
            # choice flags only for those (the metadata entries move; nothing refers to them by number)
            new = type(tg_by[pred])(name, data, b"", {})
            set_entry(new, data)
            tg_script.entries.insert(first_meta, new)
            first_meta += 1
            how = f"added; {pred} now jumps here instead of {jp_exit}"
        else:
            if name not in tg_by:
                raise BuildError(f"{name} is not in the target SCRIPT.PAK")
            tg_exit = sp.final_jump(tg_by[name].data)
            if tg_exit != jp_exit:
                log(
                    f"  WARNING: {name}: JP exits to {jp_exit}, target exited to {tg_exit}"
                )
            set_entry(tg_by[name], data)
            how = "replaced"
        log(
            f"  {name:12s} {len(rows):4d} lines: {counts['rus']:4d} existing, {counts['tsv']:4d} translated, "
            f"{counts['todo']:4d} untranslated | {how}"
        )
    if res.missing:
        log(f"  WARNING: unmapped resources (kept or silenced): {dict(res.missing)}")

    for fix in restoration["script_fixes"]["fixes"]:
        name = fix["script"]
        if name in scenes:
            raise BuildError(f"{name} is ported; its script fix does not apply")
        if fix["kind"] == "retarget":
            data, n = sp.retarget_image(
                tg_by[name].data,
                eventcg.id_of(fix["image"]),
                eventcg.id_of(fix["new_image"]),
            )
        elif fix["kind"] == "move_y":
            data, n = sp.patch_move_y(
                tg_by[name].data,
                eventcg.id_of(fix["image"]),
                fix["old_y"],
                fix["new_y"],
            )
        else:
            raise BuildError(f"unknown script fix kind {fix['kind']!r}")
        if n == 0:
            raise BuildError(
                f"{name}: script fix {fix['kind']} {fix['image']} matched nothing"
            )
        set_entry(tg_by[name], data)
        log(f"  {name:12s} script fix: {fix['kind']} {fix['image']} ({n}x)")

    if not opt.reference:
        _restore_start_sequence(log, restoration, jp_by, tg_by, scenes)
        # before the test stub, which replaces the New Game script
        try:
            data, labels, moved = sp.rebuild_scr_label(
                tg_by["_scr_label"].data,
                tg_original,
                jp_by["_scr_label"].data,
                [
                    (e.name, e.data)
                    for e in jp_script.entries
                    if not e.name.startswith("_")
                ],
                tg_script.entries,
                set(scenes),
            )
        except (KeyError, ValueError) as e:
            raise BuildError(f"_scr_label: {e}")
        set_entry(tg_by["_scr_label"], data)
        log(
            f"  _scr_label: {labels} labels; {moved} offsets of the target build corrected"
        )
        try:
            data, n, untranslated = sp.translate_varstr(
                tg_by["_varstr"].data, sp.load_titles(lang["scene_titles"])
            )
        except ValueError as e:
            raise BuildError(f"{lang['scene_titles']}: {e}")
        if n:
            set_entry(tg_by["_varstr"], data)
            log(
                f"  _varstr: {n} scene headings translated"
                + (f"; untranslated: {', '.join(untranslated)}" if untranslated else "")
            )

    if opt.test_start:
        start = restoration["new_game_script"]
        set_entry(
            tg_by[start], test_stub(tg_by[start].data, opt.test_start, opt.test_set)
        )
        log(f"  TEST BUILD: {start} replaced by a stub that jumps to {opt.test_start}")
    if not opt.reference:
        arflag = tg_by["_arflag"]
        data, changed = sp.rebuild_arflag(arflag.data, tg_names, tg_script.entries)
        set_entry(arflag, data)
        log(f"  _arflag: read/choice flag sizes updated for {len(changed)} scripts")
    script_out = os.path.join(files_out, "SCRIPT.PAK")
    tg_script.write(script_out)
    log(
        f"  SCRIPT.PAK: {len(scenes)} scenes ({total['rus']} existing lines reused, {total['tsv']} translated, "
        f"{total['todo']} untranslated) ({os.path.getsize(script_out):,} bytes)"
    )

    log(f"[{steps - 1}/{steps}] Interface")
    original_text = (
        restoration["exe_original_text"] if lang.get("exe_original_text") else None
    )
    interface = (
        (0, 0)
        if opt.reference
        else _build_interface(
            log,
            opt,
            work,
            staging,
            files_out,
            restoration["exe_fixes"]["fixes"],
            original_text,
        )
    )

    log(f"[{steps}/{steps}] Output")
    _write_info(staging, opt, total, len(scenes), interface)
    if os.path.isdir(dist):
        if not os.path.isfile(os.path.join(dist, INFO_FILE)):
            raise BuildError(
                f"{dist} exists but was not made by this build (no {INFO_FILE}); move it away first"
            )
        shutil.rmtree(dist)
    os.makedirs(DIST_DIR, exist_ok=True)
    os.replace(staging, dist)
    return dist


def _build_gallery(log, jp, tg, files_out, patched, aliases):
    """
    Add the JP release's gallery pictures to the target's CG gallery (PARAM.PAK) and put the previews
    (image/SYSCG2.PAK) in the new slot order (see gallery.py).
    """
    param = LucaPak.read(os.path.join(tg, "PARAM.PAK"))
    jp_param = LucaPak.read(os.path.join(jp, "PARAM.PAK"))
    entry = next((e for e in param.entries if e.name == gallery.ENTRY), None)
    jp_entry = next((e for e in jp_param.entries if e.name == gallery.JP_ENTRY), None)
    if entry is None or jp_entry is None:
        raise BuildError(
            f"PARAM.PAK: no {gallery.ENTRY} in the target or no {gallery.JP_ENTRY} in the JP release"
        )
    out_images = archive_index(tg, "image", patched)
    try:
        target = gallery.Gallery.parse(entry.data)
        merged, added, origins, left_out = gallery.merge(
            target,
            gallery.Gallery.parse(jp_entry.data),
            gallery.image_map(archive_index(jp, "image"), out_images, aliases),
            [(start, len(names)) for _, start, names in out_images],
        )
    except ValueError as e:
        raise BuildError(f"PARAM.PAK {gallery.ENTRY}: {e}") from None
    set_entry(entry, merged.build())
    param.write(os.path.join(files_out, "PARAM.PAK"))
    previews = gallery.build_previews(
        LucaPak.read(os.path.join(tg, "image", "SYSCG2.PAK")),
        LucaPak.read(os.path.join(jp, "image", "SYSCG2.PAK")),
        origins,
    )
    previews.write(os.path.join(files_out, "image", "SYSCG2.PAK"))
    new_slots = sum(1 for source, _ in origins if source == "jp")
    jp_names = {
        start + i: n
        for _, start, names in archive_index(jp, "image")
        for i, n in enumerate(names)
    }
    log(
        f"  PARAM.PAK: CG gallery {len(target.slots)} -> {len(merged.slots)} slots ({gallery.pages(target)} -> "
        f"{gallery.pages(merged)} pages), {added} pictures added in {new_slots} new slots and existing ones"
        + (
            f"; not in the patched archives: {', '.join(jp_names.get(i, str(i)) for i in left_out)}"
            if left_out
            else ""
        )
    )
    log(
        f"  SYSCG2.PAK: {len(origins)} gallery previews, {new_slots} of them from the JP release"
    )


def _restore_start_sequence(log, restoration, jp_by, tg_by, scenes):
    """New Game plays the prologue and the opening again; 0308-02-00 plays the Rengoku movie again."""
    seq = restoration["start_sequence"]
    prologue, first, mv = (
        seq["prologue"],
        restoration["new_game_script"],
        seq["moved_movie"],
    )
    if sp.final_jump(jp_by[prologue].data) != first:
        raise BuildError(f"JP {prologue} does not lead to {first}")
    for name in (first, mv["from"], mv["to"]):
        if name in scenes:
            raise BuildError(f"{name} is ported; the start sequence fix does not apply")
    callers = [
        n
        for n, e in tg_by.items()
        if not n.startswith("_") and sp.calls_to(e.data, prologue)
    ]
    if callers != [mv["to"]]:
        raise BuildError(f"{prologue} is called by {callers}, expected only {mv['to']}")
    try:
        data, block = sp.cut_movie(tg_by[mv["from"]].data, mv["movie"])
        set_entry(tg_by[mv["from"]], data)
        data, n = sp.replace_calls(tg_by[mv["to"]].data, prologue, block)
        set_entry(tg_by[mv["to"]], data)
        set_entry(tg_by[first], sp.insert_call(tg_by[first].data, prologue))
    except ValueError as e:
        raise BuildError(f"start sequence: {e}") from None
    log(f"  {first:12s} start sequence: calls {prologue} (prologue + opening) first")
    log(
        f"  {mv['to']:12s} start sequence: plays {mv['movie']} instead of calling {prologue} ({n}x)"
    )
    log(f"  {mv['from']:12s} start sequence: {mv['movie']} removed")


def _build_interface(
    log, opt, work, staging, files_out, exe_fixes=(), original_text=None
):
    """
    Restore the executable's original text (restoration.json "exe_original_text", when given),
    translate its interface strings, apply the executable fixes (restoration.json "exe_fixes")
    and replace images. Returns (strings translated, images).
    """
    lang = opt.language
    try:
        rows = exe_text.load_table(lang["interface_table"])
    except ValueError as e:
        raise BuildError(str(e)) from None
    if rows:
        exe_text.write_table(os.path.join(work, "interface.tsv"), rows)
    translated = 0
    if any(r["translation"] for r in rows) or exe_fixes:
        exe = os.path.normpath(os.path.join(opt.target_dir, os.pardir, EXE_NAME))
        if not os.path.isfile(exe):
            raise BuildError(
                f"{exe} not found: copy {EXE_NAME} of the target release into the input set "
                f"(next to its files/ folder)"
            )
        with open(exe, "rb") as f:
            data = f.read()
        if original_text:
            try:
                data, n = exe_text.restore_original_text(
                    data, original_text["section"], original_text["redirects"]
                )
            except ValueError as e:
                raise BuildError(f"{exe}: {e}") from None
            log(
                f"  {EXE_NAME}: "
                + (
                    f"{n} strings point to the original text again, section {original_text['section']} removed"
                    if n
                    else f"no section {original_text['section']}: original text kept"
                )
            )
        if any(r["translation"] for r in rows):
            try:
                data, translated, nrefs = exe_text.translate(data, rows)
            except ValueError as e:
                raise BuildError(
                    f"{lang['interface_table']} does not fit {exe}:\n  "
                    + str(e).replace("\n", "\n  ")
                ) from None
            log(
                f"  {EXE_NAME}: {translated} of {len(rows)} interface strings translated "
                f"({nrefs} references redirected to section {exe_text.SECTION_NAME.decode()})"
            )
        try:
            data = exe_text.apply_fixes(data, exe_fixes)
        except ValueError as e:
            raise BuildError(f"{exe}: {e}") from None
        for fix in exe_fixes:
            log(f"  {EXE_NAME}: fix applied: {fix['name']}")
        os.makedirs(staging, exist_ok=True)
        with open(os.path.join(staging, EXE_NAME), "wb") as f:
            f.write(data)
    else:
        log(
            f"  {EXE_NAME}: not changed ("
            + ("no translations in interface.tsv)" if rows else "no interface.tsv)")
        )

    images = 0
    copies = sum(len(p) for p in language_images(lang).values())
    for arch, pngs in changed_images(lang).items():
        rel = os.path.join("image", *arch.split("/")) + ".PAK"
        out = os.path.join(files_out, rel)
        src = out if os.path.isfile(out) else os.path.join(opt.target_dir, rel)
        if not os.path.isfile(src):
            raise BuildError(
                f"replacement images in {os.path.join(lang['images_dir'], arch)}: "
                f"{os.path.join(opt.target_dir, rel)} not found (copy it into the input set)"
            )
        pak = LucaPak.read(src)
        by = {e.name: e for e in pak.entries}
        replaced = 0
        for png in pngs:
            name = os.path.splitext(os.path.basename(png))[0]
            if name not in by or by[name].data[:2] != b"CZ":
                raise BuildError(f"{png}: {arch}.PAK has no image named {name!r}")
            hd = cztool.header(by[name].data)
            try:
                w, h, rgba = cztool.read_png(png)
            except (ValueError, OSError) as e:
                raise BuildError(str(e)) from None
            if (w, h) != (hd["width"], hd["height"]):
                raise BuildError(
                    f"{png}: {w}x{h} pixels, the original is {hd['width']}x{hd['height']} "
                    f"(export the original with build.py --export-images and keep its size)"
                )
            if (
                not reference_png(lang, arch, png)
                and cztool.decode(by[name].data)[1] == rgba
            ):
                continue  # no exported original to compare files with, but the pixels are unchanged
            set_entry(by[name], cztool.encode_cz0(by[name].data, rgba))
            replaced += 1
        if not replaced:
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        pak.write(out)
        images += replaced
        log(
            f"  {arch}.PAK: {replaced} pictures replaced ({os.path.getsize(out):,} bytes)"
        )
    log(
        f"  pictures: {images} replaced, {copies - images} unchanged copies of the originals skipped"
    )
    if lang.get("font_glyphs"):
        try:
            fonts.add_glyphs(opt.target_dir, files_out, lang["font_glyphs"], log=log)
        except (OSError, ValueError) as e:
            raise BuildError(f"font_glyphs: {e}") from None
    if lang.get("font_numero"):
        try:
            fonts.redraw_numero(opt.target_dir, files_out, log=log)
        except (OSError, ValueError) as e:
            raise BuildError(f"font_numero: {e}") from None
    return translated, images


def _write_info(staging, opt, total, nscenes, interface=(0, 0)):
    lang = opt.language
    lines = [
        f"Cartagra cut-content patch - language: {lang['code']} ({lang['name']})",
        f"Status: {lang['status'].upper()} - {lang['status_note']}",
        f"Target: {lang['target_description']}",
    ]
    if opt.test_start:
        lines.append(
            f"TEST BUILD: New Game jumps to {opt.test_start}. Do NOT install for normal play."
        )
    elif opt.scenes:
        lines.append(
            f"PARTIAL BUILD: only {', '.join(opt.scenes)} restored. Do NOT install for normal play."
        )
    if total["todo"]:
        lines.append(
            f"Untranslated restored lines: {total['todo']} (shown as Japanese placeholder text)"
        )
    lines.append(
        f"Restored scenes: {nscenes}; voices: {'restored' if opt.voice else 'not included'}"
    )
    lines.append(
        f"Interface: {interface[0]} strings translated, {interface[1]} images replaced"
    )
    lines += [
        "",
        "Copy each file to the same path inside the game folder (back up the originals first):",
        "",
    ]
    for dirpath, _, names in sorted(os.walk(staging)):
        for n in sorted(names):
            if n == INFO_FILE:
                continue
            path = os.path.join(dirpath, n)
            rel = os.path.relpath(path, staging).replace(os.sep, "/")
            lines.append(f"  {rel:24s} -> <game>/{rel}   sha256 {sha256_file(path)}")
    with open(
        os.path.join(staging, INFO_FILE), "w", encoding="utf-8", newline="\n"
    ) as f:
        f.write("\n".join(lines) + "\n")
