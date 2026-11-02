#!/usr/bin/env python3
"""
Interface text of the game executable (CARTAGRA.exe).

The interface strings (options, confirmation dialogs, music and ending titles, ...) are
UTF-8 C strings in .rdata, one set per language (Japanese, Simplified Chinese, English);
the Russian release shows the English set. The code loads a string with a RIP-relative
`lea reg, [rip+disp32]`; a few (month names) are read from pointer tables, which are
absolute addresses with base relocations.

A translation is usually longer than the original (Cyrillic takes two bytes in UTF-8), so
the strings are not overwritten: translations go into a new section (.uitext) and every
reference to a translated string is redirected there. Nothing else in the file changes.
The Russian release's translators used the same method for the prologue text
(their section .rtransl).

Table (languages/<lang>/interface.tsv, UTF-8, tab-separated):
  id           RVA of the original string (hex), e.g. 50af98
  original     the string in the target release's exe (checked by the build)
  translation  replacement text; empty = keep the original
`\\n` is a line break, `\\t` a tab. printf placeholders (%d, %02d, %s, %%) must stay the
same and in the same order.

Usage:
  python -m cartagra_patch.exe_text list <exe>               every referenced string (to find new rows)
  python -m cartagra_patch.exe_text check <exe> <table.tsv>  check a table against an exe
"""

import os
import re
import struct
import sys

from .script_port import tsv_escape, tsv_unescape

TABLE_COLUMNS = ("id", "original", "translation")
SECTION_NAME = b".uitext"
SCN_INITIALIZED_DATA_READ = 0x40000040
IMAGE_REL_BASED_DIR64 = 10
# lea r64, [rip+disp32]: REX.W (0x48) or REX.WR (0x4C), 8D, ModRM with mod=00 rm=101
LEA_RIP = re.compile(rb"[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]", re.S)
PRINTF = re.compile(r"%[-+ #0]*\d*(?:\.\d+)?[hlLzjt]*[diouxXeEfgGcsp%]")


def _align(x, a):
    return -(-x // a) * a


class Section:
    HEADER = struct.Struct("<8sIIIIIIHHI")

    def __init__(self, raw_header):
        (self.name, self.vsize, self.va, self.rsize, self.raw, *_rest) = self.HEADER.unpack(raw_header)
        self.name = self.name.rstrip(b"\0")


class PE:
    """Minimal PE32+ reader/writer: sections, references to strings, adding a section."""

    def __init__(self, data):
        self.data = bytearray(data)
        if self.data[:2] != b"MZ":
            raise ValueError("not an executable (no MZ header)")
        self.pe = struct.unpack_from("<I", self.data, 0x3C)[0]
        if self.data[self.pe : self.pe + 4] != b"PE\0\0":
            raise ValueError("not a PE executable")
        self.opt = self.pe + 24
        if struct.unpack_from("<H", self.data, self.opt)[0] != 0x20B:
            raise ValueError("not a 64-bit (PE32+) executable")
        self.nsec = struct.unpack_from("<H", self.data, self.pe + 6)[0]
        self.sec_table = self.opt + struct.unpack_from("<H", self.data, self.pe + 20)[0]
        self.base = struct.unpack_from("<Q", self.data, self.opt + 24)[0]
        self.sec_align, self.file_align = struct.unpack_from("<II", self.data, self.opt + 32)
        self.sections = [Section(self.data[self.sec_table + 40 * k : self.sec_table + 40 * k + 40])
                         for k in range(self.nsec)]

    def section(self, name):
        return next((s for s in self.sections if s.name == name), None)

    def rva_to_off(self, rva):
        for s in self.sections:
            if s.va <= rva < s.va + min(s.vsize, s.rsize):
                return rva - s.va + s.raw
        return None

    def off_to_rva(self, off):
        for s in self.sections:
            if s.raw <= off < s.raw + s.rsize:
                return off - s.raw + s.va
        return None

    def cstr(self, rva):
        off = self.rva_to_off(rva)
        if off is None:
            return None
        end = self.data.find(b"\0", off)
        return bytes(self.data[off:end])

    def directory(self, index):
        return struct.unpack_from("<II", self.data, self.opt + 112 + 8 * index)

    def references(self):
        """{target RVA: [("lea", file offset of disp32) | ("abs", file offset of the pointer)]}."""
        refs = {}
        text = self.section(b".text")
        for m in LEA_RIP.finditer(self.data, text.raw, text.raw + text.rsize):
            o = m.start()
            target = self.off_to_rva(o) + 7 + struct.unpack_from("<i", self.data, o + 3)[0]
            refs.setdefault(target, []).append(("lea", o + 3))
        rva, size = self.directory(5)  # base relocations
        p, end = self.rva_to_off(rva), self.rva_to_off(rva) + size
        while p < end:
            page, block = struct.unpack_from("<II", self.data, p)
            if block < 8:
                break
            for k in range((block - 8) // 2):
                e = struct.unpack_from("<H", self.data, p + 8 + 2 * k)[0]
                if e >> 12 == IMAGE_REL_BASED_DIR64:
                    off = self.rva_to_off(page + (e & 0xFFF))
                    if off is not None:
                        target = struct.unpack_from("<Q", self.data, off)[0] - self.base
                        refs.setdefault(target, []).append(("abs", off))
            p += block
        return refs

    def add_section(self, name, payload):
        """Append a read-only data section; returns its RVA."""
        if self.section(name):
            raise ValueError(f"the executable already has a {name.decode()} section (already patched?)")
        last = max(self.sections, key=lambda s: s.va)
        header_end = self.sec_table + 40 * (self.nsec + 1)
        first_raw = min(s.raw for s in self.sections if s.rsize)
        if header_end > first_raw or any(self.data[self.sec_table + 40 * self.nsec : header_end]):
            raise ValueError("no room for another section header")
        cert_rva, cert_size = self.directory(4)
        if cert_size:
            raise ValueError("signed executable (certificate table): not supported")
        file_end = max(s.raw + s.rsize for s in self.sections)
        if len(self.data) != file_end:
            raise ValueError("data after the last section (overlay): not supported")
        va = _align(last.va + last.vsize, self.sec_align)
        raw = _align(len(self.data), self.file_align)
        rsize = _align(len(payload), self.file_align)
        self.data += b"\0" * (raw - len(self.data)) + payload + b"\0" * (rsize - len(payload))
        struct.pack_into("<8sIIIIIIHHI", self.data, self.sec_table + 40 * self.nsec,
                         name, len(payload), va, rsize, raw, 0, 0, 0, 0, SCN_INITIALIZED_DATA_READ)
        self.nsec += 1
        struct.pack_into("<H", self.data, self.pe + 6, self.nsec)
        struct.pack_into("<I", self.data, self.opt + 56, _align(va + len(payload), self.sec_align))  # SizeOfImage
        self.sections.append(Section(self.data[self.sec_table + 40 * (self.nsec - 1) : self.sec_table + 40 * self.nsec]))
        return va

    def update_checksum(self):
        pos = self.opt + 64
        struct.pack_into("<I", self.data, pos, 0)
        data = bytes(self.data) + b"\0" * (len(self.data) % 2)
        total = sum(struct.unpack("<%dH" % (len(data) // 2), data))
        while total >> 16:
            total = (total & 0xFFFF) + (total >> 16)
        struct.pack_into("<I", self.data, pos, total + len(self.data))


def load_table(path):
    """[{id, original, translation}] in file order; [] when the file does not exist."""
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        missing = [c for c in TABLE_COLUMNS if c not in header]
        if missing:
            raise ValueError(f"{path}: missing columns {', '.join(missing)}")
        col = {name: i for i, name in enumerate(header)}
        for n, line in enumerate(f, 2):
            if not line.strip():
                continue
            cells = line.rstrip("\n").split("\t")
            if len(cells) < len(header):
                cells += [""] * (len(header) - len(cells))
            try:
                rva = int(cells[col["id"]], 16)
            except ValueError:
                raise ValueError(f"{path}:{n}: bad id {cells[col['id']]!r}") from None
            rows.append(dict(id=rva, original=tsv_unescape(cells[col["original"]]),
                             translation=tsv_unescape(cells[col["translation"]]), line=n))
    return rows


def write_table(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(TABLE_COLUMNS) + "\n")
        for r in rows:
            f.write("\t".join((f"{r['id']:x}", tsv_escape(r["original"]), tsv_escape(r["translation"]))) + "\n")


def check_table(pe, rows, refs=None):
    """Problems (strings) of a table against an executable: unknown ids, changed originals, placeholders."""
    refs = pe.references() if refs is None else refs
    problems = []
    seen = set()
    for r in rows:
        where = f"line {r.get('line', '?')} (id {r['id']:x})"
        if r["id"] in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(r["id"])
        raw = pe.cstr(r["id"])
        if raw is None:
            problems.append(f"{where}: not inside the executable")
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        if text != r["original"]:
            problems.append(f"{where}: the executable has {text!r} here, the table {r['original']!r} "
                            f"(table made for another version of the game?)")
            continue
        if r["id"] not in refs:
            problems.append(f"{where}: nothing in the executable refers to this string")
        if r["translation"] and PRINTF.findall(r["translation"]) != PRINTF.findall(r["original"]):
            problems.append(f"{where}: placeholders {PRINTF.findall(r['translation'])} differ from the "
                            f"original's {PRINTF.findall(r['original'])}")
        if "\0" in r["translation"]:
            problems.append(f"{where}: NUL character in the translation")
    return problems


def translate(data, rows):
    """
    Return (patched executable, number of strings translated, number of references redirected).
    Raises ValueError with all problems when the table does not fit the executable.
    """
    pe = PE(data)
    if pe.section(SECTION_NAME):
        raise ValueError(f"the executable already has a {SECTION_NAME.decode()} section (already patched?)")
    refs = pe.references()
    problems = check_table(pe, rows, refs)
    if problems:
        raise ValueError("\n".join(problems))
    todo = [r for r in rows if r["translation"] and r["translation"] != r["original"]]
    if not todo:
        return bytes(data), 0, 0
    blob, where = bytearray(), {}
    for r in todo:
        text = r["translation"].encode("utf-8")
        if text not in where:
            where[text] = len(blob)
            blob += text + b"\0"
            blob += b"\0" * (-len(blob) % 8)
    va = pe.add_section(SECTION_NAME, bytes(blob))
    redirected = 0
    for r in todo:
        new = va + where[r["translation"].encode("utf-8")]
        for kind, off in refs[r["id"]]:
            if kind == "lea":
                disp = new - (pe.off_to_rva(off) + 4)
                struct.pack_into("<i", pe.data, off, disp)
            else:
                struct.pack_into("<Q", pe.data, off, pe.base + new)
            redirected += 1
    pe.update_checksum()
    return bytes(pe.data), len(todo), redirected


def apply_fixes(data, fixes):
    """
    Return the executable with the byte patches `fixes` applied: dicts with "name", "rva" (hex
    string) and "old"/"new" (hex bytes). Raises ValueError when a fix does not find its original bytes.
    """
    pe = PE(data)
    for fix in fixes:
        old, new = bytes.fromhex(fix["old"]), bytes.fromhex(fix["new"])
        off = pe.rva_to_off(int(fix["rva"], 16))
        if len(old) != len(new) or off is None or pe.data[off:off + len(old)] != old:
            raise ValueError(f"executable fix {fix['name']!r}: expected {fix['old']} at RVA {fix['rva']}")
        pe.data[off:off + len(new)] = new
    if fixes:
        pe.update_checksum()
    return bytes(pe.data)


def restore_original_text(data, section, redirects):
    """
    Undo a translation added the way translate() adds one: point each lea of `redirects`
    ([instruction RVA, original string RVA] as hex strings) from `section` back to its original
    string and remove the section. Returns (executable, number of references restored); an
    executable without the section is returned unchanged. Raises ValueError when it does not fit.
    """
    pe = PE(data)
    name = section.encode()
    sec = pe.section(name)
    if not sec:
        return bytes(data), 0
    if sec is not pe.sections[-1] or len(pe.data) != sec.raw + sec.rsize:
        raise ValueError(f"{section} is not the last section at the end of the file")
    inside = lambda rva: sec.va <= rva < sec.va + sec.vsize
    for ins, orig in redirects:
        off, target = pe.rva_to_off(int(ins, 16)), int(orig, 16)
        if off is None or not LEA_RIP.match(pe.data, off):
            raise ValueError(f"no lea at RVA {ins}")
        if not inside(int(ins, 16) + 7 + struct.unpack_from("<i", pe.data, off + 3)[0]):
            raise ValueError(f"the lea at RVA {ins} does not point into {section}")
        if inside(target) or not pe.cstr(target):
            raise ValueError(f"RVA {orig} is not an original string")
        struct.pack_into("<i", pe.data, off + 3, target - (int(ins, 16) + 7))
    left = [t for t in pe.references() if inside(t)]
    if left:
        raise ValueError(f"{len(left)} references into {section} are not in the list")
    del pe.data[sec.raw:]
    pe.data[pe.sec_table + 40 * (pe.nsec - 1) : pe.sec_table + 40 * pe.nsec] = bytes(40)
    pe.nsec -= 1
    pe.sections.pop()
    struct.pack_into("<H", pe.data, pe.pe + 6, pe.nsec)
    last = pe.sections[-1]
    struct.pack_into("<I", pe.data, pe.opt + 56, _align(last.va + last.vsize, pe.sec_align))  # SizeOfImage
    pe.update_checksum()
    return bytes(pe.data), len(redirects)


def list_strings(data):
    """[(rva, text, lea refs, abs refs)] for every UTF-8 string in .rdata that the code refers to."""
    pe = PE(data)
    rdata = pe.section(b".rdata")
    out = []
    for rva, rs in sorted(pe.references().items()):
        if not rdata.va <= rva < rdata.va + rdata.vsize:
            continue
        raw = pe.cstr(rva)
        if not raw or len(raw) > 4000:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not all(c.isprintable() or c in "\n\t" for c in text):
            continue
        out.append((rva, text, sum(k == "lea" for k, _ in rs), sum(k == "abs" for k, _ in rs)))
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) == 2 and argv[0] == "list":
        for rva, text, lea, ab in list_strings(open(argv[1], "rb").read()):
            print(f"{rva:x}\t{lea}\t{ab}\t{tsv_escape(text)}")
        return 0
    if len(argv) == 3 and argv[0] == "check":
        rows = load_table(argv[2])
        problems = check_table(PE(open(argv[1], "rb").read()), rows)
        for p in problems:
            print(p)
        print(f"{len(rows)} rows, {sum(1 for r in rows if r['translation'])} translated, {len(problems)} problems")
        return 1 if problems else 0
    print(__doc__.split("Usage:")[1])
    return 2


if __name__ == "__main__":
    sys.exit(main())
