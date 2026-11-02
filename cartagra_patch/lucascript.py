#!/usr/bin/env python3
"""
Bytecode helpers for Cartagra REBIRTH FHD (LucaSystem) scene scripts.

A script is a stream of instructions:
    u16 length (header included, padding excluded), u8 opcode, u8 flags,
    [u16 debug line number if flags & 1], body..., one zero pad byte if length is odd.

Jump targets are absolute byte offsets inside the same script. Opcodes that
carry them have the same numbers in the JP and RUS (Steam) builds:
    15  GOTO        body: u32 target
    18  GOSUB-like  body: str, u32 target
    19  IF          body: str, u32 target
    16  choice jump body: str, u16, u32 target, (u16, u32 target)*
where "str" is i16 -n, n bytes (Shift-JIS/ASCII), NUL.

See TECHNICAL_NOTES.md, "Scene Scripts".
"""

import struct

OP_GOTO = 15
OP_CHOICE_JUMP = 16
OP_GOSUB = 18
OP_IF = 19
OP_JUMP_SCRIPT = 21
JUMP_OPS = (OP_GOTO, OP_CHOICE_JUMP, OP_GOSUB, OP_IF)


class Instr:
    def __init__(self, op, flags, line, body, offset=None):
        self.op = op
        self.flags = flags
        self.line = line  # debug line number (flags & 1), else None
        self.body = body
        self.offset = offset  # offset in the source script
        self.targets = []  # source offsets this instruction jumps to (filled by jump_fields)

    def encode(self):
        head = struct.pack("<H", self.line) if self.flags & 1 else b""
        length = 4 + len(head) + len(self.body)
        raw = struct.pack("<HBB", length, self.op, self.flags) + head + self.body
        return raw + (b"\x00" if length & 1 else b"")


def parse(data):
    out = []
    pos = 0
    while pos + 4 <= len(data):
        length, op, flags = struct.unpack_from("<HBB", data, pos)
        if length < 4:
            raise ValueError(f"bad instruction length {length} at 0x{pos:X}")
        p = pos + 4
        line = None
        if flags & 1:
            line = struct.unpack_from("<H", data, p)[0]
            p += 2
        out.append(Instr(op, flags, line, data[p : pos + length], pos))
        pos += length + (length & 1)
    if pos != len(data):
        raise ValueError(f"trailing bytes after 0x{pos:X}")
    return out


def read_str(body, p):
    """Return (bytes, next offset) for an i16 -n length-prefixed, NUL-terminated string."""
    n = -struct.unpack_from("<h", body, p)[0]
    if n < 0 or body[p + 2 + n] != 0:
        raise ValueError(f"not a negative-length string at {p}")
    return body[p + 2 : p + 2 + n], p + 3 + n


def make_str(raw):
    return struct.pack("<h", -len(raw)) + raw + b"\x00"


def jump_fields(ins):
    """Offsets inside ins.body that hold u32 jump targets."""
    if ins.op == OP_GOTO:
        return [0]
    if ins.op in (OP_GOSUB, OP_IF):
        _, p = read_str(ins.body, 0)
        return [p]
    if ins.op == OP_CHOICE_JUMP:
        _, p = read_str(ins.body, 0)
        fields = []
        p += 2
        while p + 4 <= len(ins.body):
            fields.append(p)
            p += 6
        return fields
    return []


def assemble(instrs, valid_targets=None):
    """
    Encode instructions, rewriting jump targets from source offsets to new offsets.
    Each instruction's jump fields must point at a source offset of an instruction
    in the list (or in valid_targets: {source offset -> instruction that replaces it}).
    """
    new_off = {}
    pos = 0
    for ins in instrs:
        if ins.offset is not None:
            new_off[ins.offset] = pos
        pos += len(ins.encode())
    for src, repl in (valid_targets or {}).items():
        new_off.setdefault(src, new_off[repl.offset])

    out = bytearray()
    for ins in instrs:
        body = bytearray(ins.body)
        for f in jump_fields(ins):
            src = struct.unpack_from("<I", body, f)[0]
            if src not in new_off:
                raise ValueError(f"jump target 0x{src:X} (op {ins.op} at 0x{ins.offset or 0:X}) is not an instruction start")
            struct.pack_into("<I", body, f, new_off[src])
        ins.body = bytes(body)
        out += ins.encode()
    return bytes(out)


def lzw_unpack(data):
    """
    Contents of an "LZW\\0" metadata entry (_scr_label): u32 size, u32 chunk count, then per
    chunk u32 code count, u32 output size and 16-bit codes; new codes start at 257 in each chunk.
    """
    if data[:4] != b"LZW\0":
        raise ValueError("not an LZW entry")
    total, chunks = struct.unpack_from("<II", data, 4)
    p, out = 12, bytearray()
    for _ in range(chunks):
        count, size = struct.unpack_from("<II", data, p)
        codes = struct.unpack_from(f"<{count}H", data, p + 8)
        p += 8 + 2 * count
        table, chunk, prev, nxt = {i: bytes([i]) for i in range(256)}, bytearray(), None, 257
        for c in codes:
            if c in table:
                cur = table[c]
            elif prev is not None and c == nxt:
                cur = prev + prev[:1]
            else:
                raise ValueError(f"bad LZW code {c}")
            if prev is not None:
                table[nxt] = prev + cur[:1]
                nxt += 1
            chunk += cur
            prev = cur
        out += chunk[:size]
    if len(out) != total:
        raise ValueError(f"LZW entry: {len(out)} bytes decoded, header says {total}")
    return bytes(out)


def lzw_pack(raw):
    """Inverse of lzw_unpack, in one chunk (reproduces the original _scr_label entries byte for byte)."""
    table, codes, w, nxt = {bytes([i]): i for i in range(256)}, [], raw[:1], 257
    for c in raw[1:]:
        wc = w + bytes([c])
        if wc in table:
            w = wc
            continue
        codes.append(table[w])
        table[wc] = nxt
        nxt += 1
        w = bytes([c])
    if w:
        codes.append(table[w])
    if nxt > 0x10000:
        raise ValueError("too much data for one LZW chunk")
    return b"LZW\0" + struct.pack("<IIII", len(raw), 1, len(codes), len(raw)) + struct.pack(f"<{len(codes)}H", *codes)


def check(data):
    """Parse a script and verify every jump target is an instruction start."""
    instrs = parse(data)
    starts = {i.offset for i in instrs}
    bad = []
    for ins in instrs:
        for f in jump_fields(ins):
            t = struct.unpack_from("<I", ins.body, f)[0]
            if t not in starts:
                bad.append((ins.offset, ins.op, t))
    return instrs, bad
