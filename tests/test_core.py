"""
Automated tests (standard library only):  python tests/test_core.py

The integration test builds the real ru patch twice from inputs/ (slow: a few
minutes, about 1.7 GB in a temporary folder). It runs only when
CARTAGRA_INTEGRATION=1 is set and the input files are present.
"""

import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cartagra_patch import cztool  # noqa: E402
from cartagra_patch import exe_text  # noqa: E402
from cartagra_patch import gallery  # noqa: E402
from cartagra_patch import lucascript as ls  # noqa: E402
from cartagra_patch import project  # noqa: E402
from cartagra_patch import script_port as sp  # noqa: E402
from cartagra_patch.lucapak import (
    Entry,
    LucaPak,
    SEC_HASH,
    SEC_PARENT,
    append_missing,
    replace_from,
    xxh64_pure,
)  # noqa: E402

# SHA-256 of the ru patch made by the pre-refactoring build_patch.py (installed and tested in game),
# i.e. without translation tables, start sequence and _arflag update; these only change SCRIPT.PAK
REFERENCE_RU = {
    "SCRIPT.PAK": "578b31f79f8d8a8b041bfa44e4e7b34c3b04dcf949ce8fc870ad877b2d5271ae",
    "image/EVENTCG.PAK": "a390601d1758eee655f632c55ecc6cf586a8e3ba62f3ea86981a6ec74e2774c4",
    "image/OTHCG.PAK": "46ddcb03fb3a6a904257c203fff4f28064313327f7f9dde0d50a9610a7aa74a6",
    "voice/VOICE.PAK": "d1ddf178abbee528c6e81b663d1d72b6e6e8b015ce3a6570dea475b5c5e390ae",
}


def quiet(_msg):
    pass


def make_pak(names, id_start=1001):
    pak = LucaPak()
    pak.id_start, pak.block_size, pak.flags = id_start, 2048, 0x06
    pak.section_types = [(SEC_PARENT, 2), (SEC_HASH, 8)]
    for n in names:
        pak.entries.append(
            Entry(n, n.encode() * 100, b"", {SEC_PARENT: b"\0\0", SEC_HASH: b"\0" * 8})
        )
    return pak


def lzw_encode(data):
    """Inverse of cztool's LZW: its decoder adds an entry for the first code too, so new codes start at 257."""
    table = {bytes([i]): i for i in range(256)}
    next_code, codes, w = 257, [], b""
    for c in data:
        wc = w + bytes([c])
        if wc in table:
            w = wc
            continue
        codes.append(table[w])
        table[wc] = next_code
        next_code += 1
        w = bytes([c])
    if w:
        codes.append(table[w])
    return codes


def make_exe():
    """
    A minimal PE32+ file: .text loads "Hello" with lea rcx,[rip+d] (twice) and "Other" once, .data holds a
    relocated pointer to "%d items", .reloc lists that pointer.
    """
    base = 0x140000000
    secs = [
        (b".text", 0x1000, 0x400),
        (b".rdata", 0x2000, 0x600),
        (b".data", 0x3000, 0x800),
        (b".reloc", 0x4000, 0xA00),
    ]
    data = bytearray(0xC00)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x40)
    data[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x44, 0x8664, len(secs), 0, 0, 0, 0xF0, 0x22)
    opt = 0x58
    struct.pack_into("<H", data, opt, 0x20B)
    struct.pack_into("<Q", data, opt + 24, base)
    struct.pack_into("<IIIII", data, opt + 32, 0x1000, 0x200, 0, 0, 0)
    struct.pack_into("<II", data, opt + 56, 0x5000, 0x400)
    struct.pack_into("<I", data, opt + 108, 16)
    struct.pack_into("<II", data, opt + 112 + 5 * 8, 0x4000, 12)
    for k, (name, va, raw) in enumerate(secs):
        struct.pack_into(
            "<8sIIIIIIHHI",
            data,
            opt + 0xF0 + 40 * k,
            name,
            0x200,
            va,
            0x200,
            raw,
            0,
            0,
            0,
            0,
            0x40000040,
        )

    def lea(at_rva, target_rva):
        off = at_rva - 0x1000 + 0x400
        data[off : off + 7] = b"\x48\x8d\x0d" + struct.pack(
            "<i", target_rva - (at_rva + 7)
        )

    lea(0x1000, 0x2000)
    lea(0x1010, 0x2000)
    lea(0x1020, 0x2020)
    data[0x600:0x606] = b"Hello\0"
    data[0x610:0x619] = b"%d items\0"
    data[0x620:0x626] = b"Other\0"
    struct.pack_into("<Q", data, 0x800, base + 0x2010)
    struct.pack_into("<IIHH", data, 0xA00, 0x3000, 12, 10 << 12, 0)
    return bytes(data)


FONT_PALETTE = b"".join(bytes((255, 255, 255, i)) for i in range(256))


def make_cz2(idx, w, h):
    return cztool.encode_cz2(
        b"CZ2\0" + struct.pack("<IHHHHH", 18, w, h, 8, 4, 0), FONT_PALETTE, w, h, idx
    )


def make_font_set(folder, group, size, glyphs):
    """FONTn__INFO.PAK (info<size>) and FONTn_<face>.PAK ("F<size>") with `glyphs` ({char: (left, width)}):
    glyph k + 1 is a filled box of that width in its cell."""
    from cartagra_patch import fonts

    cell = size + 1
    info = struct.pack("<4H", size, size + 1, 100, len(glyphs) + 1) + bytes(
        (0, size, 0)
    )
    table, widths = [0] * 65536, [0] * 65536
    for k, (c, (left, width)) in enumerate(glyphs.items()):
        info += bytes((left, width, size // 9))
        table[ord(c)], widths[ord(c)] = k + 1, width << 8 | left
    info += struct.pack("<65536H", *table) + struct.pack("<65536H", *widths)
    w, h = 100 * cell + 8, cell + 1
    idx = bytearray(w * h)
    for k, (_, (_, width)) in enumerate(glyphs.items()):
        for y in range(2, size - 2):
            idx[y * w + (k + 1) * cell + 1 : y * w + (k + 1) * cell + width - 1] = (
                b"\xff" * (width - 2)
            )
    os.makedirs(folder, exist_ok=True)
    pak = make_pak([])
    pak.entries.append(
        Entry(f"info{size}", info, b"", {SEC_PARENT: b"\0\0", SEC_HASH: b"\0" * 8})
    )
    pak.write(os.path.join(folder, f"{group}__INFO.PAK"))
    for face in fonts.FACES:
        pak = make_pak([])
        pak.entries.append(
            Entry(
                f"F{size}",
                make_cz2(bytes(idx), w, h),
                b"",
                {SEC_PARENT: b"\0\0", SEC_HASH: b"\0" * 8},
            )
        )
        pak.write(os.path.join(folder, f"{group}_{face}.PAK"))


def make_cz4(rgba, w, h, blocks=2):
    """CZ4 file for an RGBA image: delta-coded RGB plane + alpha plane, LZW in `blocks` blocks."""
    band = -(-h // 3)

    def delta(plane, bpp):
        stride = w * bpp
        out = bytearray(plane)
        for y in range(h):
            if y % band:
                for x in range(stride):
                    out[y * stride + x] = (
                        plane[y * stride + x] - plane[(y - 1) * stride + x]
                    ) & 0xFF
        return bytes(out)

    rgb = bytes(b for i in range(0, len(rgba), 4) for b in rgba[i : i + 3])
    raw = delta(rgb, 3) + delta(rgba[3::4], 1)
    cut = len(raw) // blocks
    parts = [
        raw[k * cut : (k + 1) * cut if k < blocks - 1 else len(raw)]
        for k in range(blocks)
    ]
    encoded = [lzw_encode(part) for part in parts]
    head = b"CZ4\0" + struct.pack("<IHHHHHHHHHH", 0x1C, w, h, 32, 4, 0, 0, w, h, w, h)
    sizes = b"".join(struct.pack("<II", len(c), len(p)) for c, p in zip(encoded, parts))
    return (
        head
        + struct.pack("<I", blocks)
        + sizes
        + b"".join(struct.pack("<%dH" % len(c), *c) for c in encoded)
    )


class LucaPakTests(unittest.TestCase):
    def test_xxh64_known_vectors(self):
        for data, want in (
            (b"", "ef46db3751d8e999"),
            (b"abc", "44bc2cf5ad770999"),
            (b"Nobody inspects the spammish repetition", "fbcea83c8a378bf1"),
        ):
            self.assertEqual(
                int.from_bytes(xxh64_pure(data), "little").to_bytes(8, "big").hex(),
                want,
            )

    def test_roundtrip_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.PAK")
            make_pak(["a", "b", "c"]).write(path)
            with open(path, "rb") as f:
                raw = f.read()
            back = LucaPak.read(path)
            self.assertEqual(back.build(), raw)
            self.assertEqual([e.name for e in back.entries], ["a", "b", "c"])
            self.assertEqual(back.id_of("b"), 1002)

    def test_name_prefix_is_kept(self):
        """PARTS.PAK has "PARTS/\\0" before the first name; the engine looks pictures up as PARTS/<name>."""
        pak = make_pak(["a", "b"])
        pak.name_prefix = b"PARTS/\0"
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "PARTS.PAK")
            pak.write(path)
            with open(path, "rb") as f:
                raw = f.read()
            back = LucaPak.read(path)
            self.assertEqual(back.name_prefix, b"PARTS/\0")
            self.assertEqual([e.name for e in back.entries], ["a", "b"])
            self.assertEqual(back.build(), raw)
            self.assertIn(b"PARTS/\0a\0b\0", raw)

    def test_append_keeps_ids_and_remaps_parent(self):
        base, donor = make_pak(["x", "a"]), make_pak(["a", "b", "b_k1"])
        donor.entries[2].sections[SEC_PARENT] = donor.id_of("b").to_bytes(2, "little")
        added = append_missing(base, donor)
        self.assertEqual([e.name for e in added], ["b", "b_k1"])
        self.assertEqual(base.id_of("x"), 1001)  # original entries keep their IDs
        self.assertEqual(
            int.from_bytes(base.entries[3].sections[SEC_PARENT], "little"),
            base.id_of("b"),
        )

    def test_replace_in_place(self):
        base, donor = make_pak(["x", "a"]), make_pak(["a"])
        donor.entries[0].data = b"new"
        replace_from(base, donor, ["a"])
        self.assertEqual(base.id_of("a"), 1002)
        self.assertEqual(base.entries[1].data, b"new")


class LucaScriptTests(unittest.TestCase):
    def test_jump_relocation(self):
        target = ls.Instr(26, 0, None, b"", 0)
        goto = ls.Instr(ls.OP_GOTO, 0, None, (0).to_bytes(4, "little"), 4)
        data = ls.assemble([target, goto])
        instrs = ls.parse(data)
        extra = ls.Instr(41, 1, 7, b"\x01\x02\x03")  # odd length -> padded
        out = ls.assemble([extra] + instrs)
        parsed, bad = ls.check(out)
        self.assertEqual(bad, [])
        self.assertEqual(int.from_bytes(parsed[2].body[:4], "little"), parsed[1].offset)

    def test_lzw_entry_roundtrip(self):
        for raw in (
            b"",
            b"a",
            b"\r\nLABEL01:10(3),LABEL02:20(5),\r\n\r\n" * 50,
            bytes(range(256)) * 3,
        ):
            packed = ls.lzw_pack(raw)
            self.assertEqual(packed[:4], b"LZW\0")
            self.assertEqual(ls.lzw_unpack(packed), raw)
        self.assertLess(len(ls.lzw_pack(b"abc" * 1000)), 3000)
        with self.assertRaises(ValueError):
            ls.lzw_unpack(b"CZ0\0" + bytes(8))


def build_script(instrs, jumps=None):
    """Assemble instrs; jumps: {index of a GOTO/IF: index of its target}."""
    pos = 0
    for ins in instrs:
        ins.offset = pos
        pos += len(ins.encode())
    for k, t in (jumps or {}).items():
        body = bytearray(instrs[k].body)
        struct.pack_into("<I", body, ls.jump_fields(instrs[k])[0], instrs[t].offset)
        instrs[k].body = bytes(body)
    return ls.assemble(instrs)


def op(code, body=b"", line=None):
    return ls.Instr(code, 1 if line is not None else 0, line, body)


def named(code, name, head=b"\0\0", tail=b""):
    return op(code, head + ls.make_str(name.encode()) + tail)


class StartSequenceTests(unittest.TestCase):
    def ops(self, data):
        return [i.op for i in ls.parse(data)]

    def test_insert_call_after_setup(self):
        data = build_script(
            [
                op(26),
                op(27),
                op(72, b"\x96\0", 5),
                op(ls.OP_GOTO, b"\0" * 4),
                op(21, ls.make_str(b"x")),
            ],
            {3: 2},
        )
        out = ls.parse(sp.insert_call(data, "0000-op0_HD"))
        self.assertEqual([i.op for i in out], [26, 27, sp.OP_CALL, 72, ls.OP_GOTO, 21])
        self.assertEqual(
            sp.calls_to(sp.insert_call(data, "0000-op0_HD"), "0000-op0_HD"), 1
        )
        self.assertEqual(int.from_bytes(out[4].body, "little"), out[3].offset)
        with self.assertRaises(ValueError):
            sp.insert_call(sp.insert_call(data, "a"), "b")

    def test_cut_movie_redirects_jumps_and_renumbers(self):
        instrs = [
            op(ls.OP_GOTO, b"\0" * 4),
            named(sp.OP_MOVIE_RUS, "m1", b"\x00\x80"),
            op(123, b"1234"),
            op(1, b"\x16\x2f\x01\0"),
            op(72, b"\x78\0"),
            op(21, ls.make_str(b"next")),
            op(25, b"\x01\x80"),
        ]
        data, block = sp.cut_movie(build_script(instrs, {0: 1}), "m1")
        out = ls.parse(data)
        self.assertEqual([i.op for i in out], [ls.OP_GOTO, 21, 25])
        self.assertEqual(int.from_bytes(out[0].body, "little"), out[1].offset)
        self.assertEqual(out[2].body, b"\x00\x80")
        self.assertEqual([i.op for i in block], [sp.OP_MOVIE_RUS, 123, 1, 72])
        with self.assertRaises(ValueError):
            sp.cut_movie(data, "m1")

    def test_replace_calls_with_movie(self):
        block = [
            named(sp.OP_MOVIE_RUS, "m1", b"\x00\x80"),
            op(123, b"1234"),
            op(1, b"\x16\x2f\x01\0"),
            op(72, b"\x78\0"),
        ]
        call = lambda: named(sp.OP_CALL, "pro", b"\0\0", b"\0" * 4)  # noqa: E731
        instrs = [
            op(18, ls.make_str(b"#1") + b"\0" * 4),
            op(ls.OP_GOTO, b"\0" * 4),
            call(),
            op(21, ls.make_str(b"a")),
            op(25, b"\x00\x80"),
            call(),
            op(21, ls.make_str(b"b")),
            op(25, b"\x01\x80"),
        ]
        data, n = sp.replace_calls(build_script(instrs, {0: 5, 1: 2}), "pro", block)
        out = ls.parse(data)
        self.assertEqual(n, 2)
        self.assertEqual(
            self.ops(data), [18, ls.OP_GOTO, 119, 123, 1, 21, 25, 119, 123, 1, 21, 25]
        )
        self.assertEqual(int.from_bytes(out[0].body[-4:], "little"), out[7].offset)
        self.assertEqual(int.from_bytes(out[1].body, "little"), out[2].offset)
        markers = [i.body[:2] for i in out if i.op in (25, 119)]
        self.assertEqual(markers, [struct.pack("<H", 0x8000 | k) for k in range(4)])
        self.assertEqual(sp.calls_to(data, "pro"), 0)


def message(line):
    return op(
        sp.OP_MESSAGE, sp.build_rus_message(line, 0, "あ", "а", b"\x0b\x0a\0\0\0"), line
    )


def select(first_bit, options):
    head = struct.pack("<4H", 0x6D61, 197, 0, 0x4000 | first_bit)
    text = "$d".join("x" * options)
    return op(
        sp.OP_SELECT,
        sp.build_rus_select(head, text, text, struct.pack("<HH", 0, options)),
    )


class ReadFlagTests(unittest.TestCase):
    def test_arflag_counts(self):
        data = build_script(
            [
                message(0),
                message(7),
                select(0, 3),
                select(7, 2),
                op(25, b"\x00\x80"),
                named(sp.OP_MOVIE_RUS, "m", b"\x02\x80"),
                op(43, struct.pack("<H", 9) + b"\0" * 5),
            ]
        )
        # lines: highest index 9 (op 43) + 1; selects: 7 + 2 * 2 + 1; markers: highest ID 2 + 1
        self.assertEqual(sp.arflag_counts(data), (10, 12, 3))
        self.assertEqual(sp.arflag_counts(build_script([op(26)])), (0, 0, 0))

    def test_rebuild_arflag(self):
        s1, meta = Entry("s1", build_script([message(0), message(1)])), Entry(
            "_meta", b"x"
        )
        old = sp.ARFLAG_RECORD.pack(
            16, 0x11F, 0, 1, 2, 0, 0, 0
        ) + sp.ARFLAG_RECORD.pack(  # s1: up to date
            16, 0x11F, 0, 2, 0, 0, 4, 0
        )  # _meta: kept as is
        self.assertEqual(sp.rebuild_arflag(old, ["s1", "_meta"], [s1, meta]), (old, []))
        # s1 changed; new script s2 inserted before the metadata entry, whose record moves to number 3
        s1.data = build_script([message(0), message(30)])
        data, changed = sp.rebuild_arflag(
            old, ["s1", "_meta"], [s1, Entry("s2", build_script([message(4)])), meta]
        )
        self.assertEqual(changed, ["s1", "s2"])
        self.assertEqual(
            [sp.ARFLAG_RECORD.unpack_from(data, k) for k in range(0, len(data), 16)],
            [
                (16, 0x11F, 0, 1, 31, 0, 0, 0),
                (16, 0x11F, 0, 2, 5, 0, 0, 0),
                (16, 0x11F, 0, 3, 0, 0, 4, 0),
            ],
        )


def said(line, text):
    return op(
        sp.OP_MESSAGE,
        sp.build_rus_message(line, 0, "あ", text, b"\x0b\x0a\0\0\0"),
        line,
    )


class LabelTableTests(unittest.TestCase):
    def test_line_target_and_offset_map(self):
        src = build_script(
            [op(26), said(5, "a"), op(41, b"\0\0", 9), op(21, ls.make_str(b"x"), 12)]
        )
        self.assertEqual(sp.label_line_target(src, 7), ls.parse(src)[2].offset)
        with self.assertRaises(ValueError):
            sp.label_line_target(src, 12)
        a = ls.parse(src)
        out = ls.parse(
            build_script(
                [
                    op(26),
                    op(22, b"\0\0", 1),
                    said(5, "a"),
                    op(21, ls.make_str(b"x"), 12),
                ]
            )
        )
        # op 41 was removed: it maps to the next instruction that is still there
        self.assertEqual(
            sp.offset_map(src, b"".join(i.encode() for i in out)),
            {
                a[0].offset: out[0].offset,
                a[1].offset: out[2].offset,
                a[2].offset: out[3].offset,
                a[3].offset: out[3].offset,
            },
        )

    def test_rebuild_scr_label(self):
        # s1: target script with a stale offset; the build inserts an instruction in front
        s1 = build_script(
            [
                op(26),
                said(5, "a"),
                said(9, "b"),
                op(41, b"\0\0", 12),
                op(21, ls.make_str(b"x"), 13),
            ]
        )
        s1_out = build_script(
            [
                op(26),
                op(22, b"\0\0", 1),
                said(5, "a"),
                said(9, "b"),
                op(41, b"\0\0", 12),
                op(21, ls.make_str(b"x"), 13),
            ]
        )
        # p1: ported from JP (op 54 -> 55, op 129 dropped); the target's own version has a label JP lacks
        p1_jp = build_script(
            [
                op(26),
                op(54, b"\0\0", 3),
                op(129, b"", 4),
                said(6, "до"),
                op(41, b"\0\0", 7),
            ]
        )
        p1_tg = build_script(
            [
                op(26),
                said(2, "до"),
                op(19, ls.make_str(b"#1") + bytes(4), 4),
                op(41, b"\0\0", 5),
            ],
            {2: 3},
        )
        p1_out = build_script(
            [op(26), op(55, b"\0\0", 3), said(6, "до"), op(41, b"\0\0", 7)]
        )
        jp_off, out_off, s1_off = (
            [i.offset for i in ls.parse(d)] for d in (p1_jp, p1_out, s1_out)
        )
        tg_label = ls.lzw_pack(b"\r\nA:3(10),\r\nENDING:1(3),\r\n\r\n")
        jp_label = ls.lzw_pack(b"\r\n\r\nX:%d,Y:%d,\r\n" % (jp_off[2], jp_off[1]))
        entries = [
            Entry("s1", s1_out),
            Entry("p1", p1_out),
            Entry("n1", build_script([op(26)])),
            Entry("_meta", b""),
        ]
        data, total, moved = sp.rebuild_scr_label(
            tg_label,
            [("s1", s1), ("p1", p1_tg)],
            jp_label,
            [("j0", b""), ("p1", p1_jp), ("n1", b"")],
            entries,
            {"p1", "n1"},
        )
        self.assertEqual((total, moved), (4, 1))
        self.assertEqual(
            ls.lzw_unpack(data).split(b"\r\n"),
            [
                b"",
                b"A:%d(10)," % s1_off[4],  # before the first line above 10
                b"X:%d,Y:%d,ENDING:%d,"
                % (out_off[2], out_off[1], out_off[3]),  # X was on the dropped op 129
                b"",  # n1 (new) has no labels
                b"",
                b"",
            ],
        )  # the target's last lines
        p1_bad = build_script([op(26), op(55, b"\0\0", 3), op(41, b"\0\0", 7)])
        with self.assertRaisesRegex(
            ValueError, "p1: label ENDING"
        ):  # its message is not in the ported script
            sp.rebuild_scr_label(
                tg_label,
                [("s1", s1), ("p1", p1_tg)],
                jp_label,
                [("j0", b""), ("p1", p1_jp)],
                [Entry("s1", s1_out), Entry("p1", p1_bad)],
                {"p1"},
            )
        with self.assertRaisesRegex(ValueError, "p1: label X has no instruction"):
            sp.rebuild_scr_label(
                tg_label,
                [("s1", s1), ("p1", p1_tg)],
                jp_label,
                [("j0", b""), ("p1", p1_jp)],
                [
                    Entry("s1", s1_out),
                    Entry("p1", build_script([op(26), op(55, b"\0\0", 3)])),
                ],
                {"p1"},
            )


def varstr_record(name, var, texts):
    return ls.Instr(
        29,
        1,
        0,
        ls.make_str(name)
        + struct.pack("<H", var)
        + b"".join(sp._w16(t) for t in texts),
    ).encode()


class SceneTitleTests(unittest.TestCase):
    def test_read_and_translate_varstr(self):
        data = (
            varstr_record(b"0206-01-00", 201, ["第一幕", "Chapter 1", "第一幕"])
            + varstr_record(
                b"0000-op1", 202, ["二月六日", "Feb. 6", "二月六日"]
            )  # odd length: padded
            + varstr_record(b"0210-12-00", 201, ["", "", ""])
        )
        self.assertEqual(
            sp.read_varstr(data),
            [
                ("0206-01-00", 201, ["第一幕", "Chapter 1", "第一幕"]),
                ("0000-op1", 202, ["二月六日", "Feb. 6", "二月六日"]),
                ("0210-12-00", 201, ["", "", ""]),
            ],
        )
        self.assertEqual(
            sp.translate_varstr(data, {}), (data, 0, ["Chapter 1", "Feb. 6"])
        )
        out, n, untranslated = sp.translate_varstr(data, {"Feb. 6": "6 февраля"})
        self.assertEqual((n, untranslated), (1, ["Chapter 1"]))
        self.assertEqual(
            [t for _, _, t in sp.read_varstr(out)][1],
            ["二月六日", "6 февраля", "二月六日"],
        )
        with self.assertRaisesRegex(ValueError, "'Feb. 7'"):
            sp.translate_varstr(data, {"Feb. 7": "7 февраля"})

    def test_load_titles(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.tsv")
            self.assertEqual(sp.load_titles(path), {})
            with open(path, "w", encoding="utf-8") as f:
                f.write("original\ttranslation\nFeb. 6\t6 февраля\nChapter 1\t\n")
            self.assertEqual(sp.load_titles(path), {"Feb. 6": "6 февраля"})
            with open(path, "a", encoding="utf-8") as f:
                f.write("Feb. 6\tx\n")
            with self.assertRaisesRegex(ValueError, "twice"):
                sp.load_titles(path)

    def test_language_titles_fit_the_target(self):
        """languages/ru/scene_titles.tsv translates every heading of the Russian release, when it is present."""
        path = os.path.join(project.INPUTS_DIR, "ru-steam", "files", "SCRIPT.PAK")
        if not os.path.isfile(path):
            self.skipTest("inputs/ru-steam/files/SCRIPT.PAK is not present")
        data = next(e.data for e in LucaPak.read(path).entries if e.name == "_varstr")
        self.assertEqual(sp.translate_varstr(data, {})[0], data)  # round trip
        _, n, untranslated = sp.translate_varstr(
            data, sp.load_titles(project.load_language("ru")["scene_titles"])
        )
        self.assertEqual((n, untranslated), (58, []))


class CzToolTests(unittest.TestCase):
    def test_cz4_decode(self):
        rnd = random.Random(1)
        w, h = 7, 8
        # few distinct values, so the codes reuse dictionary entries (including the code being defined)
        rgba = bytes(rnd.choice((0, 0, 0, 7, 255)) for _ in range(4 * w * h))
        hd, out = cztool.decode(make_cz4(rgba, w, h))
        self.assertEqual((hd["width"], hd["height"]), (w, h))
        self.assertEqual(out, rgba)

    def test_composite_alpha(self):
        base = bytes([10, 20, 30, 255]) * 4
        over = bytes([200, 200, 200, 255, 0, 0, 0, 0])
        out = cztool.composite(base, 2, over, 2, 1, 0, 1)
        self.assertEqual(out[:8], base[:8])
        self.assertEqual(out[8:12], bytes([200, 200, 200, 255]))
        self.assertEqual(out[12:16], bytes([10, 20, 30, 255]))

    def test_cz2_roundtrip(self):
        rnd = random.Random(2)
        w, h = 300, 200
        # runs and noise: enough distinct strings for 18-bit codes (dictionary beyond 0x8000)
        idx = bytes(
            rnd.choice((0, 0, 0, 255, rnd.randrange(256))) for _ in range(w * h)
        )
        data = make_cz2(idx, w, h)
        hd, palette, out = cztool.decode_cz2(data)
        self.assertEqual(
            (hd["width"], hd["height"], palette, out), (w, h, FONT_PALETTE, idx)
        )
        self.assertEqual(cztool.decode_cz2(data, rows=3)[2], idx[: 3 * w])
        self.assertEqual(
            cztool.decode(data)[1][4 * 5 : 4 * 6],
            FONT_PALETTE[4 * idx[5] : 4 * idx[5] + 4],
        )
        self.assertEqual(cztool.encode_cz2(data, palette, w, h, out), data)

    def test_cz2_blocks(self):
        # a block ends when its dictionary is full; the next block starts with a new dictionary
        saved = cztool.CZ2_MAX_CODES
        try:
            cztool.CZ2_MAX_CODES = 500
            rnd = random.Random(3)
            idx = bytes(rnd.randrange(4) for _ in range(20000))
            data = make_cz2(idx, 200, 100)
        finally:
            cztool.CZ2_MAX_CODES = saved
        self.assertGreater(struct.unpack_from("<I", data, 18 + 1024)[0], 1)
        self.assertEqual(cztool.decode_cz2(data)[2], idx)


class FontTests(unittest.TestCase):
    def test_add_glyphs(self):
        from cartagra_patch import fonts
        from cartagra_patch.lucapak import LucaPak as Pak

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in", fonts.FONT_DIR)
            make_font_set(src, "FONT0", 44, {"A": (0, 36), "Б": (7, 29), "ж": (4, 40)})
            make_font_set(src, "FONT1", 22, {"A": (0, 18)})
            out = os.path.join(tmp, "out")
            self.assertEqual(
                fonts.add_glyphs(os.path.join(tmp, "in"), out, "Бж", log=quiet), 2
            )
            info = fonts.FontInfo(
                Pak.read(os.path.join(out, fonts.FONT_DIR, "FONT1__INFO.PAK"))
                .entries[0]
                .data
            )
            self.assertEqual(
                (info.glyph[ord("A")], info.glyph[ord("Б")], info.glyph[ord("ж")]),
                (1, 2, 3),
            )
            self.assertEqual(
                info.cells[2], (4, 14, 2)
            )  # left and width halved, letter spacing as in FONT1's "A"
            self.assertEqual(info.width[ord("Б")], 14 << 8 | 4)
            for face in fonts.FACES:
                sheet = Pak.read(
                    os.path.join(out, fonts.FONT_DIR, f"FONT1_{face}.PAK")
                ).entries[0]
                hd, _, idx = cztool.decode_cz2(sheet.data)
                self.assertEqual((hd["width"], hd["height"]), (100 * 23 + 8, 24))
                row = idx[11 * hd["width"] : 12 * hd["width"]]
                self.assertTrue(
                    row[2 * 23 + 3] > 200 and row[2 * 23 + 18] < 50
                )  # Б: box about 14 px wide
                self.assertTrue(
                    row[3 * 23 + 3] > 200 and row[3 * 23 + 17] > 200
                )  # ж: about 20 px
            self.assertEqual(
                fonts.add_glyphs(
                    os.path.join(tmp, "in"), os.path.join(tmp, "out2"), "A", log=quiet
                ),
                0,
            )
            with self.assertRaises(ValueError):
                fonts.add_glyphs(os.path.join(tmp, "in"), out, "Ы", log=quiet)

    def test_redraw_numero(self):
        from cartagra_patch import fonts
        from cartagra_patch.lucapak import LucaPak as Pak

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in", fonts.FONT_DIR)
            make_font_set(
                src, "FONT0", 44, {"N": (0, 30), "o": (0, 20), "№": (0, 44)}
            )  # boxes in rows 2..41
            out = os.path.join(tmp, "out")
            fonts.redraw_numero(os.path.join(tmp, "in"), out, log=quiet)
            info = fonts.FontInfo(
                Pak.read(os.path.join(out, fonts.FONT_DIR, "FONT0__INFO.PAK"))
                .entries[0]
                .data
            )
            adv = info.width[ord("№")] >> 8
            self.assertEqual(info.glyph[ord("№")], 3)
            self.assertEqual(info.cells[3], (0, adv, 44 // 9))
            self.assertTrue(30 < adv <= 45)
            orig = cztool.decode_cz2(
                Pak.read(os.path.join(src, "FONT0_MINCHO.PAK")).entries[0].data
            )[2]
            for face in fonts.FACES:
                hd, _, idx = cztool.decode_cz2(
                    Pak.read(os.path.join(out, fonts.FONT_DIR, f"FONT0_{face}.PAK"))
                    .entries[0]
                    .data
                )
                w, x0 = hd["width"], 3 * 45
                at = lambda x, y: idx[y * w + x0 + x]
                self.assertEqual(
                    [idx[y * w : y * w + x0] for y in range(46)],
                    [orig[y * w : y * w + x0] for y in range(46)],
                )
                self.assertTrue(at(5, 20) > 200)  # N, narrowed
                self.assertTrue(at(adv - 6, 5) > 200)  # raised o: half the cap height
                self.assertTrue(at(adv - 6, 24) < 50 and at(adv - 6, 33) < 50)
                self.assertTrue(at(adv - 6, 27) > 200)  # the bar under it
            make_font_set(src, "FONT0", 44, {"N": (0, 30), "o": (0, 20)})
            with self.assertRaisesRegex(ValueError, "no glyph"):
                fonts.redraw_numero(os.path.join(tmp, "in"), out, log=quiet)


class CzReplacementTests(unittest.TestCase):
    def test_cz0_roundtrip_keeps_placement(self):
        w, h = 4, 3
        original = make_cz4(bytes(4 * w * h), w, h)
        original = original[:0x10] + struct.pack("<HH", 5, 7) + original[0x14:]
        rgba = bytes(range(4 * w * h))
        cz0 = cztool.encode_cz0(original, rgba)
        hd, out = cztool.decode(cz0)
        self.assertEqual(
            (hd["magic"], hd["header_length"], hd["width"], hd["height"], hd["bits"]),
            (b"CZ0\x00", 64, w, h, 32),
        )
        self.assertEqual((hd["x"], hd["y"]), (5, 7))
        self.assertEqual(out, rgba)
        with self.assertRaises(ValueError):
            cztool.encode_cz0(original, rgba[:-4])

    def test_read_png_filters_and_color_types(self):
        def png(w, h, ctype, rows, filters, extra=b""):
            def chunk(t, d):
                return (
                    struct.pack(">I", len(d))
                    + t
                    + d
                    + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
                )

            ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
            raw, prev = b"", bytes(w * ch)
            for row, ft in zip(rows, filters):
                enc = bytearray(row)
                for i in range(len(row)):
                    a = row[i - ch] if i >= ch else 0
                    b, c = prev[i], prev[i - ch] if i >= ch else 0
                    pred = {
                        0: 0,
                        1: a,
                        2: b,
                        3: (a + b) // 2,
                        4: (
                            a
                            if abs(b - c) <= abs(a - c)
                            and abs(b - c) <= abs(a + b - 2 * c)
                            else b if abs(a - c) <= abs(a + b - 2 * c) else c
                        ),
                    }[ft]
                    enc[i] = (row[i] - pred) & 0xFF
                raw += bytes([ft]) + bytes(enc)
                prev = row
            return (
                b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
                + extra
                + chunk(b"IDAT", zlib.compress(raw))
                + chunk(b"IEND", b"")
            )

        rnd = random.Random(2)
        w, h = 3, 5
        rgba = [bytes(rnd.randrange(256) for _ in range(4 * w)) for _ in range(h)]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.png")
            with open(path, "wb") as f:
                f.write(png(w, h, 6, rgba, [0, 1, 2, 3, 4]))
            self.assertEqual(cztool.read_png(path), (w, h, b"".join(rgba)))
            rgb = [bytes(v for i, v in enumerate(r) if i % 4 != 3) for r in rgba]
            with open(path, "wb") as f:
                f.write(png(w, h, 2, rgb, [4, 3, 2, 1, 0]))
            self.assertEqual(
                cztool.read_png(path)[2],
                b"".join(
                    bytes(r[i : i + 3]) + b"\xff"
                    for r in rgb
                    for i in range(0, 3 * w, 3)
                ),
            )
            plte = struct.pack(">I", 6) + b"PLTE" + b"\x01\x02\x03\x04\x05\x06"
            plte += struct.pack(
                ">I", zlib.crc32(b"PLTE\x01\x02\x03\x04\x05\x06") & 0xFFFFFFFF
            )
            trns = (
                struct.pack(">I", 1)
                + b"tRNS\x80"
                + struct.pack(">I", zlib.crc32(b"tRNS\x80") & 0xFFFFFFFF)
            )
            with open(path, "wb") as f:
                f.write(png(2, 1, 3, [bytes([0, 1])], [0], plte + trns))
            self.assertEqual(
                cztool.read_png(path), (2, 1, b"\x01\x02\x03\x80\x04\x05\x06\xff")
            )
            cztool.write_png(path, b"".join(rgba), w, h)
            self.assertEqual(cztool.read_png(path), (w, h, b"".join(rgba)))
            with open(path, "wb") as f:
                f.write(b"GIF89a")
            with self.assertRaises(ValueError):
                cztool.read_png(path)

    def test_build_replaces_images(self):
        from cartagra_patch import pipeline

        w, h = 2, 2
        pak = make_pak([])
        pak.entries = [
            Entry(
                "menu",
                make_cz4(bytes(4 * w * h), w, h),
                b"",
                {SEC_PARENT: b"\0\0", SEC_HASH: b"\0" * 8},
            ),
            Entry(
                "other", b"CZ4\0rest", b"", {SEC_PARENT: b"\0\0", SEC_HASH: b"\0" * 8}
            ),
        ]
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "target", "files")
            os.makedirs(os.path.join(target, "image", "resident"))
            pak.write(os.path.join(target, "image", "resident", "PARTS.PAK"))
            images = os.path.join(d, "lang", "images", "resident", "PARTS")
            os.makedirs(images)
            rgba = bytes(range(16))
            cztool.write_png(os.path.join(images, "menu.png"), rgba, w, h)
            lang = {
                "code": "xx",
                "interface_table": os.path.join(d, "lang", "interface.tsv"),
                "images_dir": os.path.join(d, "lang", "images"),
            }
            self.assertEqual(
                project.needed_optional_inputs(lang), ["image/resident/PARTS.PAK"]
            )
            opt = pipeline.BuildOptions(lang, "jp", target)
            staging = os.path.join(d, "staging")
            result = pipeline._build_interface(
                quiet, opt, d, staging, os.path.join(staging, "files")
            )
            self.assertEqual(result, (0, 1))
            out = LucaPak.read(
                os.path.join(staging, "files", "image", "resident", "PARTS.PAK")
            )
            self.assertEqual(cztool.decode(out.entries[0].data)[1], rgba)
            self.assertEqual(
                out.entries[0].sections[SEC_HASH], xxh64_pure(out.entries[0].data)
            )
            self.assertEqual(out.entries[1].data, b"CZ4\0rest")
            self.assertFalse(os.path.exists(os.path.join(staging, "CARTAGRA.exe")))
            cztool.write_png(os.path.join(images, "menu.png"), rgba + rgba, w, 2 * h)
            with self.assertRaisesRegex(
                project.BuildError, "2x4 pixels, the original is 2x2"
            ):
                pipeline._build_interface(
                    quiet, opt, d, staging, os.path.join(staging, "files")
                )
            os.rename(
                os.path.join(images, "menu.png"), os.path.join(images, "missing.png")
            )
            with self.assertRaisesRegex(project.BuildError, "no image named 'missing'"):
                pipeline._build_interface(
                    quiet, opt, d, staging, os.path.join(staging, "files")
                )

    def test_export_copy_and_unchanged_copies(self):
        from cartagra_patch import images, pipeline

        w, h = 2, 2
        pak = make_pak([])
        pics = {
            "menu": bytes(range(16)),
            "title_a": bytes(range(16, 32)),
            "title_b": bytes(range(32, 48)),
        }
        pak.entries = [
            Entry(
                n, make_cz4(px, w, h), b"", {SEC_PARENT: b"\0\0", SEC_HASH: b"\0" * 8}
            )
            for n, px in pics.items()
        ]
        pak.entries.append(
            Entry("tone", b"\0\3\6\t", b"", {SEC_PARENT: b"\0\0", SEC_HASH: b"\0" * 8})
        )
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "target", "files")
            os.makedirs(os.path.join(target, "image", "resident"))
            pak.write(os.path.join(target, "image", "resident", "PARTS.PAK"))
            original = os.path.join(d, "_original_steam", "en")
            os.makedirs(original)
            with open(os.path.join(original, "images.tsv"), "w", encoding="utf-8") as f:
                f.write(
                    "archive\tentry\tshows\nresident/PARTS\tmenu\tmenu\nresident/PARTS\ttitle_*\ttitles\n"
                )
            rows = images.load_list(os.path.join(original, "images.tsv"))
            self.assertEqual(
                images.export(
                    target, rows, os.path.join(original, "images"), log=quiet
                ),
                3,
            )
            lang = {
                "code": "xx",
                "interface_table": os.path.join(d, "xx", "interface.tsv"),
                "images_dir": os.path.join(d, "xx", "images"),
                "interface_original_dir": original,
            }
            self.assertEqual(
                images.copy_missing(
                    os.path.join(original, "images"), lang["images_dir"]
                ),
                3,
            )
            copies = os.path.join(lang["images_dir"], "resident", "PARTS")
            self.assertEqual(
                sorted(os.listdir(copies)), ["menu.png", "title_a.png", "title_b.png"]
            )
            self.assertEqual(
                cztool.read_png(os.path.join(copies, "menu.png"))[2], pics["menu"]
            )

            # unedited copies: nothing needed, nothing written
            self.assertEqual(images.changed_images(lang), {})
            self.assertEqual(project.needed_optional_inputs(lang), [])
            opt = pipeline.BuildOptions(lang, "jp", target)
            staging = os.path.join(d, "staging")
            out = os.path.join(staging, "files", "image", "resident", "PARTS.PAK")
            self.assertEqual(
                pipeline._build_interface(
                    quiet, opt, d, staging, os.path.join(staging, "files")
                ),
                (0, 0),
            )
            self.assertFalse(os.path.exists(out))

            # an edited copy is kept by copy_missing and replaced by the build
            edited = bytes(255 - b for b in pics["menu"])
            cztool.write_png(os.path.join(copies, "menu.png"), edited, w, h)
            self.assertEqual(
                images.copy_missing(
                    os.path.join(original, "images"), lang["images_dir"]
                ),
                0,
            )
            self.assertEqual(list(images.changed_images(lang)), ["resident/PARTS"])
            self.assertEqual(
                project.needed_optional_inputs(lang), ["image/resident/PARTS.PAK"]
            )
            self.assertEqual(
                pipeline._build_interface(
                    quiet, opt, d, staging, os.path.join(staging, "files")
                ),
                (0, 1),
            )
            by = {e.name: e for e in LucaPak.read(out).entries}
            self.assertEqual(cztool.decode(by["menu"].data)[1], edited)
            self.assertEqual(by["title_a"].data[:4], b"CZ4\0")

            # without exported originals the build compares pixels: unchanged copies are still skipped
            os.remove(out)
            shutil.rmtree(os.path.join(original, "images"))
            self.assertEqual(
                pipeline._build_interface(
                    quiet, opt, d, staging, os.path.join(staging, "files")
                ),
                (0, 1),
            )

            with self.assertRaisesRegex(
                ValueError, "no picture matching 'nothing_\\*'"
            ):
                images.export(
                    target,
                    [("resident/PARTS", "nothing_*", "")],
                    os.path.join(d, "x"),
                    log=quiet,
                )


class ExeTextTests(unittest.TestCase):
    def rows(self, **translations):
        originals = {0x2000: "Hello", 0x2010: "%d items", 0x2020: "Other"}
        return [
            dict(id=k, original=v, translation=translations.get(v.split()[-1], ""))
            for k, v in originals.items()
        ]

    def test_references_and_translate(self):
        exe = make_exe()
        pe = exe_text.PE(exe)
        refs = pe.references()
        self.assertEqual(sorted(k for k, _ in refs[0x2000]), ["lea", "lea"])
        self.assertEqual([k for k, _ in refs[0x2010]], ["abs"])
        self.assertEqual(
            [s[1] for s in exe_text.list_strings(exe)], ["Hello", "%d items", "Other"]
        )
        out, n, nrefs = exe_text.translate(
            exe, self.rows(Hello="Привет, мир", items="%d предметов")
        )
        self.assertEqual((n, nrefs), (2, 3))
        new = exe_text.PE(out)
        sec = new.section(exe_text.SECTION_NAME)
        self.assertEqual((sec.va, new.nsec), (0x5000, 5))
        self.assertEqual(
            struct.unpack_from("<I", out, new.opt + 56)[0], 0x6000
        )  # SizeOfImage
        for code_rva, text in (
            (0x1000, "Привет, мир"),
            (0x1010, "Привет, мир"),
            (0x1020, "Other"),
        ):
            off = new.rva_to_off(code_rva) + 3
            target = code_rva + 7 + struct.unpack_from("<i", out, off)[0]
            self.assertEqual(new.cstr(target).decode(), text)
        pointer = struct.unpack_from("<Q", out, 0x800)[0] - new.base
        self.assertEqual(new.cstr(pointer).decode(), "%d предметов")
        self.assertEqual(new.cstr(0x2000), b"Hello")  # originals stay
        self.assertEqual(len(out) % 0x200, 0)
        with self.assertRaisesRegex(ValueError, "already has a .uitext section"):
            exe_text.translate(out, self.rows(Hello="x"))
        self.assertEqual(exe_text.translate(exe, self.rows()), (exe, 0, 0))

    def test_apply_fixes(self):
        exe = make_exe()
        fix = {"name": "lea -> mov", "rva": "0x1000", "old": "48 8d", "new": "48 8b"}
        out = exe_text.apply_fixes(exe, [fix])
        self.assertEqual(out[0x400:0x402], b"\x48\x8b")
        self.assertEqual(
            [k for k in range(len(exe)) if exe[k] != out[k] and not 0x98 <= k < 0x9C],
            [0x401],
        )  # + checksum
        self.assertEqual(exe_text.apply_fixes(exe, []), exe)
        with self.assertRaisesRegex(
            ValueError, "'lea -> mov': expected 48 8d at RVA 0x1000"
        ):
            exe_text.apply_fixes(out, [fix])  # already applied / other executable
        with self.assertRaises(ValueError):
            exe_text.apply_fixes(exe, [dict(fix, rva="0x9000")])  # outside the sections

    def test_restoration_exe_fixes_fit_the_target_exe(self):
        exe = os.path.join(project.INPUTS_DIR, "ru-steam", "CARTAGRA.exe")
        if not os.path.isfile(exe):
            self.skipTest("inputs/ru-steam/CARTAGRA.exe not present")
        with open(exe, "rb") as f:
            data = f.read()
        fixes = project.load_restoration()["exe_fixes"]["fixes"]
        self.assertTrue(fixes)
        out = exe_text.apply_fixes(
            exe_text.translate(
                data,
                exe_text.load_table(project.load_language("ru")["interface_table"]),
            )[0],
            fixes,
        )
        self.assertEqual(
            exe_text.PE(out).data[exe_text.PE(out).rva_to_off(0x2F4293)], 0xEB
        )

    def test_restore_original_text(self):
        exe = make_exe()
        translated = exe_text.translate(exe, self.rows(Hello="Привет"))[0]
        back = [["0x1000", "0x2000"], ["0x1010", "0x2000"]]
        out, n = exe_text.restore_original_text(translated, ".uitext", back)
        self.assertEqual(n, 2)
        self.assertEqual(
            [k for k in range(len(exe)) if exe[k] != out[k] and not 0x98 <= k < 0x9C],
            [],
        )  # + checksum
        self.assertEqual(len(out), len(exe))
        self.assertEqual(
            exe_text.restore_original_text(exe, ".uitext", back), (exe, 0)
        )  # no section: unchanged
        with self.assertRaisesRegex(
            ValueError, "1 references into .uitext are not in the list"
        ):
            exe_text.restore_original_text(translated, ".uitext", back[:1])
        with self.assertRaisesRegex(ValueError, "does not point into .uitext"):
            exe_text.restore_original_text(
                translated, ".uitext", back + [["0x1020", "0x2020"]]
            )
        with self.assertRaisesRegex(ValueError, "not an original string"):
            exe_text.restore_original_text(
                translated, ".uitext", [["0x1000", "0x5000"], back[1]]
            )

    def test_original_text_restores_the_target_exe(self):
        exe = os.path.join(project.INPUTS_DIR, "ru-steam", "CARTAGRA.exe")
        if not os.path.isfile(exe):
            self.skipTest("inputs/ru-steam/CARTAGRA.exe not present")
        with open(exe, "rb") as f:
            data = f.read()
        spec = project.load_restoration()["exe_original_text"]
        out, n = exe_text.restore_original_text(
            data, spec["section"], spec["redirects"]
        )
        self.assertEqual(n, 58)
        pe = exe_text.PE(out)
        self.assertIsNone(pe.section(b".rtransl"))
        self.assertNotRegex(
            out, rb"(?:[\xd0\xd1][\x80-\xbf]){3}"
        )  # no Russian text left
        for ins, _ in spec["redirects"]:
            rva = int(ins, 16)
            target = rva + 7 + struct.unpack_from("<i", out, pe.rva_to_off(rva) + 3)[0]
            self.assertRegex(
                pe.cstr(target).decode("utf-8"), r"^[ -~\n—﹣é]+$"
            )  # the English text
        self.assertEqual(
            sum(a != b for a, b in zip(data[0x400:0x650C00], out[0x400:0x650C00])), 229
        )  # the leas only
        fixed = exe_text.apply_fixes(
            out, project.load_restoration()["exe_fixes"]["fixes"]
        )
        self.assertEqual(fixed[pe.rva_to_off(0x2F4293)], 0xEB)

    def test_check_table_problems(self):
        pe = exe_text.PE(make_exe())
        rows = self.rows(items="%s предметов")
        rows.append(dict(id=0x2000, original="Hello", translation=""))
        rows.append(dict(id=0x2001, original="Hi", translation=""))
        rows.append(dict(id=0x9000, original="x", translation=""))
        problems = exe_text.check_table(pe, rows)
        self.assertEqual(len(problems), 4)
        self.assertIn("placeholders ['%s'] differ", problems[0])
        self.assertIn("duplicate id", problems[1])
        self.assertIn("the table 'Hi'", problems[2])
        self.assertIn("not inside the executable", problems[3])

    def test_picture_list_fits_the_target_archives(self):
        """Every row of _original_steam/en/images.tsv names pictures of the Russian release, when its archives are present."""
        import fnmatch
        from cartagra_patch import images
        from cartagra_patch.lucapak import read_index

        files = os.path.join(project.INPUTS_DIR, "ru-steam", "files")
        rows = images.load_list(
            os.path.join(project.LANGUAGES_DIR, "_original_steam", "en", "images.tsv")
        )
        for archive in sorted({r[0] for r in rows}):
            path = images.archive_path(files, archive)
            if not os.path.isfile(path):
                continue
            names = read_index(path)[1]
            for _, pattern, _ in (r for r in rows if r[0] == archive):
                self.assertTrue(fnmatch.filter(names, pattern), f"{archive}: {pattern}")

    def test_table_roundtrip(self):
        rows = [
            dict(id=0x50AF98, original="Only Choices", translation="Только\tвыборы\n")
        ]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "interface.tsv")
            exe_text.write_table(path, rows)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(
                    f.read(),
                    "id\toriginal\ttranslation\n50af98\tOnly Choices\tТолько\\tвыборы\\n\n",
                )
            self.assertEqual(
                [
                    {k: r[k] for k in ("id", "original", "translation")}
                    for r in exe_text.load_table(path)
                ],
                rows,
            )
            self.assertEqual(exe_text.load_table(os.path.join(d, "absent.tsv")), [])

    def test_language_tables_fit_the_target_exe(self):
        """Every interface table (and the original one) matches the Russian release's exe, when it is present."""
        exe = os.path.join(project.INPUTS_DIR, "ru-steam", "CARTAGRA.exe")
        if not os.path.isfile(exe):
            self.skipTest("inputs/ru-steam/CARTAGRA.exe is not present")
        with open(exe, "rb") as f:
            pe = exe_text.PE(f.read())
        refs = pe.references()
        original = exe_text.load_table(
            os.path.join(
                project.LANGUAGES_DIR, "_original_steam", "en", "interface.tsv"
            )
        )
        self.assertTrue(original and not any(r["translation"] for r in original))
        ru = exe_text.load_table(project.load_language("ru")["interface_table"])
        self.assertEqual([r["id"] for r in ru], [r["id"] for r in original])
        # kept in English: a song title (the labels drawn with the small font FONT1 get Cyrillic from font_glyphs)
        self.assertEqual(
            {r["original"] for r in ru if not r["translation"]}, {"❝LUNA❞"}
        )
        self.assertEqual(exe_text.check_table(pe, original, refs), [])
        self.assertEqual(exe_text.check_table(pe, ru, refs), [])


def gallery_table(slots, ranges):
    words = [0, 0, 0, 1, 1, len(slots)]
    groups = [s for s in slots if len(s) > 1]
    k = 0
    for s in slots:
        if len(s) > 1:
            k += 1
        words.append(s[0] if len(s) == 1 else 0x10000 - k)
    words += [0] * len(slots) + [len(groups)]
    for g in groups:
        words += [len(g)] + g
    data = struct.pack(f"<{len(words)}H", *words)
    for base, flags in ranges:
        data += struct.pack(f"<IH{len(flags)}H", base, len(flags), *flags)
    return data


class GalleryTests(unittest.TestCase):
    def test_round_trip(self):
        data = gallery_table(
            [[101], [102, 103], [104]], [[1, [7, 0xFFFF]], [101, [0, 1, 2, 3]]]
        )
        g = gallery.Gallery.parse(data)
        self.assertEqual(g.slots, [[101], [102, 103], [104]])
        self.assertEqual(g.seen_flag(103), 2)
        self.assertEqual(g.seen_flag(2), 0xFFFF)
        self.assertEqual(g.build(), data)
        with self.assertRaisesRegex(ValueError, "group 2"):
            bad = bytearray(gallery_table([[101], [102, 103]], []))
            bad[14:16] = struct.pack(
                "<H", 0xFFFE
            )  # the second slot refers to group 2 of 1
            gallery.Gallery.parse(bytes(bad))

    def test_merge(self):
        target = gallery.Gallery.parse(
            gallery_table([[101], [102], [103, 104]], [[101, [0, 1, 2, 4]]])
        )
        # JP: 201 = 101, 203 = 103; 202, 205, 206 and 207 are new pictures (output 105..108); 209 is missing
        jp = gallery.Gallery.parse(
            gallery_table([[205], [201], [202, 209], [203, 206], [207]], [])
        )
        jp_to_out = {
            201: [101],
            202: [105],
            203: [103],
            205: [106],
            206: [107],
            207: [108],
            209: [],
        }
        g, added, origins, left_out = gallery.merge(target, jp, jp_to_out, [(101, 8)])
        self.assertEqual(g.slots, [[106], [101], [105], [102], [103, 104, 107], [108]])
        self.assertEqual((added, left_out), (4, [209]))
        self.assertEqual(
            origins,
            [
                ("jp", 0),
                ("target", 0),
                ("jp", 2),
                ("target", 1),
                ("target", 2),
                ("jp", 4),
            ],
        )
        self.assertEqual(g.strings, [""] * 6)
        # the target's flags stay; new pictures get the free numbers in ID order
        self.assertEqual(g.ranges, [[101, [0, 1, 2, 4, 3, 5, 6, 7]]])
        self.assertEqual(gallery.Gallery.parse(g.build()).slots, g.slots)
        with self.assertRaisesRegex(ValueError, "in no range"):
            gallery.merge(target, jp, jp_to_out, [])

    def test_previews(self):
        def preview(w, h, vw, vh, rgb):
            head = bytearray(28)
            head[0:4] = b"CZ0\x00"
            struct.pack_into("<IHHH", head, 4, 28, w, h, 32)
            struct.pack_into("<HH", head, 0x18, vw, vh)
            return bytes(head) + bytes(rgb + (255,)) * (w * h)

        target, jp = LucaPak(), LucaPak()
        target.section_types = [(3, 1), (SEC_HASH, 8)]
        target.entries = [
            Entry(
                f"CGGALLERY_CH01_{i:03d}",
                preview(8, 4, 6, 3, (i, i, i)),
                b"",
                {3: b"\x00"},
            )
            for i in (1, 2)
        ]
        jp.entries = [
            Entry(
                "CGMODE_CH01_001",
                preview(10, 6, 9, 5, (200, 100, 50)),
                b"",
                {3: b"\x00"},
            )
        ]
        gallery.build_previews(target, jp, [("target", 1), ("jp", 0), ("target", 0)])
        self.assertEqual(
            [e.name for e in target.entries],
            ["CGGALLERY_CH01_001", "CGGALLERY_CH01_002", "CGGALLERY_CH01_003"],
        )
        self.assertEqual(target.entries[0].data[28:31], bytes((2, 2, 2)))
        hd, rgba = cztool.decode(target.entries[1].data)
        self.assertEqual(
            (hd["magic"], hd["width"], hd["height"], hd["canvas"]),
            (b"CZ0\x00", 8, 4, (6, 3)),
        )
        self.assertEqual(
            rgba[:4], bytes((200, 100, 50, 255))
        )  # the visible part, scaled
        self.assertEqual(rgba[4 * 6 : 4 * 8], b"\x00\x00\x00\xff" * 2)  # black margin
        self.assertEqual(rgba[4 * 8 * 3 :], b"\x00\x00\x00\xff" * 8)
        self.assertEqual(
            target.entries[1].sections[SEC_HASH], xxh64_pure(target.entries[1].data)
        )
        self.assertEqual(cztool.resize(bytes(range(16)), 2, 2, 2, 2), bytes(range(16)))

    def test_image_map(self):
        jp = [("EVENTCG", 1001, ["e1", "e2", "e3"])]
        out = [("EVENTCG", 1001, ["e1", "e3", "e2", "e2_jp"])]
        self.assertEqual(
            gallery.image_map(jp, out, {("EVENTCG", "e2"): "e2_jp"}),
            {1001: [1001], 1002: [1004, 1003], 1003: [1002]},
        )
        self.assertEqual(
            gallery.image_map(jp, [("EVENTCG", 1001, ["e1"])]),
            {1001: [1001], 1002: [], 1003: []},
        )

    def test_real_tables(self):
        """The tables of both releases are read and written back unchanged; the merge gives 18 pages."""
        paths = {
            s: os.path.join(project.INPUTS_DIR, s, "files", "PARAM.PAK")
            for s in ("jp-fhd", "ru-steam")
        }
        if not all(os.path.isfile(p) for p in paths.values()):
            self.skipTest("inputs/*/files/PARAM.PAK is not present")
        jp = next(
            e.data
            for e in LucaPak.read(paths["jp-fhd"]).entries
            if e.name == gallery.JP_ENTRY
        )
        tg = next(
            e.data
            for e in LucaPak.read(paths["ru-steam"]).entries
            if e.name == gallery.ENTRY
        )
        for data, slots, pictures in ((jp, 254, 473), (tg, 185, 301)):
            g = gallery.Gallery.parse(data)
            self.assertEqual((len(g.slots), len(g.pictures())), (slots, pictures))
            self.assertEqual(g.build(), data)


class TsvTests(unittest.TestCase):
    def test_roundtrip_and_legacy_columns(self):
        rows = [
            dict(
                row=0,
                kind="msg",
                voice="12",
                jp="a\tb",
                translation="x\ny",
                source="tsv",
            ),
            dict(row=1, kind="msg", voice="0", jp="c", translation="", source="todo"),
        ]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.tsv")
            sp.write_tsv(path, rows)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(
                    f.readline().rstrip("\n").split("\t"),
                    ["row", "kind", "voice", "jp", "translation"],
                )
                self.assertEqual(
                    f.readline().rstrip("\n").split("\t"),
                    ["0", "msg", "12", "a\\tb", "x\\ny"],
                )
            self.assertEqual(sp.load_tsv(path), {(0, "a\tb"): "x\ny"})
            for header, row in (
                (
                    "row\tkind\tvoice\tsource\tjp\tru_existing\tru",
                    "0\tmsg\t0\ttsv\tjp\t\tперевод",
                ),
                (
                    "row\tkind\tvoice\tsource\tjp\texisting\ttranslation",
                    "0\tmsg\t0\ttsv\tjp\tx\tперевод",
                ),
            ):
                legacy = os.path.join(d, "legacy.tsv")
                with open(legacy, "w", encoding="utf-8") as f:
                    f.write(header + "\n" + row + "\n")
                self.assertEqual(sp.load_tsv(legacy), {(0, "jp"): "перевод"})
            self.assertEqual(sp.load_tsv(os.path.join(d, "absent.tsv")), {})


class ProjectTests(unittest.TestCase):
    def test_languages_and_manifest(self):
        langs = project.available_languages()
        self.assertIn("ru", langs)
        self.assertIn("en", langs)
        manifest = project.load_manifest()
        for code in langs:
            cfg = project.load_language(code)
            self.assertIn(cfg["target"], manifest["sets"])
            self.assertIn(cfg["status"], project.STATUSES)
            if cfg["interface_original_dir"]:
                for name in ("interface.tsv", "images.tsv"):
                    self.assertTrue(
                        os.path.isfile(
                            os.path.join(cfg["interface_original_dir"], name)
                        ),
                        name,
                    )
        self.assertNotEqual(langs["en"]["status"], "complete")
        with self.assertRaises(project.BuildError):
            project.load_language("xx")

    def test_paths_do_not_depend_on_cwd(self):
        for path in (
            project.DEFINITIONS_DIR,
            project.LANGUAGES_DIR,
            project.INPUTS_DIR,
            project.BUILD_DIR,
            project.DIST_DIR,
        ):
            self.assertTrue(os.path.isabs(path))
            self.assertEqual(os.path.dirname(path), ROOT)

    def test_output_names(self):
        from cartagra_patch.pipeline import BuildOptions

        lang = {"code": "ru"}
        self.assertEqual(BuildOptions(lang, "j", "t").output_name, "ru")
        self.assertEqual(
            BuildOptions(lang, "j", "t", scenes=["a1-7-2h"]).output_name, "ru-partial"
        )
        self.assertEqual(
            BuildOptions(lang, "j", "t", test_start="a1-7-2h").output_name, "ru-test"
        )

    def test_check_inputs_reports_missing(self):
        with tempfile.TemporaryDirectory() as d:
            problems = project.check_inputs(
                "ru-steam", os.path.join(d, "none"), project.load_manifest()
            )
            self.assertTrue(problems and "does not exist" in problems[0])
            os.makedirs(os.path.join(d, "files"))
            problems = project.check_inputs(
                "ru-steam", os.path.join(d, "files"), project.load_manifest()
            )
            self.assertTrue(any("missing" in p for p in problems))

    def test_check_inputs_detects_wrong_files(self):
        files = {
            "A.PAK": {"use": "data"},
            "image/B.PAK": {"use": "index", "entries": 2},
            "C.PAK": {"use": "data", "size": 5},
        }
        manifest = {"sets": {"s": {"description": "test", "files": files}}}
        with tempfile.TemporaryDirectory() as d:
            make_pak(["a"]).write(os.path.join(d, "A.PAK"))
            os.makedirs(os.path.join(d, "image"))
            make_pak(["a", "b", "c"]).write(os.path.join(d, "image", "B.PAK"))
            with open(os.path.join(d, "C.PAK"), "wb") as f:
                f.write(b"123")
            files["A.PAK"]["sha256"] = project.sha256_file(os.path.join(d, "A.PAK"))
            problems = project.check_inputs("s", d, manifest, log=quiet)
            self.assertEqual(len(problems), 2)
            self.assertIn("3 entries, expected 2", problems[0])
            self.assertIn("3 bytes, expected 5", problems[1])
            with open(os.path.join(d, "A.PAK"), "r+b") as f:
                f.seek(-1, 2)
                f.write(b"!")
            problems = project.check_inputs("s", d, manifest, log=quiet)
            self.assertTrue(any("SHA-256 differs" in p for p in problems))
            self.assertEqual(
                len(
                    project.check_inputs(
                        "s", d, manifest, verify_checksums=False, log=quiet
                    )
                ),
                2,
            )

    def test_check_inputs_optional_files(self):
        files = {
            "../GAME.exe": {
                "use": "data",
                "optional": True,
                "needed_for": "interface translation",
            }
        }
        manifest = {"sets": {"s": {"description": "test", "files": files}}}
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, "files")
            os.makedirs(folder)
            self.assertEqual(project.check_inputs("s", folder, manifest, log=quiet), [])
            problems = project.check_inputs(
                "s", folder, manifest, log=quiet, needed=["../GAME.exe"]
            )
            self.assertEqual(len(problems), 1)
            self.assertIn("needed for interface translation", problems[0])
            with open(os.path.join(d, "GAME.exe"), "wb") as f:
                f.write(b"MZ" + bytes(100))
            files["../GAME.exe"]["sha256"] = project.sha256_file(
                os.path.join(d, "GAME.exe")
            )
            self.assertEqual(
                project.check_inputs(
                    "s", folder, manifest, log=quiet, needed=["../GAME.exe"]
                ),
                [],
            )
            with open(os.path.join(d, "GAME.exe"), "wb") as f:
                f.write(b"XX" + bytes(100))
            problems = project.check_inputs("s", folder, manifest, log=quiet)
            self.assertEqual(
                problems, [f"{os.path.join(d, 'GAME.exe')}: not a Windows executable"]
            )


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        with tempfile.TemporaryDirectory(prefix="cwd with spaces ") as cwd:
            return subprocess.run(
                [sys.executable, os.path.join(ROOT, "build.py"), *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

    def test_help_and_errors(self):
        self.assertEqual(self.run_cli("--help").returncode, 0)
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(self.run_cli("--language", "xx").returncode, 2)
        self.assertEqual(
            self.run_cli("--language", "ru", "--test-set", "1=2").returncode, 2
        )

    def test_list_languages_marks_status(self):
        r = self.run_cli("--list-languages")
        self.assertEqual(r.returncode, 0)
        self.assertRegex(r.stdout, r"ru +Russian +incomplete")
        self.assertRegex(r.stdout, r"en +English +untested")

    def test_missing_inputs_fail_cleanly(self):
        with tempfile.TemporaryDirectory(prefix="inputs with spaces ") as empty:
            r = self.run_cli("--language", "ru", "--check", "--inputs", empty)
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not exist", r.stderr)


def tree_hashes(folder):
    out = {}
    for dirpath, _, names in os.walk(folder):
        for n in names:
            path = os.path.join(dirpath, n)
            out[os.path.relpath(path, folder).replace(os.sep, "/")] = (
                project.sha256_file(path)
            )
    return out


@unittest.skipUnless(
    os.environ.get("CARTAGRA_INTEGRATION") == "1", "set CARTAGRA_INTEGRATION=1 to run"
)
class IntegrationTests(unittest.TestCase):
    """
    Builds ru from the real inputs into a temporary folder (not the project's build/ or dist/):
    once as the reference build (no tables, start sequence, _arflag update or interface; must equal the reference),
    twice normally (must be identical; New Game must call the prologue; _arflag must match every script;
    CARTAGRA.exe is written when the interface is translated).
    """

    def test_ru_build_is_reproducible_and_leaves_inputs_alone(self):
        from cartagra_patch import fonts, images, pipeline

        lang = project.load_language("ru")
        manifest = project.load_manifest()
        dirs = {
            "jp-fhd": os.path.join(project.INPUTS_DIR, "jp-fhd", "files"),
            lang["target"]: os.path.join(project.INPUTS_DIR, lang["target"], "files"),
        }
        for set_name, folder in dirs.items():
            if project.check_inputs(
                set_name, folder, manifest, verify_checksums=False, log=quiet
            ):
                self.skipTest(f"inputs/{set_name} is not complete")
        mtimes = {
            d: os.path.getmtime(os.path.join(d, "SCRIPT.PAK")) for d in dirs.values()
        }
        hashes = []
        with tempfile.TemporaryDirectory(prefix="cartagra build ") as tmp:
            saved = pipeline.BUILD_DIR, pipeline.DIST_DIR
            try:
                pipeline.BUILD_DIR = os.path.join(tmp, "build")
                pipeline.DIST_DIR = os.path.join(tmp, "dist")
                for tables, start in (
                    (os.path.join(tmp, "no tables"), False),
                    (lang["translation_dir"], True),
                    (lang["translation_dir"], True),
                ):
                    opt = pipeline.BuildOptions(
                        dict(lang, translation_dir=tables),
                        dirs["jp-fhd"],
                        dirs[lang["target"]],
                        reference=not start,
                    )
                    dist = pipeline.run_build(
                        opt, project.load_restoration(), log=quiet
                    )
                    hashes.append(tree_hashes(dist))
                    shutil.rmtree(os.path.join(tmp, "build"))
                entries = LucaPak.read(
                    os.path.join(dist, "files", "SCRIPT.PAK")
                ).entries
                script = {e.name: e.data for e in entries}
            finally:
                pipeline.BUILD_DIR, pipeline.DIST_DIR = saved
        files = [
            {k[len("files/") :]: v for k, v in h.items() if k.startswith("files/")}
            for h in hashes
        ]
        self.assertEqual(files[0], REFERENCE_RU)
        self.assertEqual(hashes[1], hashes[2])
        self.assertNotIn("CARTAGRA.exe", hashes[0])
        self.assertEqual(
            "CARTAGRA.exe" in hashes[1], project.interface_translated(lang)
        )
        self.assertEqual(sp.calls_to(script["0000-op1"], "0000-op0_HD"), 1)
        self.assertEqual(sp.calls_to(script["0308-02-00"], "0000-op0_HD"), 0)
        self.assertEqual(
            sp.rebuild_arflag(script["_arflag"], [e.name for e in entries], entries)[1],
            [],
        )  # every script has a correct record
        # every label (the ending list starts scripts there) is an instruction start
        labels = sp.read_labels(script["_scr_label"])
        for k, e in enumerate(x for x in entries if not x.name.startswith("_")):
            starts = {i.offset for i in ls.parse(e.data)}
            self.assertEqual(
                [n for n, o, _ in labels[k + 1] if o not in starts], [], e.name
            )
        self.assertIn(
            b"ENDING",
            [
                n
                for n, _, _ in labels[
                    [e.name for e in entries].index("0210-12-01h") + 1
                ]
            ],
        )
        # the archives of the translated pictures (languages/ru/images/, not in git) are added
        pictures = {f"image/{archive}.PAK" for archive in images.changed_images(lang)}
        # and the small fonts with the added letters
        if lang.get("font_glyphs"):
            pictures |= {
                f
                for f in fonts.input_files()
                if os.path.basename(f).startswith(fonts.TARGET)
            }
        # and the large fonts with the redrawn №
        if lang.get("font_numero"):
            pictures |= {
                f
                for f in fonts.input_files()
                if os.path.basename(f).startswith(fonts.SOURCE)
            }
        self.assertLessEqual(pictures, set(files[1]))
        # the CG gallery (PARAM.PAK) and its previews (SYSCG2.PAK) are new since the reference build
        self.assertLessEqual({"PARAM.PAK", "image/SYSCG2.PAK"}, set(files[1]))
        self.assertEqual(
            {
                k: v
                for k, v in files[1].items()
                if k not in ("SCRIPT.PAK", "PARAM.PAK", "image/SYSCG2.PAK")
                and k not in pictures
            },
            {
                k: v
                for k, v in REFERENCE_RU.items()
                if k != "SCRIPT.PAK" and k not in pictures
            },
        )
        for set_name, folder in dirs.items():
            self.assertEqual(
                project.check_inputs(set_name, folder, manifest, log=quiet), []
            )
        self.assertEqual(
            mtimes,
            {d: os.path.getmtime(os.path.join(d, "SCRIPT.PAK")) for d in dirs.values()},
        )


if __name__ == "__main__":
    unittest.main()
