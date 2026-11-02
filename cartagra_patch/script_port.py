#!/usr/bin/env python3
"""
Port scene scripts from the Japanese FHD build to a Steam build (the target:
the Russian release for "ru", the English Steam release for "en"). Names below
say "RUS" because the rules were measured on the Russian release, which is the
Steam build with Russian written into its English text slot.

The two engines share the bytecode format but differ in:
- opcode numbers above ~51 (OPMAP below; derived by aligning all 65 scripts
  with identical instruction counts, then checked by argument shapes);
- resource IDs: images and voices are addressed by archive position, so
  they are remapped by name (the RUS archives must already contain them);
- variable IDs 6044..6069 (shifted by one in RUS), remapped by name;
- MESSAGE/SELECT: RUS adds an "English" text slot (filled with Russian by
  the translators) after the Japanese text;
- op 57 -> 58: the u8 at body[3] became a u16 with different values;
- JP ops 129 and 130 (save-thumbnail and a JP-only marker) do not exist in RUS
  and are dropped.

Text for the target's text slot comes from, in order: the "translation" column
of the language's translation table, an existing line of the target build whose
Japanese text is identical, or the Japanese original as a placeholder (with the
speaker tag translated when known).
"""

import collections
import difflib
import os
import re
import struct

from . import lucascript as ls

OPMAP = {
    1: 1, 3: 3, 11: 11, 15: 15, 16: 16, 18: 18, 19: 19, 21: 21, 25: 25, 26: 26, 27: 27,
    36: 36, 40: 40, 41: 41, 48: 48, 51: 52, 52: 53, 54: 55, 57: 58, 61: 62, 62: 63, 63: 64,
    70: 71, 71: 72, 73: 74, 74: 75, 78: 79, 79: 80, 106: 107, 111: 113, 115: 117,
    117: 119, 118: 120, 121: 123, 122: 124, 132: 138,
}
DROP_OPS = {129, 130}
OP_SET, OP_MESSAGE, OP_SELECT, OP_IMAGE_JP, OP_MOVE_JP = 3, 36, 40, 54, 57
IMAGE_ID_OPS = {54: 2, 74: 2, 118: 0}  # JP opcode -> body offset of an image resource ID (118 = mark CG as seen)
OP57_EASE = {0: 1, 1: 2, 2: 3, 10: 33}  # JP u8 -> RUS u16, measured on aligned scripts
VAR_OPS = (1, 3)  # first u16 of the body is a variable ID
EXPR_OPS = (16, 18, 19)  # body starts with an expression string such as "#6069!=0"
INT_TAG = b"\xfe\x7f"  # op 3: RUS stores the value as tag + i16 where JP stores a decimal string


# ---------------------------------------------------------------- text fields

def _utf16(body, p):
    n = struct.unpack_from("<H", body, p)[0]
    if n == 0:
        return "", p + 2
    return body[p + 2 : p + 2 + 2 * n].decode("utf-16-le"), p + 4 + 2 * n


def _w16(s):
    if not s:
        return b"\x00\x00"
    return struct.pack("<H", len(s)) + s.encode("utf-16-le") + b"\x00\x00"


def _w8(s):
    if not s:
        return b"\x00\x00"
    raw = s.encode("utf-8")
    return struct.pack("<h", -len(raw)) + raw + b"\x00"


def parse_jp_message(body):
    line, voice = struct.unpack_from("<HH", body, 0)
    text, p = _utf16(body, 4)
    return line, voice, text, body[p:]


def parse_rus_message(body):
    line, voice = struct.unpack_from("<HH", body, 0)
    jp, p = _utf16(body, 4)
    n = -struct.unpack_from("<h", body, p)[0]
    ru8 = body[p + 2 : p + 2 + n].decode("utf-8", "replace") if n > 0 else ""
    p += 3 + n if n > 0 else 2
    ru16, p = _utf16(body, p)
    return line, voice, jp, ru16 or ru8, body[p:]


def build_rus_message(line, voice, jp, ru, tail):
    return struct.pack("<HH", line, voice) + _w16(jp) + _w8(ru) + _w16(ru) + tail


def parse_select(body, rus):
    head = body[:8]
    jp, p = _utf16(body, 8)
    ru = ""
    if rus:
        ru, p = _utf16(body, p)
        _, p = _utf16(body, p)
    return head, jp, ru, body[p:]


def build_rus_select(head, jp, ru, tail):
    return head + _w16(jp) + _w16(ru) + _w16(ru) + tail


# ---------------------------------------------------------------- translation

def tsv_escape(s):
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def tsv_unescape(s):
    return re.sub(r"\\(.)", lambda m: {"t": "\t", "n": "\n"}.get(m.group(1), m.group(1)), s)


TSV_COLUMNS = ("row", "kind", "voice", "jp", "translation")


def load_tsv(path):
    """
    {(row, jp): text} for rows with a non-empty translation column.
    Older tables (with extra source/existing columns, or "ru" instead of
    "translation") are read too; columns are found by name.
    """
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        col = {name: i for i, name in enumerate(header)}
        for line in f:
            cells = line.rstrip("\n").split("\t")
            if len(cells) < len(header):
                continue
            ru = tsv_unescape(cells[col["translation" if "translation" in col else "ru"]])
            if ru:
                out[(int(cells[col["row"]]), tsv_unescape(cells[col["jp"]]))] = ru
    return out


def write_tsv(path, rows):
    """
    Columns: see TSV_COLUMNS. "translation" is the translator's column: when it
    is not empty it is used, otherwise the build falls back to an identical line
    of the target build, then to the Japanese text.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(TSV_COLUMNS) + "\n")
        for r in rows:
            cells = [str(r["row"]), r["kind"], r["voice"], r["jp"], r["translation"]]
            f.write("\t".join(tsv_escape(c) for c in cells) + "\n")


class Translations:
    """Japanese -> target-language lines collected from the target build's own scripts."""

    def __init__(self, rus_scripts):
        """rus_scripts: {script name: data}. Lines from the same scene win over other scenes."""
        lines = collections.defaultdict(collections.Counter)
        self.names = collections.defaultdict(collections.Counter)
        self.by_script = collections.defaultdict(dict)
        for name, data in rus_scripts.items():
            for ins in ls.parse(data):
                if ins.op == OP_MESSAGE:
                    _, _, jp, ru, _ = parse_rus_message(ins.body)
                elif ins.op == OP_SELECT:
                    _, jp, ru, _ = parse_select(ins.body, rus=True)
                else:
                    continue
                if jp and ru:
                    lines[jp][ru] += 1
                    self.by_script[name].setdefault(jp, ru)
                    mj, mr = re.match(r"@([^@]+)@", jp), re.match(r"@([^@]+)@", ru)
                    if mj and mr:
                        self.names[mj.group(1)][mr.group(1)] += 1
        self.lines = {jp: c.most_common(1)[0][0] for jp, c in lines.items()}
        self.names = {jp: c.most_common(1)[0][0] for jp, c in self.names.items()}

    def lookup(self, jp, script=None):
        return self.by_script.get(script, {}).get(jp) or self.lines.get(jp)

    def placeholder(self, jp):
        m = re.match(r"@([^@]+)@", jp)
        if m and m.group(1) in self.names:
            return "@" + self.names[m.group(1)] + "@" + jp[m.end():]
        return jp


# ---------------------------------------------------------------- resources

class ResourceMap:
    """Name-based ID remapping between the JP build and the (patched) target build."""

    def __init__(self, jp_images, rus_images, jp_voices, rus_voices, jp_varnames, rus_varnames, image_aliases=None):
        # image_aliases: {(archive, JP name): RUS name} for JP pictures stored under another name in RUS
        rus_images = [(a, s, list(n)) for a, s, n in rus_images]
        for (arch, jp_name), rus_name in (image_aliases or {}).items():
            for a, s, names in rus_images:
                if a == arch:
                    names[names.index(jp_name)] = None  # never map to the RUS picture of that name
                    names[names.index(rus_name)] = jp_name
        self.image = self._build(jp_images, rus_images)
        self.voice = self._build(jp_voices, rus_voices)
        rv = {name: vid for vid, name in rus_varnames.items()}
        self.var = {vid: rv[name] for vid, name in jp_varnames.items() if name in rv and rv[name] != vid}
        self.missing = collections.Counter()
        self.next_select_id = None  # first free SELECT flag slot in the RUS build (see free_select_id)

    @staticmethod
    def _build(jp, rus):
        # jp/rus: lists of (archive name, id_start, [names])
        where = {}
        for arch, start, names in rus:
            for i, n in enumerate(names):
                where.setdefault((arch, n), start + i)
        out = {}
        for arch, start, names in jp:
            for i, n in enumerate(names):
                out[start + i] = where.get((arch, n), where.get((arch.rstrip("0123456789"), n)))
        return out

    def map_image(self, vid):
        if vid not in self.image:
            return vid  # built-in IDs such as 65000 (not in any archive)
        new = self.image[vid]
        if new is None:
            self.missing[("image", vid)] += 1
            return vid
        return new

    def map_voice(self, vid):
        if vid == 0:
            return 0
        new = self.voice.get(vid)
        if new is None:
            self.missing[("voice", vid)] += 1
            return 0
        return new

    def map_var(self, vid):
        return self.var.get(vid, vid)


def free_select_id(rus_scripts):
    """
    SELECT head = u16 0x6D61, u16 flag slot, ... ; tail = u16 0, u16 choice count.
    A select uses one flag slot per choice; return the first slot after all RUS ones.
    """
    end = 0
    for data in rus_scripts:
        for ins in ls.parse(data):
            if ins.op == OP_SELECT:
                head, _, _, tail = parse_select(ins.body, rus=True)
                end = max(end, struct.unpack_from("<H", head, 2)[0] + struct.unpack_from("<H", tail, 2)[0])
    return end


def read_varnames(data):
    out = {}
    p = 0
    while p + 3 <= len(data):
        vid = struct.unpack_from("<H", data, p)[0]
        end = data.index(b"\x00", p + 2)
        out[vid] = data[p + 2 : end].decode("cp932", "replace")
        p = end + 1
    return out


# ---------------------------------------------------------------- porting

def _map_expr(raw, res):
    return re.sub(rb"#(\d+)", lambda m: b"#%d" % res.map_var(int(m.group(1))), raw)


def port_script(jp_data, res, tr, tsv=None, script=None):
    """
    Convert one JP script to the RUS dialect.
    Returns (bytes, rows) where rows describe every text line for the TSV
    (plus "source": tsv, rus = line of the target build, todo = Japanese shown).
    """
    tsv = tsv or {}
    src = ls.parse(jp_data)
    kept, dropped = [], []
    rows = []
    row = 0
    for ins in src:
        if ins.op in DROP_OPS:
            dropped.append(ins)
            continue
        if ins.op not in OPMAP:
            raise ValueError(f"JP opcode {ins.op} at 0x{ins.offset:X} has no RUS equivalent")
        body = ins.body
        if ins.op == OP_MESSAGE:
            line, voice, jp, tail = parse_jp_message(body)
            ru, source, user = _pick(row, jp, tr, tsv, script)
            rows.append(dict(row=row, kind="msg", voice=str(voice), jp=jp, translation=user, source=source))
            row += 1
            body = build_rus_message(line, res.map_voice(voice), jp, ru, tail)
        elif ins.op == OP_SELECT:
            head, jp, _, tail = parse_select(body, rus=False)
            ru, source, user = _pick(row, jp, tr, tsv, script)
            rows.append(dict(row=row, kind="select", voice="", jp=jp, translation=user, source=source))
            row += 1
            # every ported select is new to the RUS build: give it unused flag slots
            head = head[:2] + struct.pack("<H", res.next_select_id) + head[4:]
            res.next_select_id += struct.unpack_from("<H", tail, 2)[0]
            body = build_rus_select(head, jp, ru, tail)
        elif ins.op in IMAGE_ID_OPS and len(body) >= IMAGE_ID_OPS[ins.op] + 2:
            k = IMAGE_ID_OPS[ins.op]
            vid = struct.unpack_from("<H", body, k)[0]
            body = body[:k] + struct.pack("<H", res.map_image(vid)) + body[k + 2:]
        elif ins.op == OP_SET:
            value, p = ls.read_str(body, 2)
            if not re.fullmatch(rb"-?\d+", value):
                raise ValueError(f"op 3 at 0x{ins.offset:X}: non-numeric value {value!r}")
            vid = res.map_var(struct.unpack_from("<H", body, 0)[0])
            body = struct.pack("<H", vid) + INT_TAG + struct.pack("<h", int(value)) + body[p:]
        elif ins.op == OP_MOVE_JP:
            if body[3] not in OP57_EASE:
                raise ValueError(f"op 57 at 0x{ins.offset:X}: unknown mode byte {body[3]}")
            body = body[:3] + struct.pack("<H", OP57_EASE[body[3]]) + body[4:]
        elif ins.op in VAR_OPS and len(body) >= 2:
            body = struct.pack("<H", res.map_var(struct.unpack_from("<H", body, 0)[0])) + body[2:]
        elif ins.op in EXPR_OPS:
            expr, p = ls.read_str(body, 0)
            body = ls.make_str(_map_expr(expr, res)) + body[p:]
        kept.append(ls.Instr(OPMAP[ins.op], ins.flags, ins.line, body, ins.offset))

    # A jump into a dropped instruction lands on the next kept one
    redirect = {}
    for d in dropped:
        nxt = next((k for k in kept if k.offset > d.offset), None)
        if nxt is not None:
            redirect[d.offset] = nxt
    return ls.assemble(kept, redirect), rows


def _pick(row, jp, tr, tsv, script):
    """Return (text for the RUS slot, source, translator's line or "")."""
    user = tsv.get((row, jp), "")
    if user:
        return user, "tsv", user
    known = tr.lookup(jp, script) or ""
    if known or not jp:
        return known, "rus", ""
    return tr.placeholder(jp), "todo", ""


OP_IMAGE_RUS, OP_MOVE_RUS = 55, 58


def retarget_image(rus_data, old_id, new_id):
    """In a RUS script, make every image load of old_id load new_id (in place, same size)."""
    instrs = ls.parse(rus_data)
    n = 0
    for ins in instrs:
        if ins.op == OP_IMAGE_RUS and len(ins.body) >= 4 and struct.unpack_from("<H", ins.body, 2)[0] == old_id:
            ins.body = ins.body[:2] + struct.pack("<H", new_id) + ins.body[4:]
            n += 1
    return ls.assemble(instrs), n


def patch_move_y(rus_data, image_id, old_y, new_y):
    """
    After each RUS load of image_id, change the y position of the following move
    instructions (op 58, float at body[11:15]) from old_y to new_y, up to the next
    message. Used when the JP picture has a different height (scrolling images).
    """
    instrs = ls.parse(rus_data)
    n = 0
    active = False
    for ins in instrs:
        if ins.op == OP_IMAGE_RUS and len(ins.body) >= 4:
            active = struct.unpack_from("<H", ins.body, 2)[0] == image_id
        elif ins.op == OP_MESSAGE:
            active = False
        elif active and ins.op == OP_MOVE_RUS and len(ins.body) >= 15 and struct.unpack_from("<f", ins.body, 11)[0] == old_y:
            ins.body = ins.body[:11] + struct.pack("<f", new_y) + ins.body[15:]
            n += 1
    return ls.assemble(instrs), n


def script_jumps(data):
    return [ls.read_str(i.body, 0)[0].decode("cp932") for i in ls.parse(data) if i.op == ls.OP_JUMP_SCRIPT]


def retarget_jump(rus_data, jp_data, scene, scene_exit):
    """
    Make a RUS predecessor script enter `scene` the way the JP one does.
    The script JUMPs of both versions are aligned by position; every JUMP that
    goes to `scene` in JP and to `scene_exit` in RUS is retargeted to `scene`.
    """
    jp_seq, rus_seq = script_jumps(jp_data), script_jumps(rus_data)
    if len(jp_seq) != len(rus_seq):
        raise ValueError(f"JUMP sequences differ: JP {jp_seq} / RUS {rus_seq}")
    picks = [k for k, t in enumerate(jp_seq) if t == scene]
    if not picks or any(rus_seq[k] != scene_exit for k in picks):
        raise ValueError(f"no aligned JUMP to {scene_exit}: JP {jp_seq} / RUS {rus_seq}")
    instrs = ls.parse(rus_data)
    k = 0
    for ins in instrs:
        if ins.op == ls.OP_JUMP_SCRIPT:
            if k in picks:
                _, p = ls.read_str(ins.body, 0)
                ins.body = ls.make_str(scene.encode("cp932")) + ins.body[p:]
            k += 1
    return ls.assemble(instrs), len(picks)


def final_jump(data):
    """Script name targeted by the last script JUMP in a script (None if there is none)."""
    target = None
    for ins in ls.parse(data):
        if ins.op == ls.OP_JUMP_SCRIPT:
            target = ls.read_str(ins.body, 0)[0].decode("cp932")
    return target


# ---------------------------------------------------------------- start sequence
# Steam moved the prologue and the opening movie from New Game to just before
# part 2 and moved the Rengoku movie the other way (TECHNICAL_NOTES.md, "Start
# Sequence"). Ops 20 (return) and 22 (call a script) exist only in the Steam build.

OP_RETURN, OP_CALL, OP_MARKER, OP_MOVIE_RUS, OP_PAUSE_RUS = 20, 22, 25, 119, 72
MOVIE_TAIL_OPS = (123, 1, OP_PAUSE_RUS)  # what follows a movie up to the next script JUMP


def _str_at(ins, op, p=2):
    """String argument at body[p] of an `op` instruction (None for other ops)."""
    return ls.read_str(ins.body, p)[0].decode("cp932") if ins.op == op else None


def _renumber_markers(instrs):
    """Number the marker IDs (u16 0x8000 | n at body[0] of ops 25 and 119) 0, 1, 2... in script order, as JP does."""
    n = 0
    for ins in instrs:
        if ins.op in (OP_MARKER, OP_MOVIE_RUS) and len(ins.body) >= 2 and ins.body[1] & 0x80:
            ins.body = struct.pack("<H", 0x8000 | n) + ins.body[2:]
            n += 1


def calls_to(data, script):
    """How many times a RUS script calls `script` (op 22)."""
    return sum(1 for ins in ls.parse(data) if _str_at(ins, OP_CALL) == script)


def insert_call(rus_data, script):
    """Call `script` (op 22, which returns with op 20) right after the setup instructions (up to op 27)."""
    instrs = ls.parse(rus_data)
    if any(ins.op == OP_CALL for ins in instrs):
        raise ValueError("the script already calls another script")
    end = next(k for k, ins in enumerate(instrs) if ins.op == 27) + 1
    body = struct.pack("<H", 0) + ls.make_str(script.encode("cp932")) + struct.pack("<I", 0)
    call = ls.Instr(OP_CALL, 1, instrs[end].line or 0, body)
    return ls.assemble(instrs[:end] + [call] + instrs[end:])


def cut_movie(rus_data, movie):
    """
    Remove the block that plays `movie` from a RUS script: the movie instruction and
    what follows it up to the next script JUMP (MOVIE_TAIL_OPS only).
    Returns (new data, removed instructions).
    """
    instrs = ls.parse(rus_data)
    found = [k for k, ins in enumerate(instrs) if _str_at(ins, OP_MOVIE_RUS) == movie]
    if len(found) != 1:
        raise ValueError(f"{movie} is played {len(found)} times, expected once")
    start = end = found[0]
    end += 1
    while instrs[end].op != ls.OP_JUMP_SCRIPT:
        if instrs[end].op not in MOVIE_TAIL_OPS:
            raise ValueError(f"unexpected op {instrs[end].op} after {movie}")
        end += 1
    block, kept = instrs[start:end], instrs[:start] + instrs[end:]
    _renumber_markers(kept)
    return ls.assemble(kept, {ins.offset: instrs[end] for ins in block}), block


def replace_calls(rus_data, script, block):
    """
    Replace every call of `script` (op 22) in a RUS script by a copy of `block`
    (from cut_movie) without its pauses (op 72). Returns (new data, calls replaced).
    """
    out, n = [], 0
    for ins in ls.parse(rus_data):
        if _str_at(ins, OP_CALL) != script:
            out.append(ins)
            continue
        copy = [ls.Instr(b.op, b.flags, b.line, b.body) for b in block if b.op != OP_PAUSE_RUS]
        copy[0].offset = ins.offset  # jumps to the call now land on the movie
        out += copy
        n += 1
    _renumber_markers(out)
    return ls.assemble(out), n


# ---------------------------------------------------------------- read flags
# The "_arflag" metadata entry sizes each script's bitmaps in the system data
# (read lines, chosen options, passed markers). TECHNICAL_NOTES.md, "Read Flags".

ARFLAG_RECORD = struct.Struct("<8H")  # 16, 0x011F, 0, script number (entry index + 1), lines, select bits, markers, 0
ARFLAG_HEAD = (16, 0x011F, 0)
MARKER_OPS_RUS = (OP_MARKER, OP_MOVIE_RUS)


def arflag_counts(rus_data):
    """
    (lines, select bits, markers) of a RUS script, as _arflag stores them:
    highest MESSAGE/op 43 line index + 1; end of the last select's bit range
    (head u16 at [6] = 0x4000 | first bit; 2 * options + 1 bits); highest marker ID + 1.
    """
    lines = sel_bits = markers = 0
    for ins in ls.parse(rus_data):
        if ins.op in (OP_MESSAGE, 43):
            lines = max(lines, struct.unpack_from("<H", ins.body, 0)[0] + 1)
        elif ins.op == OP_SELECT:
            head, jp, _, _ = parse_select(ins.body, True)
            first = struct.unpack_from("<H", head, 6)[0] & 0x3FFF
            sel_bits = max(sel_bits, first + 2 * (jp.count("$d") + 1) + 1)
        elif ins.op in MARKER_OPS_RUS and len(ins.body) >= 2 and ins.body[1] & 0x80:
            markers = max(markers, (struct.unpack_from("<H", ins.body, 0)[0] & 0x7FFF) + 1)
    return lines, sel_bits, markers


def rebuild_arflag(arflag, old_names, entries):
    """
    New _arflag data for `entries` (all entries of SCRIPT.PAK, in order), from the
    data of the original archive whose entry names were `old_names`. Records of
    scripts are recomputed, records of metadata entries kept, scripts without a
    record get one, and every record gets its entry's new number. Records are sorted
    by number, as in the originals (scripts first, `_varset...` last).
    Returns (data, changed script names).
    """
    index = {e.name: k + 1 for k, e in enumerate(entries)}
    by_name = {e.name: e for e in entries}
    records, changed = {}, []
    for off in range(0, len(arflag), ARFLAG_RECORD.size):
        rec = list(ARFLAG_RECORD.unpack_from(arflag, off))
        name = old_names[rec[3] - 1]
        if not name.startswith("_"):
            counts = list(arflag_counts(by_name[name].data))
            if counts != rec[4:7]:
                rec[4:7] = counts
                changed.append(name)
        rec[3] = index[name]
        records[name] = rec
    for e in entries:
        if not e.name.startswith("_") and e.name not in records:
            records[e.name] = list(ARFLAG_HEAD) + [index[e.name]] + list(arflag_counts(e.data)) + [0]
            changed.append(e.name)
    return b"".join(ARFLAG_RECORD.pack(*r) for r in sorted(records.values(), key=lambda r: r[3])), changed


# ---------------------------------------------------------------- label table
# "_scr_label" (LZW) has an empty line, then one line per script in entry order:
# "NAME:offset," (JP) or "NAME:offset(source line)," (RUS). The ending list starts
# a script at a label by setting the program counter to the offset. The Russian
# release kept the offsets of the shorter English scripts, which now point into the
# middle of instructions; the source line still places the label: before the first
# instruction with a higher line number (TECHNICAL_NOTES.md, "Label table").

LABEL = re.compile(rb"([^:,]+):(\d+)(?:\((\d+)\))?,")


def read_labels(data):
    """Lines of a _scr_label entry as [[(name, offset, source line or None), ...], ...]; index = script number."""
    return [[(m[1], int(m[2]), int(m[3]) if m[3] else None) for m in LABEL.finditer(line)]
            for line in ls.lzw_unpack(data).split(b"\r\n")]


def label_line_target(data, line):
    """Offset of the instruction a label on source line `line` stands before."""
    for ins in ls.parse(data):
        if ins.line is not None and ins.line > line:
            return ins.offset
    raise ValueError(f"no instruction after line {line}")


def offset_map(src_data, out_data, opmap=None):
    """
    {source offset: output offset} for the instructions of a script and of an edited or
    ported copy (source opcodes translated by opmap), aligned on (opcode, line). An
    instruction without a counterpart maps to the next one that has one.
    """
    src, out = ls.parse(src_data), ls.parse(out_data)
    match = difflib.SequenceMatcher(None, [((opmap or {}).get(i.op, i.op), i.line) for i in src],
                                    [(i.op, i.line) for i in out], autojunk=False)
    offsets = {}
    for a, b, size in match.get_matching_blocks():
        for k in range(size):
            offsets[src[a + k].offset] = out[b + k].offset
    nxt = None
    for ins in reversed(src):
        nxt = offsets.setdefault(ins.offset, nxt)
    return {k: v for k, v in offsets.items() if v is not None}


def after_same_message(rus_data, target, out_data):
    """
    Offset in out_data where a label of rus_data at `target` belongs: after the message that
    precedes it in rus_data, found in out_data by its translated text.
    """
    before = [i for i in ls.parse(rus_data) if i.op == OP_MESSAGE and i.offset < target]
    if not before:
        raise ValueError(f"no message before 0x{target:X}")
    text = parse_rus_message(before[-1].body)[3]
    out = ls.parse(out_data)
    hits = [k for k, i in enumerate(out[:-1]) if i.op == OP_MESSAGE and parse_rus_message(i.body)[3] == text]
    if len(hits) != 1:
        raise ValueError(f"the message {text[:40]!r} occurs {len(hits)} times")
    return out[hits[0] + 1].offset


def rebuild_scr_label(tg_label, tg_scripts, jp_label, jp_scripts, entries, ported):
    """
    New _scr_label data for `entries` (all entries of the new SCRIPT.PAK, scripts first).
    tg_label/jp_label: the _scr_label data of the target and JP archives; tg_scripts/jp_scripts:
    their scripts in entry order, as [(name, data)]; ported: names of the scripts ported from JP.
    Ported scripts get the JP labels (exact offsets, followed through the port) and the target's
    other labels after the same message; the other scripts get the target's labels, placed by
    source line and followed through the edits of the build.
    Returns (data, number of labels, number of labels whose offset changed).
    """
    tg_lines, jp_lines = read_labels(tg_label), read_labels(jp_label)
    tg = {name: (data, tg_lines[k + 1]) for k, (name, data) in enumerate(tg_scripts)}
    jp = {name: (data, jp_lines[k + 1]) for k, (name, data) in enumerate(jp_scripts)}
    lines, total, moved = [b""], 0, 0
    for e in entries:
        if e.name.startswith("_"):
            break

        def follow(offsets, n, o):
            if o not in offsets:
                raise ValueError(f"{e.name}: label {n.decode('utf-8', 'replace')} has no instruction in the new script")
            return offsets[o]

        labels = []
        if e.name in ported:
            jp_data, jp_labels = jp[e.name]
            offsets = offset_map(jp_data, e.data, OPMAP)
            labels = [(n, follow(offsets, n, o), None) for n, o, _ in jp_labels]
            tg_data, tg_labels = tg.get(e.name, (None, []))
            for n, _, line in tg_labels:
                if n not in {m for m, _, _ in jp_labels}:
                    try:
                        labels.append((n, after_same_message(tg_data, label_line_target(tg_data, line), e.data), None))
                    except ValueError as err:
                        raise ValueError(f"{e.name}: label {n.decode('utf-8', 'replace')}: {err}")
        elif e.name in tg:
            tg_data, tg_labels = tg[e.name]
            offsets = offset_map(tg_data, e.data)
            for n, o, line in tg_labels:
                labels.append((n, follow(offsets, n, o if line is None else label_line_target(tg_data, line)), line))
                moved += labels[-1][1] != o
        total += len(labels)
        lines.append(b"".join(b"%s:%d%s," % (n, o, b"" if line is None else b"(%d)" % line) for n, o, line in labels))
    if len(lines) != sum(1 for e in entries if not e.name.startswith("_")) + 1:
        raise ValueError("scripts must come before the metadata entries")
    tail = ls.lzw_unpack(tg_label).split(b"\r\n")[len(tg_scripts) + 1:]
    return ls.lzw_pack(b"\r\n".join(lines + tail)), total, moved


# ---------------------------------------------------------------- scene titles
# "_varstr" has one op-29 record per string variable a script sets when it starts: the
# script name, a u16 variable ID and the text in each language slot (Japanese, English,
# Chinese). The save and load screens show it as the scene heading ("Chapter 1", "Feb. 10")
# and every save keeps a copy of it. The Russian release left the English slot in English
# (TECHNICAL_NOTES.md, "Scene titles").

VARSTR_SLOT = 1  # the target's text slot (English; read by the Russian release)
TITLE_COLUMNS = ("original", "translation")


def _varstr_fields(ins):
    _, p = ls.read_str(ins.body, 0)
    p += 2
    head, texts = ins.body[:p], []
    while p < len(ins.body):
        text, p = _utf16(ins.body, p)
        texts.append(text)
    return head, texts


def read_varstr(data):
    """[(script name, variable ID, [text per language slot])]."""
    out = []
    for ins in ls.parse(data):
        head, texts = _varstr_fields(ins)
        name, p = ls.read_str(head, 0)
        out.append((name.decode("utf-8"), struct.unpack_from("<H", head, p)[0], texts))
    return out


def load_titles(path):
    """{original: translation} for the rows with a translation; {} when the file does not exist."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        missing = [c for c in TITLE_COLUMNS if c not in header]
        if missing:
            raise ValueError(f"{path}: missing columns {', '.join(missing)}")
        col = {name: i for i, name in enumerate(header)}
        for n, line in enumerate(f, 2):
            if not line.strip():
                continue
            cells = line.rstrip("\n").split("\t") + [""] * len(header)
            original, text = (tsv_unescape(cells[col[c]]) for c in TITLE_COLUMNS)
            if original in out:
                raise ValueError(f"{path}:{n}: {original!r} appears twice")
            if text:
                out[original] = text
    return out


def translate_varstr(data, titles):
    """
    Return (new _varstr data, number of texts replaced, [target texts without a translation]):
    the target slot's texts replaced by titles[text]. Raises ValueError for titles not in the data.
    """
    instrs = ls.parse(data)
    seen, replaced = set(), 0
    for ins in instrs:
        head, texts = _varstr_fields(ins)
        if len(texts) <= VARSTR_SLOT or not texts[VARSTR_SLOT]:
            continue
        seen.add(texts[VARSTR_SLOT])
        if texts[VARSTR_SLOT] in titles:
            texts[VARSTR_SLOT] = titles[texts[VARSTR_SLOT]]
            ins.body = head + b"".join(_w16(t) for t in texts)
            replaced += 1
    unknown = sorted(set(titles) - seen)
    if unknown:
        raise ValueError(f"not in the target's _varstr: {', '.join(map(repr, unknown))}")
    return b"".join(ins.encode() for ins in instrs), replaced, sorted(seen - set(titles))
