#!/usr/bin/env python3
"""
Header-preserving PAK reader/writer for Cartagra REBIRTH FHD (LucaSystem engine).

Unlike pak_tool.py, this keeps every header field the engine uses:
- 0x08 id_start: resource ID of entry 0. Scripts refer to images by
  numeric ID (id_start + entry index), so entry order must not change.
- 0x20 section count, 0x21 flags, and the per-entry sections
  (type 0x01 = parent/base image ID, type 0x0b = xxh64 of the data, ...).
- the per-entry metadata table present when flags & 1 (e.g. BGCG sizes).

See TECHNICAL_NOTES.md, "PAK Archive Format".
"""

import struct
import sys

SEC_PARENT = 0x01
SEC_HASH = 0x0B

_P1, _P2, _P3, _P4, _P5 = (
    0x9E3779B185EBCA87,
    0xC2B2AE3D27D4EB4F,
    0x165667B19E3779F9,
    0x85EBCA77C2B2AE63,
    0x27D4EB2F165667C5,
)
_M = 0xFFFFFFFFFFFFFFFF


def _rotl(x, r):
    return ((x << r) | (x >> (64 - r))) & _M


def _round(acc, lane):
    acc = (acc + lane * _P2) & _M
    return (_rotl(acc, 31) * _P1) & _M


def _merge(acc, val):
    acc ^= _round(0, val)
    return (acc * _P1 + _P4) & _M


def xxh64(data: bytes, seed: int = 0) -> bytes:
    """xxHash64 as 8 little-endian bytes (uses the xxhash module if present)."""
    try:
        import xxhash
    except ImportError:
        return xxh64_pure(data, seed)
    return xxhash.xxh64(data, seed).digest()[::-1]


def xxh64_pure(data: bytes, seed: int = 0) -> bytes:
    """Pure-Python xxHash64 (8 little-endian bytes)."""
    n = len(data)
    p = 0
    if n >= 32:
        v1 = (seed + _P1 + _P2) & _M
        v2 = (seed + _P2) & _M
        v3 = seed & _M
        v4 = (seed - _P1) & _M
        lanes = struct.unpack_from("<%dQ" % ((n // 32) * 4), data)
        for i in range(0, len(lanes), 4):
            v1 = _round(v1, lanes[i])
            v2 = _round(v2, lanes[i + 1])
            v3 = _round(v3, lanes[i + 2])
            v4 = _round(v4, lanes[i + 3])
        p = (n // 32) * 32
        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & _M
        for v in (v1, v2, v3, v4):
            h = _merge(h, v)
    else:
        h = (seed + _P5) & _M
    h = (h + n) & _M
    while p + 8 <= n:
        k = _round(0, struct.unpack_from("<Q", data, p)[0])
        h = ((_rotl(h ^ k, 27) * _P1) + _P4) & _M
        p += 8
    if p + 4 <= n:
        h ^= (struct.unpack_from("<I", data, p)[0] * _P1) & _M
        h = ((_rotl(h, 23) * _P2) + _P3) & _M
        p += 4
    while p < n:
        h ^= (data[p] * _P5) & _M
        h = (_rotl(h, 11) * _P1) & _M
        p += 1
    h ^= h >> 33
    h = (h * _P2) & _M
    h ^= h >> 29
    h = (h * _P3) & _M
    h ^= h >> 32
    return struct.pack("<Q", h)


class Entry:
    def __init__(self, name, data, meta=b"", sections=None, pad=None):
        self.name = name
        self.data = data
        self.meta = meta  # per-entry metadata (flags & 1), raw bytes
        self.sections = sections or {}  # section type -> raw bytes
        self.pad = pad  # original bytes after the data (not always zeros); None = zero fill


class LucaPak:
    def __init__(self):
        self.id_start = 0
        self.block_size = 2048
        self.reserved = b"\x00" * 16  # 0x10..0x1F, copied verbatim
        self.flags = 0x06
        self.section_types = []  # [(type, element_size)] in header order
        self.meta_size = 0
        self.name_prefix = b""  # bytes before the first name, e.g. b"PARTS/\0" (the engine looks up "PARTS/<name>")
        self.entries = []

    @classmethod
    def read(cls, path):
        pak = cls()
        with open(path, "rb") as f:
            raw = f.read()
        data_offset, count, pak.id_start, pak.block_size = struct.unpack_from("<IIII", raw, 0)
        pak.reserved = raw[0x10:0x20]
        nsec, pak.flags = raw[0x20], raw[0x21]
        pos = 0x22
        sec_offsets = []
        for _ in range(nsec):
            stype, esize, off = struct.unpack_from("<BBI", raw, pos)
            pak.section_types.append((stype, esize))
            sec_offsets.append(off)
            pos += 6
        pos = (pos + 3) & ~3
        names_offset = struct.unpack_from("<I", raw, pos)[0]
        index = pos + 4
        if pak.flags & 1 and count:
            pak.meta_size = (names_offset - (index + 8 * count)) // count
        pak.name_prefix = raw[index + (8 + pak.meta_size) * count : names_offset]

        names = []
        p = names_offset
        for _ in range(count):
            end = raw.index(b"\x00", p)
            names.append(raw[p:end].decode("utf-8"))
            p = end + 1

        spans = [struct.unpack_from("<II", raw, index + 8 * i) for i in range(count)]
        for i, (blk, size) in enumerate(spans):
            off = blk * pak.block_size
            end = spans[i + 1][0] * pak.block_size if i + 1 < count else len(raw)
            m0 = index + 8 * count + pak.meta_size * i
            secs = {}
            for (stype, esize), soff in zip(pak.section_types, sec_offsets):
                secs[stype] = raw[soff + esize * i : soff + esize * (i + 1)]
            pak.entries.append(
                Entry(names[i], raw[off : off + size], raw[m0 : m0 + pak.meta_size], secs, raw[off + size : end])
            )
        return pak

    def id_of(self, name):
        for i, e in enumerate(self.entries):
            if e.name == name:
                return self.id_start + i
        raise KeyError(name)

    def name_of(self, res_id):
        i = res_id - self.id_start
        return self.entries[i].name if 0 <= i < len(self.entries) else None

    def build(self) -> bytes:
        count = len(self.entries)
        bs = self.block_size
        nsec = len(self.section_types)
        pos = (0x22 + 6 * nsec + 3) & ~3
        index = pos + 4
        meta_start = index + 8 * count
        names_offset = meta_start + self.meta_size * count + len(self.name_prefix)
        names = b"".join(e.name.encode("utf-8") + b"\x00" for e in self.entries)
        sec_offsets = []
        p = names_offset + len(names)
        for _, esize in self.section_types:
            sec_offsets.append(p)
            p += esize * count
        data_offset = (p + bs - 1) // bs * bs

        head = bytearray(data_offset)
        struct.pack_into("<IIII", head, 0, data_offset, count, self.id_start, bs)
        head[0x10:0x20] = self.reserved
        head[0x20] = nsec
        head[0x21] = self.flags
        for k, ((stype, esize), soff) in enumerate(zip(self.section_types, sec_offsets)):
            struct.pack_into("<BBI", head, 0x22 + 6 * k, stype, esize, soff)
        struct.pack_into("<I", head, pos, names_offset)
        head[names_offset - len(self.name_prefix) : names_offset] = self.name_prefix
        head[names_offset : names_offset + len(names)] = names

        body = bytearray()
        blk = data_offset // bs
        for i, e in enumerate(self.entries):
            struct.pack_into("<II", head, index + 8 * i, blk, len(e.data))
            if self.meta_size:
                head[meta_start + self.meta_size * i : meta_start + self.meta_size * (i + 1)] = e.meta.ljust(self.meta_size, b"\x00")
            for (stype, esize), soff in zip(self.section_types, sec_offsets):
                val = e.sections.get(stype, b"").ljust(esize, b"\x00")[:esize]
                head[soff + esize * i : soff + esize * (i + 1)] = val
            body += e.data
            pad = (-len(e.data)) % bs
            last = i == count - 1
            if e.pad is not None and (len(e.pad) == pad or (last and len(e.pad) < bs)):
                body += e.pad  # keep the original filler (the last entry may be unpadded)
            else:
                body += b"\x00" * pad
            blk += (len(e.data) + pad) // bs
        return bytes(head) + bytes(body)

    def write(self, path):
        with open(path, "wb") as f:
            f.write(self.build())


def read_index(path):
    """Return (id_start, [names]) reading only the header (fast for large archives)."""
    with open(path, "rb") as f:
        data_offset = struct.unpack("<I", f.read(4))[0]
        f.seek(0)
        raw = f.read(data_offset)
    count, id_start = struct.unpack_from("<II", raw, 4)
    pos = (0x22 + 6 * raw[0x20] + 3) & ~3
    p = struct.unpack_from("<I", raw, pos)[0]
    names = []
    for _ in range(count):
        end = raw.index(b"\x00", p)
        names.append(raw[p:end].decode("utf-8"))
        p = end + 1
    return id_start, names


def append_missing(base, donor, remap_parent=True):
    """
    Append to `base` every donor entry whose name base lacks, keeping base's
    entries and resource IDs unchanged. In image archives section 0x01 is the
    parent image ID and is remapped by name (remap_parent); in voice archives
    it is a per-clip value and is copied. Hashes are recomputed.
    Returns the list of appended entries.
    """
    have = {e.name for e in base.entries}
    types = dict(base.section_types)
    added = []
    for e in donor.entries:
        if e.name not in have:
            secs = {t: v for t, v in e.sections.items() if t in types}
            added.append(Entry(e.name, e.data, e.meta, secs))
    base.entries.extend(added)
    new_ids = {e.name: base.id_start + i for i, e in enumerate(base.entries)}
    for e in added:
        if remap_parent and SEC_PARENT in types:
            old = int.from_bytes(e.sections.get(SEC_PARENT, b""), "little")
            if old:
                pname = donor.name_of(old)
                if pname not in new_ids:
                    raise ValueError(f"parent {pname} of {e.name} is not in the output archive")
                e.sections[SEC_PARENT] = new_ids[pname].to_bytes(types[SEC_PARENT], "little")
        if SEC_HASH in types:
            e.sections[SEC_HASH] = xxh64(e.data)
    return added


def _donor_entry(base, donor, name):
    """Copy of donor entry `name` with its parent ID remapped to base numbering."""
    types = dict(base.section_types)
    src = next(e for e in donor.entries if e.name == name)
    secs = {t: b"\x00" * types[t] for t in types}
    for t, v in src.sections.items():
        if t in types:
            secs[t] = v
    if SEC_PARENT in types:
        old = int.from_bytes(src.sections.get(SEC_PARENT, b""), "little")
        pname = donor.name_of(old) if old else None
        secs[SEC_PARENT] = (base.id_of(pname) if pname else 0).to_bytes(types[SEC_PARENT], "little")
    if SEC_HASH in types:
        secs[SEC_HASH] = xxh64(src.data)
    return src, secs


def replace_from(base, donor, names):
    """
    Overwrite base entries `names` in place (same index, same resource ID) with
    the donor's data, metadata and parent (remapped by name). Used for images the
    Steam release censored by editing them. Returns the replaced names.
    """
    by = {e.name: e for e in base.entries}
    for name in names:
        src, secs = _donor_entry(base, donor, name)
        dst = by[name]
        if base.meta_size and len(src.meta) != base.meta_size:
            raise ValueError(f"{name}: metadata size differs")
        dst.data, dst.meta, dst.sections, dst.pad = src.data, src.meta or dst.meta, secs, None
    return list(names)


def append_copy(base, donor, name, new_name):
    """Append the donor's entry `name` under `new_name`; returns its resource ID."""
    src, secs = _donor_entry(base, donor, name)
    base.entries.append(Entry(new_name, src.data, src.meta, secs))
    return base.id_start + len(base.entries) - 1


def describe(path):
    pak = LucaPak.read(path)
    print(f"{path}: {len(pak.entries)} entries, ids {pak.id_start}..{pak.id_start + len(pak.entries) - 1}, "
          f"block {pak.block_size}, flags 0x{pak.flags:02X}, sections "
          + ", ".join(f"0x{t:02X}x{s}" for t, s in pak.section_types)
          + (f", meta {pak.meta_size} B/entry" if pak.meta_size else ""))
    parents = {}
    for i, e in enumerate(pak.entries):
        par = int.from_bytes(e.sections.get(SEC_PARENT, b""), "little")
        parents[e.name] = pak.name_of(par) if par else ""
        print(f"  {pak.id_start + i:6d}  {e.name:24s} {len(e.data):10d}  parent={parents[e.name]}")


def unpack(path, out_dir):
    """Write every entry to out_dir/<name> (names are flat in all known archives)."""
    import os

    pak = LucaPak.read(path)
    os.makedirs(out_dir, exist_ok=True)
    for e in pak.entries:
        with open(os.path.join(out_dir, e.name), "wb") as f:
            f.write(e.data)
    print(f"{path}: {len(pak.entries)} entries -> {out_dir}")


def compare(path_a, path_b):
    """Compare two archives entry by entry (names, ids, data). Returns the number of differences."""
    a, b = LucaPak.read(path_a), LucaPak.read(path_b)
    ia = {e.name: (a.id_start + i, e) for i, e in enumerate(a.entries)}
    ib = {e.name: (b.id_start + i, e) for i, e in enumerate(b.entries)}
    only_a, only_b = sorted(set(ia) - set(ib)), sorted(set(ib) - set(ia))
    moved = sorted(n for n in set(ia) & set(ib) if ia[n][0] != ib[n][0])
    changed = sorted(n for n in set(ia) & set(ib) if ia[n][1].data != ib[n][1].data)
    print(f"A: {path_a} ({len(a.entries)} entries, ids from {a.id_start})")
    print(f"B: {path_b} ({len(b.entries)} entries, ids from {b.id_start})")
    for label, names in (("only in A", only_a), ("only in B", only_b), ("different resource ID", moved), ("different data", changed)):
        print(f"  {label}: {len(names)}" + (f"  {', '.join(names[:20])}{' ...' if len(names) > 20 else ''}" if names else ""))
    return len(only_a) + len(only_b) + len(moved) + len(changed)


USAGE = """Usage: python -m cartagra_patch.lucapak <command> ...
  list <pak>               list entries with resource IDs and parents
  roundtrip <pak>          check that read + build reproduces the file byte for byte
  unpack <pak> <out_dir>   write every entry to a file
  compare <pak_a> <pak_b>  compare two archives (names, resource IDs, data)

There is deliberately no "pack from a directory" command: a new archive must keep
the original header, sections and entry order (resource IDs), so archives are
built by modifying a copy of the original (see cartagra_patch/pipeline.py)."""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    nargs = {"list": 1, "roundtrip": 1, "unpack": 2, "compare": 2}
    if not argv or argv[0] not in nargs or len(argv) != nargs[argv[0]] + 1:
        print(USAGE)
        return 1
    cmd, args = argv[0], argv[1:]
    if cmd == "list":
        describe(args[0])
    elif cmd == "unpack":
        unpack(args[0], args[1])
    elif cmd == "compare":
        return 2 if compare(args[0], args[1]) else 0
    else:
        with open(args[0], "rb") as f:
            orig = f.read()
        rebuilt = LucaPak.read(args[0]).build()
        same = rebuilt == orig
        print(f"{args[0]}: {'identical' if same else 'DIFFERENT'} ({len(orig):,} vs {len(rebuilt):,} bytes)")
        if not same:
            first = next((i for i in range(min(len(orig), len(rebuilt))) if orig[i] != rebuilt[i]), None)
            print(f"  first difference at 0x{first:X}" if first is not None else "  differs in length only")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
