#!/usr/bin/env python3
"""
Decoder for LucaSystem CZ0/CZ1/CZ3/CZ4 images (Cartagra REBIRTH FHD), after
Cartagra_FHD_CHS/image/czximage/cz2image.cpp, and a CZ0 encoder for
replacement images.

Header (little-endian):
  0x00 "CZ4\0" | u32 header_length | u16 width | u16 height | u16 bits (32)
  u16 ?(4) | u16 offset_x | u16 offset_y | u16 width | u16 height (again)
  u16 canvas_width | u16 canvas_height | ...
Variants ("k" images) are partial overlays placed at (offset_x, offset_y)
on their parent image (PAK section 0x01). The stored width is rounded up to
a multiple of 8; the second width is the visible one.

CZ0 (64-byte header): uncompressed RGBA rows. The engine loads it wherever
another CZ type is expected: the Russian release replaced the title menu
(CZ1 in the Japanese release) with CZ0 images.

CZ2 (the font sheets): a 256 x RGBA palette, then LZW blocks (u32 count, count x (u32
compressed bytes, u32 raw size)) of bit-packed codes; decoded and encoded by decode_cz2/encode_cz2.

CZ1/CZ3/CZ4 data: u32 block count, block_count x (u32 code count, u32 raw size), then the
16-bit LZW codes of every block (dictionary starts with the 256 bytes). The
decompressed stream is RGB (CZ4) or RGBA (CZ3) rows followed (CZ4) by an
alpha plane; rows are delta-coded against the previous row except at the
start of each of 3 horizontal bands.

Usage:
  python -m cartagra_patch.cztool png <pak> <entry> <out.png> [--composite]
  python -m cartagra_patch.cztool export <pak> <out_dir> [entry ...]
"""

import os
import struct
import sys
import zlib

CZ0_HEADER_LENGTH = 64


def header(data):
    magic = data[:4]
    hl, w, h, bits = struct.unpack_from("<IHHH", data, 4)
    ox, oy = struct.unpack_from("<HH", data, 0x10)
    cw, ch = struct.unpack_from("<HH", data, 0x18)
    return dict(magic=magic, header_length=hl, width=w, height=h, bits=bits, x=ox, y=oy, canvas=(cw, ch))


def _lzw_blocks(data, p):
    count = struct.unpack_from("<I", data, p)[0]
    p += 4
    sizes = []
    for _ in range(count):
        n, raw = struct.unpack_from("<II", data, p)
        sizes.append((n, raw))
        p += 8
    out = bytearray()
    for n, raw in sizes:
        codes = struct.unpack_from("<%dH" % n, data, p)
        p += 2 * n
        # as in cz2image.cpp: w starts as "\0" and every code (the first too) adds an entry
        table = [bytes([i]) for i in range(256)]
        w = b"\x00"
        for k in codes:
            if k < len(table):
                entry = table[k]
            elif k == len(table):
                entry = w + w[:1]
            else:
                raise ValueError("bad LZW code")
            out += entry
            table.append(w + entry[:1])
            w = entry
    return bytes(out)


def _undelta(plane, width, height, bpp):
    stride = width * bpp
    band = -(-height // 3)
    rows = bytearray(plane[: stride * height])
    for y in range(height):
        if y % band:
            cur = memoryview(rows)[y * stride : (y + 1) * stride]
            prev = rows[(y - 1) * stride : y * stride]
            cur[:] = bytes((a + b) & 0xFF for a, b in zip(cur, prev))
    return rows


def _decode_cz1(data, hd):
    """CZ1: LZW-compressed RGBA (32 bit) or 8-bit indices into a 256 x RGBA palette."""
    w, h, p = hd["width"], hd["height"], hd["header_length"]
    if hd["bits"] == 32:
        raw = _lzw_blocks(data, p)
        if len(raw) == 4 * w * h:
            return raw
    palette = [data[p + 4 * i : p + 4 * i + 4] for i in range(256)]
    idx = _lzw_blocks(data, p + 1024)
    if len(idx) < w * h:
        raise ValueError("CZ1: short index data")
    return b"".join(palette[i] for i in idx[: w * h])


CZ2_MAX_CODES = 261885  # codes per block: the block ends when the dictionary reaches 2^18 - 3 entries


def _lzw2_decode(data, raw_size):
    """One CZ2 block: LZW codes packed LSB first, each a flag bit and 15 (flag 0) or 18 (flag 1) bits."""
    pos, acc, nacc = 0, 0, 0
    table = [bytes([i]) for i in range(256)] + [b""]  # the first new entry is 257
    out = bytearray()
    w = None
    while len(out) < raw_size:
        while nacc < 19:
            acc |= (data[pos] if pos < len(data) else 0) << nacc
            pos += 1
            nacc += 8
        k = 18 if acc & 1 else 15
        code = (acc >> 1) & ((1 << k) - 1)
        acc >>= k + 1
        nacc -= k + 1
        if code < len(table) and (code < 256 or code > 256):
            entry = table[code]
        elif w is not None and code == len(table):
            entry = w + w[:1]
        else:
            raise ValueError("CZ2: bad LZW code")
        out += entry
        if w is not None:
            table.append(w + entry[:1])
        w = entry
    return bytes(out[:raw_size])


def _lzw2_encode(raw, start):
    """Encode raw[start:] as one CZ2 block, until the dictionary is full. Returns (codes bytes, end)."""
    table = {}  # (code of a string) << 8 | next byte -> code of the longer string
    out, acc, nacc, ncodes, new = bytearray(), 0, 0, 0, 257
    code, i, n = raw[start], start + 1, len(raw)
    while True:
        longer = table.get(code << 8 | raw[i]) if i < n else None
        if longer is not None:
            code = longer
            i += 1
            continue
        acc |= ((code << 1) | (code >= 0x8000)) << nacc
        nacc += 19 if code >= 0x8000 else 16
        while nacc >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            nacc -= 8
        ncodes += 1
        if i >= n or ncodes == CZ2_MAX_CODES:
            break
        table[code << 8 | raw[i]] = new
        new += 1
        code = raw[i]
        i += 1
    if nacc:
        out.append(acc & 0xFF)
    return bytes(out), i


def decode_cz2(data, rows=None):
    """CZ2 (8-bit indices into a 256 x RGBA palette): (header, palette bytes, indices of the first `rows` rows)."""
    hd = header(data)
    p = hd["header_length"]
    palette = bytes(data[p : p + 1024])
    count = struct.unpack_from("<I", data, p + 1024)[0]
    sizes = [struct.unpack_from("<II", data, p + 1028 + 8 * i) for i in range(count)]
    p += 1028 + 8 * count
    need = hd["width"] * (hd["height"] if rows is None else rows)
    idx = bytearray()
    for n, raw in sizes:
        if len(idx) >= need:
            break
        idx += _lzw2_decode(data[p : p + n], raw)
        p += n
    if len(idx) < need:
        raise ValueError("CZ2: short index data")
    return hd, palette, bytes(idx[:need])


def encode_cz2(original, palette, width, height, indices):
    """A CZ2 image with the given size and indices, keeping the rest of `original`'s CZ2 header."""
    blocks, pos = [], 0
    while pos < len(indices):
        codes, end = _lzw2_encode(indices, pos)
        blocks.append((codes, end - pos))
        pos = end
    head = bytearray(original[: struct.unpack_from("<I", original, 4)[0]])
    struct.pack_into("<HH", head, 8, width, height)
    return (bytes(head) + palette + struct.pack("<I", len(blocks))
            + b"".join(struct.pack("<II", len(c), n) for c, n in blocks) + b"".join(c for c, _ in blocks))


def decode(data):
    """Return (header dict, RGBA bytes of width x height)."""
    hd = header(data)
    w, h = hd["width"], hd["height"]
    if hd["magic"] == b"CZ2\x00":
        _, palette, idx = decode_cz2(data)
        return hd, b"".join(palette[4 * i : 4 * i + 4] for i in idx)
    if hd["magic"] == b"CZ0\x00":
        p = hd["header_length"]
        if hd["bits"] != 32 or len(data) < p + 4 * w * h:
            raise ValueError("CZ0: only 32-bit images are supported")
        return hd, bytes(data[p : p + 4 * w * h])
    if hd["magic"] == b"CZ1\x00":
        return hd, _decode_cz1(data, hd)
    if hd["magic"] not in (b"CZ4\x00", b"CZ3\x00"):
        raise ValueError(f"unsupported {hd['magic']!r}")
    raw = _lzw_blocks(data, hd["header_length"])
    if hd["magic"] == b"CZ3\x00":
        return hd, bytes(_undelta(raw, w, h, 4))
    rgb = _undelta(raw, w, h, 3)
    alpha = _undelta(raw[3 * w * h :], w, h, 1)
    rgba = bytearray(4 * w * h)
    rgba[0::4], rgba[1::4], rgba[2::4] = rgb[0::3], rgb[1::3], rgb[2::3]
    rgba[3::4] = alpha
    return hd, bytes(rgba)


def encode_cz0(original, rgba):
    """
    A CZ0 image with the pixels `rgba` (the stored width x height of `original`, RGBA) that keeps
    the rest of `original`'s header (placement, visible size), whatever CZ type `original` is.
    """
    hd = header(original)
    w, h = hd["width"], hd["height"]
    if len(rgba) != 4 * w * h:
        raise ValueError(f"expected {w}x{h} RGBA pixels")
    head = bytearray(original[: min(hd["header_length"], CZ0_HEADER_LENGTH)])
    head += b"\0" * (CZ0_HEADER_LENGTH - len(head))
    head[0:4] = b"CZ0\x00"
    struct.pack_into("<IHHH", head, 4, CZ0_HEADER_LENGTH, w, h, 32)
    return bytes(head) + bytes(rgba)


def composite(base_rgba, base_w, over_rgba, over_w, over_h, x, y):
    """Alpha-blend an overlay onto a copy of the base image."""
    out = bytearray(base_rgba)
    for row in range(over_h):
        for col in range(over_w):
            s = 4 * (row * over_w + col)
            a = over_rgba[s + 3]
            if not a:
                continue
            d = 4 * ((y + row) * base_w + x + col)
            for c in range(3):
                out[d + c] = (over_rgba[s + c] * a + out[d + c] * (255 - a)) // 255
            out[d + 3] = max(out[d + 3], a)
    return bytes(out)


def write_png(path, rgba, w, h):
    raw = b"".join(b"\x00" + rgba[y * 4 * w : (y + 1) * 4 * w] for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def read_png(path):
    """(width, height, RGBA bytes) of an 8-bit non-interlaced PNG (RGBA, RGB, grey, grey+alpha or palette)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG file")
    p, idat, palette, trns, ihdr = 8, bytearray(), b"", b"", None
    while p + 8 <= len(data):
        n, kind = struct.unpack_from(">I4s", data, p)
        body = data[p + 8 : p + 8 + n]
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        p += 12 + n
    if ihdr is None:
        raise ValueError(f"{path}: no IHDR chunk")
    w, h, depth, ctype, _, _, interlace = ihdr
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if depth != 8 or interlace or ch is None:
        raise ValueError(f"{path}: only 8-bit, non-interlaced PNGs are supported (save it as 32-bit RGBA)")
    raw = zlib.decompress(bytes(idat))
    stride = w * ch
    rows, prev = bytearray(), bytearray(stride)
    for y in range(h):
        ft = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)])
        if ft == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif ft == 2:
            line = bytearray((a + b) & 0xFF for a, b in zip(line, prev))
        elif ft == 3:
            for i in range(stride):
                line[i] = (line[i] + ((line[i - ch] if i >= ch else 0) + prev[i]) // 2) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b, c = prev[i], prev[i - ch] if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        elif ft:
            raise ValueError(f"{path}: bad PNG filter {ft}")
        rows += line
        prev = line
    if ctype == 6:
        return w, h, bytes(rows)
    out = bytearray(4 * w * h)
    if ctype == 2:
        out[0::4], out[1::4], out[2::4] = rows[0::3], rows[1::3], rows[2::3]
        out[3::4] = b"\xff" * (w * h)
    elif ctype in (0, 4):
        grey = rows[0::ch]
        out[0::4], out[1::4], out[2::4] = grey, grey, grey
        out[3::4] = rows[1::2] if ctype == 4 else b"\xff" * (w * h)
    else:
        alpha = trns + b"\xff" * (256 - len(trns))
        colors = [palette[3 * k : 3 * k + 3] + alpha[k : k + 1] for k in range(len(palette) // 3)]
        out = bytearray(b"".join(colors[k] for k in rows))
    return w, h, bytes(out)


def export(pak, out_dir, names=None):
    """Write the images of an archive as PNGs (stored size, before placement); returns [(name, w, h)]."""
    os.makedirs(out_dir, exist_ok=True)
    done = []
    for e in pak.entries:
        if (names and e.name not in names) or e.data[:2] != b"CZ":
            continue
        try:
            hd, rgba = decode(e.data)
        except ValueError:
            continue
        write_png(os.path.join(out_dir, e.name + ".png"), rgba, hd["width"], hd["height"])
        done.append((e.name, hd["width"], hd["height"]))
    return done


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "export":
        from .lucapak import LucaPak

        done = export(LucaPak.read(sys.argv[2]), sys.argv[3], set(sys.argv[4:]) or None)
        print(f"{len(done)} images written to {sys.argv[3]}")
        return
    if len(sys.argv) < 5 or sys.argv[1] != "png":
        print(__doc__)
        sys.exit(1)
    from .lucapak import LucaPak, SEC_PARENT

    pak = LucaPak.read(sys.argv[2])
    by = {e.name: e for e in pak.entries}
    e = by[sys.argv[3]]
    hd, rgba = decode(e.data)
    w, h = hd["width"], hd["height"]
    parent = int.from_bytes(e.sections.get(SEC_PARENT, b""), "little")
    if "--composite" in sys.argv and parent:
        ph, prgba = decode(by[pak.name_of(parent)].data)
        rgba = composite(prgba, ph["width"], rgba, w, h, hd["x"], hd["y"])
        w, h = ph["width"], ph["height"]
    write_png(sys.argv[4], rgba, w, h)
    print(f"{sys.argv[3]}: {hd['magic'][:3].decode()} {hd['width']}x{hd['height']} at ({hd['x']},{hd['y']}) -> {sys.argv[4]}")


if __name__ == "__main__":
    main()
