"""
Build pipeline: original files in -> patch files out.

Inputs (read only):
  jp_dir      Japanese FHD release, files/ folder (input set "jp-fhd")
  target_dir  the Steam build the patch is for, files/ folder (input set of the language)
  languages/<lang>/translation/*.tsv  translations of restored lines (optional)
  definitions/restoration.json        what to restore (shared by all languages)

Outputs:
  build/<lang>/staging/      archives while they are being written
  build/<lang>/translation/  the tables in the current format, one per restored scene (empty translation
                             where the language has none: a starting point for new tables)
  dist/<lang>/               the finished patch: files/... + BUILD_INFO.txt
                             (replaced only after the whole build succeeded)
"""

import collections
import os
import shutil
import struct

from . import lucascript as ls
from . import script_port as sp
from .lucapak import LucaPak, SEC_HASH, append_copy, append_missing, read_index, replace_from, xxh64
from .project import BUILD_DIR, DIST_DIR, BuildError, sha256_file

INFO_FILE = "BUILD_INFO.txt"


class BuildOptions:
    def __init__(self, language, jp_dir, target_dir, voice=True, scenes=None, test_start=None, test_set=(),
                 start_sequence=True):
        self.language = language  # loaded languages/<code>/language.json (project.load_language)
        self.jp_dir = jp_dir
        self.target_dir = target_dir
        self.voice = voice
        self.start_sequence = start_sequence  # False only to compare with builds made before it existed
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
    stub = instrs[: end + 1] + [ls.Instr(1, 0, None, struct.pack("<HH", var, val)) for var, val in sets]
    stub.append(ls.Instr(ls.OP_JUMP_SCRIPT, 1, 1, ls.make_str(scene.encode("cp932"))))
    for i in stub:
        i.offset = None
    return ls.assemble(stub)


def _patch_archive(log, label, orig, donor, out, remap_parent=True, replace=(), split=None, append=True):
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
    ids = f" (ids {base.id_start + n0}..{base.id_start + len(base.entries) - 1})" if extra else ""
    log(f"  {label}: {n0} original, {len(replace)} replaced in place, {len(added)} appended"
        f"{', ' + str(len(split)) + ' split copies' if split else ''}{ids} ({os.path.getsize(out):,} bytes)")
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
    split_images = {(arch, name): new for arch, m in restoration["split_images"].items()
                    if not arch.startswith("_") for name, new in m.items()}
    ported = list(restoration["censored_scenes"]["scenes"])
    removed = dict(restoration["removed_scenes"]["scenes"])

    steps = 4 if opt.voice else 3
    log(f"[1/{steps}] Images")
    eventcg_out = os.path.join(files_out, "image", "EVENTCG.PAK")
    eventcg = _patch_archive(log, "EVENTCG.PAK", os.path.join(tg, "image", "EVENTCG.PAK"),
                             os.path.join(jp, "image", "EVENTCG.PAK"), eventcg_out,
                             replace=censored["EVENTCG"],
                             split={n: new for (a, n), new in split_images.items() if a == "EVENTCG"})
    _patch_archive(log, "OTHCG.PAK", os.path.join(tg, "image", "OTHCG.PAK"), os.path.join(jp, "image", "OTHCG.PAK"),
                   os.path.join(files_out, "image", "OTHCG.PAK"), replace=censored["OTHCG"], append=False)

    voice_index_path = os.path.join(tg, "voice", "VOICE.PAK")
    if opt.voice:
        log(f"[2/{steps}] Voices")
        voice_index_path = os.path.join(files_out, "voice", "VOICE.PAK")
        _patch_archive(log, "VOICE.PAK", os.path.join(tg, "voice", "VOICE.PAK"), os.path.join(jp, "voice", "VOICE0.PAK"),
                       voice_index_path, remap_parent=False)

    log(f"[{steps - 1}/{steps}] Scenes")
    tg_script = LucaPak.read(os.path.join(tg, "SCRIPT.PAK"))
    jp_script = LucaPak.read(os.path.join(jp, "SCRIPT.PAK"))
    jp_by = {e.name: e for e in jp_script.entries}
    tg_by = {e.name: e for e in tg_script.entries}
    res = sp.ResourceMap(
        archive_index(jp, "image"), archive_index(tg, "image", {"EVENTCG.PAK": eventcg_out}),
        archive_index(jp, "voice"), archive_index(tg, "voice", {"VOICE.PAK": voice_index_path}),
        sp.read_varnames(jp_by["_varname"].data), sp.read_varnames(tg_by["_varname"].data),
        image_aliases=split_images,
    )
    tg_scenes = {e.name: e.data for e in tg_script.entries if not e.name.startswith("_")}
    res.next_select_id = sp.free_select_id(tg_scenes.values())
    tr = sp.Translations(tg_scenes)
    log(f"  translation memory: {len(tr.lines)} lines, {len(tr.names)} speaker names; "
        f"new SELECT flag slots from {res.next_select_id}; {len(res.var)} variable IDs remapped")

    unknown = sorted(set(opt.scenes or ()) - set(ported) - set(removed))
    if unknown:
        raise BuildError(f"unknown scene(s): {', '.join(unknown)}")
    scenes = [s for s in ported + list(removed) if opt.scenes is None or s in opt.scenes]
    total = collections.Counter()
    for name in scenes:
        if name not in jp_by:
            raise BuildError(f"{name} is not in the JP SCRIPT.PAK")
        data, rows = sp.port_script(jp_by[name].data, res, tr,
                                    sp.load_tsv(os.path.join(lang["translation_dir"], name + ".tsv")), name)
        _, bad = ls.check(data)
        if bad:
            raise BuildError(f"{name}: bad jump targets after porting: {bad[:5]}")
        sp.write_tsv(os.path.join(tables_out, name + ".tsv"), rows)
        counts = {k: sum(1 for r in rows if r["source"] == k) for k in ("rus", "tsv", "todo")}
        total.update(counts)
        jp_exit = sp.final_jump(jp_by[name].data)
        if name in removed:
            pred = removed[name]
            if pred not in tg_by:
                raise BuildError(f"{pred} (predecessor of {name}) is not in the target SCRIPT.PAK")
            pdata, n = sp.retarget_jump(tg_by[pred].data, jp_by[pred].data, name, jp_exit)
            set_entry(tg_by[pred], pdata)
            tg_script.entries.append(type(tg_by[pred])(name, data, b"", {}))
            set_entry(tg_script.entries[-1], data)
            how = f"added; {pred} now jumps here instead of {jp_exit}"
        else:
            if name not in tg_by:
                raise BuildError(f"{name} is not in the target SCRIPT.PAK")
            tg_exit = sp.final_jump(tg_by[name].data)
            if tg_exit != jp_exit:
                log(f"  WARNING: {name}: JP exits to {jp_exit}, target exited to {tg_exit}")
            set_entry(tg_by[name], data)
            how = "replaced"
        log(f"  {name:12s} {len(rows):4d} lines: {counts['rus']:4d} existing, {counts['tsv']:4d} translated, "
            f"{counts['todo']:4d} untranslated | {how}")
    if res.missing:
        log(f"  WARNING: unmapped resources (kept or silenced): {dict(res.missing)}")

    for fix in restoration["script_fixes"]["fixes"]:
        name = fix["script"]
        if name in scenes:
            raise BuildError(f"{name} is ported; its script fix does not apply")
        if fix["kind"] == "retarget":
            data, n = sp.retarget_image(tg_by[name].data, eventcg.id_of(fix["image"]), eventcg.id_of(fix["new_image"]))
        elif fix["kind"] == "move_y":
            data, n = sp.patch_move_y(tg_by[name].data, eventcg.id_of(fix["image"]), fix["old_y"], fix["new_y"])
        else:
            raise BuildError(f"unknown script fix kind {fix['kind']!r}")
        if n == 0:
            raise BuildError(f"{name}: script fix {fix['kind']} {fix['image']} matched nothing")
        set_entry(tg_by[name], data)
        log(f"  {name:12s} script fix: {fix['kind']} {fix['image']} ({n}x)")

    if opt.start_sequence:
        _restore_start_sequence(log, restoration, jp_by, tg_by, scenes)

    if opt.test_start:
        start = restoration["new_game_script"]
        set_entry(tg_by[start], test_stub(tg_by[start].data, opt.test_start, opt.test_set))
        log(f"  TEST BUILD: {start} replaced by a stub that jumps to {opt.test_start}")
    script_out = os.path.join(files_out, "SCRIPT.PAK")
    tg_script.write(script_out)
    log(f"  SCRIPT.PAK: {len(scenes)} scenes ({total['rus']} existing lines reused, {total['tsv']} translated, "
        f"{total['todo']} untranslated) ({os.path.getsize(script_out):,} bytes)")

    log(f"[{steps}/{steps}] Output")
    _write_info(staging, opt, total, len(scenes))
    if os.path.isdir(dist):
        if not os.path.isfile(os.path.join(dist, INFO_FILE)):
            raise BuildError(f"{dist} exists but was not made by this build (no {INFO_FILE}); move it away first")
        shutil.rmtree(dist)
    os.makedirs(DIST_DIR, exist_ok=True)
    os.replace(staging, dist)
    return dist


def _restore_start_sequence(log, restoration, jp_by, tg_by, scenes):
    """New Game plays the prologue and the opening again; 0308-02-00 plays the Rengoku movie again."""
    seq = restoration["start_sequence"]
    prologue, first, mv = seq["prologue"], restoration["new_game_script"], seq["moved_movie"]
    if sp.final_jump(jp_by[prologue].data) != first:
        raise BuildError(f"JP {prologue} does not lead to {first}")
    for name in (first, mv["from"], mv["to"]):
        if name in scenes:
            raise BuildError(f"{name} is ported; the start sequence fix does not apply")
    callers = [n for n, e in tg_by.items() if not n.startswith("_") and sp.calls_to(e.data, prologue)]
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
    log(f"  {mv['to']:12s} start sequence: plays {mv['movie']} instead of calling {prologue} ({n}x)")
    log(f"  {mv['from']:12s} start sequence: {mv['movie']} removed")


def _write_info(staging, opt, total, nscenes):
    lang = opt.language
    lines = [
        f"Cartagra cut-content patch - language: {lang['code']} ({lang['name']})",
        f"Status: {lang['status'].upper()} - {lang['status_note']}",
        f"Target: {lang['target_description']}",
    ]
    if opt.test_start:
        lines.append(f"TEST BUILD: New Game jumps to {opt.test_start}. Do NOT install for normal play.")
    elif opt.scenes:
        lines.append(f"PARTIAL BUILD: only {', '.join(opt.scenes)} restored. Do NOT install for normal play.")
    if total["todo"]:
        lines.append(f"Untranslated restored lines: {total['todo']} (shown as Japanese placeholder text)")
    lines.append(f"Restored scenes: {nscenes}; voices: {'restored' if opt.voice else 'not included'}")
    lines += ["", "Copy each file to the same path inside the game folder (back up the originals first):", ""]
    for dirpath, _, names in sorted(os.walk(os.path.join(staging, "files"))):
        for n in sorted(names):
            path = os.path.join(dirpath, n)
            rel = os.path.relpath(path, staging).replace(os.sep, "/")
            lines.append(f"  {rel:24s} -> <game>/{rel}   sha256 {sha256_file(path)}")
    with open(os.path.join(staging, INFO_FILE), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
